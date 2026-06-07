from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..i18n import t
from ..library_manager import LibraryManager
from ..models import LibraryItem
from .library_panel import LibraryItemWidget
from .preview_dialog import AudioPreviewDialog, ImagePreviewDialog, VideoPreviewDialog


class LibraryPage(QWidget):
    def __init__(self, library_manager: LibraryManager, parent=None):
        super().__init__(parent)
        self.setObjectName("library_page")
        self._lm = library_manager
        self._item_widgets: dict[str, LibraryItemWidget] = {}
        self._collection_filter: int | None = None
        self._select_mode = False
        self._selected: set[str] = set()
        self._build_ui()
        self._lm.thumbnail_updated.connect(self._on_thumbnail_updated)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- Row 1: Title + Search + Reset ---
        header = QHBoxLayout()
        header.setContentsMargins(32, 20, 32, 8)
        header.setSpacing(10)

        title = QLabel(t("library_title"))
        title.setObjectName("page_title")
        header.addWidget(title)

        self._badge = QLabel("0")
        self._badge.setObjectName("history_badge")
        self._badge.setVisible(False)
        header.addWidget(self._badge)

        header.addStretch()

        # Search box (wide, prominent)
        self._search = QLineEdit()
        self._search.setObjectName("history_search")
        self._search.setPlaceholderText(t("library_search"))
        self._search.setMinimumWidth(280)
        self._search.setFixedHeight(30)
        self._search.textChanged.connect(self._apply_filter)
        header.addWidget(self._search)

        # Reset filters button
        self._reset_btn = QPushButton(t("library_reset_filters"))
        self._reset_btn.setObjectName("secondary")
        self._reset_btn.setFixedHeight(30)
        self._reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reset_btn.clicked.connect(self._reset_filters)
        header.addWidget(self._reset_btn)

        root.addLayout(header)

        # --- Row 2: Filters + Date range + Select mode ---
        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(32, 0, 32, 8)
        filter_row.setSpacing(8)

        # Favorites filter toggle
        self._fav_toggle = QPushButton("♥")
        self._fav_toggle.setObjectName("fav_btn")
        self._fav_toggle.setCheckable(True)
        self._fav_toggle.setFixedSize(30, 28)
        self._fav_toggle.setToolTip(t("library_filter_favorites"))
        self._fav_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fav_toggle.clicked.connect(self._apply_filter)
        filter_row.addWidget(self._fav_toggle)

        # Platform filter
        self._platform_combo = QComboBox()
        self._platform_combo.setObjectName("history_filter")
        self._platform_combo.setFixedWidth(104)
        self._platform_combo.setFixedHeight(28)
        self._platform_combo.addItem(t("library_filter_all_platform"), "all")
        self._platform_combo.addItem("YouTube", "youtube")
        self._platform_combo.addItem("Instagram", "instagram")
        self._platform_combo.addItem("X (Twitter)", "x")
        self._platform_combo.currentIndexChanged.connect(self._apply_filter)
        filter_row.addWidget(self._platform_combo)

        # Media type filter
        self._type_combo = QComboBox()
        self._type_combo.setObjectName("history_filter")
        self._type_combo.setFixedWidth(104)
        self._type_combo.setFixedHeight(28)
        self._type_combo.addItem(t("library_filter_all_type"), "all")
        self._type_combo.addItem(t("library_filter_video"), "video")
        self._type_combo.addItem(t("library_filter_audio"), "audio")
        self._type_combo.addItem(t("library_filter_image"), "image")
        self._type_combo.currentIndexChanged.connect(self._apply_filter)
        filter_row.addWidget(self._type_combo)

        # Batch filter
        self._batch_combo = QComboBox()
        self._batch_combo.setObjectName("history_filter")
        self._batch_combo.setFixedWidth(104)
        self._batch_combo.setFixedHeight(28)
        self._batch_combo.addItem(t("library_filter_all_batch"), "all")
        self._batch_combo.currentIndexChanged.connect(self._apply_filter)
        filter_row.addWidget(self._batch_combo)

        # Separator
        sep = QLabel("|")
        sep.setObjectName("muted")
        filter_row.addWidget(sep)

        # Date range
        from_label = QLabel(t("library_date_from") + ":")
        from_label.setObjectName("muted")
        filter_row.addWidget(from_label)
        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDisplayFormat("yyyy-MM-dd")
        from PySide6.QtCore import QDate
        self._date_from.setDate(QDate(2020, 1, 1))
        self._date_from.setMaximumDate(QDate.currentDate())
        self._date_from.setFixedWidth(110)
        self._date_from.setFixedHeight(28)
        self._date_from.dateChanged.connect(self._on_date_from_changed)
        filter_row.addWidget(self._date_from)

        to_label = QLabel(t("library_date_to") + ":")
        to_label.setObjectName("muted")
        filter_row.addWidget(to_label)
        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDisplayFormat("yyyy-MM-dd")
        self._date_to.setDate(QDate.currentDate())
        self._date_to.setMaximumDate(QDate.currentDate())
        self._date_to.setMinimumDate(self._date_from.date())
        self._date_to.setFixedWidth(110)
        self._date_to.setFixedHeight(28)
        self._date_to.dateChanged.connect(self._on_date_to_changed)
        filter_row.addWidget(self._date_to)

        # Select mode toggle
        filter_row.addStretch()
        self._select_btn = QPushButton(t("library_batch_select"))
        self._select_btn.setObjectName("secondary")
        self._select_btn.setFixedHeight(28)
        self._select_btn.clicked.connect(self._toggle_select_mode)
        filter_row.addWidget(self._select_btn)

        root.addLayout(filter_row)

        # --- Batch action bar (hidden by default) ---
        self._batch_bar = QWidget()
        self._batch_bar.setObjectName("batch_bar")
        batch_layout = QHBoxLayout(self._batch_bar)
        batch_layout.setContentsMargins(32, 6, 32, 6)
        batch_layout.setSpacing(10)

        self._batch_label = QLabel("")
        self._batch_label.setObjectName("muted")
        batch_layout.addWidget(self._batch_label)

        batch_layout.addStretch()

        batch_fav_btn = QPushButton(t("library_batch_fav"))
        batch_fav_btn.setObjectName("secondary")
        batch_fav_btn.clicked.connect(self._batch_favorite)
        batch_layout.addWidget(batch_fav_btn)

        batch_col_btn = QPushButton(t("library_batch_collection"))
        batch_col_btn.setObjectName("secondary")
        batch_col_btn.clicked.connect(self._batch_collection)
        batch_layout.addWidget(batch_col_btn)

        batch_del_btn = QPushButton(t("library_batch_delete"))
        batch_del_btn.setObjectName("task_btn_danger")
        batch_del_btn.clicked.connect(self._batch_delete)
        batch_layout.addWidget(batch_del_btn)

        self._batch_bar.setVisible(False)
        root.addWidget(self._batch_bar)

        # --- Scrollable list ---
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

        self._refresh_batch_combo()
        self._update_empty()

    # ---- Item widgets ----

    def _add_item_widget(self, item: LibraryItem):
        widget = LibraryItemWidget(item)
        widget.action_requested.connect(self._on_action)
        widget.selection_changed.connect(self._on_selection_changed)
        self._item_widgets[item.id] = widget
        self._list_layout.insertWidget(self._list_layout.count() - 1, widget)

    def _update_empty(self):
        has_items = len(self._item_widgets) > 0
        self._empty_label.setVisible(not has_items)
        visible_count = sum(1 for w in self._item_widgets.values() if w.isVisible())
        self._badge.setText(str(visible_count))
        self._badge.setVisible(visible_count > 0)

    def _on_thumbnail_updated(self, item_id: str, local_path: str):
        """Slot: update card thumbnail when async generation completes."""
        widget = self._item_widgets.get(item_id)
        if widget:
            widget.update_thumbnail(local_path)

    # ---- Filters ----

    def _refresh_batch_combo(self):
        """Rebuild batch_id combo with human-readable labels."""
        current = self._batch_combo.currentData()
        self._batch_combo.blockSignals(True)
        self._batch_combo.clear()
        self._batch_combo.addItem(t("library_filter_all_batch"), "all")
        for bid in self._lm.get_all_batch_ids():
            items = self._lm.search(batch_id=bid)
            if items:
                first = items[0]
                platform = first.platform.upper() if first.platform else "?"
                author = first.author[:12] if first.platform else ""
                count = len(items)
                label = f"{platform} {author} ({count})".strip()
            else:
                label = bid[:12]
            self._batch_combo.addItem(label, bid)
        # Restore previous selection
        idx = self._batch_combo.findData(current)
        if idx >= 0:
            self._batch_combo.setCurrentIndex(idx)
        self._batch_combo.blockSignals(False)

    def _reset_filters(self):
        """Clear all filter controls to defaults."""
        self._search.blockSignals(True)
        self._search.clear()
        self._search.blockSignals(False)
        self._platform_combo.setCurrentIndex(0)
        self._type_combo.setCurrentIndex(0)
        self._batch_combo.setCurrentIndex(0)
        self._fav_toggle.setChecked(False)
        from PySide6.QtCore import QDate
        self._date_from.setDate(QDate(2020, 1, 1))
        self._date_to.setDate(QDate.currentDate())
        self._date_to.setMinimumDate(self._date_from.date())
        self._date_from.setMaximumDate(QDate.currentDate())
        self._apply_filter()

    def _on_date_from_changed(self):
        """Sync To's minimum date when From changes."""
        from PySide6.QtCore import QDate
        from_date = self._date_from.date()
        self._date_to.setMinimumDate(from_date)
        if self._date_to.date() < from_date:
            self._date_to.setDate(from_date)
        self._apply_filter()

    def _on_date_to_changed(self):
        """Sync From's maximum date when To changes."""
        from PySide6.QtCore import QDate
        to_date = self._date_to.date()
        self._date_from.setMaximumDate(to_date)
        if self._date_from.date() > to_date:
            self._date_from.setDate(to_date)
        self._apply_filter()

    def _batch_collection(self):
        """Add selected items to a collection."""
        if not self._selected:
            return
        collections = self._lm.get_all_collections()
        if not collections:
            return

        from PySide6.QtWidgets import QDialog, QVBoxLayout, QRadioButton, QPushButton, QHBoxLayout, QLabel, QButtonGroup
        dlg = QDialog(self)
        dlg.setWindowTitle(t("library_batch_collection"))
        dlg.setMinimumWidth(220)
        layout = QVBoxLayout(dlg)

        label = QLabel(t("library_batch_selected", n=len(self._selected)))
        label.setObjectName("muted")
        layout.addWidget(label)

        btn_group = QButtonGroup(dlg)
        radio_btns = []
        for col in collections:
            rb = QRadioButton(f"{col.icon} {col.name}")
            btn_group.addButton(rb)
            layout.addWidget(rb)
            radio_btns.append((col.id, rb))

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondary")
        ok_btn = QPushButton("OK")
        ok_btn.setObjectName("accent_btn")
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

        cancel_btn.clicked.connect(dlg.reject)
        ok_btn.clicked.connect(dlg.accept)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            for cid, rb in radio_btns:
                if rb.isChecked():
                    for item_id in self._selected:
                        self._lm.add_item_to_collection(item_id, cid)
                    break
        self._toggle_select_mode()

    @Slot()
    def _apply_filter(self):
        search_text = self._search.text().strip()
        platform_filter = self._platform_combo.currentData()
        type_filter = self._type_combo.currentData()
        batch_filter = self._batch_combo.currentData()
        favorites_only = self._fav_toggle.isChecked()

        date_from = self._date_from.date().toString("yyyyMMdd")
        date_to = self._date_to.date().toString("yyyyMMdd")

        items = self._lm.search(
            query=search_text,
            platform=platform_filter if platform_filter != "all" else "",
            media_type=type_filter if type_filter != "all" else "",
            favorites_only=favorites_only,
            collection_id=self._collection_filter,
            date_from=date_from,
            date_to=date_to,
            batch_id=batch_filter if batch_filter != "all" else "",
        )

        visible_ids = {item.id for item in items}
        for item_id, widget in self._item_widgets.items():
            widget.setVisible(item_id in visible_ids)

        self._update_empty()

    # ---- Select mode / batch operations ----

    def _toggle_select_mode(self):
        self._select_mode = not self._select_mode
        self._selected.clear()
        for w in self._item_widgets.values():
            w.set_checkable(self._select_mode)
        self._batch_bar.setVisible(self._select_mode)
        self._select_btn.setText(t("library_batch_cancel") if self._select_mode else t("library_batch_select"))
        self._update_batch_label()

    def _on_selection_changed(self, item_id: str, checked: bool):
        if checked:
            self._selected.add(item_id)
        else:
            self._selected.discard(item_id)
        self._update_batch_label()

    def _update_batch_label(self):
        self._batch_label.setText(t("library_batch_selected", n=len(self._selected)))

    def _batch_favorite(self):
        if not self._selected:
            return
        self._lm.batch_toggle_favorite(list(self._selected), True)
        for item_id in self._selected:
            w = self._item_widgets.get(item_id)
            if w:
                w.update_favorite(True)
        self._toggle_select_mode()

    def _batch_delete(self):
        if not self._selected:
            return
        reply = QMessageBox.question(
            self, t("library_title"),
            t("library_batch_delete_confirm", n=len(self._selected)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        ids = list(self._selected)
        self._lm.batch_delete(ids)
        for item_id in ids:
            w = self._item_widgets.pop(item_id, None)
            if w:
                w.deleteLater()
        self._toggle_select_mode()
        self._update_empty()

    # ---- Actions ----

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
        elif action == "preview":
            self._open_preview(item)
        elif action == "show_collections":
            self._show_collection_dialog(item_id)

    def _open_preview(self, item: LibraryItem):
        """Open the appropriate preview dialog for the item."""
        if not item.file_path:
            return
        p = Path(item.file_path)

        # Resolve directory → list of media files
        if p.is_dir():
            media_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.mp4', '.mkv', '.webm', '.mov', '.avi', '.mp3', '.wav', '.aac', '.flac', '.ogg'}
            files = sorted(f for f in p.iterdir() if f.suffix.lower() in media_exts)
            if not files:
                return
        elif p.exists():
            files = [p]
        else:
            return

        # Infer type from actual file extension, not database media_type
        ext = files[0].suffix.lower()
        img_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
        vid_exts = {'.mp4', '.mkv', '.webm', '.mov', '.avi'}
        aud_exts = {'.mp3', '.wav', '.aac', '.flac', '.ogg'}

        if ext in img_exts:
            ImagePreviewDialog([str(f) for f in files], self).exec()
        elif ext in vid_exts:
            VideoPreviewDialog(str(files[0]), self).exec()
        elif ext in aud_exts:
            AudioPreviewDialog(str(files[0]), self).exec()

    def on_item_added(self, item: LibraryItem):
        """Slot connected to DownloadManager.library_record_added."""
        self._add_item_widget(item)
        self._refresh_batch_combo()
        self._update_empty()
        self._apply_filter()

    def set_collection_filter(self, collection_id: int | None):
        self._collection_filter = collection_id
        self._apply_filter()

    def _show_collection_dialog(self, item_id: str):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QCheckBox, QPushButton, QHBoxLayout
        collections = self._lm.get_all_collections()
        if not collections:
            return
        item_cols = {c.id for c in self._lm.get_item_collections(item_id)}

        dlg = QDialog(self)
        dlg.setWindowTitle(t("collection_add_to"))
        dlg.setMinimumWidth(220)
        layout = QVBoxLayout(dlg)

        checks: dict[int, QCheckBox] = {}
        for col in collections:
            cb = QCheckBox(f"{col.icon} {col.name}")
            cb.setChecked(col.id in item_cols)
            checks[col.id] = cb
            layout.addWidget(cb)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.setObjectName("accent_btn")
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondary")
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

        cancel_btn.clicked.connect(dlg.reject)
        ok_btn.clicked.connect(dlg.accept)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            for cid, cb in checks.items():
                was_in = cid in item_cols
                is_in = cb.isChecked()
                if is_in and not was_in:
                    self._lm.add_item_to_collection(item_id, cid)
                elif not is_in and was_in:
                    self._lm.remove_item_from_collection(item_id, cid)
            self._apply_filter()
