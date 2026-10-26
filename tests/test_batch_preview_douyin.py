"""Tests for Douyin batch preview homepage recognition (preview_batch).

Regression coverage for the 5.0.1 real-device failure: a valid homepage
URL (short link or full share/user URL) must reach listing instead of
NOT_SUPPORTED, even when PC-UA short-link expansion misbehaves.

Rules under test (src/lumio/batch_download.py, Douyin branch):
1. A URL that already matches a profile pattern is used directly —
   no resolve step that could redirect a good link away (PC UA is
   known to be intercepted by Douyin anti-scraping; see
   _expand_share_url's docstring).
2. When normalize expansion does not yield a profile URL, a
   v.douyin.com short link gets a second expansion attempt with the
   provider's mobile-UA _expand_share_url (proven on real devices
   via the single-parse path).
3. When the expanded URL carries sec_uid only in the query string,
   the sec_uid fallback builds the canonical share/user URL.
4. Non-profile URLs still raise NOT_SUPPORTED.
"""
from __future__ import annotations

import pytest

from lumio.batch_download import (
    CODE_NOT_SUPPORTED,
    BatchPreviewError,
    preview_batch,
)
from lumio.providers import douyin as douyin_mod
from lumio.providers import url_normalizer as normalizer_mod

SHARE_USER_URL = (
    "https://www.iesdouyin.com/share/user/"
    "MS4wLjABAAAAPk5v6Pt4J6aeRMDpih7zkn64B1v7qqFgmFTMcxgIlRiCz8JZ9th7t-bYFBfWXgKy"
)
SHORT_URL = "https://v.douyin.com/MgNCNtk4L0A/"
QUERY_FORM_URL = (
    "https://www.iesdouyin.com/share/user/?sec_uid=QUERYSECUID123"
)


def _fake_enumerator_factory(seen):
    def fake_enumerator(url, limit):
        seen.append((url, limit))
        return [{
            "url": "https://www.douyin.com/video/111",
            "title": "t1",
            "thumbnail": "",
            "media_type": "video",
            "duration": 10,
            "post_time": "",
            "author": "A",
        }]

    return fake_enumerator


def test_full_share_user_url_skips_resolve(monkeypatch):
    """完整主页链接不再经过 resolve：即使 resolve 会重定向走也无影响。"""
    def _boom(url):
        raise AssertionError("resolve must not run for an already-profile URL")

    monkeypatch.setattr(normalizer_mod, "normalize_url", _boom)
    seen: list = []
    res = preview_batch(SHARE_USER_URL, douyin_enumerator=_fake_enumerator_factory(seen))
    assert res["platform"] == "douyin"
    assert len(res["works"]) == 1
    assert seen[0][0] == SHARE_USER_URL


def test_short_link_falls_back_to_mobile_ua_expansion(monkeypatch):
    """normalize 展开失败时，用移动端 UA 的 provider 展开再试一次。"""
    monkeypatch.setattr(normalizer_mod, "normalize_url", lambda url: url)
    monkeypatch.setattr(
        douyin_mod, "_expand_share_url", lambda url: SHARE_USER_URL)
    seen: list = []
    res = preview_batch(SHORT_URL, douyin_enumerator=_fake_enumerator_factory(seen))
    assert res["platform"] == "douyin"
    assert seen[0][0] == SHARE_USER_URL


def test_query_form_sec_uid_fallback(monkeypatch):
    """展开后 sec_uid 只在查询参数时，拼规范 share/user 链接再进列表。"""
    monkeypatch.setattr(normalizer_mod, "normalize_url", lambda url: QUERY_FORM_URL)
    monkeypatch.setattr(douyin_mod, "_expand_share_url", lambda url: None)
    seen: list = []
    res = preview_batch(SHORT_URL, douyin_enumerator=_fake_enumerator_factory(seen))
    assert res["platform"] == "douyin"
    assert seen[0][0] == (
        "https://www.iesdouyin.com/share/user/QUERYSECUID123"
    )


def test_raw_text_short_link_routes_when_normalize_expands(monkeypatch):
    """原文粘贴 + normalize 展开成功时仍走批量（3bc76ef 回归）。"""
    monkeypatch.setattr(normalizer_mod, "normalize_url", lambda url: SHARE_USER_URL)
    seen: list = []
    raw = f"长按复制此条消息，打开抖音搜索，查看TA的更多作品。 {SHORT_URL}"
    res = preview_batch(raw, douyin_enumerator=_fake_enumerator_factory(seen))
    assert res["platform"] == "douyin"
    assert seen[0][0] == SHARE_USER_URL


def test_non_profile_url_still_not_supported(monkeypatch):
    """非主页链接仍返回 NOT_SUPPORTED，不被兜底逻辑误收。"""
    monkeypatch.setattr(normalizer_mod, "normalize_url", lambda url: url)
    with pytest.raises(BatchPreviewError) as excinfo:
        preview_batch(
            "https://www.douyin.com/video/7696555746569368666",
            douyin_enumerator=_fake_enumerator_factory([]),
        )
    assert excinfo.value.code == CODE_NOT_SUPPORTED
