"""Tests for the V4 Platform Layer (providers module).

Covers: detector, registry, dispatch.
"""

from lumio.providers.base import (
    BaseProvider,
    FormatOption,
    MediaInfo,
    MediaItem,
    Platform,
)
from lumio.providers.detector import detect_domestic
from lumio.providers.registry import (
    clear,
    get_all_platforms,
    get_provider,
    get_provider_for,
    is_registered,
    register,
)
from lumio.providers.dispatch import (
    media_info_to_video_info,
    resolve_via_providers,
)


# ========================================================================
# 1. detect_domestic — URL pattern matching
# ========================================================================


class TestDetectWeibo:
    def test_weibo_post(self):
        r = detect_domestic("https://weibo.com/1234567890/AbCdEfGhI")
        assert r is not None
        p, k = r
        assert p == Platform.WEIBO
        assert k == "post"

    def test_weibo_profile(self):
        r = detect_domestic("https://weibo.com/1234567890/")
        assert r is not None
        p, k = r
        assert p == Platform.WEIBO
        assert k == "profile"

    def test_weibo_mobile_status(self):
        r = detect_domestic("https://m.weibo.cn/status/AbCdEfGhI")
        assert r is not None
        p, k = r
        assert p == Platform.WEIBO
        assert k == "post"

    def test_weibo_mobile_profile(self):
        r = detect_domestic("https://m.weibo.cn/u/1234567890")
        assert r is not None
        p, k = r
        assert p == Platform.WEIBO
        assert k == "profile"

    def test_not_weibo(self):
        r = detect_domestic("https://example.com/something")
        assert r is None


class TestDetectXiaohongshu:
    def test_explore_post(self):
        r = detect_domestic("https://www.xiaohongshu.com/explore/abcdef1234567890")
        assert r is not None
        p, k = r
        assert p == Platform.XIAOHONGSHU
        assert k == "post"

    def test_user_profile(self):
        r = detect_domestic("https://www.xiaohongshu.com/user/profile/abcdef1234567890")
        assert r is not None
        p, k = r
        assert p == Platform.XIAOHONGSHU
        assert k == "profile"

    def test_xhslink_short(self):
        r = detect_domestic("https://xhslink.com/Abc123")
        assert r is not None
        p, k = r
        assert p == Platform.XIAOHONGSHU
        assert k == "post"

    def test_not_xiaohongshu(self):
        r = detect_domestic("https://example.com/explore/abc")
        assert r is None


class TestDetectBilibili:
    def test_bv_video(self):
        r = detect_domestic("https://www.bilibili.com/video/BV1GJ411x7y2")
        assert r is not None
        p, k = r
        assert p == Platform.BILIBILI
        assert k == "video"

    def test_av_video(self):
        r = detect_domestic("https://www.bilibili.com/video/av12345678")
        assert r is not None
        p, k = r
        assert p == Platform.BILIBILI
        assert k == "video"

    def test_b23_short(self):
        r = detect_domestic("https://b23.tv/BV1GJ411x7y2")
        assert r is not None
        p, k = r
        assert p == Platform.BILIBILI
        assert k == "video"

    def test_space_profile(self):
        r = detect_domestic("https://space.bilibili.com/12345678")
        assert r is not None
        p, k = r
        assert p == Platform.BILIBILI
        assert k == "profile"

    def test_not_bilibili(self):
        r = detect_domestic("https://example.com/video/BV123")
        assert r is None


class TestDetectDouyin:
    def test_douyin_video(self):
        r = detect_domestic("https://www.douyin.com/video/1234567890")
        assert r is not None
        p, k = r
        assert p == Platform.DOUYIN
        assert k == "video"

    def test_douyin_profile(self):
        r = detect_domestic("https://www.douyin.com/user/username.123")
        assert r is not None
        p, k = r
        assert p == Platform.DOUYIN
        assert k == "profile"

    def test_iesdouyin_short(self):
        r = detect_domestic("https://iesdouyin.com/share/video/1234567890")
        assert r is not None
        p, k = r
        assert p == Platform.DOUYIN
        assert k == "video"

    def test_not_douyin(self):
        r = detect_domestic("https://example.com/video/123")
        assert r is None


