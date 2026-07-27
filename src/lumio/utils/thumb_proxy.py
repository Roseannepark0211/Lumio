"""缩略图代理下载 — 替代 qml_bridge.ThumbnailProvider 的下载逻辑。

api_fastapi.py 的 /api/thumb-proxy 端点用此模块下载远程缩略图，
附加 Referer/Cookie 处理 IG/sinaimg/twimg 等 CDN 鉴权要求，
返回原始字节给 FastAPI Response。

与 qml_bridge.ThumbnailProvider 差异：
- 不依赖 PySide6（QQuickImageProvider/QImage/QSize）
- 不做 QImage 缩放（前端 CSS/object-fit 处理）
- 不做本地缓存（浏览器侧通过 Cache-Control 长缓存）
"""

from __future__ import annotations

import requests


# 需要 Referer 的 CDN 域名
_NEEDS_REFERER_DOMAINS = (
    "instagram.",
    "fbcdn.net",
    "sinaimg.cn",
    "twimg.com",
    "x.com",
)


def _referer_for(url: str) -> str:
    """根据 URL 域名返回对应 Referer，无匹配返回空串。"""
    for d in _NEEDS_REFERER_DOMAINS:
        if d in url:
            if "instagram" in d or "fbcdn" in d:
                return "https://www.instagram.com/"
            if "sinaimg" in d:
                return "https://weibo.com/"
            if "twimg" in d or "x.com" in d:
                return "https://x.com/"
    return ""


def _load_cookie_header() -> str:
    """加载用户 cookie 文件内容作为 Cookie 请求头。无 cookie 返回空串。"""
    try:
        from .config import get_cookie_path
        cookie_path = get_cookie_path()
    except Exception:
        return ""
    if not cookie_path or not cookie_path.exists():
        return ""
    try:
        from ..providers.network.cookie import load_cookie_string
        return load_cookie_string(str(cookie_path))
    except Exception:
        return ""


def fetch_thumbnail_bytes(url: str, timeout: int = 15) -> tuple[bytes, str]:
    """下载远程缩略图，返回 (content_bytes, content_type)。

    - 附加 User-Agent + Referer（按域名匹配）+ Cookie（用户配置）
    - 用 requests.Session(trust_env=True) 走系统代理
    - 失败抛 requests.HTTPError / RequestException

    Returns:
        (content_bytes, content_type) — content_type 缺省 "image/jpeg"
    """
    headers = {"User-Agent": "Mozilla/5.0 Lumio/4.2"}
    ref = _referer_for(url)
    if ref:
        headers["Referer"] = ref
    cookie = _load_cookie_header()
    if cookie:
        headers["Cookie"] = cookie

    session = requests.Session()
    session.trust_env = True  # 读取系统代理（HTTP_PROXY/HTTPS_PROXY/Windows 注册表）
    r = session.get(url, headers=headers, timeout=timeout, stream=False)
    r.raise_for_status()
    content_type = r.headers.get("Content-Type", "image/jpeg")
    return r.content, content_type
