from __future__ import annotations

import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import http.cookiejar
import requests
import yt_dlp

from .utils.config import get_cookie_path, get_download_dir
from .utils.url_parser import Platform, parse_url


def _find_ffmpeg() -> str | None:
    """Locate ffmpeg: system PATH first, then imageio-ffmpeg bundle."""
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


@dataclass
class MediaItem:
    url: str
    is_video: bool
    index: int = 0


@dataclass
class VideoInfo:
    title: str
    url: str
    thumbnail: str | None
    duration: int | None  # seconds
    formats: list[dict]  # raw yt-dlp format dicts (YouTube only)
    platform: str
    author: str = ""  # uploader / channel / IG username
    items: list[MediaItem] = field(default_factory=list)
    post_time: str = ""


@dataclass
class DownloadTask:
    url: str
    format_id: str | None
    output_dir: Path
    custom_name: str = ""
    author: str = ""
    post_time: str = ""
    format_type: str = ""  # "video" | "audio" | "combined" | ""
    status: str = "pending"
    progress: float = 0.0
    speed: str = ""
    filename: str = ""
    error: str = ""
    _cancelled: bool = field(default=False, repr=False)


# ---- YouTube ----

def _yt_opts(cookie_file: Path | None = None) -> dict:
    opts: dict = {"quiet": True, "no_warnings": True, "noprogress": True}
    if cookie_file and cookie_file.exists():
        opts["cookiefile"] = str(cookie_file)
    ffmpeg = _find_ffmpeg()
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg  # full path to binary
    return opts


def _yt_extract_info(url: str) -> VideoInfo:
    cookie = get_cookie_path()
    opts = _yt_opts(cookie)
    opts["skip_download"] = True

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    info = yt_dlp.YoutubeDL.sanitize_info(info)
    entries = info.get("entries") or [info]
    first = entries[0]

    author = (
        first.get("uploader")
        or first.get("channel")
        or first.get("creator")
        or ""
    )

    upload_date = first.get("upload_date", "")  # format: "20240315"
    post_time = ""
    if upload_date and len(upload_date) == 8:
        post_time = f"{upload_date[:4]}{upload_date[4:6]}{upload_date[6:8]}"

    return VideoInfo(
        title=first.get("title", "Unknown"),
        url=url,
        thumbnail=first.get("thumbnail"),
        duration=first.get("duration"),
        formats=first.get("formats", []),
        platform=first.get("extractor", "youtube"),
        author=author,
        post_time=post_time,
    )


# ---- Instagram ----

def _ig_session():
    import instaloader
    L = instaloader.Instaloader(
        download_videos=True,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
    )
    cookie_path = get_cookie_path()
    if cookie_path:
        cj = http.cookiejar.MozillaCookieJar(str(cookie_path))
        cj.load(ignore_discard=True, ignore_expires=True)
        for c in cj:
            L.context._session.cookies.set(c.name, c.value, domain=c.domain)
    return L


def _ig_extract_info(url: str) -> VideoInfo:
    import instaloader
    shortcode = url.rstrip("/").split("/")[-1]
    parts = url.rstrip("/").split("/")
    for i, p in enumerate(parts):
        if p in ("reel", "p") and i + 1 < len(parts):
            shortcode = parts[i + 1]
            break

    L = _ig_session()
    post = instaloader.Post.from_shortcode(L.context, shortcode)

    title = (post.caption or "Instagram post")[:80]
    thumb = str(post.url) if not post.is_video else None
    post_time = post.date_utc.strftime("%Y%m%d_%H%M%S") if post.date_utc else ""
    author = post.owner_username or ""
    items: list[MediaItem] = []

    if post.typename == "GraphSidecar":
        for i, node in enumerate(post.get_sidecar_nodes()):
            url_str = str(node.video_url) if node.is_video else str(node.display_url)
            items.append(MediaItem(url=url_str, is_video=node.is_video, index=i))
    elif post.is_video:
        items.append(MediaItem(url=str(post.video_url), is_video=True, index=0))
    else:
        items.append(MediaItem(url=str(post.url), is_video=False, index=0))

    return VideoInfo(
        title=title,
        url=url,
        thumbnail=thumb,
        duration=None,
        formats=[],
        platform="instagram",
        author=author,
        items=items,
        post_time=post_time,
    )


