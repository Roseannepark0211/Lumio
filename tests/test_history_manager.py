"""Tests for history_manager.py — HistoryRecord CRUD + persistence."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch

from lumio.history_manager import HistoryManager, HistoryRecord


@pytest.fixture(autouse=True)
def _redirect_history(tmp_path, monkeypatch):
    """Redirect history.json to a tmp dir so tests don't touch real data."""
    fake_path = tmp_path / "history.json"
    monkeypatch.setattr(
        "lumio.history_manager.get_history_path", lambda: fake_path
    )
    return fake_path


class TestHistoryRecord:
    def test_auto_id(self):
        r = HistoryRecord(title="test")
        assert len(r.record_id) == 12

    def test_auto_download_time(self):
        r = HistoryRecord(title="test")
        assert r.download_time  # non-empty

    def test_explicit_id_preserved(self):
        r = HistoryRecord(record_id="myid12345678", title="test")
        assert r.record_id == "myid12345678"

    def test_default_success_true(self):
        r = HistoryRecord()
        assert r.success is True

    def test_default_duration_zero(self):
        r = HistoryRecord()
        assert r.duration_seconds == 0.0


class TestHistoryManager:
    def test_add_and_list(self):
        hm = HistoryManager()
        r1 = HistoryRecord(title="First", author="alice")
        r2 = HistoryRecord(title="Second", author="bob")
        hm.add(r1)
        hm.add(r2)
        # Most recent first
        assert hm.records[0].title == "Second"
        assert hm.records[1].title == "First"
        assert len(hm.records) == 2

    def test_delete(self):
        hm = HistoryManager()
        r = HistoryRecord(title="ToDelete")
        hm.add(r)
        assert len(hm.records) == 1
        hm.delete(r.record_id)
        assert len(hm.records) == 0

    def test_delete_nonexistent(self):
        hm = HistoryManager()
        hm.delete("no_such_id")  # should not raise

    def test_clear(self):
        hm = HistoryManager()
        hm.add(HistoryRecord(title="A"))
        hm.add(HistoryRecord(title="B"))
        hm.clear()
        assert len(hm.records) == 0

    def test_persistence(self, _redirect_history):
        path = _redirect_history
        hm = HistoryManager()
        hm.add(HistoryRecord(title="Persisted", author="carol"))
        # Read from disk in a new manager
        hm2 = HistoryManager()
        assert len(hm2.records) == 1
        assert hm2.records[0].title == "Persisted"

    def test_load_empty_when_no_file(self):
        hm = HistoryManager()
        assert hm.records == []

    def test_load_corrupted_file(self, _redirect_history):
        _redirect_history.write_text("NOT VALID JSON", encoding="utf-8")
        hm = HistoryManager()
        assert hm.records == []
