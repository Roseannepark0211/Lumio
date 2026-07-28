from __future__ import annotations

import json
import logging
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import http.cookiejar
import requests
import yt_dlp

from .utils.config import get_cookie_path, get_file_conflict_policy, get_platform_mode, get_storage_mode
from .utils.url_parser import Platform, parse_url
from .providers.registry import get_provider_for
from .utils.media_utils import MediaItem, VideoInfo

logger = logging.getLogger(__name__)

# --- Conflict ask callback (set by Downloader instance) ---
_conflict_ask_handler = None  # Callable[[Path], str] — returns "rename"/"skip"/"overwrite"

_DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}

def _ask_user_conflict(file_path: Path) -> str:
    """Ask user how to handle a file conflict. Blocks until response."""
    if _conflict_ask_handler:
        return _conflict_ask_handler(file_path)
    return "rename"  # fallback


def _resolve_conflict_path(path: Path, policy: str) -> Path | None:
    """Resolve file path based on conflict policy.

    Returns the resolved path, or None if the file should be skipped.
    Ignores .part files (partial downloads) to allow resume.
    """
    if policy == "overwrite" or not path.exists():
        return path
    if policy == "skip":
        return None
    if policy == "ask":
        choice = _ask_user_conflict(path)
        if choice == "overwrite":
            return path
        if choice == "skip":
            return None
    # rename: append (1), (2), ... — skip .part files
    stem, suffix = path.stem, path.suffix
    counter = 1
    while True:
        new_path = path.parent / f"{stem} ({counter}){suffix}"
        if not new_path.exists():
            return new_path
        counter += 1


def _resolve_conflict_stem(out_dir: Path, stem: str, policy: str) -> str | None:
    """For yt-dlp outtmpl: check if any file matching stem.* exists.

    Returns the resolved stem, or None if should skip.
    """
    if policy == "overwrite":
        return stem
    existing = list(out_dir.glob(f"{stem}.*"))
    if not existing:
        return stem
    if policy == "skip":
        return None
    if policy == "ask":
        example = existing[0]
        choice = _ask_user_conflict(example)
        if choice == "overwrite":
            return stem
        if choice == "skip":
            return None
        # "rename" fallback
    # rename
    counter = 1
    while True:
        new_stem = f"{stem} ({counter})"
        if not list(out_dir.glob(f"{new_stem}.*")):
            return new_stem
        counter += 1


def _cleanup_empty_dir(path: Path):
    """Remove directory if empty (and parent if also empty)."""
    try:
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    except OSError:
        pass


def _resume_headers(file_path: Path) -> dict:
    """Return HTTP headers for resume download if partial file exists."""
    if file_path.exists() and file_path.stat().st_size > 0:
        return {"Range": f"bytes={file_path.stat().st_size}-"}
    return {}


def _resolve_output_dir(task) -> Path:
    """Resolve output directory based on current storage mode.

    For batch tasks in organized mode, returns a batch-level subdirectory.
    Always reads storage mode at call time (download time).
    Does NOT create the directory — caller is responsible for mkdir.
    """
    base = Path(task.output_dir)
    if get_storage_mode() != "organized" or not task.batch_id:
        return base
    platform = (task.platform or "download").capitalize()
    author = _safe_filename(task.author or "unknown")[:30]
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    return base / f"{platform}_{author}_{date_str}"


def _find_ffmpeg() -> str | None:
    """Locate ffmpeg: system PATH first, then imageio-ffmpeg bundle."""
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None



@dataclass
class DownloadTask:
    url: str
    format_id: str | None
    output_dir: Path
    custom_name: str = ""
    author: str = ""
    post_time: str = ""
    format_type: str = ""  # "video" | "audio" | "combined" | ""
    platform: str = ""
    batch_id: str = ""
    direct_url: str = ""  # Pre-resolved download URL (e.g. from X-Sou)
    media_items_json: str = ""  # Pre-resolved media items JSON (Apify, avoids re-fetching)
    status: str = "pending"
    progress: float = 0.0
    speed: str = ""
    filename: str = ""
    error: str = ""
    _cancelled: bool = field(default=False, repr=False)


# ---- YouTube ----

def _yt_opts(cookie_file: Path | None = None) -> dict:
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "continuedl": True,
        "keep_fragments": True,
        "socket_timeout": 15,
    }
    if cookie_file and cookie_file.exists():
        opts["cookiefile"] = str(cookie_file)
    ffmpeg = _find_ffmpeg()
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg  # full path to binary
    return opts


# ---- Instagram ----

def _ig_shortcode_from_url(url: str) -> str:
    """Extract Instagram shortcode from a post/reel URL."""
    parts = url.rstrip("/").split("/")
    shortcode = parts[-1]
    for i, p in enumerate(parts):
        if p in ("reel", "p") and i + 1 < len(parts):
            shortcode = parts[i + 1]
            break
    return shortcode


def _ig_shortcode_to_media_id(shortcode: str) -> str:
    """Convert Instagram shortcode to numeric media_id."""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    media_id = 0
    for ch in shortcode:
        media_id = media_id * 64 + alphabet.index(ch)
    return str(media_id)


def _ig_get_media_info(shortcode: str) -> dict:
    """Fetch post info via mobile API, return media dict."""
    session = _ig_api_session()
    media_id = _ig_shortcode_to_media_id(shortcode)
    url = f"https://i.instagram.com/api/v1/media/{media_id}/info/"
    resp = session.get(url, timeout=15)
    if resp.status_code == 429:
        import time
        time.sleep(3)
        resp = session.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json().get("items", [{}])[0]


def _ig_best_video_url(video_versions: list[dict]) -> str:
    """Pick the highest resolution video URL from Instagram's video_versions."""
    if not video_versions:
        return ""
    best = max(video_versions, key=lambda v: v.get("width", 0))
    return best.get("url", "")


def _ig_best_image_url(candidates: list[dict]) -> str:
    """Pick the highest resolution image URL from Instagram's image candidates."""
    if not candidates:
        return ""
    best = max(candidates, key=lambda c: c.get("width", 0))
    return best.get("url", "")


