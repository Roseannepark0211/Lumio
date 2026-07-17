"""Tests for DouyinProvider (V4 Platform Layer).

Covers: URL parsing, HTML parsing, media extraction, error handling.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from lumio.providers.base import MediaItem, MediaInfo, Platform
from lumio.providers.douyin import DouyinProvider, _extract_video_id

# ========================================================================
# _extract_video_id - URL parsing
# ========================================================================


class TestExtractVideoId:
    def test_douyin_com_video(self):
        assert _extract_video_id("https://www.douyin.com/video/1234567890") == "1234567890"

    def test_iesdouyin(self):
        assert _extract_video_id("https://iesdouyin.com/share/video/1234567890") == "1234567890"

    def test_non_douyin(self):
        assert _extract_video_id("https://www.youtube.com/watch?v=xxx") is None

    def test_garbage(self):
        assert _extract_video_id("not a url") is None


# ========================================================================
# DouyinProvider - match()
# ========================================================================


class TestDouyinProviderMatch:
    def setup_method(self):
        self.provider = DouyinProvider()

    def test_match_douyin_video(self):
        assert self.provider.match("https://www.douyin.com/video/1234567890") is True

    def test_match_douyin_profile(self):
        assert self.provider.match("https://www.douyin.com/user/username.123") is True

    def test_match_iesdouyin(self):
        assert self.provider.match("https://iesdouyin.com/share/video/1234567890") is True

    def test_match_share_url(self):
        assert self.provider.match("https://v.douyin.com/abc123") is True

    def test_not_match_youtube(self):
        assert self.provider.match("https://www.youtube.com/watch?v=xxx") is False

    def test_not_match_random(self):
        assert self.provider.match("not a douyin url") is False


# ========================================================================
# DouyinProvider - extract_info() with mocks
# ========================================================================

_MOCK_HTML_WITH_SSR = """
<html>
<head>
<meta property="og:title" content="Test Douyin Video" />
<meta property="og:image" content="https://www.douyin.com/thumb.jpg" />
</head>
<body>
<script>
window.__INITIAL_STATE__={"CursorData":{"videoData":{"desc":"Test Video Description","author":{"nickname":"test_author"},"cover":"https://www.douyin.com/cover.jpg","video":{"url_list":["https://www.douyin.com/video.mp4"]},"create_time":"1700000000"}}};
</script>
</body>
</html>
"""

_MOCK_HTML_OG_ONLY = """
<html>
<head>
<meta property="og:title" content="OG Title Video" />
<meta property="og:image" content="https://www.douyin.com/og_thumb.jpg" />
<meta property="og:video" content="https://www.douyin.com/og_video.mp4" />
</head>
<body>
<p>No SSR data available</p>
</body>
</html>
"""

_MOCK_HTML_EMPTY = """
<html>
<head><title>Empty Page</title></head>
<body></body>
</html>
"""


class TestDouyinProviderExtractInfo:
    def setup_method(self):
        self.provider = DouyinProvider()

    def test_platform_property(self):
        assert self.provider.platform == Platform.DOUYIN

    @patch("lumio.providers.douyin.NetworkClient")
    def test_basic_parse_via_html(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_html.return_value = _MOCK_HTML_WITH_SSR

        info = self.provider.extract_info("https://www.douyin.com/video/1234567890")
        assert info.platform == Platform.DOUYIN
        assert info.title == "Test Douyin Video"
        assert info.author == "test_author"
        assert "cover.jpg" in info.thumbnail

    @patch("lumio.providers.douyin.NetworkClient")
    def test_media_items_from_ssr(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_html.return_value = _MOCK_HTML_WITH_SSR

        info = self.provider.extract_info("https://www.douyin.com/video/1234567890")
        assert len(info.media_items) >= 1
        # Should have video URL
        assert any(item.is_video for item in info.media_items)

    @patch("lumio.providers.douyin.NetworkClient")
    def test_html_fallback_og_only(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_html.return_value = _MOCK_HTML_OG_ONLY

        info = self.provider.extract_info("https://www.douyin.com/video/9876543210")
        assert info.title == "OG Title Video"
        assert len(info.media_items) > 0

    @patch("lumio.providers.douyin.NetworkClient")
    def test_html_failure_returns_degraded(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_html.return_value = None

        info = self.provider.extract_info("https://www.douyin.com/video/fail123")
        assert "链接识别失败" in info.title

    @patch("lumio.providers.douyin.NetworkClient")
    def test_empty_html_returns_degraded(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_html.return_value = _MOCK_HTML_EMPTY

        info = self.provider.extract_info("https://www.douyin.com/video/8765432101")
        assert "解析失败" in info.title

    def test_profile_url_returns_degraded(self):
        info = self.provider.extract_info("https://www.douyin.com/user/testuser.123")
        assert "个人主页" in info.title

    def test_non_matching_url_returns_degraded(self):
        info = self.provider.extract_info("https://www.youtube.com/watch?v=xxx")
        assert info.platform == Platform.DOUYIN
        assert "链接识别失败" in info.title


# ========================================================================
# _parse_from_html - HTML parsing
# ========================================================================


class TestDouyinParseFromHtml:
    def setup_method(self):
        self.provider = DouyinProvider()

    def test_parse_with_ssr(self):
        items, title, author, thumb, post_time = self.provider._parse_from_html(_MOCK_HTML_WITH_SSR)
        assert len(items) >= 1
        assert "Test Douyin Video" in title
        assert author == "test_author"
        assert "cover.jpg" in thumb

    def test_parse_og_only(self):
        items, title, author, thumb, post_time = self.provider._parse_from_html(_MOCK_HTML_OG_ONLY)
        assert "OG Title Video" in title
        assert len(items) >= 1

    def test_parse_empty_html(self):
        items, title, author, thumb, post_time = self.provider._parse_from_html("")
        assert items == []
        assert title == ""


# ========================================================================
# Provider properties
# ========================================================================


class TestDouyinProviderProperties:
    def setup_method(self):
        self.provider = DouyinProvider()

    def test_classify_error_cookie(self):
        result = self.provider.classify_error("cookie expired")
        assert "cookie" in result.lower()

    def test_classify_error_rate_limit(self):
        result = self.provider.classify_error("429 Too Many Requests")
        assert "rate" in result.lower() or "limit" in result.lower()

    def test_classify_error_general(self):
        from lumio.utils.error_types import ErrorCategory
        result = self.provider.classify_error(Exception("connection timeout"))
        assert result == ErrorCategory.NETWORK.value

    def test_get_request_headers_contains_referer(self):
        headers = self.provider.get_request_headers()
        assert "Referer" in headers
        assert "douyin" in headers.get("Referer", "")
