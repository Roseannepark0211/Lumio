"""Lumio Python-QML 桥接层

将 Python 后端逻辑（DownloadManager 等）暴露给 QML UI。
通过 setContextProperty 注册到 QML 上下文。
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot, Property


class QmlController(QObject):
    """QML 中央控制器，暴露所有后端功能给 QML。

    在 main.py 中通过 engine.rootContext().setContextProperty("controller", ctrl) 注册。
    QML 中通过 controller.xxx 访问。
    """

    # 信号
    themeChanged = Signal(str)
    queueChanged = Signal()
    historyChanged = Signal()
    libraryChanged = Signal()
    notificationsChanged = Signal()
    inboxChanged = Signal()
    toastRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        from ..utils.config import load_config
        self._config = load_config()
        self._theme = self._config.get("theme", "dark")
        self._manager = None
        self._history_manager = None
        self._library_manager = None
        self._notif_manager = None
        self._inbox_manager = None
        self._current_page = "home"

    def set_managers(self, download_manager=None, history_manager=None,
                     library_manager=None, notification_manager=None,
                     inbox_manager=None):
        """注入后端管理器实例。"""
        self._manager = download_manager
        self._history_manager = history_manager
        self._library_manager = library_manager
        self._notif_manager = notification_manager
        self._inbox_manager = inbox_manager

        # 连接信号
        if self._manager:
            self._manager.queue_changed.connect(self.queueChanged.emit)
        if self._notif_manager:
            # notifications_changed 携带 unread count(int)，转发时丢弃参数
            self._notif_manager.notifications_changed.connect(
                lambda *_: self.notificationsChanged.emit()
            )

    # ---- helpers ----
    @staticmethod
    def _to_dict(obj) -> dict:
        """将 dataclass / SQLAlchemy ORM 实例转为供 QML 使用的纯字典。

        过滤掉以 ``_`` 开头的属性（如 SQLAlchemy 的 ``_sa_instance_state``）。
        """
        d = getattr(obj, "__dict__", None)
        if d is None:
            try:
                return dict(obj)
            except Exception:
                return {}
        return {k: v for k, v in d.items() if not k.startswith("_")}

    # ---- Theme ----
    @Property(str, notify=themeChanged)
    def theme(self):
        return self._theme

    @Slot(str)
    def setTheme(self, theme: str):
        if theme != self._theme:
            self._theme = theme
            self._config["theme"] = theme
            from ..utils.config import save_config
            save_config(self._config)
            self.themeChanged.emit(theme)

    @Slot()
    def toggleTheme(self):
        self.setTheme("light" if self._theme == "dark" else "dark")

    # ---- Navigation ----
    @Property(str)
    def currentPage(self):
        return self._current_page

    @Slot(str)
    def navigateTo(self, page_id: str):
        self._current_page = page_id
        # 这里会触发 QML 的页面切换

    # ---- Queue (Downloads) ----
    @Slot(result=list)
    def queueItems(self):
        """返回当前下载队列的任务列表（供 QML ListView 使用）。"""
        if not self._manager:
            return []
        items = []
        for task in self._manager.get_all_tasks():
            items.append({
                "task_id": task.task_id,
                "url": task.url,
                "title": task.title or "",
                "author": task.author or "",
                "platform": task.platform or "auto",
                "status": task.status,
                "progress": task.progress,
                "thumbnail_url": getattr(task, "thumbnail_url", "") or "",
            })
        return items

    @Slot(str)
    def startDownload(self, task_id: str):
        if self._manager:
            self._manager.start_task(task_id)

    @Slot(str)
    def pauseDownload(self, task_id: str):
        if self._manager:
            self._manager.pause_task(task_id)

    @Slot(str)
    def cancelDownload(self, task_id: str):
        if self._manager:
            self._manager.cancel_task(task_id)

    @Slot(str)
    def removeDownload(self, task_id: str):
        if self._manager:
            self._manager.delete_task(task_id)

    @Slot(str)
    def retryDownload(self, task_id: str):
        if self._manager:
            self._manager.retry_task(task_id)

    # ---- History ----
    @Slot(result=list)
    def historyItems(self):
        if not self._history_manager:
            return []
        return [self._to_dict(item) for item in self._history_manager.records]

    # ---- Library ----
    @Slot(result=list)
    def libraryItems(self):
        if not self._library_manager:
            return []
        return [self._to_dict(item) for item in self._library_manager.get_all_items()]

    @Slot(result=list)
    def collections(self):
        if not self._library_manager:
            return []
        return [{"id": c.id, "name": c.name, "icon": c.icon}
                for c in self._library_manager.get_all_collections()]

    # ---- Notifications ----
    @Property(int, notify=notificationsChanged)
    def notificationCount(self):
        if not self._notif_manager:
            return 0
        return self._notif_manager.unread_count()

    @Slot(result=list)
    def notifications(self):
        if not self._notif_manager:
            return []
        return [self._to_dict(n) for n in self._notif_manager.get_all()]

    # ---- Inbox ----
    @Slot(result=list)
    def inboxItems(self):
        if not self._inbox_manager:
            return []
        return [self._to_dict(item) for item in self._inbox_manager.get_all()]

    # ---- Download URL ----
    @Slot(str, str, str, str)
    def addDownloadTask(self, url: str, title: str = "", platform: str = "auto",
                        custom_name: str = ""):
        """添加下载任务。"""
        if not self._manager:
            return
        from ..queue_manager import QueueTask
        from ..utils.config import get_download_dir
        qt = QueueTask(
            url=url,
            title=title or url,
            author="",
            platform=platform,
            output_dir=str(get_download_dir()),
            custom_name=custom_name,
        )
        self._manager.add_task(qt)
        self._manager.start_task(qt.task_id)

    # ---- Stats ----
    @Slot(result=dict)
    def stats(self):
        if not self._history_manager:
            return {}
        if hasattr(self._history_manager, "get_stats"):
            return self._history_manager.get_stats()
        # 回退：基于历史记录构造最小统计
        records = self._history_manager.records
        per_platform: dict[str, int] = {}
        for r in records:
            key = getattr(r, "platform", "") or "unknown"
            per_platform[key] = per_platform.get(key, 0) + 1
        return {"total": len(records), "per_platform": per_platform}

    # ---- Config ----
    @Slot(str, result=str)
    def getConfig(self, key: str):
        return str(self._config.get(key, ""))

    @Slot(str, str)
    def setConfig(self, key: str, value: str):
        self._config[key] = value
        from ..utils.config import save_config
        save_config(self._config)

    # ---- Toast ----
    @Slot(str)
    def showToast(self, message: str):
        self.toastRequested.emit(message)
