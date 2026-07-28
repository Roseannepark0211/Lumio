"""平台请求头配置。

每个平台的默认 User-Agent / Referer / Accept 等。
"""

from __future__ import annotations

from ...utils.ua import DEFAULT_UA
from ..base import Platform

# 通用 Chrome UA（跨平台，运行时按 sys.platform 生成对应平台 token）
# M5 修复：旧实现硬编码 Windows NT 10.0，macOS/Linux 运行时也伪装 Windows
CHROME_UA = DEFAULT_UA

DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": CHROME_UA,
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 各平台专用请求头
_PLATFORM_HEADERS: dict[Platform, dict[str, str]] = {
    Platform.WEIBO: {
        "User-Agent": CHROME_UA,
        "Referer": "https://weibo.com/",
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
    },
    Platform.XIAOHONGSHU: {
        "User-Agent": CHROME_UA,
        "Referer": "https://www.xiaohongshu.com/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
    Platform.BILIBILI: {
        "User-Agent": CHROME_UA,
        "Referer": "https://www.bilibili.com/",
        "Accept": "application/json, text/plain, */*",
    },
    Platform.DOUYIN: {
        "User-Agent": CHROME_UA,
        "Referer": "https://www.douyin.com/",
        "Accept": "application/json, text/plain, */*",
    },
    Platform.KUAISHOU: {
        "User-Agent": CHROME_UA,
        "Referer": "https://www.kuaishou.com/",
        "Accept": "application/json, text/plain, */*",
    },
}


def platform_headers(platform: Platform) -> dict[str, str]:
    """获取指定平台的默认请求头。"""
    base = dict(DEFAULT_HEADERS)
    extra = _PLATFORM_HEADERS.get(platform, {})
    base.update(extra)
    return base
