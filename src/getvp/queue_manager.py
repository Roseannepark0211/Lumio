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

from .downloader import DownloadTask, start_download_with_pause
from .history_manager import HistoryManager, HistoryRecord
from .utils.config import get_queue_path, load_config


class TaskStatus(str, Enum):
    WAITING = "等待中"
    DOWNLOADING = "下载中"
    PAUSED = "暂停中"
    COMPLETED = "已完成"
    FAILED = "失败"
    CANCELLED = "已取消"


@dataclass
class QueueTask:
    task_id: str = ""
    url: str = ""
    format_id: str | None = None
    format_type: str = ""
    output_dir: str = ""
    custom_name: str = ""

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
        return DownloadTask(
            url=self.url,
            format_id=self.format_id,
            output_dir=Path(self.output_dir),
            custom_name=self.custom_name,
            author=self.author,
            post_time=self.post_time,
            format_type=self.format_type,
        )

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "url": self.url,
            "format_id": self.format_id,
            "format_type": self.format_type,
            "output_dir": self.output_dir,
            "custom_name": self.custom_name,
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
        # Reset downloading tasks to waiting on restore
        if qt.status == TaskStatus.DOWNLOADING.value:
            qt.status = TaskStatus.WAITING.value
        qt.progress = 0.0
        qt.speed = ""
        qt.filename = ""
        qt.error = ""
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

    def __init__(self, history_manager: HistoryManager | None = None, parent=None):
        super().__init__(parent)
        self._tasks: dict[str, QueueTask] = {}
        self._active: dict[str, threading.Thread] = {}
        self._download_tasks: dict[str, DownloadTask] = {}
        self._paused_events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._history_manager = history_manager

        cfg = load_config()
        self._max_workers: int = cfg.get("max_concurrent", 3)
        self._max_retries: int = cfg.get("max_retries", 3)

    # ---- Public API ----

    def set_history_manager(self, hm: HistoryManager):
        self._history_manager = hm

    def set_max_workers(self, n: int):
        self._max_workers = max(1, min(10, n))
        self._schedule()

    def add_task_from_info(self, info, format_id, format_type, custom_name, output_dir) -> str:
        qt = QueueTask(
            url=info.url,
            format_id=format_id,
            format_type=format_type,
            output_dir=str(output_dir),
            custom_name=custom_name,
            title=info.title,
            platform=info.platform,
            author=info.author,
            post_time=info.post_time,
            thumbnail_url=info.thumbnail,
            max_retries=self._max_retries,
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
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[QueueTask]:
        with self._lock:
            return list(self._tasks.values())

    def start_task(self, task_id: str):
        qt = self._tasks.get(task_id)
        if not qt or qt.status not in (
            TaskStatus.WAITING.value, TaskStatus.PAUSED.value
        ):
            return
        qt.status = TaskStatus.DOWNLOADING.value
        self.task_status_changed.emit(task_id, qt.status)
        self._launch_download(qt)

    def pause_task(self, task_id: str):
        event = self._paused_events.get(task_id)
        if event:
            event.clear()
        qt = self._tasks.get(task_id)
        if qt:
            qt.status = TaskStatus.PAUSED.value
            self.task_status_changed.emit(task_id, qt.status)
            self.queue_changed.emit()

    def resume_task(self, task_id: str):
        event = self._paused_events.get(task_id)
        if event:
            event.set()
        qt = self._tasks.get(task_id)
        if qt and qt.status == TaskStatus.PAUSED.value:
            qt.status = TaskStatus.DOWNLOADING.value
            self.task_status_changed.emit(task_id, qt.status)
            self._launch_download(qt)

    def cancel_task(self, task_id: str):
        dt = self._download_tasks.get(task_id)
        if dt:
            dt._cancelled = True
        qt = self._tasks.get(task_id)
        if qt:
            qt.status = TaskStatus.CANCELLED.value
            self.task_status_changed.emit(task_id, qt.status)
        self._cleanup_task(task_id)
        self.queue_changed.emit()

    def retry_task(self, task_id: str):
        qt = self._tasks.get(task_id)
        if not qt:
            return
        qt.retry_count = 0
        qt.progress = 0.0
        qt.speed = ""
        qt.error = ""
        qt.status = TaskStatus.DOWNLOADING.value
        self.task_status_changed.emit(task_id, qt.status)
        self._launch_download(qt)

    def delete_task(self, task_id: str):
        self.cancel_task(task_id)
        with self._lock:
            self._tasks.pop(task_id, None)
        self.queue_changed.emit()

    def start_all(self):
        for qt in self._tasks.values():
            if qt.status in (TaskStatus.WAITING.value, TaskStatus.PAUSED.value):
                if qt.status == TaskStatus.PAUSED.value:
                    event = self._paused_events.get(qt.task_id)
                    if event:
                        event.set()
                qt.status = TaskStatus.WAITING.value
        self._schedule()
        # Update UI for any tasks that didn't get launched (not enough slots)
        for qt in self._tasks.values():
            if qt.status == TaskStatus.WAITING.value:
                self.task_status_changed.emit(qt.task_id, qt.status)

    def pause_all(self):
        for qt in self._tasks.values():
            if qt.status == TaskStatus.DOWNLOADING.value:
                self.pause_task(qt.task_id)

    def resume_all(self):
        for qt in self._tasks.values():
            if qt.status == TaskStatus.PAUSED.value:
                self.resume_task(qt.task_id)

    def clear_completed(self):
        to_remove = [
            tid for tid, qt in self._tasks.items()
            if qt.status == TaskStatus.COMPLETED.value
        ]
        for tid in to_remove:
            with self._lock:
                self._tasks.pop(tid, None)
        self.queue_changed.emit()

    # ---- Persistence ----

    def save_queue(self):
        path = get_queue_path()
        tasks_to_save = []
        for qt in self._tasks.values():
            # Only save tasks that can be resumed
            if qt.status not in (TaskStatus.WAITING.value, TaskStatus.PAUSED.value):
                continue
            tasks_to_save.append(qt.to_dict())

        data = {"version": 1, "tasks": tasks_to_save}
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load_queue(self):
        path = get_queue_path()
        if not path.exists():
            return

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        for d in data.get("tasks", []):
            qt = QueueTask.from_dict(d)
            if qt.status not in (TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value):
                self._tasks[qt.task_id] = qt

        self.queue_changed.emit()

    def shutdown(self):
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
            success = t.status == "done"
            qt.filename = t.filename  # sync final filename
            self._cleanup_task(qt.task_id)
            if success:
                qt.status = TaskStatus.COMPLETED.value
                qt.progress = 100
                self._record_history(qt)
                self.task_finished.emit(qt.task_id, True, "")
            else:
                qt.retry_count += 1
                if qt.retry_count < qt.max_retries:
                    qt.status = TaskStatus.WAITING.value
                    qt.progress = 0.0
                    self.task_status_changed.emit(qt.task_id, qt.status)
                    timer = threading.Timer(qt.retry_interval, self._schedule)
                    timer.daemon = True
                    timer.start()
                    return  # don't count as finished yet
                else:
                    qt.status = TaskStatus.FAILED.value
                    qt.error = t.error
                    self.task_finished.emit(qt.task_id, False, t.error)
            self._emit_batch_progress()

        thread = start_download_with_pause(dt, event, on_progress=on_progress, on_done=on_done)
        self._active[qt.task_id] = thread
        self.task_status_changed.emit(qt.task_id, qt.status)
        self.task_started.emit(qt.task_id)

    def _cleanup_task(self, task_id: str):
        self._active.pop(task_id, None)
        self._download_tasks.pop(task_id, None)
        self._paused_events.pop(task_id, None)

    def _record_history(self, qt: QueueTask):
        if not self._history_manager:
            return
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
        record = HistoryRecord(
            title=qt.title,
            author=qt.author,
            platform=qt.platform,
            url=qt.url,
            file_path=qt.filename,
            file_size=file_size,
            thumbnail_url=qt.thumbnail_url or "",
        )
        self._history_manager.add(record)
        self.history_record_added.emit(record)

    def _schedule(self):
        # Phase 1: under lock, just collect which tasks to launch
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
            if qt.status == TaskStatus.WAITING.value
            and qt.task_id not in self._active
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda q: q.created_at)

    def _emit_batch_progress(self):
        total = len(self._tasks)
        completed = sum(1 for qt in self._tasks.values() if qt.status == TaskStatus.COMPLETED.value)
        failed = sum(1 for qt in self._tasks.values() if qt.status == TaskStatus.FAILED.value)
        self.batch_progress.emit(completed, failed, total)
