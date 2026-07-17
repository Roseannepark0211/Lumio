"""Tests for BilibiliProvider (V4 Platform Layer).

Covers: URL parsing, API parsing, media extraction, error handling.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from lumio.providers.base import MediaItem, MediaInfo, Platform
from lumio.providers.bilibili import (
    BilibiliProvider,
    _extract_bv,
    _extract_av,
    _extract_aid,
)

# ========================================================================
# _extract_bv - BV ID extraction
# ========================================================================


class TestExtractBv:
    def test_bilibili_com_bv(self):
        assert _extract_bv("https://www.bilibili.com/video/BV1GJ411x7y2") == "BV1GJ411x7y2"

    def test_with_query(self):
        assert _extract_bv("https://www.bilibili.com/video/BV1GJ411x7y2?p=2") == "BV1GJ411x7y2"

    def test_non_bilibili(self):
        assert _extract_bv("https://www.youtube.com/watch?v=xxx") is None

    def test_av_url_returns_none(self):
        assert _extract_bv("https://www.bilibili.com/video/av12345678") is None


# ========================================================================
# _extract_av - AV ID extraction
# ========================================================================


class TestExtractAv:
    def test_bilibili_com_av(self):
        assert _extract_av("https://www.bilibili.com/video/av12345678") == "av12345678"

    def test_with_query(self):
        assert _extract_av("https://www.bilibili.com/video/av12345678?p=2") == "av12345678"

    def test_bv_url_returns_none(self):
        assert _extract_av("https://www.bilibili.com/video/BV1GJ411x7y2") is None


# ========================================================================
# _extract_aid - AID numeric extraction
# ========================================================================


class TestExtractAid:
    def test_extract_aid(self):
        assert _extract_aid("https://www.bilibili.com/video/av12345678") == "12345678"

    def test_bv_returns_none(self):
        assert _extract_aid("https://www.bilibili.com/video/BV1GJ411x7y2") is None


# ========================================================================
# BilibiliProvider - match()
# ========================================================================


class TestBilibiliProviderMatch:
    def setup_method(self):
        self.provider = BilibiliProvider()

    def test_match_bv(self):
        assert self.provider.match("https://www.bilibili.com/video/BV1GJ411x7y2") is True

    def test_match_av(self):
        assert self.provider.match("https://www.bilibili.com/video/av12345678") is True

    def test_match_b23(self):
        assert self.provider.match("https://b23.tv/BV1GJ411x7y2") is True

    def test_match_space(self):
        assert self.provider.match("https://space.bilibili.com/12345678") is True

    def test_not_match_youtube(self):
        assert self.provider.match("https://www.youtube.com/watch?v=xxx") is False

    def test_not_match_random(self):
        assert self.provider.match("not a bilibili url") is False


# ========================================================================
# BilibiliProvider - extract_info() with mocks
# ========================================================================

_MOCK_VIEW_API_RESPONSE = {
    "code": 0,
    "data": {
        "title": "Test Bilibili Video",
        "desc": "A test video description for unit testing",
        "owner": {"name": "up_owner", "mid": 12345678},
        "pic": "https://i0.hdslb.com/bfs/archive/cover.jpg",
        "aid": 123456,
        "cid": 789,
        "pubdate": 1700000000,
    },
}

_MOCK_PLAYER_API_RESPONSE = {
    "code": 0,
    "data": {
        "accept_description": ["1080P", "720P", "360P"],
        "accept_quality": [80, 64, 16],
        "durl": [
            {
                "url": "https://upos-sz-mirrorcos.bilivideo.com/video.mp4",
                "backup_url": ["https://backup.bilivideo.com/video.mp4"],
            }
        ],
    },
}

_MOCK_API_ERROR = {
    "code": -404,
    "message": "video not found",
}


class TestBilibiliProviderExtractInfo:
    def setup_method(self):
        self.provider = BilibiliProvider()

    def test_platform_property(self):
        assert self.provider.platform == Platform.BILIBILI

    @patch("lumio.providers.bilibili.NetworkClient")
    def test_basic_parse_bv(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_json.side_effect = [
            _MOCK_VIEW_API_RESPONSE,
            _MOCK_PLAYER_API_RESPONSE,
        ]

        info = self.provider.extract_info("https://www.bilibili.com/video/BV1GJ411x7y2")
        assert info.platform == Platform.BILIBILI
        assert info.title == "Test Bilibili Video"
        assert info.author == "up_owner"
        assert info.author_id == "12345678"
        assert info.thumbnail == "https://i0.hdslb.com/bfs/archive/cover.jpg"

    @patch("lumio.providers.bilibili.NetworkClient")
    def test_media_items_with_cover_and_video(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_json.side_effect = [
            _MOCK_VIEW_API_RESPONSE,
            _MOCK_PLAYER_API_RESPONSE,
        ]

        info = self.provider.extract_info("https://www.bilibili.com/video/BV1GJ411x7y2")
        # Cover image + video stream
        assert len(info.media_items) >= 1
        assert info.media_items[0].is_video is False  # cover image

    @patch("lumio.providers.bilibili.NetworkClient")
    def test_extract_info_av_url(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_json.side_effect = [
            _MOCK_VIEW_API_RESPONSE,
            _MOCK_PLAYER_API_RESPONSE,
        ]

        info = self.provider.extract_info("https://www.bilibili.com/video/av123456")
        assert info.title == "Test Bilibili Video"
        assert info.author == "up_owner"

    @patch("lumio.providers.bilibili.NetworkClient")
    def test_api_failure_returns_degraded(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_json.return_value = _MOCK_API_ERROR

        info = self.provider.extract_info("https://www.bilibili.com/video/BV1xx0000")
        assert "解析失败" in info.title
        assert info.media_items == []

    def test_profile_url_returns_degraded(self):
        info = self.provider.extract_info("https://space.bilibili.com/12345678")
        assert "个人主页" in info.title

    def test_non_matching_url_returns_degraded(self):
        info = self.provider.extract_info("https://www.youtube.com/watch?v=xxx")
        assert info.platform == Platform.BILIBILI
        assert "个人主页" in info.title


# ========================================================================
# Provider properties
# ========================================================================


class TestBilibiliProviderProperties:
    def setup_method(self):
        self.provider = BilibiliProvider()

    def test_classify_error_cookie(self):
        result = self.provider.classify_error("bili_jct expired")
        assert "cookie" in result.lower()

    def test_classify_error_rate_limit(self):
        result = self.provider.classify_error("412 precondition failed")
        assert "rate" in result.lower() or "limit" in result.lower()

    def test_classify_error_content_removed(self):
        result = self.provider.classify_error("video not found")
        assert "content" in result.lower() or "removed" in result.lower() or "not" in result.lower()

    def test_classify_error_general(self):
        from lumio.utils.error_types import ErrorCategory
        result = self.provider.classify_error(Exception("connection reset"))
        assert result == ErrorCategory.NETWORK.value

    def test_get_request_headers_contains_referer(self):
        headers = self.provider.get_request_headers()
        assert "Referer" in headers
        assert "bilibili" in headers.get("Referer", "")
