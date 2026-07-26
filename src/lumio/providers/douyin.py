"""Lumio V4 — 抖音 (Douyin) Provider。

参考 HelloTik 解析架构分析报告实现：
- 无水印：取 play_addr（播放地址体系），不取 download_addr（下载地址体系含水印）
- 多清晰度：调 aweme detail API，遍历 bit_rate[] 数组提取所有档位（报告第五节）
- CDN 直链：URL 直接透传，不包 token（报告第三节）
- 自动 ttwid：通过 bytedance register endpoint 自动获取，无需用户 cookie

URL 格式：
- v.douyin.com/{code}          → 移动端分享短链（normalize_url 先 302 展开）
- www.douyin.com/video/{id}    → PC 视频页（JS 混淆空壳，纯 requests 拿不到数据）
- www.iesdouyin.com/share/video/{id}/ → 移动端分享页（fallback，单清晰度）

解析优先级：
1. aweme detail API（多清晰度，需要 ttwid，自动获取或用户 cookie）
2. share 页 HTML（单清晰度 fallback）
"""

from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import urlparse, parse_qs

from .base import BaseProvider, MediaInfo, MediaItem, MediaType, FormatOption, Platform
from .network.client import NetworkClient
from .network.headers import platform_headers
from .registry import register
from ..utils.error_types import ErrorCategory, classify_error as _ce

logger = logging.getLogger(__name__)

# === URL 模式 ===
_VIDEO_ID_RE = re.compile(r"douyin\.com/video/(\d+)")
# 图文帖（note）路径，aweme_id 在路径里，API 与视频共用
_NOTE_ID_RE = re.compile(r"douyin\.com/note/(\d+)")
_PROFILE_RE = re.compile(r"douyin\.com/user/([\w.]+)")
_IES_RE = re.compile(r"iesdouyin\.com/(?:share/)?video/(\d+)")
_SHARE_URL_RE = re.compile(r"v\.douyin\.com/[\w]+")

# 移动端 UA（share 页需要移动端 UA，PC UA 会被反爬拦截）
_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
)
# PC UA（aweme detail API 需要 PC UA）
_PC_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# ttwid 自动获取 endpoint
_TTWID_REGISTER_URL = "https://ttwid.bytedance.com/ttwid/union/register/"
# aweme detail API（无需 a_bogus 签名，只需 ttwid cookie）
_AWEME_DETAIL_API = "https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={}&aid=6383&device_platform=webapp&channel=channel_pc_web"
# a_bogus 签名服务（方案B Playwright，可选增强：签名后多拿 H.265 档位）
_SIGN_SERVICE_URL = "http://localhost:9528"
# 签名服务健康检查缓存（避免每次解析都探测）
_sign_service_available: Optional[bool] = None


def _extract_video_id(url: str) -> Optional[str]:
    """从 URL 提取抖音 aweme_id（视频/图文帖共用同一 API）。"""
    m = _VIDEO_ID_RE.search(url) or _NOTE_ID_RE.search(url) or _IES_RE.search(url)
    return m.group(1) if m else None


def _get_douyin_cookies() -> dict[str, str]:
    """读取用户导入的抖音 cookie（可选增强，无则返回空）。

    用户可在 settings 页面导入 Netscape 格式 cookie 文件。
    若有 cookie，优先用用户的（可能含 msToken，更稳定）；
    若无，自动获取 ttwid 也能工作。
    """
    try:
        from ..utils.config import get_cookie_path
        cookie_path = get_cookie_path()
        if not cookie_path or not cookie_path.exists():
            return {}
        import http.cookiejar
        jar = http.cookiejar.MozillaCookieJar(str(cookie_path))
        jar.load(ignore_discard=True, ignore_expires=True)
        cookies = {}
        for c in jar:
            if "douyin" in c.domain or "iesdouyin" in c.domain or "snssdk" in c.domain:
                cookies[c.name] = c.value
        return cookies
    except Exception:
        return {}