def _ig_media_to_items(media: dict) -> list[MediaItem]:
    """Convert mobile API media dict to MediaItem list."""
    items: list[MediaItem] = []
    carousel = media.get("carousel_media")
    if carousel:
        for i, cm in enumerate(carousel):
            if cm.get("video_versions"):
                url_str = _ig_best_video_url(cm["video_versions"])
                items.append(MediaItem(url=url_str, is_video=True, index=i))
            else:
                candidates = cm.get("image_versions2", {}).get("candidates", [])
                url_str = _ig_best_image_url(candidates)
                items.append(MediaItem(url=url_str, is_video=False, index=i))
    elif media.get("video_versions"):
        url_str = _ig_best_video_url(media["video_versions"])
        items.append(MediaItem(url=url_str, is_video=True, index=0))
    else:
        candidates = media.get("image_versions2", {}).get("candidates", [])
        url_str = _ig_best_image_url(candidates)
        items.append(MediaItem(url=url_str, is_video=False, index=0))
    return items


def _ig_api_session() -> requests.Session:
    """Create a requests.Session with cookies and standard IG headers."""
    session = requests.Session()
    session.trust_env = True  # respect system proxy (Windows registry, env vars)
    cookie_path = get_cookie_path()
    csrf_token = ""
    if cookie_path and Path(cookie_path).exists():
        cj = http.cookiejar.MozillaCookieJar(str(cookie_path))
        cj.load(ignore_discard=True, ignore_expires=True)
        session.cookies = cj
        for c in cj:
            if c.name == "csrftoken":
                csrf_token = c.value
                break
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-IG-App-ID": "936619743392459",
        "X-CSRFToken": csrf_token,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "*/*",
    })
    return session


# ---- X (Twitter) ----

_X_BEARER = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"

_X_GRAPHQL_TWEET = "2ICDjqPd81tulZcYrtpTuQ/TweetResultByRestId"
_X_GRAPHQL_USER = "xc8f1g7BYqr6VTzTbvNlGw/UserByScreenName"

_X_TWEET_FEATURES = {
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "tweetypie_unmention_optimization_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": False,
    "tweet_awards_web_tipping_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "responsive_web_media_download_video_enabled": False,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}

_X_USER_FEATURES = {
    "hidden_profile_subscriptions_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "subscriptions_verification_info_is_identity_verified_enabled": True,
    "subscriptions_verification_info_verified_since_enabled": True,
    "highlights_tweets_tab_ui_enabled": True,
    "responsive_web_twitter_article_notes_tab_enabled": True,
    "subscriptions_feature_can_gift_premium": True,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
}


def _x_api_session() -> requests.Session:
    """Create a requests.Session with X cookies and headers."""
    session = requests.Session()
    session.trust_env = True
    cookie_path = get_cookie_path()
    ct0 = ""
    if cookie_path and Path(cookie_path).exists():
        cj = http.cookiejar.MozillaCookieJar(str(cookie_path))
        cj.load(ignore_discard=True, ignore_expires=True)
        session.cookies = cj
        for c in cj:
            if c.name == "ct0" and ("x.com" in c.domain or "twitter.com" in c.domain):
                ct0 = c.value
                break
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Authorization": f"Bearer {_X_BEARER}",
        "x-csrf-token": ct0,
    })
    return session


def _x_extract_tweet_media(tweet_result: dict) -> list[MediaItem]:
    """Extract MediaItem list from a GraphQL tweet result."""
    items: list[MediaItem] = []
    legacy = tweet_result.get("legacy", {})
    media_list = legacy.get("extended_entities", {}).get("media", [])
    for i, m in enumerate(media_list):
        mtype = m.get("type", "")
        if mtype == "photo":
            url = m.get("media_url_https", "")
            if url:
                # Request original quality
                url = url + "?format=jpg&name=orig"
                items.append(MediaItem(url=url, is_video=False, index=i))
        elif mtype in ("video", "animated_gif"):
            # Get best video URL
            variants = m.get("video_info", {}).get("variants", [])
            best_url = ""
            best_br = 0
            for v in variants:
                if v.get("content_type") == "video/mp4":
                    br = v.get("bitrate", 0)
                    if br > best_br:
                        best_br = br
                        best_url = v["url"]
            if not best_url and variants:
                best_url = variants[0].get("url", "")
            if best_url:
                items.append(MediaItem(url=best_url, is_video=True, index=i))
    return items


