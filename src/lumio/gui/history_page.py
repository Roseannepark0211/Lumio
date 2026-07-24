from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
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

from ..history_manager import HistoryManager, HistoryRecord
from ..i18n import t
from .history_panel import BatchGroupWidget, HistoryRecordWidget
from .theme.paint import FocusLineEdit, GradientLabel


class HistoryPage(QWidget):
    def __init__(self, history_manager: HistoryManager, parent=None):
        super().__init__(parent)
        self.setObjectName("history_page")
        self._hm = history_manager
        self._record_widgets: dict[str, HistoryRecordWidget] = {}
        self._batch_widgets: list[BatchGroupWidget] = []
        self._batch_widget_map: dict[str, BatchGroupWidget] = {}  # batch_id -> widget
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar
        header = QHBoxLayout()
        header.setContentsMargins(0, 20, 0, 12)
        header.setSpacing(10)

        title = GradientLabel(t("history_title"), direction="vertical")
        title.setObjectName("page_title")
        header.addWidget(title)

        self._badge = QLabel(str(len(self._hm.records)))
        self._badge.setObjectName("history_badge")
        self._badge.setVisible(len(self._hm.records) > 0)
        header.addWidget(self._badge)

        header.addStretch()

        # Platform filter
        self._filter_combo = QComboBox()
        self._filter_combo.setObjectName("history_filter")
        self._filter_combo.setFixedWidth(120)
        self._filter_combo.addItem(t("history_filter_all"), "all")
        self._filter_combo.addItem("YouTube", "youtube")
        self._filter_combo.addItem("Instagram", "instagram")
        self._filter_combo.addItem("X (Twitter)", "x")
        self._filter_combo.addItem("Weibo", "weibo")
        self._filter_combo.addItem("Bilibili", "bilibili")
        self._filter_combo.addItem("Douyin", "douyin")
        self._filter_combo.addItem("Kuaishou", "kuaishou")
        self._filter_combo.addItem("Xiaohongshu", "xiaohongshu")
        self._filter_combo.currentIndexChanged.connect(self._apply_filter)
        header.addWidget(self._filter_combo)

        # Search box
        self._search = FocusLineEdit()
        self._search.setObjectName("history_search")
        self._search.setPlaceholderText(t("history_search"))
        self._search.setFixedWidth(200)
        self._search.setFixedHeight(30)
        self._search.textChanged.connect(self._apply_filter)
        header.addWidget(self._search)

        # Clear button
        self._clear_btn = QPushButton(t("history_clear"))
        self._clear_btn.setObjectName("task_btn_danger")
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setFixedHeight(30)
        self._clear_btn.clicked.connect(self._on_clear)
        header.addWidget(self._clear_btn)

        root.addLayout(header)

        # Scrollable list
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setObjectName("history_scroll")
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 8, 0, 16)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()

        self._scroll.setWidget(self._list_widget)
        root.addWidget(self._scroll, 1)

        # Empty state — 使用 EmptyState 组件替代裸 QLabel
        from .widgets import EmptyState
        self._empty_state = EmptyState(
            icon="i-history",
            title=t("history_empty"),
            hint="",
        )
        self._empty_state.setObjectName("history_empty_state")
        self._list_layout.insertWidget(0, self._empty_state)

        # Load existing records with batch grouping
        self._load_records()
        self._update_empty()

    def _load_records(self):
        """Group records by batch_id and build widgets."""
        batches: dict[str, list[HistoryRecord]] = {}
        singles: list[HistoryRecord] = []
        for rec in self._hm.records:
            if rec.batch_id:
                batches.setdefault(rec.batch_id, []).append(rec)
            else:
                singles.append(rec)

        # Render batches (sorted by latest download_time desc)
        for batch_id, items in sorted(
            batches.items(),
            key=lambda x: max((r.download_time for r in x[1]), default=""),
            reverse=True,
        ):
            self._add_batch_widget(items)

        # Render singles
        for rec in singles:
            self._add_record_widget(rec)

    def _add_batch_widget(self, records: list[HistoryRecord]):
        widget = BatchGroupWidget(records)
        widget.action_requested.connect(self._on_action)
        self._batch_widgets.append(widget)
        if records and records[0].batch_id:
            self._batch_widget_map[records[0].batch_id] = widget
        self._list_layout.insertWidget(self._list_layout.count() - 1, widget)

    def _add_record_widget(self, rec: HistoryRecord):
        widget = HistoryRecordWidget(rec)
        widget.action_requested.connect(self._on_action)
        self._record_widgets[rec.record_id] = widget
        self._list_layout.insertWidget(self._list_layout.count() - 1, widget)

    def _update_empty(self):
        has_records = len(self._record_widgets) > 0 or len(self._batch_widgets) > 0
        self._empty_state.setVisible(not has_records)
        visible_count = (
            sum(1 for w in self._record_widgets.values() if w.isVisible())
            + sum(1 for w in self._batch_widgets if w.isVisible())
        )
        self._badge.setText(str(visible_count))
        self._badge.setVisible(visible_count > 0)

    @Slot()
    def _apply_filter(self):
        search_text = self._search.text().lower().strip()
        platform_filter = self._filter_combo.currentData()

        # Filter individual record widgets
        for rid, widget in self._record_widgets.items():
            rec = next((r for r in self._hm.records if r.record_id == rid), None)
            if not rec:
                widget.setVisible(False)
                continue

            if platform_filter != "all" and rec.platform != platform_filter:
                widget.setVisible(False)
                continue

            if search_text:
                searchable = (
                    f"{rec.title} {rec.author} {rec.platform} "
                    f"{rec.url} {rec.file_path} {rec.download_time}"
                ).lower()
                widget.setVisible(search_text in searchable)
            else:
                widget.setVisible(True)

        # Filter batch widgets
        for bw in self._batch_widgets:
            bw.setVisible(bw.match_filter(search_text, platform_filter if platform_filter != "all" else ""))

        self._update_empty()

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
        for bw in self._batch_widgets:
            bw.deleteLater()
        self._batch_widgets.clear()
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
            # Check if the deleted record was part of a batch and clean up empty batches
            self._cleanup_empty_batches()
            self._update_empty()

    def _cleanup_empty_batches(self):
        """Remove batch widgets whose records have all been deleted."""
        to_remove = []
        for bw in self._batch_widgets:
            remaining = [r for r in bw._records if r.record_id in {rec.record_id for rec in self._hm.records}]
            if not remaining:
                to_remove.append(bw)
        for bw in to_remove:
            bw.deleteLater()
            self._batch_widgets.remove(bw)

    @Slot(HistoryRecord)
    def on_history_added(self, record: HistoryRecord):
        if record.batch_id:
            existing = self._batch_widget_map.get(record.batch_id)
            if existing:
                existing.add_record(record)
            else:
                self._add_batch_widget([record])
        else:
            self._add_record_widget(record)
        self._update_empty()
        self._apply_filter()
