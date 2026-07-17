"""Lumio V4 — 抖音 (Douyin) Provider。

通过网页抓取 + API 解析抖音视频。
- douyin.com/video/{id}
- douyin.com/user/{username}
- iesdouyin.com 短链接
"""

from __future__ import annotations

import json
import logging
import re
import html as _html
from typing import Optional
from urllib.parse import urlparse, parse_qs

from .base import BaseProvider, MediaInfo, MediaItem, MediaType, FormatOption, Platform
from .network.client import NetworkClient
from .network.headers import platform_headers
from .registry import register
from ..utils.error_types import ErrorCategory, classify_error as _ce

logger = logging.getLogger(__name__)

_VIDEO_ID_RE = re.compile(r"douyin\.com/video/(\d+)")
_PROFILE_RE = re.compile(r"douyin\.com/user/([\w.]+)")
_IES_RE = re.compile(r"iesdouyin\.com/(?:share/)?video/(\d+)")
_SHARE_URL_RE = re.compile(r"v\.douyin\.com/[\w]+")


def _extract_video_id(url: str) -> Optional[str]:
    m = _VIDEO_ID_RE.search(url) or _IES_RE.search(url)
    return m.group(1) if m else None


@register
class DouyinProvider(BaseProvider):
    """抖音 (Douyin) 内容解析 Provider。"""

    @property
    def platform(self) -> Platform:
        return Platform.DOUYIN

    def match(self, url: str) -> bool:
        return bool(_VIDEO_ID_RE.search(url) or _PROFILE_RE.search(url)
                    or _IES_RE.search(url) or _SHARE_URL_RE.search(url))

    def extract_info(self, url: str) -> MediaInfo:
        video_id = _extract_video_id(url)
        if not video_id:
            # 个人主页
            m = _PROFILE_RE.search(url)
            if m:
                return MediaInfo(
                    platform=Platform.DOUYIN,
                    url=url,
                    title="抖音（个人主页）",
                    author=m.group(1),
                    description="抖音个人主页批量下载暂未接入，请使用单条视频 URL。",
                )
            return MediaInfo(
                platform=Platform.DOUYIN,
                url=url,
                title="抖音（链接识别失败）",
                author="",
                description="无法识别抖音链接格式。",
            )

        client = NetworkClient(Platform.DOUYIN)

        # 尝试通过网页抓取获取信息
        html_url = f"https://www.douyin.com/video/{video_id}"
        html = client.get_html(html_url)

        if html:
            items, title, author, thumb, post_time = self._parse_from_html(html)
            if items:
                return MediaInfo(
                    platform=Platform.DOUYIN,
                    url=url,
                    title=title or "抖音视频",
                    author=author or "",
                    thumbnail=thumb or "",
                    post_time=post_time or "",
                    description=title or "抖音视频",
                    media_items=items,
                )

        return MediaInfo(
            platform=Platform.DOUYIN,
            url=url,
            title="抖音（解析失败）",
            author="",
            description=f"无法解析抖音视频（video_id: {video_id}）。视频可能不存在或需要 Cookie。",
        )

    def _parse_from_html(self, html: str) -> tuple[list[MediaItem], str, str, str, str]:
        """从抖音页面 HTML 提取媒体信息。"""
        items: list[MediaItem] = []
        title = ""
        author = ""
        thumbnail = ""
        post_time = ""
        seen: set[str] = set()

        # og:title
        m = re.search(r"""<meta\s+property=["']og:title["']\s+content=["']([^"']+)["']""", html)
        if m:
            title = _html.unescape(m.group(1)).strip()[:80]

        # og:image (thumbnail)
        m = re.search(r"""<meta\s+property=["']og:image["']\s+content=["']([^"']+)["']""", html)
        if m:
            thumbnail = m.group(1)
            if thumbnail not in seen:
                seen.add(thumbnail)
                items.append(MediaItem(url=thumbnail, is_video=False, index=0))

        # window.__INITIAL_STATE__ (SSR data)
        m = re.search(r"window\.__INITIAL_STATE__\s*=\s*({.*?});", html, re.DOTALL)
        if m:
            try:
                state = json.loads(m.group(1))
                cursor_data = state.get("CursorData", {}) or {}
                video_data = cursor_data.get("videoData", {}) or {}
                if not video_data:
                    video_data = state.get("videoData", {}) or {}
                if not video_data:
                    # 尝试其他路径
                    for key in state:
                        if isinstance(state[key], dict) and "video" in (state[key].get("type", "") or ""):
                            video_data = state[key]
                            break

                if video_data:
                    # 标题
                    title = title or video_data.get("desc", "") or video_data.get("title", "") or ""
                    # 作者
                    author_info = video_data.get("author", {}) or {}
                    author = author_info.get("nickname", "") or author_info.get("nick_name", "") or ""
                    author_id = str(author_info.get("uid", author_info.get("id", "")))
                    # 封面
                    thumb = video_data.get("cover", "") or video_data.get("poster", "") or (
                        video_data.get("video", {}).get("cover", {}).get("url_list", [""])[0]
                    )
                    if thumb:
                        thumbnail = thumb
                    if not items and thumb:
                        items.append(MediaItem(url=thumb, is_video=False, index=0))

                    # 视频 URL
                    video = video_data.get("video", {}) or {}
                    url_list = video.get("url_list", []) or []
                    if url_list:
                        video_url = url_list[0]
                        if video_url:
                            items.append(MediaItem(url=video_url, is_video=True, index=len(items)))

                    # 时间
                    create_time = video_data.get("create_time", "") or video_data.get("timestamp", "")
                    if create_time:
                        import datetime
                        try:
                            post_time = datetime.datetime.fromtimestamp(
                                int(create_time), tz=datetime.timezone.utc
                            ).strftime("%Y%m%d_%H%M%S")
                        except (ValueError, OSError):
                            post_time = str(create_time)

                    return items, title, author, thumbnail, post_time
            except (json.JSONDecodeError, AttributeError) as e:
                logger.debug("Failed to parse __INITIAL_STATE__: %s", e)

        # 纯 HTML 提取：video URL + images
        # og:video
        m = re.search(r"""<meta\s+property=["']og:video["']\s+content=["']([^"']+)["']""", html)
        if m:
            video_url = m.group(1)
            if video_url not in seen:
                seen.add(video_url)
                items.append(MediaItem(url=video_url, is_video=True, index=len(items)))

        # og:image (repeat check if second call hit)
        m = re.search(r"""<meta\s+property=["']og:image["']\s+content=["']([^"']+)["']""", html)
        if m and m.group(1) not in seen:
            url = m.group(1)
            seen.add(url)
            items.append(MediaItem(url=url, is_video=False, index=len(items)))

        # 提取任何在 video/ douyin 域下的 mp4
        for m in re.finditer(r'(https?://[^"\'\s]*v[0-9a-z]*\.douyin\.(?:com|cdn)[^"\'\s]*(?:mp4))',
                             html, re.IGNORECASE):
            url = m.group(1)
            if url not in seen:
                seen.add(url)
                items.append(MediaItem(url=url, is_video=True, index=len(items)))

        # 提取图片 URL
        for m in re.finditer(r'(https?://[^"\'\s]*douyin[^"\'\s]*(?:png|jpg|jpeg|webp))',
                             html, re.IGNORECASE):
            url = m.group(1)
            if url not in seen:
                seen.add(url)
                items.append(MediaItem(url=url, is_video=False, index=len(items)))

        return items, title, author, thumbnail, post_time

    def get_request_headers(self) -> dict[str, str]:
        return platform_headers(Platform.DOUYIN)

    def enumerate_profile_posts(
        self,
        identifier: str,
        limit: int = 20,
        callback=None,
        cancel_event=None,
    ) -> list[dict]:
        """抖音主页批量枚举暂不支持。"""
        logger.warning(
            "Douyin enumerate_profile_posts(%s, limit=%d): 暂不支持主页批量枚举",
            identifier, limit,
        )
        return []

    def classify_error(self, error: Exception | str) -> str:
        text = str(error).lower()
        if any(kw in text for kw in ("cookie", "login", "auth", "session")):
            return ErrorCategory.COOKIE_EXPIRED.value
        if any(kw in text for kw in ("429", "rate limit", "too many")):
            return ErrorCategory.RATE_LIMITED.value
        return _ce(error).value
