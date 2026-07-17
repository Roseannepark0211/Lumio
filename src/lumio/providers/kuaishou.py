"""Lumio V4 — 快手 (Kuaishou) Provider。

通过页面抓取和 API 解析快手视频。
- kuaishou.com/{id}
"""

from __future__ import annotations

import json
import logging
import re
import html as _html
from typing import Optional

from .base import BaseProvider, MediaInfo, MediaItem, MediaType, Platform
from .network.client import NetworkClient
from .network.headers import platform_headers
from .registry import register
from ..utils.error_types import ErrorCategory, classify_error as _ce

logger = logging.getLogger(__name__)

_VIDEO_ID_RE = re.compile(r"(?:kuaishou|kwai)\.com/(?:photo|short-video)/([\w]+)")
_PROFILE_RE = re.compile(r"(?:kuaishou|kwai)\.com/profile/(\d+)")


def _extract_video_id(url: str) -> Optional[str]:
    m = _VIDEO_ID_RE.search(url)
    return m.group(1) if m else None


@register
class KuaishouProvider(BaseProvider):
    """快手 (Kuaishou) 内容解析 Provider。"""

    @property
    def platform(self) -> Platform:
        return Platform.KUAISHOU

    def match(self, url: str) -> bool:
        return bool(_VIDEO_ID_RE.search(url) or _PROFILE_RE.search(url))

    def extract_info(self, url: str) -> MediaInfo:
        video_id = _extract_video_id(url)
        if not video_id:
            if _PROFILE_RE.search(url):
                return MediaInfo(
                    platform=Platform.KUAISHOU,
                    url=url,
                    title="快手（个人主页）",
                    author="",
                    description="快手个人主页批量下载暂未接入，请使用单条视频 URL。",
                )
            return MediaInfo(
                platform=Platform.KUAISHOU,
                url=url,
                title="快手（链接识别失败）",
                author="",
                description="无法识别快手链接格式。",
            )

        client = NetworkClient(Platform.KUAISHOU)
        html_url = f"https://www.kuaishou.com/photo/{video_id}"
        html = client.get_html(html_url)

        if html:
            items, title, author, thumb, post_time = self._parse_from_html(html)
            if items:
                return MediaInfo(
                    platform=Platform.KUAISHOU,
                    url=url,
                    title=title or "快手视频",
                    author=author or "",
                    thumbnail=thumb or "",
                    post_time=post_time or "",
                    description=title or "快手视频",
                    media_items=items,
                )

        return MediaInfo(
            platform=Platform.KUAISHOU,
            url=url,
            title="快手（解析失败）",
            author="",
            description=f"无法解析快手视频（video_id: {video_id}）。",
        )

    def _parse_from_html(self, html: str) -> tuple[list[MediaItem], str, str, str, str]:
        """从快手页面 HTML 提取媒体信息。"""
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

        # window.__INITIAL_STATE__
        m = re.search(r"window\.__INITIAL_STATE__\s*=\s*({.*?});", html, re.DOTALL)
        if m:
            try:
                state = json.loads(m.group(1))
                photo = state.get("photo", {}) or {}
                if not photo:
                    for key in ("detail", "videoInfo", "feed"):
                        photo = state.get(key, {}) or {}
                        if photo:
                            break

                if photo:
                    title = title or photo.get("caption", "") or photo.get("title", "") or ""
                    author_info = photo.get("user", {}) or {}
                    if not author_info:
                        author_info = photo.get("author", {}) or {}
                    author = author_info.get("name", "") or author_info.get("nickname", "") or ""
                    author_id = str(author_info.get("id", author_info.get("userId", "")))

                    # 封面
                    cover = photo.get("coverUrl", "") or photo.get("cover", "") or (
                        photo.get("coverUrls", [{}])[0].get("url", "") if photo.get("coverUrls") else ""
                    )
                    if cover:
                        thumbnail = cover

                    # 视频 URL
                    video_url = ""
                    for key in ("videoUrl", "srcUrl", "mainUrl", "playUrl", "url"):
                        video_url = photo.get(key, "")
                        if video_url:
                            break
                    if not video_url:
                        # 多分辨率
                        resolutions = photo.get("videoResolutions", {}) or {}
                        if resolutions:
                            best_key = sorted(resolutions.keys(), reverse=True)[0]
                            video_url = resolutions[best_key].get("url", "")
                    if video_url:
                        items.append(MediaItem(url=video_url, is_video=True, index=len(items)))
                    elif thumbnail and not items:
                        items.append(MediaItem(url=thumbnail, is_video=False, index=0))

                    # 时间
                    ts = photo.get("timestamp", "") or photo.get("createTime", "") or photo.get("createdAt", "")
                    if ts:
                        import datetime
                        try:
                            ts_int = int(ts)
                            # ms timestamp
                            if ts_int > 1e12:
                                ts_int = ts_int // 1000
                            post_time = datetime.datetime.fromtimestamp(
                                ts_int, tz=datetime.timezone.utc
                            ).strftime("%Y%m%d_%H%M%S")
                        except (ValueError, OSError):
                            post_time = str(ts)

                    return items, title, author, thumbnail, post_time
            except (json.JSONDecodeError, AttributeError) as e:
                logger.debug("Failed to parse __INITIAL_STATE__: %s", e)

        # og:video
        m = re.search(r"""<meta\s+property=["']og:video["']\s+content=["']([^"']+)["']""", html)
        if m:
            video_url = m.group(1)
            if video_url not in seen:
                seen.add(video_url)
                items.append(MediaItem(url=video_url, is_video=True, index=len(items)))

        return items, title, author, thumbnail, post_time

    def get_request_headers(self) -> dict[str, str]:
        return platform_headers(Platform.KUAISHOU)

    def enumerate_profile_posts(
        self,
        identifier: str,
        limit: int = 20,
        callback=None,
        cancel_event=None,
    ) -> list[dict]:
        """快手主页批量枚举暂不支持。"""
        logger.warning(
            "Kuaishou enumerate_profile_posts(%s, limit=%d): 暂不支持主页批量枚举",
            identifier, limit,
        )
        return []

    def classify_error(self, error: Exception | str) -> str:
        text = str(error).lower()
        if any(kw in text for kw in ("cookie", "login", "auth", "session")):
            return ErrorCategory.COOKIE_EXPIRED.value
        if any(kw in text for kw in ("429", "rate limit")):
            return ErrorCategory.RATE_LIMITED.value
        return _ce(error).value
