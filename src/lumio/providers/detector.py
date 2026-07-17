"""Platform detection — URL 到平台的识别，用于国内平台。

先匹配国内平台 URL 模式，再回退到现有 url_parser。
"""

from __future__ import annotations

import re
from typing import Optional

from .base import Platform

# 国内平台 URL 模式
# 格式: (编译后的正则, kind)
_DOMESTIC_PATTERNS: dict[Platform, list[tuple[re.Pattern, str]]] = {
    Platform.WEIBO: [
        (re.compile(r"weibo\.com/\d+/([a-zA-Z0-9]+)"), "post"),
        (re.compile(r"weibo\.com/(\d+)/?"), "profile"),
        (re.compile(r"m\.weibo\.cn/status/([a-zA-Z0-9]+)"), "post"),
        (re.compile(r"m\.weibo\.cn/u/(\d+)"), "profile"),
    ],
    Platform.XIAOHONGSHU: [
        (re.compile(r"xiaohongshu\.com/explore/([a-f0-9]+)"), "post"),
        (re.compile(r"xiaohongshu\.com/user/profile/([a-f0-9]+)"), "profile"),
        (re.compile(r"xhslink\.com/[a-zA-Z0-9]+"), "post"),
    ],
    Platform.BILIBILI: [
        (re.compile(r"bilibili\.com/video/(BV[\w]+)"), "video"),
        (re.compile(r"bilibili\.com/video/(av\d+)"), "video"),
        (re.compile(r"b23\.tv/[\w]+"), "video"),
        (re.compile(r"bilibili\.com/space/(\d+)"), "profile"),
        (re.compile(r"space\.bilibili\.com/(\d+)"), "profile"),
    ],
    Platform.DOUYIN: [
        (re.compile(r"douyin\.com/video/(\d+)"), "video"),
        (re.compile(r"douyin\.com/user/([\w.]+)"), "profile"),
        (re.compile(r"iesdouyin\.com/[\w]+"), "video"),
    ],
}


def detect_domestic(url: str) -> Optional[tuple[Platform, str]]:
    """识别国内平台 URL。

    Returns:
        (platform, kind) 如果匹配成功
        None 如果不匹配任何国内平台
    """
    for platform, patterns in _DOMESTIC_PATTERNS.items():
        for pattern, kind in patterns:
            if pattern.search(url):
                return platform, kind
    return None
