from __future__ import annotations

import json
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .models import Collection, ItemCollection, LibraryItem
from .utils.config import get_history_path
from .utils.database import get_session_factory, init_db
from .utils.media_utils import infer_media_type

_MIGRATED_MARKER = Path.home() / ".lumio" / ".library_migrated"


class LibraryManager(QObject):
    thumbnail_updated = Signal(str, str)  # item_id, local_path
    collection_changed = Signal()  # any collection content change

    def __init__(self):
        super().__init__()
        init_db()
        self._migrate_from_history_json()
        self._migrate_add_storage_fields()
        self._backfill_media_types()
        self.backfill_hashes()

    def _session(self):
        return get_session_factory()()

    def _backfill_media_types(self):
        """Fill in or correct media_type for existing items."""
        session = self._session()
        try:
            items = session.query(LibraryItem).all()
            changed = False
            for item in items:
                inferred = infer_media_type(item.file_path, item.platform)
                if inferred and inferred != item.media_type:
                    item.media_type = inferred
                    changed = True
            if changed:
                session.commit()
        finally:
            session.close()

    def backfill_thumbnails(self):
        """Generate thumbnails for all items missing one. Call from GUI thread."""
        session = self._session()
        try:
            items = session.query(LibraryItem).filter(
                (LibraryItem.local_thumbnail_path == "")
                | (LibraryItem.local_thumbnail_path.is_(None))
            ).all()
            if not items:
                return
            session.expunge_all()
        finally:
            session.close()
        from .thumbnail_engine import generate_thumbnail_async
        for item in items:
            if not item.file_path:
                continue
            generate_thumbnail_async(
                item.id, item.file_path, item.media_type,
                item.thumbnail_url or "", self.set_local_thumbnail,
            )

    def _migrate_add_storage_fields(self):
        """Add folder_path, batch_id, content_hash columns if missing."""
        from sqlalchemy import text
        session = self._session()
        try:
            existing = {row[1] for row in session.execute(text("PRAGMA table_info(library_items)")).fetchall()}
            if "folder_path" not in existing:
                session.execute(text("ALTER TABLE library_items ADD COLUMN folder_path TEXT DEFAULT ''"))
            if "batch_id" not in existing:
                session.execute(text("ALTER TABLE library_items ADD COLUMN batch_id TEXT DEFAULT ''"))
            if "content_hash" not in existing:
                session.execute(text("ALTER TABLE library_items ADD COLUMN content_hash TEXT"))
            session.commit()
        finally:
            session.close()

    # ---- CRUD ----

    def add_item(
        self,
        title: str = "",
        author: str = "",
        platform: str = "",
        url: str = "",
        file_path: str = "",
        file_size: int = 0,
        media_type: str = "",
        duration: int | None = None,
        post_time: str = "",
        thumbnail_url: str = "",
        folder_path: str = "",
        batch_id: str = "",
    ) -> str:
        session = self._session()
        try:
            item = LibraryItem(
                id=uuid.uuid4().hex[:12],
                title=title,
                author=author,
                platform=platform,
                url=url,
                file_path=file_path,
                file_size=file_size,
                media_type=infer_media_type(file_path, platform) or media_type,
                duration=duration,
                post_time=post_time,
                thumbnail_url=thumbnail_url,
                folder_path=folder_path,
                batch_id=batch_id,
            )
            session.add(item)
            session.commit()
            item_id = item.id
        finally:
            session.close()
        # Compute content hash for dedup
        if file_path:
            h = self.compute_content_hash(file_path)
            if h:
                self.set_content_hash(item_id, h)
        return item_id

    def get_item(self, item_id: str) -> LibraryItem | None:
        session = self._session()
        try:
            item = session.get(LibraryItem, item_id)
            if item:
                session.expunge(item)
            return item
        finally:
            session.close()

    def get_all_items(self) -> list[LibraryItem]:
        session = self._session()
        try:
            items = (
                session.query(LibraryItem)
                .order_by(LibraryItem.created_at.desc())
                .all()
            )
            # Detach from session so objects are usable outside
            session.expunge_all()
            return items
        finally:
            session.close()

    def delete_item(self, item_id: str):
        session = self._session()
        try:
            item = session.get(LibraryItem, item_id)
            if item:
                session.delete(item)
                session.commit()
        finally:
            session.close()
        self.collection_changed.emit()

    # ---- Favorites ----

    def toggle_favorite(self, item_id: str) -> bool:
        session = self._session()
        try:
            item = session.get(LibraryItem, item_id)
            if not item:
                return False
            item.is_favorite = not item.is_favorite
            session.commit()
            return item.is_favorite
        finally:
            session.close()

    # ---- Thumbnail ----

    def set_local_thumbnail(self, item_id: str, path: str):
        session = self._session()
        try:
            item = session.get(LibraryItem, item_id)
            if item:
                item.local_thumbnail_path = path
                session.commit()
        finally:
            session.close()
        self.thumbnail_updated.emit(item_id, path)

    # ---- Collections ----

    def create_collection(self, name: str, icon: str = "📁") -> int:
        session = self._session()
        try:
            col = Collection(name=name, icon=icon)
            session.add(col)
            session.commit()
            return col.id
        finally:
            session.close()

    def delete_collection(self, collection_id: int):
        session = self._session()
        try:
            col = session.get(Collection, collection_id)
            if col:
                session.delete(col)
                session.commit()
        finally:
            session.close()

    def rename_collection(self, collection_id: int, new_name: str):
        session = self._session()
        try:
            col = session.get(Collection, collection_id)
            if col:
                col.name = new_name
                session.commit()
        finally:
            session.close()

    def get_all_collections(self) -> list[Collection]:
        session = self._session()
        try:
            cols = session.query(Collection).order_by(Collection.name).all()
            session.expunge_all()
            return cols
        finally:
            session.close()

    def add_item_to_collection(self, item_id: str, collection_id: int):
        session = self._session()
        try:
            existing = session.query(ItemCollection).filter_by(
                item_id=item_id, collection_id=collection_id
            ).first()
            if not existing:
                session.add(ItemCollection(item_id=item_id, collection_id=collection_id))
                session.commit()
        finally:
            session.close()
        self.collection_changed.emit()

    def remove_item_from_collection(self, item_id: str, collection_id: int):
        session = self._session()
        try:
            assoc = session.query(ItemCollection).filter_by(
                item_id=item_id, collection_id=collection_id
            ).first()
            if assoc:
                session.delete(assoc)
                session.commit()
        finally:
            session.close()
        self.collection_changed.emit()

    def get_collection_items(self, collection_id: int) -> list[LibraryItem]:
        session = self._session()
        try:
            items = (
                session.query(LibraryItem)
                .join(ItemCollection)
                .filter(ItemCollection.collection_id == collection_id)
                .order_by(LibraryItem.created_at.desc())
                .all()
            )
            session.expunge_all()
            return items
        finally:
            session.close()

    def get_item_collections(self, item_id: str) -> list[Collection]:
        session = self._session()
        try:
            assocs = session.query(ItemCollection).filter_by(item_id=item_id).all()
            cols = [a.collection for a in assocs]
            session.expunge_all()
            return cols
        finally:
            session.close()

    def is_item_in_collection(self, item_id: str, collection_id: int) -> bool:
        session = self._session()
        try:
            return session.query(ItemCollection).filter_by(
                item_id=item_id, collection_id=collection_id
            ).first() is not None
        finally:
            session.close()

    def get_collection_stats(self, collection_id: int) -> tuple[int, int]:
        """Return (item_count, total_size) for a collection."""
        session = self._session()
        try:
            items = (
                session.query(LibraryItem)
                .join(ItemCollection)
                .filter(ItemCollection.collection_id == collection_id)
                .all()
            )
            return (len(items), sum(i.file_size or 0 for i in items))
        finally:
            session.close()

    # ---- Dedup ----

    def url_exists(self, url: str) -> bool:
        session = self._session()
        try:
            return session.query(LibraryItem).filter_by(url=url).first() is not None
        finally:
            session.close()

    def compute_content_hash(self, file_path: str) -> str:
        """Compute content hash. Images: full MD5. Video/audio: first 1MB + size."""
        import hashlib
        p = Path(file_path)
        if p.is_dir():
            # Hash first media file in directory
            media_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.mp4', '.mkv', '.webm', '.mov', '.mp3', '.wav', '.aac', '.flac', '.ogg'}
            files = sorted(f for f in p.iterdir() if f.suffix.lower() in media_exts)
            if not files:
                return ""
            p = files[0]
        if not p.exists():
            return ""
        ext = p.suffix.lower()
        img_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
        try:
            h = hashlib.md5()
            if ext in img_exts:
                h.update(p.read_bytes())
            else:
                with open(p, "rb") as f:
                    h.update(f.read(1024 * 1024))
                h.update(str(p.stat().st_size).encode())
            return h.hexdigest()
        except OSError:
            return ""

    def set_content_hash(self, item_id: str, content_hash: str):
        session = self._session()
        try:
            item = session.get(LibraryItem, item_id)
            if item:
                item.content_hash = content_hash
                session.commit()
        finally:
            session.close()

    def backfill_hashes(self):
        """Compute content_hash for all items missing one."""
        session = self._session()
        try:
            items = session.query(LibraryItem).filter(
                (LibraryItem.content_hash == "") | (LibraryItem.content_hash.is_(None))
            ).all()
            if not items:
                return
            session.expunge_all()
        finally:
            session.close()
        for item in items:
            if item.file_path:
                h = self.compute_content_hash(item.file_path)
                if h:
                    self.set_content_hash(item.id, h)

    # ---- Batch info ----

    def get_all_batch_ids(self) -> list[str]:
        """Return distinct non-empty batch_ids."""
        session = self._session()
        try:
            rows = (
                session.query(LibraryItem.batch_id)
                .filter(LibraryItem.batch_id != "")
                .distinct()
                .all()
            )
            return [r[0] for r in rows]
        finally:
            session.close()

    def batch_toggle_favorite(self, item_ids: list[str], state: bool):
        session = self._session()
        try:
            for item in session.query(LibraryItem).filter(LibraryItem.id.in_(item_ids)).all():
                item.is_favorite = state
            session.commit()
        finally:
            session.close()

    def batch_delete(self, item_ids: list[str]):
        session = self._session()
        try:
            for item in session.query(LibraryItem).filter(LibraryItem.id.in_(item_ids)).all():
                session.delete(item)
            session.commit()
        finally:
            session.close()
        self.collection_changed.emit()

    # ---- Search ----

    def search(
        self,
        query: str = "",
        platform: str = "",
        media_type: str = "",
        favorites_only: bool = False,
        collection_id: int | None = None,
        date_from: str = "",
        date_to: str = "",
        batch_id: str = "",
    ) -> list[LibraryItem]:
        session = self._session()
        try:
            q = session.query(LibraryItem)
            if query:
                like = f"%{query}%"
                q = q.filter(
                    (LibraryItem.title.ilike(like))
                    | (LibraryItem.author.ilike(like))
                    | (LibraryItem.url.ilike(like))
                    | (LibraryItem.file_path.ilike(like))
                    | (LibraryItem.post_time.ilike(like))
                )
            if platform:
                q = q.filter(LibraryItem.platform == platform)
            if media_type:
                q = q.filter(LibraryItem.media_type == media_type)
            if favorites_only:
                q = q.filter(LibraryItem.is_favorite.is_(True))
            if collection_id is not None:
                q = q.join(ItemCollection).filter(ItemCollection.collection_id == collection_id)
            if date_from:
                q = q.filter(
                    (LibraryItem.post_time >= date_from) | (LibraryItem.post_time == "")
                )
            if date_to:
                q = q.filter(
                    (LibraryItem.post_time <= date_to + "z") | (LibraryItem.post_time == "")
                )
            if batch_id:
                q = q.filter(LibraryItem.batch_id == batch_id)
            items = q.order_by(LibraryItem.created_at.desc()).all()
            session.expunge_all()
            return items
        finally:
            session.close()

    # ---- Migration ----

    def _migrate_from_history_json(self):
        if _MIGRATED_MARKER.exists():
            return
        history_path = get_history_path()
        if not history_path.exists():
            _MIGRATED_MARKER.touch()
            return
        # Only migrate if library is empty
        session = self._session()
        try:
            count = session.query(LibraryItem).count()
            if count > 0:
                _MIGRATED_MARKER.touch()
                return
        finally:
            session.close()

        try:
            with open(history_path, encoding="utf-8") as f:
                records = json.load(f)
        except Exception:
            _MIGRATED_MARKER.touch()
            return

        for rec in records:
            media_type = infer_media_type(rec.get("file_path", ""), rec.get("platform", ""))
            self.add_item(
                title=rec.get("title", ""),
                author=rec.get("author", ""),
                platform=rec.get("platform", ""),
                url=rec.get("url", ""),
                file_path=rec.get("file_path", ""),
                file_size=rec.get("file_size", 0),
                media_type=media_type,
                post_time=rec.get("download_time", ""),
                thumbnail_url=rec.get("thumbnail_url", ""),
            )
        _MIGRATED_MARKER.touch()
