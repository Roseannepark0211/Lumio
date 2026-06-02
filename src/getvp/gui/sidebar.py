from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

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

    NAV_ITEMS = [
        ("⌂", "home", "home"),
        ("↓", "downloads", "downloads"),
        ("🕘", "history", "history"),
        ("☰", "stats", "stats"),
        ("⚙", "settings", "settings"),
    ]

    PLACEHOLDER_ITEMS = [
        ("☐", "library", "library"),
        ("☐", "workspace", "workspace"),
    ]

    def __init__(self, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(200)
        self._theme = theme
        self._nav_buttons: dict[str, NavButton] = {}
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
        ver = QLabel("v1.5")
        ver.setObjectName("sidebar_version")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(ver)

        # Select first item
        self._nav_buttons["home"].setChecked(True)

    def _on_nav(self, page_id: str):
        for pid, btn in self._nav_buttons.items():
            btn.setChecked(pid == page_id)
        self.navigation_changed.emit(page_id)

    def set_active(self, page_id: str):
        for pid, btn in self._nav_buttons.items():
            btn.setChecked(pid == page_id)

    def _update_theme_btn_text(self):
        if self._theme == "dark":
            self._theme_btn.setText(f"  ☀   {t('theme_light')}")
        else:
            self._theme_btn.setText(f"  ☾   {t('theme_dark')}")

    def update_theme(self, theme: str):
        self._theme = theme
        self._update_theme_btn_text()
