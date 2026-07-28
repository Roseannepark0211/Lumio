"""Lumio V4 — YouTube Provider。

包装 yt-dlp 提取视频元数据 + 格式列表，供下载时选格式。
所有下载逻辑仍由 downloader.py 的 yt-dlp 路径处理。

URL 格式：
- youtube.com/watch?v={id}
- youtu.be/{id}
- youtube.com/playlist?list={id}  （批量枚举，由 yt_dialog.py 处理）
- youtube.com/@channel/videos       （批量枚举）
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from .base import BaseProvider, FormatOption, MediaInfo, MediaItem, MediaType, Platform
from .registry import register

logger = logging.getLogger(__name__)

# URL 模式
_YT_WATCH_RE = re.compile(r"youtube\.com/watch\?v=([\w-]+)")
_YT_SHORT_RE = re.compile(r"youtu\.be/([\w-]+)")
_YT_EMBED_RE = re.compile(r"youtube\.com/embed/([\w-]+)")
_YT_SHORTS_RE = re.compile(r"youtube\.com/shorts/([\w-]+)")


def _yt_opts(cookie_path) -> dict:
    """构造 yt-dlp 选项 — 已迁移到 utils.yt_opts，此处保留 re-export。"""
    from ..utils.yt_opts import yt_opts
    return yt_opts(cookie_path)


@register
class YouTubeProvider(BaseProvider):
    """YouTube 内容解析 Provider（包装 yt-dlp）。

    下载时仍走 downloader.py 的 _yt_download_with_pause（yt-dlp 路径），
    本 Provider 只负责 extract_info 阶段。
    """

    @property
    def platform(self) -> Platform:
        return Platform.YOUTUBE

    def match(self, url: str) -> bool:
        return bool(
            "youtube.com" in url
            or "youtu.be" in url
            or "googleapis.com/youtube" in url
        )

    def extract_info(self, url: str) -> MediaInfo:
        import yt_dlp
        from ..utils.config import get_cookie_path

        cookie = get_cookie_path()
        opts = _yt_opts(cookie)
        opts["skip_download"] = True

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            logger.warning("YouTube 解析失败 (%s): %s", url, e)
            return MediaInfo(
                platform=Platform.YOUTUBE,
                url=url,
                title="YouTube（解析失败）",
                author="",
                description=f"yt-dlp 提取失败：{e}",
            )

        info = yt_dlp.YoutubeDL.sanitize_info(info)
        entries = info.get("entries") or [info]
        first = entries[0]

        author = (
            first.get("uploader")
            or first.get("channel")
            or first.get("creator")
            or ""
        )

        upload_date = first.get("upload_date", "")
        post_time = ""
        if upload_date and len(upload_date) == 8:
            post_time = f"{upload_date[:4]}{upload_date[4:6]}{upload_date[6:8]}"

        # 构建 FormatOption 列表（供 Home 格式选择）
        formats = []
        for f in first.get("formats", []):
            fmt_id = f.get("format_id", "")
            if not fmt_id:
                continue
            ext = f.get("ext", "mp4")
            vcodec = f.get("vcodec", "none")
            acodec = f.get("acodec", "none")
            if vcodec != "none" and acodec != "none":
                ftype = "video"
            elif vcodec != "none":
                ftype = "video"
            elif acodec != "none":
                ftype = "audio"
            else:
                continue
            w = f.get("width") or 0
            h = f.get("height") or 0
            label_parts = []
            if h:
                label_parts.append(f"{h}p")
            if f.get("fps"):
                label_parts.append(f"{f['fps']}fps")
            label = " ".join(label_parts) if label_parts else fmt_id
            formats.append(FormatOption(
                format_id=fmt_id,
                label=label,
                type=ftype,
                ext=ext,
                width=w,
                height=h,
            ))

        return MediaInfo(
            platform=Platform.YOUTUBE,
            url=url,
            title=first.get("title", "Unknown"),
            author=author,
            post_time=post_time,
            thumbnail=first.get("thumbnail", ""),
            duration=first.get("duration"),
            formats=formats,
            # 下载仍走 yt-dlp，不需要 media_items 直链
            media_items=[],
        )
