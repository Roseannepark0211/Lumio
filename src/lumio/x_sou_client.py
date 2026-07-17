"""X-Sou API client for video search.

Provides search and download functions for X-Sou (third-party X/Twitter video search).
Independent module, no dependencies on downloader internals.
"""

from __future__ import annotations

from pathlib import Path

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


def x_sou_download_video(video_url: str, dest_path: Path, cancel_event=None) -> bool:
    """Download a video from X-Sou direct URL. Returns True if successful."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Referer": "https://x.com/",
    }
    resp = requests.get(video_url, stream=True, timeout=30, headers=headers)
    try:
        if resp.status_code == 403:
            return False
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(8192):
                if cancel_event and cancel_event.is_set():
                    dest_path.unlink(missing_ok=True)
                    return False
                f.write(chunk)
                downloaded += len(chunk)
        return True
    finally:
        resp.close()
