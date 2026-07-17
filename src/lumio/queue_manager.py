from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Signal

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .downloader import DownloadTask, start_download_with_pause
from .history_manager import HistoryManager, HistoryRecord
from .utils.config import get_queue_path, load_config


class _ConflictAskHandler(QObject):
    """Bridges downloader's conflict-ask to main-thread dialog."""
    conflict_detected = Signal(str)  # file_path

    def __init__(self):
        super().__init__()
        self._event = threading.Event()
        self._result = "rename"

    def register(self):
        from . import downloader
        downloader._conflict_ask_handler = self._handle

    def _handle(self, file_path: Path) -> str:
        self._result = "rename"
        self._event.clear()
        self.conflict_detected.emit(str(file_path))
        self._event.wait()
        return self._result

    def respond(self, choice: str):
        self._result = choice
        self._event.set()


class TaskStatus(str, Enum):
    WAITING = "等待中"
    DOWNLOADING = "下载中"
    PAUSED = "暂停中"
    RETRYING = "重试中"
    INTERRUPTED = "已中断"
    COMPLETED = "已完成"
    FAILED = "失败"
    CANCELLED = "已取消"


_RETRY_INTERVALS = [5, 15, 30]  # exponential backoff in seconds


@dataclass
class QueueTask:
    task_id: str = ""
    url: str = ""
    format_id: str | None = None
    format_type: str = ""
    output_dir: str = ""
    custom_name: str = ""
    batch_id: str = ""
    direct_url: str = ""  # Pre-resolved download URL (e.g. from X-Sou)
    media_items_json: str = ""  # Pre-resolved media items JSON (Apify, avoids re-fetching)

    # Display metadata (frozen at enqueue time)
    title: str = ""
    platform: str = ""
    author: str = ""
    post_time: str = ""
    thumbnail_url: str | None = None

    # State
    status: str = TaskStatus.WAITING.value
    progress: float = 0.0
    speed: str = ""
    filename: str = ""
    error: str = ""
    error_category: str = ""

    # Scheduling
    retry_count: int = 0
    max_retries: int = 3
    retry_interval: float = 3.0
    created_at: float = 0.0

    def __post_init__(self):
        if not self.task_id:
            self.task_id = uuid.uuid4().hex[:12]
        if not self.created_at:
            self.created_at = time.time()

    def to_download_task(self) -> DownloadTask:
        from .downloader import DownloadTask
        return DownloadTask(
            url=self.url,
            format_id=self.format_id,
            output_dir=Path(self.output_dir),
            custom_name=self.custom_name,
            author=self.author,
            post_time=self.post_time,
            format_type=self.format_type,
            platform=self.platform,
            batch_id=self.batch_id,
            direct_url=self.direct_url,
            media_items_json=self.media_items_json,
        )

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "url": self.url,
            "format_id": self.format_id,
            "format_type": self.format_type,
            "output_dir": self.output_dir,
            "custom_name": self.custom_name,
            "batch_id": self.batch_id,
            "direct_url": self.direct_url,
            "media_items_json": self.media_items_json,
            "title": self.title,
            "platform": self.platform,
            "author": self.author,
            "post_time": self.post_time,
            "thumbnail_url": self.thumbnail_url,
            "status": self.status,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> QueueTask:
        qt = cls()
        for k, v in d.items():
            if hasattr(qt, k):
                setattr(qt, k, v)
        # Reset downloading tasks to interrupted on restore
        if qt.status == TaskStatus.DOWNLOADING.value:
            qt.status = TaskStatus.INTERRUPTED.value
        qt.progress = 0.0
        qt.speed = ""
        qt.filename = ""
        qt.error = ""
        qt.error_category = ""
        qt.retry_count = 0  # reset retry count on restore
        return qt


