"""Platform detection — URL 到平台的识别，用于国内平台。

先匹配国内平台 URL 模式，再回退到现有 url_parser。
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from .base import Platform

logger = logging.getLogger(__name__)

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
        # discovery/item/{note_id} 是 PC 分享链接路径（带 xsec_token 鉴权）
        (re.compile(r"xiaohongshu\.com/discovery/item/([a-f0-9]+)"), "post"),
        (re.compile(r"xiaohongshu\.com/user/profile/([a-f0-9]+)"), "profile"),
        # 移动端分享短链：xhslink.com（旧）/ xhslink.cn（新）
        # normalize_url 会先 302 展开成 xiaohongshu.com/discovery/item/...，这里是兜底
        (re.compile(r"xhslink\.(?:com|cn)/[a-zA-Z0-9]+"), "post"),
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
        # 图文帖（note）：与视频共用 aweme detail API，aweme_id 在路径里
        (re.compile(r"douyin\.com/note/(\d+)"), "post"),
        (re.compile(r"douyin\.com/user/([\w.]+)"), "profile"),
        (re.compile(r"iesdouyin\.com/[\w]+"), "video"),
        # v.douyin.com/{code}/ 移动端分享短链（normalize_url 会先 302 展开，这里是兜底）
        (re.compile(r"v\.douyin\.com/[\w]+"), "video"),
    ],
    Platform.KUAISHOU: [
        (re.compile(r"kuaishou\.com/short-video/([\w]+)"), "video"),
        (re.compile(r"kuaishou\.com/profile/(\d+)"), "profile"),
        (re.compile(r"v\.kuaishou\.com/[\w]+"), "video"),
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


# ========================================================================
# Profile 标识提取（Section 16）
# ========================================================================

_PROFILE_PATTERNS: dict[Platform, list[re.Pattern]] = {
    Platform.WEIBO: [
        re.compile(r"weibo\.com/(\d+)"),
        re.compile(r"m\.weibo\.cn/u/(\d+)"),
    ],
    Platform.XIAOHONGSHU: [
        re.compile(r"xiaohongshu\.com/user/profile/([a-f0-9]+)"),
    ],
    Platform.BILIBILI: [
        re.compile(r"bilibili\.com/space/(\d+)"),
        re.compile(r"space\.bilibili\.com/(\d+)"),
    ],
    Platform.DOUYIN: [
        re.compile(r"douyin\.com/user/([\w.]+)"),
    ],
    Platform.KUAISHOU: [
        re.compile(r"kuaishou\.com/profile/(\d+)"),
    ],
}


def extract_profile_identifier(url: str) -> Optional[str]:
    """从国内平台个人主页 URL 中提取用户标识。

    用于 GUI 批量下载对话框的信号参数。
    如果 URL 不匹配任何已知个人主页模式，返回 None。

    Examples:
        >>> extract_profile_identifier("https://weibo.com/1234567890")
        "1234567890"
        >>> extract_profile_identifier("https://m.weibo.cn/u/1234567890")
        "1234567890"
        >>> extract_profile_identifier("https://example.com/foo")
        None
    """
    for platform, patterns in _PROFILE_PATTERNS.items():
        for pat in patterns:
            m = pat.search(url)
            if m:
                identifier = m.group(1)
                logger.debug("Extracted profile identifier %s from %s", identifier, url[:60])
                return identifier
    return None


__all__ = [
    "detect_domestic",
    "extract_profile_identifier",
]
