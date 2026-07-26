import signal
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from .utils.config import load_config, save_config

_ASSETS = Path(__file__).parent / "assets"


def main():
    # 修复：Qt 事件循环默认不响应 SIGINT，导致终端 Ctrl+C 无效
    # 让 Python 默认 SIGINT 处理器接管，可在运行中按 Ctrl+C 退出
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setApplicationName("Lumio")
    # 修复：QML 版本未创建系统托盘（QWidget 版 window.py 才有），
    # 关闭窗口应直接退出，否则会变成"窗口关了但进程不退"的僵尸状态
    app.setQuitOnLastWindowClosed(True)
    logo = _ASSETS / "logo.png"
    if logo.exists():
        app.setWindowIcon(QIcon(str(logo)))
    cfg = load_config()

    _init_app_components(app, cfg)

    # 兜底：app.exec() 异常返回时强制退出
    # （某些后台 daemon 线程可能持有资源导致 sys.exit 不彻底）
    exit_code = app.exec()
    sys.exit(exit_code)


def _init_app_components(app, cfg):
    """Initialise shared components and launch QML UI."""
    from .api_server import start_server, stop_server
    from .gui.qml_bridge import launch_qml, QmlController
    from .inbox_manager import InboxManager
    from .queue_manager import DownloadManager
    from .notification_manager import NotificationManager, set_notification_manager

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

    # 创建 NotificationManager 并注册为全局单例
    # （settings_page 等其他模块通过 get_notification_manager() 复用此实例，
    # 避免双实例并发写 JSON 文件导致数据丢失）
    notification_manager = NotificationManager()
    set_notification_manager(notification_manager)
    # 启动时检测环境（Python deps / 网络代理 / FFmpeg / Cookie 7天预警 / 插件 / IG 风险 / 版本检查）
    # check_all 默认后台异步执行，不阻塞 GUI 启动
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
