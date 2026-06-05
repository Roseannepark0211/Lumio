from __future__ import annotations

import json
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import http.cookiejar
import requests
import yt_dlp

from .utils.config import get_cookie_path, get_download_dir, get_file_conflict_policy, get_storage_mode
from .utils.url_parser import Platform, parse_url


def _resolve_conflict_path(path: Path, policy: str) -> Path | None:
    """Resolve file path based on conflict policy.

    Returns the resolved path, or None if the file should be skipped.
    """
    if policy == "overwrite" or not path.exists():
        return path
    if policy == "skip":
        return None
    # rename (default): append (1), (2), ...
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
    # rename
    counter = 1
    while True:
        new_stem = f"{stem} ({counter})"
        if not list(out_dir.glob(f"{new_stem}.*")):
            return new_stem
        counter += 1


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
class MediaItem:
    url: str
    is_video: bool
    index: int = 0


@dataclass
class VideoInfo:
    title: str
    url: str
    thumbnail: str | None
    duration: int | None  # seconds
    formats: list[dict]  # raw yt-dlp format dicts (YouTube only)
    platform: str
    author: str = ""  # uploader / channel / IG username
    items: list[MediaItem] = field(default_factory=list)
    post_time: str = ""


@dataclass
class DownloadTask:
    url: str
    format_id: str | None
    output_dir: Path
    custom_name: str = ""
    author: str = ""
    post_time: str = ""
    format_type: str = ""  # "video" | "audio" | "combined" | ""
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
    }
    if cookie_file and cookie_file.exists():
        opts["cookiefile"] = str(cookie_file)
    ffmpeg = _find_ffmpeg()
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg  # full path to binary
    return opts


def _yt_extract_info(url: str) -> VideoInfo:
    cookie = get_cookie_path()
    opts = _yt_opts(cookie)
    opts["skip_download"] = True

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    info = yt_dlp.YoutubeDL.sanitize_info(info)
    entries = info.get("entries") or [info]
    first = entries[0]

    author = (
        first.get("uploader")
        or first.get("channel")
        or first.get("creator")
        or ""
    )

    upload_date = first.get("upload_date", "")  # format: "20240315"
    post_time = ""
    if upload_date and len(upload_date) == 8:
        post_time = f"{upload_date[:4]}{upload_date[4:6]}{upload_date[6:8]}"

    return VideoInfo(
        title=first.get("title", "Unknown"),
        url=url,
        thumbnail=first.get("thumbnail"),
        duration=first.get("duration"),
        formats=first.get("formats", []),
        platform=first.get("extractor", "youtube"),
        author=author,
        post_time=post_time,
    )


# ---- Instagram ----

def _ig_session():
    import instaloader
    L = instaloader.Instaloader(
        download_videos=True,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
    )
    cookie_path = get_cookie_path()
    if cookie_path:
        cj = http.cookiejar.MozillaCookieJar(str(cookie_path))
        cj.load(ignore_discard=True, ignore_expires=True)
        for c in cj:
            L.context._session.cookies.set(c.name, c.value, domain=c.domain)
    return L


def _ig_build_items(post) -> list[MediaItem]:
    """Extract MediaItems from an instaloader.Post."""
    items: list[MediaItem] = []
    if post.typename == "GraphSidecar":
        for i, node in enumerate(post.get_sidecar_nodes()):
            url_str = str(node.video_url) if node.is_video else str(node.display_url)
            items.append(MediaItem(url=url_str, is_video=node.is_video, index=i))
    elif post.is_video:
        items.append(MediaItem(url=str(post.video_url), is_video=True, index=0))
    else:
        items.append(MediaItem(url=str(post.url), is_video=False, index=0))
    return items


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


def _post_to_queue_task(post_data: dict, custom_name: str, output_dir, max_retries: int = 3, batch_id: str = ""):
    """Create QueueTask from Instagram API post dict (mobile or GraphQL format)."""
    from .queue_manager import QueueTask
    # Mobile API format
    shortcode = post_data.get("code", post_data.get("shortcode", ""))
    is_video = post_data.get("video", post_data.get("is_video", False))
    caption_obj = post_data.get("caption", {})
    caption = caption_obj.get("text", "") if isinstance(caption_obj, dict) else ""
    title = caption[:80] or "Instagram post"
    owner = post_data.get("user", {}).get("username", post_data.get("owner", {}).get("username", ""))
    ts = post_data.get("taken_at_timestamp", post_data.get("taken_at", 0))
    post_time = ""
    if ts:
        from datetime import datetime, timezone
        post_time = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    # Thumbnail: mobile API uses image_versions2, GraphQL uses display_url
    thumb = ""
    if "image_versions2" in post_data:
        candidates = post_data["image_versions2"].get("candidates", [])
        if candidates:
            thumb = candidates[0].get("url", "")
    if not thumb:
        thumb = post_data.get("display_url", "")
    url = f"https://www.instagram.com/p/{shortcode}/"
    return QueueTask(
        url=url,
        output_dir=str(output_dir),
        custom_name=custom_name,
        batch_id=batch_id,
        title=title,
        platform="instagram",
        author=owner,
        post_time=post_time,
        thumbnail_url=thumb,
        max_retries=max_retries,
    )


