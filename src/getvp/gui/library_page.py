from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..i18n import t
from ..library_manager import LibraryManager
from ..models import LibraryItem
from .library_panel import LibraryItemWidget


class LibraryPage(QWidget):
    def __init__(self, library_manager: LibraryManager, parent=None):
        super().__init__(parent)
        self.setObjectName("library_page")
        self._lm = library_manager
        self._item_widgets: dict[str, LibraryItemWidget] = {}
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar
        header = QHBoxLayout()
        header.setContentsMargins(32, 20, 32, 12)
        header.setSpacing(10)

        title = QLabel(t("library_title"))
        title.setObjectName("page_title")
        header.addWidget(title)

        self._badge = QLabel("0")
        self._badge.setObjectName("history_badge")
        self._badge.setVisible(False)
        header.addWidget(self._badge)

        header.addStretch()

        # Favorites filter toggle
        self._fav_toggle = QPushButton("♥")
        self._fav_toggle.setObjectName("fav_btn")
        self._fav_toggle.setCheckable(True)
        self._fav_toggle.setFixedSize(30, 30)
        self._fav_toggle.setToolTip(t("library_filter_favorites"))
        self._fav_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fav_toggle.clicked.connect(self._apply_filter)
        header.addWidget(self._fav_toggle)

        # Platform filter
        self._platform_combo = QComboBox()
        self._platform_combo.setObjectName("history_filter")
        self._platform_combo.setFixedWidth(120)
        self._platform_combo.addItem(t("library_filter_all_platform"), "all")
        self._platform_combo.addItem("YouTube", "youtube")
        self._platform_combo.addItem("Instagram", "instagram")
        self._platform_combo.addItem("X (Twitter)", "x")
        self._platform_combo.currentIndexChanged.connect(self._apply_filter)
        header.addWidget(self._platform_combo)

        # Media type filter
        self._type_combo = QComboBox()
        self._type_combo.setObjectName("history_filter")
        self._type_combo.setFixedWidth(100)
        self._type_combo.addItem(t("library_filter_all_type"), "all")
        self._type_combo.addItem(t("library_filter_video"), "video")
        self._type_combo.addItem(t("library_filter_audio"), "audio")
        self._type_combo.addItem(t("library_filter_image"), "image")
        self._type_combo.currentIndexChanged.connect(self._apply_filter)
        header.addWidget(self._type_combo)

        # Search box
        self._search = QLineEdit()
        self._search.setObjectName("history_search")
        self._search.setPlaceholderText(t("library_search"))
        self._search.setFixedWidth(200)
        self._search.setFixedHeight(30)
        self._search.textChanged.connect(self._apply_filter)
        header.addWidget(self._search)

        root.addLayout(header)

        # Scrollable list
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
        self._empty_label = QLabel(t("library_empty"))
        self._empty_label.setObjectName("muted")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("padding: 40px; font-size: 14px;")
        self._list_layout.insertWidget(0, self._empty_label)

        # Load existing items
        for item in self._lm.get_all_items():
            self._add_item_widget(item)

        self._update_empty()

    def _add_item_widget(self, item: LibraryItem):
        widget = LibraryItemWidget(item)
        widget.action_requested.connect(self._on_action)
        self._item_widgets[item.id] = widget
        self._list_layout.insertWidget(self._list_layout.count() - 1, widget)

    def _update_empty(self):
        has_items = len(self._item_widgets) > 0
        self._empty_label.setVisible(not has_items)
        visible_count = sum(1 for w in self._item_widgets.values() if w.isVisible())
        self._badge.setText(str(visible_count))
        self._badge.setVisible(visible_count > 0)

    @Slot()
    def _apply_filter(self):
        search_text = self._search.text().strip()
        platform_filter = self._platform_combo.currentData()
        type_filter = self._type_combo.currentData()
        favorites_only = self._fav_toggle.isChecked()

        items = self._lm.search(
            query=search_text,
            platform=platform_filter if platform_filter != "all" else "",
            media_type=type_filter if type_filter != "all" else "",
            favorites_only=favorites_only,
        )

        visible_ids = {item.id for item in items}
        for item_id, widget in self._item_widgets.items():
            widget.setVisible(item_id in visible_ids)

        self._update_empty()

    def _on_action(self, item_id: str, action: str):
        item = self._lm.get_item(item_id)
        if not item:
            return
        if action == "open_file":
            if item.file_path and Path(item.file_path).exists():
                os.startfile(item.file_path)
        elif action == "open_dir":
            if item.file_path:
                parent = Path(item.file_path).parent
                if parent.exists():
                    os.startfile(str(parent))
        elif action == "delete":
            widget = self._item_widgets.pop(item_id, None)
            if widget:
                widget.deleteLater()
            self._lm.delete_item(item_id)
            self._update_empty()
        elif action == "toggle_favorite":
            new_state = self._lm.toggle_favorite(item_id)
            widget = self._item_widgets.get(item_id)
            if widget:
                widget.update_favorite(new_state)
            self._apply_filter()
        elif action == "toggle_pin":
            new_state = self._lm.toggle_pinned(item_id)
            widget = self._item_widgets.get(item_id)
            if widget:
                widget.update_pinned(new_state)

    def on_item_added(self, item: LibraryItem):
        """Slot connected to DownloadManager.library_record_added."""
        self._add_item_widget(item)
        self._update_empty()
        self._apply_filter()
