from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
        if "content" not in cols:
            try:
                with engine.connect() as conn:
                    conn.exec_driver_sql("ALTER TABLE inbox_items ADD COLUMN content VARCHAR DEFAULT ''")
                    conn.commit()
            except Exception as e:
                logger.warning("Inbox migration failed (content): %s", e)
        if "post_time" not in cols:
            try:
                with engine.connect() as conn:
                    conn.exec_driver_sql("ALTER TABLE inbox_items ADD COLUMN post_time VARCHAR DEFAULT ''")
                    conn.commit()
            except Exception as e:
                logger.warning("Inbox migration failed (post_time): %s", e)

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
        content: str = "",
        post_time: str = "",
        duration: int | None = None,
    ) -> str:
        """添加一条采集记录。URL 重复时重置状态为 new 并更新元数据。"""
        session = self._session()
        is_new = False
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
                content=content,
                post_time=post_time,
                duration=duration,
            )
            session.add(item)
            session.commit()
            item_id = item.id
            is_new = True
        except IntegrityError:
            session.rollback()
            existing = session.query(InboxItem).filter_by(url=url).first()
            if existing:
                # 重复 URL：更新元数据 + 重置状态为 new，让用户能在「新内容」筛选中看到
                existing.title = title or existing.title
                existing.author = author or existing.author
                existing.platform = platform or existing.platform
                existing.thumbnail_url = thumbnail_url or existing.thumbnail_url
                existing.direct_url = direct_url or existing.direct_url
                existing.content = content or existing.content
                existing.post_time = post_time or existing.post_time
                if duration is not None:
                    existing.duration = duration
                existing.status = "new"
                existing.error_message = ""
                existing.captured_at = datetime.now(timezone.utc)
                session.commit()
                item_id = existing.id
            else:
                item_id = ""
        finally:
            session.close()

        if item_id:
            if is_new:
                self.item_added.emit(item_id)
            else:
                # 重复 URL 重置状态后，同时 emit added + updated 让 UI 刷新
                self.item_added.emit(item_id)
                self.item_updated.emit(item_id)
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
        # 先收集 direct_url 指向的本地文件路径，删除记录后清理文件
        # 避免 inbox_media/ 中残留孤儿文件
        local_paths_to_clean: list[str] = []
        session = self._session()
        try:
            items = session.query(InboxItem).filter(InboxItem.id.in_(item_ids)).all()
            for item in items:
                if item.direct_url and "inbox_media" in item.direct_url:
                    local_paths_to_clean.append(item.direct_url)
            session.query(InboxItem).filter(InboxItem.id.in_(item_ids)).delete(
                synchronize_session=False
            )
            session.commit()
            self.items_deleted.emit(item_ids)
        finally:
            session.close()

        # 清理本地文件（在 session 关闭后执行，避免阻塞 DB）
        self._cleanup_local_files(local_paths_to_clean)

    def _cleanup_local_files(self, paths: list[str]) -> None:
        """清理 direct_url 指向的本地文件或文件夹。

        仅清理 inbox_media/ 目录内的文件，避免误删用户数据。
        """
        for p_str in paths:
            try:
                p = Path(p_str)
                if not p.exists():
                    continue
                # 安全检查：只清理 inbox_media/ 路径下的文件
                if "inbox_media" not in p.name and "inbox_media" not in str(p.parent):
                    continue
                if p.is_file():
                    p.unlink(missing_ok=True)
                elif p.is_dir():
                    # 相册文件夹：整个目录删除
                    shutil.rmtree(p, ignore_errors=True)
            except Exception:
                # 清理失败不影响主流程
                pass

    def cleanup_old(self, days: int = 30) -> int:
        """删除超过 N 天且状态为终态（downloaded/archived）的记录。"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        local_paths_to_clean: list[str] = []
        session = self._session()
        try:
            items = (
                session.query(InboxItem)
                .filter(
                    InboxItem.status.in_(["downloaded", "archived"]),
                    InboxItem.captured_at < cutoff,
                )
                .all()
            )
            for item in items:
                if item.direct_url and "inbox_media" in item.direct_url:
                    local_paths_to_clean.append(item.direct_url)
            # 重新执行 delete（前面 .all() 已消费查询，需重新 query）
            deleted = (
                session.query(InboxItem)
                .filter(
                    InboxItem.status.in_(["downloaded", "archived"]),
                    InboxItem.captured_at < cutoff,
                )
                .delete(synchronize_session=False)
            )
            session.commit()
        finally:
            session.close()

        # 清理本地文件
        self._cleanup_local_files(local_paths_to_clean)
        return deleted
