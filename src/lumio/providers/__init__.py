"""Lumio V4 Platform Layer.

统一的平台抽象层，用于国内平台支持。
新平台只需实现 Provider + Parser，复用现有下载/队列/存储流程。
"""

from .exceptions import (
    CacheError,
    ContentRemoved,
    CookieExpired,
    NetworkError,
    ParseError,
    ParserError,
    RateLimit,
    UnsupportedPlatform,
)
from .base import (
    BaseProvider,
    FormatOption,
    MediaInfo,
    MediaItem,
    MediaType,
    Platform,
)
from .detector import detect_domestic
from .detector import extract_profile_identifier
from .url_normalizer import normalize_url
from .weibo import WeiboProvider  # noqa: F401
from .xiaohongshu import XiaohongshuProvider  # noqa: F401
from .bilibili import BilibiliProvider  # noqa: F401
from .douyin import DouyinProvider  # noqa: F401
from .kuaishou import KuaishouProvider  # noqa: F401
from .youtube import YouTubeProvider  # noqa: F401
from .instagram import InstagramProvider  # noqa: F401
from .x import XProvider  # noqa: F401
from .registry import (
    get_all_platforms,
    get_provider,
    get_provider_for,
    is_registered,
    register,
)
from . import cache as provider_cache

__all__ = [
    # 异常类
    "CacheError",
    "ContentRemoved",
    "CookieExpired",
    "NetworkError",
    "ParseError",
    "ParserError",
    "RateLimit",
    "UnsupportedPlatform",
    # 类型
    "BaseProvider",
    "FormatOption",
    "MediaInfo",
    "MediaItem",
    "MediaType",
    "Platform",
    # URL 检测
    "detect_domestic",
    "extract_profile_identifier",
    # URL 规范化
    "normalize_url",
    # 缓存
    "provider_cache",
    # 注册表
    "get_all_platforms",
    "get_provider",
    "get_provider_for",
    "is_registered",
    "register",
    # 新 Provider 类
    "WeiboProvider",
    "XiaohongshuProvider",
    "BilibiliProvider",
    "DouyinProvider",
    "KuaishouProvider",
    "YouTubeProvider",
    "InstagramProvider",
    "XProvider",
    "normalize_url",
    "extract_profile_identifier",
    "provider_cache",
]
