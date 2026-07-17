"""Lumio V4 — Bilibili (B站) Provider。

通过 Bilibili 开放 API 解析视频信息。
- BV / av 号支持
- b23.tv 短链接自动展开
- 视频基本信息 + 封面
"""

from __future__ import annotations

import json
import logging
import re
import html as _html
from typing import Optional

from .base import BaseProvider, MediaInfo, MediaItem, MediaType, FormatOption, Platform
from .network.client import NetworkClient
from .network.headers import platform_headers
from .registry import register
from ..utils.error_types import ErrorCategory, classify_error as _ce

logger = logging.getLogger(__name__)

_BV_ID_RE = re.compile(r"bilibili\.com/video/(BV[\w]+)")
_AV_ID_RE = re.compile(r"bilibili\.com/video/(av\d+)")
_B23_RE = re.compile(r"b23\.tv/[\w]+")
_PROFILE_BILIBILI_RE = re.compile(r"(?:bilibili\.com/space|space\.bilibili\.com)/(\d+)")
_PROFILE_ID_RE = re.compile(r"bilibili\.com/space/(\d+)")

# Bilibili API
_BV_TO_AID_API = "https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
_AID_API = "https://api.bilibili.com/x/web-interface/view?aid={aid}"
_VIDEO_INFO_API = "https://api.bilibili.com/x/web-interface/view?aid={aid}"
_PLAYER_INFO_API = "https://api.bilibili.com/x/player/playurl?avid={aid}&cid={cid}&qn=80&type=&otype=json"


def _extract_bv(url: str) -> Optional[str]:
    m = _BV_ID_RE.search(url)
    return m.group(1) if m else None


def _extract_av(url: str) -> Optional[str]:
    m = _AV_ID_RE.search(url)
    return m.group(1) if m else None


def _extract_aid(url: str) -> Optional[str]:
    """提取 aid 数值"""
    m = re.search(r"bilibili\.com/video/(av\d+)", url)
    if m:
        aid_str = m.group(1)
        return aid_str[2:]  # 去掉 "av" 前缀
    return None


def _resolve_b23(url: str) -> Optional[str]:
    """展开 b23.tv 短链接。"""
    import requests
    try:
        resp = requests.get(url, allow_redirects=True, timeout=10)
        return resp.url if resp.status_code == 200 else None
    except Exception:
        return None


