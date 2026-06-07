from __future__ import annotations

import threading
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, Slot
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

from ..downloader import enumerate_yt_videos, fetch_yt_channel_info, _yt_entry_to_queue_task
from ..i18n import t
from ..utils.config import get_download_dir
from .widgets import NoWheelComboBox


class _YtInfoWorker(QThread):
    finished = Signal(object)

    def __init__(self, url: str):
        super().__init__()
        self._url = url

    def run(self):
        try:
            info = fetch_yt_channel_info(self._url)
            self.finished.emit(info)
        except Exception as e:
            self.finished.emit(e)


class _YtEnumerateWorker(QThread):
    progress = Signal(int, int)
    finished = Signal(object)

    def __init__(self, url: str, limit: int, cancel_event: threading.Event):
        super().__init__()
        self._url = url
        self._limit = limit
        self._cancel_event = cancel_event

    def run(self):
        try:
            entries = enumerate_yt_videos(
                self._url,
                self._limit,
                callback=lambda cur, tot: self.progress.emit(cur, tot),
                cancel_event=self._cancel_event,
            )
            self.finished.emit(entries)
        except Exception as e:
            self.finished.emit(e)


_YT_TAB_LABELS = {
    "videos": "yt_tab_videos",
    "shorts": "yt_tab_shorts",
    "streams": "yt_tab_streams",
    "live": "yt_tab_streams",
    "playlists": "yt_tab_playlists",
    "channels": "yt_tab_channels",
    "community": "yt_tab_community",
}


class YouTubeDialog(QDialog):
    batch_add_requested = Signal(object)

    def __init__(self, url: str, tab: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._url = url
        self._tab = tab
        self._channel_info: dict | None = None
        self._cancel_event = threading.Event()

        self.setWindowTitle(t("yt_dialog_title"))
        self.setMinimumWidth(460)
        self.setModal(True)
        self._build_ui()
        self._start_fetch_info()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        # ---- Channel header ----
        self._title_label = QLabel(t("yt_fetching"))
        self._title_label.setObjectName("accent")
        self._title_label.setWordWrap(True)
        root.addWidget(self._title_label)

        self._channel_label = QLabel("")
        self._channel_label.setObjectName("muted")
        root.addWidget(self._channel_label)

        if self._tab:
            key = _YT_TAB_LABELS.get(self._tab)
            tab_text = t(key) if key else self._tab
            self._tab_label = QLabel(tab_text)
            self._tab_label.setObjectName("muted")
            self._tab_label.setStyleSheet("font-size: 11px;")
            root.addWidget(self._tab_label)

        # ---- Settings group ----
        settings_group = QGroupBox(t("yt_videos_label"))
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
        self._name_input = QLineEdit()
        name_row.addWidget(self._name_input, 1)
        sg.addLayout(name_row)

        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel(t("format_label")))
        self._format_combo = NoWheelComboBox()
        self._format_combo.addItem(t("yt_fmt_best"), ("best", "combined"))
        self._format_combo.addItem("1080p", ("bestvideo[height<=1080]+bestaudio/best[height<=1080]", "video"))
        self._format_combo.addItem("720p", ("bestvideo[height<=720]+bestaudio/best[height<=720]", "video"))
        self._format_combo.addItem("480p", ("bestvideo[height<=480]+bestaudio/best[height<=480]", "video"))
        self._format_combo.addItem(t("yt_fmt_audio"), ("bestaudio", "audio"))
        fmt_row.addWidget(self._format_combo, 1)
        sg.addLayout(fmt_row)

        root.addWidget(settings_group)

        # ---- Progress section ----
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
        self._info_worker = _YtInfoWorker(self._url)
        self._info_worker.finished.connect(self._on_info_done)
        self._info_worker.start()

    @Slot(object)
    def _on_info_done(self, result):
        if isinstance(result, Exception):
            QMessageBox.warning(self, t("error"), t("yt_error", err=str(result)))
            self.reject()
            return

        self._channel_info = result
        title = result.get("title", "")
        channel = result.get("channel", "")
        self._title_label.setText(title)
        if channel and channel != title:
            self._channel_label.setText(channel)
        self._name_input.setPlaceholderText(t("yt_name_hint"))
        self._from_spin.setEnabled(True)
        self._to_spin.setEnabled(True)
        self._add_btn.setEnabled(True)

    @Slot()
    def _on_add_to_queue(self):
        if not self._channel_info:
            return

        start = self._from_spin.value()
        end = self._to_spin.value()
        if start > end:
            start, end = end, start

        self._progress_widget.show()
        self._progress_label.setText(t("yt_fetching"))
        self._progress_bar.setRange(0, 0)
        self._add_btn.setEnabled(False)
        self._from_spin.setEnabled(False)
        self._to_spin.setEnabled(False)
        self._name_input.setEnabled(False)

        self._cancel_event.clear()
        self._enumerate_worker = _YtEnumerateWorker(self._url, end, self._cancel_event)
        self._enumerate_worker.progress.connect(self._on_enumerate_progress)
        self._enumerate_worker.finished.connect(self._on_enumerate_done)
        self._enumerate_worker.start()

    @Slot(int, int)
    def _on_enumerate_progress(self, current: int, total: int):
        self._progress_label.setText(t("yt_enumerating", current=current, total=total))
        self._progress_bar.setRange(0, total)
        self._progress_bar.setValue(current)

    @Slot(object)
    def _on_enumerate_done(self, result):
        if isinstance(result, Exception):
            QMessageBox.warning(self, t("error"), t("yt_error", err=str(result)))
            self._reset_controls()
            return

        if isinstance(result, list) and self._cancel_event.is_set():
            if not result:
                QMessageBox.information(self, t("profile_cancelled"), t("profile_cancelled"))
                self._reset_controls()
                return

        entries = result
        if not entries:
            QMessageBox.information(self, t("yt_no_videos"), t("yt_no_videos"))
            self._reset_controls()
            return

        # Slice to selected range
        start = self._from_spin.value()
        end = self._to_spin.value()
        if start > end:
            start, end = end, start
        entries = entries[start - 1:end]

        custom_name = self._name_input.text().strip()
        output_dir = Path(get_download_dir())
        batch_id = uuid.uuid4().hex[:12]
        channel_name = self._channel_info.get("channel", self._channel_info.get("title", ""))

        fmt_data = self._format_combo.currentData()
        format_id, format_type = fmt_data if isinstance(fmt_data, tuple) else ("best", "combined")
        tasks = [_yt_entry_to_queue_task(e, custom_name, output_dir, format_id=format_id,
                                         format_type=format_type, batch_id=batch_id,
                                         default_author=channel_name) for e in entries]

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
        if hasattr(self, "_enumerate_worker") and self._enumerate_worker.isRunning():
            self._cancel_event.set()
            self._cancel_btn.setEnabled(False)
            self._progress_label.setText(t("profile_cancelled"))
        else:
            self.reject()
