from getvp.utils.url_parser import Platform, parse_url


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

    def test_no_scheme(self):
        r = parse_url("youtube.com/watch?v=dQw4w9WgXcQ")
        assert r.platform == Platform.YOUTUBE
        assert r.url.startswith("https://")


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


class TestUnsupported:
    def test_random_url(self):
        r = parse_url("https://example.com/foo")
        assert r.platform == Platform.UNSUPPORTED

    def test_garbage(self):
        r = parse_url("not a url at all")
        assert r.platform == Platform.UNSUPPORTED
