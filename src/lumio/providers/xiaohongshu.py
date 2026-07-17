"""Lumio V4 — 小红书 (Xiaohongshu) Provider。

通过页面 HTML 爬取或 API 接口解析小红书笔记内容。
- 支持 xhslink.com 短链接自动展开
- 图片 / 视频笔记解析
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

# 短链接展开 API
_XHSLINK_EXPAND = "https://www.xiaohongshu.com"

# 笔记正则
_NOTE_ID_RE = re.compile(r"xiaohongshu\.com/explore/([a-f0-9]+)")
_PROFILE_ID_RE = re.compile(r"xiaohongshu\.com/user/profile/([a-f0-9]+)")
_SHORTLINK_RE = re.compile(r"xhslink\.com/[a-zA-Z0-9]+")


def _extract_note_id(url: str) -> Optional[str]:
    """从 URL 提取笔记 ID。"""
    m = _NOTE_ID_RE.search(url)
    return m.group(1) if m else None


def _is_profile_url(url: str) -> bool:
    return bool(_PROFILE_ID_RE.search(url) or _SHORTLINK_RE.search(url))


def _parse_media_type(note_data: dict) -> str:
    """从笔记数据推断媒体类型。"""
    note = note_data.get("note", {}) or note_data
    if note.get("type") == "video" or note.get("video", {}).get("media"):
        return "video"
    return "image"


def _extract_image_items(note: dict) -> list[MediaItem]:
    """从笔记数据中提取图片列表。"""
    items: list[MediaItem] = []
    image_list = note.get("image_list", []) or note.get("images", [])
    for idx, img in enumerate(image_list):
        url = (img.get("original", img.get("url", ""))
               or img.get("info_list", [{}])[0].get("url", ""))
        if not url:
            continue
        # 确保原图 URL
        url = re.sub(r"![\w.]+$", "", url)
        url = re.sub(r"~\w+", "", url)
        items.append(MediaItem(url=url, is_video=False, index=idx))
    return items


def _extract_video_item(note: dict) -> Optional[MediaItem]:
    """从笔记数据中提取视频。"""
    video = note.get("video", {}) or {}
    media = video.get("media", {}) or {}
    stream = media.get("stream", {}) or {}
    # 取最高分辨率
    master_url = stream.get("master_url", "")
    if not master_url:
        # fallback: 各分辨率
        res_list = stream.get("resolution_list", [])
        if res_list:
            best = max(res_list, key=lambda x: x.get("width", 0) or x.get("height", 0))
            master_url = best.get("url", "")
    if master_url:
        return MediaItem(url=master_url, is_video=True, index=0)
    return None


@register
class XiaohongshuProvider(BaseProvider):
    """小红书 (Xiaohongshu) 内容解析 Provider。"""

    @property
    def platform(self) -> Platform:
        return Platform.XIAOHONGSHU

    def match(self, url: str) -> bool:
        return bool(_NOTE_ID_RE.search(url) or _SHORTLINK_RE.search(url) or _PROFILE_ID_RE.search(url))

    def extract_info(self, url: str) -> MediaInfo:
        note_id = _extract_note_id(url)
        if not note_id:
            return MediaInfo(
                platform=Platform.XIAOHONGSHU,
                url=url,
                title="小红书（个人主页）",
                author="",
                description="小红书个人主页批量下载暂未接入，请使用单条笔记 URL。",
            )

        # 优先通过 API 获取
        api_url = f"https://www.xiaohongshu.com/api/sns/v1/note/{note_id}"
        client = NetworkClient(Platform.XIAOHONGSHU)
        data = client.get_json(api_url)

        if data and data.get("success") and data.get("data"):
            note = data["data"].get("note", data["data"])
            title = note.get("title", "") or ""
            desc = note.get("desc", "") or note.get("title", "") or ""
            author_info = note.get("user", {}) or {}
            author = author_info.get("nickname", "") or author_info.get("nick_name", "") or ""
            author_id = author_info.get("user_id", "") or str(author_info.get("id", ""))
            post_time = str(note.get("time", note.get("create_time", "")))
            cover = note.get("cover", note.get("image_list", [{}])[0].get("url", "")) if note.get("image_list") else ""

            # 图片
            items = _extract_image_items(note)
            # 视频
            video = _extract_video_item(note)
            if video:
                items.append(video)
            # 封面的图片
            if cover and not cover.startswith("http"):
                cover = ""

            return MediaInfo(
                platform=Platform.XIAOHONGSHU,
                url=url,
                title=title or "小红书",
                author=author,
                author_id=author_id,
                post_time=post_time,
                thumbnail=cover or "",
                description=desc or title or "小红书笔记",
                media_items=items,
            )

        # API 失败：尝试网页抓取
        html_url = f"https://www.xiaohongshu.com/explore/{note_id}"
        html = client.get_html(html_url)
        if html:
            items, title, thumb = self._parse_from_html(html)
            if items:
                return MediaInfo(
                    platform=Platform.XIAOHONGSHU,
                    url=url,
                    title=title or "小红书",
                    author="",
                    thumbnail=thumb or "",
                    description=title or "小红书笔记",
                    media_items=items,
                )

        return MediaInfo(
            platform=Platform.XIAOHONGSHU,
            url=url,
            title="小红书（解析失败）",
            author="",
            description=f"无法解析小红书笔记（note_id: {note_id}）。可能需要 Cookie 或笔记已删除。",
        )

    def _parse_from_html(self, html: str) -> tuple[list[MediaItem], str, str]:
        """从 HTML 页面提取媒体。"""
        items: list[MediaItem] = []
        title = ""
        thumbnail = ""
        seen: set[str] = set()

        # ext: og:title
        m = re.search(r"""<meta\s+property=["']og:title["']\s+content=["']([^"']+)["']""", html)
        if m:
            title = _html.unescape(m.group(1)).strip()[:80]

        # og:image
        m = re.search(r"""<meta\s+property=["']og:image["']\s+content=["']([^"']+)["']""", html)
        if m:
            thumbnail = m.group(1)

        # window.__INITIAL_STATE__ JSON
        m = re.search(r"window\.__INITIAL_STATE__\s*=\s*({.*?});", html, re.DOTALL)
        if m:
            try:
                state = json.loads(m.group(1))
                note = state.get("note", {}) or {}
                items = _extract_image_items(note)
                video = _extract_video_item(note)
                if video:
                    items.append(video)
                if not title:
                    title = note.get("title", "") or note.get("desc", "")[:80] or ""
                if not thumbnail and items:
                    thumbnail = items[0].url
                return items, title, thumbnail
            except (json.JSONDecodeError, AttributeError):
                pass

        # 图片 URL 提取
        for idx, m in enumerate(re.finditer(r'(https?://[^"\'\s]*(?:xhscdn|xiaohongshu)[^"\'\s]*(?:jpg|jpeg|png|webp))',
                                            html, re.IGNORECASE)):
            url = m.group(1)
            url = re.sub(r"[?!].*$", "", url)
            if url not in seen:
                seen.add(url)
                items.append(MediaItem(url=url, is_video=False, index=len(items)))

        return items, title, thumbnail

    def get_request_headers(self) -> dict[str, str]:
        return platform_headers(Platform.XIAOHONGSHU)

    def enumerate_profile_posts(
        self,
        identifier: str,
        limit: int = 20,
        callback=None,
        cancel_event=None,
    ) -> list[dict]:
        """枚举小红书用户主页笔记。

        通过抓取 HTML 提取 window.__INITIAL_STATE__ 中的笔记列表。
        受反爬限制可能返回空列表。

        Args:
            identifier: 用户 ID（十六进制字符串）
            limit: 最大枚举数量
            callback: 进度回调 callback(current, total)
            cancel_event: 取消事件

        Returns:
            list[dict]，每项含 {title, url, thumbnail}
        """
        user_id = identifier.strip()
        if not user_id or not re.match(r"^[a-f0-9]+$", user_id):
            logger.warning("Xiaohongshu enumerate_profile_posts: invalid user_id: %s", identifier)
            return []

        client = NetworkClient(Platform.XIAOHONGSHU)
        profile_url = f"https://www.xiaohongshu.com/user/profile/{user_id}"
        html = client.get_html(profile_url)

        if not html:
            logger.warning("Xiaohongshu enumerate_profile_posts: failed to fetch HTML for %s", user_id)
            return []

        # Extract window.__INITIAL_STATE__
        m = re.search(r"window\.__INITIAL_STATE__\s*=\s*({.*?});", html, re.DOTALL)
        if not m:
            logger.warning("Xiaohongshu enumerate_profile_posts: no __INITIAL_STATE__ found for %s", user_id)
            return []

        try:
            state = json.loads(m.group(1))
        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning("Xiaohongshu enumerate_profile_posts: failed to parse __INITIAL_STATE__: %s", e)
            return []

        # Try to find note list in various state paths
        notes = []
        # Path 1: user -> notes -> note_id dict
        user_data = state.get("user", {}) or state.get("profile", {}) or {}
        user_notes = user_data.get("notes", user_data.get("note", {}))
        if isinstance(user_notes, dict):
            notes = list(user_notes.values())
        elif isinstance(user_notes, list):
            notes = user_notes

        # Path 2: feed / noteFeed
        if not notes:
            for key in ("feed", "noteFeed", "userFeed", "noteList"):
                feed = state.get(key, []) or state.get(key, {})
                if isinstance(feed, dict):
                    notes = list(feed.values())
                elif isinstance(feed, list):
                    notes = feed
                if notes:
                    break

        if not notes:
            logger.warning("Xiaohongshu enumerate_profile_posts: no notes data found in state for %s", user_id)
            return []

        result: list[dict] = []
        for idx, note in enumerate(notes):
            if cancel_event and cancel_event.is_set():
                break
            if len(result) >= limit:
                break

            if isinstance(note, dict):
                title = note.get("title", "") or note.get("desc", "") or "小红书"
                note_id = note.get("note_id", "") or note.get("id", "")
                if not note_id:
                    continue

                # thumbnail from cover
                cover = note.get("cover", {}) or {}
                thumbnail = (
                    cover.get("url", "")
                    or cover.get("url_default", "")
                    or (cover.get("info_list", [{}])[0].get("url", "") if cover.get("info_list") else "")
                )
                if not thumbnail:
                    # maybe it's a string directly
                    thumbnail = note.get("cover", "") if isinstance(note.get("cover"), str) else ""

                result.append({
                    "title": title[:80],
                    "url": f"https://www.xiaohongshu.com/explore/{note_id}",
                    "thumbnail": thumbnail,
                })

            if callback:
                callback(len(result), limit)

        logger.info(
            "Xiaohongshu enumerate_profile_posts: user_id=%s, found %d notes",
            user_id, len(result),
        )
        return result

    def classify_error(self, error: Exception | str) -> str:
        text = str(error).lower()
        if any(kw in text for kw in ("cookie", "login", "session", "auth", "unauthenticated")):
            return ErrorCategory.COOKIE_EXPIRED.value
        return _ce(error).value
