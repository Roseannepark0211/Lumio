"""Lumio V4 — YouTube Provider。

包装 yt-dlp 提取视频元数据 + 格式列表，供下载时选格式。
所有下载逻辑仍由 downloader.py 的 yt-dlp 路径处理。

URL 格式：
- youtube.com/watch?v={id}
- youtu.be/{id}
- youtube.com/playlist?list={id}  （批量枚举，由 yt_dialog.py 处理）
- youtube.com/@channel/videos       （批量枚举）
- 频道/主页（批量下载重做阶段 1）：youtube.com/channel/{id}、
  youtube.com/@handle、youtube.com/user/{name}、youtube.com/c/{name}
  → 用 list_channel_works() 拉取作品列表（yt-dlp flat-playlist）。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from .base import BaseProvider, FormatOption, MediaInfo, MediaItem, MediaType, Platform
from .registry import register

logger = logging.getLogger(__name__)

# URL 模式
_YT_WATCH_RE = re.compile(r"youtube\.com/watch\?v=([\w-]+)")
_YT_SHORT_RE = re.compile(r"youtu\.be/([\w-]+)")
_YT_EMBED_RE = re.compile(r"youtube\.com/embed/([\w-]+)")
_YT_SHORTS_RE = re.compile(r"youtube\.com/shorts/([\w-]+)")

# 频道/主页 URL 模式（批量下载：主页作品列表入口）
# 覆盖 /channel/UC…、/@handle、/user/…、/c/… 及其子路径（/videos、/shorts 等）
_YT_CHANNEL_RES = [
    re.compile(r"youtube\.com/channel/([\w-]+)"),
    re.compile(r"youtube\.com/@([\w.\-]+)"),
    re.compile(r"youtube\.com/user/([\w\-]+)"),
    re.compile(r"youtube\.com/c/([\w\-]+)"),
]


def is_channel_url(url: str) -> bool:
    """判断是否为 YouTube 频道/主页链接（区别于单个视频/播放列表）。"""
    if not url:
        return False
    return any(p.search(url) for p in _YT_CHANNEL_RES)


# 频道子标签：已带标签的链接保持原样，不带标签的裸主页默认指向 /videos
_YT_CHANNEL_TAB_RE = re.compile(
    r"/(videos|shorts|streams|playlists|search|channels|about|community|featured)\b"
)


def _normalize_channel_url(url: str) -> str:
    """把裸频道/主页链接规范化到 /videos 标签页。

    实测：flat 模式下直接传裸主页（如 /@CHUANGASIA）会返回
    Videos/Live/Shorts 三个标签页本身而非作品；/videos 标签页才返回作品。
    已带标签的链接保持原样；query/fragment 不影响列表，顺手去掉。
    """
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    if not _YT_CHANNEL_TAB_RE.search(path):
        path = f"{path}/videos"
    return urlunparse(parsed._replace(path=path, query="", fragment=""))


class ChannelListError(Exception):
    """频道作品列表拉取失败（明确错误，调用方不得静默为空列表处理）。"""


@dataclass
class ChannelWork:
    """频道作品列表中的一项（本地类型，不动 base.py 的共享模型）。

    duration 单位为秒；upload_date 为 YYYYMMDD，flat 模式下可能为空。
    """

    video_id: str
    url: str
    title: str
    thumbnail: str = ""
    duration: Optional[int] = None
    upload_date: str = ""


@dataclass
class ChannelWorksPage:
    """一页频道作品：has_more 表示是否还有下一页（用 limit+1 条探测）。

    author 为频道名（flat 列表 info 的 channel/uploader），拿不到时为空串，
    调用方用它做弹窗标题与默认文件夹名，缺失时不阻塞列表展示。
    """

    works: list = field(default_factory=list)
    has_more: bool = False
    page: int = 1
    page_size: int = 30
    author: str = ""


def _pick_thumbnail(entry: dict) -> str:
    """从 flat 条目里选一张最宽的缩略图，兜底 thumbnail 字段。"""
    thumbs = entry.get("thumbnails") or []
    best_url = ""
    best_w = -1
    for t in thumbs:
        if not isinstance(t, dict):
            continue
        u = t.get("url") or ""
        if not u:
            continue
        w = t.get("width") or 0
        if w >= best_w:
            best_w = w
            best_url = u
    return best_url or entry.get("thumbnail") or ""


def _entry_to_work(entry: dict) -> Optional[ChannelWork]:
    vid = entry.get("id") or ""
    if not vid:
        return None
    raw_url = entry.get("webpage_url") or entry.get("url") or ""
    # flat 模式下 entry["url"] 常常只是视频 id，需拼成完整 watch 链接
    if not raw_url.startswith("http"):
        raw_url = f"https://www.youtube.com/watch?v={vid}"
    duration = entry.get("duration")
    if duration is not None:
        try:
            duration = int(duration)
        except (TypeError, ValueError):
            duration = None
    return ChannelWork(
        video_id=vid,
        url=raw_url,
        title=entry.get("title") or "",
        thumbnail=_pick_thumbnail(entry),
        duration=duration,
        upload_date=entry.get("upload_date") or "",
    )


def list_channel_works(url: str, limit: int = 30, page: int = 1) -> ChannelWorksPage:
    """拉取 YouTube 频道/主页的一页作品列表。

    走 yt-dlp flat-playlist（只取列表元数据，不打开每个视频页），
    用 --playlist-items 按页切片：每次多取 1 条探测 has_more，
    绝不一次拉全量。失败时抛 ChannelListError（不返回静默空列表）；
    频道本身确实 0 作品时返回空页（has_more=False）。
    """
    import yt_dlp
    from ..utils.config import get_cookie_path

    if page < 1:
        raise ValueError(f"page 必须 >= 1，得到 {page}")
    if limit < 1 or limit > 100:
        raise ValueError(f"limit 必须在 1~100 之间，得到 {limit}")
    if not is_channel_url(url):
        raise ValueError(f"不是频道/主页链接：{url}")
    # 裸主页默认拉 /videos 标签页的作品（见 _normalize_channel_url）
    url = _normalize_channel_url(url)

    start = (page - 1) * limit + 1
    end = page * limit + 1  # 多取 1 条，用于判断是否还有下一页

    cookie = get_cookie_path()
    opts = _yt_opts(cookie)
    opts["skip_download"] = True
    # ★ 关键：--flat-playlist 在 CLI 层对应 extract_flat='in_playlist'，
    #   而不是 flat_playlist=True（后者在本版 yt-dlp 里不生效，
    #   会导致每个视频被完整提取：网页 + player API + m3u8，31 条可拖数分钟）。
    opts["extract_flat"] = "in_playlist"
    opts["playlist_items"] = f"{start}-{end}"
    # ★ 列表是交互操作：共享 yt_opts 的重试策略是为大文件下载调的
    #   （retries=30 + 指数退避到 60s，持续失败时可拖 20 分钟以上），
    #   直接沿用会导致弹窗长时间挂起。本地覆盖为快速失败：
    #   持续失败时约 1 分钟内抛 ChannelListError（明确报错，不静默）。
    #   opts 是 _yt_opts() 现场新建的 dict，覆盖不影响共享配置与其他调用方。
    opts["retries"] = 3
    opts["fragment_retries"] = 3
    opts["retry_sleep_functions"] = {
        "http": lambda n: min(n, 3),
        "fragment": lambda n: min(n, 3),
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        msg = str(e)
        if "Sign in to confirm" in msg or "not a bot" in msg:
            raise ChannelListError(
                "YouTube 要求登录态或触发机器人墙（共享出口 IP），"
                "频道列表暂时无法拉取；请在有登录态的环境重试"
            ) from e
        if "Private" in msg or "private" in msg:
            raise ChannelListError(f"频道无法访问（可能为私密频道）：{msg}") from e
        raise ChannelListError(f"频道列表拉取失败：{msg}") from e

    if not isinstance(info, dict):
        raise ChannelListError(f"频道列表返回异常结构：{type(info).__name__}")
    entries = info.get("entries") or []
    if not entries and info.get("id") and info.get("_type") != "playlist":
        # 返回的是单个视频而非列表，说明链接并非频道列表页
        raise ChannelListError("该链接未解析为频道列表（返回了单个视频）")

    works = []
    for entry in entries[:limit]:
        if not isinstance(entry, dict):
            continue
        work = _entry_to_work(entry)
        if work is not None:
            works.append(work)

    return ChannelWorksPage(
        works=works,
        has_more=len(entries) > limit,
        page=page,
        page_size=limit,
        # 频道名：flat 列表 info 的 channel/uploader；拿不到时为空串，
        # 预览调用方不因此阻塞（弹窗标题与默认文件夹名有兜底）。
        author=info.get("channel") or info.get("uploader") or "",
    )


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
        # 显式模式优先：单个视频 + 频道/主页；兜底保留原有宽泛匹配（不收窄，
        # 避免影响播放列表等既有调用方）。
        return bool(
            _YT_WATCH_RE.search(url)
            or _YT_SHORT_RE.search(url)
            or _YT_EMBED_RE.search(url)
            or _YT_SHORTS_RE.search(url)
            or is_channel_url(url)
            or "youtube.com" in url
            or "youtu.be" in url
            or "googleapis.com/youtube" in url
        )

    def list_channel(self, url: str, limit: int = 30, page: int = 1) -> ChannelWorksPage:
        """频道/主页作品列表（批量下载入口），见模块级 list_channel_works。"""
        return list_channel_works(url, limit=limit, page=page)

    def extract_info(self, url: str) -> MediaInfo:
        import yt_dlp
        from ..utils.config import get_cookie_path

        # 频道/主页链接不再静默返回列表第一个视频：明确失败并指引到
        # list_channel_works（保持原有“解析失败”MediaInfo 契约，不会被缓存）。
        if is_channel_url(url):
            return MediaInfo(
                platform=Platform.YOUTUBE,
                url=url,
                title="YouTube（解析失败）",
                author="",
                description="频道/主页链接请使用批量下载的频道列表功能（list_channel_works），"
                "extract_info 只处理单个视频。",
            )

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
