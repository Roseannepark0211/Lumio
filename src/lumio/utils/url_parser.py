import re
from dataclasses import dataclass

from ..providers.base import Platform
from ..providers.url_normalizer import normalize_url


@dataclass
class ParsedURL:
    url: str
    platform: Platform
    kind: str  # "video", "short", "playlist", "channel", "post", "reel", "story"
    tab: str = ""  # YouTube channel tab: "videos", "shorts", "streams", "playlists", etc.

_YOUTUBE_PATTERNS = [
    (re.compile(r"youtube\.com/playlist\?.*list=([\w-]+)"), "playlist"),
    (re.compile(r"youtube\.com/(?:c/|channel/|@)([\w-]+)"), "channel"),
    (re.compile(r"youtube\.com/shorts/([\w-]{11})"), "short"),
    (re.compile(r"(?:m\.|music\.)?youtube\.com/(?:watch\?.*v=|embed/|v/|live/)([\w-]{11})"), "video"),
    (re.compile(r"youtu(?:be\.com|\.be)/(?:watch\?.*v=|embed/|v/)?([\w-]{11})"), "video"),
]

_INSTAGRAM_PATTERNS = [
    (re.compile(r"instagram\.com/(?:p|reel|tv)/([\w-]+)"), "reel"),
    (re.compile(r"instagram\.com/stories/([\w.]+)/(\d+)"), "story"),
    (re.compile(r"instagram\.com/([\w.]+)/?"), "profile"),
]

_X_PATTERNS = [
    (re.compile(r"(?:x\.com|twitter\.com)/[\w.]+/status/\d+"), "tweet"),
    (re.compile(r"(?:x\.com|twitter\.com)/i/status/\d+"), "tweet"),
    (re.compile(r"(?:pic\.)?(?:x\.com|twitter\.com)/[\w]+(?:\?.*)?$"), "profile"),
]


def parse_url(raw: str) -> ParsedURL:
    text = raw.strip()

    # Bare @username → Instagram profile URL
    # Must check BEFORE normalize_url to avoid "https://@username" mangling
    at_match = re.match(r"^@([\w.]+)$", text)
    if at_match:
        text = f"https://instagram.com/{at_match.group(1)}/"
        return ParsedURL(url=text, platform=Platform.INSTAGRAM, kind="profile")

    # V4.0: 解析短链接（t.cn → weibo.com 等）
    text = normalize_url(text)

    # Normalise: ensure scheme present
    if not text.startswith(("http://", "https://")):
        text = "https://" + text

    for pattern, kind in _YOUTUBE_PATTERNS:
        if pattern.search(text):
            tab = ""
            if kind == "channel":
                from urllib.parse import urlparse
                path = urlparse(text).path  # e.g. /@mkbhd/shorts
                segments = [s for s in path.split("/") if s]
                # segments[0] is username (e.g. "@mkbhd"), segments[1] is tab
                if len(segments) >= 2:
                    tab = segments[1]
            # For single video URLs, strip list= to avoid yt-dlp treating it as playlist
            clean = text
            if kind == "video":
                from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
                parsed_url = urlparse(text)
                qs = parse_qs(parsed_url.query)
                qs.pop("list", None)
                clean_query = urlencode(qs, doseq=True)
                clean = urlunparse(parsed_url._replace(query=clean_query))
            return ParsedURL(url=clean, platform=Platform.YOUTUBE, kind=kind, tab=tab)

    for pattern, kind in _INSTAGRAM_PATTERNS:
        if pattern.search(text):
            # Strip query params and fragments to get clean path
            from urllib.parse import urlparse, urlunparse
            parsed_url = urlparse(text)
            clean = urlunparse(parsed_url._replace(query="", fragment=""))
            return ParsedURL(url=clean, platform=Platform.INSTAGRAM, kind=kind)

    for pattern, kind in _X_PATTERNS:
        if pattern.search(text):
            clean = text
            if kind == "tweet":
                from urllib.parse import urlparse, urlunparse
                parsed_url = urlparse(text)
                clean = urlunparse(parsed_url._replace(query="", fragment=""))
            return ParsedURL(url=clean, platform=Platform.X, kind=kind)

    # Fallback: try domestic platforms via detect_domestic()
    from ..providers.detector import detect_domestic
    result = detect_domestic(text)
    if result is not None:
        platform, kind = result
        return ParsedURL(url=text, platform=platform, kind=kind)

    return ParsedURL(url=text, platform=Platform.UNSUPPORTED, kind="unknown")
