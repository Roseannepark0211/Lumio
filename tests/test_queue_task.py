"""Tests for QueueTask dataclass: serialization, deserialization, state transitions."""
import json
import pytest
from pathlib import Path

from lumio.queue_manager import QueueTask, TaskStatus


class TestQueueTaskDefaults:
    def test_auto_id(self):
        qt = QueueTask(url="https://example.com")
        assert len(qt.task_id) == 12

    def test_auto_created_at(self):
        qt = QueueTask(url="https://example.com")
        assert qt.created_at > 0

    def test_default_status(self):
        qt = QueueTask()
        assert qt.status == TaskStatus.WAITING.value

    def test_default_batch_id_empty(self):
        qt = QueueTask()
        assert qt.batch_id == ""

    def test_explicit_id_preserved(self):
        qt = QueueTask(task_id="myid12345678", url="x")
        assert qt.task_id == "myid12345678"


class TestQueueTaskSerialization:
    def test_roundtrip(self):
        qt = QueueTask(
            url="https://instagram.com/p/abc",
            title="Test Post",
            platform="instagram",
            author="alice",
            format_type="combined",
            batch_id="batch123456",
        )
        d = qt.to_dict()
        assert d["url"] == "https://instagram.com/p/abc"
        assert d["batch_id"] == "batch123456"

        restored = QueueTask.from_dict(d)
        assert restored.url == qt.url
        assert restored.title == qt.title
        assert restored.batch_id == qt.batch_id
        assert restored.author == qt.author

    def test_from_dict_resets_progress(self):
        d = {
            "task_id": "abc123",
            "url": "https://example.com",
            "status": TaskStatus.WAITING.value,
            "progress": 50.0,
            "speed": "1MB/s",
            "filename": "/tmp/f.mp4",
            "error": "something",
            "retry_count": 2,
        }
        qt = QueueTask.from_dict(d)
        assert qt.progress == 0.0
        assert qt.speed == ""
        assert qt.filename == ""
        assert qt.error == ""
        assert qt.retry_count == 0

    def test_from_dict_download_to_interrupted(self):
        d = {
            "task_id": "abc123",
            "url": "https://example.com",
            "status": TaskStatus.DOWNLOADING.value,
        }
        qt = QueueTask.from_dict(d)
        assert qt.status == TaskStatus.INTERRUPTED.value

    def test_from_dict_completed_stays(self):
        d = {
            "task_id": "abc123",
            "url": "https://example.com",
            "status": TaskStatus.COMPLETED.value,
        }
        qt = QueueTask.from_dict(d)
        assert qt.status == TaskStatus.COMPLETED.value

    def test_to_dict_excludes_runtime_fields(self):
        qt = QueueTask(url="https://example.com")
        qt.progress = 75.0
        qt.speed = "5MB/s"
        d = qt.to_dict()
        # Runtime-only fields should NOT be in serialized dict
        assert "progress" not in d
        assert "speed" not in d
        assert "error" not in d

    def test_to_dict_is_json_serializable(self):
        qt = QueueTask(url="https://example.com", batch_id="abc")
        s = json.dumps(qt.to_dict(), ensure_ascii=False)
        assert "abc" in s


class TestTaskStatusEnum:
    def test_all_values(self):
        expected = {"等待中", "下载中", "暂停中", "重试中", "已中断", "已完成", "失败", "已取消", "合并中", "解析中"}
        actual = {s.value for s in TaskStatus}
        assert actual == expected

    def test_str_enum(self):
        assert isinstance(TaskStatus.WAITING, str)
        assert TaskStatus.WAITING == "等待中"
