"""Tests for library_manager.py — CRUD, collections, search."""
import json
import time
import pytest
from pathlib import Path
from unittest.mock import patch

import lumio.utils.database as db_mod
import lumio.library_manager as lm_mod
from lumio.library_manager import LibraryManager


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    """Create a fresh SQLite database for each test."""
    db_path = tmp_path / "library.db"
    marker = tmp_path / ".library_migrated"

    monkeypatch.setattr(db_mod, "_DB_PATH", db_path)
    db_mod._engine = None
    db_mod._session_factory = None

    monkeypatch.setattr(lm_mod, "_MIGRATED_MARKER", marker)
    monkeypatch.setattr(
        "lumio.library_manager.get_history_path",
        lambda: tmp_path / "history.json",
    )
    yield
    db_mod._engine = None
    db_mod._session_factory = None


@pytest.fixture
def lm():
    return LibraryManager()


class TestAddAndGet:
    def test_add_item_returns_id(self, lm):
        item_id = lm.add_item(
            title="Test Video",
            author="alice",
            platform="youtube",
            url="https://youtube.com/watch?v=abc",
            file_path="/tmp/video.mp4",
            media_type="video",
        )
        assert len(item_id) == 12

    def test_get_item(self, lm):
        item_id = lm.add_item(title="My Post", author="bob", platform="instagram")
        item = lm.get_item(item_id)
        assert item is not None
        assert item.title == "My Post"
        assert item.author == "bob"

    def test_get_nonexistent(self, lm):
        assert lm.get_item("nope") is None

    def test_add_with_folder_path_and_batch_id(self, lm):
        item_id = lm.add_item(
            title="Organized",
            folder_path="/downloads/alice_20260601/",
            batch_id="batch123456",
        )
        item = lm.get_item(item_id)
        assert item.folder_path == "/downloads/alice_20260601/"
        assert item.batch_id == "batch123456"


class TestDelete:
    def test_delete_existing(self, lm):
        item_id = lm.add_item(title="Doomed")
        lm.delete_item(item_id)
        assert lm.get_item(item_id) is None

    def test_delete_nonexistent(self, lm):
        lm.delete_item("nope")  # should not raise


class TestFavorites:
    def test_toggle_favorite(self, lm):
        item_id = lm.add_item(title="Fav")
        assert lm.toggle_favorite(item_id) is True
        assert lm.get_item(item_id).is_favorite is True
        assert lm.toggle_favorite(item_id) is False


class TestCollections:
    def test_create_collection(self, lm):
        cid = lm.create_collection("Inspiration", icon="💡")
        assert isinstance(cid, int)
        cols = lm.get_all_collections()
        assert any(c.name == "Inspiration" for c in cols)

    def test_add_item_to_collection(self, lm):
        cid = lm.create_collection("Travel")
        item_id = lm.add_item(title="Paris")
        lm.add_item_to_collection(item_id, cid)
        assert lm.is_item_in_collection(item_id, cid)
        items = lm.get_collection_items(cid)
        assert len(items) == 1

    def test_remove_item_from_collection(self, lm):
        cid = lm.create_collection("C")
        item_id = lm.add_item(title="X")
        lm.add_item_to_collection(item_id, cid)
        lm.remove_item_from_collection(item_id, cid)
        assert not lm.is_item_in_collection(item_id, cid)

    def test_rename_collection(self, lm):
        cid = lm.create_collection("Old")
        lm.rename_collection(cid, "New")
        cols = lm.get_all_collections()
        assert any(c.name == "New" for c in cols)

    def test_delete_collection(self, lm):
        cid = lm.create_collection("Gone")
        lm.delete_collection(cid)
        assert len(lm.get_all_collections()) == 0

    def test_no_duplicate_assoc(self, lm):
        cid = lm.create_collection("C")
        item_id = lm.add_item(title="X")
        lm.add_item_to_collection(item_id, cid)
        lm.add_item_to_collection(item_id, cid)  # add again
        items = lm.get_collection_items(cid)
        assert len(items) == 1


class TestDedup:
    def test_url_exists(self, lm):
        lm.add_item(title="V", url="https://youtube.com/watch?v=abc")
        assert lm.url_exists("https://youtube.com/watch?v=abc")

    def test_url_not_exists(self, lm):
        assert not lm.url_exists("https://youtube.com/watch?v=zzz")


class TestSearch:
    def test_search_by_query(self, lm):
        lm.add_item(title="Cafe in Tokyo", author="alice")
        lm.add_item(title="NYC Vlog", author="bob")
        results = lm.search(query="tokyo")
        assert len(results) == 1
        assert results[0].title == "Cafe in Tokyo"

    def test_search_by_platform(self, lm):
        lm.add_item(title="A", platform="youtube")
        lm.add_item(title="B", platform="instagram")
        results = lm.search(platform="youtube")
        assert len(results) == 1

    def test_search_by_favorites(self, lm):
        item_id = lm.add_item(title="Fav")
        lm.toggle_favorite(item_id)
        lm.add_item(title="NotFav")
        results = lm.search(favorites_only=True)
        assert len(results) == 1

    def test_search_combined(self, lm):
        lm.add_item(title="Travel Vlog", platform="youtube", author="alice")
        lm.add_item(title="Food Pic", platform="instagram", author="alice")
        results = lm.search(query="alice", platform="youtube")
        assert len(results) == 1
        assert results[0].title == "Travel Vlog"


class TestGetAllItems:
    def test_newer_first(self, lm):
        id1 = lm.add_item(title="Older")
        time.sleep(0.05)  # ensure distinct created_at
        id2 = lm.add_item(title="Newer")
        items = lm.get_all_items()
        assert items[0].title == "Newer"
