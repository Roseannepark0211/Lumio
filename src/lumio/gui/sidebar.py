from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..i18n import t


class NavButton(QPushButton):
    def __init__(self, icon: str, label: str, page_id: str, parent=None):
        super().__init__(parent)
        self.page_id = page_id
        self.setText(f"  {icon}   {label}")
        self.setObjectName("nav_btn")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self.setFixedHeight(40)


class SidebarWidget(QFrame):
    navigation_changed = Signal(str)  # page_id
    theme_toggle_requested = Signal()
    collection_selected = Signal(int)  # collection_id
    collection_create_requested = Signal()

    NAV_ITEMS = [
        ("⌂", "home", "home"),
        ("↓", "downloads", "downloads"),
        ("🕘", "history", "history"),
        ("◻", "library", "library"),
        ("☰", "stats", "stats"),
        ("⚙", "settings", "settings"),
    ]

    PLACEHOLDER_ITEMS = [
        ("☐", "workspace", "workspace"),
    ]

    def __init__(self, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(200)
        self._theme = theme
        self._nav_buttons: dict[str, NavButton] = {}
        self._collection_buttons: dict[int, QPushButton] = {}
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 16, 8, 16)
        root.setSpacing(4)

        # Logo
        logo = QLabel("Lumio")
        logo.setObjectName("sidebar_logo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(logo)
        root.addSpacing(20)

        # Active nav items
        for icon, label_key, page_id in self.NAV_ITEMS:
            btn = NavButton(icon, t(label_key), page_id)
            btn.clicked.connect(lambda checked, pid=page_id: self._on_nav(pid))
            self._nav_buttons[page_id] = btn
            root.addWidget(btn)

            # Insert Collections section after Library
            if page_id == "library":
                self._collections_section = QWidget()
                cs_layout = QVBoxLayout(self._collections_section)
                cs_layout.setContentsMargins(8, 4, 4, 4)
                cs_layout.setSpacing(2)

                cs_header = QHBoxLayout()
                cs_header.setContentsMargins(0, 0, 0, 0)
                cs_label = QLabel(t("collections"))
                cs_label.setObjectName("sidebar_sep")
                cs_header.addWidget(cs_label)
                cs_header.addStretch()
                cs_add_btn = QPushButton("+")
                cs_add_btn.setObjectName("icon_add_btn")
                cs_add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                cs_add_btn.setFixedSize(22, 18)
                cs_add_btn.clicked.connect(self.collection_create_requested.emit)
                cs_header.addWidget(cs_add_btn)
                cs_layout.addLayout(cs_header)

                self._collections_list = QVBoxLayout()
                self._collections_list.setSpacing(2)
                cs_layout.addLayout(self._collections_list)

                root.addWidget(self._collections_section)

        root.addSpacing(16)

        # Separator label
        sep = QLabel(t("nav_coming_soon"))
        sep.setObjectName("sidebar_sep")
        sep.setAlignment(Qt.AlignmentFlag.AlignLeft)
        root.addWidget(sep)

        # Placeholder nav items (disabled)
        for icon, label_key, page_id in self.PLACEHOLDER_ITEMS:
            btn = NavButton(icon, t(label_key), page_id)
            btn.setEnabled(False)
            btn.setObjectName("nav_btn_disabled")
            self._nav_buttons[page_id] = btn
            root.addWidget(btn)

        root.addStretch()

        # Theme toggle button
        self._theme_btn = QPushButton()
        self._theme_btn.setObjectName("nav_btn")
        self._theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_btn.setFixedHeight(36)
        self._update_theme_btn_text()
        self._theme_btn.clicked.connect(self.theme_toggle_requested.emit)
        root.addWidget(self._theme_btn)

        # Version label
        from .. import __version__
        ver = QLabel(f"v{__version__}")
        ver.setObjectName("sidebar_version")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(ver)

        # Select first item
        self._nav_buttons["home"].setChecked(True)

    def _on_nav(self, page_id: str):
        for pid, btn in self._nav_buttons.items():
            btn.setChecked(pid == page_id)
        # Uncheck collection buttons
        for btn in self._collection_buttons.values():
            btn.setChecked(False)
        self.navigation_changed.emit(page_id)

    def set_active(self, page_id: str):
        for pid, btn in self._nav_buttons.items():
            btn.setChecked(pid == page_id)

    def add_collection_nav(self, collection_id: int, name: str, icon: str = "📁"):
        if collection_id in self._collection_buttons:
            return
        btn = QPushButton(f"  {icon}   {name}")
        btn.setObjectName("nav_btn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setCheckable(True)
        btn.setFixedHeight(32)
        btn.clicked.connect(lambda checked, cid=collection_id: self._on_collection_nav(cid))
        self._collection_buttons[collection_id] = btn
        self._collections_list.addWidget(btn)

    def remove_collection_nav(self, collection_id: int):
        btn = self._collection_buttons.pop(collection_id, None)
        if btn:
            btn.deleteLater()

    def _on_collection_nav(self, collection_id: int):
        # Check library nav, uncheck others
        for pid, btn in self._nav_buttons.items():
            btn.setChecked(pid == "library")
        for cid, btn in self._collection_buttons.items():
            btn.setChecked(cid == collection_id)
        self.collection_selected.emit(collection_id)

    def _update_theme_btn_text(self):
        if self._theme == "dark":
            self._theme_btn.setText(f"  ☀   {t('theme_light')}")
        else:
            self._theme_btn.setText(f"  ☾   {t('theme_dark')}")

    def update_theme(self, theme: str):
        self._theme = theme
        self._update_theme_btn_text()
