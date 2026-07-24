"""Provider registry — 管理和发现所有平台 Provider。

支持手动注册和自动发现两种方式。
在 Phase 1 中仅实现手动注册。
"""

from __future__ import annotations

from typing import Optional

from .base import BaseProvider, Platform
from .detector import detect_domestic
from .url_normalizer import normalize_url
from . import cache as provider_cache


# 全局注册表: Platform -> Provider 类
_registry: dict[Platform, type[BaseProvider]] = {}


def register(provider_cls: type[BaseProvider]) -> type[BaseProvider]:
    """注册 Provider 类。

    可用作装饰器:
        @register
        class WeiboProvider(BaseProvider):
            ...
    """
    if not (isinstance(provider_cls, type) and issubclass(provider_cls, BaseProvider)):
        raise TypeError(f"{provider_cls.__name__} must be a BaseProvider subclass")
    instance = provider_cls()
    _registry[instance.platform] = provider_cls
    return provider_cls


def get_provider(url: str) -> Optional[BaseProvider]:
    """根据 URL 获取匹配的 Provider 实例。

    优先匹配国外平台（YouTube/Instagram/X），不匹配再回退到 detect_domestic。
    URL 会先经过规范化处理（短链接解析）。
    """
    # 规范化短链接（t.cn -> weibo.com 等）
    normalized = normalize_url(url)

    # 优先：遍历已注册 Provider，按 match() 判断（覆盖国外平台）
    # 国外平台（YouTube/Instagram/X）的 match() 直接判断域名，
    # 必须先于 detect_domestic 处理，避免误判为 UNSUPPORTED。
    for platform, cls in _registry.items():
        try:
            instance = cls()
            if instance.match(normalized):
                return instance
        except Exception:
            continue

    # 回退：国内平台通过 detect_domestic() 识别
    result = detect_domestic(normalized)
    if result is None:
        return None
    platform, _ = result
    cls = _registry.get(platform)
    return cls() if cls else None


def get_provider_for(platform: Platform) -> Optional[BaseProvider]:
    """根据 Platform 枚举获取 Provider 实例。"""
    cls = _registry.get(platform)
    return cls() if cls else None


def get_all_platforms() -> list[Platform]:
    """返回所有已注册的平台列表。"""
    return list(_registry.keys())


def is_registered(platform: Platform) -> bool:
    """指定平台是否已注册 Provider。"""
    return platform in _registry


def clear() -> None:
    """清空注册表和缓存（仅用于测试）。"""
    _registry.clear()
    provider_cache.clear_cache()
