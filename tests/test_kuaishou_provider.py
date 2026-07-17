"""Tests for KuaishouProvider (V4 Platform Layer).

Covers: URL parsing, HTML parsing, media extraction, error handling.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from lumio.providers.base import MediaItem, MediaInfo, Platform
from lumio.providers.kuaishou import KuaishouProvider, _extract_video_id

# ========================================================================
# _extract_video_id - URL parsing
# ========================================================================


class TestExtractVideoId:
    def test_kuaishou_photo(self):
        assert _extract_video_id("https://www.kuaishou.com/photo/abc123") == "abc123"

    def test_kuaishou_short_video(self):
        assert _extract_video_id("https://www.kuaishou.com/short-video/abc123def") == "abc123def"

    def test_kwai_domain(self):
        assert _extract_video_id("https://www.kwai.com/photo/xyz789") == "xyz789"

    def test_non_kuaishou(self):
        assert _extract_video_id("https://www.youtube.com/watch?v=xxx") is None

    def test_garbage(self):
        assert _extract_video_id("not a url") is None


# ========================================================================
# KuaishouProvider - match()
# ========================================================================


class TestKuaishouProviderMatch:
    def setup_method(self):
        self.provider = KuaishouProvider()

    def test_match_kuaishou_photo(self):
        assert self.provider.match("https://www.kuaishou.com/photo/abc123") is True

    def test_match_kuaishou_short_video(self):
        assert self.provider.match("https://www.kuaishou.com/short-video/abc123") is True

    def test_match_kwai(self):
        assert self.provider.match("https://www.kwai.com/photo/xyz789") is True

    def test_match_profile(self):
        assert self.provider.match("https://www.kuaishou.com/profile/12345") is True

    def test_not_match_youtube(self):
        assert self.provider.match("https://www.youtube.com/watch?v=xxx") is False

    def test_not_match_random(self):
        assert self.provider.match("not a kuaishou url") is False


# ========================================================================
# KuaishouProvider - extract_info() with mocks
# ========================================================================

_MOCK_HTML_WITH_SSR = """
<html>
<head>
<meta property="og:title" content="Test Kuaishou Video" />
<meta property="og:image" content="https://www.kuaishou.com/thumb.jpg" />
</head>
<body>
<script>
window.__INITIAL_STATE__={"photo":{"caption":"Test Video Caption","user":{"name":"test_author"},"coverUrl":"https://www.kuaishou.com/cover.jpg","videoUrl":"https://www.kuaishou.com/video.mp4","timestamp":"1700000000"}};
</script>
</body>
</html>
"""

_MOCK_HTML_OG_ONLY = """
<html>
<head>
<meta property="og:title" content="OG Kuaishou Video" />
<meta property="og:image" content="https://www.kuaishou.com/og_thumb.jpg" />
<meta property="og:video" content="https://www.kuaishou.com/og_video.mp4" />
</head>
<body>
<p>No SSR data</p>
</body>
</html>
"""

_MOCK_HTML_EMPTY = """
<html>
<head><title>Empty Page</title></head>
<body></body>
</html>
"""


class TestKuaishouProviderExtractInfo:
    def setup_method(self):
        self.provider = KuaishouProvider()

    def test_platform_property(self):
        assert self.provider.platform == Platform.KUAISHOU

    @patch("lumio.providers.kuaishou.NetworkClient")
    def test_basic_parse_via_html(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_html.return_value = _MOCK_HTML_WITH_SSR

        info = self.provider.extract_info("https://www.kuaishou.com/photo/abc123")
        assert info.platform == Platform.KUAISHOU
        assert info.title == "Test Kuaishou Video"
        assert info.author == "test_author"
        assert "cover.jpg" in info.thumbnail

    @patch("lumio.providers.kuaishou.NetworkClient")
    def test_media_items_from_ssr(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_html.return_value = _MOCK_HTML_WITH_SSR

        info = self.provider.extract_info("https://www.kuaishou.com/photo/abc123")
        assert len(info.media_items) >= 1
        # Should have video from videoUrl
        assert any(item.is_video for item in info.media_items)

    @patch("lumio.providers.kuaishou.NetworkClient")
    def test_html_fallback_og_only(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_html.return_value = _MOCK_HTML_OG_ONLY

        info = self.provider.extract_info("https://www.kuaishou.com/photo/ogonly123")
        assert info.title == "OG Kuaishou Video"
        assert len(info.media_items) > 0

    @patch("lumio.providers.kuaishou.NetworkClient")
    def test_html_failure_returns_degraded(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_html.return_value = None

        info = self.provider.extract_info("https://www.kuaishou.com/photo/fail123")
        assert "解析失败" in info.title

    @patch("lumio.providers.kuaishou.NetworkClient")
    def test_empty_html_returns_degraded(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_html.return_value = _MOCK_HTML_EMPTY

        info = self.provider.extract_info("https://www.kuaishou.com/photo/emptyhtml")
        assert "解析失败" in info.title

    def test_profile_url_returns_degraded(self):
        info = self.provider.extract_info("https://www.kuaishou.com/profile/12345")
        assert "个人主页" in info.title

    def test_non_matching_url_returns_degraded(self):
        info = self.provider.extract_info("https://www.youtube.com/watch?v=xxx")
        assert info.platform == Platform.KUAISHOU
        assert "链接识别失败" in info.title


# ========================================================================
# _parse_from_html - HTML parsing
# ========================================================================


class TestKuaishouParseFromHtml:
    def setup_method(self):
        self.provider = KuaishouProvider()

    def test_parse_with_ssr(self):
        items, title, author, thumb, post_time = self.provider._parse_from_html(_MOCK_HTML_WITH_SSR)
        assert len(items) >= 1
        assert "Test Kuaishou Video" in title
        assert author == "test_author"

    def test_parse_og_only(self):
        items, title, author, thumb, post_time = self.provider._parse_from_html(_MOCK_HTML_OG_ONLY)
        assert "OG Kuaishou Video" in title
        assert len(items) >= 1

    def test_parse_empty_html(self):
        items, title, author, thumb, post_time = self.provider._parse_from_html("")
        assert items == []
        assert title == ""


# ========================================================================
# Provider properties
# ========================================================================


class TestKuaishouProviderProperties:
    def setup_method(self):
        self.provider = KuaishouProvider()

    def test_classify_error_cookie(self):
        result = self.provider.classify_error("cookie expired")
        assert "cookie" in result.lower()

    def test_classify_error_rate_limit(self):
        result = self.provider.classify_error("429 rate limit")
        assert "rate" in result.lower() or "limit" in result.lower()

    def test_classify_error_general(self):
        from lumio.utils.error_types import ErrorCategory
        result = self.provider.classify_error(Exception("connection reset"))
        assert result == ErrorCategory.NETWORK.value

    def test_get_request_headers_contains_referer(self):
        headers = self.provider.get_request_headers()
        assert "Referer" in headers
        assert "kuaishou" in headers.get("Referer", "")