def _ig_api_session() -> requests.Session:
    """Create a requests.Session with cookies and standard IG headers."""
    session = requests.Session()
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


def _ig_search_user(session: requests.Session, username: str) -> dict:
    """Search for user via GraphQL, return first exact-match user dict."""
    data = {
        "variables": json.dumps({"hasQuery": True, "query": username}),
        "doc_id": "26347858941511777",
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": f"https://www.instagram.com/{username}/",
    }
    resp = session.post("https://www.instagram.com/graphql/query", headers=headers, data=data, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    users = result.get("data", {}).get("xdt_api__v1__fbsearch__non_profiled_serp", {}).get("users", [])
    for u in users:
        if u.get("username") == username:
            return u
    raise ValueError(f"User @{username} not found")


def fetch_profile_info(username: str) -> dict:
    """Return profile metadata via GraphQL search API."""
    session = _ig_api_session()
    user = _ig_search_user(session, username)
    return {
        "username": user["username"],
        "full_name": user.get("full_name", ""),
        "profile_pic_url": user.get("profile_pic_url"),
        "post_count": 0,  # not available from search API
        "user_id": str(user["pk"]),
    }


def enumerate_profile_posts(username: str, limit: int, callback=None, cancel_event=None) -> list:
    """Return up to `limit` post dicts via mobile feed API with pagination."""
    session = _ig_api_session()

    # Get user_id from search
    user = _ig_search_user(session, username)
    user_id = str(user["pk"])

    # Fetch posts via mobile feed API
    all_posts = []
    max_id = None

    while len(all_posts) < limit:
        if cancel_event and cancel_event.is_set():
            break
        url = f"https://i.instagram.com/api/v1/feed/user/{user_id}/?count=12"
        if max_id:
            url += f"&max_id={max_id}"
        resp = session.get(url, timeout=15)
        if resp.status_code == 429:
            import time
            time.sleep(5)
            resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            break
        data = resp.json()
        items = data.get("items", [])
        if not items:
            break
        for item in items:
            if cancel_event and cancel_event.is_set():
                break
            if len(all_posts) >= limit:
                break
            all_posts.append(item)
            if callback:
                callback(len(all_posts), limit)
        if not data.get("more_available", False):
            break
        max_id = data.get("next_max_id")
        if not max_id:
            break

    return all_posts


# ---- YouTube batch scraping ----

def fetch_yt_channel_info(url: str) -> dict:
    """Fetch channel/playlist title via yt-dlp flat extraction."""
    from .utils.config import get_cookie_path
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "playlistend": 1, "ignoreerrors": True}
    cookie = get_cookie_path()
    if cookie and cookie.exists():
        opts["cookiefile"] = str(cookie)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise ValueError("Could not fetch channel info")
    return {
        "title": info.get("title", ""),
        "channel": info.get("uploader", info.get("channel", "")),
        "url": url,
    }


def enumerate_yt_videos(url: str, limit: int, callback=None, cancel_event=None) -> list:
    """Return up to `limit` video entries via yt-dlp flat extraction."""
    from .utils.config import get_cookie_path
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "playlistend": limit, "ignoreerrors": True}
    cookie = get_cookie_path()
    if cookie and cookie.exists():
        opts["cookiefile"] = str(cookie)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        return []
    entries = [e for e in (info.get("entries") or []) if e]

    # Channel URLs return tab entries (Videos/Live/Shorts) instead of actual videos.
    # Detect this and re-extract with /videos appended.
    if entries and entries[0].get("id", "").startswith("UC"):
        url_videos = url.rstrip("/") + "/videos"
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url_videos, download=False)
        if info:
            entries = [e for e in (info.get("entries") or []) if e]

    if callback:
        for i, e in enumerate(entries):
            if cancel_event and cancel_event.is_set():
                break
            callback(i + 1, len(entries))
    return entries[:limit]


