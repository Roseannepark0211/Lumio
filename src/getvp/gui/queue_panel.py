from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..i18n import t
from ..queue_manager import DownloadManager, QueueTask, TaskStatus


_STATUS_BADGE_MAP = {
    TaskStatus.WAITING.value: "badge_waiting",
    TaskStatus.DOWNLOADING.value: "badge_downloading",
    TaskStatus.PAUSED.value: "badge_paused",
    TaskStatus.COMPLETED.value: "badge_completed",
    TaskStatus.FAILED.value: "badge_failed",
    TaskStatus.CANCELLED.value: "badge_cancelled",
}


class QueueTaskWidget(QFrame):
    action_requested = Signal(str, str)  # task_id, action

    def __init__(self, qt: QueueTask, parent=None):
        super().__init__(parent)
        self.task_id = qt.task_id
        self.setObjectName("task_card")
        self._build_ui(qt)

    def _build_ui(self, qt: QueueTask):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 4)
        root.setSpacing(3)

        # Row 1: thumbnail + info + status
        top = QHBoxLayout()
        top.setSpacing(8)

        # Thumbnail
        self._thumb = QLabel()
        self._thumb.setFixedSize(36, 36)
        self._thumb.setStyleSheet(
            "background-color: #0d0f16; border-radius: 4px;"
        )
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setText(qt.platform[:2].upper())
        top.addWidget(self._thumb)

        # Info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(0)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self._title = QLabel(qt.title[:50])
        self._title.setObjectName("task_title")
        title_row.addWidget(self._title, 1)

        # Platform badge
        plat = QLabel("YT" if qt.platform == "youtube" else "IG")
        plat.setObjectName(
            "platform_yt" if qt.platform == "youtube" else "platform_ig"
        )
        plat.setFixedHeight(16)
        title_row.addWidget(plat)
        info_layout.addLayout(title_row)

        self._speed_label = QLabel("")
        self._speed_label.setObjectName("task_speed")
        info_layout.addWidget(self._speed_label)

        top.addLayout(info_layout, 1)

        # Status badge
        self._badge = QLabel(self._status_text(qt.status))
        badge_obj = _STATUS_BADGE_MAP.get(qt.status, "badge_waiting")
        self._badge.setObjectName(badge_obj)
        self._badge.setFixedHeight(18)
        top.addWidget(self._badge)

        root.addLayout(top)

        # Row 2: progress bar
        self._progress = QProgressBar()
        self._progress.setTextVisible(True)
        self._progress.setFormat("%p%")
        self._progress.setValue(int(qt.progress))
        self._progress.setFixedHeight(14)
        root.addWidget(self._progress)

        # Row 3: action buttons
        self._btn_row = QHBoxLayout()
        self._btn_row.setSpacing(4)
        self._btn_row.setContentsMargins(0, 0, 0, 0)
        self._btn_row.addStretch()
        self._update_buttons(qt.status)
        root.addLayout(self._btn_row)

    def _status_text(self, status: str) -> str:
        mapping = {
            TaskStatus.WAITING.value: t("status_waiting"),
            TaskStatus.DOWNLOADING.value: t("status_downloading"),
            TaskStatus.PAUSED.value: t("status_paused"),
            TaskStatus.COMPLETED.value: t("status_completed"),
            TaskStatus.FAILED.value: t("status_failed"),
            TaskStatus.CANCELLED.value: t("status_cancelled"),
        }
        return mapping.get(status, status)

    def _clear_buttons(self):
        while self._btn_row.count() > 1:  # keep the stretch
            item = self._btn_row.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

    def _add_btn(self, text: str, action: str, danger: bool = False):
        btn = QPushButton(text)
        btn.setObjectName("task_btn_danger" if danger else "task_btn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self.action_requested.emit(self.task_id, action))
        self._btn_row.addWidget(btn)

    def _update_buttons(self, status: str):
        self._clear_buttons()
        if status == TaskStatus.WAITING.value:
            self._add_btn(t("start"), "start")
            self._add_btn(t("cancel"), "cancel")
            self._add_btn(t("delete"), "delete", danger=True)
        elif status == TaskStatus.DOWNLOADING.value:
            self._add_btn(t("pause"), "pause")
            self._add_btn(t("cancel"), "cancel", danger=True)
        elif status == TaskStatus.PAUSED.value:
            self._add_btn(t("resume"), "resume")
            self._add_btn(t("cancel"), "cancel")
            self._add_btn(t("delete"), "delete", danger=True)
        elif status == TaskStatus.COMPLETED.value:
            self._add_btn(t("open_file"), "open_file")
            self._add_btn(t("open_dir"), "open_dir")
            self._add_btn(t("delete"), "delete", danger=True)
        elif status in (TaskStatus.FAILED.value, TaskStatus.CANCELLED.value):
            self._add_btn(t("retry"), "retry")
            self._add_btn(t("delete"), "delete", danger=True)

    # ---- Public update methods ----

    def update_progress(self, progress: float, speed: str, filename: str):
        self._progress.setValue(int(progress))
        if speed:
            self._speed_label.setText(speed)

    def update_status(self, status: str):
        self._badge.setText(self._status_text(status))
        badge_obj = _STATUS_BADGE_MAP.get(status, "badge_waiting")
        self._badge.setObjectName(badge_obj)
        self._badge.style().unpolish(self._badge)
        self._badge.style().polish(self._badge)
        self._update_buttons(status)

    def update_finished(self, success: bool, error: str):
        if success:
            self.update_status(TaskStatus.COMPLETED.value)
            self._speed_label.setText(t("pct_done"))
        else:
            self.update_status(TaskStatus.FAILED.value)
            self._speed_label.setText(f"{t('error')}: {error[:40]}")


class QueueDrawer(QWidget):
    def __init__(self, manager: DownloadManager, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._task_widgets: dict[str, QueueTaskWidget] = {}
        self._expanded = False
        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar
        self._header = QFrame()
        self._header.setObjectName("queue_header")
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(12, 6, 12, 6)
        header_layout.setSpacing(8)

        self._title_label = QLabel(t("queue_title"))
        self._title_label.setObjectName("queue_title")
        header_layout.addWidget(self._title_label)

        self._badge_label = QLabel("0")
        self._badge_label.setObjectName("queue_badge")
        header_layout.addWidget(self._badge_label)

        header_layout.addStretch()

        # Global action buttons
        self._start_all_btn = self._make_header_btn(t("start_all"), "start_all")
        self._pause_all_btn = self._make_header_btn(t("pause_all"), "pause_all")
        self._resume_all_btn = self._make_header_btn(t("resume_all"), "resume_all")
        self._clear_btn = self._make_header_btn(t("clear_completed"), "clear_completed")

        self._toggle_btn = QPushButton("▲")
        self._toggle_btn.setObjectName("task_btn")
        self._toggle_btn.setFixedSize(28, 28)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.clicked.connect(self._toggle)
        header_layout.addWidget(self._toggle_btn)

        root.addWidget(self._header)

        # Scrollable task list (collapsible)
        self._list_container = QWidget()
        list_layout = QVBoxLayout(self._list_container)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(4)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(
            "QScrollArea { background: #0f1117; border: none; }"
        )
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("background: #0f1117;")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(4, 4, 4, 4)
        self._list_layout.setSpacing(3)
        self._list_layout.addStretch()

        self._scroll.setWidget(self._list_widget)
        list_layout.addWidget(self._scroll)

        self._list_container.setMaximumHeight(0)
        self._list_container.setVisible(False)
        root.addWidget(self._list_container)

        self._update_badge()

    def _make_header_btn(self, text: str, action: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("task_btn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self._on_global_action(action))
        self._header.layout().insertWidget(
            self._header.layout().count() - 1, btn
        )
        return btn

    def _connect_signals(self):
        mgr = self._manager
        mgr.task_added.connect(self._on_task_added)
        mgr.task_progress.connect(self._on_task_progress)
        mgr.task_finished.connect(self._on_task_finished)
        mgr.task_status_changed.connect(self._on_task_status_changed)
        mgr.queue_changed.connect(self._update_badge)

    def _toggle(self):
        self._expanded = not self._expanded
        if self._expanded:
            self._list_container.setVisible(True)
            self._list_container.setMaximumHeight(520)
            self._toggle_btn.setText("▼")
        else:
            self._list_container.setMaximumHeight(0)
            self._list_container.setVisible(False)
            self._toggle_btn.setText("▲")

    def _update_badge(self):
        count = len(self._manager.get_all_tasks())
        self._badge_label.setText(str(count))
        self._badge_label.setVisible(count > 0)

    @Slot(str)
    def _on_task_added(self, task_id: str):
        qt = self._manager.get_task(task_id)
        if not qt:
            return
        widget = QueueTaskWidget(qt)
        widget.action_requested.connect(self._on_task_action)
        self._task_widgets[task_id] = widget
        self._list_layout.insertWidget(self._list_layout.count() - 1, widget)

        if not self._expanded:
            self._toggle()

    @Slot(str, float, str, str)
    def _on_task_progress(self, task_id: str, progress: float, speed: str, filename: str):
        widget = self._task_widgets.get(task_id)
        if widget:
            widget.update_progress(progress, speed, filename)

    @Slot(str, bool, str)
    def _on_task_finished(self, task_id: str, success: bool, error: str):
        widget = self._task_widgets.get(task_id)
        if widget:
            widget.update_finished(success, error)

    @Slot(str, str)
    def _on_task_status_changed(self, task_id: str, status: str):
        widget = self._task_widgets.get(task_id)
        if widget:
            widget.update_status(status)

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
        elif action == "clear_completed":
            mgr.clear_completed()
            # Remove completed widgets
            to_remove = [
                tid for tid, w in self._task_widgets.items()
                if not mgr.get_task(tid)
            ]
            for tid in to_remove:
                widget = self._task_widgets.pop(tid, None)
                if widget:
                    widget.deleteLater()
