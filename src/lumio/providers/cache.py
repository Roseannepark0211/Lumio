"""URL → MediaInfo 缓存模块（Section 23）。

支持两级缓存：
- 内存缓存（TTL 过期，进程内共享）
- 文件缓存（JSON 文件持久化，跨会话复用）

Usage:
    from .cache import get_cached, set_cached

    info = get_cached(url)
    if info is None:
        info = provider.extract_info(url)
        set_cached(url, info)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from .base import FormatOption, MediaInfo, MediaItem, Platform

logger = logging.getLogger(__name__)

# === 内存缓存 ===

_MEMORY_TTL = 1800  # 30 分钟
_cache: dict[str, tuple[float, MediaInfo]] = {}
_lock = threading.Lock()


def _hash_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def get_cached(url: str, ttl: int = _MEMORY_TTL) -> Optional[MediaInfo]:
    """从内存缓存中获取解析结果。

    优先检查内存缓存，命中且未过期则返回 MediaInfo。
    """
    key = _hash_url(url)
    with _lock:
        entry = _cache.get(key)
        if entry is not None:
            expiry, info = entry
            if time.time() < expiry:
                return info
            # 过期，惰性删除
            del _cache[key]
    return None


def set_cached(url: str, info: MediaInfo, ttl: int = _MEMORY_TTL) -> None:
    """将解析结果写入内存缓存。"""
    key = _hash_url(url)
    with _lock:
        _cache[key] = (time.time() + ttl, info)


def clear_cache() -> None:
    """清空所有缓存（内存 + 文件）。"""
    with _lock:
        _cache.clear()
    _clear_file_cache()


def cache_size() -> int:
    """当前内存缓存条目数。"""
    with _lock:
        return len(_cache)


# === 文件缓存（JSON 持久化） ===

_CACHE_DIR = Path.home() / ".lumio" / "provider_cache"
_CACHE_FILE = _CACHE_DIR / "cache.json"
_FILE_TTL = 86400  # 24 小时
_file_lock = threading.Lock()


def _media_item_to_dict(item: MediaItem) -> dict:
    d = {
        "url": item.url,
        "is_video": item.is_video,
        "index": item.index,
        "width": item.width,
        "height": item.height,
        "extension": item.extension,
        "original_url": item.original_url,
        "size": item.size,
        "quality": item.quality,
        "mime": item.mime,
        "id": item.id,
        "filename": item.filename,
        "media_type": item.media_type.value if item.media_type else "unknown",
    }
    if item.live_photo:
        d["live_photo"] = {
            "image": item.live_photo.image,
            "video": item.live_photo.video,
            "cover": item.live_photo.cover,
        }
    return d


def _dict_to_media_item(d: dict) -> MediaItem:
    from .base import LivePhoto, MediaType

    item = MediaItem(
        url=d["url"],
        is_video=d.get("is_video", False),
        index=d.get("index", 0),
        width=d.get("width", 0),
        height=d.get("height", 0),
        extension=d.get("extension", ""),
        original_url=d.get("original_url", ""),
        size=d.get("size", 0),
        quality=d.get("quality", ""),
        mime=d.get("mime", ""),
        id=d.get("id", ""),
        filename=d.get("filename", ""),
        media_type=MediaType(d.get("media_type", "unknown")),
    )
    lp = d.get("live_photo")
    if lp:
        item.live_photo = LivePhoto(
            image=lp.get("image", ""),
            video=lp.get("video", ""),
            cover=lp.get("cover", ""),
        )
    return item


def _format_option_to_dict(fmt: FormatOption) -> dict:
    return {
        "format_id": fmt.format_id,
        "label": fmt.label,
        "type": fmt.type,
        "ext": fmt.ext,
        "width": fmt.width,
        "height": fmt.height,
    }


def _dict_to_format_option(d: dict) -> FormatOption:
    return FormatOption(
        format_id=d["format_id"],
        label=d.get("label", ""),
        type=d.get("type", ""),
        ext=d.get("ext", ""),
        width=d.get("width", 0),
        height=d.get("height", 0),
    )


def _media_info_to_dict(info: MediaInfo) -> dict:
    if info.platform and isinstance(info.platform, Platform):
        platform_val = info.platform.value
    else:
        platform_val = str(info.platform) if info.platform else ""
    return {
        "platform": platform_val,
        "url": info.url,
        "title": info.title,
        "author": info.author,
        "author_id": info.author_id,
        "post_time": info.post_time,
        "thumbnail": info.thumbnail,
        "description": info.description,
        "duration": info.duration,
        "tags": info.tags,
        "type": info.type,
        "media_items": [_media_item_to_dict(it) for it in info.media_items],
        "formats": [_format_option_to_dict(f) for f in info.formats],
    }


def _dict_to_media_info(d: dict) -> Optional[MediaInfo]:
    try:
        platform = Platform(d["platform"]) if d.get("platform") else Platform.UNSUPPORTED
    except ValueError:
        platform = Platform.UNSUPPORTED
    return MediaInfo(
        platform=platform,
        url=d["url"],
        title=d.get("title", ""),
        author=d.get("author", ""),
        author_id=d.get("author_id", ""),
        post_time=d.get("post_time", ""),
        thumbnail=d.get("thumbnail", ""),
        description=d.get("description", ""),
        duration=d.get("duration"),
        tags=d.get("tags", []),
        type=d.get("type", ""),
        media_items=[_dict_to_media_item(it) for it in d.get("media_items", [])],
        formats=[_dict_to_format_option(f) for f in d.get("formats", [])],
    )


def _load_cache_file() -> dict[str, dict]:
    """从磁盘加载文件缓存。"""
    if not _CACHE_FILE.exists():
        return {}
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load provider cache file: %s", e)
        return {}


def _save_cache_file(data: dict[str, dict]) -> None:
    """原子写入文件缓存。"""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _CACHE_FILE.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        tmp.replace(_CACHE_FILE)
    except OSError as e:
        logger.warning("Failed to save provider cache file: %s", e)


def get_file_cached(url: str, ttl: int = _FILE_TTL) -> Optional[MediaInfo]:
    """从文件缓存中获取解析结果。"""
    key = _hash_url(url)
    with _file_lock:
        data = _load_cache_file()
        entry = data.get(key)
        if entry is None:
            return None
        cached_time = entry.get("_cached_at", 0)
        if time.time() - cached_time > ttl:
            # 过期
            data.pop(key, None)
            _save_cache_file(data)
            return None
        return _dict_to_media_info(entry.get("info", {}))


def set_file_cached(url: str, info: MediaInfo) -> None:
    """将解析结果写入文件缓存。"""
    key = _hash_url(url)
    with _file_lock:
        data = _load_cache_file()
        data[key] = {
            "_cached_at": time.time(),
            "info": _media_info_to_dict(info),
        }
        # 限制文件缓存大小：保留最近 500 条
        if len(data) > 500:
            sorted_items = sorted(
                data.items(), key=lambda x: x[1].get("_cached_at", 0), reverse=True
            )
            data = dict(sorted_items[:500])
        _save_cache_file(data)


def _clear_file_cache() -> None:
    """清空文件缓存。"""
    with _file_lock:
        if _CACHE_FILE.exists():
            try:
                _CACHE_FILE.unlink()
            except OSError:
                pass


# === 统一缓存接口 ===

def get(url: str, use_file_cache: bool = True) -> Optional[MediaInfo]:
    """统一查询缓存：先查内存，未命中再查文件。"""
    info = get_cached(url)
    if info is not None:
        return info
    if use_file_cache:
        info = get_file_cached(url)
        if info is not None:
            # 回填到内存缓存，缩短 TTL 避免文件缓存项长期占内存
            set_cached(url, info, ttl=_MEMORY_TTL)
            return info
    return None


def set(url: str, info: MediaInfo, use_file_cache: bool = True) -> None:
    """统一写入缓存（内存 + 可选文件）。"""
    set_cached(url, info)
    if use_file_cache:
        try:
            set_file_cached(url, info)
        except Exception:
            pass


__all__ = [
    "get",
    "set",
    "get_cached",
    "set_cached",
    "get_file_cached",
    "set_file_cached",
    "clear_cache",
    "cache_size",
]