# ---- X (Twitter) ----

def _x_extract_info(url: str) -> VideoInfo:
    cookie = get_cookie_path()
    opts = _yt_opts(cookie)
    opts["skip_download"] = True

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    info = yt_dlp.YoutubeDL.sanitize_info(info)

    author = (
        info.get("uploader")
        or info.get("creator")
        or ""
    )

    upload_date = info.get("upload_date", "")
    post_time = ""
    if upload_date and len(upload_date) == 8:
        post_time = f"{upload_date[:4]}{upload_date[4:6]}{upload_date[6:8]}"

    return VideoInfo(
        title=info.get("title", "X post"),
        url=url,
        thumbnail=info.get("thumbnail"),
        duration=info.get("duration"),
        formats=info.get("formats", []),
        platform="x",
        author=author,
        post_time=post_time,
    )


# ---- Public API ----

def extract_info(url: str) -> VideoInfo:
    parsed = parse_url(url)
    if parsed.platform == Platform.YOUTUBE:
        return _yt_extract_info(url)
    elif parsed.platform == Platform.INSTAGRAM:
        return _ig_extract_info(url)
    elif parsed.platform == Platform.X:
        return _x_extract_info(url)
    else:
        raise ValueError(f"Unsupported URL: {url}")


def _build_format_options(info: VideoInfo) -> list[dict]:
    """Build a clean, user-friendly format list for YouTube videos."""
    options: list[dict] = [{"id": "best", "label": "Best quality (auto)", "_type": "combined"}]

    seen_res: set[int] = set()
    video_opts: list[dict] = []
    audio_opts: list[dict] = []

    for f in info.formats:
        fid = f.get("format_id", "")
        ext = f.get("ext", "")
        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")
        height = f.get("height")
        abr = f.get("abr")
        vbr = f.get("tbr") or f.get("vbr") or 0

        if ext in ("mhtml", "json", "json3"):
            continue
        if f.get("format_note") == "storyboard":
            continue
        if vcodec == "none" and acodec == "none":
            continue

        has_video = vcodec != "none"
        has_audio = acodec != "none"

        # Combined stream (video+audio in one) — rare on modern YouTube
        if has_video and has_audio and height:
            if height not in seen_res:
                seen_res.add(height)
                video_opts.append({
                    "id": fid,
                    "label": f"{height}p {ext} (~{int(vbr)}kbps) [merged]" if vbr else f"{height}p {ext} [merged]",
                    "_type": "combined",
                    "_height": height,
                    "_vbr": vbr,
                })

        # Video-only stream
        elif has_video and height:
            if height in seen_res:
                for opt in video_opts:
                    if opt.get("_height") == height and vbr > opt.get("_vbr", 0):
                        opt["id"] = fid
                        opt["_vbr"] = vbr
                        opt["label"] = f"{height}p {ext} (~{int(vbr)}kbps)"
                    break
                continue
            seen_res.add(height)
            video_opts.append({
                "id": fid,
                "label": f"{height}p {ext} (~{int(vbr)}kbps)" if vbr else f"{height}p {ext}",
                "_type": "video",
                "_height": height,
                "_vbr": vbr,
            })

        # Audio-only stream
        elif has_audio and not has_video:
            label = f"Audio only {int(abr)}kbps ({ext})" if abr else f"Audio only ({ext})"
            audio_opts.append({"id": fid, "label": label, "_type": "audio"})

    video_opts.sort(key=lambda o: o.get("_height", 0), reverse=True)
    for o in video_opts:
        o.pop("_height", None)
        o.pop("_vbr", None)

    options.extend(video_opts)
    if audio_opts:
        options.append({"id": "___sep", "label": "─────────", "disabled": True})
        options.extend(audio_opts)

    return options


