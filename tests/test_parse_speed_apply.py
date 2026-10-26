"""Tests for the parse-speed application: cache fix + warm browser.

Cache fix (verification conclusions):
- Douyin video/note URLs share one canonical cache key by aweme_id,
  so www video page / ies share page / expanded short link forms hit
  the same entry (previously URL-keyed, form change = miss).
- Cached direct links are only trusted inside a link window
  (_DOUYIN_LINK_TTL); older file entries are treated as a miss
  instead of serving a possibly-403 stale link. Other platforms
  keep the previous 24h file TTL.

Warm browser (verification conclusions):
- A resident persistent context is reused across parses on the same
  thread / profile / launch args; a thread, profile or arg change
  closes the old context and rebuilds (Playwright sync objects are
  thread-bound, and one profile dir must not host two live contexts).
- Warmth comes from a successful parse session, not from launching
  alone; resource blocking is NOT part of the speed claim (measured
  no time-to-detail benefit), so no blocking is added here.
- Any warm setup/capture failure falls back to a cold launch inside
  the remaining budget; use_warm defaults to False so existing
  callers are unaffected unless they opt in.

No real browser is launched here: the browser function is driven
with fake Playwright objects, and the cache tests use tmp files.
"""
from __future__ import annotations

import json
import threading
import time

import pytest

from lumio.providers import cache as cache_mod
from lumio.providers.base import MediaInfo, MediaItem, Platform
from lumio.providers import dispatch as dispatch_mod
from lumio.providers.dispatch import _resolve_cache_key, resolve_via_providers
from lumio.providers import douyin_browser as browser_mod
from lumio.providers.douyin_browser import (
    close_warm_context,
    fetch_aweme_detail_via_browser,
)

VIDEO_ID = "7696555746569368666"
WWW_URL = f"https://www.douyin.com/video/{VIDEO_ID}"
IES_URL = f"https://www.iesdouyin.com/share/video/{VIDEO_ID}"
NOTE_URL = "https://www.douyin.com/note/1234567890123456789"
PROFILE_URL = "https://www.douyin.com/user/MS4wLjABAAAAXh3vzFZVQbYEwpeiEpGnSmr6PWxQOA1_z0y0g8wMiDk"
YOUTUBE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def _fake_info(url: str) -> MediaInfo:
    return MediaInfo(
        platform=Platform.DOUYIN,
        url=url,
        title="test video",
        author="author",
        media_items=[MediaItem(url="https://cdn.example.com/play.mp4")],
    )


# ========================================================================
# dispatch: canonical cache key
# ========================================================================


class TestCanonicalCacheKey:
    def test_www_and_ies_share_forms_share_key(self):
        key_www, ttl_www = _resolve_cache_key(WWW_URL)
        key_ies, ttl_ies = _resolve_cache_key(IES_URL)
        assert key_www == key_ies == f"douyin:aweme:{VIDEO_ID}"
        assert ttl_www == ttl_ies == dispatch_mod._DOUYIN_LINK_TTL

    def test_note_uses_aweme_key(self):
        key, ttl = _resolve_cache_key(NOTE_URL)
        assert key == "douyin:aweme:1234567890123456789"
        assert ttl == dispatch_mod._DOUYIN_LINK_TTL

    def test_profile_and_other_platforms_keep_url_key(self):
        key, ttl = _resolve_cache_key(PROFILE_URL)
        assert ttl is None
        assert "douyin:aweme:" not in key
        key_yt, ttl_yt = _resolve_cache_key(YOUTUBE_URL)
        assert ttl_yt is None
        assert "youtube.com" in key_yt


class TestDispatchFormIndependentHit:
    def test_second_form_hits_cache(self, monkeypatch):
        """www 形态解析后，ies 分享形态直接命中缓存，不再调 provider。"""
        store: dict[str, MediaInfo] = {}
        calls = []

        def fake_get(key, max_age=None):
            calls.append(("get", key, max_age))
            return store.get(key)

        def fake_set(key, info):
            calls.append(("set", key))
            store[key] = info

        monkeypatch.setattr(cache_mod, "get", fake_get)
        monkeypatch.setattr(cache_mod, "set", fake_set)

        class FakeProvider:
            def __init__(self):
                self.extract_calls = 0

            def extract_info(self, url):
                self.extract_calls += 1
                return _fake_info(url)

        provider = FakeProvider()
        monkeypatch.setattr(
            dispatch_mod, "get_provider", lambda url: provider)

        first = resolve_via_providers(WWW_URL)
        assert first is not None and provider.extract_calls == 1
        second = resolve_via_providers(IES_URL)
        assert second is not None and provider.extract_calls == 1
        get_keys = [c[1] for c in calls if c[0] == "get"]
        assert get_keys[0] == get_keys[1] == f"douyin:aweme:{VIDEO_ID}"
        assert calls[0][2] == dispatch_mod._DOUYIN_LINK_TTL


