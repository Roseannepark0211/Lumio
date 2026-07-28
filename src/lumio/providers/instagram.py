"""Lumio V4 — Instagram Provider。

复现 saveinta.com 服务端机制：
- 用户导入自己的 IG Cookie（设置页 Netscape 格式）
- 调 i.instagram.com 移动端 API（与 saveinta.com 服务端相同接口）
- 直接拿 IG CDN 直链，不需要 JWT/代理服务
- 视频取 video_versions 中 width 最大的档位
- 图片取 image_versions2.candidates 中 width 最大的档位

URL 格式：
- instagram.com/p/{shortcode}/    — 单图/视频帖
- instagram.com/reel/{shortcode}/ — Reel
- instagram.com/tv/{shortcode}/   — IGTV

模式切换（config.instagram_mode）：
- "cookie"（默认）：用户 cookie 调移动 API（本文件实现）
- "api"：Apify Actor 代理（apify_client.py，已弃用）
"""

from __future__ import annotations

import logging
from typing import Optional

from .base import BaseProvider, MediaInfo, MediaItem, MediaType, Platform
from .registry import register
from ..utils.error_types import ErrorCategory, classify_error as _ce
from ..utils.ua import CHROME_120_UA  # M5: 跨平台 UA

logger = logging.getLogger(__name__)


def _ig_shortcode_from_url(url: str) -> str:
    """从 URL 提取 Instagram shortcode。"""
    parts = url.rstrip("/").split("/")
    shortcode = parts[-1]
    for i, p in enumerate(parts):
        if p in ("reel", "p", "tv") and i + 1 < len(parts):
            shortcode = parts[i + 1]
            break
    return shortcode


def _ig_shortcode_to_media_id(shortcode: str) -> str:
    """将 Instagram shortcode 转换为数字 media_id。"""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    media_id = 0
    for ch in shortcode:
        media_id = media_id * 64 + alphabet.index(ch)
    return str(media_id)


def _ig_best_video_url(video_versions: list[dict]) -> str:
    """从 video_versions 中取最高分辨率视频 URL。"""
    if not video_versions:
        return ""
    best = max(video_versions, key=lambda v: v.get("width", 0))
    return best.get("url", "")


def _ig_best_image_url(candidates: list[dict]) -> str:
    """从 image_versions2.candidates 中取最高分辨率图片 URL。"""
    if not candidates:
        return ""
    best = max(candidates, key=lambda c: c.get("width", 0))
    return best.get("url", "")


def _ig_best_video_item(video_versions: list[dict]) -> Optional[MediaItem]:
    """取最高分辨率视频档位，返回 MediaItem（含 width/height）。"""
    if not video_versions:
        return None
    best = max(video_versions, key=lambda v: v.get("width", 0))
    return MediaItem(
        url=best.get("url", ""),
        is_video=True,
        extension="mp4",
        media_type=MediaType.VIDEO,
        width=best.get("width", 0),
        height=best.get("height", 0),
    )


def _ig_best_image_item(candidates: list[dict]) -> Optional[MediaItem]:
    """取最高分辨率图片档位，返回 MediaItem（含 width/height）。"""
    if not candidates:
        return None
    best = max(candidates, key=lambda c: c.get("width", 0))
    return MediaItem(
        url=best.get("url", ""),
        is_video=False,
        extension="jpg",
        media_type=MediaType.IMAGE,
        width=best.get("width", 0),
        height=best.get("height", 0),
    )


def _ig_media_to_items(media: dict) -> list[MediaItem]:
    """从移动 API media dict 提取 MediaItem 列表（始终取最高画质）。"""
    items: list[MediaItem] = []
    carousel = media.get("carousel_media")
    if carousel:
        for i, cm in enumerate(carousel):
            item = _ig_best_video_item(cm.get("video_versions") or [])
            if item is None:
                item = _ig_best_image_item(
                    cm.get("image_versions2", {}).get("candidates", [])
                )
            if item is not None:
                item.index = i
                items.append(item)
    else:
        item = _ig_best_video_item(media.get("video_versions") or [])
        if item is None:
            item = _ig_best_image_item(
                media.get("image_versions2", {}).get("candidates", [])
            )
        if item is not None:
            item.index = 0
            items.append(item)
    return items


def _ig_api_session():
    """创建带 IG cookie 和标准 headers 的 requests.Session。"""
    import requests
    import http.cookiejar
    from pathlib import Path
    from ..utils.config import get_cookie_path

    session = requests.Session()
    session.trust_env = True  # 尊重系统代理
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
        "User-Agent": CHROME_120_UA,  # M5: 跨平台 Chrome 120（IG 需要 120 版本）
        "X-IG-App-ID": "936619743392459",
        "X-CSRFToken": csrf_token,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "*/*",
    })
    return session


def _ig_get_media_info(shortcode: str) -> dict:
    """通过移动端 API 获取帖子信息，返回 media dict。

    对 IncompleteRead / 连接中断等网络错误自动重试 3 次（指数退避 2s/4s/8s），
    每次重试新建 session 避免复用损坏的连接。
    """
    import time
    from requests.exceptions import RequestException

    media_id = _ig_shortcode_to_media_id(shortcode)
    url = f"https://i.instagram.com/api/v1/media/{media_id}/info/"

    last_err: Exception | None = None
    for attempt in range(3):
        # 每次重试用新 session，避免连接池中损坏的连接
        session = _ig_api_session()
        try:
            resp = session.get(url, timeout=20)
            if resp.status_code == 429:
                time.sleep(3)
                resp = session.get(url, timeout=20)
            resp.raise_for_status()
            return resp.json().get("items", [{}])[0]
        except RequestException as e:
            last_err = e
            # IncompleteRead / ChunkedEncodingError / ConnectionError 重试
            err_msg = str(e)
            retryable = any(k in err_msg for k in (
                "IncompleteRead", "ChunkedEncodingError",
                "Connection broken", "ConnectionReset",
                "ConnectionError", "Read timed out",
            ))
            if not retryable or attempt == 2:
                raise
            wait = 2 ** (attempt + 1)  # 2s, 4s
            logger.warning("IG API 第 %d 次失败，%ds 后重试: %s", attempt + 1, wait, e)
            time.sleep(wait)

    # 不会执行到这里，但作为兜底
    if last_err:
        raise last_err
    return {}


@register
class InstagramProvider(BaseProvider):
    """Instagram (IG) 内容解析 Provider。

    复现 saveinta.com 服务端机制：用用户 cookie 调移动 API，
    直接拿 IG CDN 直链，不依赖第三方服务/代理/JWT。
    """

    @property
    def platform(self) -> Platform:
        return Platform.INSTAGRAM

    def match(self, url: str) -> bool:
        return "instagram.com" in url or "instagr.am" in url

    def extract_info(self, url: str) -> MediaInfo:
        # 去 query/fragment
        clean_url = url.split("?")[0].split("#")[0]
        shortcode = _ig_shortcode_from_url(clean_url)
        if not shortcode:
            return MediaInfo(
                platform=Platform.INSTAGRAM,
                url=url,
                title="Instagram（链接识别失败）",
                author="",
                description="无法从链接提取 shortcode。",
            )

        try:
            media = _ig_get_media_info(shortcode)
        except Exception as e:
            logger.warning("Instagram API 失败 (%s): %s", shortcode, e)
            return MediaInfo(
                platform=Platform.INSTAGRAM,
                url=url,
                title="Instagram（解析失败）",
                author="",
                description=f"无法获取帖子信息：{e}",
            )

        items = _ig_media_to_items(media)

        # === 基本信息 ===
        caption_obj = media.get("caption", {})
        caption = caption_obj.get("text", "") if isinstance(caption_obj, dict) else ""
        title = caption[:80] or "Instagram post"
        author = media.get("user", {}).get("username", "")

        # 发布时间
        post_time = ""
        ts = media.get("taken_at", 0)
        if ts:
            from datetime import datetime, timezone
            try:
                post_time = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
            except (ValueError, OSError):
                post_time = ""

        # 封面
        thumb = ""
        candidates = media.get("image_versions2", {}).get("candidates", [])
        if candidates:
            thumb = candidates[0].get("url", "")
        if not thumb:
            thumb = media.get("display_url", "")

        return MediaInfo(
            platform=Platform.INSTAGRAM,
            url=url,
            title=title,
            author=author,
            post_time=post_time,
            thumbnail=thumb,
            duration=None,
            media_items=items,
        )
