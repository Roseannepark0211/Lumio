import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from .utils.config import load_config, save_config

_ASSETS = Path(__file__).parent / "assets"


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Lumio")
    app.setQuitOnLastWindowClosed(False)  # 托盘模式：隐藏窗口不退出
    logo = _ASSETS / "logo.png"
    if logo.exists():
        app.setWindowIcon(QIcon(str(logo)))
    cfg = load_config()

    _init_app_components(app, cfg)

    sys.exit(app.exec())


def _init_app_components(app, cfg):
    """Initialise shared components and launch QML UI."""
    from .api_server import start_server, stop_server
    from .gui.qml_bridge import launch_qml, QmlController
    from .inbox_manager import InboxManager
    from .queue_manager import DownloadManager
    from .notification_manager import NotificationManager

    manager = DownloadManager()
    manager.load_queue()
    # 绑定 history/library manager，确保下载完成能记录历史并入库
    # 注意：必须在 launch_qml 之前绑定，否则首个任务完成时无法入库
    from .library_manager import LibraryManager
    from .history_manager import HistoryManager
    library_manager = LibraryManager()
    history_manager = HistoryManager()
    manager.set_history_manager(history_manager)
    manager.set_library_manager(library_manager)
    app.aboutToQuit.connect(manager.shutdown)

    inbox_manager = InboxManager()
    start_server(inbox_manager, port=cfg.get("api_port", 38900))
    app.aboutToQuit.connect(stop_server)

    # LibraryManager + HistoryManager 已在上方创建并绑定到 manager
    # 此处只需创建 NotificationManager（QML 端通过 controller 调用）
    notification_manager = NotificationManager()
    # 启动时检测环境（Cookie / FFmpeg / 插件提示 / IG 风险）
    try:
        notification_manager.check_all()
    except Exception:
        pass

    # Telegram Bot 轮询
    tg_service = None
    if cfg.get("telegram_enabled") and cfg.get("telegram_bot_token"):
        from .telegram_service import TelegramService
        tg_service = TelegramService(inbox_manager)
        tg_service.start_polling()
        app.aboutToQuit.connect(tg_service.stop_polling)

    # 缓存自动清理（后台线程，不阻塞启动）
    _trigger_auto_cache_clean()

    # 启动 QML UI（同步阻塞，直到窗口关闭）
    launch_qml(
        manager=manager,
        inbox_manager=inbox_manager,
        library_manager=library_manager,
        history_manager=history_manager,
        notification_manager=notification_manager,
    )

    # Prevent GC: store references on the app object
    app._lumio_manager = manager
    app._lumio_inbox_manager = inbox_manager
    app._lumio_library_manager = library_manager
    app._lumio_history_manager = history_manager
    app._lumio_notification_manager = notification_manager
    if tg_service:
        app._lumio_tg_service = tg_service


def _trigger_auto_cache_clean():
    """根据 config.cache_management 配置在后台触发一次缓存清理。"""
    import threading

    def _do():
        try:
            from .utils.cache_manager import run_auto_clean_if_needed
            run_auto_clean_if_needed()
        except Exception:
            # 缓存清理失败不应影响应用启动
            pass

    threading.Thread(target=_do, daemon=True).start()


if __name__ == "__main__":
    main()
