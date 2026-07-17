"""URL 规范化模块（Section 20）。

处理分享短链接 → 原始链接的转换，确保后续检测流程
能正确识别平台来源。

支持的短域名：
- t.cn       → Weibo（微博）
- xhslink.com → Xiaohongshu（小红书，detector.py 已有正则匹配）
- b23.tv     → Bilibili（B站，detector.py 已有正则匹配）
- iesdouyin.com → Douyin（抖音，detector.py 已有正则匹配）
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 已知的短域名列表
_SHORT_DOMAINS: list[str] = [
    "t.cn",
    "xhslink.com",
    "b23.tv",
    "iesdouyin.com",
]

# 需要 HTTP 解析的域名（不能仅靠正则匹配）
_RESOLVE_DOMAINS: set[str] = {"t.cn"}


def is_short_url(url: str) -> bool:
    """检查 URL 是否属于已知短域名。"""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        domain = parsed.hostname or parsed.netloc
        for short_domain in _SHORT_DOMAINS:
            if domain and (domain == short_domain or domain.endswith("." + short_domain)):
                return True
    except Exception:
        pass
    return False


def resolve_url(url: str, timeout: int = 10) -> str:
    """通过 HTTP 请求解析短链接，返回最终重定向后的 URL。

    仅对需要 HTTP 解析的域名发起请求（t.cn），
    其他短域名直接返回原 URL。
    """
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        domain = parsed.hostname or parsed.netloc
    except Exception:
        return url

    # 只有需要 HTTP 解析的域名才发起请求
    if domain not in _RESOLVE_DOMAINS and not any(
        domain.endswith("." + d) for d in _RESOLVE_DOMAINS
    ):
        return url

    try:
        import requests
        # 先尝试 HEAD（更快）
        resp = requests.head(
            url,
            allow_redirects=True,
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            },
        )
        if resp.status_code < 400 and resp.url != url:
            return resp.url

        # HEAD 可能不 redirect，尝试 GET
        resp = requests.get(
            url,
            allow_redirects=True,
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            },
        )
        if resp.status_code < 400 and resp.url != url:
            return resp.url
    except requests.RequestException as e:
        logger.debug("Failed to resolve short URL %s: %s", url, e)
    except ImportError:
        logger.debug("requests not available for URL resolution")
    except Exception as e:
        logger.debug("Unexpected error resolving URL %s: %s", url, e)

    return url


def normalize_url(url: str) -> str:
    """统一规范化 URL。

    1. 解析短链接（如 t.cn → weibo.com/xxx）
    2. 返回规范化后的 URL

    非短链接直接返回原 URL，不会有网络开销。
    """
    if not url:
        return url

    stripped = url.strip()
    # 确保有 scheme
    if not stripped.startswith(("http://", "https://")):
        stripped = "https://" + stripped

    if is_short_url(stripped):
        resolved = resolve_url(stripped)
        if resolved != stripped:
            logger.info("Normalized URL: %s -> %s", stripped[:80], resolved[:80])
            return resolved

    return stripped


__all__ = [
    "is_short_url",
    "resolve_url",
    "normalize_url",
]
