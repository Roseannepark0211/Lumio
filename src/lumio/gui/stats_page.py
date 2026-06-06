from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ..history_manager import HistoryManager
from ..i18n import t


def _stat_card(label: str, value: str, color: str = "#7c8fff") -> QWidget:
    card = QWidget()
    card.setObjectName("stat_card")
    card.setFixedHeight(100)
    card.setMinimumWidth(160)

    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 16, 20, 16)
    layout.setSpacing(6)

    val = QLabel(value)
    val.setObjectName("stat_value")
    val.setStyleSheet(f"color: {color}; font-size: 28px; font-weight: 700;")
    val.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(val)

    lbl = QLabel(label)
    lbl.setObjectName("stat_label")
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(lbl)

    return card


def _format_total_size(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "0 B"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


class StatsPage(QWidget):
    def __init__(self, history_manager: HistoryManager, parent=None):
        super().__init__(parent)
        self.setObjectName("stats_page")
        self._hm = history_manager
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(24)

        # Title
        title = QLabel(t("stats_title"))
        title.setObjectName("page_title")
        root.addWidget(title)

        records = self._hm.records
        total = len(records)
        yt_count = sum(1 for r in records if r.platform == "youtube")
        ig_count = sum(1 for r in records if r.platform == "instagram")
        x_count = sum(1 for r in records if r.platform == "x")
        total_size = sum(r.file_size for r in records)
        success_count = sum(1 for r in records if getattr(r, "success", True))
        success_rate = f"{success_count / total * 100:.1f}%" if total > 0 else "—"
        today = datetime.now().strftime("%Y-%m-%d")
        today_count = sum(1 for r in records if r.download_time.startswith(today))

        # Row 1: key metrics (4 cards)
        row1 = QHBoxLayout()
        row1.setSpacing(16)
        self._total_card = _stat_card(t("stats_total"), str(total), "#7c8fff")
        self._size_card = _stat_card(t("stats_size"), _format_total_size(total_size), "#10b981")
        self._success_card = _stat_card(t("stats_success_rate"), success_rate, "#f59e0b")
        self._today_card = _stat_card(t("stats_today"), str(today_count), "#10b981")
        for card in (self._total_card, self._size_card, self._success_card, self._today_card):
            row1.addWidget(card)
        root.addLayout(row1)

        # Row 2: platform breakdown (3 cards)
        row2 = QHBoxLayout()
        row2.setSpacing(16)
        self._yt_card = _stat_card("YouTube", str(yt_count), "#2563eb")
        self._ig_card = _stat_card("Instagram", str(ig_count), "#e1306c")
        self._x_card = _stat_card("X (Twitter)", str(x_count), "#1d9bf0")
        for card in (self._yt_card, self._ig_card, self._x_card):
            row2.addWidget(card)
        row2.addStretch()
        root.addLayout(row2)

        root.addStretch()

    def refresh(self):
        records = self._hm.records
        total = len(records)
        yt_count = sum(1 for r in records if r.platform == "youtube")
        ig_count = sum(1 for r in records if r.platform == "instagram")
        x_count = sum(1 for r in records if r.platform == "x")
        total_size = sum(r.file_size for r in records)
        success_count = sum(1 for r in records if getattr(r, "success", True))
        success_rate = f"{success_count / total * 100:.1f}%" if total > 0 else "—"
        today = datetime.now().strftime("%Y-%m-%d")
        today_count = sum(1 for r in records if r.download_time.startswith(today))

        for card, val in [
            (self._total_card, str(total)),
            (self._size_card, _format_total_size(total_size)),
            (self._success_card, success_rate),
            (self._today_card, str(today_count)),
            (self._yt_card, str(yt_count)),
            (self._ig_card, str(ig_count)),
            (self._x_card, str(x_count)),
        ]:
            layout = card.layout()
            if layout and layout.count() > 0:
                label = layout.itemAt(0).widget()
                if isinstance(label, QLabel):
                    label.setText(val)