def _yt_entry_to_queue_task(entry: dict, custom_name: str, output_dir, max_retries: int = 3,
                            format_id: str = "best", format_type: str = "combined", batch_id: str = ""):
    """Create QueueTask from yt-dlp flat entry dict."""
    from .queue_manager import QueueTask
    video_id = entry.get("id", "")
    url = f"https://www.youtube.com/watch?v={video_id}"
    title = entry.get("title", "YouTube video")
    author = entry.get("channel", entry.get("uploader", ""))

    # Default save name: author_short_title (timestamp appended by _effective_name)
    if not custom_name:
        short_title = title[:30].strip()
        for ch in '\\/:*?"<>|':
            short_title = short_title.replace(ch, "_")
        safe_author = author[:30].strip()
        for ch in '\\/:*?"<>|':
            safe_author = safe_author.replace(ch, "_")
        custom_name = f"{safe_author}_{short_title}" if safe_author else short_title

    post_time = ""
    ts = entry.get("timestamp")
    if ts:
        from datetime import datetime, timezone
        post_time = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y%m%d")
    thumbnail = ""
    thumbs = entry.get("thumbnails", [])
    if thumbs:
        thumbnail = thumbs[-1].get("url", "")
    return QueueTask(
        url=url,
        format_id=format_id,
        format_type=format_type,
        output_dir=str(output_dir),
        custom_name=custom_name,
        batch_id=batch_id,
        title=title,
        platform="youtube",
        author=author,
        post_time=post_time,
        thumbnail_url=thumbnail,
        max_retries=max_retries,
    )


def _ig_extract_info(url: str) -> VideoInfo:
    shortcode = url.rstrip("/").split("/")[-1]
    parts = url.rstrip("/").split("/")
    for i, p in enumerate(parts):
        if p in ("reel", "p") and i + 1 < len(parts):
            shortcode = parts[i + 1]
            break

    media = _ig_get_media_info(shortcode)
    items = _ig_media_to_items(media)

    caption_obj = media.get("caption", {})
    caption = caption_obj.get("text", "") if isinstance(caption_obj, dict) else ""
    title = caption[:80] or "Instagram post"
    owner = media.get("user", {}).get("username", "")
    ts = media.get("taken_at", 0)
    post_time = ""
    if ts:
        from datetime import datetime, timezone
        post_time = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    thumb = ""
    candidates = media.get("image_versions2", {}).get("candidates", [])
    if candidates:
        thumb = candidates[0].get("url", "")
    if not thumb:
        thumb = media.get("display_url", "")

    return VideoInfo(
        title=title,
        url=url,
        thumbnail=thumb,
        duration=None,
        formats=[],
        platform="instagram",
        author=owner,
        items=items,
        post_time=post_time,
    )


# ---- X (Twitter) ----

def _x_extract_info(url: str) -> VideoInfo:
    cookie = get_cookie_path()
    opts = _yt_opts(cookie)
    opts["skip_download"] = True

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    info = yt_dlp.YoutubeDL.sanitize_info(info)

    author = (
        info.get("uploader")
        or info.get("creator")
        or ""
    )

    upload_date = info.get("upload_date", "")
    post_time = ""
    if upload_date and len(upload_date) == 8:
        post_time = f"{upload_date[:4]}{upload_date[4:6]}{upload_date[6:8]}"

    return VideoInfo(
        title=info.get("title", "X post"),
        url=url,
        thumbnail=info.get("thumbnail"),
        duration=info.get("duration"),
        formats=info.get("formats", []),
        platform="x",
        author=author,
        post_time=post_time,
    )


# ---- Public API ----

def extract_info(url: str) -> VideoInfo:
    parsed = parse_url(url)
    if parsed.platform == Platform.YOUTUBE:
        return _yt_extract_info(url)
    elif parsed.platform == Platform.INSTAGRAM:
        return _ig_extract_info(url)
    elif parsed.platform == Platform.X:
        return _x_extract_info(url)
    else:
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


def _download_hook(task: DownloadTask, on_progress: ProgressCallback | None):
    def hook(d: dict):
        if task._cancelled:
            raise _CancelledError()

        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            task.progress = (downloaded / total * 100) if total else 0
            task.speed = d.get("_speed_str", "")
            task.filename = d.get("filename", "")
            task.status = "downloading"
        elif d["status"] == "finished":
            task.progress = 100
            task.status = "done"
            task.filename = d.get("filename", "")

        if on_progress:
            on_progress(task)

    return hook


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
    return name


