from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..utils.config import get_cookie_path


def check_ig_cookie_status() -> str:
    """Return one of: '未配置', '已失效', '已配置'."""
    cookie_path = get_cookie_path()
    if cookie_path is None:
        return "未配置"

    try:
        text = cookie_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return "未配置"

    if "sessionid" not in text:
        return "未配置"

    # Check sessionid expiry from Netscape cookie file
    now = time.time()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 5 and parts[0].endswith("instagram.com"):
            name = parts[5] if len(parts) > 5 else ""
            if name == "sessionid":
                try:
                    expiry = float(parts[4])
                    if expiry > 0 and expiry < now:
                        return "已失效"
                except (ValueError, IndexError):
                    pass

    return "已配置"


def check_x_cookie_status() -> str:
    """Return one of: '未配置', '已失效', '已配置'."""
    cookie_path = get_cookie_path()
    if cookie_path is None:
        return "未配置"

    try:
        text = cookie_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return "未配置"

    if "auth_token" not in text and "ct0" not in text:
        return "未配置"

    now = time.time()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 5 and ("x.com" in parts[0] or "twitter.com" in parts[0]):
            name = parts[5] if len(parts) > 5 else ""
            if name in ("auth_token", "ct0"):
                try:
                    expiry = float(parts[4])
                    if expiry > 0 and expiry < now:
                        return "已失效"
                except (ValueError, IndexError):
                    pass

    return "已配置"


class CookieCheckWorker(QThread):
    """Background thread for non-blocking cookie status check."""

    result = Signal(str)

    def run(self):
        status = check_ig_cookie_status()
        self.result.emit(status)
