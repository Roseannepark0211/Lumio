from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..history_manager import HistoryManager, HistoryRecord
from ..i18n import t


def _format_size(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "—"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def _platform_badge(platform: str) -> tuple[str, str]:
    if platform == "youtube":
        return "YT", "platform_yt"
    if platform == "instagram":
        return "IG", "platform_ig"
    if platform == "x":
        return "X", "platform_x"
    return platform[:2].upper(), ""


_VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv"}
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def _media_badge(rec: HistoryRecord) -> tuple[str, str]:
    """Return (label, objectName) for media type badge based on file path."""
    fp = rec.file_path.lower()
    # Check all files in the record (may be a directory with multiple files)
    if Path(rec.file_path).is_dir():
        # IG carousel: check extensions of files inside
        try:
            exts = {f.suffix.lower() for f in Path(rec.file_path).iterdir() if f.is_file()}
            has_video = exts & _VIDEO_EXTS
            has_image = exts & _IMAGE_EXTS
            if has_video and has_image:
                return "Mixed", "media_mixed"
            if has_video:
                return "MP4", "media_video"
            if has_image:
                return "JPG", "media_image"
        except OSError:
            pass
        return "", ""
    # Single file
    ext = Path(fp).suffix
    if ext in _VIDEO_EXTS:
        return "MP4", "media_video"
    if ext in _IMAGE_EXTS:
        return "JPG", "media_image"
    if ext in (".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg"):
        return "MP3", "media_audio"
    return "", ""


class HistoryRecordWidget(QFrame):
    action_requested = Signal(str, str)  # record_id, action

    def __init__(self, record: HistoryRecord, parent=None):
        super().__init__(parent)
        self.record_id = record.record_id
        self.setObjectName("history_card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._expanded = False
        self._build_ui(record)

    def _build_ui(self, rec: HistoryRecord):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 6, 10, 6)
        root.setSpacing(2)

        # Main row
        top = QHBoxLayout()
        top.setSpacing(8)

        # Platform badge
        badge_text, badge_obj = _platform_badge(rec.platform)
        badge = QLabel(badge_text)
        if badge_obj:
            badge.setObjectName(badge_obj)
        badge.setFixedSize(32, 20)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(badge)

        # Media type badge (based on file extension)
        media_label, media_obj = _media_badge(rec)
        if media_label:
            mbadge = QLabel(media_label)
            mbadge.setObjectName(media_obj)
            mbadge.setFixedHeight(16)
            top.addWidget(mbadge)

        # Info column
        info = QVBoxLayout()
        info.setSpacing(1)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title = QLabel(rec.title[:60] if rec.title else rec.url[:60])
        title.setObjectName("task_title")
        title_row.addWidget(title, 1)

        if rec.author:
            author = QLabel(f"@{rec.author}")
            author.setObjectName("muted")
            author.setStyleSheet("font-size: 11px;")
            title_row.addWidget(author)
        info.addLayout(title_row)

        # Time + size row
        meta_row = QHBoxLayout()
        meta_row.setSpacing(12)
        time_str = rec.download_time[:16].replace("T", " ") if rec.download_time else ""
        time_label = QLabel(time_str)
        time_label.setObjectName("muted")
        time_label.setStyleSheet("font-size: 11px;")
        meta_row.addWidget(time_label)

        size_label = QLabel(_format_size(rec.file_size))
        size_label.setObjectName("muted")
        size_label.setStyleSheet("font-size: 11px;")
        meta_row.addWidget(size_label)
        meta_row.addStretch()
        info.addLayout(meta_row)

        top.addLayout(info, 1)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        btn_row.setContentsMargins(0, 0, 0, 0)

        open_btn = QPushButton(t("history_open_file"))
        open_btn.setObjectName("task_btn")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(lambda: self.action_requested.emit(self.record_id, "open_file"))
        btn_row.addWidget(open_btn)

        dir_btn = QPushButton(t("history_open_dir"))
        dir_btn.setObjectName("task_btn")
        dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dir_btn.clicked.connect(lambda: self.action_requested.emit(self.record_id, "open_dir"))
        btn_row.addWidget(dir_btn)

        del_btn = QPushButton(t("history_delete"))
        del_btn.setObjectName("task_btn_danger")
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.clicked.connect(lambda: self.action_requested.emit(self.record_id, "delete"))
        btn_row.addWidget(del_btn)

        top.addLayout(btn_row)
        root.addLayout(top)

        # Detail row (hidden by default)
        self._detail = QWidget()
        detail_layout = QVBoxLayout(self._detail)
        detail_layout.setContentsMargins(40, 2, 0, 0)
        detail_layout.setSpacing(1)

        if rec.url:
            url_lbl = QLabel(rec.url)
            url_lbl.setObjectName("muted")
            url_lbl.setStyleSheet("font-size: 11px; color: #7c8fff;")
            url_lbl.setWordWrap(True)
            detail_layout.addWidget(url_lbl)

        if rec.file_path:
            path_lbl = QLabel(rec.file_path)
            path_lbl.setObjectName("muted")
            path_lbl.setStyleSheet("font-size: 11px;")
            path_lbl.setWordWrap(True)
            detail_layout.addWidget(path_lbl)

        self._detail.setVisible(False)
        root.addWidget(self._detail)

    def mousePressEvent(self, event):
        # Toggle detail on click (but not if clicking a button)
        child = self.childAt(event.position().toPoint())
        if isinstance(child, QPushButton):
            super().mousePressEvent(event)
            return
        self._expanded = not self._expanded
        self._detail.setVisible(self._expanded)


class HistoryDrawer(QWidget):
    action_requested = Signal(str, str)  # record_id, action

    def __init__(self, history_manager: HistoryManager, parent=None):
        super().__init__(parent)
        self._hm = history_manager
        self._record_widgets: dict[str, HistoryRecordWidget] = {}
        self._expanded = False
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar
        self._header = QFrame()
        self._header.setObjectName("history_header")
        hdr = QHBoxLayout(self._header)
        hdr.setContentsMargins(12, 6, 12, 6)
        hdr.setSpacing(8)

        title = QLabel(t("history_title"))
        title.setObjectName("queue_title")
        hdr.addWidget(title)

        self._badge = QLabel(str(len(self._hm.records)))
        self._badge.setObjectName("history_badge")
        self._badge.setVisible(len(self._hm.records) > 0)
        hdr.addWidget(self._badge)

        hdr.addStretch()

        # Search box
        self._search = QLineEdit()
        self._search.setObjectName("history_search")
        self._search.setPlaceholderText(t("history_search"))
        self._search.setFixedWidth(160)
        self._search.setFixedHeight(26)
        self._search.textChanged.connect(self._on_search)
        hdr.addWidget(self._search)

        # Clear button
        self._clear_btn = QPushButton(t("history_clear"))
        self._clear_btn.setObjectName("task_btn_danger")
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setFixedHeight(26)
        self._clear_btn.clicked.connect(self._on_clear)
        hdr.addWidget(self._clear_btn)

        # Toggle arrow
        self._toggle_btn = QPushButton("▲")
        self._toggle_btn.setObjectName("task_btn")
        self._toggle_btn.setFixedSize(28, 28)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.clicked.connect(self._toggle)
        hdr.addWidget(self._toggle_btn)

        root.addWidget(self._header)

        # Scrollable list (collapsible)
        self._list_container = QWidget()
        lc_layout = QVBoxLayout(self._list_container)
        lc_layout.setContentsMargins(0, 0, 0, 0)
        lc_layout.setSpacing(0)

        self._empty_label = QLabel(t("history_empty"))
        self._empty_label.setObjectName("muted")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("padding: 24px; font-size: 13px;")
        self._empty_label.setVisible(len(self._hm.records) == 0)
        lc_layout.addWidget(self._empty_label)

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
        lc_layout.addWidget(self._scroll)

        self._list_container.setMaximumHeight(0)
        self._list_container.setVisible(False)
        root.addWidget(self._list_container)

        # Load existing records
        for rec in self._hm.records:
            self._add_record_widget(rec, at_end=True)

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

    def _add_record_widget(self, rec: HistoryRecord, at_end: bool = False):
        widget = HistoryRecordWidget(rec)
        widget.action_requested.connect(self._on_action)
        self._record_widgets[rec.record_id] = widget
        if at_end:
            self._list_layout.insertWidget(self._list_layout.count() - 1, widget)
        else:
            self._list_layout.insertWidget(0, widget)
        self._update_empty()

    def _update_empty(self):
        has_records = len(self._record_widgets) > 0
        self._empty_label.setVisible(not has_records)
        self._badge.setText(str(len(self._record_widgets)))
        self._badge.setVisible(has_records)

    @Slot(str)
    def _on_search(self, text: str):
        text = text.lower().strip()
        for rid, widget in self._record_widgets.items():
            if not text:
                widget.setVisible(True)
                continue
            rec = next((r for r in self._hm.records if r.record_id == rid), None)
            if rec:
                searchable = f"{rec.title} {rec.author} {rec.platform} {rec.url}".lower()
                widget.setVisible(text in searchable)
            else:
                widget.setVisible(False)

    def _on_clear(self):
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, t("history_title"), t("history_confirm_clear"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._hm.clear()
        for widget in self._record_widgets.values():
            widget.deleteLater()
        self._record_widgets.clear()
        self._update_empty()

    def _on_action(self, record_id: str, action: str):
        rec = next((r for r in self._hm.records if r.record_id == record_id), None)
        if not rec:
            return
        if action == "open_file":
            if rec.file_path and Path(rec.file_path).exists():
                os.startfile(rec.file_path)
        elif action == "open_dir":
            if rec.file_path:
                parent = Path(rec.file_path).parent
                if parent.exists():
                    os.startfile(str(parent))
        elif action == "delete":
            widget = self._record_widgets.pop(record_id, None)
            if widget:
                widget.deleteLater()
            self._hm.delete(record_id)
            self._update_empty()

    @Slot(HistoryRecord)
    def on_history_added(self, record: HistoryRecord):
        """Called externally when a new history record is added."""
        self._add_record_widget(record, at_end=False)
        if not self._expanded:
            self._toggle()
