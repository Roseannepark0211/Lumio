"""Tests for XiaohongshuProvider (V4 Platform Layer).

Covers: URL parsing, API parsing, media extraction, HTML fallback, error handling.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from lumio.providers.base import MediaItem, MediaInfo, MediaType, Platform
from lumio.providers.xiaohongshu import (
    XiaohongshuProvider,
    _extract_note_id,
    _is_profile_url,
    _parse_media_type,
    _extract_image_items,
    _extract_video_item,
)

# ========================================================================
# _extract_note_id - URL parsing
# ========================================================================


class TestExtractNoteId:
    def test_explore_post(self):
        assert _extract_note_id("https://www.xiaohongshu.com/explore/abcdef1234567890") == "abcdef1234567890"

    def test_with_query(self):
        assert _extract_note_id("https://www.xiaohongshu.com/explore/abcdef1234567890?xmt=1") == "abcdef1234567890"

    def test_non_xiaohongshu_url(self):
        assert _extract_note_id("https://www.youtube.com/watch?v=xxx") is None

    def test_garbage(self):
        assert _extract_note_id("not a url") is None


# ========================================================================
# _is_profile_url - profile detection
# ========================================================================


class TestIsProfileUrl:
    def test_profile_url(self):
        assert _is_profile_url("https://www.xiaohongshu.com/user/profile/abcdef1234567890") is True

    def test_shortlink(self):
        assert _is_profile_url("https://xhslink.com/Abc123") is True

    def test_explore_not_profile(self):
        assert _is_profile_url("https://www.xiaohongshu.com/explore/abcdef1234567890") is False


# ========================================================================
# _parse_media_type - type inference
# ========================================================================


class TestParseMediaType:
    def test_video_note(self):
        data = {"note": {"type": "video", "video": {"media": {}}}}
        assert _parse_media_type(data) == "video"

    def test_image_note(self):
        data = {"note": {"type": "image"}}
        assert _parse_media_type(data) == "image"

    def test_from_video_field(self):
        data = {"note": {"video": {"media": {"stream": {}}}}}
        assert _parse_media_type(data) == "video"

    def test_empty_data(self):
        assert _parse_media_type({}) == "image"


# ========================================================================
# _extract_image_items - image extraction
# ========================================================================


class TestExtractImageItems:
    def test_single_image(self):
        note = {
            "image_list": [
                {"url": "https://sns-img-hw.xhscdn.com/img1.jpg", "original": "https://sns-img-hw.xhscdn.com/orig1.jpg"},
            ]
        }
        items = _extract_image_items(note)
        assert len(items) == 1
        assert items[0].url == "https://sns-img-hw.xhscdn.com/orig1.jpg"
        assert items[0].is_video is False
        assert items[0].index == 0

    def test_multiple_images(self):
        note = {
            "image_list": [
                {"url": "https://sns-img-hw.xhscdn.com/img1.jpg", "original": "https://sns-img-hw.xhscdn.com/orig1.jpg"},
                {"url": "https://sns-img-hw.xhscdn.com/img2.jpg", "original": "https://sns-img-hw.xhscdn.com/orig2.jpg"},
            ]
        }
        items = _extract_image_items(note)
        assert len(items) == 2
        assert items[0].index == 0
        assert items[1].index == 1

    def test_uses_original_url(self):
        note = {
            "image_list": [
                {"url": "https://sns-img-hw.xhscdn.com/img1.jpg"},
            ]
        }
        items = _extract_image_items(note)
        assert items[0].url == "https://sns-img-hw.xhscdn.com/img1.jpg"

    def test_empty_list(self):
        assert _extract_image_items({}) == []


# ========================================================================
# _extract_video_item - video extraction
# ========================================================================


class TestExtractVideoItem:
    def test_video_with_master_url(self):
        note = {
            "video": {
                "media": {
                    "stream": {
                        "master_url": "https://sns-video-hw.xhscdn.com/master.m3u8",
                    }
                }
            }
        }
        item = _extract_video_item(note)
        assert item is not None
        assert item.url == "https://sns-video-hw.xhscdn.com/master.m3u8"
        assert item.is_video is True

    def test_video_with_resolution_list(self):
        note = {
            "video": {
                "media": {
                    "stream": {
                        "resolution_list": [
                            {"width": 1280, "height": 720, "url": "https://sns-video-hw.xhscdn.com/720p.mp4"},
                            {"width": 1920, "height": 1080, "url": "https://sns-video-hw.xhscdn.com/1080p.mp4"},
                        ]
                    }
                }
            }
        }
        item = _extract_video_item(note)
        assert item is not None
        assert "1080p" in item.url

    def test_no_video(self):
        assert _extract_video_item({}) is None


# ========================================================================
# XiaohongshuProvider - match()
# ========================================================================


class TestXiaohongshuProviderMatch:
    def setup_method(self):
        self.provider = XiaohongshuProvider()

    def test_match_explore(self):
        assert self.provider.match("https://www.xiaohongshu.com/explore/abcdef1234567890") is True

    def test_match_xhslink(self):
        assert self.provider.match("https://xhslink.com/Abc123") is True

    def test_match_profile(self):
        assert self.provider.match("https://www.xiaohongshu.com/user/profile/abcdef1234567890") is True

    def test_not_match_youtube(self):
        assert self.provider.match("https://www.youtube.com/watch?v=xxx") is False

    def test_not_match_random(self):
        assert self.provider.match("not a xiaohongshu url") is False


# ========================================================================
# XiaohongshuProvider - extract_info() with mocks
# ========================================================================

_MOCK_API_RESPONSE = {
    "success": True,
    "data": {
        "note": {
            "title": "Test Note Title",
            "desc": "Test note description content",
            "user": {"nickname": "test_user", "user_id": "user_12345"},
            "time": "1700000000",
            "type": "image",
            "image_list": [
                {"url": "https://sns-img-hw.xhscdn.com/img1.jpg", "original": "https://sns-img-hw.xhscdn.com/orig1.jpg"},
                {"url": "https://sns-img-hw.xhscdn.com/img2.jpg", "original": "https://sns-img-hw.xhscdn.com/orig2.jpg"},
            ],
        }
    },
}

_MOCK_API_VIDEO_RESPONSE = {
    "success": True,
    "data": {
        "note": {
            "title": "Test Video Note",
            "desc": "Video description here",
            "user": {"nickname": "video_user", "user_id": "user_67890"},
            "time": "1700000001",
            "type": "video",
            "image_list": [
                {"url": "https://sns-img-hw.xhscdn.com/cover.jpg", "original": "https://sns-img-hw.xhscdn.com/cover_orig.jpg"},
            ],
            "video": {
                "media": {
                    "stream": {
                        "master_url": "https://sns-video-hw.xhscdn.com/master.m3u8",
                    }
                }
            },
        }
    },
}

_MOCK_HTML_WITH_INIT_STATE = """
<html>
<head>
<meta property="og:title" content="HTML Fallback Note" />
<meta property="og:image" content="https://sns-img-hw.xhscdn.com/fallback_cover.jpg" />
</head>
<body>
<script>window.__INITIAL_STATE__={"note":{"title":"HTML Note","desc":"HTML desc","image_list":[{"url":"https://sns-img-hw.xhscdn.com/fallback.jpg"}],"video":{"media":{"stream":{"master_url":"https://sns-video-hw.xhscdn.com/fallback_video.mp4"}}}}};</script>
</body>
</html>
"""

_MOCK_HTML_WITH_OG_ONLY = """
<html>
<head>
<meta property="og:title" content="OG Only Note" />
<meta property="og:image" content="https://sns-img-hw.xhscdn.com/og_cover.jpg" />
</head>
<body>
<p>Some text content</p>
</body>
</html>
"""


class TestXiaohongshuProviderExtractInfo:
    def setup_method(self):
        self.provider = XiaohongshuProvider()

    def test_platform_property(self):
        assert self.provider.platform == Platform.XIAOHONGSHU

    @patch("lumio.providers.xiaohongshu.NetworkClient")
    def test_basic_parse_via_api(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_json.return_value = _MOCK_API_RESPONSE

        info = self.provider.extract_info("https://www.xiaohongshu.com/explore/abcdef1234567890")
        assert info.platform == Platform.XIAOHONGSHU
        assert info.title == "Test Note Title"
        assert info.author == "test_user"
        assert info.author_id == "user_12345"
        assert "1700000000" in info.post_time

    @patch("lumio.providers.xiaohongshu.NetworkClient")
    def test_media_items_from_api(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_json.return_value = _MOCK_API_RESPONSE

        info = self.provider.extract_info("https://www.xiaohongshu.com/explore/abcdef1234567890")
        assert len(info.media_items) == 2
        assert info.media_items[0].is_video is False
        assert info.media_items[1].is_video is False

    @patch("lumio.providers.xiaohongshu.NetworkClient")
    def test_video_parse_via_api(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_json.return_value = _MOCK_API_VIDEO_RESPONSE

        info = self.provider.extract_info("https://www.xiaohongshu.com/explore/abcdef1234567890")
        assert info.title == "Test Video Note"
        assert info.author == "video_user"
        assert len(info.media_items) >= 1
        # Should have at least 1 image + 1 video
        assert any(item.is_video for item in info.media_items)

    @patch("lumio.providers.xiaohongshu.NetworkClient")
    def test_api_failure_falls_back_to_html(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_json.return_value = None
        mock_client.get_html.return_value = _MOCK_HTML_WITH_INIT_STATE

        info = self.provider.extract_info("https://www.xiaohongshu.com/explore/fallbacknote")
        assert info.title == "HTML Fallback Note"
        assert len(info.media_items) > 0

    @patch("lumio.providers.xiaohongshu.NetworkClient")
    def test_api_and_html_both_fail(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_json.return_value = None
        mock_client.get_html.return_value = None

        info = self.provider.extract_info("https://www.xiaohongshu.com/explore/bothfail")
        assert "解析失败" in info.title
        assert info.media_items == []

    def test_profile_url_returns_degraded(self):
        info = self.provider.extract_info("https://www.xiaohongshu.com/user/profile/user_12345")
        assert "个人主页" in info.title

    def test_non_matching_url_returns_degraded(self):
        info = self.provider.extract_info("https://www.youtube.com/watch?v=xxx")
        assert info.platform == Platform.XIAOHONGSHU
        assert info.media_items == []


# ========================================================================
# _parse_from_html - HTML fallback
# ========================================================================


class TestXiaohongshuParseFromHtml:
    def setup_method(self):
        self.provider = XiaohongshuProvider()

    def test_parse_with_initial_state(self):
        items, title, thumb = self.provider._parse_from_html(_MOCK_HTML_WITH_INIT_STATE)
        assert len(items) > 0
        assert "HTML Fallback Note" in title

    def test_parse_with_og_only(self):
        items, title, thumb = self.provider._parse_from_html(_MOCK_HTML_WITH_OG_ONLY)
        assert "OG Only Note" in title
        assert "og_cover" in thumb

    def test_empty_html(self):
        items, title, thumb = self.provider._parse_from_html("")
        assert items == []
        assert title == ""
        assert thumb == ""


# ========================================================================
# Provider properties
# ========================================================================


class TestXiaohongshuProviderProperties:
    def setup_method(self):
        self.provider = XiaohongshuProvider()

    def test_classify_error_cookie(self):
        result = self.provider.classify_error("cookie expired")
        assert "cookie" in result.lower()

    def test_classify_error_general(self):
        from lumio.utils.error_types import ErrorCategory
        result = self.provider.classify_error(Exception("connection timeout"))
        assert result == ErrorCategory.NETWORK.value

    def test_get_request_headers_contains_referer(self):
        headers = self.provider.get_request_headers()
        assert "Referer" in headers
        assert "xiaohongshu" in headers.get("Referer", "")
