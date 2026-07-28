"""Apify Actor wrapper for Instagram data extraction.

Replaces direct IG mobile API calls to avoid account risk control.
All IG data is fetched via Apify Actor proxy — no local IG API dependency.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone


log = logging.getLogger(__name__)


def _extract_dataset_id(run) -> str:
    """从 actor.call() 返回值中提取 defaultDatasetId。

    兼容两种 apify-client 版本：
    - 旧版（<=2.5）：返回 dict，用 run["defaultDatasetId"]
    - 新版（>=2.6）：返回 Run dataclass，用 run.default_dataset_id

    错误信息 "'Run' object is not subscriptable" 说明用户装的是新版。
    """
    if run is None:
        raise ValueError("Apify actor.call() returned None — run may have failed")
    # 优先用属性访问（新版 Run dataclass）
    ds = getattr(run, "default_dataset_id", None)
    if ds:
        return ds
    # 回退到 dict 访问（旧版）
    try:
        ds = run["defaultDatasetId"]
        if ds:
            return ds
    except (TypeError, KeyError):
        pass
    # 两者都失败，打印 run 对象帮助调试
    raise ValueError(
        f"Cannot extract defaultDatasetId from run object (type={type(run).__name__}). "
        f"Run attributes: {dir(run) if not isinstance(run, dict) else list(run.keys())}"
    )


class ApifyIGClient:
    """Instagram data client backed by Apify Actor.

    Routes all IG data fetching through Apify's infrastructure to avoid
    direct mobile API calls that risk account suspension.
    """

    def __init__(self, token: str, actor_id: str):
        from apify_client import ApifyClient
        self._client = ApifyClient(token)
        self._actor_id = actor_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def test_connection(self) -> bool:
        """Verify that the Apify token is valid by fetching actor info."""
        try:
            self._client.actor(self._actor_id).get()
            return True
        except Exception:
            return False

    def extract_post_info(self, url: str) -> VideoInfo:
        """Extract single post/reel info."""
        run = self._client.actor(self._actor_id).call(run_input={
            "directUrls": [url],
            "resultsType": "posts",
            "resultsLimit": 1,
            "addParentData": False,
        })
        dataset_id = _extract_dataset_id(run)
        items = list(self._client.dataset(dataset_id).iterate_items())
        if not items:
            raise ValueError(f"Apify returned no data for {url}")
        return self._to_video_info(items[0])

    # fetch_profile_info / enumerate_profile_posts 已删除（无任何调用点，完全死代码）
    # 历史用途：React 前端批量下载迁移被否决（commit f590fc5）后，profile/channel URL
    # 在 /api/parse-url 端点被显式拒绝，这两个方法无前端入口可触发。

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    def _to_video_info(self, item: dict) -> VideoInfo:
        """Convert Apify result item → Lumio VideoInfo.

        Filters out comment-related fields, only keeps media data.
        """
        from .utils.media_utils import VideoInfo
        items = self._extract_media_items(item)
        caption = (item.get("caption") or "").strip()
        title = caption[:80] if caption else "Instagram post"
        timestamp = self._parse_timestamp(item.get("timestamp"))

        return VideoInfo(
            title=title,
            url=item.get("url", ""),
            thumbnail=item.get("displayUrl"),
            duration=None,
            formats=[],
            platform="instagram",
            author=item.get("ownerUsername", ""),
            items=items,
            post_time=timestamp,
        )

    def _extract_media_items(self, item: dict) -> list[MediaItem]:
        """Extract MediaItem list from an Apify result item.

        Handles Sidecar (carousel), Image, and Video types.
        """
        from .utils.media_utils import MediaItem
        item_type = item.get("type", "")

        # Sidecar (carousel): use childPosts
        if item_type == "Sidecar" and item.get("childPosts"):
            return self._child_posts_to_media_items(item["childPosts"])

        # Single post: check for images list
        images = item.get("images") or []
        if images:
            media_items = []
            for idx, url in enumerate(images):
                if url:
                    media_items.append(MediaItem(url=url, is_video=False, index=idx))
            if media_items:
                return media_items

        # Single video
        video_url = item.get("videoUrl")
        if video_url:
            return [MediaItem(url=video_url, is_video=True, index=0)]

        # Fallback: displayUrl as single image
        display_url = item.get("displayUrl")
        if display_url:
            return [MediaItem(url=display_url, is_video=False, index=0)]

        return []

    @staticmethod
    def _child_posts_to_media_items(children: list[dict]) -> list[MediaItem]:
        """Convert Apify childPosts array → MediaItem list."""
        from .utils.media_utils import MediaItem
        media_items = []
        for idx, child in enumerate(children):
            child_type = child.get("type", "Image")
            video_url = child.get("videoUrl")
            if child_type == "Video" and video_url:
                media_items.append(MediaItem(url=video_url, is_video=True, index=idx))
            else:
                display_url = child.get("displayUrl")
                if display_url:
                    media_items.append(MediaItem(url=display_url, is_video=False, index=idx))
        return media_items

    @staticmethod
    def _parse_timestamp(ts: str | None) -> str:
        """Parse ISO 8601 timestamp → Lumio post_time format (YYYYMMDD_HHMMSS)."""
        if not ts:
            return ""
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.strftime("%Y%m%d_%H%M%S")
        except (ValueError, AttributeError):
            return ""

    # post_to_queue_task 已删除（无任何调用点，完全死代码）
    # 历史用途：批量下载路径专用，前端不迁移批量下载后无入口可触发。


# --- Module-level Apify client singleton ---

_apify_client_instance: ApifyIGClient | None = None


def get_apify_client() -> ApifyIGClient:
    """Get or create the Apify client singleton (lazy-init, reset on token change)."""
    global _apify_client_instance
    if _apify_client_instance is None:
        from .utils.config import get_apify_token, load_config
        token = get_apify_token()
        actor_id = load_config().get("apify_ig_actor", "")
        if not token or not actor_id:
            raise ValueError("Apify Token or Actor ID not configured; please fill in the settings page")
        _apify_client_instance = ApifyIGClient(token=token, actor_id=actor_id)
    return _apify_client_instance


def reset_apify_client() -> None:
    """Clear cached Apify client (called when token/actor config changes)."""
    global _apify_client_instance
    _apify_client_instance = None
