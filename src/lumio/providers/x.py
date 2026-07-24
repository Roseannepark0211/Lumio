"""Lumio V4 — X (Twitter) Provider。

迁移自 downloader.py 的 X GraphQL API 实现：
- 单条推文：图片走原图 URL，视频走 video_info.variants 中最高 bitrate
- 单视频推文：附加 yt-dlp formats（供格式选择）
- 下载：图片直链，视频走 yt-dlp（合并音视频）

URL 格式：
- x.com/{user}/status/{id}
- twitter.com/{user}/status/{id}
- t.co/{code} （短链，需先展开）
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from .base import BaseProvider, FormatOption, MediaInfo, MediaItem, MediaType, Platform
from .registry import register

logger = logging.getLogger(__name__)

_X_BEARER = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"

_X_GRAPHQL_TWEET = "2ICDjqPd81tulZcYrtpTuQ/TweetResultByRestId"
_X_GRAPHQL_USER = "xc8f1g7BYqr6VTzTbvNlGw/UserByScreenName"
_X_GRAPHQL_USER_TWEETS = "E3opETHurmVJflFsUBVuUQ/UserTweets"

_X_TWEET_FEATURES = {
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "tweetypie_unmention_optimization_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": False,
    "tweet_awards_web_tipping_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "responsive_web_media_download_video_enabled": False,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}

_X_USER_FEATURES = {
    "hidden_profile_subscriptions_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "subscriptions_verification_info_is_identity_verified_enabled": True,
    "subscriptions_verification_info_verified_since_enabled": True,
    "highlights_tweets_tab_ui_enabled": True,
    "responsive_web_twitter_article_notes_tab_enabled": True,
    "subscriptions_feature_can_gift_premium": True,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
}


def _x_api_session():
    """创建带 X cookies 和 Bearer headers 的 requests.Session。

    需要 cookie 文件中包含 auth_token + ct0（图片下载和 GraphQL 必需）。
    """
    import requests
    import http.cookiejar
    from pathlib import Path
    from ..utils.config import get_cookie_path

    session = requests.Session()
    session.trust_env = True
    cookie_path = get_cookie_path()
    ct0 = ""
    auth_token = ""
    if cookie_path and Path(cookie_path).exists():
        cj = http.cookiejar.MozillaCookieJar(str(cookie_path))
        cj.load(ignore_discard=True, ignore_expires=True)
        session.cookies = cj
        for c in cj:
            if c.name == "ct0" and ("x.com" in c.domain or "twitter.com" in c.domain):
                ct0 = c.value
            elif c.name == "auth_token" and ("x.com" in c.domain or "twitter.com" in c.domain):
                auth_token = c.value
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/131.0.0.0 Safari/537.36",
        "Authorization": f"Bearer {_X_BEARER}",
        "x-csrf-token": ct0,
    })
    return session, auth_token, ct0


def _x_tweet_id_from_url(url: str) -> str:
    """从 URL 提取推文 ID（x.com/user/status/123）。"""
    clean = url.split("?")[0].split("#")[0].rstrip("/")
    parts = clean.split("/")
    for i, p in enumerate(parts):
        if p == "status" and i + 1 < len(parts):
            return parts[i + 1]
    return parts[-1]


def _x_get_tweet_info(session, tweet_id: str) -> dict:
    """通过 GraphQL TweetResultByRestId 获取推文数据。"""
    variables = json.dumps({
        "tweetId": tweet_id,
        "withCommunity": False,
        "includePromotedContent": False,
        "withVoice": False,
    })
    features = json.dumps(_X_TWEET_FEATURES)
    fieldToggles = json.dumps({"withArticleRichContentState": False})
    resp = session.get(
        f"https://x.com/i/api/graphql/{_X_GRAPHQL_TWEET}",
        params={"variables": variables, "features": features, "fieldToggles": fieldToggles},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    result = data.get("data", {}).get("tweetResult", {}).get("result", {})
    if not result:
        raise ValueError("Tweet not found or not accessible")
    typename = result.get("__typename", "")
    if typename == "TweetUnavailable":
        reason = result.get("reason", "Unknown")
        raise ValueError(f"Tweet unavailable: {reason}")
    return result


def _x_extract_tweet_media(tweet_result: dict) -> list[MediaItem]:
    """从 GraphQL tweet_result 提取 MediaItem 列表。"""
    items: list[MediaItem] = []
    legacy = tweet_result.get("legacy", {})
    media_list = legacy.get("extended_entities", {}).get("media", [])
    for i, m in enumerate(media_list):
        mtype = m.get("type", "")
        if mtype == "photo":
            url = m.get("media_url_https", "")
            if url:
                url = url + "?format=jpg&name=orig"
                items.append(MediaItem(
                    url=url,
                    is_video=False,
                    index=i,
                    extension="jpg",
                    media_type=MediaType.IMAGE,
                ))
        elif mtype in ("video", "animated_gif"):
            variants = m.get("video_info", {}).get("variants", [])
            best_url = ""
            best_br = 0
            for v in variants:
                if v.get("content_type") == "video/mp4":
                    br = v.get("bitrate", 0)
                    if br > best_br:
                        best_br = br
                        best_url = v["url"]
            if not best_url and variants:
                best_url = variants[0].get("url", "")
            if best_url:
                items.append(MediaItem(
                    url=best_url,
                    is_video=True,
                    index=i,
                    extension="mp4",
                    media_type=MediaType.VIDEO,
                ))
    return items


def _yt_opts(cookie_path) -> dict:
    """构造 yt-dlp 选项（与 downloader._yt_opts 一致）。"""
    from ..utils.config import load_config
    try:
        from importlib.resources import files as _files
        ffmpeg_bin = str(_files("imageio_ffmpeg") / "ffmpeg-win-x86_64-v7.1.exe")
    except Exception:
        ffmpeg_bin = "ffmpeg"

    cfg = load_config()
    proxy = cfg.get("proxy", "")
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "no_color": True,
        "merge_output_format": "mp4",
        "ffmpeg_location": ffmpeg_bin,
        "continuedl": True,
        "keep_fragments": True,
    }
    if proxy:
        opts["proxy"] = proxy
    if cookie_path:
        opts["cookiefile"] = str(cookie_path)
    return opts


@register
class XProvider(BaseProvider):
    """X (Twitter) 内容解析 Provider。

    图片走原图直链，视频走 GraphQL 提取 + yt-dlp 格式选择（单视频推文）。
    """

    @property
    def platform(self) -> Platform:
        return Platform.X

    def match(self, url: str) -> bool:
        return (
            "x.com" in url
            or "twitter.com" in url
            or "t.co/" in url
        )

    def extract_info(self, url: str) -> MediaInfo:
        session, auth_token, ct0 = _x_api_session()
        tweet_id = _x_tweet_id_from_url(url)

        # 无关键 cookie 时跳过 GraphQL，直接走 yt-dlp 降级路径
        # （yt-dlp 内置 guest token，无需登录态即可解析视频推文）
        tweet_result = None
        if auth_token and ct0:
            try:
                tweet_result = _x_get_tweet_info(session, tweet_id)
            except Exception as e:
                logger.warning("X GraphQL 失败 (%s): %s", tweet_id, e)
                # 403/401 时降级到 yt-dlp
                tweet_result = None
        else:
            logger.info("X cookie 缺少 auth_token/ct0，跳过 GraphQL 走 yt-dlp 降级")

        # yt-dlp 降级路径：无需 cookie 即可解析视频推文
        if tweet_result is None:
            return self._extract_via_ytdlp(url, tweet_id)

        legacy = tweet_result.get("legacy", {})
        author = (
            legacy.get("user", {}).get("screen_name", "")
            or tweet_result.get("core", {}).get("user_results", {}).get("result", {}).get("legacy", {}).get("screen_name", "")
        )
        title = legacy.get("full_text", "")[:80] or "X post"

        post_time = ""
        created_at = legacy.get("created_at", "")
        if created_at:
            try:
                from datetime import datetime
                dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
                post_time = dt.strftime("%Y%m%d")
            except Exception:
                pass

        items = _x_extract_tweet_media(tweet_result)

        thumbnail = ""
        media_list = legacy.get("extended_entities", {}).get("media", [])
        if media_list:
            thumbnail = media_list[0].get("media_url_https", "")

        # 单视频推文：附加 yt-dlp formats 供格式选择
        formats: list[FormatOption] = []
        duration: Optional[int] = None
        has_video = any(item.is_video for item in items)
        if has_video and len(items) == 1:
            try:
                import yt_dlp
                from ..utils.config import get_cookie_path
                cookie = get_cookie_path()
                opts = _yt_opts(cookie)
                opts["skip_download"] = True
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl_info = ydl.extract_info(url, download=False)
                ydl_info = yt_dlp.YoutubeDL.sanitize_info(ydl_info)
                duration = ydl_info.get("duration")
                for f in ydl_info.get("formats", []):
                    fmt_id = f.get("format_id", "")
                    if not fmt_id:
                        continue
                    h = f.get("height") or 0
                    label = f"{h}p" if h else fmt_id
                    formats.append(FormatOption(
                        format_id=fmt_id,
                        label=label,
                        type="video",
                        ext=f.get("ext", "mp4"),
                        width=f.get("width") or 0,
                        height=h,
                    ))
            except Exception as e:
                logger.warning("X yt-dlp 格式提取失败: %s", e)

        return MediaInfo(
            platform=Platform.X,
            url=url,
            title=title,
            author=author,
            post_time=post_time,
            thumbnail=thumbnail,
            duration=duration,
            media_items=items,
            formats=formats,
        )

    def _extract_via_ytdlp(self, url: str, tweet_id: str) -> MediaInfo:
        """无 cookie / GraphQL 403 时的降级路径：用 yt-dlp guest token 解析视频推文。

        yt-dlp 内置 Twitter guest token 生成逻辑，无需登录态即可解析视频推文。
        限制：yt-dlp 的 TwitterIE 会过滤纯图片推文（type=='photo'），
        所以图片推文必须用 cookie + GraphQL 路径，这里只能返回友好错误。
        """
        try:
            import yt_dlp
            from ..utils.config import get_cookie_path
            cookie = get_cookie_path()
            opts = _yt_opts(cookie)
            opts["skip_download"] = True
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl_info = ydl.extract_info(url, download=False)
            ydl_info = yt_dlp.YoutubeDL.sanitize_info(ydl_info)
        except Exception as e:
            logger.warning("X yt-dlp 降级解析失败 (%s): %s", tweet_id, e)
            err_str = str(e)
            if "Unsupported URL" in err_str or "no video" in err_str.lower():
                err_str = "此推文为纯图片推文，需要导入 X cookie（含 auth_token + ct0）才能解析。请在设置中导入 X cookie 文件后重试。"
            elif "403" in err_str or "401" in err_str:
                err_str = "推文不可访问或已被删除。如为图片推文，请在设置中导入 X cookie 后重试。"
            return MediaInfo(
                platform=Platform.X,
                url=url,
                title="X（解析失败）",
                author="",
                description=f"无法获取推文信息：{err_str}",
            )

        author = ydl_info.get("uploader") or ydl_info.get("channel") or ""
        title = (ydl_info.get("title") or "X post")[:80]
        duration = ydl_info.get("duration")

        # 发布时间
        post_time = ""
        upload_date = ydl_info.get("upload_date", "")
        if upload_date:
            try:
                from datetime import datetime
                dt = datetime.strptime(upload_date, "%Y%m%d")
                post_time = dt.strftime("%Y%m%d")
            except Exception:
                pass

        thumbnail = ydl_info.get("thumbnail") or ""

        # 构造 MediaItem（取最高分辨率的 mp4）
        items: list[MediaItem] = []
        best_fmt = None
        best_h = 0
        for f in ydl_info.get("formats", []):
            if f.get("ext") == "mp4" and f.get("vcodec") != "none":
                h = f.get("height") or 0
                if h > best_h:
                    best_h = h
                    best_fmt = f
        if best_fmt:
            items.append(MediaItem(
                url=best_fmt.get("url", ""),
                is_video=True,
                index=0,
                extension="mp4",
                media_type=MediaType.VIDEO,
            ))
        elif ydl_info.get("url"):
            items.append(MediaItem(
                url=ydl_info["url"],
                is_video=True,
                index=0,
                extension="mp4",
                media_type=MediaType.VIDEO,
            ))

        # 构造 FormatOption 列表
        formats: list[FormatOption] = []
        for f in ydl_info.get("formats", []):
            fmt_id = f.get("format_id", "")
            if not fmt_id:
                continue
            h = f.get("height") or 0
            label = f"{h}p" if h else fmt_id
            formats.append(FormatOption(
                format_id=fmt_id,
                label=label,
                type="video",
                ext=f.get("ext", "mp4"),
                width=f.get("width") or 0,
                height=h,
            ))

        return MediaInfo(
            platform=Platform.X,
            url=url,
            title=title,
            author=author,
            post_time=post_time,
            thumbnail=thumbnail,
            duration=duration,
            media_items=items,
            formats=formats,
        )
