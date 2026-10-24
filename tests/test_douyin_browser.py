"""Tests for Douyin browser-intercept fallback (douyin_browser.py)
and its wiring in DouyinProvider.extract_info (priority 3).

No real browser is launched here: the browser function is monkeypatched.
End-to-end browser verification is done manually against a live video
(see douyin-cap5 evidence in ~/workspace/rea-analysis/).
"""
from __future__ import annotations

import sys

from lumio.providers.base import Platform
from lumio.providers.douyin import DouyinProvider
from lumio.providers.douyin_browser import (
    extract_detail_from_payload,
    fetch_aweme_detail_via_browser,
    playwright_available,
)


_DETAIL_FIXTURE = {
    "desc": "测试视频",
    "author": {"nickname": "测试作者", "uid": "12345"},
    "create_time": 1700000000,
    "duration": 15000,
    "video": {
        "cover": {"url_list": ["https://example.com/cover.jpg"]},
        "origin_cover": {"url_list": ["https://example.com/origin.jpg"]},
        "bit_rate": [
            {
                "gear_name": "normal_1080_0",
                "bit_rate": 2000000,
                "code_type": "h264",
                "play_addr": {
                    "url_list": ["https://example.com/video.mp4"],
                    "width": 1080,
                    "height": 1920,
                    "data_size": 1000000,
                },
            },
        ],
    },
}

_FILTER_MSG = "因作品权限或已被删除，无法观看，去看看其他作品吧"


# ========================================================================
# extract_detail_from_payload - pure helper
# ========================================================================


class TestExtractDetailFromPayload:
    def test_detail_with_video(self):
        detail, msg = extract_detail_from_payload({"aweme_detail": _DETAIL_FIXTURE})
        assert detail is _DETAIL_FIXTURE
        assert msg is None

    def test_detail_with_images_note(self):
        note = {"images": [{"url_list": ["https://example.com/1.jpg"]}]}
        detail, msg = extract_detail_from_payload({"aweme_detail": note})
        assert detail is note
        assert msg is None

    def test_filter_detail(self):
        detail, msg = extract_detail_from_payload(
            {"aweme_detail": None, "filter_detail": {"aweme_id": "1", "detail_msg": _FILTER_MSG}}
        )
        assert detail is None
        assert msg == _FILTER_MSG

    def test_empty_payload(self):
        assert extract_detail_from_payload({"aweme_detail": None}) == (None, None)
        assert extract_detail_from_payload({}) == (None, None)
        assert extract_detail_from_payload(None) == (None, None)


# ========================================================================
# playwright detection / missing-dependency guard
# ========================================================================


class TestPlaywrightGuard:
    def test_available_matches_import(self):
        try:
            import playwright  # noqa: F401

            expected = True
        except ImportError:
            expected = False
        assert playwright_available() is expected

    def test_fetch_returns_empty_without_playwright(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "playwright", None)
        monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
        assert playwright_available() is False
        assert fetch_aweme_detail_via_browser("1234567890") == (None, None)


# ========================================================================
# DouyinProvider._parse_aweme_detail - note (images) branch reused by browser path
# ========================================================================


_NOTE_FIXTURE = {
    "desc": "图文测试",
    "author": {"nickname": "测试作者", "uid": "999"},
    "create_time": 1700000000,
    "images": [
        {"url_list": ["https://example.com/n1.jpg"], "width": 1080, "height": 1440},
        {"url_list": ["https://example.com/n2.jpg"], "width": 1080, "height": 1440},
    ],
    "video": {"cover": {"url_list": ["https://example.com/n1.jpg"]}},
}


class TestNoteBranchViaBrowserDetail:
    """浏览器拦截拿到 note 详情时，同一 _parse_aweme_detail 应出图片项。

    注意：这里验证的是解析分支；浏览器侧对 note 页是否发出 detail 请求，
    仍需一条真实图文链接实测（见 implementation notes）。
    """

    def test_note_detail_yields_image_items(self):
        provider = DouyinProvider()
        info = provider._parse_aweme_detail(
            _NOTE_FIXTURE, "https://www.douyin.com/note/1234567890", "1234567890"
        )
        assert info.title == "图文测试"
        assert len(info.media_items) == 2
        assert all(item.is_video is False for item in info.media_items)
        assert info.media_items[0].url == "https://example.com/n1.jpg"
        assert info.media_items[1].url == "https://example.com/n2.jpg"
        assert info.media_items[0].width == 1080
        assert info.thumbnail == "https://example.com/n1.jpg"


# ========================================================================
# DouyinProvider.extract_info - priority 3 wiring (mocked browser)
# ========================================================================


class TestBrowserFallbackWiring:
    def setup_method(self):
        self.provider = DouyinProvider()
        self.url = "https://www.douyin.com/video/1234567890"

    def _block_fast_paths(self, monkeypatch):
        monkeypatch.setattr(DouyinProvider, "_fetch_aweme_detail", lambda self, vid: None)

    def test_browser_detail_becomes_media_info(self, monkeypatch):
        import lumio.providers.douyin as douyin_mod

        self._block_fast_paths(monkeypatch)
        monkeypatch.setattr(
            douyin_mod, "fetch_aweme_detail_via_browser",
            lambda video_id, is_note=False: (_DETAIL_FIXTURE, None),
        )
        info = self.provider.extract_info(self.url)
        assert info.platform == Platform.DOUYIN
        assert info.media_items, "browser detail should yield media items"
        assert info.media_items[0].url == "https://example.com/video.mp4"
        assert info.media_items[0].is_video is True
        assert info.formats and info.formats[0].format_id == "1080p"
        assert info.title == "测试视频"

    def test_browser_filter_message(self, monkeypatch):
        import lumio.providers.douyin as douyin_mod

        self._block_fast_paths(monkeypatch)
        monkeypatch.setattr(
            douyin_mod, "fetch_aweme_detail_via_browser",
            lambda video_id, is_note=False: (None, _FILTER_MSG),
        )
        info = self.provider.extract_info(self.url)
        assert "不可看" in info.title
        assert _FILTER_MSG in info.description
        assert info.media_items == []

    def test_missing_playwright_hint_in_failure(self, monkeypatch):
        import lumio.providers.douyin as douyin_mod

        self._block_fast_paths(monkeypatch)
        monkeypatch.setattr(
            douyin_mod, "fetch_aweme_detail_via_browser", lambda video_id, is_note=False: (None, None)
        )
        monkeypatch.setattr(douyin_mod, "playwright_available", lambda: False)
        info = self.provider.extract_info(self.url)
        assert "解析失败" in info.title
        assert "lumio[browser]" in info.description

    def test_is_note_flag_passed_through(self, monkeypatch):
        import lumio.providers.douyin as douyin_mod

        self._block_fast_paths(monkeypatch)
        seen = {}

        def fake_fetch(video_id, is_note=False):
            seen["is_note"] = is_note
            return None, None

        monkeypatch.setattr(douyin_mod, "fetch_aweme_detail_via_browser", fake_fetch)
        self.provider.extract_info("https://www.douyin.com/note/1234567890")
        assert seen["is_note"] is True
        self.provider.extract_info("https://www.douyin.com/video/1234567890")
        assert seen["is_note"] is False