# ---- Download engine ----

ProgressCallback = Callable[[DownloadTask], None]


def _download_hook(task: DownloadTask, on_progress: ProgressCallback | None):
    def hook(d: dict):
        if task._cancelled:
            raise _CancelledError()

        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            task.progress = (downloaded / total * 100) if total else 0
            task.speed = d.get("_speed_str", "")
            task.filename = d.get("filename", "")
            task.status = "downloading"
        elif d["status"] == "finished":
            task.progress = 100
            task.status = "done"
            task.filename = d.get("filename", "")

        if on_progress:
            on_progress(task)

    return hook


class _CancelledError(Exception):
    pass


def _effective_name(task: DownloadTask) -> str:
    """Return the filename stem: custom > author+timestamp > title."""
    if task.custom_name:
        name = task.custom_name
    elif task.author:
        name = task.author
    else:
        return "%(title)s"
    if task.post_time:
        name = f"{name}_{task.post_time}"
    return name


def _yt_download(
    task: DownloadTask,
    on_progress: ProgressCallback | None,
    on_done: Callable[[DownloadTask], None] | None,
):
    cookie = get_cookie_path()
    opts = _yt_opts(cookie)
    out_name = _effective_name(task)
    opts["outtmpl"] = str(task.output_dir / f"{out_name}.%(ext)s")
    opts["progress_hooks"] = [_download_hook(task, on_progress)]

    if task.format_id and task.format_id not in ("best", "___sep"):
        # Auto-merge: video-only needs audio, audio-only needs video
        if task.format_type == "video":
            opts["format"] = f"{task.format_id}+bestaudio"
        elif task.format_type == "audio":
            opts["format"] = f"bestvideo+{task.format_id}"
        else:
            opts["format"] = task.format_id
    else:
        opts["format"] = (
            "bestvideo[ext=mp4][height<=2160]+bestaudio[ext=m4a]/"
            "bestvideo+bestaudio/"
            "best[ext=mp4]/"
            "best"
        )
    opts["merge_output_format"] = "mp4"

    task.status = "downloading"
    if on_progress:
        on_progress(task)

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([task.url])

    task.status = "done"
    task.progress = 100


def _ig_download(
    task: DownloadTask,
    on_progress: ProgressCallback | None,
    on_done: Callable[[DownloadTask], None] | None,
):
    import instaloader
    parts = task.url.rstrip("/").split("/")
    shortcode = parts[-1]
    for i, p in enumerate(parts):
        if p in ("reel", "p") and i + 1 < len(parts):
            shortcode = parts[i + 1]
            break

    L = _ig_session()
    post = instaloader.Post.from_shortcode(L.context, shortcode)

    task.status = "downloading"
    if on_progress:
        on_progress(task)

    # Folder name: custom_name > author > shortcode, always append timestamp
    if task.custom_name:
        folder_name = task.custom_name
    elif task.author:
        folder_name = task.author
    else:
        folder_name = shortcode
    if task.post_time:
        folder_name = f"{folder_name}_{task.post_time}"
    out_dir = task.output_dir / folder_name
    out_dir.mkdir(parents=True, exist_ok=True)

    items: list[MediaItem] = []
    if post.typename == "GraphSidecar":
        for i, node in enumerate(post.get_sidecar_nodes()):
            url_str = str(node.video_url) if node.is_video else str(node.display_url)
            items.append(MediaItem(url=url_str, is_video=node.is_video, index=i))
    elif post.is_video:
        items.append(MediaItem(url=str(post.video_url), is_video=True, index=0))
    else:
        items.append(MediaItem(url=str(post.url), is_video=False, index=0))

    # Filename stem: custom > author > shortcode
    name_stem = task.custom_name or task.author or shortcode

    total = len(items)
    pad = len(str(total))
    for idx, item in enumerate(items):
        ext = "mp4" if item.is_video else "jpg"
        suffix = f"_{str(idx + 1).zfill(pad)}" if total > 1 else ""
        filename = out_dir / f"{name_stem}{suffix}.{ext}"

        resp = requests.get(item.url, stream=True, timeout=30)
        resp.raise_for_status()

        total_size = int(resp.headers.get("content-length", 0))
        downloaded = 0

        with open(filename, "wb") as f:
            for chunk in resp.iter_content(8192):
                if task._cancelled:
                    raise _CancelledError()
                f.write(chunk)
                downloaded += len(chunk)
                if total_size:
                    item_pct = downloaded / total_size * 100
                    task.progress = (idx + item_pct / 100) / total * 100
                    task.speed = f"{idx + 1}/{total}"
                    task.filename = str(filename)
                    if on_progress:
                        on_progress(task)

    task.status = "done"
    task.progress = 100
    task.filename = str(out_dir)


