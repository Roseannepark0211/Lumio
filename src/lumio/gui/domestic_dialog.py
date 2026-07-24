"""Domestic platform batch download dialog.

V4 Phase 1 Step 3: Enumeration + checkable result list.
Uses the Provider system's enumerate_profile_posts() API.
"""

from __future__ import annotations

import threading
import uuid

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..i18n import t
from ..providers import Platform, get_provider_for
from ..queue_manager import QueueTask
from ..utils.config import get_download_dir


class _DomesticWorker(QThread):
    """Background worker calling provider.enumerate_profile_posts()."""
    progress = Signal(int, int)
    finished = Signal(object)

    def __init__(self, platform_value: str, identifier: str, limit: int, cancel_event: threading.Event):
        super().__init__()
        self._platform_value = platform_value
        self._identifier = identifier
        self._limit = limit
        self._cancel_event = cancel_event

    def run(self):
        try:
            provider = get_provider_for(Platform(self._platform_value))
            if provider is None:
                self.finished.emit(ValueError(t("profile_error", err=t("unsupported"))))
                return
            posts = provider.enumerate_profile_posts(
                self._identifier,
                self._limit,
                callback=lambda cur, tot: self.progress.emit(cur, tot),
                cancel_event=self._cancel_event,
            )
            self.finished.emit(posts)
        except Exception as e:
            self.finished.emit(e)


class _ThumbWorker(QThread):
    """Background thumbnail loader."""
    finished = Signal(bytes, int)

    def __init__(self, url: str, index: int):
        super().__init__()
        self._url = url
        self._index = index

    def run(self):
        try:
            from urllib.request import urlopen
            data = urlopen(self._url, timeout=10).read()
            self.finished.emit(data, self._index)
        except Exception:
            self.finished.emit(b"", self._index)