class DownloadManager(QObject):
    task_added = Signal(str)
    task_started = Signal(str)
    task_progress = Signal(str, float, str, str)   # task_id, progress, speed, filename
    task_finished = Signal(str, bool, str)           # task_id, success, error
    task_status_changed = Signal(str, str)           # task_id, new_status
    queue_changed = Signal()
    batch_progress = Signal(int, int, int)           # completed, failed, total
    history_record_added = Signal(object)            # HistoryRecord
    library_record_added = Signal(object)            # LibraryItem
    conflict_ask = Signal(str)                       # file_path, respond via conflict_resolved

    def __init__(self, history_manager: HistoryManager | None = None, parent=None):
        super().__init__(parent)
        self._tasks: dict[str, QueueTask] = {}
        self._active: dict[str, threading.Thread] = {}
        self._download_tasks: dict[str, DownloadTask] = {}
        self._paused_events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._history_manager = history_manager
        self._library_manager = None

        # Register conflict-ask handler
        self._conflict_handler = _ConflictAskHandler()
        self._conflict_handler.moveToThread(self.thread())
        self._conflict_handler.conflict_detected.connect(self.conflict_ask)
        self._conflict_handler.register()

        cfg = load_config()
        self._max_workers: int = cfg.get("max_concurrent", 3)
        self._max_retries: int = cfg.get("max_retries", 3)

    # ---- Public API ----

    def set_history_manager(self, hm: HistoryManager):
        self._history_manager = hm

    def set_library_manager(self, lm):
        self._library_manager = lm

    def resolve_conflict(self, choice: str):
        """Respond to conflict_ask signal. choice: 'rename'/'skip'/'overwrite'."""
        self._conflict_handler.respond(choice)

    def check_url_duplicate(self, url: str) -> bool:
        if self._library_manager:
            return self._library_manager.url_exists(url)
        return False

    def set_max_workers(self, n: int):
        self._max_workers = max(1, min(10, n))
        self._schedule()

    def add_task_from_info(self, info, format_id, format_type, custom_name, output_dir, batch_id="") -> str:
        media_json = ""
        # Serialize media items for all platforms (IG Apify, Weibo, Bilibili, etc.)
        # avoids re-fetching during download
        if info.items:
            import json as _json
            media_json = _json.dumps([
                {"url": it.url, "is_video": it.is_video, "index": it.index}
                for it in info.items
            ])
        qt = QueueTask(
            url=info.url,
            format_id=format_id,
            format_type=format_type,
            output_dir=str(output_dir),
            custom_name=custom_name,
            batch_id=batch_id,
            title=info.title,
            platform=info.platform,
            author=info.author,
            post_time=info.post_time,
            thumbnail_url=info.thumbnail,
            max_retries=self._max_retries,
            media_items_json=media_json,
        )
        return self.add_task(qt)

    def add_task(self, qt: QueueTask) -> str:
        with self._lock:
            self._tasks[qt.task_id] = qt
        self.task_added.emit(qt.task_id)
        self.queue_changed.emit()
        # Do NOT auto-schedule — user starts manually
        return qt.task_id

    def get_task(self, task_id: str) -> QueueTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[QueueTask]:
        with self._lock:
            return list(self._tasks.values())

    def start_task(self, task_id: str):
        qt_to_launch = None
        with self._lock:
            qt = self._tasks.get(task_id)
            if not qt:
                return
            # PAUSED with active thread → just unblock, don't spawn a second thread
            if qt.status == TaskStatus.PAUSED.value and task_id in self._active:
                event = self._paused_events.get(task_id)
                if event:
                    event.set()
                qt.status = TaskStatus.DOWNLOADING.value
                self.task_status_changed.emit(task_id, qt.status)
                return
            if qt.status not in (TaskStatus.WAITING.value, TaskStatus.PAUSED.value):
                return
            qt.status = TaskStatus.DOWNLOADING.value
            qt_to_launch = qt
        self.task_status_changed.emit(task_id, qt_to_launch.status)
        self._launch_download(qt_to_launch)

    def pause_task(self, task_id: str):
        with self._lock:
            event = self._paused_events.get(task_id)
            if event:
                event.clear()
            qt = self._tasks.get(task_id)
            if qt:
                qt.status = TaskStatus.PAUSED.value
        if qt:
            self.task_status_changed.emit(task_id, TaskStatus.PAUSED.value)
            self.queue_changed.emit()

    def resume_task(self, task_id: str):
        with self._lock:
            qt = self._tasks.get(task_id)
            if not qt:
                return
            if qt.status == TaskStatus.PAUSED.value:
                # Thread is alive but blocked — just unblock it
                event = self._paused_events.get(task_id)
                if event:
                    event.set()
                qt.status = TaskStatus.DOWNLOADING.value
                self.task_status_changed.emit(task_id, qt.status)
            elif qt.status == TaskStatus.INTERRUPTED.value:
                # Thread is dead — schedule a fresh download
                qt.status = TaskStatus.WAITING.value
                self.task_status_changed.emit(task_id, qt.status)
                self._schedule()

    def cancel_task(self, task_id: str):
        qt = None
        with self._lock:
            dt = self._download_tasks.get(task_id)
            if dt:
                dt._cancelled = True
            qt = self._tasks.get(task_id)
            if qt:
                qt.status = TaskStatus.CANCELLED.value
            self._do_cleanup(task_id)
        if qt:
            self.task_status_changed.emit(task_id, TaskStatus.CANCELLED.value)
        self.queue_changed.emit()

    def retry_task(self, task_id: str):
        with self._lock:
            qt = self._tasks.get(task_id)
            if not qt:
                return
            qt.retry_count = 0
            qt.progress = 0.0
            qt.speed = ""
            qt.error = ""
            qt.status = TaskStatus.WAITING.value
        self.task_status_changed.emit(task_id, TaskStatus.WAITING.value)
        self._schedule()

    def delete_task(self, task_id: str):
        self.cancel_task(task_id)
        with self._lock:
            self._tasks.pop(task_id, None)
        self.queue_changed.emit()

    def start_all(self):
        need_schedule = False
        to_emit = []
        with self._lock:
            for qt in self._tasks.values():
                if qt.status == TaskStatus.PAUSED.value and qt.task_id in self._active:
                    # Thread alive but paused — just unblock it
                    event = self._paused_events.get(qt.task_id)
                    if event:
                        event.set()
                    qt.status = TaskStatus.DOWNLOADING.value
                    to_emit.append((qt.task_id, qt.status))
                elif qt.status in (TaskStatus.WAITING.value, TaskStatus.PAUSED.value):
                    qt.status = TaskStatus.WAITING.value
                    need_schedule = True
        if need_schedule:
            self._schedule()
        # Update UI for any tasks that didn't get launched (not enough slots)
        with self._lock:
            for qt in self._tasks.values():
                if qt.status == TaskStatus.WAITING.value:
                    to_emit.append((qt.task_id, qt.status))
        for tid, status in to_emit:
            self.task_status_changed.emit(tid, status)

    def pause_all(self):
        to_pause = []
        with self._lock:
            for qt in self._tasks.values():
                if qt.status == TaskStatus.DOWNLOADING.value:
                    to_pause.append(qt.task_id)
        for tid in to_pause:
            self.pause_task(tid)

    def resume_all(self):
        to_resume = []
        with self._lock:
            for qt in self._tasks.values():
                if qt.status == TaskStatus.PAUSED.value:
                    to_resume.append(qt.task_id)
        for tid in to_resume:
            self.resume_task(tid)

    def resume_interrupted(self):
        to_resume = []
        with self._lock:
            for qt in self._tasks.values():
                if qt.status == TaskStatus.INTERRUPTED.value:
                    to_resume.append(qt.task_id)
        for tid in to_resume:
            self.resume_task(tid)

    def clear_completed(self):
        with self._lock:
            to_remove = [
                tid for tid, qt in self._tasks.items()
                if qt.status == TaskStatus.COMPLETED.value
            ]
            for tid in to_remove:
                self._tasks.pop(tid, None)
        self.queue_changed.emit()

    # ---- Persistence ----

    def save_queue(self):
        with self._lock:
            tasks_to_save = [
                qt.to_dict() for qt in self._tasks.values()
                if qt.status in (TaskStatus.WAITING.value, TaskStatus.PAUSED.value)
            ]
        path = get_queue_path()
        data = {"version": 1, "tasks": tasks_to_save}
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)

    def load_queue(self):
        path = get_queue_path()
        if not path.exists():
            return

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        with self._lock:
            for d in data.get("tasks", []):
                qt = QueueTask.from_dict(d)
                if qt.status not in (TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value):
                    self._tasks[qt.task_id] = qt

        self.queue_changed.emit()

    def shutdown(self):
        with self._lock:
            for tid in list(self._active.keys()):
                dt = self._download_tasks.get(tid)
                if dt:
                    dt._cancelled = True
        self.save_queue()

    # ---- Internal ----

    def _launch_download(self, qt: QueueTask):
        qt.progress = 0.0
        qt.speed = ""
        qt.error = ""

        event = threading.Event()
        event.set()
        self._paused_events[qt.task_id] = event

        dt = qt.to_download_task()
        self._download_tasks[qt.task_id] = dt

        def on_progress(t: DownloadTask):
            qt.progress = t.progress
            qt.speed = t.speed
            qt.filename = t.filename
            self.task_progress.emit(qt.task_id, t.progress, t.speed, t.filename)

        def on_done(t: DownloadTask):
            qt.filename = t.filename  # sync final filename
            self._cleanup_task(qt.task_id)

            # Verify file actually exists before marking success
            file_valid = False
            if t.status == "done" and qt.filename:
                p = Path(qt.filename)
                file_valid = p.exists() and (p.is_file() or p.is_dir())

            if file_valid:
                qt.status = TaskStatus.COMPLETED.value
                qt.progress = 100
                self._record_history(qt)
                self.task_finished.emit(qt.task_id, True, "")
            else:
                qt.retry_count += 1
                if qt.retry_count < qt.max_retries:
                    qt.status = TaskStatus.RETRYING.value
                    qt.progress = 0.0
                    self.task_status_changed.emit(qt.task_id, qt.status)
                    delay = _RETRY_INTERVALS[min(qt.retry_count - 1, len(_RETRY_INTERVALS) - 1)]
                    timer = threading.Timer(delay, self._schedule)
                    timer.daemon = True
                    timer.start()
                    return  # don't count as finished yet
                else:
                    from .utils.error_types import classify_error
                    qt.status = TaskStatus.FAILED.value
                    qt.error = t.error
                    qt.error_category = classify_error(t.error).value
                    self.task_finished.emit(qt.task_id, False, t.error)
            self._emit_batch_progress()

        from .downloader import start_download_with_pause
        thread = start_download_with_pause(dt, event, on_progress=on_progress, on_done=on_done)
        with self._lock:
            self._active[qt.task_id] = thread
        self.task_status_changed.emit(qt.task_id, qt.status)
        self.task_started.emit(qt.task_id)

    def _cleanup_task(self, task_id: str):
        with self._lock:
            self._do_cleanup(task_id)

    def _do_cleanup(self, task_id: str):
        self._active.pop(task_id, None)
        self._download_tasks.pop(task_id, None)
        self._paused_events.pop(task_id, None)

    def _record_history(self, qt: QueueTask):
        file_size = 0
        if qt.filename:
            try:
                p = Path(qt.filename)
                if p.is_file():
                    file_size = p.stat().st_size
                elif p.is_dir():
                    file_size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
            except OSError:
                pass

        # History (JSON)
        if self._history_manager:
            record = HistoryRecord(
                title=qt.title,
                author=qt.author,
                platform=qt.platform,
                url=qt.url,
                file_path=qt.filename,
                file_size=file_size,
                thumbnail_url=qt.thumbnail_url or "",
                batch_id=qt.batch_id or "",
            )
            self._history_manager.add(record)
            self.history_record_added.emit(record)

        # Library (SQLite) — auto-ingest
        if self._library_manager:
            try:
                item_id = self._library_manager.add_item(
                    title=qt.title,
                    author=qt.author,
                    platform=qt.platform,
                    url=qt.url,
                    file_path=qt.filename,
                    file_size=file_size,
                    post_time=qt.post_time,
                    thumbnail_url=qt.thumbnail_url or "",
                    folder_path=qt.output_dir,
                    batch_id=qt.batch_id,
                )
            except Exception as e:
                return
            item = self._library_manager.get_item(item_id)
            if item:
                self.library_record_added.emit(item)
                # Schedule async thumbnail generation
                from .thumbnail_engine import generate_thumbnail_async
                generate_thumbnail_async(
                    item_id, qt.filename, item.media_type, qt.thumbnail_url or "",
                    self._on_thumbnail_ready,
                )

    def _on_thumbnail_ready(self, item_id: str, local_path: str):
        if self._library_manager:
            self._library_manager.set_local_thumbnail(item_id, local_path)

    def _schedule(self):
        # Phase 1: under lock, collect which tasks to launch
        to_launch = []
        with self._lock:
            while len(self._active) < self._max_workers:
                next_qt = self._next_waiting_task()
                if not next_qt:
                    break
                # Mark as downloading immediately to prevent re-selection
                next_qt.status = TaskStatus.DOWNLOADING.value
                to_launch.append(next_qt)

        # Phase 2: outside lock, launch downloads (signals may re-enter)
        for qt in to_launch:
            self._launch_download(qt)

    def _next_waiting_task(self) -> QueueTask | None:
        candidates = [
            qt for qt in self._tasks.values()
            if qt.status in (TaskStatus.WAITING.value, TaskStatus.RETRYING.value)
            and qt.task_id not in self._active
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda q: q.created_at)

    def _emit_batch_progress(self):
        with self._lock:
            total = len(self._tasks)
            completed = sum(1 for qt in self._tasks.values() if qt.status == TaskStatus.COMPLETED.value)
            failed = sum(1 for qt in self._tasks.values() if qt.status == TaskStatus.FAILED.value)
        self.batch_progress.emit(completed, failed, total)
