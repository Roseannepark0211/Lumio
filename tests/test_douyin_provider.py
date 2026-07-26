"""Tests for DouyinProvider (V4 Platform Layer).

Covers: URL parsing, match(), provider properties.
HTML 解析相关测试已移除（_parse_from_html 在重构中改名为
_parse_from_share_html 且签名变更，详细覆盖见 test_integration.py）。
"""
from __future__ import annotations

from lumio.providers.base import Platform
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
# DouyinProvider - degraded paths
# ========================================================================


class TestDouyinProviderDegraded:
    def setup_method(self):
        self.provider = DouyinProvider()

    def test_profile_url_returns_degraded(self):
        """个人主页 URL 暂未接入批量下载，返回 degraded MediaInfo（非异常）。"""
        info = self.provider.extract_info("https://www.douyin.com/user/testuser.123")
        assert "个人主页" in info.title
        assert info.media_items == []

    def test_non_matching_url_returns_degraded(self):
        """非抖音 URL 走 detect_domestic 回退路径，此处直接调 extract_info 也应安全。"""
        info = self.provider.extract_info("https://www.youtube.com/watch?v=xxx")
        assert info.platform == Platform.DOUYIN
        assert "链接识别失败" in info.title


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
