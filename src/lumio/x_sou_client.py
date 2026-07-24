"""X-Sou API client for video search.

Provides search function for X-Sou (third-party X/Twitter video search).
Independent module, no dependencies on downloader internals.

下载逻辑由 downloader._direct_download_with_pause 统一处理：
- X-Sou 搜索结果含 video_url（video.twimg.com 直链）
- Home 页面入队时把 video_url 作为 direct_url，跳过 X GraphQL 流程
- 下载阶段走通用直链路径，自动支持系统代理访问被墙的 twimg.com
"""

from __future__ import annotations

import requests

_XSOU_BASE = "https://x-sou.com/api"


def x_sou_search(query: str, page: int = 1, limit: int = 20) -> dict:
    """Search X-Sou for videos. Returns {data: [...], total: int, page: int}.

    query can be:
    - keyword: "NASA 火箭"
    - @username: "@elonmusk" → auto-converts to "from:elonmusk"
    """
    q = query.strip()
    if q.startswith("@"):
        q = f"from:{q[1:]}"
    resp = requests.get(
        f"{_XSOU_BASE}/search",
        params={"q": q, "type": "video", "page": page, "limit": limit},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()
