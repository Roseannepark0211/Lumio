import os
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from .utils.config import load_config, save_config

_ASSETS = Path(__file__).parent / "assets"


def main():
    # 设置 QtQuick.Controls 样式为 Basic，允许自定义背景和控件外观
    QQuickStyle.setStyle("Basic")

    app = QApplication(sys.argv)
    app.setApplicationName("Lumio")
    app.setQuitOnLastWindowClosed(False)  # 托盘模式：隐藏窗口不退出
    logo = _ASSETS / "logo.png"
    if logo.exists():
        app.setWindowIcon(QIcon(str(logo)))

    # 加载 Manrope + JetBrains Mono 字体（文件不存在则静默回退到系统字体）
    from .gui.theme.fonts import ensure_fonts_available
    ensure_fonts_available()

    cfg = load_config()

    if cfg.get("init_completed"):
        _show_main(app, cfg)
    else:
        _show_init(app, cfg)

    sys.exit(app.exec())


def _init_app_components(app, cfg):
    """Initialise shared components and return (manager, inbox_manager, window)."""
    from .api_server import start_server, stop_server
    from .gui.window import MainWindow
    from .inbox_manager import InboxManager
    from .queue_manager import DownloadManager

    manager = DownloadManager()
    manager.load_queue()
    app.aboutToQuit.connect(manager.shutdown)

    inbox_manager = InboxManager()
    start_server(inbox_manager, port=cfg.get("api_port", 38900))
    app.aboutToQuit.connect(stop_server)

    window = MainWindow(manager, inbox_manager=inbox_manager)
    window.show()

    # Telegram Bot 轮询
    if cfg.get("telegram_enabled") and cfg.get("telegram_bot_token"):
        from .telegram_service import TelegramService
        tg_service = TelegramService(inbox_manager)
        tg_service.start_polling()
        app.aboutToQuit.connect(tg_service.stop_polling)
        app._lumio_tg_service = tg_service

    # 缓存自动清理（后台线程，不阻塞启动）
    _trigger_auto_cache_clean()

    return manager, inbox_manager, window


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


def _show_main(app, cfg):
    from PySide6.QtQml import QQmlApplicationEngine

    from .gui.qml_bridge import QmlController
    from .gui.window import MainWindow
    from .api_server import start_server, stop_server
    from .inbox_manager import InboxManager
    from .queue_manager import DownloadManager
    from .history_manager import HistoryManager
    from .library_manager import LibraryManager
    from .notification_manager import NotificationManager

    # 初始化 managers
    manager = DownloadManager()
    manager.load_queue()
    app.aboutToQuit.connect(manager.shutdown)

    inbox_manager = InboxManager()
    start_server(inbox_manager, port=cfg.get("api_port", 38900))
    app.aboutToQuit.connect(stop_server)

    history_manager = HistoryManager()
    manager.set_history_manager(history_manager)

    library_manager = LibraryManager()
    manager.set_library_manager(library_manager)

    notif_manager = NotificationManager()

    # 创建 QML 控制器并注入 managers
    controller = QmlController()
    controller.set_managers(
        download_manager=manager,
        history_manager=history_manager,
        library_manager=library_manager,
        notification_manager=notif_manager,
        inbox_manager=inbox_manager,
    )

    # 启动 QML 引擎
    engine = QQmlApplicationEngine()

    # 注册 QML import 路径（让 `import Lumio` / `import Lumio.Components` 可解析）
    qml_dir = Path(__file__).parent / "qml"
    engine.addImportPath(str(qml_dir))

    # 注册 controller 到 root context
    engine.rootContext().setContextProperty("controller", controller)

    # 加载主 QML 文件
    engine.load(str(qml_dir / "Main.qml"))

    if not engine.rootObjects():
        print("QML 加载失败，回退到 QWidget 模式")
        # Fallback: 使用旧的 QWidget 窗口
        window = MainWindow(manager, inbox_manager=inbox_manager)
        window.show()
        app._lumio_manager = manager
        app._lumio_inbox_manager = inbox_manager
        app._lumio_window = window
        return

    notif_manager.check_all()

    # Telegram Bot 轮询
    if cfg.get("telegram_enabled") and cfg.get("telegram_bot_token"):
        from .telegram_service import TelegramService
        tg_service = TelegramService(inbox_manager)
        tg_service.start_polling()
        app.aboutToQuit.connect(tg_service.stop_polling)
        app._lumio_tg_service = tg_service

    # 缓存自动清理（后台线程，不阻塞启动）
    _trigger_auto_cache_clean()

    # Prevent GC: store references on the app object
    app._lumio_manager = manager
    app._lumio_inbox_manager = inbox_manager
    app._lumio_controller = controller
    app._lumio_engine = engine


def _show_init(app, cfg):
    from .gui.init_page import InitPage

    init_page = InitPage()
    init_page.resize(600, 500)
    init_page.setWindowTitle("Lumio")
    init_page.show()

    def on_init_done():
        cfg["init_completed"] = True
        save_config(cfg)
        manager, inbox_manager, window = _init_app_components(app, cfg)
        init_page.close()
        # Prevent GC
        app._lumio_manager = manager
        app._lumio_inbox_manager = inbox_manager
        app._lumio_window = window
        app._lumio_init_page = init_page
    init_page.check_completed.connect(on_init_done)
    init_page.start_checks()


if __name__ == "__main__":
    main()