def _x_download(
    task: DownloadTask,
    on_progress: ProgressCallback | None,
    on_done: Callable[[DownloadTask], None] | None,
):
    cookie = get_cookie_path()
    opts = _yt_opts(cookie)
    out_name = _effective_name(task)
    opts["outtmpl"] = str(task.output_dir / f"{out_name}.%(ext)s")
    opts["progress_hooks"] = [_download_hook(task, on_progress)]
    opts["format"] = "best[ext=mp4]/best"
    opts["merge_output_format"] = "mp4"

    task.status = "downloading"
    if on_progress:
        on_progress(task)

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([task.url])

    task.status = "done"
    task.progress = 100


def start_download(
    task: DownloadTask,
    on_progress: ProgressCallback | None = None,
    on_done: Callable[[DownloadTask], None] | None = None,
) -> threading.Thread:
    parsed = parse_url(task.url)

    def _run():
        try:
            if parsed.platform == Platform.YOUTUBE:
                _yt_download(task, on_progress, on_done)
            elif parsed.platform == Platform.INSTAGRAM:
                _ig_download(task, on_progress, on_done)
            elif parsed.platform == Platform.X:
                _x_download(task, on_progress, on_done)
        except _CancelledError:
            task.status = "error"
            task.error = "Cancelled"
        except Exception as e:
            task.status = "error"
            task.error = str(e)

        if on_done:
            on_done(task)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


# ---- Pause-aware download (V2 queue system) ----

def _download_hook_with_pause(
    task: DownloadTask,
    pause_event: threading.Event,
    on_progress: ProgressCallback | None,
):
    def hook(d: dict):
        if task._cancelled:
            raise _CancelledError()
        pause_event.wait()  # blocks when paused
        if task._cancelled:
            raise _CancelledError()

        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            task.progress = (downloaded / total * 100) if total else 0
            task.speed = d.get("_speed_str", "")
            task.filename = d.get("filename", "")
            task.status = "downloading"
        elif d["status"] == "finished":
            task.progress = 100
            task.status = "done"
            task.filename = d.get("filename", "")

        if on_progress:
            on_progress(task)

    return hook


def _yt_download_with_pause(task, pause_event, on_progress, on_done):
    cookie = get_cookie_path()
    opts = _yt_opts(cookie)
    out_name = _effective_name(task)
    opts["outtmpl"] = str(task.output_dir / f"{out_name}.%(ext)s")
    opts["progress_hooks"] = [_download_hook_with_pause(task, pause_event, on_progress)]

    if task.format_id and task.format_id not in ("best", "___sep"):
        if task.format_type == "video":
            opts["format"] = f"{task.format_id}+bestaudio"
        elif task.format_type == "audio":
            opts["format"] = f"bestvideo+{task.format_id}"
        else:
            opts["format"] = task.format_id
    else:
        opts["format"] = (
            "bestvideo[ext=mp4][height<=2160]+bestaudio[ext=m4a]/"
            "bestvideo+bestaudio/"
            "best[ext=mp4]/"
            "best"
        )
    opts["merge_output_format"] = "mp4"

    task.status = "downloading"
    if on_progress:
        on_progress(task)

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([task.url])

    task.status = "done"
    task.progress = 100


