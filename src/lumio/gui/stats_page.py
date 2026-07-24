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
from ..utils.media_utils import format_size
from .theme.paint import GradientLabel


def _stat_card(label: str, value: str, color: str = "#7c8fff") -> QWidget:
    """创建统计卡片。

    Args:
        label: 标签文字（如 "总下载数"）
        value: 显示值（如 "123"）
        color: 强调色，建议从 tokens 取（如 tokens.STATUS_SUCCESS / tokens.platform_color('youtube')）
    """
    card = QWidget()
    card.setObjectName("stat_card")
    card.setFixedHeight(100)
    card.setMinimumWidth(160)

    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 16, 20, 16)
    layout.setSpacing(6)

    val = QLabel(value)
    val.setObjectName("stat_value")
    # 色值来自 tokens（platform_color / STATUS_*），每张卡片不同，只能内联
    # font-size / font-weight / background 由 QSS 统一控制
    val.setStyleSheet(f"QLabel#stat_value {{ color: {color}; }}")
    val.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(val)

    lbl = QLabel(label)
    lbl.setObjectName("stat_label")
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(lbl)

    return card


def _format_total_size(size_bytes: int) -> str:
    return format_size(size_bytes, zero_default="0 B")


class StatsPage(QWidget):
    def __init__(self, history_manager: HistoryManager, parent=None):
        super().__init__(parent)
        self.setObjectName("stats_page")
        self._hm = history_manager
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(24)

        # Title
        title = GradientLabel(t("stats_title"), direction="vertical")
        title.setObjectName("page_title")
        root.addWidget(title)

        records = self._hm.records
        total = len(records)
        yt_count = sum(1 for r in records if r.platform == "youtube")
        ig_count = sum(1 for r in records if r.platform == "instagram")
        x_count = sum(1 for r in records if r.platform == "x")
        weibo_count = sum(1 for r in records if r.platform == "weibo")
        total_size = sum(r.file_size for r in records)
        success_count = sum(1 for r in records if getattr(r, "success", True))
        success_rate = f"{success_count / total * 100:.1f}%" if total > 0 else "—"
        today = datetime.now().strftime("%Y-%m-%d")
        today_count = sum(1 for r in records if r.download_time.startswith(today))

        # Row 1: key metrics (4 cards)
        # 颜色全部来自 tokens，根治原项目硬编码色值
        from .theme import tokens as T
        row1 = QHBoxLayout()
        row1.setSpacing(16)
        self._total_card = _stat_card(t("stats_total"), str(total), T.get_tokens("dark")["accent_2"])
        self._size_card = _stat_card(t("stats_size"), _format_total_size(total_size), T.STATUS_SUCCESS)
        self._success_card = _stat_card(t("stats_success_rate"), success_rate, T.STATUS_WARNING)
        self._today_card = _stat_card(t("stats_today"), str(today_count), T.STATUS_SUCCESS)
        for card in (self._total_card, self._size_card, self._success_card, self._today_card):
            row1.addWidget(card)
        root.addLayout(row1)

        # Row 2: platform breakdown (4 cards)
        # 平台色单一来源：tokens.PLATFORM_COLORS（根治 YouTube #2563eb 旧蓝）
        row2 = QHBoxLayout()
        row2.setSpacing(16)
        self._yt_card = _stat_card("YouTube", str(yt_count), T.platform_color("youtube"))
        self._ig_card = _stat_card("Instagram", str(ig_count), T.platform_color("instagram"))
        self._x_card = _stat_card("X (Twitter)", str(x_count), T.platform_color("x"))
        self._weibo_card = _stat_card("Weibo", str(weibo_count), T.platform_color("weibo"))
        for card in (self._yt_card, self._ig_card, self._x_card, self._weibo_card):
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
        weibo_count = sum(1 for r in records if r.platform == "weibo")
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
            (self._weibo_card, str(weibo_count)),
        ]:
            layout = card.layout()
            if layout and layout.count() > 0:
                label = layout.itemAt(0).widget()
                if isinstance(label, QLabel):
                    label.setText(val)