def _x_get_tweet_info(session: requests.Session, tweet_id: str) -> dict:
    """Fetch tweet data via GraphQL TweetResultByRestId."""
    variables = json.dumps({
        "tweetId": tweet_id,
        "withCommunity": False,
        "includePromotedContent": False,
        "withVoice": False,
    })
    features = json.dumps(_X_TWEET_FEATURES)
    fieldToggles = json.dumps({"withArticleRichContentState": False})
    resp = session.get(
        f"https://x.com/i/api/graphql/{_X_GRAPHQL_TWEET}",
        params={"variables": variables, "features": features, "fieldToggles": fieldToggles},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    result = data.get("data", {}).get("tweetResult", {}).get("result", {})
    if not result:
        raise ValueError("Tweet not found or not accessible")
    typename = result.get("__typename", "")
    if typename == "TweetUnavailable":
        reason = result.get("reason", "Unknown")
        raise ValueError(f"Tweet unavailable: {reason}")
    return result


def _x_tweet_id_from_url(url: str) -> str:
    """Extract tweet ID from URL like x.com/user/status/123."""
    # Strip query params and fragments
    clean = url.split("?")[0].split("#")[0].rstrip("/")
    parts = clean.split("/")
    for i, p in enumerate(parts):
        if p == "status" and i + 1 < len(parts):
            return parts[i + 1]
    return parts[-1]


# ---- X-Sou Search API ----

from .x_sou_client import x_sou_search

# ---- Public API ----

def extract_info(url: str) -> VideoInfo:
    """V4 统一架构：所有平台都走 Provider 系统。

    优先级：缓存 → 已注册 Provider (YouTube/IG/X/国内) → Apify 兜底（仅 IG）。
    """
    # IG api 模式仍走 Apify（用户主动选择的代理模式）
    parsed = parse_url(url)
    if parsed.platform == Platform.INSTAGRAM and get_platform_mode("instagram") == "api":
        from .apify_client import get_apify_client as _get_apify_client
        return _get_apify_client().extract_post_info(url)

    # V4 统一入口：YouTube/IG/X/国内平台都走 Provider 系统
    from .providers.dispatch import resolve_via_providers as _resolve
    result = _resolve(url)
    if result is not None:
        return result
    raise ValueError(f"Unsupported URL: {url}")


def _build_format_options(info: VideoInfo) -> list[dict]:
    """Build a clean, user-friendly format list for YouTube videos."""
    options: list[dict] = [{"id": "best", "label": "Best Quality", "_type": "combined"}]

    seen_res: set[int] = set()
    video_opts: list[dict] = []
    audio_opts: list[dict] = []

    for f in info.formats:
        fid = f.get("format_id", "")
        ext = f.get("ext", "")
        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")
        height = f.get("height")
        abr = f.get("abr")
        vbr = f.get("tbr") or f.get("vbr") or 0

        if ext in ("mhtml", "json", "json3"):
            continue
        if f.get("format_note") == "storyboard":
            continue
        if vcodec == "none" and acodec == "none":
            continue

        has_video = vcodec != "none"
        has_audio = acodec != "none"

        # Combined stream (video+audio in one)
        if has_video and has_audio and height:
            if height not in seen_res:
                seen_res.add(height)
                video_opts.append({
                    "id": fid,
                    "label": f"{height}P",
                    "_type": "combined",
                    "_height": height,
                    "_vbr": vbr,
                })

        # Video-only stream
        elif has_video and height:
            if height in seen_res:
                for opt in video_opts:
                    if opt.get("_height") == height and vbr > opt.get("_vbr", 0):
                        opt["id"] = fid
                        opt["_vbr"] = vbr
                        opt["label"] = f"{height}P"
                        break
                continue
            seen_res.add(height)
            video_opts.append({
                "id": fid,
                "label": f"{height}P",
                "_type": "video",
                "_height": height,
                "_vbr": vbr,
            })

        # Audio-only stream
        elif has_audio and not has_video:
            label = f"Audio ({ext})" if not abr else f"Audio {int(abr)}kbps"
            audio_opts.append({"id": fid, "label": label, "_type": "audio"})

    video_opts.sort(key=lambda o: o.get("_height", 0), reverse=True)
    for o in video_opts:
        o.pop("_height", None)
        o.pop("_vbr", None)

    if video_opts or audio_opts:
        options.append({"id": "___sep1", "label": "─────────", "disabled": True})
        options.extend(video_opts)
    if audio_opts:
        options.append({"id": "___sep2", "label": "─────────", "disabled": True})
        options.extend(audio_opts)

    return options


# ---- Download engine ----

ProgressCallback = Callable[[DownloadTask], None]


class _CancelledError(Exception):
    pass


def _safe_filename(name: str) -> str:
    """Strip path separators and unsafe sequences to prevent path traversal."""
    for ch in '\\/:*?"<>|':
        name = name.replace(ch, "_")
    # Remove ".." path traversal sequences (preserve single dots)
    while ".." in name:
        name = name.replace("..", "_")
    return name.strip().strip(".") or "_"


def _effective_name(task: DownloadTask) -> str:
    """Return the filename stem: custom > author+timestamp > title."""
    if task.custom_name:
        name = _safe_filename(task.custom_name)
    elif task.author:
        name = _safe_filename(task.author)
    else:
        return "%(title)s"
    if task.post_time:
        name = f"{name}_{task.post_time}"
    return _safe_filename(name)


# ---- Pause-aware download (V2 queue system) ----

def _wait_pause_or_cancel(pause_event: threading.Event, task: DownloadTask) -> None:
    """阻塞等待暂停事件恢复，同时定期检查取消标志。

    旧实现 pause_event.wait() 无超时，导致暂停期间 cancel 永远无法生效
    （线程卡在 wait() 无法检测 _cancelled）。改用 100ms 超时循环。
    """
    while not pause_event.wait(timeout=0.1):
        if task._cancelled:
            raise _CancelledError()
    if task._cancelled:
        raise _CancelledError()


def _download_hook_with_pause(
    task: DownloadTask,
    pause_event: threading.Event,
    on_progress: ProgressCallback | None,
):
    # 跟踪 yt-dlp 多流下载状态（bestvideo+bestaudio 会触发多次 downloading/finished）
    # 用于在第二个流的 downloading 阶段避免 progress 从 0 跳变
    # _stream_seq: 0=未开始, 1=视频流, 2=音频流, ...
    state = {"seq": 0, "last_total": 0, "last_downloaded": 0, "finished_count": 0}

    def hook(d: dict):
        if task._cancelled:
            raise _CancelledError()
        _wait_pause_or_cancel(pause_event, task)

        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)

            # 多流下载进度平滑：yt-dlp 下载 bestvideo+bestaudio 时
            # 视频流 finished → 音频流 downloading(progress=0)
            # 旧实现直接上报 0，导致 UI 从 ~100% 跳到 0%（"从0重新开始"）
            # 修复：检测到新流开始时，保留上一流的进度作为起点，
            # 后续进度按 (last_downloaded + downloaded) / (last_total + total) 计算
            if state["finished_count"] > 0 and total > 0:
                # 累积模式：把已完成的流大小计入分母和分子
                combined_total = state["last_total"] + total
                combined_downloaded = state["last_downloaded"] + downloaded
                task.progress = (combined_downloaded / combined_total * 100) if combined_total else 0
            else:
                task.progress = (downloaded / total * 100) if total else 0

            task.speed = d.get("_speed_str", "")
            task.filename = d.get("filename", "")
            task.status = "downloading"
            if on_progress:
                on_progress(task)
        elif d["status"] == "finished":
            # 不立即设置 progress=100 和 status="done"！
            # 原因：yt-dlp 多流下载会多次触发 finished（视频流→音频流→合并），
            # 旧实现设置 progress=100 + status="done" 并调用 on_progress，
            # 但 queue_manager.on_progress 跳过 "done" 状态不上报，
            # 导致：
            #   1. UI 卡在视频流最后进度（~99%）+ "下载中" 持续合并期间
            #      （"100%状态显示还是在下载中"）
            #   2. 下一个流的 downloading 从 0 上报，UI 跳变
            #      （"快速到100%然后从0重新开始"）
            # 修复：只更新 filename，记录当前流大小用于下一流进度累积，
            # 不改变 progress/status，不调用 on_progress。
            # 最终由 _yt_download_with_pause 末尾的 task.status="done" 触发 on_done。
            state["finished_count"] += 1
            state["last_total"] = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            state["last_downloaded"] = state["last_total"]  # finished 时已下载=总大小
            task.filename = d.get("filename", "")

    return hook


