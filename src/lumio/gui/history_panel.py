from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..history_manager import HistoryRecord
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
    ext = Path(fp).suffix
    # Fast path: single file with known extension — no filesystem I/O
    if ext in _VIDEO_EXTS:
        return "Video", "media_video"
    if ext in _IMAGE_EXTS:
        return "Image", "media_image"
    if ext in (".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg"):
        return "Audio", "media_audio"
    # No extension — might be a directory (IG carousel). Check filesystem.
    if not ext and Path(rec.file_path).is_dir():
        try:
            exts = {f.suffix.lower() for f in Path(rec.file_path).iterdir() if f.is_file()}
            has_video = exts & _VIDEO_EXTS
            has_image = exts & _IMAGE_EXTS
            if has_video and has_image:
                return "Mixed", "media_mixed"
            if has_video:
                return "Video", "media_video"
            if has_image:
                return "Image", "media_image"
        except OSError:
            pass
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
            url_lbl.setObjectName("url_link")
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


class BatchGroupWidget(QFrame):
    """Collapsible batch group for history records sharing a batch_id."""

    action_requested = Signal(str, str)  # record_id, action

    def __init__(self, records: list[HistoryRecord], parent=None):
        super().__init__(parent)
        self._records = records
        self._expanded = False
        self.setObjectName("history_card")
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 6, 10, 6)
        root.setSpacing(2)

        # Clickable header area
        self._header = QWidget()
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.mousePressEvent = self._on_header_click
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        # Platform badge (from first record)
        rec0 = self._records[0]
        badge_text, badge_obj = _platform_badge(rec0.platform)
        badge = QLabel(badge_text)
        if badge_obj:
            badge.setObjectName(badge_obj)
        badge.setFixedSize(32, 20)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(badge)

        # Expand indicator
        self._arrow = QLabel("▶")
        self._arrow.setObjectName("muted")
        self._arrow.setFixedWidth(14)
        header_layout.addWidget(self._arrow)

        # Info column
        info = QVBoxLayout()
        info.setSpacing(1)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        author_text = f"@{rec0.author}" if rec0.author else ""
        title = QLabel(f"{t('batch_download')}  {author_text}")
        title.setObjectName("task_title")
        title_row.addWidget(title, 1)

        count_label = QLabel(f"{len(self._records)} {t('batch_items')}")
        count_label.setObjectName("muted")
        count_label.setStyleSheet("font-size: 11px;")
        title_row.addWidget(count_label)
        info.addLayout(title_row)

        # Meta row: total size + latest time
        meta_row = QHBoxLayout()
        meta_row.setSpacing(12)
        total_size = sum(r.file_size for r in self._records)
        size_label = QLabel(_format_size(total_size))
        size_label.setObjectName("muted")
        size_label.setStyleSheet("font-size: 11px;")
        meta_row.addWidget(size_label)

        latest_time = max((r.download_time for r in self._records if r.download_time), default="")
        time_str = latest_time[:16].replace("T", " ") if latest_time else ""
        time_label = QLabel(time_str)
        time_label.setObjectName("muted")
        time_label.setStyleSheet("font-size: 11px;")
        meta_row.addWidget(time_label)
        meta_row.addStretch()
        info.addLayout(meta_row)

        header_layout.addLayout(info, 1)

        # Action buttons (separate from header click area)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        btn_row.setContentsMargins(0, 0, 0, 0)

        dir_btn = QPushButton(t("history_open_dir"))
        dir_btn.setObjectName("task_btn")
        dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dir_btn.clicked.connect(self._open_dir)
        btn_row.addWidget(dir_btn)

        del_btn = QPushButton(t("history_delete"))
        del_btn.setObjectName("task_btn_danger")
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.clicked.connect(self._delete_batch)
        btn_row.addWidget(del_btn)

        header_layout.addLayout(btn_row)
        root.addWidget(self._header)

        # Children container (hidden by default)
        self._children_widget = QWidget()
        self._children_layout = QVBoxLayout(self._children_widget)
        self._children_layout.setContentsMargins(44, 2, 0, 0)
        self._children_layout.setSpacing(2)

        for rec in self._records:
            child = HistoryRecordWidget(rec)
            child.action_requested.connect(self.action_requested)
            self._children_layout.addWidget(child)

        self._children_widget.setVisible(False)
        root.addWidget(self._children_widget)

    def _on_header_click(self, event):
        self._expanded = not self._expanded
        self._children_widget.setVisible(self._expanded)
        self._arrow.setText("▼" if self._expanded else "▶")

    def _open_dir(self):
        if self._records:
            self.action_requested.emit(self._records[0].record_id, "open_dir")

    def _delete_batch(self):
        for rec in self._records:
            self.action_requested.emit(rec.record_id, "delete")

    def match_filter(self, query: str, platform: str) -> bool:
        """Check if any child record matches the filter criteria."""
        for rec in self._records:
            if platform and rec.platform != platform:
                continue
            if query:
                text = f"{rec.title} {rec.author} {rec.url} {rec.file_path} {rec.download_time}".lower()
                if query.lower() not in text:
                    continue
            return True
        return False
