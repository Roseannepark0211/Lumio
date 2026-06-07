from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .utils.config import get_thumbs_dir

_THUMB_SIZE = 200


def generate_thumbnail(
    record_id: str, file_path: str, media_type: str, thumbnail_url: str = ""
) -> str | None:
    """Generate a local thumbnail. Returns the path or None on failure."""
    out_dir = get_thumbs_dir()
    out_path = out_dir / f"{record_id}.jpg"
    if out_path.exists():
        return str(out_path)

    p = Path(file_path) if file_path else None

    try:
        if media_type == "image" and p and p.is_file():
            return _resize_image(p, out_path)
        if media_type in ("video", "mixed") and p:
            if p.is_file():
                return _extract_video_frame(p, out_path)
            if p.is_dir():
                first = _first_media_file(p)
                if first:
                    if first.suffix.lower() in {".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv"}:
                        return _extract_video_frame(first, out_path)
                    if first.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
                        return _resize_image(first, out_path)
        # Fallback: download remote thumbnail URL
        if thumbnail_url:
            return _download_and_resize(thumbnail_url, out_path)
    except Exception:
        pass
    return None


def _resize_image(src: Path, dst: Path) -> str | None:
    from PIL import Image
    img = Image.open(src)
    img.thumbnail((_THUMB_SIZE, _THUMB_SIZE))
    img.convert("RGB").save(str(dst), "JPEG", quality=80)
    return str(dst)


def _extract_video_frame(video_path: Path, dst: Path) -> str | None:
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None
    cmd = [
        ffmpeg,
        "-ss", "1",
        "-i", str(video_path),
        "-frames:v", "1",
        "-vf", f"scale={_THUMB_SIZE}:-1",
        "-y",
        str(dst),
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=10, check=True)
        if dst.exists() and dst.stat().st_size > 0:
            return str(dst)
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def _download_and_resize(url: str, dst: Path) -> str | None:
    import requests
    from PIL import Image
    from io import BytesIO
    headers = {}
    if "twimg.com" in url or "x.com" in url:
        headers["Referer"] = "https://x.com/"
    resp = requests.get(url, timeout=10, headers=headers)
    if resp.status_code != 200:
        return None
    img = Image.open(BytesIO(resp.content))
    img.thumbnail((_THUMB_SIZE, _THUMB_SIZE))
    img.convert("RGB").save(str(dst), "JPEG", quality=80)
    return str(dst)


def _first_media_file(directory: Path) -> Path | None:
    media_exts = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
    try:
        files = sorted(f for f in directory.iterdir() if f.is_file() and f.suffix.lower() in media_exts)
        return files[0] if files else None
    except OSError:
        return None


class _ThumbWorker(QThread):
    finished = Signal(str, str)  # record_id, local_path

    def __init__(self, record_id: str, file_path: str, media_type: str, thumbnail_url: str):
        super().__init__()
        self._record_id = record_id
        self._file_path = file_path
        self._media_type = media_type
        self._thumbnail_url = thumbnail_url

    def run(self):
        result = generate_thumbnail(self._record_id, self._file_path, self._media_type, self._thumbnail_url)
        if result:
            self.finished.emit(self._record_id, result)


# Keep references to prevent GC of running workers
_active_workers: list[_ThumbWorker] = []


def generate_thumbnail_async(
    record_id: str, file_path: str, media_type: str, thumbnail_url: str,
    callback=None,
):
    """Generate thumbnail in background thread. callback(record_id, local_path)."""
    worker = _ThumbWorker(record_id, file_path, media_type, thumbnail_url)
    _active_workers.append(worker)

    def on_done(rid, path):
        if callback:
            callback(rid, path)
        _active_workers.remove(worker)

    worker.finished.connect(on_done)
    worker.start()
