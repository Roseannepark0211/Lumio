from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStackedWidget,
    QSystemTrayIcon,
    QWidget,
)

from ..history_manager import HistoryManager
from ..i18n import t
from ..library_manager import LibraryManager
from ..notification_manager import NotificationManager
from ..queue_manager import DownloadManager
from ..utils.config import load_config, save_config
from .cookie_checker import CookieCheckWorker
from .downloads_page import DownloadsPage
from .history_page import HistoryPage
from .home_page import HomePage
from .inbox_page import InboxPage
from .library_page import LibraryPage
from .settings_page import SettingsPage
from .sidebar import SidebarWidget
from .stats_page import StatsPage
from .styles import get_stylesheet

_ASSETS = Path(__file__).parent.parent / "assets"


class MainWindow(QMainWindow):
    def __init__(self, manager: DownloadManager, *, inbox_manager=None):
        super().__init__()
        self.setWindowTitle(t("app_title"))
        self.setMinimumSize(960, 640)
        self.resize(1020, 700)

        cfg = load_config()
        self._theme = cfg.get("theme", "dark")
        self.setStyleSheet(get_stylesheet(self._theme))

        logo = _ASSETS / "logo.png"
        if logo.exists():
            self.setWindowIcon(QIcon(str(logo)))

        self._manager = manager
        self._inbox_manager = inbox_manager
        self._closing = False
        self._history_manager = HistoryManager()
        self._manager.set_history_manager(self._history_manager)
        self._library_manager = LibraryManager()
        self._manager.set_library_manager(self._library_manager)

        # Notification system (before _build_ui, used by NotificationPage)
        self._notif_manager = NotificationManager(self)

        self._build_ui()
        self._connect_signals()
        self._check_cookie_status()

        self._notif_manager.notifications_changed.connect(self._sidebar.update_notification_badge)
        self._notif_manager.check_all()

        # System tray
        self._setup_tray()

        # Generate thumbnails for items missing them
        self._library_manager.backfill_thumbnails()

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
        self._inbox_page = InboxPage(self._inbox_manager, self._manager) if self._inbox_manager else None
        self._downloads_page = DownloadsPage(self._manager)
        self._history_page = HistoryPage(self._history_manager)
        self._stats_page = StatsPage(self._history_manager)
        from .notification_page import NotificationPage
        self._notif_page = NotificationPage(self._notif_manager)
        self._settings_page = SettingsPage()
        self._library_page = LibraryPage(self._library_manager)

        self._stack.addWidget(self._home_page)      # index 0
        if self._inbox_page:
            self._stack.addWidget(self._inbox_page)  # index 1
        self._stack.addWidget(self._downloads_page)  # index 1 or 2
        self._stack.addWidget(self._history_page)    # index 2 or 3
        self._stack.addWidget(self._library_page)    # index 3 or 4
        self._stack.addWidget(self._stats_page)      # index 4 or 5
        self._stack.addWidget(self._notif_page)      # index 5 or 6
        self._stack.addWidget(self._settings_page)   # index 6 or 7

        root.addWidget(self._stack, 1)

    def _connect_signals(self):
        # Sidebar navigation
        self._sidebar.navigation_changed.connect(self._on_nav)

        # Sidebar theme toggle
        self._sidebar.theme_toggle_requested.connect(self._on_theme_toggle)

        # Notification page navigation
        self._notif_page.navigate_to.connect(self._on_nav)

        # Home page -> batch dialogs
        self._home_page.request_batch_dialog.connect(self._on_batch_dialog)
        self._home_page.search_batch_added.connect(self._on_search_batch_added)

        # History: new record added -> update history page + stats
        self._manager.history_record_added.connect(self._history_page.on_history_added)
        self._manager.history_record_added.connect(lambda _: self._stats_page.refresh())

        # Library: new item added -> update library page
        self._manager.library_record_added.connect(self._library_page.on_item_added)

        # Conflict ask dialog
        self._manager.conflict_ask.connect(self._on_conflict_ask)

        # Collections: sidebar selection + creation + rename/delete + stats refresh
        self._sidebar.collection_selected.connect(self._on_collection_selected)
        self._sidebar.collection_create_requested.connect(self._on_create_collection)
        self._sidebar.collection_rename_requested.connect(self._on_rename_collection)
        self._sidebar.collection_delete_requested.connect(self._on_delete_collection)
        self._library_manager.collection_changed.connect(self._refresh_sidebar_collections)

        # Settings: restart + save toast
        self._settings_page.restart_requested.connect(self._restart_app)
        self._settings_page.saved.connect(lambda: self._show_toast(t("settings_saved")))

        # Auto download: inbox item_added → auto queue + start
        if self._inbox_manager and load_config().get("auto_download_inbox"):
            self._inbox_manager.item_added.connect(self._on_inbox_auto_download)

        # Load existing collections into sidebar
        self._refresh_sidebar_collections()

    def _on_nav(self, page_id: str):
        idx = self._page_index(page_id)
        self._stack.setCurrentIndex(idx)
        # Refresh stats when switching to stats page
        if page_id == "stats":
            self._stats_page.refresh()
        # Clear collection filter when switching to library via nav
        if page_id == "library":
            self._library_page.set_collection_filter(None)

    def _on_collection_selected(self, collection_id: int):
        self._stack.setCurrentIndex(self._page_index("library"))
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
            count, total_size = self._library_manager.get_collection_stats(col.id)
            self._sidebar.add_collection_nav(col.id, col.name, col.icon, count, total_size)

    def _on_rename_collection(self, collection_id: int):
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        from ..i18n import t
        cols = [c for c in self._library_manager.get_all_collections() if c.id == collection_id]
        if not cols:
            return
        new_name, ok = QInputDialog.getText(self, t("collection_rename"), t("collection_name_label"), text=cols[0].name)
        if ok and new_name.strip():
            self._library_manager.rename_collection(collection_id, new_name.strip())
            self._refresh_sidebar_collections()

    def _on_delete_collection(self, collection_id: int):
        from PySide6.QtWidgets import QMessageBox
        from ..i18n import t
        cols = [c for c in self._library_manager.get_all_collections() if c.id == collection_id]
        if not cols:
            return
        reply = QMessageBox.question(
            self, t("collection_delete"), f"{t('collection_delete')} \"{cols[0].name}\"?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._library_manager.delete_collection(collection_id)
            self._sidebar.remove_collection_nav(collection_id)
            self._library_page.set_collection_filter(None)

    def _on_conflict_ask(self, file_path: str):
        from PySide6.QtWidgets import QMessageBox
        from ..i18n import t
        name = Path(file_path).name
        msg = t("conflict_ask_msg", name=name)
        box = QMessageBox(self)
        box.setWindowTitle(t("file_conflict_policy"))
        box.setText(msg)
        box.addButton(t("conflict_rename"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(t("conflict_skip"), QMessageBox.ButtonRole.RejectRole)
        box.addButton(t("conflict_overwrite"), QMessageBox.ButtonRole.DestructiveRole)
        box.exec()
        role = box.buttonRole(box.clickedButton())
        if role == QMessageBox.ButtonRole.AcceptRole:
            choice = "rename"
        elif role == QMessageBox.ButtonRole.RejectRole:
            choice = "skip"
        else:
            choice = "overwrite"
        self._manager.resolve_conflict(choice)

    def _page_index(self, page_id: str) -> int:
        """动态计算页面索引（Inbox 可选插入）。"""
        base = {
            "home": 0, "downloads": 1, "history": 2, "library": 3,
            "stats": 4, "notifications": 5, "settings": 6,
        }
        idx = base.get(page_id, 0)
        if self._inbox_page and page_id != "home":
            idx += 1
        return idx

    @Slot(str)
    def _on_inbox_auto_download(self, item_id: str):
        """自动下载采集内容（auto_download_inbox 开启时）。"""
        if not self._inbox_manager or not self._inbox_page:
            return
        item = self._inbox_manager.get_item(item_id)
        if not item or item.status != "new":
            return
        from ..queue_manager import QueueTask
        from ..utils.config import get_download_dir
        custom = item.title if not item.author else ""
        if not custom and not item.author:
            custom = "download"
        qt = QueueTask(
            url=item.url,
            title=item.title,
            author=item.author,
            platform=item.platform or "auto",
            output_dir=str(get_download_dir()),
            thumbnail_url=item.thumbnail_url or "",
            custom_name=custom,
        )
        self._manager.add_task(qt)
        # 将 task_id → inbox_id 映射写入 inbox_page，由其 task_finished 统一处理
        self._inbox_page._task_to_inbox[qt.task_id] = item_id
        self._manager.start_task(qt.task_id)
        self._inbox_manager.mark_status(item_id, "queued")

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
        elif dialog_type == "x":
           self._open_x_dialog(arg)
        elif dialog_type in ("weibo", "xiaohongshu", "bilibili", "douyin", "kuaishou"):
            self._open_domestic_dialog(arg, dialog_type)

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
        self._stack.setCurrentIndex(self._page_index("downloads"))

    @Slot(int)
    def _on_search_batch_added(self, count: int):
        self._show_toast(t("batch_added", n=count))
        self._sidebar.set_active("downloads")
        self._stack.setCurrentIndex(self._page_index("downloads"))

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
        self._stack.setCurrentIndex(self._page_index("downloads"))

    def _open_x_dialog(self, username: str):
        from .x_dialog import XTimelineDialog
        dlg = XTimelineDialog(username, self)
        dlg.batch_add_requested.connect(self._on_x_batch_add)
        dlg.exec()

    @Slot(object)
    def _on_x_batch_add(self, tasks):
        for qt in tasks:
            self._manager.add_task(qt)
        self._show_toast(t("batch_added", n=len(tasks)))
        self._sidebar.set_active("downloads")
        self._stack.setCurrentIndex(self._page_index("downloads"))


    def _open_domestic_dialog(self, identifier: str, platform_value: str):
        from .domestic_dialog import DomesticBatchDialog
        dlg = DomesticBatchDialog(platform_value, identifier, self)
        dlg.batch_add_requested.connect(self._on_domestic_batch_add)
        dlg.exec()

    @Slot(object)
    def _on_domestic_batch_add(self, tasks):
        for qt in tasks:
            self._manager.add_task(qt)
        self._show_toast(t("batch_added", n=len(tasks)))
        self._sidebar.set_active("downloads")
        self._stack.setCurrentIndex(self._page_index("downloads"))
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

    # ---- System Tray ----

    def _setup_tray(self):
        logo = _ASSETS / "logo.png"
        icon = QIcon(str(logo)) if logo.exists() else QIcon()

        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip("Lumio")

        menu = QMenu()
        show_action = QAction(t("tray_show"), self)
        show_action.triggered.connect(self._tray_show)
        quit_action = QAction(t("tray_quit"), self)
        quit_action.triggered.connect(self._tray_quit)
        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._tray_show()

    def _tray_show(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _tray_quit(self):
        self._closing = True
        self._tray.hide()
        QApplication.instance().quit()

    def closeEvent(self, event):
        if self._closing:
            event.accept()
            return

        box = QMessageBox(self)
        box.setWindowTitle(t("app_title"))
        box.setText(t("close_confirm"))
        box.setIcon(QMessageBox.Icon.Question)
        tray_btn = box.addButton(t("minimize_to_tray"), QMessageBox.ButtonRole.AcceptRole)
        quit_btn = box.addButton(t("quit_app"), QMessageBox.ButtonRole.RejectRole)
        cancel_btn = box.addButton(t("cancel"), QMessageBox.ButtonRole.RejectRole)
        box.exec()

        if box.clickedButton() == tray_btn:
            event.ignore()
            self.hide()
            self._tray.showMessage(
                "Lumio", t("tray_hint"),
                QSystemTrayIcon.MessageIcon.Information, 2000,
            )
        elif box.clickedButton() == quit_btn:
            self._closing = True
            self._tray.hide()
            event.accept()
            QTimer.singleShot(0, QApplication.instance().quit)
        else:
            event.ignore()
