from __future__ import annotations

import time
from pathlib import Path

from ..utils.signal import QThread, Signal

from ..utils.config import get_cookie_path

# Seconds in 7 days
_WARNING_THRESHOLD = 7 * 24 * 3600


def _check_cookie_expiry(domains: list[str], required_names: list[str]) -> str:
    """Return one of: 'missing', 'expired', 'warning', 'valid'.

    修复：原版本用 `any(name in text for name in required_names)` 做全文文本搜索，
    会在用户只导入 IG cookie（包含 sessionid）时让抖音（要求 sessionid）/小红书
    （要求 sessionid 或 web_session）也误判为已导入。现在按 domain 过滤后再查 name。
    """
    cookie_path = get_cookie_path()
    if cookie_path is None:
        return "missing"

    try:
        text = cookie_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return "missing"

    now = time.time()
    soonest_expiry = float("inf")
    matched_any = False

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 6:
            continue
        domain = parts[0]
        # 必须先匹配 domain，再判断 name —— 避免跨平台误判
        if not any(d in domain for d in domains):
            continue
        name = parts[5]
        if name not in required_names:
            continue
        matched_any = True
        try:
            expiry = float(parts[4])
            if expiry > 0:
                if expiry < now:
                    return "expired"
                soonest_expiry = min(soonest_expiry, expiry)
        except (ValueError, IndexError):
            pass

    if not matched_any:
        return "missing"

    if soonest_expiry < now + _WARNING_THRESHOLD:
        return "warning"

    return "valid"


def check_ig_cookie_status() -> str:
    return _check_cookie_expiry(["instagram.com"], ["sessionid"])


def check_x_cookie_status() -> str:
    return _check_cookie_expiry(["x.com", "twitter.com"], ["auth_token", "ct0"])


def check_yt_cookie_status() -> str:
    return _check_cookie_expiry(["youtube.com"], ["LOGIN_INFO"])


def check_weibo_cookie_status() -> str:
    return _check_cookie_expiry(["weibo.cn", "weibo.com"], ["SUB", "SUBP"])

def check_douyin_cookie_status() -> str:
    return _check_cookie_expiry(["douyin.com"], ["sessionid"])


def check_xiaohongshu_cookie_status() -> str:
    return _check_cookie_expiry(["xiaohongshu.com", "xhslink.com"], ["sessionid", "web_session"])


def check_bilibili_cookie_status() -> str:
    return _check_cookie_expiry(["bilibili.com", "b23.tv"], ["SESSDATA", "bili_jct"])


def check_kuaishou_cookie_status() -> str:
    return _check_cookie_expiry(["kuaishou.com"], ["kuaishou.login"])



def check_all_cookies() -> dict[str, str]:
    """Return status for all platforms."""
    return {
        "instagram": check_ig_cookie_status(),
        "x": check_x_cookie_status(),
        "youtube": check_yt_cookie_status(),
        "weibo": check_weibo_cookie_status(),
        "douyin": check_douyin_cookie_status(),
        "xiaohongshu": check_xiaohongshu_cookie_status(),
        "bilibili": check_bilibili_cookie_status(),
        "kuaishou": check_kuaishou_cookie_status(),
    }


def check_apify_token_status() -> str:
    """Check if Apify API token is configured.
    Returns: 'missing' (no token) | 'valid' (token set).
    Actual connectivity validation is done via ApifyIGClient.test_connection().
    """
    from ..utils.config import get_apify_token
    return "valid" if get_apify_token() else "missing"


class CookieCheckWorker(QThread):
    """Background thread for non-blocking cookie status check."""

    result = Signal(str)

    def run(self):
        status = check_ig_cookie_status()
        self.result.emit(status)
