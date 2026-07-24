from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..i18n import t
from ..models import LibraryItem
from .history_panel import _format_size, _platform_badge


class _ClickableLabel(QLabel):
    """QLabel that emits clicked() on mouse press."""
    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


def _media_label(media_type: str) -> tuple[str, str]:
    mapping = {
        "video": ("Video", "media_video"),
        "audio": ("Audio", "media_audio"),
        "image": ("Image", "media_image"),
        "mixed": ("Mixed", "media_mixed"),
    }
    return mapping.get(media_type, ("", ""))


class LibraryItemWidget(QFrame):
    action_requested = Signal(str, str)  # item_id, action
    selection_changed = Signal(str, bool)  # item_id, checked

    def __init__(self, item: LibraryItem, parent=None):
        super().__init__(parent)
        self.item_id = item.id
        self.setObjectName("library_card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._expanded = False
        self._build_ui(item)

    def _build_ui(self, item: LibraryItem):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 6, 10, 6)
        root.setSpacing(2)

        # Main row
        top = QHBoxLayout()
        top.setSpacing(8)

        # Selection checkbox (hidden by default)
        self._checkbox = QCheckBox()
        self._checkbox.setVisible(False)
        self._checkbox.toggled.connect(lambda checked: self.selection_changed.emit(self.item_id, checked))
        top.addWidget(self._checkbox)

        # Thumbnail placeholder (clickable → preview)
        self._thumb = _ClickableLabel()
        self._thumb.setObjectName("library_card_thumb")
        self._thumb.setFixedSize(48, 48)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._thumb.setToolTip(t("library_preview"))
        if item.local_thumbnail_path and Path(item.local_thumbnail_path).exists():
            pix = QPixmap(item.local_thumbnail_path)
            if not pix.isNull():
                self._thumb.setPixmap(pix.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                self._thumb.setText(_platform_text(item.platform))
        else:
            self._thumb.setText(_platform_text(item.platform))
        self._thumb.clicked.connect(lambda: self.action_requested.emit(self.item_id, "preview"))
        top.addWidget(self._thumb)

        # Platform badge
        badge_text, badge_obj = _platform_badge(item.platform)
        badge = QLabel(badge_text)
        if badge_obj:
            badge.setObjectName(badge_obj)
        badge.setFixedSize(32, 20)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(badge)

        # Media type badge
        media_label, media_obj = _media_label(item.media_type)
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
        title = QLabel(item.title[:60] if item.title else item.url[:60])
        title.setObjectName("task_title")
        title_row.addWidget(title, 1)

        if item.author:
            author = QLabel(f"@{item.author}")
            author.setObjectName("muted")
            title_row.addWidget(author)
        info.addLayout(title_row)

        # Meta row: time + size
        meta_row = QHBoxLayout()
        meta_row.setSpacing(12)
        time_str = ""
        if item.post_time:
            time_str = item.post_time[:16].replace("T", " ").replace("_", " ")
        elif item.created_at:
            time_str = str(item.created_at)[:16]
        time_label = QLabel(time_str)
        time_label.setObjectName("muted")
        meta_row.addWidget(time_label)

        size_label = QLabel(_format_size(item.file_size))
        size_label.setObjectName("muted")
        meta_row.addWidget(size_label)
        meta_row.addStretch()
        info.addLayout(meta_row)

        top.addLayout(info, 1)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        btn_row.setContentsMargins(0, 0, 0, 0)

        fav_btn = QPushButton("♥" if item.is_favorite else "♡")
        fav_btn.setObjectName("fav_btn")
        fav_btn.setCheckable(True)
        fav_btn.setChecked(item.is_favorite)
        fav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fav_btn.setFixedSize(28, 28)
        fav_btn.clicked.connect(lambda: self.action_requested.emit(self.item_id, "toggle_favorite"))
        self._fav_btn = fav_btn
        btn_row.addWidget(fav_btn)

        open_btn = QPushButton(t("library_open_file"))
        open_btn.setObjectName("task_btn")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(lambda: self.action_requested.emit(self.item_id, "open_file"))
        btn_row.addWidget(open_btn)

        dir_btn = QPushButton(t("library_open_dir"))
        dir_btn.setObjectName("task_btn")
        dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dir_btn.clicked.connect(lambda: self.action_requested.emit(self.item_id, "open_dir"))
        btn_row.addWidget(dir_btn)

        col_btn = QPushButton(t("collection_add_to"))
        col_btn.setObjectName("task_btn")
        col_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        col_btn.clicked.connect(lambda: self.action_requested.emit(self.item_id, "show_collections"))
        btn_row.addWidget(col_btn)

        del_btn = QPushButton(t("library_delete"))
        del_btn.setObjectName("task_btn_danger")
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.clicked.connect(lambda: self.action_requested.emit(self.item_id, "delete"))
        btn_row.addWidget(del_btn)

        top.addLayout(btn_row)
        root.addLayout(top)

        # Detail row (hidden by default)
        self._detail = QWidget()
        detail_layout = QVBoxLayout(self._detail)
        detail_layout.setContentsMargins(56, 2, 0, 0)
        detail_layout.setSpacing(1)

        if item.url:
            url_lbl = QLabel(item.url)
            url_lbl.setObjectName("url_link")
            url_lbl.setWordWrap(True)
            detail_layout.addWidget(url_lbl)

        if item.file_path:
            path_lbl = QLabel(item.file_path)
            path_lbl.setObjectName("muted")
            path_lbl.setWordWrap(True)
            detail_layout.addWidget(path_lbl)

        self._detail.setVisible(False)
        root.addWidget(self._detail)

    def update_favorite(self, is_favorite: bool):
        self._fav_btn.setChecked(is_favorite)
        self._fav_btn.setText("♥" if is_favorite else "♡")

    def update_thumbnail(self, local_path: str):
        """Update thumbnail image after async generation."""
        if local_path and Path(local_path).exists():
            pix = QPixmap(local_path)
            if not pix.isNull():
                self._thumb.setPixmap(pix.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def set_checkable(self, enabled: bool):
        self._checkbox.setVisible(enabled)
        if not enabled:
            self._checkbox.setChecked(False)

    def setChecked(self, checked: bool):
        """Programmatically set checkbox state (used by select-all)."""
        self._checkbox.setChecked(checked)

    def mousePressEvent(self, event):
        child = self.childAt(event.position().toPoint())
        if isinstance(child, (QPushButton, QCheckBox)):
            super().mousePressEvent(event)
            return
        self._expanded = not self._expanded
        self._detail.setVisible(self._expanded)


def _platform_text(platform: str) -> str:
    mapping = {"youtube": "YT", "instagram": "IG", "x": "X"}
    return mapping.get(platform, "?")
