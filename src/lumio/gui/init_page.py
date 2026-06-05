from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtWidgets import (
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..i18n import t
from ..utils.config import get_download_dir, load_config, save_config


class _CheckWorker(QThread):
    log = Signal(str, str)          # message, status ([OK]/[FIXED]/[WARN]/[FAIL])
    finished_ok = Signal()
    finished_fail = Signal(str)

    def run(self):
        all_ok = True

        # 1. Python
        ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        self.log.emit(f"Python {ver}", "[OK]")

        # 2. FFmpeg
        try:
            from ..downloader import _find_ffmpeg
            ff = _find_ffmpeg()
            if ff:
                self.log.emit(f"FFmpeg: {Path(ff).name}", "[OK]")
            else:
                raise FileNotFoundError
        except Exception:
            self.log.emit("FFmpeg: installing...", "[FIXED]")
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "imageio-ffmpeg", "-q"],
                    capture_output=True, timeout=120,
                )
                from ..downloader import _find_ffmpeg
                if _find_ffmpeg():
                    self.log.emit("FFmpeg: installed", "[OK]")
                else:
                    self.log.emit("FFmpeg: install failed", "[WARN]")
                    all_ok = False
            except Exception as e:
                self.log.emit(f"FFmpeg: {e}", "[FAIL]")
                all_ok = False

        # 3. yt-dlp
        try:
            import yt_dlp
            self.log.emit(f"yt-dlp {yt_dlp.version.__version__}", "[OK]")
        except ImportError:
            self.log.emit("yt-dlp: installing...", "[FIXED]")
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "yt-dlp", "-q"],
                    capture_output=True, timeout=120,
                )
                import yt_dlp
                self.log.emit("yt-dlp: installed", "[OK]")
            except Exception as e:
                self.log.emit(f"yt-dlp: {e}", "[FAIL]")
                all_ok = False

        # 4. Config directory
        from ..utils.config import _APP_DIR
        if _APP_DIR.exists():
            self.log.emit(f"Config dir: {_APP_DIR}", "[OK]")
        else:
            _APP_DIR.mkdir(parents=True, exist_ok=True)
            self.log.emit(f"Config dir: created", "[FIXED]")

        # 5. Config file
        cfg = load_config()
        save_config(cfg)
        self.log.emit("Config file", "[OK]")

        # 6. Cookie directory
        cookie_dir = Path(cfg["cookie_file"]).parent
        cookie_dir.mkdir(parents=True, exist_ok=True)
        self.log.emit("Cookie directory", "[OK]")

        # 7. Download directory
        dl_dir = get_download_dir()
        if dl_dir.exists():
            self.log.emit(f"Download dir: {dl_dir}", "[OK]")
        else:
            dl_dir.mkdir(parents=True, exist_ok=True)
            self.log.emit("Download dir: created", "[FIXED]")

        # 8. Network
        import requests
        for url in ["https://www.youtube.com", "https://www.instagram.com", "https://x.com"]:
            try:
                requests.head(url, timeout=5, allow_redirects=True)
                self.log.emit(f"Network: {url}", "[OK]")
                break
            except Exception:
                continue
        else:
            self.log.emit("Network: unreachable", "[WARN]")
            all_ok = False

        # 9. File write permission
        test_file = dl_dir / ".lumio_write_test"
        try:
            test_file.write_text("test", encoding="utf-8")
            test_file.unlink()
            self.log.emit("File write permission", "[OK]")
        except Exception:
            self.log.emit("File write: permission denied", "[FAIL]")
            all_ok = False

        if all_ok:
            self.finished_ok.emit()
        else:
            self.finished_fail.emit("Some checks failed")


class InitPage(QWidget):
    check_completed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(60, 40, 60, 40)
        layout.setSpacing(16)

        # Title
        title = QLabel("Lumio")
        title.setObjectName("accent")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 28px; font-weight: 700; color: #7c8fff;")
        layout.addWidget(title)

        subtitle = QLabel(t("init_title"))
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #6b7084; font-size: 14px;")
        layout.addWidget(subtitle)

        layout.addSpacing(20)

        # Log area
        self._log = QPlainTextEdit()
        self._log.setObjectName("init_log")
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(200)
        layout.addWidget(self._log)

        # Status
        self._status = QLabel(t("init_checking"))
        self._status.setObjectName("muted")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status)

        # Progress
        self._progress = QProgressBar()
        self._progress.setMaximum(0)  # indeterminate
        self._progress.setTextVisible(False)
        layout.addWidget(self._progress)

        # Enter button (hidden until checks pass)
        self._enter_btn = QPushButton("")
        self._enter_btn.setObjectName("accent_btn")
        self._enter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._enter_btn.clicked.connect(self._emit_complete)
        self._enter_btn.hide()
        layout.addWidget(self._enter_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self._countdown = 10

    def _emit_complete(self):
        self.check_completed.emit()

    def start_checks(self):
        self._worker = _CheckWorker()
        self._worker.log.connect(self._on_log)
        self._worker.finished_ok.connect(self._on_all_pass)
        self._worker.finished_fail.connect(self._on_fail)
        self._worker.start()

    def _on_log(self, msg: str, status: str):
        self._log.appendPlainText(f"  {status}  {msg}")

    def _on_all_pass(self):
        self._progress.setMaximum(100)
        self._progress.setValue(100)
        self._status.setText(t("init_all_pass"))
        self._status.setStyleSheet("color: #10b981; font-size: 14px; font-weight: 600;")

        self._countdown = 10
        self._enter_btn.show()
        self._update_enter_btn()

        self._countdown_timer = QTimer(self)
        self._countdown_timer.timeout.connect(self._tick)
        self._countdown_timer.start(1000)

    def _tick(self):
        self._countdown -= 1
        if self._countdown <= 0:
            self._countdown_timer.stop()
            self._emit_complete()
        else:
            self._update_enter_btn()

    def _update_enter_btn(self):
        self._enter_btn.setText(f"{t('enter_now')} ({self._countdown}s)")

    def _on_fail(self, reason: str):
        self._progress.setMaximum(100)
        self._progress.setValue(0)
        self._status.setText(f"{t('error')}: {reason}")
        self._status.setStyleSheet("color: #f87171; font-size: 14px;")
