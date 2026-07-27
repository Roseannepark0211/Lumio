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
import logging

from .utils.signal import QObject, Signal

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .downloader import DownloadTask, start_download_with_pause
from .history_manager import HistoryManager, HistoryRecord
from .utils.config import get_queue_path, load_config


logger = logging.getLogger(__name__)


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
    library_thumbnail_ready = Signal(str, str)       # item_id, local_thumbnail_path
    conflict_ask = Signal(str)                       # file_path, respond via conflict_resolved

    def __init__(self, history_manager: HistoryManager | None = None, parent=None):
        super().__init__(parent)
        self._tasks: dict[str, QueueTask] = {}
        self._active: dict[str, threading.Thread] = {}
        self._download_tasks: dict[str, DownloadTask] = {}
        self._paused_events: dict[str, threading.Event] = {}
        # 进度上报节流：task_id → (last_progress, last_timestamp)
        # 避免 downloader chunk_size=8KB 触发的事件风暴（10MB 文件 ~1250 次事件）
        self._progress_throttle: dict[str, tuple[float, float]] = {}
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
            def _it_to_dict(it):
                d = {"url": it.url, "is_video": it.is_video, "index": it.index}
                if hasattr(it, "media_type") and it.media_type:
                    d["media_type"] = it.media_type
                if hasattr(it, "width") and it.width:
                    d["width"] = it.width
                if hasattr(it, "height") and it.height:
                    d["height"] = it.height
                if hasattr(it, "extension") and it.extension:
                    d["extension"] = it.extension
                if hasattr(it, "size") and it.size:
                    d["size"] = it.size
                if hasattr(it, "quality") and it.quality:
                    d["quality"] = it.quality
                if hasattr(it, "mime") and it.mime:
                    d["mime"] = it.mime
                if hasattr(it, "id") and it.id:
                    d["id"] = it.id
                if hasattr(it, "filename") and it.filename:
                    d["filename"] = it.filename
                if hasattr(it, "live_photo") and it.live_photo is not None:
                    d["live_photo"] = it.live_photo if isinstance(it.live_photo, dict) else {"image": str(it.live_photo), "video": "", "cover": ""}
                if hasattr(it, "original_url") and it.original_url:
                    d["original_url"] = it.original_url
                return d
            media_json = _json.dumps([_it_to_dict(it) for it in info.items])
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
        to_emit = None
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
                to_emit = (task_id, qt.status)
            else:
                if qt.status not in (TaskStatus.WAITING.value, TaskStatus.PAUSED.value):
                    return
                qt.status = TaskStatus.DOWNLOADING.value
                qt_to_launch = qt
        # 信号必须在锁外发射——QML slot 会同步调用 getQueueJson() → get_all_tasks()
        # 再次获锁，锁内 emit 会死锁（参考 AGENTS.md 踩坑记录）
        if to_emit:
            self.task_status_changed.emit(*to_emit)
            return
        if qt_to_launch:
            self.task_status_changed.emit(task_id, qt_to_launch.status)
            self._launch_download(qt_to_launch)

    def pause_task(self, task_id: str):
        with self._lock:
            qt = self._tasks.get(task_id)
            if not qt:
                return
            # 仅对真正在下载的任务生效；WAITING/RETRYING 暂停后会丢失调度入口
            # 导致状态卡在 PAUSED 但无线程，resume 时走错分支
            if qt.status != TaskStatus.DOWNLOADING.value:
                return
            event = self._paused_events.get(task_id)
            if event:
                event.clear()
            qt.status = TaskStatus.PAUSED.value
        self.task_status_changed.emit(task_id, TaskStatus.PAUSED.value)
        self.queue_changed.emit()

    def resume_task(self, task_id: str):
        # 注意：threading.Lock 不可重入，_schedule() 内部会获锁，
        # 因此先在锁内收集工作，再在锁外调用 _schedule（参考 AGENTS.md 踩坑记录）
        # 信号也必须在锁外发射——QML slot 会同步调用 getQueueJson() → get_all_tasks()
        # 再次获锁，锁内 emit 会死锁
        need_schedule = False
        to_emit = None
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
                    to_emit = (task_id, qt.status)
                else:
                    # PAUSED 但事件已丢失（异常清理过）→ 走重新调度路径
                    qt.status = TaskStatus.WAITING.value
                    to_emit = (task_id, qt.status)
                    need_schedule = True
            elif qt.status == TaskStatus.INTERRUPTED.value:
                # Thread is dead — schedule a fresh download
                qt.status = TaskStatus.WAITING.value
                to_emit = (task_id, qt.status)
                need_schedule = True
        if to_emit:
            self.task_status_changed.emit(*to_emit)
        if need_schedule:
            self._schedule()

    def cancel_task(self, task_id: str):
        qt = None
        with self._lock:
            dt = self._download_tasks.get(task_id)
            if dt:
                dt._cancelled = True
            # 重要：必须 set() pause event 以唤醒可能正阻塞在 pause_event.wait()
            # 的下载线程，否则线程会永远卡住（即使 _cancelled=True 也无法检测到）
            event = self._paused_events.get(task_id)
            if event:
                event.set()
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
        # 仅启动该任务本身，不调度其他 waiting 任务
        # （符合 AGENTS.md "任务完成后不自动启动下一个" 设计意图）
        self._schedule(only_task_id=task_id)

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
        # 注意：不重置 qt.progress！
        # - 新任务：progress 本来就是 0.0
        # - 重试任务：保留当前进度，新下载会通过 on_progress 更新（断点续传时
        #   yt-dlp/requests 会从 .part 文件恢复，进度会从恢复点继续上报）
        # 旧实现总是 qt.progress = 0.0 导致暂停后重试进度归 0，用户体验差
        qt.speed = ""
        qt.error = ""

        event = threading.Event()
        event.set()
        self._paused_events[qt.task_id] = event

        dt = qt.to_download_task()
        self._download_tasks[qt.task_id] = dt

        def on_progress(t: DownloadTask):
            # downloader 内部 progress 是 0..100，统一归一化到 0..1
            # （QML LaserProgressBar / _formatPct 均假设 0..1 范围，
            #  不归一化会导致 progress > 0.01 就被 clamp 到 1.0 显示 100%）

            # 当下载完成（t.status == "done"）时不立即上报 100% 进度。
            # yt-dlp 的 "finished" hook 表示下载完成，但随后还有后处理
            # （合并音视频），此时文件还未就绪。如果立即上报 100%，
            # UI 会显示 "100% + 下载中" 持续数秒到数十秒，非常困惑。
            # 让 on_done 统一处理最终状态和进度上报。
            if t.status == "done":
                return

            p = t.progress
            if p > 1.0:
                p = p / 100.0
            qt.progress = p
            qt.speed = t.speed
            qt.filename = t.filename

            # 节流：进度变化 < 1% 且距上次上报 < 0.3s 就跳过 emit
            # （downloader 的 chunk_size=8KB，10MB 文件会触发 ~1250 次 on_progress，
            #  多任务多项下载时事件量爆炸，WebSocket 来不及发送导致 socket.send() 异常）
            # 用 dict 临时存储 last_p/last_ts，避免给 QueueTask 加字段
            throttle = self._progress_throttle.get(qt.task_id)
            now = time.monotonic()
            if throttle is None:
                self._progress_throttle[qt.task_id] = (p, now)
            else:
                last_p, last_ts = throttle
                delta_p = abs(p - last_p)
                delta_t = now - last_ts
                if delta_p < 0.01 and delta_t < 0.3:
                    return
                self._progress_throttle[qt.task_id] = (p, now)

            self.task_progress.emit(qt.task_id, p, t.speed, t.filename)

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
                qt.progress = 1.0  # 统一 0..1 范围（与下载中一致）
                self._record_history(qt)
                # 关键：必须 emit task_status_changed！
                # qml_bridge 未连接 task_finished 信号，UI 只监听 task_status_changed
                # 旧实现只 emit task_finished → UI 永远不知道任务完成 → 卡在"下载中"
                # （适用于所有平台：视频/图片/音频，yt-dlp/直链/媒体项下载）
                self.task_status_changed.emit(qt.task_id, qt.status)
                self.task_finished.emit(qt.task_id, True, "")
            else:
                qt.retry_count += 1
                if qt.retry_count < qt.max_retries:
                    qt.status = TaskStatus.RETRYING.value
                    # 注意：不重置 qt.progress = 0.0！
                    # 保留当前进度，重试时断点续传会从 .part 文件恢复，
                    # 新进度会通过 on_progress 上报。旧实现归 0 会导致
                    # "暂停→重试→进度归0→卡住→突然100%" 的糟糕体验
                    self.task_status_changed.emit(qt.task_id, qt.status)
                    delay = _RETRY_INTERVALS[min(qt.retry_count - 1, len(_RETRY_INTERVALS) - 1)]
                    # 仅重试该任务本身，不启动其他 waiting 任务
                    # （旧实现调用 self._schedule 会启动所有 waiting 任务，
                    #  违反"任务完成后不自动启动下一个"设计意图）
                    timer = threading.Timer(delay, lambda tid=qt.task_id: self._schedule(only_task_id=tid))
                    timer.daemon = True
                    timer.start()
                    return  # don't count as finished yet
                else:
                    from .utils.error_types import classify_error
                    qt.status = TaskStatus.FAILED.value
                    qt.error = t.error
                    qt.error_category = classify_error(t.error).value
                    # 同上：必须 emit task_status_changed 让 UI 知道任务失败
                    self.task_status_changed.emit(qt.task_id, qt.status)
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
        self._progress_throttle.pop(task_id, None)

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
                logger.exception('Failed to add item to library for task %s: %s', qt.task_id, e)
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
            # 通知前端：本地缩略图已生成，可切换到 lumioFileUrl 原图（比 thumbnail_url 缩放版清晰）
            self.library_thumbnail_ready.emit(item_id, local_path)

    def _schedule(self, only_task_id: str | None = None):
        """调度 waiting/retrying 任务启动下载。

        Args:
            only_task_id: 若指定，仅启动该任务本身，不启动其他 waiting 任务。
                          用于 retry_task 和失败重试 Timer，避免单任务操作
                          意外启动其他 waiting 任务（违反"任务完成后不自动启动
                          下一个"的设计意图）。None 表示按 max_workers 并发调度
                          所有 waiting 任务（用于 start_all / resume_all）。
        """
        # Phase 1: under lock, collect which tasks to launch
        to_launch = []
        with self._lock:
            if only_task_id is not None:
                # 单任务模式：仅启动指定任务（若仍在 waiting/retrying 且未在活跃中）
                qt = self._tasks.get(only_task_id)
                if qt and qt.status in (TaskStatus.WAITING.value, TaskStatus.RETRYING.value) \
                        and qt.task_id not in self._active:
                    qt.status = TaskStatus.DOWNLOADING.value
                    to_launch.append(qt)
            else:
                # 全局调度模式：按 max_workers 并发启动所有 waiting 任务
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