def _yt_download_with_pause(task, pause_event, on_progress):
    cookie = get_cookie_path()
    opts = _yt_opts(cookie)
    out_name = _effective_name(task)

    # File conflict handling
    out_dir = _resolve_output_dir(task)
    out_dir.mkdir(parents=True, exist_ok=True)
    policy = get_file_conflict_policy()
    resolved_stem = _resolve_conflict_stem(out_dir, out_name, policy)
    if resolved_stem is None:
        task.status = "done"
        task.progress = 100
        return
    out_name = resolved_stem

    opts["outtmpl"] = str(out_dir / f"{out_name}.%(ext)s")
    opts["progress_hooks"] = [_download_hook_with_pause(task, pause_event, on_progress)]

    if task.format_id and task.format_id not in ("best", "___sep"):
        if task.format_type == "video":
            opts["format"] = f"{task.format_id}+bestaudio"
        elif task.format_type == "audio":
            opts["format"] = task.format_id
        else:
            opts["format"] = task.format_id
    else:
        opts["format"] = (
            "bestvideo[ext=mp4][height<=2160]+bestaudio[ext=m4a]/"
            "bestvideo+bestaudio/"
            "best[ext=mp4]/"
            "best"
        )
    opts["merge_output_format"] = "mp4"

    task.status = "downloading"
    if on_progress:
        on_progress(task)

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([task.url])

    # Verify file exists (yt-dlp rename may fail on Windows)
    candidates = list(out_dir.glob(f"{out_name}.*"))
    candidates = [f for f in candidates if not f.suffix.endswith(".part")]
    if not candidates:
        task.status = "error"
        task.error = "下载完成但文件未生成"
        _cleanup_empty_dir(out_dir)
        return
    task.filename = str(candidates[0])
    task.status = "done"
    task.progress = 100


def _ig_download_with_pause(task, pause_event, on_progress):
    shortcode = _ig_shortcode_from_url(task.url)

    media = _ig_get_media_info(shortcode)

    task.status = "downloading"
    if on_progress:
        on_progress(task)

    out_dir = _resolve_output_dir(task)

    # Organized mode: create per-post subdirectory
    post_out_dir = out_dir
    if get_storage_mode() == "organized":
        post_stem = task.author or shortcode
        if task.post_time:
            post_stem = _safe_filename(f"{post_stem}_{task.post_time}")
        post_out_dir = out_dir / post_stem

    post_out_dir.mkdir(parents=True, exist_ok=True)

    items = _ig_media_to_items(media)

    # Build a unique stem: author_postTime (or custom_name, or shortcode)
    name_stem = _safe_filename(task.custom_name or task.author or shortcode)
    if task.post_time:
        name_stem = _safe_filename(f"{name_stem}_{task.post_time}")
    total = len(items)
    pad = len(str(total))
    policy = get_file_conflict_policy()
    downloaded_any = False
    for idx, item in enumerate(items):
        ext = "mp4" if item.is_video else "jpg"
        suffix = f"_{str(idx + 1).zfill(pad)}" if total > 1 else ""
        filename = post_out_dir / f"{name_stem}{suffix}.{ext}"

        # IG: skip only if complete file exists and policy says skip
        # Partial files are kept for resume via Range header
        if filename.exists() and policy == "skip":
            continue

        resp = requests.get(item.url, stream=True, timeout=30,
                            headers=_resume_headers(filename))
        try:
            # Server supports resume if 206, otherwise start fresh
            is_resume = resp.status_code == 206
            if resp.status_code == 416:
                # Range not satisfiable — file already complete
                continue
            resp.raise_for_status()

            total_size = int(resp.headers.get("content-length", 0))
            if is_resume:
                downloaded = filename.stat().st_size
                total_size += downloaded
            else:
                downloaded = 0

            try:
                with open(filename, "ab" if is_resume else "wb") as f:
                    for chunk in resp.iter_content(8192):
                        _wait_pause_or_cancel(pause_event, task)
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size:
                            item_pct = downloaded / total_size * 100
                            task.progress = (idx + item_pct / 100) / total * 100
                            task.speed = f"{idx + 1}/{total}"
                            task.filename = str(filename)
                            if on_progress:
                                on_progress(task)
            except _CancelledError:
                filename.unlink(missing_ok=True)
                raise
        finally:
            resp.close()
        downloaded_any = True

    if not downloaded_any:
        _cleanup_empty_dir(post_out_dir)

    task.status = "done"
    task.progress = 100
    task.filename = str(post_out_dir)


def _apify_download_with_pause(task, pause_event, on_progress):
    """Download IG post via Apify API (replaces _ig_download_with_pause in API mode)."""
    from .apify_client import get_apify_client as _get_apify_client
    import json as _json
    # Use pre-resolved media items if available (from batch enumeration),
    # otherwise fetch via Apify Actor run.
    if task.media_items_json:
        raw_items = _json.loads(task.media_items_json)
        media_items = [MediaItem(url=i["url"], is_video=i["is_video"], index=i.get("index", 0)) for i in raw_items]
    else:
        info = _get_apify_client().extract_post_info(task.url)
        if not info.items:
            raise ValueError("Apify returned no media items")
        media_items = info.items

    task.status = "downloading"
    if on_progress:
        on_progress(task)

    out_dir = _resolve_output_dir(task)

    # Organized mode: create per-post subdirectory
    shortcode = _ig_shortcode_from_url(task.url) or "unknown"
    post_out_dir = out_dir
    if get_storage_mode() == "organized":
        post_stem = task.author or shortcode
        if task.post_time:
            post_stem = _safe_filename(f"{post_stem}_{task.post_time}")
        post_out_dir = out_dir / post_stem

    post_out_dir.mkdir(parents=True, exist_ok=True)

    items = media_items
    name_stem = _safe_filename(task.custom_name or task.author or shortcode)
    if task.post_time:
        name_stem = _safe_filename(f"{name_stem}_{task.post_time}")
    total = len(items)
    pad = len(str(total))
    policy = get_file_conflict_policy()
    downloaded_any = False

    for idx, item in enumerate(items):
        ext = "mp4" if item.is_video else "jpg"
        suffix = f"_{str(idx + 1).zfill(pad)}" if total > 1 else ""
        filename = post_out_dir / f"{name_stem}{suffix}.{ext}"

        if filename.exists() and policy == "skip":
            continue

        resp = requests.get(item.url, stream=True, timeout=30,
                            headers=_resume_headers(filename))
        try:
            is_resume = resp.status_code == 206
            if resp.status_code == 416:
                continue
            resp.raise_for_status()

            total_size = int(resp.headers.get("content-length", 0))
            if is_resume:
                downloaded = filename.stat().st_size
                total_size += downloaded
            else:
                downloaded = 0

            try:
                with open(filename, "ab" if is_resume else "wb") as f:
                    for chunk in resp.iter_content(8192):
                        _wait_pause_or_cancel(pause_event, task)
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size:
                            item_pct = downloaded / total_size * 100
                            task.progress = (idx + item_pct / 100) / total * 100
                            task.speed = f"{idx + 1}/{total}"
                            task.filename = str(filename)
                            if on_progress:
                                on_progress(task)
            except _CancelledError:
                filename.unlink(missing_ok=True)
                raise
        finally:
            resp.close()
        downloaded_any = True

    if not downloaded_any:
        _cleanup_empty_dir(post_out_dir)

    task.status = "done"
    task.progress = 100
    task.filename = str(post_out_dir)


