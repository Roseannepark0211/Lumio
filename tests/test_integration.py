"""Integration tests — real network calls against live platforms.

Requires: proxy/VPN enabled for YouTube, Instagram, X.
Run: PYTHONPATH=src python -m pytest tests/test_integration.py -v -s
"""
from __future__ import annotations

import shutil
import tempfile
import threading
import time
from pathlib import Path

import pytest

from lumio.downloader import (
    DownloadTask,
    VideoInfo,
    extract_info,
    start_download_with_pause,
)
from lumio.utils.url_parser import Platform, parse_url

# ---- Test links (from 测试链接.md) ----

IG_PROFILE = "https://www.instagram.com/jujingyi_kikuuu/"
IG_POST = "https://www.instagram.com/p/DYlrmb-FGFg/"
YT_CHANNEL = "https://www.youtube.com/@deepblueofficial"
YT_VIDEO = "https://youtu.be/vS-Tx6REeFs"
X_TWEET = "https://x.com/justinbieber/status/2049344366985331105"

TIMEOUT = 120  # seconds per download


@pytest.fixture(scope="module")
def tmp_dir():
    """Create a temp download directory; clean up after all tests."""
    d = Path(tempfile.mkdtemp(prefix="lumio_test_"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ================================================================
# 1. URL Parsing
# ================================================================

class TestURLParsing:
    def test_ig_profile(self):
        p = parse_url(IG_PROFILE)
        assert p.platform == Platform.INSTAGRAM
        assert p.kind == "profile"

    def test_ig_post(self):
        p = parse_url(IG_POST)
        assert p.platform == Platform.INSTAGRAM
        assert p.kind == "reel"

    def test_yt_channel(self):
        p = parse_url(YT_CHANNEL)
        assert p.platform == Platform.YOUTUBE
        assert p.kind == "channel"

    def test_yt_video(self):
        p = parse_url(YT_VIDEO)
        assert p.platform == Platform.YOUTUBE
        assert p.kind == "video"

    def test_x_tweet(self):
        p = parse_url(X_TWEET)
        assert p.platform == Platform.X
        assert p.kind == "tweet"


# ================================================================
# 2. Info Extraction
# ================================================================

class TestExtractInfo:
    def test_ig_post_info(self):
        info = extract_info(IG_POST)
        assert isinstance(info, VideoInfo)
        assert info.platform == "instagram"
        assert info.title, "IG post title should not be empty"
        assert info.author, "IG post author should not be empty"
        assert len(info.items) > 0, "IG post should have at least 1 media item"

    def test_yt_video_info(self):
        info = extract_info(YT_VIDEO)
        assert isinstance(info, VideoInfo)
        assert info.platform == "youtube"
        assert info.title, "YT video title should not be empty"
        assert info.author, "YT video author should not be empty"

    @pytest.mark.xfail(reason="测试推文可能无视频内容", raises=Exception)
    def test_x_tweet_info(self):
        info = extract_info(X_TWEET)
        assert isinstance(info, VideoInfo)
        assert info.platform == "x"
        assert info.title, "X tweet title should not be empty"
        assert len(info.items) > 0, "X tweet should have at least 1 media item"


# ================================================================
# 3. Download (single file each platform)
# ================================================================

class TestDownload:
    def _download(self, url: str, tmp_dir: Path, timeout: int = TIMEOUT) -> DownloadTask:
        """Run a download and wait for completion."""
        task = DownloadTask(
            url=url,
            format_id=None,
            output_dir=tmp_dir,
        )
        pause_event = threading.Event()
        pause_event.set()  # not paused

        done_event = threading.Event()

        def on_done(t: DownloadTask):
            done_event.set()

        thread = start_download_with_pause(task, pause_event, on_done=on_done)
        finished = done_event.wait(timeout=timeout)
        assert finished, f"Download timed out after {timeout}s"
        thread.join(timeout=5)
        return task

    def test_yt_video_download(self, tmp_dir):
        task = self._download(YT_VIDEO, tmp_dir)
        assert task.status == "done", f"Download failed: {task.error}"
        # Verify at least one file was created
        files = list(tmp_dir.rglob("*"))
        media_files = [f for f in files if f.is_file() and f.suffix.lower() in (".mp4", ".mkv", ".webm", ".mp3", ".m4a")]
        assert len(media_files) > 0, f"No media files found in {tmp_dir}"

    def test_ig_post_download(self, tmp_dir):
        ig_dir = tmp_dir / "ig"
        ig_dir.mkdir(exist_ok=True)
        task = self._download(IG_POST, ig_dir)
        assert task.status == "done", f"Download failed: {task.error}"

    @pytest.mark.xfail(reason="测试推文可能无视频内容", raises=AssertionError)
    def test_x_tweet_download(self, tmp_dir):
        x_dir = tmp_dir / "x"
        x_dir.mkdir(exist_ok=True)
        task = self._download(X_TWEET, x_dir)
        assert task.status == "done", f"Download failed: {task.error}"
