"""通知页面 — 展示依赖/环境/版本更新通知，持久化存储。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..i18n import t
from ..notification_manager import Notification, NotificationManager

_TYPE_ICONS = {
    "warning": "⚠️",
    "info": "ℹ️",
    "update": "🆕",
    "tip": "💡",
}

_CATEGORY_LABELS = {}  # 延迟填充，依赖 i18n


def _get_category_label(cat: str) -> str:
    return t(f"notif_cat_{cat}") if cat != "update" else t("notif_cat_update")


class _NotifCard(QWidget):
    """单条通知卡片。"""

    action_clicked = Signal(str, str)
    dismiss_clicked = Signal(str)

    def __init__(self, notif: Notification, parent=None):
        super().__init__(parent)
        self._notif = notif
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # Icon
        icon = _TYPE_ICONS.get(self._notif.type, "ℹ️")
        icon_lbl = QLabel(icon)
        icon_lbl.setFixedWidth(28)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(icon_lbl)

        # Content
        content = QVBoxLayout()
        content.setSpacing(4)

        # Category tag + title
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        cat_label = QLabel(_get_category_label(self._notif.category))
        cat_label.setObjectName("notif_cat_tag")
        cat_label.setFixedHeight(18)
        title_row.addWidget(cat_label)

        title_lbl = QLabel(self._notif.title)
        title_lbl.setObjectName("card_title")
        title_lbl.setWordWrap(True)
        title_row.addWidget(title_lbl, 1)
        content.addLayout(title_row)

        # Message
        if self._notif.message:
            msg_lbl = QLabel(self._notif.message)
            msg_lbl.setObjectName("card_meta")
            msg_lbl.setWordWrap(True)
            content.addWidget(msg_lbl)

        # Action button
        if self._notif.action:
            btn_row = QHBoxLayout()
            btn_row.setSpacing(8)
            action_btn = QPushButton(self._notif.action_text or t("learn_more"))
            action_btn.setObjectName("secondary")
            action_btn.setFixedHeight(26)
            action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            action_btn.clicked.connect(
                lambda: self.action_clicked.emit(self._notif.id, self._notif.action))
            btn_row.addWidget(action_btn)
            btn_row.addStretch()
            content.addLayout(btn_row)

        layout.addLayout(content, 1)

        # Unread indicator — 用 lg_led 复用 QSS 规则
        if not self._notif.read:
            dot = QLabel()
            dot.setObjectName("lg_led")
            dot.setProperty("led", "blue")
            dot.setFixedWidth(12)
            dot.setAlignment(Qt.AlignmentFlag.AlignTop)
            layout.addWidget(dot)

        # Dismiss (永久通知不显示关闭按钮)
        if self._notif.dismissable:
            close_btn = QPushButton("✕")
            close_btn.setObjectName("card_close_btn")
            close_btn.setFixedSize(20, 20)
            close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            close_btn.clicked.connect(lambda: self.dismiss_clicked.emit(self._notif.id))
            layout.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignTop)


class NotificationPage(QWidget):
    """通知页面 — sidebar 独立页面。"""

    navigate_to = Signal(str)  # page_id，用于跳转设置等页面

    def __init__(self, manager: NotificationManager, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._cards: dict[str, _NotifCard] = {}
        self._build_ui()
        self._connect_signals()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # Header
        header = QHBoxLayout()
        title = QLabel(t("notifications"))
        title.setObjectName("page_title")
        header.addWidget(title)

        self._badge = QLabel("0")
        self._badge.setObjectName("history_badge")
        self._badge.setVisible(False)
        header.addWidget(self._badge)
        header.addStretch()
        root.addLayout(header)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._btn_mark_all = QPushButton(t("mark_all_read"))
        self._btn_mark_all.clicked.connect(self._manager.mark_all_read)
        toolbar.addWidget(self._btn_mark_all)

        self._btn_clear = QPushButton(t("notif_clear_read"))
        self._btn_clear.clicked.connect(self._manager.clear_read)
        toolbar.addWidget(self._btn_clear)

        toolbar.addStretch()

        # Category filter buttons
        for cat, label in [("all", t("notif_filter_all")),
                           ("deps", t("notif_cat_deps")),
                           ("env", t("notif_cat_env")),
                           ("update", t("notif_cat_update"))]:
            btn = QPushButton(label)
            btn.setObjectName("filter_btn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, c=cat: self._on_filter(c))
            toolbar.addWidget(btn)
            if cat == "all":
                btn.setChecked(True)
                self._filter_btns: dict[str, QPushButton] = {}
            self._filter_btns[cat] = btn

        root.addLayout(toolbar)

        # Scrollable list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("search_scroll")
        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_container)
        root.addWidget(scroll, 1)

        # Empty state — 使用 EmptyState 组件替代裸 QLabel
        from .widgets import EmptyState
        self._empty_state = EmptyState(
            icon="i-bell",
            title=t("no_notifications"),
            hint="",
        )
        self._empty_state.setObjectName("notif_empty_state")
        self._empty_state.hide()
        root.addWidget(self._empty_state)

        self._current_filter = "all"

    def _connect_signals(self):
        self._manager.notifications_changed.connect(self._on_changed)

    def refresh(self):
        self._rebuild_list()

    def _rebuild_list(self):
        # 清空
        for w in self._cards.values():
            w.setParent(None)
            w.deleteLater()
        self._cards.clear()

        category = self._current_filter if self._current_filter != "all" else None
        items = self._manager.get_all(category=category)
        self._empty_state.setVisible(len(items) == 0)

        for notif in items:
            card = _NotifCard(notif, self._list_container)
            card.action_clicked.connect(self._on_action)
            card.dismiss_clicked.connect(self._on_dismiss)
            self._list_layout.insertWidget(self._list_layout.count() - 1, card)
            self._cards[notif.id] = card

        unread = self._manager.unread_count()
        self._badge.setText(str(unread))
        self._badge.setVisible(unread > 0)

    def _on_filter(self, category: str):
        self._current_filter = category
        for cat, btn in self._filter_btns.items():
            btn.setChecked(cat == category)
        self._rebuild_list()

    @Slot(int)
    def _on_changed(self, count: int):
        self._badge.setText(str(count))
        self._badge.setVisible(count > 0)
        self._rebuild_list()

    @Slot(str, str)
    def _on_action(self, notif_id: str, action: str):
        self._manager.mark_read(notif_id)
        if action.startswith("open_page:"):
            page_id = action.split(":", 1)[1]
            self.navigate_to.emit(page_id)
        elif action.startswith("open_url:"):
            url = action.split(":", 1)[1]
            QDesktopServices.openUrl(QUrl(url))
            # 标记 tip 为已展示
            self._mark_tip_shown(notif_id)

    @Slot(str)
    def _on_dismiss(self, notif_id: str):
        self._manager.dismiss(notif_id)

    def _mark_tip_shown(self, notif_id: str):
        try:
            from ..utils.config import load_config, save_config
            cfg = load_config()
            shown = cfg.get("shown_tips", [])
            for n in self._manager.get_all():
                if n.id == notif_id and n.type == "tip":
                    if n.source_key and n.source_key not in shown:
                        shown.append(n.source_key)
                        cfg["shown_tips"] = shown
                        save_config(cfg)
        except Exception:
            pass