# ========================================================================
# cache: file-layer max_age
# ========================================================================


def _write_file_entry(cache_file, key_url, info, age_seconds):
    import hashlib

    key = hashlib.sha256(key_url.encode("utf-8")).hexdigest()
    data = {
        key: {
            "_cached_at": time.time() - age_seconds,
            "info": cache_mod._media_info_to_dict(info),
        }
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture()
def isolated_file_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(cache_mod, "_CACHE_FILE", tmp_path / "cache.json")
    monkeypatch.setattr(cache_mod, "_CACHE_DIR", tmp_path)
    cache_mod._cache.clear()
    yield tmp_path
    cache_mod._cache.clear()


class TestFileCacheMaxAge:
    def test_young_entry_with_max_age_hits(self, isolated_file_cache):
        _write_file_entry(
            isolated_file_cache / "cache.json",
            "https://example.com/v1", _fake_info("https://example.com/v1"),
            age_seconds=3600,
        )
        got = cache_mod.get_file_cached(
            "https://example.com/v1",
            max_age=dispatch_mod._DOUYIN_LINK_TTL,
        )
        assert got is not None and got.title == "test video"

    def test_old_entry_with_max_age_misses_and_evicts(self, isolated_file_cache):
        _write_file_entry(
            isolated_file_cache / "cache.json",
            "https://example.com/v2", _fake_info("https://example.com/v2"),
            age_seconds=dispatch_mod._DOUYIN_LINK_TTL + 3600,
        )
        got = cache_mod.get_file_cached(
            "https://example.com/v2",
            max_age=dispatch_mod._DOUYIN_LINK_TTL,
        )
        assert got is None
        data = json.loads(
            (isolated_file_cache / "cache.json").read_text(encoding="utf-8"))
        assert data == {}

    def test_old_entry_without_max_age_keeps_24h_default(self, isolated_file_cache):
        _write_file_entry(
            isolated_file_cache / "cache.json",
            "https://example.com/v3", _fake_info("https://example.com/v3"),
            age_seconds=dispatch_mod._DOUYIN_LINK_TTL + 3600,
        )
        got = cache_mod.get_file_cached("https://example.com/v3")
        assert got is not None and got.title == "test video"


# ========================================================================
# warm browser: fake Playwright
# ========================================================================

DETAIL_URL = (
    "https://www.douyin.com/aweme/v1/web/aweme/detail/?aid=6383"
)
DETAIL_PAYLOAD = {"aweme_detail": {"video": {"play_addr": {}}, "desc": "t"}}


class _FakeResponse:
    def __init__(self, url, status, payload):
        self.url = url
        self.status = status
        self._payload = payload

    def json(self):
        return self._payload


class _FakePage:
    def __init__(self, fire_detail=True):
        self.fire_detail = fire_detail
        self.gotos: list[str] = []
        self.closed = False

    def on(self, event, handler):
        if event == "response" and self.fire_detail:
            handler(_FakeResponse(DETAIL_URL, 200, DETAIL_PAYLOAD))

    def goto(self, url, wait_until=None, timeout=None):
        self.gotos.append(url)

    def wait_for_timeout(self, ms):
        pass

    def close(self):
        self.closed = True


class _FakeContext:
    def __init__(self, fire_detail=True):
        self.fire_detail = fire_detail
        self.pages: list[_FakePage] = []
        self.closed = False
        self.init_scripts: list[str] = []

    def new_page(self):
        if self.closed:
            raise RuntimeError("context closed")
        page = _FakePage(fire_detail=self.fire_detail)
        self.pages.append(page)
        return page

    def add_init_script(self, script):
        self.init_scripts.append(script)

    def close(self):
        self.closed = True


class _FakeChromium:
    def __init__(self, factory):
        self.factory = factory

    @property
    def executable_path(self):
        return "/nonexistent/chromium"

    def launch_persistent_context(self, user_data_dir, **kwargs):
        self.factory.launches.append((user_data_dir, kwargs))
        ctx = _FakeContext(fire_detail=self.factory.fire_detail)
        self.factory.contexts.append(ctx)
        return ctx


class _FakePW:
    def __init__(self, factory):
        self.factory = factory
        self.chromium = _FakeChromium(factory)
        self.stopped = False

    def stop(self):
        self.stopped = True


class _FakeFactory:
    """Callable factory: factory() -> object with .start() -> FakePW."""

    def __init__(self, fire_detail=True):
        self.fire_detail = fire_detail
        self.starts = 0
        self.launches: list = []
        self.contexts: list[_FakeContext] = []

    def __call__(self):
        return self

    def start(self):
        self.starts += 1
        return _FakePW(self)


@pytest.fixture()
def warm_env(monkeypatch, tmp_path):
    monkeypatch.setattr(
        browser_mod, "find_system_browser", lambda: None)
    close_warm_context()
    factory = _FakeFactory()
    yield factory, tmp_path / "profile"
    close_warm_context()


def _fetch_warm(factory, profile, video_id="123", timeout=30):
    return fetch_aweme_detail_via_browser(
        video_id, timeout=timeout, user_data_dir=profile,
        use_warm=True, _playwright_factory=factory)


class TestWarmBrowser:
    def test_second_parse_reuses_context(self, warm_env):
        factory, profile = warm_env
        detail1, _ = _fetch_warm(factory, profile, "111")
        assert detail1 is not None
        detail2, _ = _fetch_warm(factory, profile, "222")
        assert detail2 is not None
        assert factory.starts == 1
        assert len(factory.contexts) == 1
        ctx = factory.contexts[0]
        assert not ctx.closed
        assert len(ctx.pages) == 2
        assert all(p.closed for p in ctx.pages)
        assert ctx.init_scripts

    def test_thread_change_rebuilds_context(self, warm_env):
        factory, profile = warm_env
        detail, _ = _fetch_warm(factory, profile, "111")
        assert detail is not None
        old_ctx = factory.contexts[0]
        results: list = []

        def _in_other_thread():
            results.append(_fetch_warm(factory, profile, "222"))

        t = threading.Thread(target=_in_other_thread)
        t.start()
        t.join(timeout=30)
        assert not t.is_alive()
        assert results and results[0][0] is not None
        assert old_ctx.closed
        assert factory.starts == 2

    def test_broken_context_falls_back_to_cold(self, warm_env, monkeypatch):
        factory, profile = warm_env
        detail, _ = _fetch_warm(factory, profile, "111")
        assert detail is not None
        ctx = factory.contexts[0]
        ctx.close()  # simulate a dead resident context
        cold_calls = []

        def fake_cold(video_id, is_note, deadline, user_data_dir,
                      executable_path, chromium_args):
            cold_calls.append(video_id)
            return {"video": {}}, None

        monkeypatch.setattr(browser_mod, "_fetch_cold", fake_cold)
        detail2, _ = _fetch_warm(factory, profile, "222")
        assert detail2 == {"video": {}}
        assert cold_calls == ["222"]
        # warm state was dropped; next warm call relaunches
        assert factory.starts == 1

    def test_cold_path_does_not_touch_warm_state(self, warm_env, monkeypatch):
        factory, profile = warm_env
        cold_calls = []

        def fake_cold(video_id, is_note, deadline, user_data_dir,
                      executable_path, chromium_args):
            cold_calls.append(video_id)
            return {"video": {}}, None

        monkeypatch.setattr(browser_mod, "_fetch_cold", fake_cold)
        detail, _ = fetch_aweme_detail_via_browser(
            "111", timeout=30, user_data_dir=profile, use_warm=False)
        assert detail == {"video": {}}
        assert cold_calls == ["111"]
        assert factory.starts == 0

    def test_warm_timeout_returns_none_and_keeps_context(self, warm_env):
        factory, profile = warm_env
        factory.fire_detail = False
        started = time.monotonic()
        detail, filter_msg = _fetch_warm(factory, profile, "111", timeout=2)
        elapsed = time.monotonic() - started
        assert detail is None and filter_msg is None
        assert elapsed < 10
        assert not factory.contexts[0].closed
