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
from typing import Optional, Union
import html as _html

from .base import BaseProvider, FormatOption, MediaInfo, MediaItem, Platform
from .registry import register
import logging

import requests as _requests

logger = logging.getLogger(__name__)

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

    返回 dict（API JSON）或 None（HTTP/JSON/网络错误，或返回了 HTML 页面）。
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
            "X-Requested-With": "XMLHttpRequest",
            **({"Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())} if cookies else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            # 检查 Content-Type：如果返回了 HTML（访客系统/反爬），不是 JSON
            ct = resp.headers.get('Content-Type', '')
            if 'text/html' in ct or 'text/plain' in ct:
                text = raw.decode('utf-8', errors='replace')
                if '<html' in text[:200] or 'Sina Visitor' in text[:500] or 'passport' in text[:500]:
                    logger.warning('weibo API returned HTML (Sina Visitor System), need cookies for %s', api_url[:50])
                    return None
            return json.loads(raw.decode('utf-8', errors='replace'))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError):
        return None


def _fetch_html(url: str, timeout: int = 15) -> Optional[str]:
    """Fetch HTML page, trying requests.Session first, then urllib fallback."""
    # 1) Try requests.Session with MozillaCookieJar first
    result = _fetch_with_session(url, as_json=False, timeout=timeout)
    if result is not None:
        return result

    # 2) Fallback: urllib with manual Cookie header
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
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            **({"Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())} if cookies else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            if 'Sina Visitor' in text[:500] or 'passport' in text[:300]:
                logger.warning('weibo page returned Sina Visitor System for %s', url[:50])
                return None
            return text
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

# ---- Unified media extraction (v4.1) ----

def _extract_all_media(data: dict) -> list[MediaItem]:
    """Extract all media items from Weibo post data.

    Handles:
    - mix_media_info (carousel/album posts with mixed video+images)
    - page_info (single video/video+image)
    - pics (standalone images)

    Returns videos first, then images (user preference).
    """
    videos: list[MediaItem] = []
    images: list[MediaItem] = []
    seen_urls: set[str] = set()

    # 1. mix_media_info (carousel/album posts)
    mix = data.get("mix_media_info", {}) or {}
    for item in mix.get("items", []):
        item_type = item.get("type", "")
        item_data = item.get("data", {}) or {}
        if item_type == "video":
            mi = item_data.get("media_info", {}) or {}
            url = (
                mi.get("stream_url")
                or mi.get("mp4_hd_url")
                or mi.get("mp4_url")
                or ""
            ).replace("\\", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                videos.append(MediaItem(url=url, is_video=True, index=len(videos)))
        elif item_type == "pic":
            # Check for live photo (embedded video data)
            lp_mi = (item_data.get("media_info") or {})
            lp_vid = lp_mi.get("stream_url") or lp_mi.get("mp4_hd_url") or lp_mi.get("mp4_url") or ""
            lp_vid = lp_vid.replace("\\", "")
            if lp_vid and lp_vid not in seen_urls:
                seen_urls.add(lp_vid)
                videos.append(MediaItem(url=lp_vid, is_video=True, index=len(videos)))
            pic_url = (
                (item_data.get("large") or {}).get("url", "")
                or item_data.get("url", "")
            )
            if pic_url and pic_url not in seen_urls:
                seen_urls.add(pic_url)
                images.append(MediaItem(url=pic_url, is_video=False, index=len(images)))

    # 2. page_info (single video or live photo)
    page_info = data.get("page_info", {}) or {}
    if page_info and page_info.get("type") in ("video", "livephoto"):
        mi = page_info.get("media_info", {}) or {}
        url = (
            mi.get("stream_url")
            or mi.get("mp4_hd_url")
            or mi.get("mp4_url")
            or ""
        ).replace("\\", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            videos.append(MediaItem(url=url, is_video=True, index=len(videos)))

    # 3. live_photo / live_photos (live photos with embedded video)
    #    API returns live_photo (singular) as a list of play-page URL strings.
    #    Some API responses use live_photos (plural) as a list of dicts.
    #    Accept both and handle each format.
    #
    #    重要：livephoto.us.sinaimg.cn 裸直链需要签名（?Expires&ssig&KID），
    #    直接请求一律 403。必须保留 video.weibo.com/media/play?livephoto=...
    #    播放页 URL，下载时服务器会 302 跳转到带签名的临时直链。
    #    （类似 HelloTik 报告第十四章：302 + Signed URL 机制）
    live_photos_raw = data.get("live_photo") or data.get("live_photos", []) or []
    for lp_item in live_photos_raw:
        lp_video = ""
        lp_image = ""
        if isinstance(lp_item, dict):
            mi = (lp_item.get("media_info") or {})
            lp_video = mi.get("stream_url") or mi.get("mp4_hd_url") or mi.get("mp4_url") or ""
            lp_video = lp_video.replace("\\", "")
            lp_image = lp_item.get("pic", {}).get("large", {}).get("url", "") or lp_item.get("pic", "").get("url", "") or lp_item.get("url", "")
        elif isinstance(lp_item, str):
            # 保留完整的 video.weibo.com 播放页 URL（含 livephoto= 参数）
            # 不要解码成裸 livephoto.us.sinaimg.cn 直链（会 403）
            if "video.weibo.com/media/play" in lp_item and "livephoto=" in lp_item:
                lp_video = lp_item.replace("\\", "")
        if lp_video and lp_video not in seen_urls:
            seen_urls.add(lp_video)
            videos.append(MediaItem(url=lp_video, is_video=True, index=len(videos)))
        if lp_image and lp_image not in seen_urls:
            seen_urls.add(lp_image)
            images.append(MediaItem(url=lp_image, is_video=False, index=len(images)))

    # 4. pics (standalone images)
    pics = data.get("pics", [])
    for pic in pics:
        url = pic.get("large", {}).get("url", "") or pic.get("url", "")
        if not url:
            pid = pic.get("pid", "")
            if pid:
                url = f"https://wx1.sinaimg.cn/large/{pid}.jpg"
        if url and url not in seen_urls:
            seen_urls.add(url)
            images.append(MediaItem(url=url, is_video=False, index=len(images)))
    
    result = videos + images
    # 安全网：任何裸 livephoto.us.sinaimg.cn 直链需要签名才能访问（裸直链一律 403），
    # 转换成 video.weibo.com 播放页 URL，下载时服务器会 302 跳转到带签名的临时直链。
    # 覆盖所有可能产生裸直链的分支（dict 形式 live_photos、page_info 等）。
    from urllib.parse import quote
    for item in result:
        if item.is_video and "livephoto.us.sinaimg.cn" in item.url and "video.weibo.com" not in item.url:
            item.url = f"https://video.weibo.com/media/play?livephoto={quote(item.url, safe='')}"
    for i, item in enumerate(result):
        item.index = i
    return result




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
    """从 page_info 提取视频 MediaItem，含 Live Photo 支持。"""
    if page_info.get("type") not in ("video", "livephoto"):
        return None
    media_info = page_info.get("media_info", {})
    url = (
        media_info.get("mp4_hd_url")
        or media_info.get("mp4_url")
        or media_info.get("stream_url")
        or media_info.get("livephoto_mp4")
        or ""
    )
    if not url:
        return None
    url = url.replace("\\", "")
    is_live = page_info.get("type") == "livephoto"
    kwargs = dict(url=url, is_video=True, index=index)
    if is_live:
        lp_image = (
            page_info.get("page_pic", {}).get("url", "")
            or media_info.get("livephoto_static_url", "")
            or ""
        )
        kwargs["media_type"] = "live_photo"
        kwargs["live_photo"] = {
            "image": lp_image,
            "video": url,
            "cover": page_info.get("page_pic", {}).get("url", ""),
        }
    return MediaItem(**kwargs)


def _format_weibo_time(raw: str) -> str:
    """将微博 API 的 created_at 格式化为 YYYYMMDD_HHMMSS。

    微博 API 返回格式如 "Sun Jun 07 21:40:10 +0800 2026"
    Library 日期过滤器用字符串比较，需要统一格式。
    """
    if not raw:
        return ""
    import datetime as _dt
    for fmt in (
        "%a %b %d %H:%M:%S %z %Y",       # "Sun Jun 07 21:40:10 +0800 2026"
        "%a %b %d %H:%M:%S %Y",            # 无时区变体
        "%Y-%m-%d %H:%M:%S",               # "2026-06-07 21:40:10"
        "%Y-%m-%dT%H:%M:%S",               # ISO 格式
        "%Y-%m-%dT%H:%M:%S%z",             # ISO + 时区
    ):
        try:
            dt = _dt.datetime.strptime(raw.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_dt.timezone.utc)
            return dt.strftime("%Y%m%d_%H%M%S")
        except ValueError:
            continue
    return raw  # 解析失败原样返回


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
        try:
            f = open(path, encoding='utf-8', errors='replace')
        except UnicodeDecodeError:
            f = open(path, encoding='latin-1')
        with f:
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


def _fetch_with_session(url: str, *, as_json: bool = False, timeout: int = 15) -> Optional[Union[dict, str]]:
    """Fetch using requests.Session + MozillaCookieJar for proper Netscape cookie file support."""
    try:
        from http.cookiejar import MozillaCookieJar as _MozillaCookieJar
        from ..utils.config import load_config
        cfg = load_config()
        cookie_file = cfg.get('weibo_cookie_file', '') or cfg.get('cookie_file', '')

        session = _requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://weibo.com/",
        })

        if cookie_file and Path(cookie_file).exists():
            try:
                jar = _MozillaCookieJar(str(cookie_file))
                jar.load(ignore_discard=True, ignore_expires=True)
                session.cookies = jar

                # MozillaCookieJar filters by domain: cookies bound to weibo.com
                # won't be sent to m.weibo.cn.  Manually inject Weibo cookies to
                # ensure they reach the API servers regardless of domain mismatch.
                _weibo_cookies = _get_weibo_cookies()
                if _weibo_cookies:
                    from http.cookiejar import Cookie as _Cookie
                    for name, value in _weibo_cookies.items():
                        c = _Cookie(
                            version=0, name=name, value=value,
                            port=None, port_specified=False,
                            domain='', domain_specified=False, domain_initial_dot=False,
                            path='/', path_specified=True,
                            secure=False, expires=None, discard=True,
                            comment=None, comment_url=None, rest={},
                            rfc2109=False,
                        )
                        session.cookies.set_cookie(c)
            except Exception:
                pass

        if as_json:
            session.headers.update({
                "Accept": "application/json, text/plain, */*",
                "X-Requested-With": "XMLHttpRequest",
            })
        else:
            session.headers.update({
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            })

        resp = session.get(url, timeout=timeout)

        if as_json:
            ct = resp.headers.get('Content-Type', '')
            if 'text/html' in ct or 'text/plain' in ct:
                text = resp.text[:500]
                if '<html' in text or 'Sina Visitor' in text or 'passport' in text:
                    logger.warning('weibo API returned HTML (Sina Visitor System) via session, need cookies for %s', url[:50])
                    return None
            try:
                data = resp.json()
                if data.get("ok") == -100:
                    logger.warning('weibo API returned ok=-100 (login required) via session for %s', url[:50])
                    return None
                return data
            except ValueError:
                return None
        else:
            text = resp.text
            if 'Sina Visitor' in text[:500] or 'passport' in text[:300]:
                logger.warning('weibo page returned Sina Visitor System via session, need cookies for %s', url[:50])
                return None
            return text
    except Exception as e:
        logger.debug('Session fetch failed for %s: %s', url[:50], e)
        return None



def _extract_video_fullinfo(media_info: dict) -> list[FormatOption]:
    formats = []
    seen = set()
    for label, key, w, h in [
        ("1080p", "video_1080p_url", 1920, 1080),
        ("720p", "stream_url_hd", 1280, 720),
        ("540p", "stream_url", 960, 540),
        ("HD", "mp4_hd_url", 1280, 720),
        ("SD", "mp4_url", 640, 360),
    ]:
        url = media_info.get(key, "")
        if url and url not in seen:
            seen.add(url)
            formats.append(FormatOption(
                format_id=key, label=label + (" (mp4)" if label in ("HD","SD") else ""),
                type="video", ext="mp4", width=w, height=h,
            ))
    return formats

def _classify_weibo_type(data: dict) -> str:
    if "mix_media_info" in data or data.get("live_photo") or data.get("live_photos"):
        return "livephoto"
    pi = data.get("page_info", {})
    has_video = pi.get("type") in ("video", "livephoto") and bool(
        pi.get("media_info", {}).get("stream_url") or pi.get("media_info", {}).get("mp4_url"))
    has_pics = bool(data.get("pics"))
    if has_video and has_pics: return "mixed"
    if has_video: return "video"
    if has_pics: return "images"
    return "unknown"

def _build_image_from_pic_ids(pic_ids: list[str]) -> list:
    hosts = ["wx1","wx2","wx3","wx4"]
    items = []
    for idx, pid in enumerate(pic_ids):
        url = f"https://{hosts[idx % 4]}.sinaimg.cn/large/{pid}.jpg"
        items.append(MediaItem(url=url, is_video=False, index=idx))
    return items

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
                        formats=[],
                    )
            # Fallback 2: try weibo.com API (ajax endpoint)
            try:
                wb_url = f"https://weibo.com/ajax/statuses/show?id={post_id}"
                wb_raw = _fetch_json(wb_url)
                if wb_raw and wb_raw.get("ok") == 1:
                    d = wb_raw.get("data", {}) or wb_raw
                    wb_items = _extract_all_media(d)
                    text_raw = d.get("text_raw", "") or d.get("text", "") or ""
                    wb_title = _clean_title(text_raw)
                    user = d.get("user", {}) or {}
                    wb_author = user.get("screen_name", "") or ""
                    wb_thumb = _get_thumbnail(d)
                    wb_time = _format_weibo_time(d.get("created_at", ""))
                    return MediaInfo(
                        platform=Platform.WEIBO,
                        url=url,
                        title=wb_title,
                        author=wb_author,
                        author_id=str(user.get("id", "")),
                        post_time=wb_time,
                        description=wb_title,
                        media_items=wb_items,
                        thumbnail=wb_thumb,
                        formats=[],
                    )
            except Exception:
                pass
            # All fallbacks failed
            _no_cookies = not bool(_get_weibo_cookies())
            _cookie_hint = (
                "需要微博 Cookie，请在 设置 → 平台凭证 → 微博 中导入包含 SUB 和 SUBP 的 Netscape Cookie 文件"
                if _no_cookies else
                "微博 Cookie 可能已过期或缺少必要字段（SUB/SUBP），请重新导出 Cookie"
            )
            return MediaInfo(
                platform=Platform.WEIBO,
                url=url,
                title="微博（解析失败）",
                author="",
                description=f"无法解析微博内容（post_id: {post_id}）。{_cookie_hint}",
            )

        d = raw.get("data", {}) or {}

        # 标题&描述
        text_raw = d.get("text_raw", "") or d.get("text", "") or ""
        title = _clean_title(text_raw)

        # 作者
        user = d.get("user", {}) or {}
        author = user.get("screen_name", "") or ""
        author_id = str(user.get("id", ""))

        # 时间 — 格式化为 YYYYMMDD_HHMMSS（Library 日期过滤器依赖此格式）
        created_at = _format_weibo_time(d.get("created_at", ""))

        # ??
        items: list[MediaItem] = _extract_all_media(d)
        formats = []
        mi = (d.get("page_info", {}) or {}).get("media_info", {})
        if mi:
            formats = _extract_video_fullinfo(mi)

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

        thumbnail = _get_thumbnail(d) or (items[0].url if items else "")

        mt = _classify_weibo_type(d)
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
            formats=formats,
            raw_data={**d, "_media_type": mt},
        )
    def get_request_headers(self) -> dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Referer": "https://weibo.com/",
        }

    def classify_error(self, error: Exception | str) -> str:
        text = str(error).lower()
        if any(kw in text for kw in ("sub","subp","weibo cookie","sina visitor","need login","login required","passport","not authorized")):
            from ..utils.error_types import ErrorCategory
            return ErrorCategory.COOKIE_EXPIRED.value
        from ..utils.error_types import classify_error as _ce
        return _ce(error).value

    def enumerate_profile_posts(
        self,
        identifier: str,
        limit: int = 20,
        callback=None,
        cancel_event=None,
    ) -> list[dict]:
        """枚举微博用户主页帖文。

        两阶段 API：
        1. m.weibo.cn/api/container/getIndex?type=uid&value={uid} → containerid
        2. 分页取 cards[].mblog

        Args:
            identifier: 用户 uid（纯数字）
            limit: 最大枚举数量
            callback: 进度回调 callback(current, total)
            cancel_event: 取消事件

        Returns:
            list[dict]，每项含 {title, url, thumbnail}
        """
        uid = identifier.strip()
        if not uid.isdigit():
            logger.warning("Weibo enumerate_profile_posts: identifier is not a numeric UID: %s", identifier)
            return []

        result: list[dict] = []
        page = 1
        containerid = ""

        # Phase 1: get containerid
        container_api = (
            f"https://m.weibo.cn/api/container/getIndex"
            f"?type=uid&value={uid}"
        )
        data = _fetch_json(container_api)
        if not data or data.get("ok") != 1:
            logger.warning("Weibo enumerate_profile_posts: failed to get containerid for uid=%s", uid)
            return []

        tabs = data.get("data", {}).get("tabs", [])
        for tab in tabs:
            if tab.get("tab_type") == "weibo":
                containerid = tab.get("containerid", "")
                break
        if not containerid:
            containerid = data.get("data", {}).get("cardlistInfo", {}).get("containerid", "")
        if not containerid:
            logger.warning("Weibo enumerate_profile_posts: no containerid found for uid=%s", uid)
            return []

        # Phase 2: paginate
        while len(result) < limit:
            if cancel_event and cancel_event.is_set():
                break

            api = (
                f"https://m.weibo.cn/api/container/getIndex"
                f"?type=uid&value={uid}"
                f"&containerid={containerid}"
                f"&page={page}"
            )
            page_data = _fetch_json(api)
            if not page_data or page_data.get("ok") != 1:
                break

            cards = page_data.get("data", {}).get("cards", [])
            if not cards:
                break

            for card in cards:
                if cancel_event and cancel_event.is_set():
                    break

                mblog = card.get("mblog")
                if not mblog:
                    continue

                # title: text_raw stripped of HTML
                text_raw = mblog.get("text_raw", "") or mblog.get("text", "") or ""
                title = re.sub(r"<[^>]+>", "", text_raw).strip()[:80]
                if not title:
                    title = "微博"

                # thumbnail: first pic large url
                pics = mblog.get("pics", [])
                thumbnail = ""
                if pics:
                    thumbnail = pics[0].get("large", {}).get("url", "") or pics[0].get("url", "")
                    if not thumbnail:
                        pid = pics[0].get("pid", "")
                        if pid:
                            thumbnail = f"https://wx1.sinaimg.cn/large/{pid}.jpg"

                post_id = mblog.get("id", "")
                if not post_id:
                    continue
                url = f"https://m.weibo.cn/status/{post_id}"

                result.append({
                    "title": title,
                    "url": url,
                    "thumbnail": thumbnail,
                })

                if len(result) >= limit:
                    break

            if callback:
                callback(len(result), limit)

            page += 1

        logger.info("Weibo enumerate_profile_posts: uid=%s, found %d posts", uid, len(result))
        return result
