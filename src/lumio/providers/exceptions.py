"""Lumio V4 — 统一异常体系。

所有 Parser/Provider 异常继承自 ParserError，
上层（GUI/Downloader）统一捕获处理。
"""

from __future__ import annotations


class ParserError(Exception):
    """解析层基类异常。"""


class NetworkError(ParserError):
    """网络错误（连接超时/DNS 解析失败/SSL 错误等）。"""


class CookieExpired(ParserError):
    """Cookie 缺失/过期/权限不足。"""


class RateLimit(ParserError):
    """接口限流（429 Too Many Requests）。"""


class ContentRemoved(ParserError):
    """内容已删除/私密/不可用（404/403/410）。"""


class UnsupportedPlatform(ParserError):
    """URL 不匹配任何已注册平台。"""


class ParseError(ParserError):
    """API 返回了意外的数据结构。"""


class CacheError(ParserError):
    """缓存系统异常。"""
