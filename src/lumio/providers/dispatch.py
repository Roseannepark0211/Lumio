"""Provider dispatch — bridge between Provider system and existing download flow.

Phase 1 Step 2:
  Provider → MediaInfo → Queue（迁移完成，旧 VideoInfo 已删除）

V4.0 additions:
  - URL normalization before detection (Section 20)
  - URL → MediaInfo cache (Section 23)
"""

from __future__ import annotations

import logging
from typing import Optional

from . import cache as provider_cache
from .base import MediaInfo
from .detector import detect_domestic
from .registry import get_provider
from .url_normalizer import normalize_url

logger = logging.getLogger(__name__)


def _is_failed_media_info(info: MediaInfo) -> bool:
    """判断 MediaInfo 是否是解析失败的结果（不应被缓存）。

    失败标志：
    - 无 media_items（没提取到任何媒体）
    - title 含"解析失败"/"链接识别失败"
    - description 含错误信息（"无法"/"失败"等）
    """
    if not info.media_items:
        return True
    title = info.title or ""
    if "解析失败" in title or "链接识别失败" in title:
        return True
    desc = info.description or ""
    if desc and ("无法" in desc or "失败" in desc):
        return True
    return False


def _normalize_cache_key(url: str) -> str:
    """规范化 URL 作为缓存 key：去掉 query/fragment，避免同一资源因不同 query 重复缓存。

    例：instagram.com/p/ABC/?utm_source=ig_web_copy_link 与 instagram.com/p/ABC/ 共享缓存。
    """
    from urllib.parse import urlparse, urlunparse
    try:
        parsed = urlparse(url)
        return urlunparse(parsed._replace(query="", fragment=""))
    except Exception:
        return url


def resolve_via_providers(url: str) -> Optional[MediaInfo]:
    """Try to resolve a URL through the Provider system.

    Returns a MediaInfo if a registered provider handles the URL,
    or None if no provider matches.

    V4 统一架构：所有平台（YouTube/Instagram/X/国内平台）都走此入口。
    优先级：缓存 → 已注册 Provider match() → detect_domestic 兜底。

    注意：失败的 MediaInfo（无 media_items / 含错误描述）不会被缓存，
    避免网络抖动/cookie 失效导致的失败结果阻塞后续重试。
    """
    # Step 1: normalize short URLs (t.cn -> weibo.com, etc.)
    normalized = normalize_url(url)

    # Step 2: 用规范化 URL（去 query/fragment）作为缓存 key，
    # 避免同一帖子因 igsh/utm_source 等 query 参数重复缓存
    cache_key = _normalize_cache_key(normalized)

    # Step 2.5: 检查缓存 —— 跳过失败的缓存项（兼容旧版本写入的失败缓存）
    cached = provider_cache.get(cache_key)
    if cached is not None:
        if _is_failed_media_info(cached):
            # 命中失败缓存，跳过直接重新解析（不返回缓存的失败结果）
            logger.debug("resolve_via_providers: 跳过失败缓存 %s", cache_key[:60])
        else:
            logger.debug("resolve_via_providers: cache hit for %s", cache_key[:60])
            return cached

    # Step 3: get_provider 会先遍历已注册 Provider 的 match()，
    # 再回退到 detect_domestic() 识别国内平台
    provider = get_provider(normalized)
    if provider is None:
        return None

    media_info = provider.extract_info(normalized)

    # Step 4: 仅缓存成功的结果，失败结果不缓存
    # （避免网络抖动/cookie 失效/429 限流等临时错误阻塞后续重试）
    if not _is_failed_media_info(media_info):
        try:
            provider_cache.set(cache_key, media_info)
        except Exception:
            pass
    else:
        logger.debug("resolve_via_providers: 解析失败，跳过缓存 %s", cache_key[:60])

    return media_info
