from lumio.utils.url_parser import Platform, parse_url


class TestYouTubeParsing:
    def test_watch_url(self):
        r = parse_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert r.platform == Platform.YOUTUBE
        assert r.kind == "video"

    def test_short_url(self):
        r = parse_url("https://youtu.be/dQw4w9WgXcQ")
        assert r.platform == Platform.YOUTUBE
        assert r.kind == "video"

    def test_shorts_url(self):
        r = parse_url("https://www.youtube.com/shorts/abc123DEF45")
        assert r.platform == Platform.YOUTUBE
        assert r.kind == "short"

    def test_playlist_url(self):
        r = parse_url("https://www.youtube.com/playlist?list=PLxxxxxxx")
        assert r.platform == Platform.YOUTUBE
        assert r.kind == "playlist"

    def test_channel_at_url(self):
        r = parse_url("https://www.youtube.com/@MrBeast")
        assert r.platform == Platform.YOUTUBE
        assert r.kind == "channel"
        assert r.tab == ""

    def test_no_scheme(self):
        r = parse_url("youtube.com/watch?v=dQw4w9WgXcQ")
        assert r.platform == Platform.YOUTUBE
        assert r.url.startswith("https://")

    def test_channel_videos_tab(self):
        r = parse_url("https://www.youtube.com/@mkbhd/videos")
        assert r.platform == Platform.YOUTUBE
        assert r.kind == "channel"
        assert r.tab == "videos"
        assert "@mkbhd" in r.url

    def test_channel_shorts_tab(self):
        r = parse_url("https://www.youtube.com/@mkbhd/shorts")
        assert r.platform == Platform.YOUTUBE
        assert r.kind == "channel"
        assert r.tab == "shorts"

    def test_strips_feature_param(self):
        """YouTube 地址栏 URL 含 feature=share 跟踪参数，应被移除"""
        r = parse_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=share")
        assert r.platform == Platform.YOUTUBE
        assert r.kind == "video"
        assert "feature=" not in r.url
        assert "v=dQw4w9WgXcQ" in r.url

    def test_strips_si_param(self):
        """YouTube 分享 URL 含 si= 跟踪参数，应被移除"""
        r = parse_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=ABC123def456")
        assert r.platform == Platform.YOUTUBE
        assert "si=" not in r.url
        assert "v=dQw4w9WgXcQ" in r.url

    def test_strips_all_tracking_params(self):
        """多跟踪参数（pp/si/feature/t）应全部移除，只保留 v="""
        r = parse_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ&pp=xxx&feature=share&si=ABC&t=120s")
        assert r.platform == Platform.YOUTUBE
        assert "pp=" not in r.url
        assert "feature=" not in r.url
        assert "si=" not in r.url
        assert "t=" not in r.url
        assert "v=dQw4w9WgXcQ" in r.url

    def test_strips_list_param(self):
        """list= 参数应被移除（避免 yt-dlp 当作播放列表处理）"""
        r = parse_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123abc")
        assert r.platform == Platform.YOUTUBE
        assert "list=" not in r.url
        assert "v=dQw4w9WgXcQ" in r.url

    def test_strips_short_link_si(self):
        """youtu.be 短链的 si= 参数应被移除"""
        r = parse_url("https://youtu.be/dQw4w9WgXcQ?si=ABC123")
        assert r.platform == Platform.YOUTUBE
        assert "si=" not in r.url
        assert "dQw4w9WgXcQ" in r.url


class TestInstagramParsing:
    def test_reel_url(self):
        r = parse_url("https://www.instagram.com/reel/ABC123xyz/")
        assert r.platform == Platform.INSTAGRAM
        assert r.kind == "reel"

    def test_post_url(self):
        r = parse_url("https://www.instagram.com/p/ABC123xyz/")
        assert r.platform == Platform.INSTAGRAM
        assert r.kind == "reel"

    def test_story_url(self):
        r = parse_url("https://www.instagram.com/stories/someuser/123456789/")
        assert r.platform == Platform.INSTAGRAM
        assert r.kind == "story"


class TestInstagramProfileParsing:
    def test_bare_at_username(self):
        r = parse_url("@natgeo")
        assert r.platform == Platform.INSTAGRAM
        assert r.kind == "profile"
        assert "natgeo" in r.url

    def test_bare_at_with_dots(self):
        r = parse_url("@user.name")
        assert r.platform == Platform.INSTAGRAM
        assert r.kind == "profile"
        assert "user.name" in r.url

    def test_bare_at_short(self):
        r = parse_url("@a")
        assert r.platform == Platform.INSTAGRAM
        assert r.kind == "profile"

    def test_profile_url(self):
        r = parse_url("instagram.com/natgeo")
        assert r.platform == Platform.INSTAGRAM
        assert r.kind == "profile"
        assert r.url.startswith("https://")

    def test_profile_url_with_params(self):
        r = parse_url("https://www.instagram.com/test_user_123?utm_source=ig_web_button_share_sheet&igsh=abc")
        assert r.platform == Platform.INSTAGRAM
        assert r.kind == "profile"
        assert "?" not in r.url
        assert "test_user_123" in r.url


class TestUnsupported:
    def test_random_url(self):
        r = parse_url("https://example.com/foo")
        assert r.platform == Platform.UNSUPPORTED

    def test_garbage(self):
        r = parse_url("not a url at all")
        assert r.platform == Platform.UNSUPPORTED


class TestXParsing:
    def test_x_tweet_url(self):
        r = parse_url("https://x.com/elonmusk/status/1234567890")
        assert r.platform == Platform.X
        assert r.kind == "tweet"

    def test_twitter_tweet_url(self):
        r = parse_url("https://twitter.com/user/status/1234567890")
        assert r.platform == Platform.X
        assert r.kind == "tweet"

    def test_x_i_status_url(self):
        r = parse_url("https://x.com/i/status/1234567890")
        assert r.platform == Platform.X
        assert r.kind == "tweet"

    def test_no_scheme(self):
        r = parse_url("x.com/user/status/1234567890")
        assert r.platform == Platform.X
        assert r.url.startswith("https://")