def _x_download_with_pause(task, pause_event, on_progress):
    session = _x_api_session()
    tweet_id = _x_tweet_id_from_url(task.url)
    tweet_result = _x_get_tweet_info(session, tweet_id)
    items = _x_extract_tweet_media(tweet_result)

    out_dir = _resolve_output_dir(task)
    out_dir.mkdir(parents=True, exist_ok=True)
    policy = get_file_conflict_policy()
    out_name = _effective_name(task)

    # Single video only — use yt-dlp for format merging
    if len(items) == 1 and items[0].is_video:
        resolved_stem = _resolve_conflict_stem(out_dir, out_name, policy)
        if resolved_stem is None:
            task.status = "done"
            task.progress = 100
            return
        cookie = get_cookie_path()
        opts = _yt_opts(cookie)
        opts["outtmpl"] = str(out_dir / f"{resolved_stem}.%(ext)s")
        opts["progress_hooks"] = [_download_hook_with_pause(task, pause_event, on_progress)]
        opts["format"] = "best[ext=mp4]/best"
        opts["merge_output_format"] = "mp4"
        task.status = "downloading"
        if on_progress:
            on_progress(task)
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([task.url])
        # Verify file actually exists (yt-dlp may report "finished" before rename)
        expected = out_dir / f"{resolved_stem}.mp4"
        if not expected.exists():
            # Check for .part or other extensions
            candidates = list(out_dir.glob(f"{resolved_stem}.*"))
            if not candidates:
                task.status = "error"
                task.error = "下载完成但文件未生成"
                _cleanup_empty_dir(out_dir)
                return
        task.status = "done"
        task.progress = 100
        task.filename = str(expected) if expected.exists() else str(candidates[0])
        return

    # Multi-item (images + videos) — download each individually
    total = len(items)
    pad = len(str(total))
    downloaded_any = False

    for idx, item in enumerate(items):
        ext = "mp4" if item.is_video else "jpg"
        suffix = f"_{str(idx + 1).zfill(pad)}" if total > 1 else ""
        filename = out_dir / f"{out_name}{suffix}.{ext}"

        if filename.exists() and policy == "skip":
            continue

        resolved = _resolve_conflict_path(filename, policy)
        if resolved is None:
            continue
        filename = resolved

        if item.is_video:
            # Download video via requests with resume
            headers = _resume_headers(filename)
            resp = requests.get(item.url, stream=True, timeout=30, headers=headers)
            try:
                is_resume = resp.status_code == 206
                if resp.status_code == 416:
                    continue
                resp.raise_for_status()
                total_size = int(resp.headers.get("content-length", 0))
                if is_resume:
                    downloaded = filename.stat().st_size
                    total_size += downloaded
                else:
                    downloaded = 0
                try:
                    with open(filename, "ab" if is_resume else "wb") as f:
                        for chunk in resp.iter_content(8192):
                            _wait_pause_or_cancel(pause_event, task)
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size:
                                pct = downloaded / total_size * 100
                                task.progress = (idx + pct / 100) / total * 100
                                task.speed = f"{idx + 1}/{total}"
                                task.filename = str(filename)
                                if on_progress:
                                    on_progress(task)
                except _CancelledError:
                    filename.unlink(missing_ok=True)
                    raise
            finally:
                resp.close()
        else:
            # Download image via requests
            resp = requests.get(item.url, timeout=30)
            try:
                resp.raise_for_status()
                filename.write_bytes(resp.content)
            finally:
                resp.close()

        downloaded_any = True
        task.progress = (idx + 1) / total * 100
        task.speed = f"{idx + 1}/{total}"
        task.filename = str(filename)
        if on_progress:
            on_progress(task)

    if not downloaded_any:
        _cleanup_empty_dir(post_out_dir)

    task.status = "done"
    task.progress = 100


def _ensure_bilibili_buvid3() -> str | None:
    """获取 B 站访客 buvid3 cookie，绕过 412 Precondition Failed。

    复用 providers.bilibili._ensure_buvid3 实现（已缓存）。
    yt-dlp 的 BiliBiliIE._real_extract 不会自动获取 buvid3（与
    BiliBiliSearchIE._search_results 不同），需手动注入。
    """
    from .providers.bilibili import _ensure_buvid3
    return _ensure_buvid3()