class DomesticBatchDialog(QDialog):
    """国内平台批量下载对话框。

    Three-stage UI:
    1. count_limit setting -> Start button
    2. QProgressBar during enumeration
    3. Checkable result list + Add to Queue

    Emits batch_add_requested(list[QueueTask]) on confirm.
    """

    batch_add_requested = Signal(object)

    def __init__(self, platform_value: str, identifier: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._platform_value = platform_value
        self._identifier = identifier
        self._cancel_event = threading.Event()
        self._worker: _DomesticWorker | None = None
        self._posts: list[dict] = []
        self._result_rows: list[dict] = []
        self._thumb_loaders: list[_ThumbWorker] = []

        _PLATFORM_LABELS = {
            "weibo": "微博 (Weibo)",
            "xiaohongshu": "小红书 (Xiaohongshu)",
            "bilibili": "Bilibili (B站)",
            "douyin": "抖音 (Douyin)",
            "kuaishou": "快手 (Kuaishou)",
        }
        self._platform_label = _PLATFORM_LABELS.get(platform_value, platform_value)

        self.setWindowTitle(f"{self._platform_label} - {t('batch_download')}")
        self.setMinimumWidth(520)
        self.setModal(True)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        # ---- Header ----
        header = QLabel(f"{self._platform_label}  @{self._identifier}")
        header.setObjectName("accent")
        root.addWidget(header)

        # ---- Settings group ----
        settings_group = QGroupBox(t("count_limit"))
        sg = QVBoxLayout(settings_group)
        sg.setSpacing(8)

        limit_row = QHBoxLayout()
        limit_row.addWidget(QLabel(t("count_limit")))
        self._limit_spin = QSpinBox()
        self._limit_spin.setRange(1, 500)
        self._limit_spin.setValue(20)
        limit_row.addWidget(self._limit_spin)
        limit_row.addStretch()
        sg.addLayout(limit_row)
        root.addWidget(settings_group)

        # ---- Progress section ----
        self._progress_widget = QWidget()
        pw = QVBoxLayout(self._progress_widget)
        pw.setContentsMargins(0, 0, 0, 0)
        self._progress_label = QLabel()
        self._progress_label.setObjectName("muted")
        pw.addWidget(self._progress_label)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        pw.addWidget(self._progress_bar)
        self._progress_widget.hide()
        root.addWidget(self._progress_widget)

        # ---- Result list ----
        self._result_container = QWidget()
        self._result_container.hide()
        rc = QVBoxLayout(self._result_container)
        rc.setContentsMargins(0, 0, 0, 0)
        rc.setSpacing(6)

        self._status_label = QLabel()
        self._status_label.setObjectName("muted")
        rc.addWidget(self._status_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(200)
        scroll.setMaximumHeight(400)
        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_widget)
        rc.addWidget(scroll, 1)

        # Action row
        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        self._select_all_btn = QPushButton(t("select_all"))
        self._select_all_btn.setObjectName("secondary")
        self._select_all_btn.clicked.connect(self._on_toggle_select_all)
        action_row.addWidget(self._select_all_btn)

        self._add_btn = QPushButton(t("add_to_queue"))
        self._add_btn.setObjectName("accent_btn")
        self._add_btn.setEnabled(False)
        self._add_btn.clicked.connect(self._on_add_to_queue)
        action_row.addWidget(self._add_btn)

        action_row.addStretch()
        rc.addLayout(action_row)
        root.addWidget(self._result_container, 1)

        # ---- Bottom buttons ----
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._start_btn = QPushButton(t("start"))
        self._start_btn.setObjectName("accent_btn")
        self._start_btn.clicked.connect(self._on_start)
        btn_row.addWidget(self._start_btn)

        self._cancel_btn = QPushButton(t("cancel"))
        self._cancel_btn.setObjectName("secondary")
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(self._cancel_btn)
        root.addLayout(btn_row)

    # ---- Slots ----

    @Slot()
    def _on_start(self):
        limit = self._limit_spin.value()
        self._start_btn.setEnabled(False)
        self._limit_spin.setEnabled(False)
        self._progress_widget.show()
        self._progress_label.setText(t("parsing"))
        self._progress_bar.setRange(0, 0)

        self._cancel_event.clear()
        self._worker = _DomesticWorker(
            self._platform_value, self._identifier, limit, self._cancel_event,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    @Slot(int, int)
    def _on_progress(self, current: int, total: int):
        self._progress_label.setText(t("profile_enumerating", current=current, total=total))
        if total > 0:
            self._progress_bar.setRange(0, total)
            self._progress_bar.setValue(current)

    @Slot(object)
    def _on_finished(self, result):
        self._progress_widget.hide()
        self._start_btn.setEnabled(True)
        self._limit_spin.setEnabled(True)

        if isinstance(result, Exception):
            QMessageBox.warning(self, t("error"), t("profile_error", err=str(result)))
            return

        posts: list[dict] = result
        if not posts:
            QMessageBox.information(self, t("error"), t("batch_empty"))
            return

        self._posts = posts
        self._status_label.setText(t("batch_found") + f" {len(posts)} " + t("items"))
        self._show_results(posts)
        self._result_container.show()
        self._add_btn.setEnabled(True)
        self._start_btn.hide()

    def _show_results(self, posts: list[dict]):
        """Populate checkable result list."""
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._result_rows.clear()

        for idx, post in enumerate(posts):
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(4, 4, 4, 4)
            rl.setSpacing(8)

            cb = QCheckBox()
            cb.setChecked(True)
            cb.stateChanged.connect(self._update_add_btn)
            rl.addWidget(cb)

            thumb = QLabel()
            thumb.setFixedSize(80, 50)
            thumb.setObjectName("search_thumb")
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rl.addWidget(thumb)

            title_lbl = QLabel(post.get("title", "")[:80])
            title_lbl.setWordWrap(True)
            title_lbl.setObjectName("search_result_title")
            rl.addWidget(title_lbl, 1)

            self._list_layout.insertWidget(self._list_layout.count() - 1, row)
            self._result_rows.append({"checkbox": cb, "data": post, "thumb_label": thumb})

            thumb_url = post.get("thumbnail", "")
            if thumb_url:
                loader = _ThumbWorker(thumb_url, idx)
                loader.finished.connect(self._on_thumb_loaded)
                loader.start()
                self._thumb_loaders.append(loader)

    @Slot(bytes, int)
    def _on_thumb_loaded(self, data: bytes, index: int):
        if not data or index >= len(self._result_rows):
            return
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        if pixmap.isNull():
            return
        scaled = pixmap.scaled(
            80, 50,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        row = self._result_rows[index]
        row["thumb_label"].setPixmap(scaled)

    def _update_add_btn(self):
        any_checked = any(r["checkbox"].isChecked() for r in self._result_rows)
        self._add_btn.setEnabled(any_checked)

    @Slot()
    def _on_toggle_select_all(self):
        all_checked = all(r["checkbox"].isChecked() for r in self._result_rows)
        for r in self._result_rows:
            r["checkbox"].setChecked(not all_checked)

    @Slot()
    def _on_add_to_queue(self):
        selected = [r for r in self._result_rows if r["checkbox"].isChecked()]
        if not selected:
            return

        batch_id = uuid.uuid4().hex[:12]
        output_dir = str(get_download_dir())
        tasks = []
        for r in selected:
            post = r["data"]
            task = QueueTask(
                url=post.get("url", ""),
                title=post.get("title", ""),
                author=self._identifier,
                platform=self._platform_value,
                thumbnail_url=post.get("thumbnail"),
                output_dir=output_dir,
                batch_id=batch_id,
            )
            tasks.append(task)

        self.batch_add_requested.emit(tasks)
        self.accept()

    @Slot()
    def _on_cancel(self):
        if self._worker and self._worker.isRunning():
            self._cancel_event.set()
            self._cancel_btn.setEnabled(False)
            self._progress_label.setText(t("profile_cancelled"))
        else:
            self.reject()
