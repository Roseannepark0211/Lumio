"""统一网络客户端 — 封装 requests.Session。

所有 Parser/Provider 统一使用此客户端，
自动注入 Cookie、设置请求头、处理重试。
"""

from __future__ import annotations

import logging
from typing import Optional, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .cookie import CookieManager
from .headers import platform_headers
from ..base import Platform

logger = logging.getLogger(__name__)


class NetworkClient:
    """统一网络客户端。

    用法:
        client = NetworkClient(Platform.WEIBO)
        data = client.get_json("https://m.weibo.cn/statuses/show?id=xxx")
        html = client.get_html("https://weibo.com/xxx")
        text = client.get_text("https://api.xxx.com/data")
    """

    def __init__(
        self,
        platform: Optional[Platform] = None,
        cookie_manager: Optional[CookieManager] = None,
        timeout: int = 15,
        max_retries: int = 3,
    ):
        self.platform = platform
        self.cookie_manager = cookie_manager or CookieManager()
        self.timeout = timeout

        self._session = requests.Session()

        # 配置请求重试
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

        # 设置默认请求头
        if platform:
            headers = platform_headers(platform)
            self._session.headers.update(headers)

        # 注入 Cookie
        if platform:
            cookies = self.cookie_manager.load_cookies(platform)
            if cookies:
                for name, value in cookies.items():
                    self._session.cookies.set(name, value)

    def get(self, url: str, **kwargs) -> requests.Response:
        """发送 GET 请求。"""
        kwargs.setdefault("timeout", self.timeout)
        return self._session.get(url, **kwargs)

    def post(self, url: str, data=None, json=None, **kwargs) -> requests.Response:
        """发送 POST 请求。"""
        kwargs.setdefault("timeout", self.timeout)
        return self._session.post(url, data=data, json=json, **kwargs)

    def get_json(self, url: str, **kwargs) -> Optional[Union[dict, list]]:
        """GET 请求并解析 JSON。"""
        kwargs.setdefault("timeout", self.timeout)
        try:
            resp = self._session.get(url, **kwargs)
            if resp.status_code == 429:
                logger.warning("Rate limited (429) for %s", url[:80])
                return None
            ct = resp.headers.get("Content-Type", "")
            if "text/html" in ct or "text/plain" in ct:
                text = resp.text[:500].lower()
                if "<html" in text or "sina visitor" in text or "passport" in text:
                    logger.warning("API returned HTML (visitor system) for %s", url[:80])
                    return None
            return resp.json()
        except Exception as e:
            logger.debug("get_json failed for %s: %s", url[:80], e)
            return None

    def get_html(self, url: str, **kwargs) -> Optional[str]:
        """GET 请求并返回 HTML 文本。"""
        kwargs.setdefault("timeout", self.timeout)
        try:
            resp = self._session.get(url, **kwargs)
            text = resp.text
            if "Sina Visitor" in text[:500] or "passport" in text[:300]:
                logger.warning("Page returned visitor system for %s", url[:80])
                return None
            return text
        except Exception as e:
            logger.debug("get_html failed for %s: %s", url[:80], e)
            return None

    def get_text(self, url: str, **kwargs) -> Optional[str]:
        """GET 请求返回纯文本。"""
        kwargs.setdefault("timeout", self.timeout)
        try:
            resp = self._session.get(url, **kwargs)
            return resp.text
        except Exception as e:
            logger.debug("get_text failed for %s: %s", url[:80], e)
            return None

    def close(self) -> None:
        """关闭会话。"""
        self._session.close()