@register
class BilibiliProvider(BaseProvider):
    """Bilibili (B站) 内容解析 Provider。"""

    @property
    def platform(self) -> Platform:
        return Platform.BILIBILI

    def match(self, url: str) -> bool:
        if bool(_BV_ID_RE.search(url) or _AV_ID_RE.search(url) or _B23_RE.search(url)):
            return True
        return bool(_PROFILE_BILIBILI_RE.search(url) or _PROFILE_ID_RE.search(url))

    def extract_info(self, url: str) -> MediaInfo:
        # 展开 b23.tv 短链接
        if _B23_RE.search(url):
            resolved = _resolve_b23(url)
            if resolved:
                url = resolved

        bv = _extract_bv(url)
        av = _extract_av(url)

        if not bv and not av:
            # 个人主页
            return MediaInfo(
                platform=Platform.BILIBILI,
                url=url,
                title="Bilibili（个人主页）",
                author="",
                description="Bilibili 个人主页批量下载暂未接入，请使用单条视频 URL。",
            )

        client = NetworkClient(Platform.BILIBILI)

        # 获取视频基本信息
        if bv:
            api_url = _BV_TO_AID_API.format(bvid=bv)
        else:
            api_url = _AID_API.format(aid=av[2:] if av.startswith("av") else av)

        data = client.get_json(api_url)
        if not data or data.get("code") != 0:
            return MediaInfo(
                platform=Platform.BILIBILI,
                url=url,
                title="Bilibili（解析失败）",
                author="",
                description=f"无法解析 Bilibili 视频（BV: {bv or av}）。视频可能不存在或已被删除。",
            )

        v_info = data.get("data", {})
        title = v_info.get("title", "") or ""
        desc = v_info.get("desc", "") or ""
        owner = v_info.get("owner", {}) or {}
        author = owner.get("name", "") or ""
        author_id = str(owner.get("mid", ""))
        pic = v_info.get("pic", "") or ""
        aid = str(v_info.get("aid", ""))
        cid = v_info.get("cid", 0)

        # 时间
        pubtime = v_info.get("pubdate", 0)
        import datetime
        post_time = ""
        if pubtime:
            post_time = datetime.datetime.fromtimestamp(pubtime, tz=datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")

        # 播放器信息 API（格式 + 视频流 URL）
        pf_data = None
        if aid and cid:
            pf_url = _PLAYER_INFO_API.format(aid=aid, cid=cid)
            pf_data = client.get_json(pf_url)

        # 视频格式
        formats: list[FormatOption] = []
        if pf_data and pf_data.get("code") == 0:
            pf_info = pf_data.get("data", {})
            accept_formats = pf_info.get("accept_description", [])
            accept_quality = pf_info.get("accept_quality", [])
            for i, q in enumerate(accept_quality):
                desc = accept_formats[i] if i < len(accept_formats) else f"品质{q}"
                formats.append(FormatOption(
                    format_id=str(q), label=desc, type="video", ext="mp4",
                ))

        # 构建 MediaItem
        items: list[MediaItem] = []
        if pic:
            # 封面作为图片项（可下载）
            items.append(MediaItem(url=pic, is_video=False, index=0))

        # 视频流 URL（取最高分辨率，复用 pf_data）
        if pf_data and pf_data.get("code") == 0:
            durl = pf_data.get("data", {}).get("durl", [])
            if durl:
                best = durl[0]
                video_url = best.get("url", "") or best.get("backup_url", [""])[0]
                if video_url:
                    items.append(MediaItem(url=video_url, is_video=True, index=len(items)))

        return MediaInfo(
            platform=Platform.BILIBILI,
            url=url,
            title=title or "Bilibili 视频",
            author=author,
            author_id=author_id,
            post_time=post_time,
            thumbnail=pic or "",
            description=desc or title or "Bilibili 视频",
            media_items=items,
            formats=formats,
        )

    def get_request_headers(self) -> dict[str, str]:
        return platform_headers(Platform.BILIBILI)

    def enumerate_profile_posts(
        self,
        identifier: str,
        limit: int = 20,
        callback=None,
        cancel_event=None,
    ) -> list[dict]:
        """枚举 Bilibili 用户空间视频列表。

        API: api.bilibili.com/x/space/arc/search?mid={mid}&ps={limit}&pn={page}

        Args:
            identifier: 用户 mid（数字 UID）
            limit: 最大枚举数量
            callback: 进度回调 callback(current, total)
            cancel_event: 取消事件

        Returns:
            list[dict]，每项含 {title, url, thumbnail}
        """
        mid = identifier.strip()
        if not mid.isdigit():
            logger.warning("Bilibili enumerate_profile_posts: identifier is not a numeric mid: %s", identifier)
            return []

        result: list[dict] = []
        client = NetworkClient(Platform.BILIBILI)
        page = 1
        page_size = min(limit, 50)

        while len(result) < limit:
            if cancel_event and cancel_event.is_set():
                break

            api = (
                f"https://api.bilibili.com/x/space/arc/search"
                f"?mid={mid}&ps={page_size}&pn={page}"
            )
            data = client.get_json(api)
            if not data or data.get("code") != 0:
                break

            vlist = data.get("data", {}).get("list", {}).get("vlist", [])
            if not vlist:
                break

            for v in vlist:
                if cancel_event and cancel_event.is_set():
                    break

                title = v.get("title", "") or ""
                bvid = v.get("bvid", "") or ""
                if not title or not bvid:
                    continue

                result.append({
                    "title": title[:80],
                    "url": f"https://www.bilibili.com/video/{bvid}",
                    "thumbnail": v.get("pic", ""),
                })

                if len(result) >= limit:
                    break

            if callback:
                callback(len(result), limit)

            page += 1

            # Check if there are more pages
            page_data = data.get("data", {}).get("page", {})
            total = page_data.get("count", 0)
            if not total or page * page_size >= total:
                break

        logger.info(
            "Bilibili enumerate_profile_posts: mid=%s, found %d videos",
            mid, len(result),
        )
        return result

    def classify_error(self, error: Exception | str) -> str:
        text = str(error).lower()
        if any(kw in text for kw in ("cookie", "login", "auth", "session", "bili_jct", "buvid")):
            return ErrorCategory.COOKIE_EXPIRED.value
        if any(kw in text for kw in ("412", "precondition")):
            return ErrorCategory.RATE_LIMITED.value
        if any(kw in text for kw in ("not found", "已删除", "404", "unavailable", "private")):
            return ErrorCategory.CONTENT_REMOVED.value
        return _ce(error).value
