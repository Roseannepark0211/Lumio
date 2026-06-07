from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QObject, Signal
from sqlalchemy.exc import IntegrityError

from .models import InboxItem
from .utils.database import get_engine, get_session_factory

logger = logging.getLogger(__name__)


class InboxManager(QObject):
    """收件箱管理 — 接收浏览器/Telegram 采集的 URL，等待用户下载。"""

    item_added = Signal(str)      # inbox_item_id
    item_updated = Signal(str)    # inbox_item_id
    items_deleted = Signal(list)  # list of ids

    def __init__(self, parent=None):
        super().__init__(parent)
        self._migrate()

    def _migrate(self):
        """添加缺失的列。"""
        engine = get_engine()
        cols = set()
        try:
            with engine.connect() as conn:
                result = conn.exec_driver_sql("PRAGMA table_info(inbox_items)")
                cols = {row[1] for row in result}
        except Exception as e:
            logger.debug("Inbox migration check failed: %s", e)
            return
        if "direct_url" not in cols:
            try:
                with engine.connect() as conn:
                    conn.exec_driver_sql("ALTER TABLE inbox_items ADD COLUMN direct_url VARCHAR DEFAULT ''")
                    conn.commit()
            except Exception as e:
                logger.warning("Inbox migration failed (direct_url): %s", e)

    # ── session helper ──────────────────────────────────────────────

    def _session(self):
        return get_session_factory()()

    # ── CRUD ────────────────────────────────────────────────────────

    def add_item(
        self,
        url: str,
        *,
        source: str = "browser",
        type_: str = "url",
        title: str = "",
        author: str = "",
        platform: str = "",
        thumbnail_url: str = "",
        direct_url: str = "",
        duration: int | None = None,
    ) -> str:
        """添加一条采集记录。URL 重复时返回已有记录 id。"""
        session = self._session()
        try:
            item = InboxItem(
                source=source,
                type=type_,
                url=url,
                title=title,
                author=author,
                platform=platform,
                thumbnail_url=thumbnail_url,
                direct_url=direct_url,
                duration=duration,
            )
            session.add(item)
            session.commit()
            item_id = item.id
        except IntegrityError:
            session.rollback()
            existing = session.query(InboxItem).filter_by(url=url).first()
            item_id = existing.id if existing else ""
        finally:
            session.close()

        if item_id:
            self.item_added.emit(item_id)
        return item_id

    def get_pending(self) -> list[InboxItem]:
        return self.get_all(status_filter="new")

    def get_all(self, *, status_filter: str | None = None) -> list[InboxItem]:
        session = self._session()
        try:
            q = session.query(InboxItem)
            if status_filter:
                q = q.filter(InboxItem.status == status_filter)
            items = q.order_by(InboxItem.captured_at.desc()).all()
            session.expunge_all()
            return items
        finally:
            session.close()

    def get_item(self, item_id: str) -> InboxItem | None:
        session = self._session()
        try:
            item = session.query(InboxItem).get(item_id)
            if item:
                session.expunge(item)
            return item
        finally:
            session.close()

    def mark_status(self, item_id: str, status: str, error_message: str = "") -> None:
        session = self._session()
        try:
            item = session.query(InboxItem).get(item_id)
            if item:
                item.status = status
                item.error_message = error_message
                session.commit()
                self.item_updated.emit(item_id)
        finally:
            session.close()

    def update_item_info(self, item_id: str, **fields) -> None:
        """更新 InboxItem 的元数据字段（title/author/thumbnail_url 等）。"""
        if not fields:
            return
        session = self._session()
        try:
            item = session.query(InboxItem).get(item_id)
            if item:
                for k, v in fields.items():
                    if hasattr(item, k) and v:
                        setattr(item, k, v)
                session.commit()
                self.item_updated.emit(item_id)
        finally:
            session.close()

    def delete_item(self, item_id: str) -> None:
        self.delete_items([item_id])

    def delete_items(self, item_ids: list[str]) -> None:
        session = self._session()
        try:
            session.query(InboxItem).filter(InboxItem.id.in_(item_ids)).delete(
                synchronize_session=False
            )
            session.commit()
            self.items_deleted.emit(item_ids)
        finally:
            session.close()

    def cleanup_old(self, days: int = 30) -> int:
        """删除超过 N 天且状态为终态（downloaded/archived）的记录。"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        session = self._session()
        try:
            deleted = (
                session.query(InboxItem)
                .filter(
                    InboxItem.status.in_(["downloaded", "archived"]),
                    InboxItem.captured_at < cutoff,
                )
                .delete(synchronize_session=False)
            )
            session.commit()
            return deleted
        finally:
            session.close()
