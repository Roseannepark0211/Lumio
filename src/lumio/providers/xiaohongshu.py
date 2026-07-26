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

# 笔记正则（explore/ 和 discovery/item/ 两种路径都支持）
_NOTE_ID_RE = re.compile(r"xiaohongshu\.com/(?:explore/|discovery/item/)([a-f0-9]+)")
_PROFILE_ID_RE = re.compile(r"xiaohongshu\.com/user/profile/([a-f0-9]+)")
_SHORTLINK_RE = re.compile(r"xhslink\.(?:com|cn)/[a-zA-Z0-9]+")


def _extract_note_id(url: str) -> Optional[str]:
    """从 URL 提取笔记 ID。"""
    m = _NOTE_ID_RE.search(url)
    return m.group(1) if m else None


def _is_profile_url(url: str) -> bool:
    return bool(_PROFILE_ID_RE.search(url) or _SHORTLINK_RE.search(url))


def _pick_best_image_url(img: dict) -> str:
    """从单张图片字段中选出最佳原图 URL。

    新版 __INITIAL_STATE__ 字段是 camelCase：
    - urlDefault: 默认展示图（WB_DFT 场景，带 token，可直接下载）
    - url: 原图 URL（部分笔记为空）
    - urlPre: 预览图（WB_PRV，画质低）
    - infoList: 各场景 URL 列表
    """
    # 1) url 字段（最高优先级，原图）
    url = (img.get("url") or "").strip()
    if url and url.startswith("http"):
        return url
    # 2) urlDefault（WB_DFT 场景，可直接下载）
    url = (img.get("urlDefault") or "").strip()
    if url and url.startswith("http"):
        return url
    # 3) infoList 里找 WB_DFT 场景
    info_list = img.get("infoList") or img.get("info_list") or []
    for info in info_list:
        scene = info.get("imageScene") or info.get("image_scene") or ""
        if scene in ("WB_DFT", "CRD_DEFAULT") and info.get("url", "").startswith("http"):
            return info["url"]
    # 4) infoList 任意一条
    for info in info_list:
        if info.get("url", "").startswith("http"):
            return info["url"]
    # 5) urlPre 兜底
    url = (img.get("urlPre") or "").strip()
    if url and url.startswith("http"):
        return url
    return ""


def _pick_best_video(stream: dict) -> tuple[str, int]:
    """从 stream 字典中选出最高画质视频 URL + 高度。

    新版结构：stream.{h264,h265,av1}[].masterUrl / backupUrls
    h264 兼容性最好优先用，其次按 qualityType/weight 排序。

    Returns:
        (url, height) — height 为 0 表示未知
    """
    for codec in ("h264", "h265", "av1", "h266"):
        codec_list = stream.get(codec) or []
        if not codec_list:
            continue
        # 按 weight 降序（weight 越大画质越高）
        sorted_list = sorted(
            codec_list,
            key=lambda x: x.get("weight", 0) if isinstance(x, dict) else 0,
            reverse=True,
        )
        for v in sorted_list:
            if not isinstance(v, dict):
                continue
            master = (v.get("masterUrl") or "").strip()
            url = ""
            if master and master.startswith("http"):
                url = master
            else:
                # fallback: backupUrls
                for b in v.get("backupUrls") or []:
                    if isinstance(b, str) and b.startswith("http"):
                        url = b
                        break
            if url:
                height = int(v.get("height") or v.get("videoHeight") or 0)
                return url, height
    return "", 0


def _pick_best_video_url(stream: dict) -> str:
    """兼容旧调用：只返回 URL。"""
    return _pick_best_video(stream)[0]


