"""Tests for Douyin mobile homepage share links (share/user form).

Regression: a mobile homepage share (v.douyin.com short link) 302-expands
to www.iesdouyin.com/share/user/{sec_uid}, which no homepage pattern
used to cover (only douyin.com/user/), so single parse fell through to
"链接识别失败" and batch preview rejected it before expansion.

Network boundaries are mocked (normalize_url / _expand_share_url /
fetch_user_post_list_via_browser); these tests cover routing and sec_uid
extraction only, never live Douyin.
"""
from __future__ import annotations

import pytest

from lumio.batch_download import BatchPreviewError, preview_batch
from lumio.providers.base import Platform
from lumio.providers.detector import detect_domestic
from lumio.providers.douyin import DouyinProvider, _extract_profile_sec_uid

SEC_UID = "MS4wLjABAAAAXh3vzFZVQbYEwpeiEpGnSmr6PWxQOA1_z0y0g8wMiDk"
OTHER_UID = "MS4wLjABAAAAOtherSecUidForParamFallback"
SHARE_USER_URL = (
    "https://www.iesdouyin.com/share/user/" + SEC_UID
    + "?from_aid=6383&sec_uid=" + SEC_UID
)
SHARE_USER_PARAM_ONLY_URL = (
    "https://www.iesdouyin.com/share/user/?sec_uid=" + SEC_UID
)
SHARE_USER_PATH_WINS_URL = (
    "https://www.iesdouyin.com/share/user/" + SEC_UID
    + "?sec_uid=" + OTHER_UID
)
DOUYIN_USER_URL = "https://www.douyin.com/user/" + SEC_UID
SHORT_URL = "https://v.douyin.com/lutbWcKkEmk/"


# ========================================================================
# _extract_profile_sec_uid
# ========================================================================


class TestExtractProfileSecUid:
    def test_douyin_user_url(self):
        assert _extract_profile_sec_uid(DOUYIN_USER_URL) == SEC_UID

    def test_share_user_path(self):
        assert _extract_profile_sec_uid(SHARE_USER_URL) == SEC_UID

    def test_share_user_query_param_fallback(self):
        # 路径上没有 sec_uid 时退到 sec_uid 查询参数
        assert _extract_profile_sec_uid(SHARE_USER_PARAM_ONLY_URL) == SEC_UID

    def test_share_user_path_wins_over_param(self):
        assert _extract_profile_sec_uid(SHARE_USER_PATH_WINS_URL) == SEC_UID

    def test_video_url_returns_none(self):
        assert _extract_profile_sec_uid("https://www.douyin.com/video/1234567890") is None
        assert _extract_profile_sec_uid(
            "https://www.iesdouyin.com/share/video/1234567890") is None

    def test_garbage_returns_none(self):
        assert _extract_profile_sec_uid("not a url") is None
        assert _extract_profile_sec_uid("") is None


# ========================================================================
# detector: share/user -> profile, not video
# ========================================================================


class TestDetectorShareUser:
    def test_share_user_is_profile(self):
        assert detect_domestic(SHARE_USER_URL) == (Platform.DOUYIN, "profile")

    def test_share_video_still_video(self):
        assert detect_domestic(
            "https://www.iesdouyin.com/share/video/1234567890"
        ) == (Platform.DOUYIN, "video")


# ========================================================================
# DouyinProvider: match / extract_info / enumerate_profile_posts
# ========================================================================


class TestProviderShareUser:
    def setup_method(self):
        self.provider = DouyinProvider()

    def test_match_share_user(self):
        assert self.provider.match(SHARE_USER_URL) is True

    def test_extract_info_share_user_is_profile_placeholder(self):
        """展开后的 share/user 走个人主页分支（不触网，直接返回占位）。"""
        info = self.provider.extract_info(SHARE_USER_URL)
        assert "个人主页" in info.title
        assert info.author == SEC_UID
        assert info.media_items == []

    def test_extract_info_short_link_expands_to_profile(self, monkeypatch):
        """原始短链经移动端 UA 展开后同样走个人主页分支。"""
        monkeypatch.setattr(
            "lumio.providers.douyin._expand_share_url",
            lambda url: SHARE_USER_URL,
        )
        info = self.provider.extract_info(SHORT_URL)
        assert "个人主页" in info.title
        assert info.author == SEC_UID
        assert "链接识别失败" not in info.title

    def _enumerate_with_fake_fetch(self, monkeypatch, identifier):
        seen = []

        def fake_fetch(sec_uid, *args, **kwargs):
            seen.append(sec_uid)
            return ([], "", False, None)

        monkeypatch.setattr(
            "lumio.providers.douyin.fetch_user_post_list_via_browser",
            fake_fetch,
        )
        result = self.provider.enumerate_profile_posts(identifier)
        assert result == []
        return seen

    def test_enumerate_share_user_path(self, monkeypatch):
        seen = self._enumerate_with_fake_fetch(monkeypatch, SHARE_USER_URL)
        assert seen == [SEC_UID]

    def test_enumerate_share_user_param_fallback(self, monkeypatch):
        seen = self._enumerate_with_fake_fetch(
            monkeypatch, SHARE_USER_PARAM_ONLY_URL)
        assert seen == [SEC_UID]

    def test_enumerate_douyin_user_still_works(self, monkeypatch):
        seen = self._enumerate_with_fake_fetch(monkeypatch, DOUYIN_USER_URL)
        assert seen == [SEC_UID]


