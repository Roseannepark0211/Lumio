"""Provider dispatch — bridge between Provider system and existing download flow.

Phase 1 Step 2:
  Provider → MediaInfo → VideoInfo → Queue
  (The "DownloadTask" bridge from the design doc)

V4.0 additions:
  - URL normalization before detection (Section 20)
  - URL → MediaInfo cache (Section 23)
"""

from __future__ import annotations

import logging
from typing import Optional

from . import cache as provider_cache
from .base import MediaInfo
from .detector import detect_domestic
from .registry import get_provider
from .url_normalizer import normalize_url

logger = logging.getLogger(__name__)


def _to_downloader_item(item):
    """Convert provider MediaItem to media_utils.MediaItem for queue/GUI compatibility.

    V4.0 Phase 3: passes all fields including media_type, extension, live_photo, etc.
    """
    from ..utils.media_utils import MediaItem as _DownloaderMediaItem
    from .base import LivePhoto as _LivePhoto

    # Convert LivePhoto dataclass to dict for serialization
    lp_dict = None
    if item.live_photo is not None:
        if isinstance(item.live_photo, _LivePhoto):
            lp_dict = {
                "image": item.live_photo.image,
                "video": item.live_photo.video,
                "cover": item.live_photo.cover,
            }
        elif isinstance(item.live_photo, dict):
            lp_dict = item.live_photo
        else:
            lp_dict = None

    return _DownloaderMediaItem(
        url=item.url,
        is_video=item.is_video,
        index=item.index,
        media_type=item.media_type.value if hasattr(item.media_type, "value") else str(item.media_type),
        width=item.width,
        height=item.height,
        extension=item.extension,
        size=item.size,
        quality=item.quality,
        mime=item.mime,
        id=item.id,
        filename=item.filename,
        live_photo=lp_dict,
        original_url=item.original_url,
    )


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
    # Step 1: normalize short URLs (t.cn -> weibo.com, etc.)
    normalized = normalize_url(url)

    # Step 2: check cache
    cached = provider_cache.get(normalized)
    if cached is not None:
        logger.debug("resolve_via_providers: cache hit for %s", normalized[:60])
        return media_info_to_video_info(cached, url)

    result = detect_domestic(normalized)
    if result is None:
        return None

    _platform, _kind = result
    provider = get_provider(normalized)
    if provider is None:
        return None

    media_info = provider.extract_info(normalized)

    # Step 3: cache the result
    try:
        provider_cache.set(normalized, media_info)
    except Exception:
        pass

    return media_info_to_video_info(media_info, url)
