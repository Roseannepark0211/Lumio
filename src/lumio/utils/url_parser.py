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
            # For single video URLs, strip all tracking params and keep only v=
            # YouTube 地址栏 URL 含大量跟踪参数（feature=share, si=..., pp=...,
            # t=..., start=..., end=..., lc=... 等），这些参数会让 yt-dlp
            # 触发额外的 token 验证请求导致解析慢，部分参数还会触发限流。
            # 分享按钮复制的是 youtu.be/ID?si=... 短链，参数少所以快。
            # 修复：只保留 v= 参数（视频 ID），移除所有其他查询参数。
            clean = text
            if kind == "video":
                from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
                parsed_url = urlparse(text)
                qs = parse_qs(parsed_url.query)
                # 只保留 v=（视频 ID），移除 list=/si=/feature=/pp=/t=/start=/end= 等所有跟踪参数
                video_id = qs.get("v", [""])[0]
                if video_id:
                    clean = urlunparse(parsed_url._replace(query=f"v={video_id}"))
                else:
                    # youtu.be/ID 短链无 v= 参数，直接清空 query
                    clean = urlunparse(parsed_url._replace(query=""))
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


# ============================================================
# 从混合文本中提取纯 URL
# ============================================================

# URL 提取正则：匹配 http(s):// 开头直到遇到中文/空格/反引号/引号/全角字符为止
# 覆盖场景：
#   - 纯 URL：https://www.xiaohongshu.com/explore/xxx
#   - 微信分享混合文本：64 【描述】 😆 xxx 😆 `https://...`
#   - QQ 分享：描述 https://... 描述
#   - 多行文本：第一行 URL，第二行描述
_URL_EXTRACT_RE = re.compile(
    r"https?://[^\s\u4e00-\u9fff\u3000-\u303f\uff00-\uffef`'\"<>]+",
    re.IGNORECASE,
)


def extract_url_from_text(text: str) -> str:
    """从混合文本中提取纯 URL。

    处理用户从微信/QQ/小红书分享按钮复制的混合文本：
    - 中文描述 + 反引号包裹的 URL
    - 多行文本中的 URL
    - 纯 URL 直接返回

    Returns:
        提取出的 URL 字符串；无 URL 时返回空字符串。
    """
    if not text:
        return ""
    text = text.strip()
    # 快速路径：纯 URL（无中文/空格）
    if text.startswith(("http://", "https://")) and " " not in text and "\n" not in text:
        # 仍需检查无中文/全角字符
        if not re.search(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]", text):
            return text
    # 提取第一个匹配的 URL
    m = _URL_EXTRACT_RE.search(text)
    if m:
        url = m.group(0)
        # 去掉末尾可能粘连的标点（中文标点已被正则排除，但英文标点可能粘在末尾）
        url = url.rstrip(".,;:!?)")
        return url
    return ""