def _bilibili_download_with_pause(task, pause_event, on_progress):
    """B站视频下载：封面图走直链，视频走 yt-dlp（自动处理 DASH + ffmpeg 合并音视频）。

    B站 web API 启用 fnval=404 后返回 DASH 结构（音视频分离），直链下载视频流
    会没有声音。yt-dlp 内置 B站 extractor，自动选择最高画质 + 合并音视频 +
    处理 Cookie/Referer，是最稳妥的下载路径。

    流程：
    1. 从 task.media_items_json 提取封面图 URL（图片项）→ 直链下载
    2. 视频项 → 走 yt-dlp（用 task.url，让 yt-dlp 自己解析 DASH）
    """
    out_dir = _resolve_output_dir(task)
    out_dir.mkdir(parents=True, exist_ok=True)
    policy = get_file_conflict_policy()
    out_name = _effective_name(task)

    # === 1. 下载封面图（如果 media_items 中有图片项）===
    cover_downloaded = False
    if task.media_items_json:
        import json as _json
        try:
            items_data = _json.loads(task.media_items_json)
            image_items = [i for i in items_data if not i.get("is_video", False)]
            if image_items:
                # 封面图文件名：out_name_cover.jpg
                cover_name = _safe_filename(f"{out_name}_cover")
                cover_path = out_dir / f"{cover_name}.jpg"
                if not (cover_path.exists() and policy == "skip"):
                    resolved = _resolve_conflict_path(cover_path, policy)
                    if resolved is not None:
                        cover_url = image_items[0].get("url", "")
                        if cover_url:
                            try:
                                from .providers.network.headers import platform_headers
                                from .providers.base import Platform as _P
                                headers = platform_headers(_P.BILIBILI)
                                resp = requests.get(cover_url, timeout=30, headers=headers)
                                resp.raise_for_status()
                                with open(resolved, "wb") as f:
                                    f.write(resp.content)
                                cover_downloaded = True
                            except Exception as e:
                                logger.warning("B站封面下载失败: %s", e)
        except Exception as e:
            logger.warning("B站封面解析失败: %s", e)

    # === 2. 下载视频（走 yt-dlp 路径）===
    resolved_stem = _resolve_conflict_stem(out_dir, out_name, policy)
    if resolved_stem is None:
        task.status = "done"
        task.progress = 100
        task.filename = str(out_dir / f"{out_name}.mp4") if cover_downloaded else ""
        return

    cookie = get_cookie_path()
    # 仅当 cookie 文件含 B站 SESSDATA 时才传给 yt-dlp
    if cookie:
        import http.cookiejar
        try:
            cj = http.cookiejar.MozillaCookieJar(str(cookie))
            cj.load(ignore_discard=True, ignore_expires=True)
            has_bilibili_cookie = any(
                c.name in ("SESSDATA", "bili_jct")
                and "bilibili.com" in c.domain
                for c in cj
            )
            if not has_bilibili_cookie:
                cookie = None
        except Exception:
            cookie = None

    opts = _yt_opts(cookie)
    opts["outtmpl"] = str(out_dir / f"{resolved_stem}.%(ext)s")
    opts["progress_hooks"] = [_download_hook_with_pause(task, pause_event, on_progress)]
    # B站：注入 buvid3 防止 412 Precondition Failed
    # yt-dlp 的 BiliBiliIE._real_extract 不会自动获取 buvid3（与 BiliBiliSearchIE 不同），
    # B站近期强制要求 buvid3 才能调 api.bilibili.com/x/web-interface/view。
    # 这里在 yt-dlp opts 中通过 http_headers.cookies 注入访客 buvid3。
    buvid3 = _ensure_bilibili_buvid3()
    if buvid3:
        # 用 extractor_args 让 yt-dlp 在请求时带 buvid3 cookie
        opts.setdefault("http_headers", {})
        opts["http_headers"]["Cookie"] = (
            opts["http_headers"].get("Cookie", "") + f"; buvid3={buvid3}"
        ).lstrip("; ")
    # B站：选最高画质，合并音视频为 mp4
    opts["format"] = "bestvideo+bestaudio/best"
    opts["merge_output_format"] = "mp4"
    task.status = "downloading"
    if on_progress:
        on_progress(task)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([task.url])
    except Exception as e:
        # yt-dlp 失败时尝试降级：用 best 单流（合流 MP4，可能封顶 720P）
        logger.warning("B站 yt-dlp 最佳画质下载失败，降级到 best: %s", e)
        opts["format"] = "best[ext=mp4]/best"
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([task.url])

    # 验证输出文件
    expected = out_dir / f"{resolved_stem}.mp4"
    if not expected.exists():
        candidates = list(out_dir.glob(f"{resolved_stem}.*"))
        if not candidates:
            task.status = "error"
            task.error = "下载完成但文件未生成"
            _cleanup_empty_dir(out_dir)
            return
        expected = candidates[0]
    task.status = "done"
    task.progress = 100
    task.filename = str(expected)