def _extract_media_items_from_note(note: dict) -> list[MediaItem]:
    """从新版笔记数据（camelCase 字段）提取所有媒体项。

    处理：
    - 纯视频笔记：note.video.media.stream
    - 图片/实况图笔记：note.imageList（含 livePhoto 字段，实况图含 stream 视频流）

    返回顺序：视频在前，图片在后（用户偏好）。
    """
    videos: list[MediaItem] = []
    images: list[MediaItem] = []
    seen_urls: set[str] = set()

    # 1) 纯视频笔记：note.video.media.stream
    video = note.get("video") or {}
    media = video.get("media") or {}
    stream = media.get("stream") or {}
    main_video_url, main_video_h = _pick_best_video(stream)
    if main_video_url and main_video_url not in seen_urls:
        seen_urls.add(main_video_url)
        videos.append(MediaItem(
            url=main_video_url,
            is_video=True,
            index=len(videos),
            media_type=MediaType.VIDEO,
            height=main_video_h,
            quality=f"{main_video_h}P" if main_video_h else "",
            extension="mp4",
        ))

    # 2) imageList（图片 + 实况图视频流）
    #    兼容 camelCase (imageList) 和 snake_case (image_list) 两种字段名
    image_list = note.get("imageList") or note.get("image_list") or note.get("images") or []
    for img in image_list:
        if not isinstance(img, dict):
            continue
        # 实况图：livePhoto=true 时含 stream 视频流，先取视频
        is_livephoto = bool(img.get("livePhoto") or img.get("live_photo"))
        if is_livephoto:
            lp_stream = img.get("stream") or {}
            lp_url, lp_h = _pick_best_video(lp_stream)
            if lp_url and lp_url not in seen_urls:
                seen_urls.add(lp_url)
                videos.append(MediaItem(
                    url=lp_url,
                    is_video=True,
                    index=len(videos),
                    media_type=MediaType.VIDEO,
                    height=lp_h,
                    quality=f"{lp_h}P" if lp_h else "",
                    extension="mp4",
                ))
        # 图片原图
        img_url = _pick_best_image_url(img)
        if img_url and img_url not in seen_urls:
            seen_urls.add(img_url)
            images.append(MediaItem(url=img_url, is_video=False, index=len(images)))

    # 重新编号，视频在前
    result = videos + images
    for i, item in enumerate(result):
        item.index = i
    return result


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

        # 新版 PC 分享链接带 xsec_token + xsec_source 鉴权参数，
        # 抓取 HTML 时必须带上，否则被访客系统拦截返回登录页。
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        xsec_token = (qs.get("xsec_token", [""])[0] or "").strip()
        xsec_source = (qs.get("xsec_source", [""])[0] or "").strip()
        auth_query = {}
        if xsec_token:
            auth_query["xsec_token"] = xsec_token
        if xsec_source:
            auth_query["xsec_source"] = xsec_source

        # 统一用 explore/ 路径抓取 HTML（discovery/item/ 路径也能用，但 explore/ 更通用）
        html_path = f"/explore/{note_id}"
        html_parsed = parsed._replace(path=html_path)
        if auth_query:
            html_parsed = html_parsed._replace(query=urlencode(auth_query))
        else:
            html_parsed = html_parsed._replace(query="")
        html_url = urlunparse(html_parsed)

        client = NetworkClient(Platform.XIAOHONGSHU)
        html = client.get_html(
            html_url,
            headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
        )

        if html:
            info = self._parse_from_html(html, note_id, url)
            if info is not None:
                return info

        return MediaInfo(
            platform=Platform.XIAOHONGSHU,
            url=url,
            title="小红书（解析失败）",
            author="",
            description=f"无法解析小红书笔记（note_id: {note_id}）。可能需要 Cookie 或笔记已删除。",
        )

    def _parse_from_html(
        self, html: str, note_id: str, original_url: str
    ) -> Optional[MediaInfo]:
        """从 HTML 页面提取媒体信息。

        优先解析 window.__INITIAL_STATE__（camelCase 新版结构），
        数据路径: state.note.noteDetailMap[note_id].note
        失败时回退到 og:* meta + 正则。
        """
        # 1) 解析 window.__INITIAL_STATE__
        m = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.+?\})\s*</script>", html, re.DOTALL)
        if m:
            try:
                # __INITIAL_STATE__ 里有 undefined 字面量，替换成 null 才能解析
                raw = m.group(1).replace("undefined", "null")
                state = json.loads(raw)
                note_state = state.get("note", {}) or {}
                note_detail_map = note_state.get("noteDetailMap", {}) or {}

                # 查找 note 数据：优先 note_id key，否则取第一个
                note = None
                if note_id in note_detail_map:
                    note = note_detail_map[note_id].get("note", {})
                elif note_detail_map:
                    first_key = next(iter(note_detail_map))
                    note = note_detail_map[first_key].get("note", {})

                if note and isinstance(note, dict):
                    title = (note.get("title") or "").strip() or "小红书"
                    desc = (note.get("desc") or "").strip()
                    user = note.get("user", {}) or {}
                    author = (user.get("nickname") or "").strip()
                    author_id = (user.get("userId") or user.get("user_id") or "").strip()

                    # 时间戳：新版是毫秒级
                    post_time = ""
                    ts = note.get("time") or note.get("create_time") or 0
                    if ts:
                        try:
                            ts_int = int(ts)
                            # 毫秒级时间戳（>1e12）需要 /1000
                            if ts_int > 1e12:
                                ts_int = ts_int // 1000
                            import datetime as _dt
                            dt = _dt.datetime.fromtimestamp(ts_int, tz=_dt.timezone.utc)
                            post_time = dt.strftime("%Y%m%d_%H%M%S")
                        except (ValueError, OSError):
                            pass

                    # 媒体项（视频在前、图片在后，实况图含视频流）
                    items = _extract_media_items_from_note(note)

                    # 缩略图：取首张图片
                    thumbnail = ""
                    if items:
                        for it in items:
                            if not it.is_video and it.url.startswith("http"):
                                thumbnail = it.url
                                break
                        if not thumbnail:
                            thumbnail = items[0].url

                    return MediaInfo(
                        platform=Platform.XIAOHONGSHU,
                        url=original_url,
                        title=title,
                        author=author,
                        author_id=author_id,
                        post_time=post_time,
                        thumbnail=thumbnail,
                        description=desc or title or "小红书笔记",
                        media_items=items,
                    )
            except (json.JSONDecodeError, AttributeError, ValueError) as e:
                logger.warning("Xiaohongshu: failed to parse __INITIAL_STATE__: %s", e)

        # 2) 回退：og:* meta + 正则提取
        items: list[MediaItem] = []
        title = ""
        thumbnail = ""
        seen: set[str] = set()

        m = re.search(r"""<meta\s+property=["']og:title["']\s+content=["']([^"']+)["']""", html)
        if m:
            title = _html.unescape(m.group(1)).strip()[:80]
        m = re.search(r"""<meta\s+property=["']og:image["']\s+content=["']([^"']+)["']""", html)
        if m:
            thumbnail = m.group(1)

        for m in re.finditer(
            r'(https?://[^"\'\s]*(?:xhscdn|xiaohongshu)[^"\'\s]*(?:jpg|jpeg|png|webp))',
            html, re.IGNORECASE,
        ):
            url = re.sub(r"[?!].*$", "", m.group(1))
            if url not in seen:
                seen.add(url)
                items.append(MediaItem(url=url, is_video=False, index=len(items)))

        if not items:
            return None
        return MediaInfo(
            platform=Platform.XIAOHONGSHU,
            url=original_url,
            title=title or "小红书",
            author="",
            thumbnail=thumbnail,
            description=title or "小红书笔记",
            media_items=items,
        )

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
