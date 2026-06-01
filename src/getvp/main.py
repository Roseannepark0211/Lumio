import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .utils.config import load_config, save_config

_ASSETS = Path(__file__).parent / "assets"


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Lumio")
    logo = _ASSETS / "logo.png"
    if logo.exists():
        app.setWindowIcon(QIcon(str(logo)))
    cfg = load_config()

    if cfg.get("init_completed"):
        _show_main(app, cfg)
    else:
        _show_init(app, cfg)

    sys.exit(app.exec())


def _show_main(app, cfg):
    from .gui.window import MainWindow
    from .queue_manager import DownloadManager

    manager = DownloadManager()
    manager.load_queue()
    app.aboutToQuit.connect(manager.shutdown)

    window = MainWindow(manager)
    window.show()


def _show_init(app, cfg):
    from .gui.init_page import InitPage

    init_page = InitPage()
    init_page.resize(600, 500)
    init_page.setWindowTitle("Lumio")
    init_page.show()

    def on_init_done():
        cfg["init_completed"] = True
        save_config(cfg)

        from .gui.window import MainWindow
        from .queue_manager import DownloadManager

        manager = DownloadManager()
        manager.load_queue()
        app.aboutToQuit.connect(manager.shutdown)

        window = MainWindow(manager)
        window.show()
        init_page.close()

    init_page.check_completed.connect(on_init_done)
    init_page.start_checks()


if __name__ == "__main__":
    main()
