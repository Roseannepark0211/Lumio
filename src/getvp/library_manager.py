from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from .models import ItemTag, LibraryItem, Tag
from .utils.config import get_history_path
from .utils.database import get_session_factory, init_db
from .utils.media_utils import infer_media_type

_MIGRATED_MARKER = Path.home() / ".getvp" / ".library_migrated"


class LibraryManager:
    def __init__(self):
        init_db()
        self._migrate_from_history_json()
        self._backfill_media_types()

    def _session(self):
        return get_session_factory()()

    def _backfill_media_types(self):
        """Fill in empty media_type for existing items."""
        session = self._session()
        try:
            items = session.query(LibraryItem).filter(
                (LibraryItem.media_type == "") | (LibraryItem.media_type.is_(None))
            ).all()
            if not items:
                return
            for item in items:
                mt = infer_media_type(item.file_path, item.platform)
                if mt:
                    item.media_type = mt
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
                media_type=media_type or infer_media_type(file_path, platform),
                duration=duration,
                post_time=post_time,
                thumbnail_url=thumbnail_url,
            )
            session.add(item)
            session.commit()
            item_id = item.id
        finally:
            session.close()
        # Auto-tag after commit (outside the session)
        self.auto_tag_item(item_id)
        return item_id

    def get_item(self, item_id: str) -> LibraryItem | None:
        session = self._session()
        try:
            return session.get(LibraryItem, item_id)
        finally:
            session.close()

    def get_all_items(self) -> list[LibraryItem]:
        session = self._session()
        try:
            items = (
                session.query(LibraryItem)
                .order_by(LibraryItem.is_pinned.desc(), LibraryItem.created_at.desc())
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

    # ---- Favorites & Pin ----

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

    def toggle_pinned(self, item_id: str) -> bool:
        session = self._session()
        try:
            item = session.get(LibraryItem, item_id)
            if not item:
                return False
            item.is_pinned = not item.is_pinned
            session.commit()
            return item.is_pinned
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

    # ---- Tags ----

    def auto_tag_item(self, item_id: str):
        session = self._session()
        try:
            item = session.get(LibraryItem, item_id)
            if not item:
                return
            # Only auto-tag with platform, not media_type (media_type has its own filter)
            if item.platform:
                self._ensure_tag_assoc(session, item_id, item.platform)
            self._sync_tags_json(session, item)
            session.commit()
        finally:
            session.close()

    def add_tag_to_item(self, item_id: str, tag_name: str, color: str = "#7c8fff"):
        session = self._session()
        try:
            self._ensure_tag_assoc(session, item_id, tag_name, color)
            item = session.get(LibraryItem, item_id)
            if item:
                self._sync_tags_json(session, item)
            session.commit()
        finally:
            session.close()

    def remove_tag_from_item(self, item_id: str, tag_name: str):
        session = self._session()
        try:
            tag = session.query(Tag).filter_by(name=tag_name).first()
            if tag:
                assoc = session.query(ItemTag).filter_by(item_id=item_id, tag_id=tag.id).first()
                if assoc:
                    session.delete(assoc)
            item = session.get(LibraryItem, item_id)
            if item:
                self._sync_tags_json(session, item)
            session.commit()
        finally:
            session.close()

    def get_item_tags(self, item_id: str) -> list[Tag]:
        session = self._session()
        try:
            assocs = session.query(ItemTag).filter_by(item_id=item_id).all()
            tags = [a.tag for a in assocs]
            session.expunge_all()
            return tags
        finally:
            session.close()

    def get_all_tags(self) -> list[Tag]:
        session = self._session()
        try:
            tags = session.query(Tag).order_by(Tag.name).all()
            session.expunge_all()
            return tags
        finally:
            session.close()

    def delete_tag(self, tag_id: int):
        session = self._session()
        try:
            tag = session.get(Tag, tag_id)
            if tag:
                session.delete(tag)
                session.commit()
        finally:
            session.close()

    # ---- Search ----

    def search(
        self,
        query: str = "",
        platform: str = "",
        media_type: str = "",
        favorites_only: bool = False,
        tag_name: str = "",
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
                )
            if platform:
                q = q.filter(LibraryItem.platform == platform)
            if media_type:
                q = q.filter(LibraryItem.media_type == media_type)
            if favorites_only:
                q = q.filter(LibraryItem.is_favorite.is_(True))
            if tag_name:
                q = q.join(ItemTag).join(Tag).filter(Tag.name == tag_name)
            items = q.order_by(LibraryItem.is_pinned.desc(), LibraryItem.created_at.desc()).all()
            session.expunge_all()
            return items
        finally:
            session.close()

    # ---- Internal helpers ----

    def _ensure_tag_assoc(self, session, item_id: str, tag_name: str, color: str = "#7c8fff"):
        tag = session.query(Tag).filter_by(name=tag_name).first()
        if not tag:
            tag = Tag(name=tag_name, color=color)
            session.add(tag)
            session.flush()
        existing = session.query(ItemTag).filter_by(item_id=item_id, tag_id=tag.id).first()
        if not existing:
            session.add(ItemTag(item_id=item_id, tag_id=tag.id))

    def _sync_tags_json(self, session, item: LibraryItem):
        assocs = session.query(ItemTag).filter_by(item_id=item.id).all()
        names = []
        for a in assocs:
            tag = session.get(Tag, a.tag_id)
            if tag:
                names.append(tag.name)
        item.tags_json = json.dumps(names)

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
