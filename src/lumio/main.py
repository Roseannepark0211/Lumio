import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .utils.config import load_config, save_config

_ASSETS = Path(__file__).parent / "assets"


def main():
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
    manager, inbox_manager, window = _init_app_components(app, cfg)
    # Prevent GC: store references on the app object
    app._lumio_manager = manager
    app._lumio_inbox_manager = inbox_manager
    app._lumio_window = window


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
