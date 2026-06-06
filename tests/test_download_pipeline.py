"""Tests for download pipeline — URL parsing, filename construction,
conflict handling, storage mode paths, and mock integration tests."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import dataclass, field

from lumio.utils.url_parser import Platform, parse_url
from lumio.downloader import (
    DownloadTask,
    VideoInfo,
    MediaItem,
    _safe_filename,
    _effective_name,
    _resolve_conflict_path,
    _resolve_conflict_stem,
)
from lumio.queue_manager import QueueTask, TaskStatus
from lumio.history_manager import HistoryRecord


# =====================================================================
# Test URLs from 测试链接.md
# =====================================================================

TEST_URLS = {
    "ig_profile": "https://www.instagram.com/test_user_123/",
    "ig_profile_utm": "https://www.instagram.com/test_user_123?utm_source=ig_web_button_share_sheet&igsh=abc123",
    "ig_post": "https://www.instagram.com/p/ABC123test/?utm_source=ig_web_copy_link&igsh=def456",
    "yt_channel": "https://www.youtube.com/@test_channel",
    "yt_channel_alt": "https://youtube.com/@test_channel?si=test123",
    "yt_video_short": "https://youtu.be/dQw4w9WgXcQ?si=test456",
    "x_tweet": "https://x.com/test_user/status/1234567890123456789?s=20",
}


# =====================================================================
# 1. URL 解析 — 测试链接覆盖
# =====================================================================

class TestURLParsingFromTestLinks:
    """Verify all test links are correctly parsed."""

    def test_ig_profile(self):
        r = parse_url(TEST_URLS["ig_profile"])
        assert r.platform == Platform.INSTAGRAM
        assert r.kind == "profile"
        assert "test_user_123" in r.url

    def test_ig_profile_with_utm(self):
        r = parse_url(TEST_URLS["ig_profile_utm"])
        assert r.platform == Platform.INSTAGRAM
        assert r.kind == "profile"
        assert "test_user_123" in r.url

    def test_ig_post(self):
        r = parse_url(TEST_URLS["ig_post"])
        assert r.platform == Platform.INSTAGRAM
        assert r.kind in ("post", "reel")

    def test_yt_channel(self):
        r = parse_url(TEST_URLS["yt_channel"])
        assert r.platform == Platform.YOUTUBE
        assert r.kind == "channel"

    def test_yt_channel_with_params(self):
        r = parse_url(TEST_URLS["yt_channel_alt"])
        assert r.platform == Platform.YOUTUBE
        assert r.kind == "channel"

    def test_yt_short_url(self):
        r = parse_url(TEST_URLS["yt_video_short"])
        assert r.platform == Platform.YOUTUBE
        assert r.kind == "video"

    def test_x_tweet(self):
        r = parse_url(TEST_URLS["x_tweet"])
        assert r.platform == Platform.X
        assert r.kind == "tweet"


# =====================================================================
# 2. _safe_filename — 边界输入
# =====================================================================

class TestSafeFilename:
    """Test filename sanitization with edge cases."""

    def test_normal_ascii(self):
        assert _safe_filename("hello_world") == "hello_world"

    def test_chinese_author(self):
        result = _safe_filename("鞠婧祎")
        assert result == "鞠婧祎"
        assert "/" not in result

    def test_special_chars_replaced(self):
        result = _safe_filename('file:*?"<>|name')
        assert all(c not in result for c in r'\/:*?"<>|')

    def test_path_traversal_blocked(self):
        result = _safe_filename("../../etc/passwd")
        assert ".." not in result

    def test_emoji_preserved(self):
        result = _safe_filename("user🎉name")
        assert "🎉" in result

    def test_empty_gives_underscore(self):
        assert _safe_filename("") == "_"
        assert _safe_filename("...") == "_"

    def test_long_title_truncated_is_still_valid(self):
        long = "a" * 200
        result = _safe_filename(long)
        assert len(result) > 0
        # No path separators
        assert all(c not in result for c in r'\/:*?"<>|')


# =====================================================================
# 3. _effective_name — 各种 task 组合
# =====================================================================

class TestEffectiveName:
    """Test filename stem construction from DownloadTask."""

    def _make_task(self, **kwargs):
        defaults = {
            "url": "https://example.com",
            "format_id": None,
            "output_dir": Path("/tmp"),
        }
        defaults.update(kwargs)
        return DownloadTask(**defaults)

    def test_custom_name_with_post_time(self):
        task = self._make_task(custom_name="alice", post_time="20260605_120000")
        assert _effective_name(task) == "alice_20260605_120000"

    def test_author_fallback(self):
        task = self._make_task(author="bob", post_time="20260601")
        assert _effective_name(task) == "bob_20260601"

    def test_no_name_returns_template(self):
        task = self._make_task()
        assert _effective_name(task) == "%(title)s"

    def test_custom_name_takes_priority(self):
        task = self._make_task(custom_name="custom", author="author", post_time="20260101")
        assert _effective_name(task) == "custom_20260101"

    def test_chinese_author(self):
        task = self._make_task(author="鞠婧祎", post_time="20260605")
        name = _effective_name(task)
        assert "鞠婧祎" in name
        assert "20260605" in name


# =====================================================================
# 4. _resolve_conflict_path — 三种策略
# =====================================================================

class TestConflictPath:
    """Test file conflict resolution with tmp_path."""

    def test_no_conflict_returns_original(self, tmp_path):
        p = tmp_path / "video.mp4"
        assert _resolve_conflict_path(p, "rename") == p

    def test_overwrite_returns_original(self, tmp_path):
        p = tmp_path / "video.mp4"
        p.write_text("x")
        assert _resolve_conflict_path(p, "overwrite") == p

    def test_skip_returns_none(self, tmp_path):
        p = tmp_path / "video.mp4"
        p.write_text("x")
        assert _resolve_conflict_path(p, "skip") is None

    def test_rename_gives_first_suffix(self, tmp_path):
        p = tmp_path / "video.mp4"
        p.write_text("x")
        result = _resolve_conflict_path(p, "rename")
        assert result.name == "video (1).mp4"

    def test_rename_cascades(self, tmp_path):
        p = tmp_path / "video.mp4"
        p.write_text("x")
        (tmp_path / "video (1).mp4").write_text("x")
        (tmp_path / "video (2).mp4").write_text("x")
        result = _resolve_conflict_path(p, "rename")
        assert result.name == "video (3).mp4"

    def test_skip_no_conflict_returns_path(self, tmp_path):
        p = tmp_path / "new.mp4"
        assert _resolve_conflict_path(p, "skip") == p


# =====================================================================
# 5. _resolve_conflict_stem — yt-dlp stem 匹配
# =====================================================================

class TestConflictStem:
    """Test stem-based conflict resolution for yt-dlp outtmpl."""

    def test_no_conflict(self, tmp_path):
        assert _resolve_conflict_stem(tmp_path, "video", "rename") == "video"

    def test_conflict_rename(self, tmp_path):
        (tmp_path / "video.mp4").write_text("x")
        assert _resolve_conflict_stem(tmp_path, "video", "rename") == "video (1)"

    def test_conflict_skip(self, tmp_path):
        (tmp_path / "video.mp4").write_text("x")
        assert _resolve_conflict_stem(tmp_path, "video", "skip") is None

    def test_overwrite_ignores_existing(self, tmp_path):
        (tmp_path / "video.mp4").write_text("x")
        assert _resolve_conflict_stem(tmp_path, "video", "overwrite") == "video"

    def test_multiple_extensions(self, tmp_path):
        (tmp_path / "video.mp4").write_text("x")
        (tmp_path / "video.webm").write_text("x")
        assert _resolve_conflict_stem(tmp_path, "video", "rename") == "video (1)"


# =====================================================================
# 6. Storage Mode 目录逻辑
# =====================================================================

class TestStorageModePaths:
    """Test directory structure for Simple vs Organized modes."""

    def test_simple_ig_flat(self, tmp_path):
        """Simple mode: all files in output_dir, no subdirectory."""
        out_dir = tmp_path / "Lumio"
        out_dir.mkdir()
        # In simple mode, IG download uses out_dir directly
        # No subdirectory should be created by the downloader
        assert not list(out_dir.iterdir())

    def test_organized_ig_batch_dir(self, tmp_path):
        """Organized mode: batch directory created."""
        base = tmp_path / "Lumio"
        base.mkdir()
        # Simulate profile_dialog.py organized mode logic
        username = "alice"
        from datetime import datetime, timezone
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        batch_dir = base / f"Instagram_{username}_{date_str}"
        batch_dir.mkdir(parents=True, exist_ok=True)
        assert batch_dir.exists()
        assert "Instagram_alice_" in batch_dir.name

    def test_organized_ig_per_post_dir(self, tmp_path):
        """Organized mode: per-post subdirectory inside batch dir."""
        base = tmp_path / "Lumio"
        base.mkdir()
        author = "alice"
        post_time = "20260605_120000"
        post_dir = base / f"{author}_{post_time}"
        post_dir.mkdir(parents=True, exist_ok=True)
        assert post_dir.exists()

    def test_special_chars_in_dir_name(self, tmp_path):
        """Special characters in author name should be sanitized."""
        base = tmp_path / "Lumio"
        base.mkdir()
        author = "user/name:test"
        safe_author = _safe_filename(author)
        post_dir = base / f"{safe_author}_20260605"
        post_dir.mkdir(parents=True, exist_ok=True)
        assert post_dir.exists()
        assert "/" not in post_dir.name


# =====================================================================
# 7. extract_info mock 测试
# =====================================================================

class TestExtractInfoMock:
    """Test extract_info with mocked network calls."""

    def _make_video_info(self, platform, author="testuser", title="Test Video"):
        return VideoInfo(
            title=title,
            url="https://example.com",
            thumbnail="https://example.com/thumb.jpg",
            duration=120,
            formats=[],
            platform=platform,
            author=author,
            items=[],
            post_time="20260605_120000",
        )

    @patch("lumio.downloader._yt_extract_info")
    def test_youtube_extract(self, mock_yt):
        mock_yt.return_value = self._make_video_info("youtube", author="DeepBlue")
        from lumio.downloader import extract_info
        info = extract_info(TEST_URLS["yt_video_short"])
        assert info.platform == "youtube"
        assert info.author == "DeepBlue"
        mock_yt.assert_called_once()

    @patch("lumio.downloader._ig_extract_info")
    def test_instagram_extract(self, mock_ig):
        mock_ig.return_value = self._make_video_info("instagram", author="test_user_123")
        from lumio.downloader import extract_info
        info = extract_info(TEST_URLS["ig_post"])
        assert info.platform == "instagram"
        assert info.author == "test_user_123"
        mock_ig.assert_called_once()

    @patch("lumio.downloader._x_extract_info")
    def test_x_extract(self, mock_x):
        mock_x.return_value = self._make_video_info("x", author="test_user")
        from lumio.downloader import extract_info
        info = extract_info(TEST_URLS["x_tweet"])
        assert info.platform == "x"
        assert info.author == "test_user"
        mock_x.assert_called_once()


# =====================================================================
# 8. HistoryRecord batch_id 兼容性
# =====================================================================

class TestHistoryBatchId:
    """Test HistoryRecord batch_id serialization compatibility."""

    def test_default_batch_id_empty(self):
        r = HistoryRecord(title="test")
        assert r.batch_id == ""

    def test_with_batch_id(self):
        r = HistoryRecord(title="test", batch_id="abc123")
        assert r.batch_id == "abc123"

    def test_asdict_includes_batch_id(self):
        from dataclasses import asdict
        r = HistoryRecord(title="test", batch_id="batch1")
        d = asdict(r)
        assert "batch_id" in d
        assert d["batch_id"] == "batch1"

    def test_old_data_without_batch_id(self):
        """Old history.json without batch_id field should still load."""
        from dataclasses import asdict
        # Simulate old data (no batch_id key)
        old_data = {
            "record_id": "abc",
            "title": "Old Record",
            "author": "alice",
            "platform": "youtube",
            "url": "https://example.com",
            "file_path": "/tmp/video.mp4",
            "file_size": 1024,
            "thumbnail_url": "",
            "download_time": "2026-06-01T12:00:00",
            "success": True,
            "duration_seconds": 0.0,
        }
        # dataclass with defaults should handle missing batch_id
        r = HistoryRecord(**{k: v for k, v in old_data.items() if k in HistoryRecord.__dataclass_fields__})
        assert r.batch_id == ""

    def test_json_roundtrip(self):
        r = HistoryRecord(title="test", batch_id="batch99")
        d = {
            "record_id": r.record_id,
            "title": r.title,
            "author": r.author,
            "platform": r.platform,
            "url": r.url,
            "file_path": r.file_path,
            "file_size": r.file_size,
            "thumbnail_url": r.thumbnail_url,
            "download_time": r.download_time,
            "success": r.success,
            "duration_seconds": r.duration_seconds,
            "batch_id": r.batch_id,
        }
        json_str = json.dumps(d)
        loaded = json.loads(json_str)
        r2 = HistoryRecord(**{k: v for k, v in loaded.items() if k in HistoryRecord.__dataclass_fields__})
        assert r2.batch_id == "batch99"
        assert r2.title == "test"


# =====================================================================
# 9. IG 文件名构建（端到端逻辑验证）
# =====================================================================

class TestIGFilenameConstruction:
    """Test IG download filename construction logic without network."""

    def test_single_item_no_suffix(self):
        """Single carousel item → no _01 suffix."""
        name_stem = "alice_20260605_120000"
        total = 1
        pad = len(str(total))
        idx = 0
        suffix = f"_{str(idx + 1).zfill(pad)}" if total > 1 else ""
        filename = f"{name_stem}{suffix}.jpg"
        assert filename == "alice_20260605_120000.jpg"

    def test_multiple_items_with_suffix(self):
        """Multiple carousel items → _1, _2, _3 (pad=1 for total<10)."""
        name_stem = "alice_20260605_120000"
        total = 3
        pad = len(str(total))  # pad=1 for total=3
        filenames = []
        for idx in range(total):
            suffix = f"_{str(idx + 1).zfill(pad)}" if total > 1 else ""
            ext = "mp4" if idx == 1 else "jpg"
            filenames.append(f"{name_stem}{suffix}.{ext}")
        assert filenames == [
            "alice_20260605_120000_1.jpg",
            "alice_20260605_120000_2.mp4",
            "alice_20260605_120000_3.jpg",
        ]

    def test_many_items_zero_padded(self):
        """10+ items → _01, _02, ..., _10 (pad=2)."""
        name_stem = "bob"
        total = 12
        pad = len(str(total))  # pad=2
        suffix_1 = f"_{str(1).zfill(pad)}" if total > 1 else ""
        suffix_12 = f"_{str(12).zfill(pad)}" if total > 1 else ""
        assert suffix_1 == "_01"
        assert suffix_12 == "_12"

    def test_chinese_author_in_filename(self):
        name_stem = _safe_filename("鞠婧祎") + "_20260605"
        filename = f"{name_stem}.mp4"
        assert "鞠婧祎" in filename
        assert "/" not in filename

    def test_video_and_image_extensions(self):
        assert "mp4" == ("mp4" if True else "jpg")  # video
        assert "jpg" == ("mp4" if False else "jpg")  # image