def _yt_download(
    task: DownloadTask,
    on_progress: ProgressCallback | None,
):
    cookie = get_cookie_path()
    opts = _yt_opts(cookie)
    out_name = _effective_name(task)

    # File conflict handling
    out_dir = Path(task.output_dir)
    policy = get_file_conflict_policy()
    resolved_stem = _resolve_conflict_stem(out_dir, out_name, policy)
    if resolved_stem is None:
        task.status = "done"
        task.progress = 100
        return
    out_name = resolved_stem

    opts["outtmpl"] = str(task.output_dir / f"{out_name}.%(ext)s")
    opts["progress_hooks"] = [_download_hook(task, on_progress)]

    if task.format_id and task.format_id not in ("best", "___sep"):
        # Auto-merge: video-only needs audio, audio-only needs video
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

    task.status = "done"
    task.progress = 100


def _ig_download(
    task: DownloadTask,
    on_progress: ProgressCallback | None,
):
    parts = task.url.rstrip("/").split("/")
    shortcode = parts[-1]
    for i, p in enumerate(parts):
        if p in ("reel", "p") and i + 1 < len(parts):
            shortcode = parts[i + 1]
            break

    media = _ig_get_media_info(shortcode)

    task.status = "downloading"
    if on_progress:
        on_progress(task)

    out_dir = Path(task.output_dir)

    # Organized mode: create per-post subdirectory
    if get_storage_mode() == "organized":
        post_stem = task.author or shortcode
        if task.post_time:
            post_stem = f"{post_stem}_{task.post_time}"
        out_dir = out_dir / post_stem

    out_dir.mkdir(parents=True, exist_ok=True)

    items = _ig_media_to_items(media)

    # Build a unique stem: author_postTime (or custom_name, or shortcode)
    name_stem = _safe_filename(task.custom_name or task.author or shortcode)
    if task.post_time:
        name_stem = f"{name_stem}_{task.post_time}"

    total = len(items)
    pad = len(str(total))
    policy = get_file_conflict_policy()
    for idx, item in enumerate(items):
        ext = "mp4" if item.is_video else "jpg"
        suffix = f"_{str(idx + 1).zfill(pad)}" if total > 1 else ""
        filename = out_dir / f"{name_stem}{suffix}.{ext}"

        # File conflict handling
        resolved = _resolve_conflict_path(filename, policy)
        if resolved is None:
            continue  # skip
        filename = resolved

        resp = requests.get(item.url, stream=True, timeout=30)
        try:
            resp.raise_for_status()

            total_size = int(resp.headers.get("content-length", 0))
            downloaded = 0

            try:
                with open(filename, "wb") as f:
                    for chunk in resp.iter_content(8192):
                        if task._cancelled:
                            raise _CancelledError()
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

    task.status = "done"
    task.progress = 100
    task.filename = str(out_dir)


def _x_download(
    task: DownloadTask,
    on_progress: ProgressCallback | None,
):
    cookie = get_cookie_path()
    opts = _yt_opts(cookie)
    out_name = _effective_name(task)

    # File conflict handling
    out_dir = Path(task.output_dir)
    policy = get_file_conflict_policy()
    resolved_stem = _resolve_conflict_stem(out_dir, out_name, policy)
    if resolved_stem is None:
        task.status = "done"
        task.progress = 100
        return
    out_name = resolved_stem

    opts["outtmpl"] = str(task.output_dir / f"{out_name}.%(ext)s")
    opts["progress_hooks"] = [_download_hook(task, on_progress)]
    opts["format"] = "best[ext=mp4]/best"
    opts["merge_output_format"] = "mp4"

    task.status = "downloading"
    if on_progress:
        on_progress(task)

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([task.url])

    task.status = "done"
    task.progress = 100


def start_download(
    task: DownloadTask,
    on_progress: ProgressCallback | None = None,
    on_done: Callable[[DownloadTask], None] | None = None,
) -> threading.Thread:
    parsed = parse_url(task.url)

    def _run():
        try:
            if parsed.platform == Platform.YOUTUBE:
                _yt_download(task, on_progress)
            elif parsed.platform == Platform.INSTAGRAM:
                _ig_download(task, on_progress)
            elif parsed.platform == Platform.X:
                _x_download(task, on_progress)
        except _CancelledError:
            task.status = "error"
            task.error = "Cancelled"
        except Exception as e:
            task.status = "error"
            task.error = str(e)

        if on_done:
            on_done(task)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


# ---- Pause-aware download (V2 queue system) ----

def _download_hook_with_pause(
    task: DownloadTask,
    pause_event: threading.Event,
    on_progress: ProgressCallback | None,
):
    def hook(d: dict):
        if task._cancelled:
            raise _CancelledError()
        pause_event.wait()  # blocks when paused
        if task._cancelled:
            raise _CancelledError()

        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            task.progress = (downloaded / total * 100) if total else 0
            task.speed = d.get("_speed_str", "")
            task.filename = d.get("filename", "")
            task.status = "downloading"
        elif d["status"] == "finished":
            task.progress = 100
            task.status = "done"
            task.filename = d.get("filename", "")

        if on_progress:
            on_progress(task)

    return hook


