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


@dataclass
class MediaItem:
    """单条媒体资源（图片或视频）。"""
    url: str
    is_video: bool
    index: int = 0
    width: int = 0
    height: int = 0
    extension: str = ""
    original_url: str = ""


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