def _ig_download_with_pause(task, pause_event, on_progress, on_done):
    import instaloader
    parts = task.url.rstrip("/").split("/")
    shortcode = parts[-1]
    for i, p in enumerate(parts):
        if p in ("reel", "p") and i + 1 < len(parts):
            shortcode = parts[i + 1]
            break

    L = _ig_session()
    post = instaloader.Post.from_shortcode(L.context, shortcode)

    task.status = "downloading"
    if on_progress:
        on_progress(task)

    if task.custom_name:
        folder_name = task.custom_name
    elif task.author:
        folder_name = task.author
    else:
        folder_name = shortcode
    if task.post_time:
        folder_name = f"{folder_name}_{task.post_time}"
    out_dir = task.output_dir / folder_name
    out_dir.mkdir(parents=True, exist_ok=True)

    items: list[MediaItem] = []
    if post.typename == "GraphSidecar":
        for i, node in enumerate(post.get_sidecar_nodes()):
            url_str = str(node.video_url) if node.is_video else str(node.display_url)
            items.append(MediaItem(url=url_str, is_video=node.is_video, index=i))
    elif post.is_video:
        items.append(MediaItem(url=str(post.video_url), is_video=True, index=0))
    else:
        items.append(MediaItem(url=str(post.url), is_video=False, index=0))

    name_stem = task.custom_name or task.author or shortcode
    total = len(items)
    pad = len(str(total))
    for idx, item in enumerate(items):
        ext = "mp4" if item.is_video else "jpg"
        suffix = f"_{str(idx + 1).zfill(pad)}" if total > 1 else ""
        filename = out_dir / f"{name_stem}{suffix}.{ext}"

        resp = requests.get(item.url, stream=True, timeout=30)
        resp.raise_for_status()

        total_size = int(resp.headers.get("content-length", 0))
        downloaded = 0

        with open(filename, "wb") as f:
            for chunk in resp.iter_content(8192):
                if task._cancelled:
                    raise _CancelledError()
                pause_event.wait()  # blocks when paused
                if task._cancelled:
                    raise _CancelledError()
                f.write(chunk)
                downloaded += len(chunk)
                if total_size:
                    item_pct = downloaded / total_size * 100
                    task.progress = (idx + item_pct / 100) / total * 100
                    task.speed = f"{idx + 1}/{total}"
                    task.filename = str(filename)
                    if on_progress:
                        on_progress(task)

    task.status = "done"
    task.progress = 100
    task.filename = str(out_dir)


def _x_download_with_pause(task, pause_event, on_progress, on_done):
    cookie = get_cookie_path()
    opts = _yt_opts(cookie)
    out_name = _effective_name(task)
    opts["outtmpl"] = str(task.output_dir / f"{out_name}.%(ext)s")
    opts["progress_hooks"] = [_download_hook_with_pause(task, pause_event, on_progress)]
    opts["format"] = "best[ext=mp4]/best"
    opts["merge_output_format"] = "mp4"

    task.status = "downloading"
    if on_progress:
        on_progress(task)

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([task.url])

    task.status = "done"
    task.progress = 100


def start_download_with_pause(
    task: DownloadTask,
    pause_event: threading.Event,
    on_progress: ProgressCallback | None = None,
    on_done: Callable[[DownloadTask], None] | None = None,
) -> threading.Thread:
    parsed = parse_url(task.url)

    def _run():
        try:
            if parsed.platform == Platform.YOUTUBE:
                _yt_download_with_pause(task, pause_event, on_progress, on_done)
            elif parsed.platform == Platform.INSTAGRAM:
                _ig_download_with_pause(task, pause_event, on_progress, on_done)
            elif parsed.platform == Platform.X:
                _x_download_with_pause(task, pause_event, on_progress, on_done)
        except _CancelledError:
            task.status = "error"
            task.error = "Cancelled"
        except Exception as e:
            task.status = "error"
            task.error = str(e)

        if on_done:
            on_done(task)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread
