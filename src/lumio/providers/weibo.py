# Lumio V4 Phase 2 — WeiboProvider
#
# 通过 m.weibo.cn 公开 API 解析微博内容：
# - 图片 / 多图 / 视频 / 图文混合
# - 转发微博内容
# - API 失败时优雅降级返回基本信息

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional
import html as _html

from .base import BaseProvider, MediaInfo, MediaItem, Platform
from .registry import register

_WEIBO_API = "https://m.weibo.cn/statuses/show?id={}"

# 微博 URL 中的 post_id 模式（字母数字组合）
_POST_ID_RE = re.compile(r"(?:weibo\.com/\d+|m\.weibo\.cn/status)/([a-zA-Z0-9]+)")


def _extract_post_id(url: str) -> Optional[str]:
    """从微博 URL 中提取 post_id。"""
    m = _POST_ID_RE.search(url)
    return m.group(1) if m else None


def _fetch_json(api_url: str, timeout: int = 15) -> Optional[dict]:
    """调用 HTTP API 并解析 JSON。
    
    如已有微博 cookie，会自动附加 Cookie 头以绕过访客系统拦截。
    """
    cookies = _get_weibo_cookies()
    req = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://m.weibo.cn/",
            "Accept": "application/json, text/plain, */*",
            **({"Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())} if cookies else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError):
        return None


def _fetch_html(url: str, timeout: int = 15) -> Optional[str]:
    """Fetch an HTML page, with optional cookie support."""
    cookies = _get_weibo_cookies()
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            **({"Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())} if cookies else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return None


def _extract_items_from_html(html: str, post_id: str) -> tuple[list[MediaItem], str, str]:
    """Parse Weibo page HTML to extract media items, title, and thumbnail."""
    items: list[MediaItem] = []
    title = ""
    thumbnail = ""
    seen_urls: set[str] = set()

    # 1. og:title
    m = re.search(r'''<meta\s+property=["']og:title["']\s+content=["']([^"']+)["']''', html)
    if m:
        title = _html.unescape(m.group(1)).strip()[:80]

    # 2. og:image (thumbnail)
    m = re.search(r'''<meta\s+property=["']og:image["']\s+content=["']([^"']+)["']''', html)
    if m:
        thumbnail = m.group(1)

    # 3. og:video
    m = re.search(r'''<meta\s+property=["']og:video["']\s+content=["']([^"']+)["']''', html)
    if m:
        url = m.group(1)
        seen_urls.add(url)
        items.append(MediaItem(url=url, is_video=True, index=len(items)))

    # 4. sinaimg.cn in img tags
    for idx, m in enumerate(re.finditer(r'''<img[^>]+src=["'](https?://[^"']*sinaimg[^"']*)["']''', html)):
        url = m.group(1)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        items.append(MediaItem(url=url, is_video=False, index=len(items)))

    # 5. sinaimg.cn in any attribute (WB_IMG_U / data-src / etc)
    for m in re.finditer(r'(https?://[^"' + chr(39) + r'\s]*sinaimg[^"' + chr(39) + r'\s]*(?:jpg|jpeg|png|gif|webp))', html):
        url = m.group(1)
        if url in seen_urls:
            continue
        # Prefer large/original size
        url = re.sub(r'/(thumb|small|orj\d+|mw\d+)/', '/large/', url)
        seen_urls.add(url)
        items.append(MediaItem(url=url, is_video=False, index=len(items)))

    # 6. Video URLs (mp4/m3u8)
    for m in re.finditer(r'(https?://[^"' + chr(39) + r'\s]*video[^"' + chr(39) + r'\s]*(?:mp4|m3u8))', html, re.IGNORECASE):
        url = m.group(1)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        items.append(MediaItem(url=url, is_video=True, index=len(items)))

    # Deduplicate by url, keep first occurrence
    deduped: list[MediaItem] = []
    dedup_seen: set[str] = set()
    for it in items:
        if it.url not in dedup_seen:
            dedup_seen.add(it.url)
            deduped.append(it)

    return deduped, title, thumbnail


def _extract_images_from_pics(pics: list[dict]) -> list[MediaItem]:
    """从 pics 数组提取图片 MediaItem 列表。"""
    items: list[MediaItem] = []
    for idx, pic in enumerate(pics):
        # 优先 large 尺寸，否则根据 pid 构造
        url = pic.get("large", {}).get("url", "") or pic.get("url", "")
        if not url:
            pid = pic.get("pid", "")
            if pid:
                url = f"https://wx1.sinaimg.cn/large/{pid}.jpg"
            else:
                continue
        items.append(MediaItem(url=url, is_video=False, index=idx))
    return items


def _extract_video(page_info: dict, index: int = 0) -> Optional[MediaItem]:
    """从 page_info 提取视频 MediaItem。"""
    if page_info.get("type") != "video":
        return None
    media_info = page_info.get("media_info", {})
    url = (
        media_info.get("mp4_hd_url")
        or media_info.get("mp4_url")
        or media_info.get("stream_url")
        or ""
    )
    if not url:
        return None
    return MediaItem(url=url.replace("\\", ""), is_video=True, index=index)


def _clean_title(text: str) -> str:
    """清理标题文本。"""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()[:80] or "微博"


def _get_thumbnail(data: dict) -> str:
    """从 data 中提取缩略图 URL。"""
    page_info = data.get("page_info", {})
    thumb = page_info.get("page_pic", {}).get("url", "")
    if thumb:
        return thumb
    pics = data.get("pics", [])
    if pics:
        return pics[0].get("large", {}).get("url", "")
    return ""



def _get_weibo_cookies() -> dict[str, str]:
    """从 NetScape cookie 文件中读取微博 Cookie。

    解析 .weibo.cn / .weibo.com 域的 cookie 返回 {name: value} 字典。
    Cookie 文件路径从配置的 `cookie_file`（或独立的 `weibo_cookie_file`）读取。
    无 cookie 时静默返回空字典。

    Returns:
        dict: cookie 键值对，失败时返回空 dict
    """
    try:
        from ..utils.config import load_config
        cfg = load_config()
        cookie_file = cfg.get('weibo_cookie_file', '') or cfg.get('cookie_file', '')
        if not cookie_file:
            return {}
        path = Path(cookie_file)
        if not path.exists():
            return {}
        cookies: dict[str, str] = {}
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split('\t')
                if len(parts) >= 7:
                    domain = parts[0]
                    if 'weibo.cn' in domain or 'weibo.com' in domain:
                        name = parts[5]
                        value = parts[6]
                        cookies[name] = value
        return cookies
    except Exception:
        return {}

@register
class WeiboProvider(BaseProvider):
    """微博内容解析 Provider。

    通过 m.weibo.cn/statuses/show API 获取微博内容，
    提取图片、视频及元数据。
    API 失败时返回带基本信息（含错误描述）的 MediaInfo。
    """

    @property
    def platform(self) -> Platform:
        return Platform.WEIBO

    def match(self, url: str) -> bool:
        return _extract_post_id(url) is not None

    def extract_info(self, url: str) -> MediaInfo:
        post_id = _extract_post_id(url)
        if not post_id:
            raise ValueError(f"无法从 URL 提取微博 post_id: {url}")

        api_url = _WEIBO_API.format(post_id)
        raw = _fetch_json(api_url)

        # API 失败 -> 尝试 HTML 页面爬取做党底
        if raw is None or raw.get("ok") != 1:
            # Fallback 1: m.weibo.cn HTML page scraping
            m_url = f"https://m.weibo.cn/status/{post_id}"
            html = _fetch_html(m_url)
            if html:
                html_items, html_title, html_thumb = _extract_items_from_html(html, post_id)
                if html_items:
                    return MediaInfo(
                        platform=Platform.WEIBO,
                        url=url,
                        title=html_title or f"微博 {post_id[:8]}",
                        author="",
                        description=html_title or f"微博 {post_id[:8]}",
                        media_items=html_items,
                        thumbnail=html_thumb,
                    )
            # Fallback 2: try weibo.com API (ajax endpoint)
            try:
                wb_url = f"https://weibo.com/ajax/statuses/show?id={post_id}"
                wb_raw = _fetch_json(wb_url)
                if wb_raw and wb_raw.get("ok") == 1:
                    d = wb_raw.get("data", {}) or wb_raw
                    wb_items = []
                    pics = d.get("pics", [])
                    if pics:
                        wb_items.extend(_extract_images_from_pics(pics))
                    page_info = d.get("page_info", {})
                    if page_info:
                        video = _extract_video(page_info, len(wb_items))
                        if video:
                            wb_items.append(video)
                    text_raw = d.get("text_raw", "") or d.get("text", "") or ""
                    wb_title = _clean_title(text_raw)
                    user = d.get("user", {}) or {}
                    wb_author = user.get("screen_name", "") or ""
                    wb_thumb = _get_thumbnail(d)
                    return MediaInfo(
                        platform=Platform.WEIBO,
                        url=url,
                        title=wb_title,
                        author=wb_author,
                        description=wb_title,
                        media_items=wb_items,
                        thumbnail=wb_thumb,
                    )
            except Exception:
                pass
            # All fallbacks failed
            return MediaInfo(
                platform=Platform.WEIBO,
                url=url,
                title="微博（解析失败）",
                author="",
                description=f"无法解析微博内容，post_id: {post_id}，请检查网络或Cookie配置",
            )

        d = raw.get("data", {}) or {}

        # 标题&描述
        text_raw = d.get("text_raw", "") or d.get("text", "") or ""
        title = _clean_title(text_raw)

        # 作者
        user = d.get("user", {}) or {}
        author = user.get("screen_name", "") or ""
        author_id = str(user.get("id", ""))

        # 时间
        created_at = d.get("created_at", "")

        # 媒体
        items: list[MediaItem] = []

        pics = d.get("pics", [])
        if pics:
            items.extend(_extract_images_from_pics(pics))

        page_info = d.get("page_info", {})
        if page_info:
            video = _extract_video(page_info, len(items))
            if video:
                items.append(video)

        # 主条目无媒体时尝试转发内容
        if not items:
            retweeted = d.get("retweeted_status", {})
            if retweeted:
                r_pics = retweeted.get("pics", [])
                if r_pics:
                    items.extend(_extract_images_from_pics(r_pics))
                r_page = retweeted.get("page_info", {})
                if r_page:
                    rv = _extract_video(r_page, len(items))
                    if rv:
                        items.append(rv)
                # 转发微博的标题/作者作为兜底
                if not title:
                    r_text = retweeted.get("text_raw", "") or retweeted.get("text", "") or ""
                    title = _clean_title(r_text)
                if not author:
                    r_user = retweeted.get("user", {}) or {}
                    author = r_user.get("screen_name", "") or ""

        thumbnail = _get_thumbnail(d)

        return MediaInfo(
            platform=Platform.WEIBO,
            url=url,
            title=title or "微博",
            author=author,
            author_id=author_id,
            post_time=created_at,
            thumbnail=thumbnail,
            description=title,
            media_items=items,
            raw_data=d,
        )
