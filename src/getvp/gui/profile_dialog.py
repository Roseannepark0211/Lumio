from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..downloader import enumerate_profile_posts, fetch_profile_info, _post_to_queue_task
from ..i18n import t
from ..utils.config import get_download_dir


class _ProfileInfoWorker(QThread):
    finished = Signal(object)  # dict or Exception

    def __init__(self, username: str):
        super().__init__()
        self._username = username

    def run(self):
        try:
            info = fetch_profile_info(self._username)
            self.finished.emit(info)
        except Exception as e:
            self.finished.emit(e)


class _ProfileEnumerateWorker(QThread):
    progress = Signal(int, int)  # current, total
    finished = Signal(object)  # list[Post] or Exception

    def __init__(self, username: str, limit: int, cancel_event: threading.Event):
        super().__init__()
        self._username = username
        self._limit = limit
        self._cancel_event = cancel_event

    def run(self):
        try:
            posts = enumerate_profile_posts(
                self._username,
                self._limit,
                callback=lambda cur, tot: self.progress.emit(cur, tot),
                cancel_event=self._cancel_event,
            )
            self.finished.emit(posts)
        except Exception as e:
            self.finished.emit(e)


class ProfileDialog(QDialog):
    batch_add_requested = Signal(object)  # list[QueueTask]

    def __init__(self, username: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._username = username
        self._profile_info: dict | None = None
        self._cancel_event = threading.Event()
        self._enumerate_worker: _ProfileEnumerateWorker | None = None

        self.setWindowTitle(t("profile_dialog_title"))
        self.setMinimumWidth(460)
        self.setModal(True)
        self._build_ui()
        self._start_fetch_info()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        # ---- Profile header ----
        header = QHBoxLayout()
        self._pic_label = QLabel()
        self._pic_label.setFixedSize(64, 64)
        self._pic_label.setObjectName("profile_pic")
        self._pic_label.setStyleSheet(
            "background-color: #12141c; border: 2px solid #2a2e3a; border-radius: 32px;"
        )
        self._pic_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self._pic_label)

        info_col = QVBoxLayout()
        self._username_label = QLabel(f"@{self._username}")
        self._username_label.setObjectName("accent")
        info_col.addWidget(self._username_label)

        self._fullname_label = QLabel(t("profile_fetching"))
        self._fullname_label.setObjectName("muted")
        info_col.addWidget(self._fullname_label)

        self._count_label = QLabel()
        self._count_label.setObjectName("muted")
        info_col.addWidget(self._count_label)

        header.addLayout(info_col, 1)
        root.addLayout(header)

        # ---- Settings group ----
        settings_group = QGroupBox(t("profile_posts_label"))
        sg = QVBoxLayout(settings_group)

        range_row = QHBoxLayout()
        range_row.addWidget(QLabel(t("range_from")))
        self._from_spin = QSpinBox()
        self._from_spin.setRange(1, 500)
        self._from_spin.setValue(1)
        self._from_spin.setEnabled(False)
        range_row.addWidget(self._from_spin)
        range_row.addWidget(QLabel(t("range_to")))
        self._to_spin = QSpinBox()
        self._to_spin.setRange(1, 500)
        self._to_spin.setValue(20)
        self._to_spin.setEnabled(False)
        range_row.addWidget(self._to_spin)
        sg.addLayout(range_row)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel(t("profile_folder_name")))
        self._name_input = QLineEdit(f"@{self._username}")
        name_row.addWidget(self._name_input, 1)
        sg.addLayout(name_row)

        root.addWidget(settings_group)

        # ---- Progress section (hidden initially) ----
        self._progress_widget = QWidget()
        pv = QVBoxLayout(self._progress_widget)
        pv.setContentsMargins(0, 0, 0, 0)
        self._progress_label = QLabel()
        self._progress_label.setObjectName("muted")
        pv.addWidget(self._progress_label)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        pv.addWidget(self._progress_bar)
        self._progress_widget.hide()
        root.addWidget(self._progress_widget)

        # ---- Buttons ----
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._cancel_btn = QPushButton(t("cancel"))
        self._cancel_btn.setObjectName("secondary")
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(self._cancel_btn)

        self._add_btn = QPushButton(t("profile_add_to_queue"))
        self._add_btn.setObjectName("accent_btn")
        self._add_btn.setEnabled(False)
        self._add_btn.clicked.connect(self._on_add_to_queue)
        btn_row.addWidget(self._add_btn)
        root.addLayout(btn_row)

    def _start_fetch_info(self):
        self._info_worker = _ProfileInfoWorker(self._username)
        self._info_worker.finished.connect(self._on_info_done)
        self._info_worker.start()

    @Slot(object)
    def _on_info_done(self, result):
        if isinstance(result, Exception):
            err_msg = str(result)
            if "429" in err_msg:
                err_msg = t("profile_rate_limited")
            QMessageBox.warning(self, t("error"), t("profile_error", err=err_msg))
            self.reject()
            return

        self._profile_info = result
        self._fullname_label.setText(result.get("full_name", ""))
        count = result.get("post_count", 0)
        if count > 0:
            self._count_label.setText(t("profile_post_count", n=count))
            max_val = min(count, 500)
            self._from_spin.setMaximum(max_val)
            self._to_spin.setMaximum(max_val)
        else:
            self._count_label.setText("")
        self._from_spin.setEnabled(True)
        self._to_spin.setEnabled(True)
        self._add_btn.setEnabled(True)

        # Load profile pic
        pic_url = result.get("profile_pic_url")
        if pic_url:
            self._load_pic(pic_url)

    def _load_pic(self, url: str):
        from urllib.request import urlopen

        class _PicLoader(QThread):
            finished = Signal(bytes)

            def __init__(self, u):
                super().__init__()
                self._url = u

            def run(self):
                try:
                    data = urlopen(self._url, timeout=10).read()
                    self.finished.emit(data)
                except Exception:
                    self.finished.emit(b"")

        self._pic_thread = _PicLoader(url)
        self._pic_thread.finished.connect(self._on_pic_loaded)
        self._pic_thread.start()

    @Slot(bytes)
    def _on_pic_loaded(self, data: bytes):
        if not data:
            return
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                64, 64,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._pic_label.setPixmap(scaled)
            self._pic_label.setStyleSheet(
                "border: 2px solid #2a2e3a; border-radius: 32px;"
            )

    @Slot()
    def _on_add_to_queue(self):
        if not self._profile_info:
            return

        start = self._from_spin.value()
        end = self._to_spin.value()
        if start > end:
            start, end = end, start

        self._progress_widget.show()
        self._progress_label.setText(t("profile_fetching"))
        self._progress_bar.setRange(0, 0)
        self._add_btn.setEnabled(False)
        self._from_spin.setEnabled(False)
        self._to_spin.setEnabled(False)
        self._name_input.setEnabled(False)

        self._cancel_event.clear()
        self._enumerate_worker = _ProfileEnumerateWorker(
            self._username, end, self._cancel_event
        )
        self._enumerate_worker.progress.connect(self._on_enumerate_progress)
        self._enumerate_worker.finished.connect(self._on_enumerate_done)
        self._enumerate_worker.start()

    @Slot(int, int)
    def _on_enumerate_progress(self, current: int, total: int):
        self._progress_label.setText(t("profile_enumerating", current=current, total=total))
        self._progress_bar.setRange(0, total)
        self._progress_bar.setValue(current)

    @Slot(object)
    def _on_enumerate_done(self, result):
        if isinstance(result, Exception):
            QMessageBox.warning(self, t("error"), t("profile_error", err=str(result)))
            self._reset_controls()
            return

        if isinstance(result, list) and self._cancel_event.is_set():
            if not result:
                QMessageBox.information(self, t("profile_cancelled"), t("profile_cancelled"))
                self._reset_controls()
                return

        posts = result
        if not posts:
            QMessageBox.information(self, t("profile_no_posts"), t("profile_no_posts"))
            self._reset_controls()
            return

        # Slice to selected range
        start = self._from_spin.value()
        end = self._to_spin.value()
        if start > end:
            start, end = end, start
        posts = posts[start - 1:end]

        custom_name = self._name_input.text().strip() or f"@{self._username}"
        output_dir = Path(get_download_dir())
        tasks = [_post_to_queue_task(p, custom_name, output_dir) for p in posts]

        self.batch_add_requested.emit(tasks)
        self.accept()

    def _reset_controls(self):
        self._progress_widget.hide()
        self._add_btn.setEnabled(True)
        self._from_spin.setEnabled(True)
        self._to_spin.setEnabled(True)
        self._name_input.setEnabled(True)

    @Slot()
    def _on_cancel(self):
        if self._enumerate_worker and self._enumerate_worker.isRunning():
            self._cancel_event.set()
            self._cancel_btn.setEnabled(False)
            self._progress_label.setText(t("profile_cancelled"))
        else:
            self.reject()
