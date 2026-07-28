"""Lumio V4 Platform Layer — 基础类型与 Provider 抽象接口。

所有新平台（微博/小红书/B站/抖音等）均基于此层构建。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Platform(Enum):
    """支持的所有平台枚举。"""

    # === 现有 ===
    YOUTUBE = "youtube"
    INSTAGRAM = "instagram"
    X = "x"
    UNSUPPORTED = "unsupported"

    # === V4 国内平台 ===
    WEIBO = "weibo"
    XIAOHONGSHU = "xiaohongshu"
    BILIBILI = "bilibili"
    DOUYIN = "douyin"
    KUAISHOU = "kuaishou"       # 预留
    SHIPINHAO = "shipinhao"     # 预留

    @property
    def is_domestic(self) -> bool:
        """是否属于国内平台。"""
        return self in {
            Platform.WEIBO, Platform.XIAOHONGSHU,
            Platform.BILIBILI, Platform.DOUYIN,
            Platform.KUAISHOU, Platform.SHIPINHAO,
        }



class MediaType(Enum):
    """媒体类型枚举。

    替代 is_video bool 标记，支持更多媒体类型。
    """
    IMAGE = "image"
    VIDEO = "video"
    LIVE_PHOTO = "live_photo"
    GIF = "gif"
    AUDIO = "audio"
    DOCUMENT = "document"
    UNKNOWN = "unknown"





@dataclass
class LivePhoto:
    image: str = ""
    video: str = ""
    cover: str = ""

@dataclass
class MediaItem:
    """单条媒体资源（图片/视频/Live Photo/音频/文档）。

    所有 Provider 的 media_items 列表中的元素。
    新增平台应使用 media_type 字段而非 is_video。
    """
    url: str
    is_video: bool = False
    index: int = 0
    width: int = 0
    height: int = 0
    extension: str = ""
    original_url: str = ""
    media_type: MediaType = MediaType.UNKNOWN
    size: int = 0
    quality: str = ""
    mime: str = ""
    id: str = ""
    filename: str = ""
    live_photo: Optional[LivePhoto] = None

    def __post_init__(self):
        if self.media_type == MediaType.UNKNOWN:
            if self.is_video:
                self.media_type = MediaType.VIDEO
            else:
                self.media_type = MediaType.IMAGE


@dataclass
class FormatOption:
    """下载格式选项（用于格式选择对话框）。"""
    format_id: str
    label: str
    type: str          # "video" / "audio" / "image"
    ext: str = ""
    width: int = 0
    height: int = 0


@dataclass
class MediaInfo:
    """统一解析结果 —— 替换 VideoInfo 用于新平台。

    所有 Provider 的 extract_info() 均返回此结构。
    """
    platform: Platform
    url: str
    title: str
    author: str
    author_id: str = ""
    post_time: str = ""
    thumbnail: str = ""
    description: str = ""
    duration: Optional[int] = None
    tags: list[str] = field(default_factory=list)
    media_items: list[MediaItem] = field(default_factory=list)
    formats: list[FormatOption] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)
    type: str = ""


class BaseProvider(ABC):
    """所有平台 Provider 的抽象基类。

    Provider 只负责：
    - URL 匹配（match）
    - 内容解析 + 元数据提取（extract_info）

    不负责下载、队列、存储 —— 这些由现有模块统一处理。
    """

    @property
    @abstractmethod
    def platform(self) -> Platform:
        """返回此 Provider 对应的平台枚举。"""
        ...

    @abstractmethod
    def match(self, url: str) -> bool:
        """URL 是否属于此平台。"""
        ...

    @abstractmethod
    def extract_info(self, url: str) -> MediaInfo:
        """解析 URL，返回统一的媒体信息。"""
        ...

    def get_request_headers(self) -> dict[str, str]:
        """返回此平台 HTTP 请求的默认请求头。

        子类可重写此方法添加 Referer/Cookie/UA 等。
        """
        # M5 修复：用 utils.ua.DEFAULT_UA 跨平台 UA 替代硬编码 Windows NT 10.0
        from ..utils.ua import DEFAULT_UA
        return {
            "User-Agent": DEFAULT_UA,
        }


    def classify_error(self, error: Exception | str) -> str:
        """将异常分类为预定义的错误类别。

        返回 ErrorCategory 的 value 字符串。
        默认调用 error_types.classify_error() 分类。
        各 Provider 可重写此方法添加平台特定的错误判断。
        """
        from ..utils.error_types import classify_error as _ce
        return _ce(error).value

    def enumerate_profile_posts(
        self,
        identifier: str,
        limit: int = 20,
        callback=None,
        cancel_event=None,
    ) -> list[dict]:
        """枚举用户主页的帖子列表。

        Args:
            identifier: 用户 ID / 用户名（从 URL 提取）
            limit: 最大枚举数量
            callback: 可选进度回调 callback(current, total)
            cancel_event: 可选取消事件 threading.Event

        Returns:
            帖子信息列表，每项含 {title, url, thumbnail} 三个键
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} 不支持主页批量枚举，"
            "请使用单条链接解析下载。"
        )
