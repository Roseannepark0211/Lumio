from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..i18n import t
from ..queue_manager import DownloadManager, TaskStatus
from .queue_panel import QueueTaskWidget


class DownloadsPage(QWidget):
    def __init__(self, manager: DownloadManager, parent=None):
        super().__init__(parent)
        self.setObjectName("downloads_page")
        self._manager = manager
        self._task_widgets: dict[str, QueueTaskWidget] = {}
        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar
        header = QHBoxLayout()
        header.setContentsMargins(32, 20, 32, 12)
        header.setSpacing(10)

        title = QLabel(t("queue_title"))
        title.setObjectName("page_title")
        header.addWidget(title)

        self._badge = QLabel("0")
        self._badge.setObjectName("queue_badge")
        header.addWidget(self._badge)

        self._batch_label = QLabel("")
        self._batch_label.setObjectName("muted")
        self._batch_label.setStyleSheet("font-size: 11px; margin-left: 4px;")
        self._batch_label.hide()
        header.addWidget(self._batch_label)

        header.addStretch()

        # Global action buttons
        for text, action in [
            (t("start_all"), "start_all"),
            (t("pause_all"), "pause_all"),
            (t("resume_all"), "resume_all"),
            (t("resume_interrupted"), "resume_interrupted"),
            (t("clear_completed"), "clear_completed"),
        ]:
            btn = QPushButton(text)
            btn.setObjectName("task_btn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, a=action: self._on_global_action(a))
            header.addWidget(btn)

        root.addLayout(header)

        # Scrollable task list
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { border: none; }")
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(32, 8, 32, 16)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()

        self._scroll.setWidget(self._list_widget)
        root.addWidget(self._scroll, 1)

        # Empty state
        self._empty_label = QLabel(t("downloads_empty"))
        self._empty_label.setObjectName("muted")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("padding: 40px; font-size: 14px;")
        self._list_layout.insertWidget(0, self._empty_label)

        self._update_badge()
        self._update_empty()

    def _connect_signals(self):
        mgr = self._manager
        mgr.task_added.connect(self._on_task_added)
        mgr.task_progress.connect(self._on_task_progress)
        mgr.task_finished.connect(self._on_task_finished)
        mgr.task_status_changed.connect(self._on_task_status_changed)
        mgr.queue_changed.connect(self._update_badge)
        mgr.batch_progress.connect(self._on_batch_progress)

    def _update_empty(self):
        has_tasks = len(self._task_widgets) > 0
        self._empty_label.setVisible(not has_tasks)

    def _update_badge(self):
        count = len(self._manager.get_all_tasks())
        self._badge.setText(str(count))
        self._badge.setVisible(count > 0)
        self._update_empty()

    @Slot(int, int, int)
    def _on_batch_progress(self, completed: int, failed: int, total: int):
        done = completed + failed
        if total > 0 and done < total:
            self._batch_label.setText(f"{completed}/{total}")
            self._batch_label.setStyleSheet("font-size: 11px; margin-left: 4px; color: #a0a8c8;")
            self._batch_label.show()
        elif total > 0 and done >= total:
            self._batch_label.setText(t("batch_done", n=completed, total=total))
            self._batch_label.setStyleSheet("font-size: 11px; margin-left: 4px; color: #10b981;")
            self._batch_label.show()
        else:
            self._batch_label.hide()

    @Slot(str)
    def _on_task_added(self, task_id: str):
        qt = self._manager.get_task(task_id)
        if not qt:
            return
        widget = QueueTaskWidget(qt)
        widget.action_requested.connect(self._on_task_action)
        self._task_widgets[task_id] = widget
        self._list_layout.insertWidget(self._list_layout.count() - 1, widget)
        self._update_empty()

    @Slot(str, float, str, str)
    def _on_task_progress(self, task_id: str, progress: float, speed: str, filename: str):
        widget = self._task_widgets.get(task_id)
        if widget:
            widget.update_progress(progress, speed, filename)

    @Slot(str, bool, str)
    def _on_task_finished(self, task_id: str, success: bool, error: str):
        widget = self._task_widgets.get(task_id)
        if widget:
            task = self._manager.get_task(task_id)
            category = task.error_category if task and not success else ""
            widget.update_finished(success, error, category)

    @Slot(str, str)
    def _on_task_status_changed(self, task_id: str, status: str):
        widget = self._task_widgets.get(task_id)
        if widget:
            task = self._manager.get_task(task_id)
            retry_info = ""
            if task and status == TaskStatus.RETRYING.value:
                retry_info = f" ({task.retry_count}/{task.max_retries})"
            widget.update_status(status, retry_info)

    def _on_task_action(self, task_id: str, action: str):
        mgr = self._manager
        if action == "start":
            mgr.start_task(task_id)
        elif action == "pause":
            mgr.pause_task(task_id)
        elif action == "resume":
            mgr.resume_task(task_id)
        elif action == "cancel":
            mgr.cancel_task(task_id)
        elif action == "retry":
            mgr.retry_task(task_id)
        elif action == "delete":
            widget = self._task_widgets.pop(task_id, None)
            if widget:
                widget.deleteLater()
            mgr.delete_task(task_id)
        elif action == "open_file":
            qt = mgr.get_task(task_id)
            if qt and qt.filename and Path(qt.filename).exists():
                os.startfile(qt.filename)
        elif action == "open_dir":
            qt = mgr.get_task(task_id)
            if qt and qt.filename:
                parent = Path(qt.filename).parent
                if parent.exists():
                    os.startfile(str(parent))

    def _on_global_action(self, action: str):
        mgr = self._manager
        if action == "start_all":
            mgr.start_all()
        elif action == "pause_all":
            mgr.pause_all()
        elif action == "resume_all":
            mgr.resume_all()
        elif action == "resume_interrupted":
            mgr.resume_interrupted()
        elif action == "clear_completed":
            mgr.clear_completed()
            to_remove = [
                tid for tid, w in self._task_widgets.items()
                if not mgr.get_task(tid)
            ]
            for tid in to_remove:
                widget = self._task_widgets.pop(tid, None)
                if widget:
                    widget.deleteLater()
            self._update_empty()
