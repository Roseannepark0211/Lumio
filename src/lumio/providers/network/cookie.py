"""Cookie 管理器 — 平台 Cookie 统一管理。

支持从 Netscape 格式 cookie 文件加载，
按域名过滤、缓存、状态检测。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from ..base import Platform
from ...utils.config import load_config


class CookieManager:
    """平台 Cookie 统一管理器。

    用法:
        mgr = CookieManager()
        cookies = mgr.load_cookies(Platform.WEIBO)
        status = mgr.get_valid_status(Platform.WEIBO)
    """

    # 每个平台所需的 cookie 字段名
    _REQUIRED_NAMES: dict[Platform, list[str]] = {
        Platform.WEIBO: ["SUB", "SUBP"],
        Platform.XIAOHONGSHU: ["sessionid", "web_session"],
        Platform.BILIBILI: ["SESSDATA", "bili_jct"],
        Platform.DOUYIN: ["sessionid"],
        Platform.KUAISHOU: ["kuaishou.login"],
    }

    # 每个平台 cookie 应匹配的域名
    _DOMAIN_FILTER: dict[Platform, list[str]] = {
        Platform.WEIBO: ["weibo.cn", "weibo.com"],
        Platform.XIAOHONGSHU: ["xiaohongshu.com", "xhscdn.com"],
        Platform.BILIBILI: ["bilibili.com"],
        Platform.DOUYIN: ["douyin.com"],
        Platform.KUAISHOU: ["kuaishou.com"],
    }

    def __init__(self):
        self._cache: dict[Platform, dict[str, str]] = {}

    def _get_cookie_config_key(self, platform: Platform) -> str:
        """获取配置中的 cookie 文件路径键名。"""
        return f"{platform.value}_cookie_file"

    def _get_cookie_file(self, platform: Platform) -> Optional[Path]:
        """获取指定平台的 cookie 文件路径。"""
        cfg = load_config()
        key = self._get_cookie_config_key(platform)
        path_str = cfg.get(key, "") or cfg.get("cookie_file", "")
        if not path_str:
            return None
        p = Path(path_str)
        return p if p.exists() else None

    def load_cookies(self, platform: Platform) -> dict[str, str]:
        """从 Netscape 文件加载指定平台的 cookie。"""
        if platform in self._cache:
            return self._cache[platform]

        cookie_file = self._get_cookie_file(platform)
        if not cookie_file:
            return {}

        domains = self._DOMAIN_FILTER.get(platform, [])
        required = self._REQUIRED_NAMES.get(platform, [])

        cookies: dict[str, str] = {}
        try:
            for encoding in ("utf-8", "latin-1"):
                try:
                    f = open(cookie_file, encoding=encoding, errors="replace")
                    break
                except UnicodeDecodeError:
                    continue
            else:
                f = open(cookie_file, encoding="latin-1")

            with f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 7:
                        domain = parts[0]
                        if domains and not any(d in domain for d in domains):
                            continue
                        name = parts[5]
                        value = parts[6]
                        cookies[name] = value
        except Exception:
            return {}

        self._cache[platform] = cookies
        return cookies

    def get_valid_status(self, platform: Platform) -> str:
        """返回 'missing' / 'expired' / 'warning' / 'valid'。"""
        cookie_file = self._get_cookie_file(platform)
        if not cookie_file:
            return "missing"

        required = self._REQUIRED_NAMES.get(platform, [])
        try:
            text = cookie_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return "missing"

        has_any = any(name in text for name in required)
        if not has_any:
            return "missing"

        domains = self._DOMAIN_FILTER.get(platform, [])
        now = time.time()
        soonest_expiry = float("inf")

        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 5:
                domain = parts[0]
                if domains and not any(d in domain for d in domains):
                    continue
                name = parts[5] if len(parts) > 5 else ""
                if name not in required:
                    continue
                try:
                    expiry = float(parts[4])
                    if expiry > 0:
                        if expiry < now:
                            return "expired"
                        soonest_expiry = min(soonest_expiry, expiry)
                except (ValueError, IndexError):
                    pass

        if soonest_expiry < now + 7 * 24 * 3600:
            return "warning"
        return "valid"

    def get_by_domain(self, domain_substr: str) -> dict[str, str]:
        """从所有已加载的 cookie 中查找匹配域名的 cookies。"""
        all_cookies: dict[str, str] = {}
        for platform in Platform:
            if not platform.is_domestic:
                continue
            cookies = self.load_cookies(platform)
            for name, value in cookies.items():
                all_cookies[name] = value
        return all_cookies

    def invalidate_cache(self, platform: Optional[Platform] = None) -> None:
        """清除指定平台（或所有平台）的缓存。"""
        if platform:
            self._cache.pop(platform, None)
        else:
            self._cache.clear()
