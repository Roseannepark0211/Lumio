from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..utils.config import get_cookie_path

# Seconds in 7 days
_WARNING_THRESHOLD = 7 * 24 * 3600


def _check_cookie_expiry(domains: list[str], required_names: list[str]) -> str:
    """Return one of: 'missing', 'expired', 'warning', 'valid'."""
    cookie_path = get_cookie_path()
    if cookie_path is None:
        return "missing"

    try:
        text = cookie_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return "missing"

    has_any = any(name in text for name in required_names)
    if not has_any:
        return "missing"

    now = time.time()
    soonest_expiry = float("inf")

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 5:
            domain = parts[0]
            if not any(d in domain for d in domains):
                continue
            name = parts[5] if len(parts) > 5 else ""
            if name not in required_names:
                continue
            try:
                expiry = float(parts[4])
                if expiry > 0:
                    if expiry < now:
                        return "expired"
                    soonest_expiry = min(soonest_expiry, expiry)
            except (ValueError, IndexError):
                pass

    if soonest_expiry < now + _WARNING_THRESHOLD:
        return "warning"

    return "valid"


def check_ig_cookie_status() -> str:
    return _check_cookie_expiry(["instagram.com"], ["sessionid"])


def check_x_cookie_status() -> str:
    return _check_cookie_expiry(["x.com", "twitter.com"], ["auth_token", "ct0"])


def check_yt_cookie_status() -> str:
    return _check_cookie_expiry(["youtube.com"], ["LOGIN_INFO"])


def check_all_cookies() -> dict[str, str]:
    """Return status for all platforms."""
    return {
        "instagram": check_ig_cookie_status(),
        "x": check_x_cookie_status(),
        "youtube": check_yt_cookie_status(),
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
