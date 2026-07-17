"""Tests for utils/config.py 鈥?config read/write, caching, defaults."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import lumio.utils.config as cfg_mod


@pytest.fixture(autouse=True)
def _reset_cache(tmp_path, monkeypatch):
    """Redirect config files to tmp and reset global cache."""
    fake_dir = tmp_path / ".lumio"
    fake_dir.mkdir()
    fake_config = fake_dir / "config.json"
    fake_queue = fake_dir / "queue.json"
    fake_history = fake_dir / "history.json"

    monkeypatch.setattr(cfg_mod, "_APP_DIR", fake_dir)
    monkeypatch.setattr(cfg_mod, "_CONFIG_FILE", fake_config)
    monkeypatch.setattr(cfg_mod, "_QUEUE_FILE", fake_queue)
    monkeypatch.setattr(cfg_mod, "_HISTORY_FILE", fake_history)
    cfg_mod._cache = None
    yield
    cfg_mod._cache = None


class TestLoadConfig:
    def test_defaults_when_no_file(self):
        result = cfg_mod.load_config()
        assert result["lang"] == "zh"
        assert result["theme"] == "light"
        assert result["max_concurrent"] == 3
        assert result["max_retries"] == 3
        assert result["storage_mode"] == "simple"
        assert result["init_completed"] is False

    def test_merges_with_disk(self, tmp_path):
        disk_cfg = {"lang": "en", "max_concurrent": 8}
        cfg_mod._CONFIG_FILE.write_text(json.dumps(disk_cfg), encoding="utf-8")
        result = cfg_mod.load_config()
        assert result["lang"] == "en"
        assert result["max_concurrent"] == 8
        # defaults still present
        assert result["theme"] == "light"

    def test_caches_after_first_read(self, tmp_path):
        cfg_mod._CONFIG_FILE.write_text(json.dumps({"lang": "en"}), encoding="utf-8")
        first = cfg_mod.load_config()
        # Modify file on disk 鈥?cache should NOT reflect change
        cfg_mod._CONFIG_FILE.write_text(json.dumps({"lang": "zh"}), encoding="utf-8")
        second = cfg_mod.load_config()
        assert second["lang"] == "en"
        assert first is second  # same object


class TestSaveConfig:
    def test_writes_to_disk(self):
        cfg = cfg_mod.load_config()
        cfg["lang"] = "en"
        cfg_mod.save_config(cfg)
        on_disk = json.loads(cfg_mod._CONFIG_FILE.read_text(encoding="utf-8"))
        assert on_disk["lang"] == "en"

    def test_updates_cache(self):
        cfg = cfg_mod.load_config()
        cfg["theme"] = "light"
        cfg_mod.save_config(cfg)
        assert cfg_mod.load_config()["theme"] == "light"


class TestGetters:
    def test_get_queue_path(self):
        assert cfg_mod.get_queue_path() == cfg_mod._QUEUE_FILE

    def test_get_history_path(self):
        assert cfg_mod.get_history_path() == cfg_mod._HISTORY_FILE

    def test_get_download_dir(self):
        cfg_mod.load_config()
        d = cfg_mod.get_download_dir()
        assert isinstance(d, Path)
        assert "Lumio" in str(d)

    def test_get_storage_mode_default(self):
        assert cfg_mod.get_storage_mode() == "simple"

    def test_get_storage_mode_organized(self, tmp_path):
        cfg_mod._CONFIG_FILE.write_text(
            json.dumps({"storage_mode": "organized"}), encoding="utf-8"
        )
        assert cfg_mod.get_storage_mode() == "organized"

    def test_get_cookie_path_none_when_missing(self):
        cfg_mod._cache = None
        cfg = cfg_mod.load_config()
        cfg["cookie_file"] = str(cfg_mod._APP_DIR / "nonexistent_cookies.txt")
        cfg_mod.save_config(cfg)
        assert cfg_mod.get_cookie_path() is None

    def test_get_cookie_path_exists(self, tmp_path):
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("# Netscape cookie", encoding="utf-8")
        cfg_mod.load_config()
        cfg_mod._cache["cookie_file"] = str(cookie_file)
        assert cfg_mod.get_cookie_path() == cookie_file
