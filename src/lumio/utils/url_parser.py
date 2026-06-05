import re
from enum import Enum
from dataclasses import dataclass


class Platform(Enum):
    YOUTUBE = "youtube"
    INSTAGRAM = "instagram"
    X = "x"
    UNSUPPORTED = "unsupported"


@dataclass
class ParsedURL:
    url: str
    platform: Platform
    kind: str  # "video", "short", "playlist", "channel", "post", "reel", "story"
    tab: str = ""  # YouTube channel tab: "videos", "shorts", "streams", "playlists", etc.

_YOUTUBE_PATTERNS = [
    (re.compile(r"(?:youtube\.com/watch\?.*v=|youtu\.be/)([\w-]{11})"), "video"),
    (re.compile(r"youtube\.com/shorts/([\w-]{11})"), "short"),
    (re.compile(r"youtube\.com/playlist\?.*list=([\w-]+)"), "playlist"),
    (re.compile(r"youtube\.com/(?:c/|channel/|@)([\w-]+)"), "channel"),
]

_INSTAGRAM_PATTERNS = [
    (re.compile(r"instagram\.com/(?:p|reel)/([\w-]+)"), "reel"),
    (re.compile(r"instagram\.com/stories/([\w.]+)/(\d+)"), "story"),
    (re.compile(r"instagram\.com/([\w.]+)/?"), "profile"),
]

_X_PATTERNS = [
    (re.compile(r"(?:x\.com|twitter\.com)/[\w.]+/status/\d+"), "tweet"),
    (re.compile(r"(?:x\.com|twitter\.com)/i/status/\d+"), "tweet"),
]


def parse_url(raw: str) -> ParsedURL:
    text = raw.strip()

    # Bare @username → Instagram profile URL
    at_match = re.match(r"^@([\w.]+)$", text)
    if at_match:
        text = f"instagram.com/{at_match.group(1)}"

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
            return ParsedURL(url=text, platform=Platform.YOUTUBE, kind=kind, tab=tab)

    for pattern, kind in _INSTAGRAM_PATTERNS:
        if pattern.search(text):
            # Strip query params and fragments to get clean path
            from urllib.parse import urlparse, urlunparse
            parsed_url = urlparse(text)
            clean = urlunparse(parsed_url._replace(query="", fragment=""))
            return ParsedURL(url=clean, platform=Platform.INSTAGRAM, kind=kind)

    for pattern, kind in _X_PATTERNS:
        if pattern.search(text):
            return ParsedURL(url=text, platform=Platform.X, kind=kind)

    return ParsedURL(url=text, platform=Platform.UNSUPPORTED, kind="unknown")
