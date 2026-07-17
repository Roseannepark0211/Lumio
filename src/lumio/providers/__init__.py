"""Lumio V4 Platform Layer.

统一的平台抽象层，用于国内平台支持。
新平台只需实现 Provider + Parser，复用现有下载/队列/存储流程。
"""

from .base import (
    BaseProvider,
    FormatOption,
    MediaInfo,
    MediaItem,
    Platform,
)
from .detector import detect_domestic
from .weibo import WeiboProvider  # noqa: F401 — triggers @register
from .registry import (
    get_all_platforms,
    get_provider,
    get_provider_for,
    is_registered,
    register,
)

__all__ = [
    # 类型
    "BaseProvider",
    "FormatOption",
    "MediaInfo",
    "MediaItem",
    "Platform",
    # URL 检测
    "detect_domestic",
    # 注册表
    "get_all_platforms",
    "get_provider",
    "get_provider_for",
    "is_registered",
    "register",
]
