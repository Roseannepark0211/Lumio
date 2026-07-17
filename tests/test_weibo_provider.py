"""Tests for WeiboProvider (Phase 2).

Covers: URL extraction, API parsing, media extraction, error handling.
"""

from __future__ import annotations

from unittest.mock import ANY, MagicMock, patch

from lumio.providers.base import MediaItem, MediaInfo, Platform
from lumio.providers.weibo import (
    WeiboProvider,
    _extract_images_from_pics,
    _extract_post_id,
    _extract_video,
    _get_thumbnail,
)


# ========================================================================
# _extract_post_id — URL parsing
# ========================================================================


class TestExtractPostId:
    def test_weibo_com_post(self):
        assert _extract_post_id("https://weibo.com/1234567890/AbCdEfGhI") == "AbCdEfGhI"

    def test_weibo_com_with_query(self):
        assert _extract_post_id("https://weibo.com/1234567890/AbCdEfGhI?type=comment") == "AbCdEfGhI"

    def test_m_weibo_cn_status(self):
        assert _extract_post_id("https://m.weibo.cn/status/AbCdEfGhI") == "AbCdEfGhI"

    def test_m_weibo_cn_status_with_query(self):
        assert _extract_post_id("https://m.weibo.cn/status/AbCdEfGhI?type=comment") == "AbCdEfGhI"

    def test_non_weibo_url(self):
        assert _extract_post_id("https://www.youtube.com/watch?v=xxx") is None

    def test_garbage_text(self):
        assert _extract_post_id("not a url at all") is None


# ========================================================================
# _extract_images_from_pics — pics array parsing
# ========================================================================


class TestExtractImagesFromPics:
    def test_single_image_with_large_url(self):
        pics = [{"large": {"url": "https://wx1.sinaimg.cn/large/001.jpg"}, "pid": "001"}]
        items = _extract_images_from_pics(pics)
        assert len(items) == 1
        assert items[0].url == "https://wx1.sinaimg.cn/large/001.jpg"
        assert items[0].is_video is False
        assert items[0].index == 0

    def test_multiple_images(self):
        pics = [
            {"large": {"url": "https://wx1.sinaimg.cn/large/001.jpg"}, "pid": "001"},
            {"large": {"url": "https://wx1.sinaimg.cn/large/002.jpg"}, "pid": "002"},
            {"large": {"url": "https://wx1.sinaimg.cn/large/003.jpg"}, "pid": "003"},
        ]
        items = _extract_images_from_pics(pics)
        assert len(items) == 3
        assert items[0].index == 0
        assert items[1].index == 1
        assert items[2].index == 2

    def test_missing_large_url_falls_back_to_pid(self):
        pics = [{"pid": "abc123"}]
        items = _extract_images_from_pics(pics)
        assert len(items) == 1
        assert items[0].url == "https://wx1.sinaimg.cn/large/abc123.jpg"

    def test_empty_pics(self):
        assert _extract_images_from_pics([]) == []


# ========================================================================
# _extract_video — page_info video extraction
# ========================================================================


class TestExtractVideo:
    def test_video_with_mp4_hd(self):
        page_info = {
            "type": "video",
            "media_info": {
                "mp4_hd_url": "https://example.com/video_hd.mp4",
                "mp4_url": "https://example.com/video.mp4",
            },
        }
        item = _extract_video(page_info)
        assert item is not None
        assert item.url == "https://example.com/video_hd.mp4"
        assert item.is_video is True
        assert item.index == 0

    def test_video_falls_back_to_mp4_url(self):
        page_info = {
            "type": "video",
            "media_info": {"mp4_url": "https://example.com/video.mp4"},
        }
        item = _extract_video(page_info)
        assert item is not None
        assert item.url == "https://example.com/video.mp4"

    def test_video_falls_back_to_stream_url(self):
        page_info = {
            "type": "video",
            "media_info": {"stream_url": "https://example.com/stream.mp4"},
        }
        item = _extract_video(page_info)
        assert item is not None
        assert item.url == "https://example.com/stream.mp4"

    def test_not_video_type_returns_none(self):
        page_info = {"type": "article", "media_info": {}}
        assert _extract_video(page_info) is None

    def test_no_url_returns_none(self):
        page_info = {"type": "video", "media_info": {}}
        assert _extract_video(page_info) is None


# ========================================================================
# _get_thumbnail — thumbnail extraction
# ========================================================================


class TestGetThumbnail:
    def test_from_page_pic(self):
        data = {"page_info": {"page_pic": {"url": "https://example.com/thumb.jpg"}}}
        assert _get_thumbnail(data) == "https://example.com/thumb.jpg"

    def test_from_first_pic(self):
        data = {
            "pics": [
                {"large": {"url": "https://wx1.sinaimg.cn/large/cover.jpg"}},
                {"large": {"url": "https://wx1.sinaimg.cn/large/img.jpg"}},
            ]
        }
        assert _get_thumbnail(data) == "https://wx1.sinaimg.cn/large/cover.jpg"

    def test_empty_data(self):
        assert _get_thumbnail({}) == ""


# ========================================================================
# WeiboProvider — match / extract_info
# ========================================================================


class TestWeiboProviderMatch:
    def setup_method(self):
        self.provider = WeiboProvider()

    def test_match_weibo_com(self):
        assert self.provider.match("https://weibo.com/1234567890/AbCdEfGhI") is True

    def test_match_m_weibo_cn(self):
        assert self.provider.match("https://m.weibo.cn/status/AbCdEfGhI") is True

    def test_not_match_youtube(self):
        assert self.provider.match("https://www.youtube.com/watch?v=xxx") is False

    def test_not_match_random(self):
        assert self.provider.match("not a url") is False


