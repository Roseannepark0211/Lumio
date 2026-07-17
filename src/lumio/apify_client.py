"""Apify Actor wrapper for Instagram data extraction.

Replaces direct IG mobile API calls to avoid account risk control.
All IG data is fetched via Apify Actor proxy — no local IG API dependency.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone


log = logging.getLogger(__name__)


class ApifyIGClient:
    """Instagram data client backed by Apify Actor.

    Provides the same logical operations as the direct IG API functions
    (extract_post_info, fetch_profile_info, enumerate_profile_posts)
    but routes all data fetching through Apify's infrastructure.
    """

    def __init__(self, token: str, actor_id: str):
        from apify_client import ApifyClient
        self._client = ApifyClient(token)
        self._actor_id = actor_id

    # ------------------------------------------------------------------
    # Public API (mirrors downloader.py IG functions)
    # ------------------------------------------------------------------

    def test_connection(self) -> bool:
        """Verify that the Apify token is valid by fetching actor info."""
        try:
            self._client.actor(self._actor_id).get()
            return True
        except Exception:
            return False

    def extract_post_info(self, url: str) -> VideoInfo:
        """Extract single post/reel info. Replaces _ig_extract_info()."""
        run = self._client.actor(self._actor_id).call(run_input={
            "directUrls": [url],
            "resultsType": "posts",
            "resultsLimit": 1,
            "addParentData": False,
        })
        items = list(self._client.dataset(run["defaultDatasetId"]).iterate_items())
        if not items:
            raise ValueError(f"Apify returned no data for {url}")
        return self._to_video_info(items[0])

    def fetch_profile_info(self, username: str) -> dict:
        """Fetch profile metadata. Replaces fetch_profile_info()."""
        run = self._client.actor(self._actor_id).call(run_input={
            "directUrls": [f"https://www.instagram.com/{username}/"],
            "resultsType": "posts",
            "resultsLimit": 1,
            "addParentData": True,
        })
        items = list(self._client.dataset(run["defaultDatasetId"]).iterate_items())
        if not items:
            raise ValueError(f"Apify returned no data for @{username}")
        item = items[0]
        return {
            "username": item.get("ownerUsername", username),
            "full_name": item.get("ownerFullName", ""),
            "profile_pic_url": item.get("ownerProfilePicUrl"),
            "post_count": 0,  # Apify doesn't return this from posts query
            "user_id": str(item.get("ownerId", "")),
        }

    def enumerate_profile_posts(
        self,
        username: str,
        limit: int,
        callback=None,
        cancel_event: threading.Event | None = None,
    ) -> list[dict]:
        """Enumerate profile posts. Replaces enumerate_profile_posts().

        Returns list of Apify item dicts (not QueueTask — caller converts).
        Each dict is a raw Apify result, suitable for _post_to_queue_task() bridge.
        """
        run_input = {
            "directUrls": [f"https://www.instagram.com/{username}/"],
            "resultsType": "posts",
            "resultsLimit": limit,
        }
        # apify_client .call() blocks until the actor run finishes.
        # We run it in a thread to support cancel_event polling.
        result_holder: dict = {}
        error_holder: list = []

        def _run():
            try:
                result_holder["run"] = self._client.actor(self._actor_id).call(
                    run_input=run_input,
                )
            except Exception as e:
                error_holder.append(e)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

        # Poll for cancellation while waiting
        while thread.is_alive():
            if cancel_event and cancel_event.is_set():
                # Can't cancel an Apify run mid-flight, but we can stop waiting
                return []
            thread.join(timeout=0.5)

        if error_holder:
            raise error_holder[0]

        run = result_holder.get("run")
        if not run:
            return []

        # Iterate dataset, collect items, report progress
        all_items = []
        dataset = self._client.dataset(run["defaultDatasetId"])
        for idx, item in enumerate(dataset.iterate_items()):
            if cancel_event and cancel_event.is_set():
                break
            all_items.append(item)
            if callback:
                callback(len(all_items), limit)
        return all_items

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    def _to_video_info(self, item: dict) -> VideoInfo:
        """Convert Apify result item → Lumio VideoInfo.

        Filters out comment-related fields, only keeps media data.
        """
        from .downloader import VideoInfo
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
        from .downloader import MediaItem
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
        from .downloader import MediaItem
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

    def post_to_queue_task(self, item: dict, custom_name: str, output_dir, max_retries: int = 3, batch_id: str = ""):
        """Convert Apify result item → QueueTask. Replaces _post_to_queue_task() for API mode."""
        from .queue_manager import QueueTask

        short_code = item.get("shortCode", "")
        caption = (item.get("caption") or "").strip()
        title = caption[:80] if caption else "Instagram post"
        author = item.get("ownerUsername", "")
        post_time = self._parse_timestamp(item.get("timestamp"))
        thumb = item.get("displayUrl", "")
        url = item.get("url", f"https://www.instagram.com/p/{short_code}/")

        return QueueTask(
            url=url,
            output_dir=str(output_dir),
            custom_name=custom_name,
            batch_id=batch_id,
            title=title,
            platform="instagram",
            author=author,
            post_time=post_time,
            thumbnail_url=thumb,
            max_retries=max_retries,
        )


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