def _fetch_ttwid() -> str:
    """自动获取 ttwid cookie（通过 bytedance register endpoint）。

    无需用户 cookie，纯自动获取。ttwid 是抖音访客标识，
    有了它就能调 aweme detail API 拿到完整视频数据。
    """
    import requests
    try:
        r = requests.post(
            _TTWID_REGISTER_URL,
            json={
                "region": "cn",
                "aid": 1768,
                "needFid": False,
                "service": "www.douyin.com",
                "migrate_info": {"ticket": "", "source": "node"},
                "cbUrlProtocol": "https",
                "union": True,
            },
            timeout=15,
            headers={"User-Agent": _PC_UA},
        )
        return r.cookies.get("ttwid", "")
    except Exception as e:
        logger.warning("Failed to fetch ttwid: %s", e)
        return ""


def _check_sign_service() -> bool:
    """检查 a_bogus 签名服务是否可用（localhost:9528）。

    签名服务基于 Playwright 真实浏览器（方案B），可选增强：
    - 签名后 API 返回更多 H.265 档位（15档 vs 12档）
    - 注意：web API 即使签名也拿不到超高清原画档（需 app API）

    结果缓存到模块级变量，避免每次解析都探测。
    """
    global _sign_service_available
    if _sign_service_available is not None:
        return _sign_service_available
    import requests
    try:
        r = requests.get(f"{_SIGN_SERVICE_URL}/health", timeout=2)
        ok = r.status_code == 200 and r.json().get("status") == "ok"
        _sign_service_available = ok
        if ok:
            logger.info("a_bogus 签名服务可用，将使用签名 API 获取更多档位")
        return ok
    except Exception:
        _sign_service_available = False
        return False