def _yt_download_with_pause(task, pause_event, on_progress):
    cookie = get_cookie_path()
    opts = _yt_opts(cookie)
    out_name = _effective_name(task)

    # File conflict handling
    out_dir = Path(task.output_dir)
    policy = get_file_conflict_policy()
    resolved_stem = _resolve_conflict_stem(out_dir, out_name, policy)
    if resolved_stem is None:
        task.status = "done"
        task.progress = 100
        return
    out_name = resolved_stem

    opts["outtmpl"] = str(task.output_dir / f"{out_name}.%(ext)s")
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

    task.status = "done"
    task.progress = 100


def _ig_download_with_pause(task, pause_event, on_progress):
    parts = task.url.rstrip("/").split("/")
    shortcode = parts[-1]
    for i, p in enumerate(parts):
        if p in ("reel", "p") and i + 1 < len(parts):
            shortcode = parts[i + 1]
            break

    media = _ig_get_media_info(shortcode)

    task.status = "downloading"
    if on_progress:
        on_progress(task)

    out_dir = Path(task.output_dir)

    # Organized mode: create per-post subdirectory
    if get_storage_mode() == "organized":
        post_stem = task.author or shortcode
        if task.post_time:
            post_stem = f"{post_stem}_{task.post_time}"
        out_dir = out_dir / post_stem

    out_dir.mkdir(parents=True, exist_ok=True)

    items = _ig_media_to_items(media)

    # Build a unique stem: author_postTime (or custom_name, or shortcode)
    name_stem = _safe_filename(task.custom_name or task.author or shortcode)
    if task.post_time:
        name_stem = f"{name_stem}_{task.post_time}"
    total = len(items)
    pad = len(str(total))
    policy = get_file_conflict_policy()
    for idx, item in enumerate(items):
        ext = "mp4" if item.is_video else "jpg"
        suffix = f"_{str(idx + 1).zfill(pad)}" if total > 1 else ""
        filename = out_dir / f"{name_stem}{suffix}.{ext}"

        # File conflict handling
        resolved = _resolve_conflict_path(filename, policy)
        if resolved is None:
            continue  # skip
        filename = resolved

        resp = requests.get(item.url, stream=True, timeout=30)
        try:
            resp.raise_for_status()

            total_size = int(resp.headers.get("content-length", 0))
            downloaded = 0

            try:
                with open(filename, "wb") as f:
                    for chunk in resp.iter_content(8192):
                        if task._cancelled:
                            raise _CancelledError()
                        pause_event.wait()  # blocks when paused
                        if task._cancelled:
                            raise _CancelledError()
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

    task.status = "done"
    task.progress = 100
    task.filename = str(out_dir)


def _x_download_with_pause(task, pause_event, on_progress):
    cookie = get_cookie_path()
    opts = _yt_opts(cookie)
    out_name = _effective_name(task)

    # File conflict handling
    out_dir = Path(task.output_dir)
    policy = get_file_conflict_policy()
    resolved_stem = _resolve_conflict_stem(out_dir, out_name, policy)
    if resolved_stem is None:
        task.status = "done"
        task.progress = 100
        return
    out_name = resolved_stem

    opts["outtmpl"] = str(task.output_dir / f"{out_name}.%(ext)s")
    opts["progress_hooks"] = [_download_hook_with_pause(task, pause_event, on_progress)]
    opts["format"] = "best[ext=mp4]/best"
    opts["merge_output_format"] = "mp4"

    task.status = "downloading"
    if on_progress:
        on_progress(task)

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([task.url])

    task.status = "done"
    task.progress = 100


def start_download_with_pause(
    task: DownloadTask,
    pause_event: threading.Event,
    on_progress: ProgressCallback | None = None,
    on_done: Callable[[DownloadTask], None] | None = None,
) -> threading.Thread:
    parsed = parse_url(task.url)

    def _run():
        try:
            if parsed.platform == Platform.YOUTUBE:
                _yt_download_with_pause(task, pause_event, on_progress)
            elif parsed.platform == Platform.INSTAGRAM:
                _ig_download_with_pause(task, pause_event, on_progress)
            elif parsed.platform == Platform.X:
                _x_download_with_pause(task, pause_event, on_progress)
        except _CancelledError:
            task.status = "error"
            task.error = "Cancelled"
        except Exception as e:
            task.status = "error"
            task.error = str(e)

        if on_done:
            on_done(task)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread
