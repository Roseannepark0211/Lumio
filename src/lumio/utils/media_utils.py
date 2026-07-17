from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


_VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv"}
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
_AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg"}


def infer_media_type(file_path: str, platform: str = "") -> str:
    """Infer media type from file path or directory contents."""
    if not file_path:
        return ""
    p = Path(file_path)
    if p.is_dir():
        try:
            exts = {f.suffix.lower() for f in p.iterdir() if f.is_file()}
        except OSError:
            return ""
        has_video = exts & _VIDEO_EXTS
        has_image = exts & _IMAGE_EXTS
        if has_video and has_image:
            return "mixed"
        if has_video:
            return "video"
        if has_image:
            return "image"
        return ""
    if p.is_file():
        ext = p.suffix.lower()
        if ext in _VIDEO_EXTS:
            return "video"
        if ext in _IMAGE_EXTS:
            return "image"
        if ext in _AUDIO_EXTS:
            return "audio"
        return ""
    # Path does not exist — infer from platform as fallback
    if platform == "instagram":
        return "mixed"
    return ""


def format_size(size_bytes: int, zero_default: str = "—") -> str:
    """Format bytes as human-readable size string."""
    if size_bytes <= 0:
        return zero_default
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


@dataclass
class MediaItem:
    """Single media resource (image or video) for download pipeline."""
    url: str
    is_video: bool
    index: int = 0


@dataclass
class VideoInfo:
    """Unified media metadata result from URL extraction."""
    title: str
    url: str
    thumbnail: str | None
    duration: int | None  # seconds
    formats: list[dict]  # raw yt-dlp format dicts (YouTube only)
    platform: str
    author: str = ""  # uploader / channel / IG username
    items: list[MediaItem] = field(default_factory=list)
    post_time: str = ""
