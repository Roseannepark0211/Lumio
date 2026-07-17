"""Provider dispatch — bridge between Provider system and existing download flow.

Phase 1 Step 2:
  Provider → MediaInfo → VideoInfo → Queue
  (The "DownloadTask" bridge from the design doc)
"""

from __future__ import annotations

from typing import Optional

from .base import MediaInfo
from .detector import detect_domestic
from .registry import get_provider


def _to_downloader_item(item) -> dict:
    """Convert provider MediaItem to a plain dict (avoids circular import)."""
    return {
        "url": item.url,
        "is_video": item.is_video,
        "index": item.index,
    }


def media_info_to_video_info(media: MediaInfo, url: str) -> object:
    """Convert provider MediaInfo to the existing VideoInfo format.

    This bridges the Provider → Queue flow so that Provider results can be
    fed into DownloadManager.add_task_from_info().

    Lazy-imports VideoInfo to avoid circular dependency:
      downloader → providers.dispatch → downloader
    """
    from ..utils.media_utils import VideoInfo as _VideoInfo

    items = [_to_downloader_item(it) for it in media.media_items]

    # Build format dicts for compatibility with format selection UI
    formats = []
    for fmt in media.formats:
        formats.append({
            "format_id": fmt.format_id,
            "ext": fmt.ext,
            "height": fmt.height,
            "width": fmt.width,
            "vcodec": "avc1",
            "acodec": "mp4a",
            "tbr": 0,
            "format_note": fmt.label,
        })

    return _VideoInfo(
        title=media.title or "Untitled",
        url=url,
        thumbnail=media.thumbnail or None,
        duration=media.duration,
        formats=formats,
        platform=media.platform.value,
        author=media.author,
        items=items,
        post_time=media.post_time,
    )


def resolve_via_providers(url: str) -> Optional[object]:
    """Try to resolve a URL through the Provider system.

    Returns a VideoInfo if a registered provider handles the URL,
    or None if no provider matches.

    This is called as a fallback in downloader.extract_info().
    """
    result = detect_domestic(url)
    if result is None:
        return None

    _platform, _kind = result
    provider = get_provider(url)
    if provider is None:
        return None

    media_info = provider.extract_info(url)
    return media_info_to_video_info(media_info, url)