# ========================================================================
# preview_batch: share/user routes to the Douyin branch
# ========================================================================


def _douyin_enumerator(seen):
    def enumerator(identifier, limit):
        assert limit == 31  # page1 limit30 + 1 探针
        seen.append(identifier)
        return [
            {"url": "https://www.douyin.com/video/111", "title": "视频",
             "thumbnail": "https://th/v.jpg", "media_type": "video",
             "duration": 15, "post_time": "20261001", "author": "作者"},
        ]

    return enumerator


class TestPreviewBatchShareUser:
    def test_preview_routes_expanded_share_user_to_douyin(self, monkeypatch):
        # normalize_url 恒等 mock：避免 iesdouyin 短域名触发真实 302 解析
        monkeypatch.setattr(
            "lumio.providers.url_normalizer.normalize_url", lambda u: u)
        seen = []
        res = preview_batch(SHARE_USER_URL,
                            douyin_enumerator=_douyin_enumerator(seen))
        assert res["platform"] == "douyin"
        assert len(res["works"]) == 1
        assert res["works"][0]["type"] == "video"
        assert seen == [SHARE_USER_URL]

    def test_preview_expands_short_link_before_routing(self, monkeypatch):
        # 短链在判定前展开：展开后的 share/user 应路由到抖音分支
        monkeypatch.setattr(
            "lumio.providers.url_normalizer.normalize_url",
            lambda u: SHARE_USER_URL,
        )
        seen = []
        res = preview_batch(SHORT_URL,
                            douyin_enumerator=_douyin_enumerator(seen))
        assert res["platform"] == "douyin"
        assert len(res["works"]) == 1
        assert seen == [SHARE_USER_URL]


# ========================================================================
# preview_batch: raw share text is extracted before judging
# ========================================================================
# Regression: the frontend sends the raw pasted text (share password
# text with a short link inside) to /api/batch/preview. normalize_url
# cannot handle free text with Chinese, so without extraction the
# Douyin branch never matched and raw pastes fell back to single parse.


RAW_SHARE_TEXT = (
    "4- 长按复制此条消息，打开抖音搜索，查看TA的更多作品。 "
    + SHORT_URL + " 7@5.com :3pm"
)
RAW_LONG_USER_TEXT = (
    "看看TA的主页 " + DOUYIN_USER_URL + " 记得关注"
)


class TestPreviewBatchRawText:
    def test_preview_raw_share_text_routes_to_douyin(self, monkeypatch):
        # 提纯用真实 extract_url_from_text（纯正则，不触网）；
        # 展开 mock 成短链 -> share/user
        monkeypatch.setattr(
            "lumio.providers.url_normalizer.normalize_url",
            lambda u: SHARE_USER_URL if u == SHORT_URL else u,
        )
        seen = []
        res = preview_batch(RAW_SHARE_TEXT,
                            douyin_enumerator=_douyin_enumerator(seen))
        assert res["platform"] == "douyin"
        assert len(res["works"]) == 1
        assert seen == [SHARE_USER_URL]

    def test_preview_raw_text_with_long_user_url_routes(self, monkeypatch):
        monkeypatch.setattr(
            "lumio.providers.url_normalizer.normalize_url", lambda u: u)
        seen = []
        res = preview_batch(RAW_LONG_USER_TEXT,
                            douyin_enumerator=_douyin_enumerator(seen))
        assert res["platform"] == "douyin"
        assert seen == [DOUYIN_USER_URL]

    def test_preview_raw_text_without_url_still_not_supported(self, monkeypatch):
        monkeypatch.setattr(
            "lumio.providers.url_normalizer.normalize_url", lambda u: u)
        with pytest.raises(BatchPreviewError) as exc_info:
            preview_batch("长按复制此条消息，打开抖音搜索，查看TA的更多作品。",
                          douyin_enumerator=_douyin_enumerator([]))
        assert exc_info.value.code == "profile_not_supported"