_MOCK_API_RESPONSE = {
    "ok": 1,
    "data": {
        "text_raw": "今天的天气真好啊",
        "user": {"screen_name": "测试用户", "id": 12345},
        "created_at": "2025-01-15 14:30:00",
        "pics": [
            {"large": {"url": "https://wx1.sinaimg.cn/large/001.jpg"}, "pid": "001"},
            {"large": {"url": "https://wx1.sinaimg.cn/large/002.jpg"}, "pid": "002"},
        ],
        "page_info": {
            "type": "video",
            "media_info": {"mp4_hd_url": "https://example.com/video.mp4"},
            "page_pic": {"url": "https://example.com/thumb.jpg"},
        },
    },
}

_MOCK_API_NO_MEDIA = {
    "ok": 1,
    "data": {
        "text_raw": "这是一条纯文字微博",
        "user": {"screen_name": "文字用户", "id": 67890},
        "created_at": "2025-02-01 10:00:00",
    },
}

_MOCK_API_RETWEETED = {
    "ok": 1,
    "data": {
        "text_raw": "转发微博",
        "user": {"screen_name": "转发用户", "id": 11111},
        "created_at": "2025-03-01 08:00:00",
        "retweeted_status": {
            "text_raw": "原文内容",
            "user": {"screen_name": "原文作者", "id": 22222},
            "created_at": "2025-02-28 12:00:00",
            "pics": [
                {"large": {"url": "https://wx1.sinaimg.cn/large/retweet.jpg"}, "pid": "retweet"},
            ],
        },
    },
}


class TestWeiboProviderExtractInfo:
    def setup_method(self):
        self.provider = WeiboProvider()

    def test_platform_property(self):
        assert self.provider.platform == Platform.WEIBO

    @patch("lumio.providers.weibo._fetch_json", return_value=_MOCK_API_RESPONSE)
    def test_basic_parse(self, mock_fetch):
        info = self.provider.extract_info("https://weibo.com/12345/AbCdEfGhI")
        assert info.platform == Platform.WEIBO
        assert info.author == "测试用户"
        assert info.title == "今天的天气真好啊"
        assert "2025-01-15" in info.post_time
        assert info.thumbnail == "https://example.com/thumb.jpg"

    @patch("lumio.providers.weibo._fetch_json", return_value=_MOCK_API_RESPONSE)
    def test_media_items_images_and_video(self, mock_fetch):
        info = self.provider.extract_info("https://weibo.com/12345/AbCdEfGhI")
        # 2 images + 1 video = 3 items
        assert len(info.media_items) == 3
        assert info.media_items[0].is_video is False
        assert info.media_items[1].is_video is False
        assert info.media_items[2].is_video is True
        assert info.media_items[2].index == 2

    @patch("lumio.providers.weibo._fetch_json", return_value=_MOCK_API_NO_MEDIA)
    def test_text_only_post(self, mock_fetch):
        info = self.provider.extract_info("https://weibo.com/12345/NoMedia")
        assert info.author == "文字用户"
        assert info.media_items == []

    @patch("lumio.providers.weibo._fetch_json", return_value=_MOCK_API_RETWEETED)
    def test_retweeted_media_fallback(self, mock_fetch):
        info = self.provider.extract_info("https://weibo.com/11111/Retweet")
        assert len(info.media_items) == 1
        assert info.media_items[0].url == "https://wx1.sinaimg.cn/large/retweet.jpg"
        assert info.media_items[0].is_video is False

    @patch("lumio.providers.weibo._fetch_json", return_value=None)
    def test_api_failure_returns_degraded_info(self, mock_fetch):
        info = self.provider.extract_info("https://weibo.com/12345/Fail")
        assert info.platform == Platform.WEIBO
        assert "解析失败" in info.title
        assert info.media_items == []

    def test_invalid_url_raises(self):
        try:
            self.provider.extract_info("https://example.com/not-weibo")
            assert False, "应该抛出 ValueError"
        except ValueError:
            pass

    @patch("lumio.providers.weibo._fetch_json", return_value={"ok": 0})
    def test_api_not_ok_returns_degraded(self, mock_fetch):
        info = self.provider.extract_info("https://weibo.com/12345/Fail2")
        assert "解析失败" in info.title
        assert info.media_items == []

    @patch("lumio.providers.weibo._fetch_json")
    def test_thumbnail_uses_first_pic_when_no_page_pic(self, mock_fetch):
        mock_fetch.return_value = {
            "ok": 1,
            "data": {
                "text_raw": "带图的微博",
                "user": {"screen_name": "用户"},
                "created_at": "2025-01-01",
                "pics": [
                    {"large": {"url": "https://wx1.sinaimg.cn/large/first.jpg"}, "pid": "first"},
                ],
            },
        }
        info = self.provider.extract_info("https://weibo.com/12345/Photo")
        assert info.thumbnail == "https://wx1.sinaimg.cn/large/first.jpg"


class TestWeiboProviderIntegration:
    """End-to-end: match → extract_info → MediaInfo fields."""

    @patch("lumio.providers.weibo._fetch_json", return_value=_MOCK_API_RESPONSE)
    def test_full_flow(self, mock_fetch):
        provider = WeiboProvider()
        url = "https://weibo.com/12345/AbCdEfGhI"

        assert provider.match(url) is True

        info = provider.extract_info(url)
        assert isinstance(info, MediaInfo)
        assert info.platform == Platform.WEIBO
        assert info.url == url
        assert info.title
        assert info.author
        assert len(info.media_items) > 0

        # Verify each media item has a URL
        for item in info.media_items:
            assert item.url.startswith("http")
            assert isinstance(item.is_video, bool)
