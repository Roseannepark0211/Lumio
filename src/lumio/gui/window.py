from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QWidget,
)

from ..history_manager import HistoryManager
from ..i18n import t
from ..library_manager import LibraryManager
from ..queue_manager import DownloadManager
from ..utils.config import load_config, save_config
from .cookie_checker import CookieCheckWorker
from .downloads_page import DownloadsPage
from .history_page import HistoryPage
from .home_page import HomePage
from .library_page import LibraryPage
from .settings_page import SettingsPage
from .sidebar import SidebarWidget
from .stats_page import StatsPage
from .styles import get_stylesheet

_ASSETS = Path(__file__).parent.parent / "assets"


class MainWindow(QMainWindow):
    def __init__(self, manager: DownloadManager):
        super().__init__()
        self.setWindowTitle(t("app_title"))
        self.setMinimumSize(960, 640)
        self.resize(1020, 700)

        cfg = load_config()
        self._theme = cfg.get("theme", "dark")
        self.setStyleSheet(get_stylesheet(self._theme))

        from PySide6.QtGui import QIcon
        logo = _ASSETS / "logo.png"
        if logo.exists():
            self.setWindowIcon(QIcon(str(logo)))

        self._manager = manager
        self._history_manager = HistoryManager()
        self._manager.set_history_manager(self._history_manager)
        self._library_manager = LibraryManager()
        self._manager.set_library_manager(self._library_manager)

        self._build_ui()
        self._connect_signals()
        self._check_cookie_status()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Sidebar ----
        self._sidebar = SidebarWidget(theme=self._theme)
        root.addWidget(self._sidebar)

        # ---- Separator ----
        sep = QFrame()
        sep.setObjectName("sidebar_sep_line")
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setFixedWidth(1)
        root.addWidget(sep)

        # ---- Content Area ----
        self._stack = QStackedWidget()
        self._stack.setObjectName("content_area")

        # Create pages
        self._home_page = HomePage(self._manager)
        self._downloads_page = DownloadsPage(self._manager)
        self._history_page = HistoryPage(self._history_manager)
        self._stats_page = StatsPage(self._history_manager)
        self._settings_page = SettingsPage()
        self._library_page = LibraryPage(self._library_manager)

        self._stack.addWidget(self._home_page)      # index 0
        self._stack.addWidget(self._downloads_page)  # index 1
        self._stack.addWidget(self._history_page)    # index 2
        self._stack.addWidget(self._library_page)    # index 3
        self._stack.addWidget(self._stats_page)      # index 4
        self._stack.addWidget(self._settings_page)   # index 5

        root.addWidget(self._stack, 1)

    def _connect_signals(self):
        # Sidebar navigation
        self._sidebar.navigation_changed.connect(self._on_nav)

        # Sidebar theme toggle
        self._sidebar.theme_toggle_requested.connect(self._on_theme_toggle)

        # Home page -> batch dialogs
        self._home_page.request_batch_dialog.connect(self._on_batch_dialog)

        # History: new record added -> update history page + stats
        self._manager.history_record_added.connect(self._history_page.on_history_added)

        # Library: new item added -> update library page
        self._manager.library_record_added.connect(self._library_page.on_item_added)

        # Collections: sidebar selection + creation
        self._sidebar.collection_selected.connect(self._on_collection_selected)
        self._sidebar.collection_create_requested.connect(self._on_create_collection)

        # Settings: restart
        self._settings_page.restart_requested.connect(self._restart_app)

        # Load existing collections into sidebar
        self._refresh_sidebar_collections()

    def _on_nav(self, page_id: str):
        page_map = {
            "home": 0,
            "downloads": 1,
            "history": 2,
            "library": 3,
            "stats": 4,
            "settings": 5,
        }
        idx = page_map.get(page_id, 0)
        self._stack.setCurrentIndex(idx)
        # Refresh stats when switching to stats page
        if page_id == "stats":
            self._stats_page.refresh()
        # Clear collection filter when switching to library via nav
        if page_id == "library":
            self._library_page.set_collection_filter(None)

    def _on_collection_selected(self, collection_id: int):
        self._stack.setCurrentIndex(3)  # Library page
        self._library_page.set_collection_filter(collection_id)

    def _on_create_collection(self):
        from PySide6.QtWidgets import QInputDialog
        from ..i18n import t
        name, ok = QInputDialog.getText(self, t("collection_create"), t("collection_name_label"))
        if ok and name.strip():
            self._library_manager.create_collection(name.strip())
            self._refresh_sidebar_collections()

    def _refresh_sidebar_collections(self):
        for col in self._library_manager.get_all_collections():
            self._sidebar.add_collection_nav(col.id, col.name, col.icon)

    def _on_theme_toggle(self):
        self._theme = "light" if self._theme == "dark" else "dark"
        self.setStyleSheet(get_stylesheet(self._theme))
        # Force all child widgets to re-apply the new stylesheet
        self.style().unpolish(self)
        self.style().polish(self)
        self._stack.style().unpolish(self._stack)
        self._stack.style().polish(self._stack)
        for i in range(self._stack.count()):
            page = self._stack.widget(i)
            page.style().unpolish(page)
            page.style().polish(page)
            for child in page.findChildren(QWidget):
                child.style().unpolish(child)
                child.style().polish(child)
        self._sidebar.update_theme(self._theme)
        cfg = load_config()
        cfg["theme"] = self._theme
        save_config(cfg)

    # ---- Cookie status ----

    def _check_cookie_status(self):
        self._cookie_worker = CookieCheckWorker()
        self._cookie_worker.result.connect(self._on_cookie_result)
        self._cookie_worker.start()

    @Slot(str)
    def _on_cookie_result(self, status: str):
        self._settings_page.refresh_cookie_status()

    # ---- Batch dialogs ----

    @Slot(str, str, str)
    def _on_batch_dialog(self, dialog_type: str, arg: str, tab: str):
        if dialog_type == "instagram":
            self._open_profile_dialog(arg)
        elif dialog_type == "youtube":
            self._open_yt_dialog(arg, tab=tab)

    def _open_profile_dialog(self, username: str):
        from .profile_dialog import ProfileDialog
        dlg = ProfileDialog(username, self)
        dlg.batch_add_requested.connect(self._on_profile_batch_add)
        dlg.exec()

    @Slot(object)
    def _on_profile_batch_add(self, tasks):
        for qt in tasks:
            self._manager.add_task(qt)
        self._show_toast(t("batch_added", n=len(tasks)))
        self._sidebar.set_active("downloads")
        self._stack.setCurrentIndex(1)

    def _open_yt_dialog(self, url: str, tab: str = ""):
        from .yt_dialog import YouTubeDialog
        dlg = YouTubeDialog(url, tab=tab, parent=self)
        dlg.batch_add_requested.connect(self._on_yt_batch_add)
        dlg.exec()

    @Slot(object)
    def _on_yt_batch_add(self, tasks):
        for qt in tasks:
            self._manager.add_task(qt)
        self._show_toast(t("batch_added", n=len(tasks)))
        self._sidebar.set_active("downloads")
        self._stack.setCurrentIndex(1)

    # ---- Restart ----

    @Slot()
    def _restart_app(self):
        program = sys.executable
        args = ["-m", "lumio.main"]
        import os
        QProcess.startDetached(program, args, os.getcwd())
        QApplication.instance().quit()

    # ---- Toast ----

    def _show_toast(self, msg: str):
        toast = QLabel(msg, self)
        toast.setObjectName("toast")
        toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toast.setFixedHeight(36)
        toast.setMinimumWidth(200)
        toast.adjustSize()
        toast.move(
            (self.width() - toast.width()) // 2,
            self.height() - 100,
        )
        toast.show()
        QTimer.singleShot(2000, toast.deleteLater)