def _direct_download_with_pause(task, pause_event, on_progress):
    """通用直链下载（浏览器提取的媒体 URL 或本地文件路径）。"""
    import urllib.parse
    import shutil

    out_dir = _resolve_output_dir(task)
    out_dir.mkdir(parents=True, exist_ok=True)
    policy = get_file_conflict_policy()
    out_name = _effective_name(task)
    # 兜底：当 task 既无 custom_name 也无 author 时，_effective_name 会返回
    # "%(title)s" 字面值（yt-dlp 模板语法）。直链下载不经过 yt-dlp outtmpl
    # 处理，必须在这里替换为实际 title，否则文件名会变成 "%(title)s.mp4"
    if out_name == "%(title)s":
        out_name = _safe_filename(task.title or "download")

    # 从 media_items_json 读取 is_video（单项下载入队时写入）
    # 用于 URL 无扩展名时推断默认扩展名（图片 .jpg / 视频 .mp4）
    is_video_from_items = False
    if task.media_items_json:
        try:
            import json as _json
            items_data = _json.loads(task.media_items_json)
            if items_data:
                is_video_from_items = bool(items_data[0].get("is_video", False))
        except (ValueError, IndexError, KeyError):
            pass

    # 本地文件路径（Telegram 媒体已下载到本地）
    src = Path(task.direct_url)
    if src.is_file():
        ext = src.suffix or ".bin"
        resolved_stem = _resolve_conflict_stem(out_dir, out_name, policy)
        if resolved_stem is None:
            task.status = "done"
            task.progress = 100
            return
        dst = out_dir / f"{resolved_stem}{ext}"
        shutil.copy2(str(src), str(dst))
        task.filename = str(dst)
        task.status = "done"
        task.progress = 100
        return

    # 本地文件夹（Telegram 媒体组）
    if src.is_dir():
        files = sorted([f for f in src.iterdir() if f.is_file()], key=lambda f: f.name)
        total = len(files)
        if total == 0:
            task.status = "done"
            task.progress = 100
            return
        # 创建子文件夹
        dst_dir = out_dir / out_name
        dst_dir.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(files):
            dst = dst_dir / f"{i + 1}{f.suffix}"
            shutil.copy2(str(f), str(dst))
            task.progress = (i + 1) / total * 100
            if on_progress:
                on_progress(task)
        task.filename = str(dst_dir)
        task.status = "done"
        task.progress = 100
        return

    # 从 URL 推断扩展名
    url_path = urllib.parse.urlparse(task.direct_url).path
    ext = Path(url_path).suffix or ""
    if ext == ".jpeg":
        ext = ".jpg"
    # URL 无扩展名时，按 media_items_json 的 is_video 推断（修复清单问题 1）：
    #   小红书 CDN URL 通常无扩展名，原默认 .mp4 导致单项图片被命名为 .mp4
    #   → infer_media_type 返回 "video" → 双击用 PotPlayer 打开
    if not ext:
        ext = ".mp4" if is_video_from_items else ".jpg"

    resolved_stem = _resolve_conflict_stem(out_dir, out_name, policy)
    if resolved_stem is None:
        task.status = "done"
        task.progress = 100
        return

    filename = out_dir / f"{resolved_stem}{ext}"

    task.status = "downloading"
    if on_progress:
        on_progress(task)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    # IG CDN 需要 Referer
    if "cdninstagram" in task.direct_url or "fbcdn" in task.direct_url:
        headers["Referer"] = "https://www.instagram.com/"
    # Weibo sinaimg.cn CDN (livephoto/video/image) 需要 Referer + Cookie 防 403
    _wb_cookies = {}
    if "sinaimg" in task.direct_url or "weibo" in task.direct_url:
        headers.setdefault("Referer", "https://weibo.com/")
        headers.setdefault("Accept", "*/*")
        headers.setdefault("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
        try:
            from .providers.weibo import _get_weibo_cookies
            _wb_cookies = _get_weibo_cookies()
        except Exception:
            pass
    # X (Twitter) CDN（video.twimg.com / pbs.twimg.com）在中国大陆被墙，
    # 需通过系统代理访问；Referer 头提升成功率（部分 CDN 校验）
    if "twimg.com" in task.direct_url or "x.com" in task.direct_url:
        headers.setdefault("Referer", "https://x.com/")
        headers.setdefault("Accept", "*/*")
    # 国内平台 CDN Referer（浏览器插件发送的直链场景）
    # 抖音 CDN（aweme.snssdk.com / douyinvod.com / bytecdn / bytedance）
    if any(d in task.direct_url for d in ("douyinvod", "bytecdn", "bytedance", "aweme.snssdk", "byteimg")):
        headers.setdefault("Referer", "https://www.douyin.com/")
        headers.setdefault("Accept", "*/*")
    # B站 CDN（bilivideo.com / akamaized.net / bdstatic）
    if any(d in task.direct_url for d in ("bilivideo", "akamaized", "bdstatic", "bilivideo.com")):
        headers.setdefault("Referer", "https://www.bilibili.com/")
        headers.setdefault("Accept", "*/*")
    # 小红书 CDN（xhscdn.com / sns-img-*.xhscdn.com）
    if "xhscdn" in task.direct_url:
        headers.setdefault("Referer", "https://www.xiaohongshu.com/")
        headers.setdefault("Accept", "*/*")
    # 快手 CDN（kwaicdn.com / yxixy.com）
    if any(d in task.direct_url for d in ("kwaicdn", "yxixy")):
        headers.setdefault("Referer", "https://www.kuaishou.com/")
        headers.setdefault("Accept", "*/*")

    # 用 Session 而非 requests.get，确保 trust_env=True 尊重系统代理
    # （HTTP_PROXY/HTTPS_PROXY 环境变量 / Windows 注册表代理设置）
    # 这对 video.twimg.com 在中国大陆必须的代理访问至关重要
    session = requests.Session()
    session.trust_env = True

    # 断点续传：检查是否有部分文件，支持暂停/断线后恢复
    # （旧实现总是 "wb" 覆盖 + except Exception 删除部分文件，导致暂停后重试从 0 开始）
    is_resume = filename.exists() and filename.stat().st_size > 0
    resume_headers = dict(headers)
    if is_resume:
        resume_headers["Range"] = f"bytes={filename.stat().st_size}-"

    resp = session.get(
        task.direct_url, stream=True, timeout=120,
        headers=resume_headers, cookies=_wb_cookies or None,
    )
    try:
        if resp.status_code == 416:
            # Range not satisfiable — 文件已完整下载
            resp.close()
            task.filename = str(filename)
            task.status = "done"
            task.progress = 100
            if on_progress:
                on_progress(task)
            return
        resp.raise_for_status()
        is_resume = resp.status_code == 206
        total_size = int(resp.headers.get("content-length", 0))
        if is_resume:
            downloaded = filename.stat().st_size
            total_size += downloaded
        else:
            downloaded = 0
        with open(filename, "ab" if is_resume else "wb") as f:
            for chunk in resp.iter_content(8192):
                _wait_pause_or_cancel(pause_event, task)
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    task.progress = downloaded / total_size * 100
                    if on_progress:
                        on_progress(task)
        task.filename = str(filename)
        task.status = "done"
        task.progress = 100
    except _CancelledError:
        Path(filename).unlink(missing_ok=True)
        raise
    # 注意：except Exception 不再删除部分文件！
    # 连接断开（暂停期间超时等）时保留 .part 文件，以便重试时断点续传。
    # 只有用户主动取消（_CancelledError）才删除。
    finally:
        resp.close()


def _items_download_with_pause(
    task: DownloadTask,
    pause_event: threading.Event,
    on_progress: ProgressCallback | None = None,
):
    """通用媒体文件下载（用于国内平台如微博、小红书等）。

    读取 task.media_items_json 中的媒体列表，逐个下载。
    图片和视频均通过 requests 直链下载，支持断点续传（视频）。
    """
    import json as _json

    items_data = _json.loads(task.media_items_json)
    media_items = [
        MediaItem(url=i["url"], is_video=i["is_video"], index=i.get("index", 0))
        for i in items_data
    ]

    if not media_items:
        raise ValueError("没有可下载的媒体项目")

    task.status = "downloading"
    if on_progress:
        on_progress(task)

    out_dir = _resolve_output_dir(task)

    # Organized mode: create per-post subdirectory
    post_out_dir = out_dir
    if get_storage_mode() == "organized":
        post_stem = task.author or task.title or "post"
        if task.post_time:
            post_stem = _safe_filename(f"{post_stem}_{task.post_time}")
        post_out_dir = out_dir / post_stem

    post_out_dir.mkdir(parents=True, exist_ok=True)

    # Track output dir early so on_done can find it even on partial failure
    task.filename = str(post_out_dir)

    name_stem = _effective_name(task)
    if name_stem == "%(title)s":
        name_stem = _safe_filename(task.title or "download")

    total = len(media_items)
    pad = len(str(total))
    policy = get_file_conflict_policy()
    downloaded_any = False
    failed_count = 0

    for idx, item in enumerate(media_items):
        ext = "mp4" if item.is_video else "jpg"
        suffix = f"_{str(idx + 1).zfill(pad)}" if total > 1 else ""
        filename = post_out_dir / f"{name_stem}{suffix}.{ext}"

        if filename.exists() and policy == "skip":
            continue

        resolved = _resolve_conflict_path(filename, policy)
        if resolved is None:
            continue
        filename = resolved

        try:
            if item.is_video:
                headers = _resume_headers(filename)
                # Add provider-specific headers (Referer, UA, etc.)
                _wb_cookies = {}
                try:
                    from .providers.base import Platform as _P
                    prov = get_provider_for(_P(task.platform))
                    if prov:
                        pheaders = prov.get_request_headers()
                        for k, v in pheaders.items():
                            headers.setdefault(k, v)
                    # Weibo sinaimg.cn CDN (especially livephoto.us.sinaimg.cn)
                    # requires cookies for 403-free access
                    if "sinaimg" in item.url or "weibo" in item.url:
                        from .providers.weibo import _get_weibo_cookies
                        _wb_cookies = _get_weibo_cookies()
                except Exception:
                    pass
                # sinaimg.cn 需要完整浏览器 UA + Referer
                if "sinaimg" in item.url:
                    headers.setdefault("Referer", "https://weibo.com/")
                    headers.setdefault("Accept", "*/*")
                    headers.setdefault("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
                resp = requests.get(item.url, stream=True, timeout=30, headers=headers, cookies=_wb_cookies or None)
                try:
                    is_resume = resp.status_code == 206
                    if resp.status_code == 416:
                        continue
                    resp.raise_for_status()
                    total_size = int(resp.headers.get("content-length", 0))
                    if is_resume:
                        downloaded = filename.stat().st_size
                        total_size += downloaded
                    else:
                        downloaded = 0
                    try:
                        with open(filename, "ab" if is_resume else "wb") as f:
                            for chunk in resp.iter_content(8192):
                                _wait_pause_or_cancel(pause_event, task)
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total_size:
                                    pct = downloaded / total_size * 100
                                    task.progress = (idx + pct / 100) / total * 100
                                    task.speed = f"{idx + 1}/{total}"
                                    task.filename = str(filename)
                                    if on_progress:
                                        on_progress(task)
                    except _CancelledError:
                        filename.unlink(missing_ok=True)
                        raise
                finally:
                    resp.close()
            else:
                # Image — use provider headers if available, fall back to domain-based
                img_headers = dict(_DOWNLOAD_HEADERS)
                _img_cookies = {}
                try:
                    from .providers.base import Platform as _P
                    prov = get_provider_for(_P(task.platform))
                    if prov:
                        pheaders = prov.get_request_headers()
                        img_headers.update(pheaders)
                except Exception:
                    pass
                # Domain-based fallback as safety net
                if "sinaimg" in item.url or "weibo" in item.url:
                    img_headers.setdefault("Referer", "https://weibo.com/")
                    img_headers.setdefault("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
                    # Weibo sinaimg.cn CDN requires cookies to avoid 403
                    try:
                        from .providers.weibo import _get_weibo_cookies
                        _img_cookies = _get_weibo_cookies()
                    except Exception:
                        pass
                elif "xiaohongshu" in item.url or "xhscdn" in item.url:
                    img_headers.setdefault("Referer", "https://www.xiaohongshu.com/")
                elif "cdninstagram" in item.url or "fbcdn" in item.url:
                    img_headers.setdefault("Referer", "https://www.instagram.com/")
                resp = requests.get(item.url, timeout=30, headers=img_headers, cookies=_img_cookies or None)
                try:
                    resp.raise_for_status()
                    # Detect extension from content-type if possible
                    ct = resp.headers.get("content-type", "")
                    if "gif" in ct:
                        ext = "gif"
                    elif "png" in ct:
                        ext = "png"
                    elif "webp" in ct:
                        ext = "webp"
                    elif "jpeg" in ct or "jpg" in ct:
                        ext = "jpg"
                    else:
                        ext = ext  # fallback to original
                    # Rebuild filename with correct extension
                    new_filename = post_out_dir / f"{name_stem}{suffix}.{ext}"
                    if new_filename != filename:
                        # Check conflict for new extension
                        if new_filename.exists() and policy == "skip":
                            continue
                        resolved2 = _resolve_conflict_path(new_filename, policy)
                        if resolved2 is None:
                            continue
                        new_filename = resolved2
                        filename = new_filename
                    filename.write_bytes(resp.content)
                finally:
                    resp.close()

            downloaded_any = True
            task.progress = (idx + 1) / total * 100
            task.speed = f"{idx + 1}/{total}"
            task.filename = str(filename)
            if on_progress:
                on_progress(task)
        except _CancelledError:
            raise
        except Exception as e:
            failed_count += 1
            logger.warning('Failed to download item %d/%d for %s: %s', idx + 1, total, task.url, e)
            # Continue with next item — don't let one failure kill the batch

    if not downloaded_any:
        _cleanup_empty_dir(post_out_dir)
        raise ValueError(f"所有 {total} 个媒体项目都下载失败")

    task.status = "done"
    task.progress = 100
    # 单文件下载：保持循环内已设置的实际文件路径，避免 infer_media_type 扫描目录
    # 误判（如小红书单项图片在 simple 模式下被 output_dir 中其他视频文件污染）
    # 多文件下载：用目录路径表示合集
    if total > 1:
        task.filename = str(post_out_dir)
    if failed_count:
        logger.info('Downloaded %d/%d items for %s (%d failed)', downloaded_any, total, task.url, failed_count)


def start_download_with_pause(
    task: DownloadTask,
    pause_event: threading.Event,
    on_progress: ProgressCallback | None = None,
    on_done: Callable[[DownloadTask], None] | None = None,
) -> threading.Thread:
    parsed = parse_url(task.url)

    def _run():
        try:
            if task.direct_url:
                _direct_download_with_pause(task, pause_event, on_progress)
            elif parsed.platform == Platform.YOUTUBE:
                _yt_download_with_pause(task, pause_event, on_progress)
            elif parsed.platform == Platform.INSTAGRAM:
                if get_platform_mode("instagram") == "api":
                    _apify_download_with_pause(task, pause_event, on_progress)
                else:
                    _ig_download_with_pause(task, pause_event, on_progress)
            elif parsed.platform == Platform.X:
                _x_download_with_pause(task, pause_event, on_progress)
            elif parsed.platform == Platform.BILIBILI:
                _bilibili_download_with_pause(task, pause_event, on_progress)
            else:
                # Phase 2: domestic platform items download (Weibo, Bilibili, etc.)
                if task.media_items_json:
                    _items_download_with_pause(task, pause_event, on_progress)
                else:
                    raise ValueError(f"不支持的平台或缺少媒体信息: {task.url}")
        except _CancelledError:
            task.status = "error"
            task.error = "Cancelled"
            _cleanup_empty_dir(_resolve_output_dir(task))
        except Exception as e:
            task.status = "error"
            task.error = str(e)
            # Use provider classify_error if available
            try:
                from .providers.base import Platform as _P
                prov = get_provider_for(_P(task.platform))
                if prov:
                    task.error_category = prov.classify_error(e)
            except Exception:
                pass
            _cleanup_empty_dir(_resolve_output_dir(task))

        if on_done:
            on_done(task)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread
