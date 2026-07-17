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


def _post_to_queue_task(post_data: dict, custom_name: str, output_dir, max_retries: int = 3, batch_id: str = ""):
    """Create QueueTask from Instagram post dict (mobile API / GraphQL / Apify format)."""
    import json as _json
    from .queue_manager import QueueTask

    # Detect Apify format (has "type" = "Image"/"Video"/"Sidecar")
    is_apify = post_data.get("type") in ("Image", "Video", "Sidecar")

    if is_apify:
        shortcode = post_data.get("shortCode", "")
        caption = (post_data.get("caption") or "").strip()
        title = caption[:80] or "Instagram post"
        owner = post_data.get("ownerUsername", "")
        # Parse ISO timestamp
        ts_str = post_data.get("timestamp", "")
        post_time = ""
        if ts_str:
            from datetime import datetime, timezone
            try:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                post_time = dt.strftime("%Y%m%d_%H%M%S")
            except (ValueError, AttributeError):
                pass
        thumb = post_data.get("displayUrl", "")
        url = post_data.get("url", f"https://www.instagram.com/p/{shortcode}/")
        # Extract media items and serialize to JSON
        media_items = _extract_apify_media_items(post_data)
        media_json = _json.dumps(media_items) if media_items else ""
    else:
        # Mobile API / GraphQL format (original logic)
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
        thumb = ""
        if "image_versions2" in post_data:
            candidates = post_data["image_versions2"].get("candidates", [])
            if candidates:
                thumb = candidates[0].get("url", "")
        if not thumb:
            thumb = post_data.get("display_url", "")
        url = f"https://www.instagram.com/p/{shortcode}/"
        media_json = ""

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
        media_items_json=media_json,
    )


def _extract_apify_media_items(item: dict) -> list[dict]:
    """Extract media items list from an Apify result item.
    Returns list of {"url": str, "is_video": bool, "index": int, "media_type": str}.
    """
    item_type = item.get("type", "")
    items = []
    if item_type == "Sidecar" and item.get("childPosts"):
        for idx, child in enumerate(item["childPosts"]):
            child_type = child.get("type", "Image")
            if child_type == "Video" and child.get("videoUrl"):
                items.append({"url": child["videoUrl"], "is_video": True, "index": idx, "media_type": "video"})
            elif child.get("displayUrl"):
                items.append({"url": child["displayUrl"], "is_video": False, "index": idx, "media_type": "image"})
    elif item.get("images"):
        for idx, url in enumerate(item["images"]):
            if url:
                items.append({"url": url, "is_video": False, "index": idx, "media_type": "image"})
    elif item.get("videoUrl"):
        items.append({"url": item["videoUrl"], "is_video": True, "index": 0, "media_type": "video"})
    elif item.get("displayUrl"):
        items.append({"url": item["displayUrl"], "is_video": False, "index": 0, "media_type": "image"})
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
    if get_platform_mode("instagram") == "api":
        from .apify_client import get_apify_client as _get_apify_client
        return _get_apify_client().fetch_profile_info(username)
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
    if get_platform_mode("instagram") == "api":
        from .apify_client import get_apify_client as _get_apify_client
        return _get_apify_client().enumerate_profile_posts(username, limit, callback, cancel_event)
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
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "playlistend": 1, "ignoreerrors": True, "socket_timeout": 15}
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
                            format_id: str = "best", format_type: str = "combined",
                            batch_id: str = "", default_author: str = ""):
    """Create QueueTask from yt-dlp flat entry dict."""
    from .queue_manager import QueueTask
    video_id = entry.get("id", "")
    url = f"https://www.youtube.com/watch?v={video_id}"
    title = entry.get("title", "YouTube video")
    author = entry.get("channel", "") or entry.get("uploader", "") or default_author

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
    shortcode = _ig_shortcode_from_url(url)

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

_X_BEARER = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"

_X_GRAPHQL_TWEET = "2ICDjqPd81tulZcYrtpTuQ/TweetResultByRestId"
_X_GRAPHQL_USER = "xc8f1g7BYqr6VTzTbvNlGw/UserByScreenName"
_X_GRAPHQL_USER_TWEETS = "E3opETHurmVJflFsUBVuUQ/UserTweets"

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

_X_TIMELINE_FEATURES = {
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "tweetypie_unmention_optimization_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "creator_subscriptions_quote_tweet_preview_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
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


def _x_get_user_id(session: requests.Session, username: str) -> str:
    """Get user rest_id from screen name via GraphQL."""
    variables = json.dumps({"screen_name": username, "withSafetyModeUserFields": True})
    features = json.dumps(_X_USER_FEATURES)
    resp = session.get(
        f"https://x.com/i/api/graphql/{_X_GRAPHQL_USER}",
        params={"variables": variables, "features": features},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["data"]["user"]["result"]["rest_id"]


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


def fetch_x_profile_info(username: str) -> dict:
    """Return X user profile metadata."""
    session = _x_api_session()
    variables = json.dumps({"screen_name": username, "withSafetyModeUserFields": True})
    features = json.dumps(_X_USER_FEATURES)
    resp = session.get(
        f"https://x.com/i/api/graphql/{_X_GRAPHQL_USER}",
        params={"variables": variables, "features": features},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    user = data["data"]["user"]["result"]
    legacy = user.get("legacy", {})
    return {
        "username": legacy.get("screen_name", username),
        "full_name": legacy.get("name", ""),
        "profile_pic_url": legacy.get("profile_image_url_https", "").replace("_normal", "_400x400"),
        "post_count": legacy.get("statuses_count", 0),
        "user_id": user.get("rest_id", ""),
    }


def enumerate_x_tweets(username: str, limit: int, callback=None, cancel_event=None) -> list:
    """Return up to `limit` tweet dicts with media from user timeline."""
    session = _x_api_session()
    user_info = fetch_x_profile_info(username)
    user_id = user_info["user_id"]

    all_tweets = []
    cursor = None

    while len(all_tweets) < limit:
        if cancel_event and cancel_event.is_set():
            break

        variables = {
            "userId": user_id,
            "count": min(20, limit - len(all_tweets)),
            "includePromotedContent": False,
            "withQuickPromoteEligibilityTweetFields": True,
            "withVoice": True,
            "withV2Timeline": True,
        }
        if cursor:
            variables["cursor"] = cursor

        resp = session.get(
            f"https://x.com/i/api/graphql/{_X_GRAPHQL_USER_TWEETS}",
            params={
                "variables": json.dumps(variables),
                "features": json.dumps(_X_TIMELINE_FEATURES),
            },
            timeout=15,
        )
        if resp.status_code != 200:
            break

        data = resp.json()
        instructions = (
            data.get("data", {})
            .get("user", {})
            .get("result", {})
            .get("timeline_v2", {})
            .get("timeline", {})
            .get("instructions", [])
        )

        new_cursor = None
        found_any = False

        for inst in instructions:
            if inst.get("type") == "TimelineAddEntries":
                entries = inst.get("entries", [])
            elif inst.get("type") == "TimelineAddToModule":
                entries = inst.get("moduleItems", [])
            else:
                entries = inst.get("entries", [])

            for entry in entries:
                if cancel_event and cancel_event.is_set():
                    break
                if len(all_tweets) >= limit:
                    break

                # Extract tweet from nested structure
                content = entry.get("content", {})
                entry_type = content.get("entryType", "")

                tweet_result = None
                if entry_type == "TimelineTimelineItem":
                    tweet_result = (
                        content.get("itemContent", {})
                        .get("tweet_results", {})
                        .get("result", {})
                    )
                elif entry_type == "TimelineTimelineModule":
                    items = content.get("items", [])
                    if items:
                        tweet_result = (
                            items[0].get("item", {})
                            .get("itemContent", {})
                            .get("tweet_results", {})
                            .get("result", {})
                        )

                if not tweet_result or tweet_result.get("__typename") == "TweetTombstone":
                    continue

                # Check if tweet has media
                legacy = tweet_result.get("legacy", {})
                media = legacy.get("extended_entities", {}).get("media", [])
                if not media:
                    continue

                all_tweets.append(tweet_result)
                found_any = True
                if callback:
                    callback(len(all_tweets), limit)

                # Look for cursor
                if content.get("cursorType") == "Bottom":
                    new_cursor = content.get("value")

            # Check for cursor in entry
            if entry.get("content", {}).get("cursorType") == "Bottom":
                new_cursor = entry.get("content", {}).get("value")

        if not found_any or not new_cursor or new_cursor == cursor:
            break
        cursor = new_cursor

    return all_tweets


def _x_tweet_to_queue_task(tweet_result: dict, custom_name: str, output_dir, batch_id: str = "") -> DownloadTask:
    """Convert a GraphQL tweet result to a DownloadTask."""
    legacy = tweet_result.get("legacy", {})
    author = legacy.get("user", {}).get("screen_name", "") if "user" in legacy else ""
    if not author:
        # Try to get from core.user_results
        core = tweet_result.get("core", {})
        author = core.get("user_results", {}).get("result", {}).get("legacy", {}).get("screen_name", "")

    title = legacy.get("full_text", "")[:80]
    tweet_id = tweet_result.get("rest_id", "")
    url = f"https://x.com/{author}/status/{tweet_id}" if author else ""

    # Parse post time
    created_at = legacy.get("created_at", "")
    post_time = ""
    if created_at:
        try:
            from datetime import datetime
            dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
            post_time = dt.strftime("%Y%m%d")
        except Exception:
            pass

    # Determine media type
    media = legacy.get("extended_entities", {}).get("media", [])
    has_video = any(m.get("type") in ("video", "animated_gif") for m in media)
    has_photo = any(m.get("type") == "photo" for m in media)
    if has_video and has_photo:
        media_type = "mixed"
    elif has_video:
        media_type = "video"
    elif has_photo:
        media_type = "image"
    else:
        media_type = ""

    return DownloadTask(
        url=url,
        format_id=None,
        output_dir=output_dir,
        custom_name=custom_name,
        author=author,
        post_time=post_time,
        platform="x",
        batch_id=batch_id,
    )


def _x_extract_info(url: str) -> VideoInfo:
    session = _x_api_session()
    tweet_id = _x_tweet_id_from_url(url)
    tweet_result = _x_get_tweet_info(session, tweet_id)

    legacy = tweet_result.get("legacy", {})
    author = (
        legacy.get("user", {}).get("screen_name", "")
        or tweet_result.get("core", {}).get("user_results", {}).get("result", {}).get("legacy", {}).get("screen_name", "")
    )
    title = legacy.get("full_text", "")[:80] or "X post"

    # Parse post time
    created_at = legacy.get("created_at", "")
    post_time = ""
    if created_at:
        try:
            from datetime import datetime
            dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
            post_time = dt.strftime("%Y%m%d")
        except Exception:
            pass

    # Extract media items (images + videos)
    items = _x_extract_tweet_media(tweet_result)

    # Get thumbnail (first media item or user profile pic)
    thumbnail = None
    media_list = legacy.get("extended_entities", {}).get("media", [])
    if media_list:
        thumbnail = media_list[0].get("media_url_https")

    # For video-only tweets, also get yt-dlp format info for quality selection
    formats = []
    duration = None
    has_video = any(item.is_video for item in items)
    if has_video and len(items) == 1:
        # Single video — use yt-dlp for format selection
        try:
            cookie = get_cookie_path()
            opts = _yt_opts(cookie)
            opts["skip_download"] = True
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl_info = ydl.extract_info(url, download=False)
            ydl_info = yt_dlp.YoutubeDL.sanitize_info(ydl_info)
            formats = ydl_info.get("formats", [])
            duration = ydl_info.get("duration")
        except Exception:
            pass

    return VideoInfo(
        title=title,
        url=url,
        thumbnail=thumbnail,
        duration=duration,
        formats=formats,
        platform="x",
        author=author,
        post_time=post_time,
        items=items,
    )


# ---- X-Sou Search API ----

from .x_sou_client import x_sou_search, x_sou_download_video

# ---- Public API ----

def extract_info(url: str) -> VideoInfo:
    parsed = parse_url(url)
    if parsed.platform == Platform.YOUTUBE:
        return _yt_extract_info(url)
    elif parsed.platform == Platform.INSTAGRAM:
        if get_platform_mode("instagram") == "api":
            from .apify_client import get_apify_client as _get_apify_client
            return _get_apify_client().extract_post_info(url)
        return _ig_extract_info(url)
    elif parsed.platform == Platform.X:
        return _x_extract_info(url)
    else:
        # Phase 1 Step 2: try domestic platform providers
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
                        if task._cancelled:
                            raise _CancelledError()
                        pause_event.wait()
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
        downloaded_any = True

    if not downloaded_any:
        _cleanup_empty_dir(post_out_dir)

    task.status = "done"
    task.progress = 100
    task.filename = str(post_out_dir)


def _x_download_direct(task, pause_event, on_progress):
    """Download a video from a pre-resolved direct URL (e.g. X-Sou)."""
    out_dir = _resolve_output_dir(task)
    out_dir.mkdir(parents=True, exist_ok=True)
    policy = get_file_conflict_policy()
    out_name = _effective_name(task)

    resolved_stem = _resolve_conflict_stem(out_dir, out_name, policy)
    if resolved_stem is None:
        task.status = "done"
        task.progress = 100
        return

    filename = out_dir / f"{resolved_stem}.mp4"

    task.status = "downloading"
    if on_progress:
        on_progress(task)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Referer": "https://x.com/",
    }
    resp = requests.get(task.direct_url, stream=True, timeout=30, headers=headers)
    try:
        if resp.status_code == 403:
            # Video from suspended/deleted account — not downloadable
            task.status = "error"
            task.error = "403 Forbidden — 内容已不可用（账号可能被封禁）"
            task.error_category = "content"
            resp.close()
            return
        resp.raise_for_status()
        total_size = int(resp.headers.get("content-length", 0))
        downloaded = 0
        try:
            with open(filename, "wb") as f:
                for chunk in resp.iter_content(8192):
                    pause_event.wait()
                    if task._cancelled:
                        raise _CancelledError()
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size:
                        task.progress = downloaded / total_size * 100
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
    task.filename = str(filename)


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
                            pause_event.wait()
                            if task._cancelled:
                                raise _CancelledError()
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


def _direct_download_with_pause(task, pause_event, on_progress):
    """通用直链下载（浏览器提取的媒体 URL 或本地文件路径）。"""
    import urllib.parse
    import shutil

    out_dir = _resolve_output_dir(task)
    out_dir.mkdir(parents=True, exist_ok=True)
    policy = get_file_conflict_policy()
    out_name = _effective_name(task)

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
    ext = Path(url_path).suffix or ".mp4"
    if ext == ".jpeg":
        ext = ".jpg"

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

    resp = requests.get(task.direct_url, stream=True, timeout=120, headers=headers)
    try:
        resp.raise_for_status()
        total_size = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(filename, "wb") as f:
            for chunk in resp.iter_content(8192):
                pause_event.wait()
                if task._cancelled:
                    raise _CancelledError()
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
    except Exception:
        Path(filename).unlink(missing_ok=True)
        raise
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
                try:
                    from .providers.base import Platform as _P
                    prov = get_provider_for(_P(task.platform))
                    if prov:
                        pheaders = prov.get_request_headers()
                        for k, v in pheaders.items():
                            headers.setdefault(k, v)
                except Exception:
                    pass
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
                                if task._cancelled:
                                    raise _CancelledError()
                                pause_event.wait()
                                if task._cancelled:
                                    raise _CancelledError()
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
                elif "xiaohongshu" in item.url or "xhscdn" in item.url:
                    img_headers.setdefault("Referer", "https://www.xiaohongshu.com/")
                elif "cdninstagram" in item.url or "fbcdn" in item.url:
                    img_headers.setdefault("Referer", "https://www.instagram.com/")
                resp = requests.get(item.url, timeout=30, headers=img_headers)
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
