"""Tests for XiaohongshuProvider (V4 Platform Layer).

 Covers: URL parsing, match(), provider properties.
 媒体项提取相关测试已移除（_parse_media_type / _extract_image_items /
 _extract_video_item 在重构中合并为 _extract_media_items_from_note，
 详细覆盖见 test_integration.py 的真实网络测试）。
"""
from __future__ import annotations

from lumio.providers.base import Platform
from lumio.providers.xiaohongshu import (
    XiaohongshuProvider,
    _extract_note_id,
    _is_profile_url,
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
# XiaohongshuProvider - degraded paths
# ========================================================================


class TestXiaohongshuProviderDegraded:
    def setup_method(self):
        self.provider = XiaohongshuProvider()

    def test_profile_url_returns_degraded(self):
        """个人主页 URL 暂未接入批量下载，返回 degraded MediaInfo（非异常）。"""
        info = self.provider.extract_info("https://www.xiaohongshu.com/user/profile/user_12345")
        assert "个人主页" in info.title
        assert info.media_items == []

    def test_non_matching_url_returns_degraded(self):
        """非小红书 URL 走 detect_domestic 回退路径，此处直接调 extract_info 也应安全。"""
        info = self.provider.extract_info("https://www.youtube.com/watch?v=xxx")
        assert info.platform == Platform.XIAOHONGSHU
        assert info.media_items == []


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
