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

    # Normalise: ensure scheme present
    if not text.startswith(("http://", "https://")):
        text = "https://" + text

    for pattern, kind in _YOUTUBE_PATTERNS:
        if pattern.search(text):
            return ParsedURL(url=text, platform=Platform.YOUTUBE, kind=kind)

    for pattern, kind in _INSTAGRAM_PATTERNS:
        if pattern.search(text):
            return ParsedURL(url=text, platform=Platform.INSTAGRAM, kind=kind)

    for pattern, kind in _X_PATTERNS:
        if pattern.search(text):
            return ParsedURL(url=text, platform=Platform.X, kind=kind)

    return ParsedURL(url=text, platform=Platform.UNSUPPORTED, kind="unknown")