def _fetch_a_bogus(query: str) -> Optional[dict]:
    """调用签名服务获取 a_bogus + msToken。

    Args:
        query: API 查询参数（如 "aid=6383&aweme_id=xxx&device_platform=webapp"）

    Returns:
        {"a_bogus": "...", "msToken": "..."} 或 None
    """
    import requests
    try:
        r = requests.post(
            f"{_SIGN_SERVICE_URL}/sign",
            json={"query": query, "method": "GET"},
            timeout=15,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get("success") and data.get("a_bogus"):
            return {"a_bogus": data["a_bogus"], "msToken": data.get("msToken", "")}
        return None
    except Exception as e:
        logger.warning("签名服务请求失败: %s", e)
        return None


def _map_gear_to_label(gear_name: str, width: int = 0, height: int = 0) -> tuple[str, int]:
    """抖音 gear_name → (友好清晰度标签, 真实分辨率数字)。

    实测 gear_name 格式：
    - adapt_lowest_1440_1 → 1440p（最高清，2K）
    - normal_1080_0      → 1080p
    - normal_720_0       → 720p
    - normal_540_0       → 540p
    - low_720_0 / lower_540_0 / adapt_low_540_0 等 → 同分辨率的低码率变体
    - origin / source    → 超高清（原始码流，未经转码，HelloTik 报告指出）

    映射规则：
    1. 先匹配 origin/source/4k 等无数字命名（超高清原画档）
    2. 再从 gear_name 提取分辨率数字
    返回 (label, res_num)，res_num 是真实分辨率（如 1080），
    不是竖屏视频的 play_addr.height 长边（如 1920）。

    注意：抖音竖屏视频 play_addr.height 是长边（1920/1440/960/768），
    不能直接用作分辨率标签，必须从 gear_name 提取。
    """
    g = gear_name.lower()
    # 超高清原画档（无数字命名）：origin/source/4k/hdr
    # HelloTik 报告：这类档位是原始上传源文件，未经转码压缩
    if g in ("origin", "source", "original", "raw", "4k", "uhd", "hdr") or "origin" in g or "source" in g:
        return "超高清", 2160  # 用 2160 排序确保超高清排在最前
    # 按分辨率从高到低匹配
    for res in ("2160", "1440", "1080", "720", "540", "480", "360", "270", "240"):
        if res in g:
            return f"{res}p", int(res)
    # 兜底：用 width（短边）推断，不用 height（竖屏长边）
    if width >= 1440 or height >= 2560:
        return "1440p", 1440
    if width >= 1080 or height >= 1920:
        return "1080p", 1080
    if width >= 720 or height >= 1280:
        return "720p", 720
    if width >= 540 or height >= 960:
        return "540p", 540
    return "unknown", 0


@register
class DouyinProvider(BaseProvider):
    """抖音 (Douyin) 内容解析 Provider。

    设计参考 HelloTik 报告：
    - 无水印：只取 play_addr，绝不取 download_addr（报告第四节）
    - 多清晰度：遍历 bit_rate[] 数组，按分辨率去重保留最高码率（报告第五节）
    - CDN 直链：URL 直接透传，不包 token（报告第三节）
    - 自动 ttwid：无需用户 cookie 即可调 API
    """

    @property
    def platform(self) -> Platform:
        return Platform.DOUYIN

    def match(self, url: str) -> bool:
        return bool(
            _VIDEO_ID_RE.search(url)
            or _NOTE_ID_RE.search(url)
            or _PROFILE_RE.search(url)
            or _IES_RE.search(url)
            or _SHARE_URL_RE.search(url)
        )

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

        # 优先级 1：aweme detail API（多清晰度）
        detail = self._fetch_aweme_detail(video_id)
        if detail:
            info = self._parse_aweme_detail(detail, url, video_id)
            if info.media_items:
                return info
            logger.warning("aweme detail API 返回数据但解析失败，回退到 share 页")

        # 优先级 2：share 页 HTML（单清晰度 fallback）
        html = self._fetch_share_page(video_id)
        if html:
            info = self._parse_from_share_html(html, url, video_id)
            if info.media_items:
                return info

        return MediaInfo(
            platform=Platform.DOUYIN,
            url=url,
            title="抖音（解析失败）",
            author="",
            description=f"无法解析抖音视频（video_id: {video_id}）。视频可能不存在或已被删除。",
        )

    # === 优先级 1：aweme detail API（多清晰度） ===

    def _fetch_aweme_detail(self, video_id: str) -> Optional[dict]:
        """调 aweme detail API，返回 aweme_detail dict。

        优先使用 a_bogus 签名 API（签名服务可用时，返回更多 H.265 档位）；
        签名服务不可用时回退到无签名 API（只需 ttwid cookie）。

        注意：web API 即使签名也拿不到超高清原画档（需 app API + X-Argus 签名）。
        """
        import requests

        # 收集 cookies：用户 cookie 优先，无则自动获取 ttwid
        cookies = _get_douyin_cookies()
        if not cookies.get("ttwid"):
            ttwid = _fetch_ttwid()
            if ttwid:
                cookies["ttwid"] = ttwid

        if not cookies.get("ttwid"):
            logger.warning("无法获取 ttwid，aweme detail API 将不可用")
            return None

        # 构造 query（签名服务需要纯 query 参数）
        query = f"aid=6383&aweme_id={video_id}&device_platform=webapp&channel=channel_pc_web"

        # 优先尝试签名 API（签名服务可用时）
        if _check_sign_service():
            sign = _fetch_a_bogus(query)
            if sign:
                a_bogus = sign["a_bogus"]
                ms_token = sign["msToken"]
                cookies["msToken"] = ms_token
                api_url = (
                    f"https://www.douyin.com/aweme/v1/web/aweme/detail/?"
                    f"{query}&a_bogus={requests.utils.quote(a_bogus)}"
                    f"&msToken={requests.utils.quote(ms_token)}"
                )
                detail = self._request_aweme_detail(api_url, cookies, video_id)
                if detail:
                    return detail
                logger.warning("签名 API 失败，回退到无签名 API")

        # 回退：无签名 API
        api_url = _AWEME_DETAIL_API.format(video_id)
        return self._request_aweme_detail(api_url, cookies, video_id)

    def _request_aweme_detail(self, api_url: str, cookies: dict, video_id: str) -> Optional[dict]:
        """实际请求 aweme detail API 并解析响应。"""
        import requests
        try:
            r = requests.get(
                api_url,
                cookies=cookies,
                timeout=15,
                headers={
                    "User-Agent": _PC_UA,
                    "Referer": f"https://www.douyin.com/video/{video_id}",
                    "Accept": "application/json",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
            )
            if r.status_code != 200:
                logger.warning("aweme detail API returned %d for %s", r.status_code, video_id)
                return None
            content_type = r.headers.get("content-type", "")
            if "json" not in content_type.lower():
                logger.warning("aweme detail API 返回非 JSON 响应 (content-type: %s)", content_type)
                return None
            data = r.json()
            detail = data.get("aweme_detail")
            if not detail:
                logger.warning("aweme detail API returned empty aweme_detail for %s", video_id)
                return None
            return detail
        except Exception as e:
            logger.warning("aweme detail API failed for %s: %s", video_id, e)
            return None

    def _parse_aweme_detail(self, detail: dict, original_url: str, video_id: str) -> MediaInfo:
        """从 aweme_detail dict 提取多清晰度 MediaInfo。

        数据结构对齐 HelloTik UnifiedMediaInfo：
        - title  ← desc
        - author ← author.nickname
        - cover  ← video.cover.url_list[0]
        - duration ← duration（毫秒）
        - videos ← bit_rate[] 遍历，每个档位一个 MediaItem
        - pics   ← [cover_url]
        """
        # === 基本信息 ===
        title = (detail.get("desc") or "")[:80]
        author_info = detail.get("author", {}) or {}
        author = author_info.get("nickname", "")
        author_id = str(author_info.get("uid", ""))

        # 创建时间
        post_time = ""
        create_time = detail.get("create_time", 0)
        if create_time:
            import datetime
            try:
                ts = int(create_time)
                dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
                post_time = dt.strftime("%Y%m%d_%H%M%S")
            except (ValueError, OSError):
                post_time = str(create_time)

        # 时长（毫秒 → 秒）
        duration = None
        raw_duration = detail.get("duration", 0)
        if raw_duration:
            duration = raw_duration // 1000 if raw_duration > 1000 else raw_duration

        # 封面
        video_info = detail.get("video", {}) or {}
        cover_url = ""
        cover = video_info.get("cover", {}) or video_info.get("origin_cover", {})
        cover_urls = cover.get("url_list", [])
        if cover_urls:
            cover_url = cover_urls[0]

        # === 图文帖（note）：images 字段非空，无 video.bit_rate ===
        images_list = detail.get("images") or []
        if images_list:
            media_items: list[MediaItem] = []
            for idx, img in enumerate(images_list):
                # 图文帖每项是图片对象，url_list 含多档清晰度，取第一个
                url_list = img.get("url_list", []) or []
                if not url_list:
                    continue
                # url_list[0] 通常是最高清，url_list[-1] 是缩略图
                img_url = url_list[0]
                # 尝试取 width/height
                width = img.get("width", 0) or 0
                height = img.get("height", 0) or 0
                media_items.append(MediaItem(
                    url=img_url,
                    is_video=False,
                    index=idx,
                    width=width,
                    height=height,
                    extension="jpg",
                    media_type=MediaType.IMAGE,
                ))

            # 图文帖封面取首图
            if not cover_url and media_items:
                cover_url = media_items[0].url

            return MediaInfo(
                platform=Platform.DOUYIN,
                url=original_url,
                title=title or "抖音图文",
                author=author,
                author_id=author_id,
                thumbnail=cover_url,
                duration=None,
                media_items=media_items,
                post_time=post_time,
            )

        # === 多清晰度：遍历 bit_rate[] 数组 ===
        # 参考报告第五节：bit_rate[] 每项含 gear_name + play_addr.url_list
        # 按分辨率去重：同分辨率只保留码率最高的 normal 档（跳过 low/adapt 变体）
        bit_rate_list = video_info.get("bit_rate", [])
        formats_by_label: dict[str, dict] = {}  # label → {url, size, width, height, bitrate}

        for br in bit_rate_list:
            gear_name = br.get("gear_name", "")
            bitrate = br.get("bit_rate", 0)
            play_addr = br.get("play_addr", {}) or {}
            url_list = play_addr.get("url_list", [])
            width = play_addr.get("width", 0)
            height = play_addr.get("height", 0)
            data_size = play_addr.get("data_size", 0)

            if not url_list:
                continue

            url = url_list[0]
            label, res_num = _map_gear_to_label(gear_name, width, height)
            if label == "unknown":
                continue

            # 同分辨率去重：保留码率最高的（normal > low > adapt）
            existing = formats_by_label.get(label)
            if existing is None:
                formats_by_label[label] = {
                    "url": url, "size": data_size,
                    "width": width, "height": height,
                    "res_num": res_num,
                    "bitrate": bitrate, "gear": gear_name,
                }
            elif bitrate > existing["bitrate"]:
                # 码率更高，替换
                formats_by_label[label].update({
                    "url": url, "size": data_size,
                    "width": width, "height": height,
                    "res_num": res_num,
                    "bitrate": bitrate, "gear": gear_name,
                })

        # 按分辨率降序排列（1440p > 1080p > 720p > 540p > ...）
        def _res_sort_key(label: str) -> int:
            num = re.search(r"(\d+)", label)
            return int(num.group(1)) if num else 0

        sorted_labels = sorted(formats_by_label.keys(), key=_res_sort_key, reverse=True)

        # === 构建 MediaItem + FormatOption ===
        # 单视频只保留一个 MediaItem（最高画质），多清晰度通过 formats 列表选择
        # 避免预览横向列表出现多个单项（修复清单问题 8）
        media_items: list[MediaItem] = []
        formats: list[FormatOption] = []

        if sorted_labels:
            best_label = sorted_labels[0]
            best = formats_by_label[best_label]
            # width/height 用 API 真实像素尺寸（竖屏视频 height 是长边如 1920），
            # 供 QML _previewAspectRatio() 计算正确宽高比（9:16），
            # 避免在 1:1 方形容器中显示导致左右大片黑边。
            # 清晰度标签走 quality 字段（如 "1080p"），FormatOption.height 用 res_num
            # 供格式下拉显示 "1080P"，两条路径互不干扰。
            media_items.append(MediaItem(
                url=best["url"],
                is_video=True,
                index=0,
                width=best["width"],
                height=best["height"],
                size=best["size"],
                quality=best_label,
                mime="video/mp4",
                extension="mp4",
                media_type=MediaType.VIDEO,
            ))

        # 所有清晰度档位写入 formats 供下载时选择
        for idx, label in enumerate(sorted_labels):
            f = formats_by_label[label]
            res_num = f["res_num"]
            size_str = f"{f['size'] / 1024 / 1024:.1f}MB" if f["size"] else ""
            formats.append(FormatOption(
                format_id=label,
                label=f"{label} ({size_str})" if size_str else label,
                type="video",
                ext="mp4",
                width=f["width"],
                height=res_num,
            ))

        # 封面图作为单独 MediaItem（与 B站一致：横向列表显示封面+视频两个卡片）
        # 顺序：视频项在前，封面图项在后
        if cover_url and media_items:
            media_items.append(MediaItem(
                url=cover_url,
                is_video=False,
                index=len(media_items),
                extension="jpg",
                media_type=MediaType.IMAGE,
                quality="封面",
            ))

        if not media_items:
            return MediaInfo(
                platform=Platform.DOUYIN,
                url=original_url,
                title=title or "抖音（解析失败）",
                author=author,
                description="aweme detail 返回数据但未提取到媒体。",
            )

        return MediaInfo(
            platform=Platform.DOUYIN,
            url=original_url,
            title=title or "抖音视频",
            author=author,
            author_id=author_id,
            thumbnail=cover_url,
            post_time=post_time,
            description=title or "抖音视频",
            duration=duration,
            media_items=media_items,
            formats=formats,
            type="video",
        )

    # === 优先级 2：share 页 HTML（单清晰度 fallback） ===

    def _fetch_share_page(self, video_id: str) -> Optional[str]:
        """抓取 iesdouyin.com/share/video/{id}/ 移动端分享页 HTML。"""
        client = NetworkClient(Platform.DOUYIN)
        share_url = f"https://www.iesdouyin.com/share/video/{video_id}/"
        return client.get_html(
            share_url,
            headers={
                "User-Agent": _MOBILE_UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )

    def _parse_from_share_html(self, html: str, original_url: str, video_id: str) -> MediaInfo:
        """从 share 页 HTML 提取单清晰度 MediaInfo（fallback）。

        share 页只有单档清晰度（通常 720p），数据结构对齐多清晰度版本。
        无水印原理：share 页返回的是 play_addr（无水印），不是 download_addr（带水印）。
        """
        title = ""
        author = ""
        thumbnail = ""
        post_time = ""
        video_url = ""
        cover_url = ""

        # 标题 desc
        m = re.search(r'"desc"\s*:\s*"((?:[^"\\]|\\.)*)"', html)
        if m:
            title = m.group(1)[:80]

        # 作者 nickname
        m = re.search(r'"nickname"\s*:\s*"((?:[^"\\]|\\.)*)"', html)
        if m:
            author = m.group(1)

        # 创建时间
        m = re.search(r'"create_time"\s*:\s*(\d+)', html)
        if m:
            import datetime
            try:
                ts = int(m.group(1))
                dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
                post_time = dt.strftime("%Y%m%d_%H%M%S")
            except (ValueError, OSError):
                post_time = m.group(1)

        # 视频 URL：play_addr.url_list[0]（playwm，302 跳转无水印 CDN 直链）
        m = re.search(r'"play_addr"\s*:\s*\{[^}]*"url_list"\s*:\s*\[([^\]]+)\]', html)
        if m:
            urls = re.findall(r'"([^"]+)"', m.group(1))
            for u in urls:
                u_decoded = u.replace("\\u002F", "/")
                if u_decoded.startswith("http") and "playwm" in u_decoded:
                    video_url = u_decoded
                    break
            if not video_url:
                for u in urls:
                    u_decoded = u.replace("\\u002F", "/")
                    if u_decoded.startswith("http"):
                        video_url = u_decoded
                        break

        # 封面图
        for m in re.finditer(r'"cover"\s*:\s*\{[^}]*"url_list"\s*:\s*\[([^\]]+)\]', html):
            urls = re.findall(r'"([^"]+)"', m.group(1))
            for u in urls:
                u_decoded = u.replace("\\u002F", "/")
                if u_decoded.startswith("http") and "1080x1080" in u_decoded:
                    cover_url = u_decoded
                    break
            if cover_url:
                break
        if not cover_url:
            m = re.search(r'"cover"\s*:\s*\{[^}]*"url_list"\s*:\s*\["([^"]+)"', html)
            if m:
                cover_url = m.group(1).replace("\\u002F", "/")
        if cover_url:
            thumbnail = cover_url

        media_items: list[MediaItem] = []
        formats: list[FormatOption] = []

        if video_url:
            # 从 playwm URL 的 ratio 参数推断清晰度
            q = parse_qs(urlparse(video_url).query)
            quality_label = q.get("ratio", [""])[0] or "720p"
            media_items.append(MediaItem(
                url=video_url, is_video=True, index=0,
                media_type=MediaType.VIDEO, quality=quality_label,
                mime="video/mp4", extension="mp4",
            ))
            formats.append(FormatOption(
                format_id=quality_label, label=quality_label,
                type="video", ext="mp4",
            ))

        # 封面图作为单独 MediaItem（与 B站一致：横向列表显示封面+视频两个卡片）
        if cover_url and media_items:
            media_items.append(MediaItem(
                url=cover_url,
                is_video=False,
                index=len(media_items),
                extension="jpg",
                media_type=MediaType.IMAGE,
                quality="封面",
            ))

        if not media_items:
            return MediaInfo(
                platform=Platform.DOUYIN,
                url=original_url,
                title=title or "抖音（解析失败）",
                author=author,
                description="无法从分享页提取媒体数据。",
            )

        return MediaInfo(
            platform=Platform.DOUYIN,
            url=original_url,
            title=title or "抖音视频",
            author=author,
            thumbnail=thumbnail,
            post_time=post_time,
            description=title or "抖音视频",
            media_items=media_items,
            formats=formats,
            type="video",
        )

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