class TestDetectUnsupported:
    def test_youtube_returns_none(self):
        r = detect_domestic("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert r is None

    def test_instagram_returns_none(self):
        r = detect_domestic("https://www.instagram.com/p/ABC123/")
        assert r is None

    def test_x_returns_none(self):
        r = detect_domestic("https://x.com/user/status/123")
        assert r is None

    def test_garbage_returns_none(self):
        r = detect_domestic("not a url")
        assert r is None


# ========================================================================
# 2. Registry — register, get_provider, lifecycle
# ========================================================================


class _TestProvider(BaseProvider):
    """A minimal provider for testing the registry."""

    @property
    def platform(self) -> Platform:
        return Platform.WEIBO

    def match(self, url: str) -> bool:
        return "weibo.com" in url

    def extract_info(self, url: str) -> MediaInfo:
        return MediaInfo(
            platform=Platform.WEIBO,
            url=url,
            title="Test",
            author="test_author",
        )


class TestRegistry:
    def setup_method(self):
        clear()

    def test_register_returns_class(self):
        cls = register(_TestProvider)
        assert cls is _TestProvider

    def test_register_then_is_registered(self):
        register(_TestProvider)
        assert is_registered(Platform.WEIBO)

    def test_not_registered_before_register(self):
        assert not is_registered(Platform.WEIBO)
        assert not is_registered(Platform.BILIBILI)

    def test_get_provider_returns_instance(self):
        register(_TestProvider)
        provider = get_provider_for(Platform.WEIBO)
        assert provider is not None
        assert isinstance(provider, _TestProvider)

    def test_get_provider_for_unregistered(self):
        provider = get_provider_for(Platform.BILIBILI)
        assert provider is None

    def test_get_provider_by_url_matches(self):
        register(_TestProvider)
        provider = get_provider("https://weibo.com/12345/AbCdEf")
        assert provider is not None
        assert isinstance(provider, _TestProvider)

    def test_get_provider_by_url_no_match(self):
        register(_TestProvider)
        provider = get_provider("https://www.youtube.com/watch?v=xxx")
        assert provider is None

    def test_clear_removes_all(self):
        register(_TestProvider)
        assert is_registered(Platform.WEIBO)
        clear()
        assert not is_registered(Platform.WEIBO)

    def test_get_all_platforms_after_register(self):
        register(_TestProvider)
        platforms = get_all_platforms()
        assert Platform.WEIBO in platforms

    def test_get_all_platforms_after_clear(self):
        register(_TestProvider)
        clear()
        assert get_all_platforms() == []

    def test_register_non_provider_raises(self):
        import pytest as _pytest
        with _pytest.raises(TypeError):
            register(int)

    def test_register_twice_overwrites(self):
        register(_TestProvider)

        class _AnotherProvider(BaseProvider):
            @property
            def platform(self) -> Platform:
                return Platform.WEIBO

            def match(self, url):
                return False

            def extract_info(self, url):
                return MediaInfo(platform=Platform.WEIBO, url=url, title="", author="")

        register(_AnotherProvider)
        provider = get_provider_for(Platform.WEIBO)
        assert isinstance(provider, _AnotherProvider)


# ========================================================================
# 3. dispatch — MediaInfo → VideoInfo conversion
# ========================================================================


class TestDispatch:
    def test_media_info_to_video_info_basic(self):
        media = MediaInfo(
            platform=Platform.WEIBO,
            url="https://weibo.com/12345/AbCdEf",
            title="Test Post",
            author="test_user",
            post_time="2025-01-01 12:00:00",
            thumbnail="https://weibo.com/thumb.jpg",
            duration=60,
            media_items=[
                MediaItem(url="https://example.com/img1.jpg", is_video=False, index=0),
                MediaItem(url="https://example.com/vid1.mp4", is_video=True, index=1),
            ],
            formats=[
                FormatOption(format_id="best", label="Best quality", type="video"),
            ],
        )
    
        vi = media_info_to_video_info(media, media.url)
        assert vi.title == "Test Post"
        assert vi.url == "https://weibo.com/12345/AbCdEf"
        assert vi.thumbnail == "https://weibo.com/thumb.jpg"
        assert vi.duration == 60
        assert vi.platform == "weibo"
        assert vi.author == "test_user"
        assert vi.post_time == "2025-01-01 12:00:00"
        assert len(vi.items) == 2
        assert vi.items[0].url == "https://example.com/img1.jpg"
        assert vi.items[0].is_video is False
        assert vi.items[1].url == "https://example.com/vid1.mp4"
        assert vi.items[1].is_video is True
        assert len(vi.formats) == 1
        assert vi.formats[0]["format_id"] == "best"

    def test_media_info_empty_media_items(self):
        media = MediaInfo(
            platform=Platform.BILIBILI,
            url="https://bilibili.com/video/BV1xx",
            title="B站视频",
            author="up主",
        )
        vi = media_info_to_video_info(media, media.url)
        assert len(vi.items) == 0

    def test_media_info_none_thumbnail(self):
        media = MediaInfo(
            platform=Platform.DOUYIN,
            url="https://douyin.com/video/123",
            title="抖音",
            author="user",
            thumbnail="",
        )
        vi = media_info_to_video_info(media, media.url)
        assert vi.thumbnail is None

    def test_resolve_via_providers_no_match(self):
        clear()
        result = resolve_via_providers("https://weibo.com/12345/AbCdEf")
        assert result is None

    def test_resolve_via_providers_non_domestic(self):
        clear()
        result = resolve_via_providers("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert result is None

    def test_resolve_via_providers_with_registered_provider(self):
        clear()
        register(_TestProvider)
        result = resolve_via_providers("https://weibo.com/12345/AbCdEf")
        assert result is not None
        assert result.title == "Test"
        assert result.author == "test_author"
        assert result.platform == "weibo"


# ========================================================================
# 4. Platform enum properties
# ========================================================================


class TestPlatformEnum:
    def test_is_domestic_true(self):
        assert Platform.WEIBO.is_domestic
        assert Platform.XIAOHONGSHU.is_domestic
        assert Platform.BILIBILI.is_domestic
        assert Platform.DOUYIN.is_domestic
        assert Platform.KUAISHOU.is_domestic
        assert Platform.SHIPINHAO.is_domestic

    def test_is_domestic_false(self):
        assert not Platform.YOUTUBE.is_domestic
        assert not Platform.INSTAGRAM.is_domestic
        assert not Platform.X.is_domestic
        assert not Platform.UNSUPPORTED.is_domestic

    def test_enum_values(self):
        assert Platform.YOUTUBE.value == "youtube"
        assert Platform.WEIBO.value == "weibo"
        assert Platform.XIAOHONGSHU.value == "xiaohongshu"
        assert Platform.BILIBILI.value == "bilibili"
        assert Platform.DOUYIN.value == "douyin"
