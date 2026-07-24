from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
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
    finished_fail = Signal(list)    # list of (name, passed, hint)

    def run(self):
        all_ok = True
        results = []  # (name, passed: bool, hint: str)
        is_packaged = getattr(sys, 'frozen', False)

        # ---- setup: ensure dirs exist (always needed, not counted as checks) ----
        from ..utils.config import _APP_DIR
        _APP_DIR.mkdir(parents=True, exist_ok=True)
        cfg = load_config()
        save_config(cfg)
        Path(cfg["cookie_file"]).parent.mkdir(parents=True, exist_ok=True)
        dl_dir = get_download_dir()
        dl_dir.mkdir(parents=True, exist_ok=True)

        if is_packaged:
            # Packaged env: Python/FFmpeg/yt-dlp all bundled, pip install won't work.
            # Only check what actually matters at runtime.
            pass
        else:
            # Dev env: verify runtime deps, attempt auto-install if missing.
            # 1. FFmpeg
            try:
                from ..downloader import _find_ffmpeg
                ff = _find_ffmpeg()
                if ff:
                    self.log.emit(f"FFmpeg: {Path(ff).name}", "[OK]")
                    results.append(("FFmpeg", True, ""))
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
                        results.append(("FFmpeg", True, ""))
                    else:
                        self.log.emit("FFmpeg: install failed", "[WARN]")
                        results.append(("FFmpeg", False, "pip install imageio-ffmpeg"))
                        all_ok = False
                except Exception as e:
                    self.log.emit(f"FFmpeg: {e}", "[FAIL]")
                    results.append(("FFmpeg", False, "pip install imageio-ffmpeg"))
                    all_ok = False

            # 2. yt-dlp
            try:
                import yt_dlp
                self.log.emit(f"yt-dlp {yt_dlp.version.__version__}", "[OK]")
                results.append(("yt-dlp", True, ""))
            except ImportError:
                self.log.emit("yt-dlp: installing...", "[FIXED]")
                try:
                    subprocess.run(
                        [sys.executable, "-m", "pip", "install", "yt-dlp", "-q"],
                        capture_output=True, timeout=120,
                    )
                    import yt_dlp
                    self.log.emit("yt-dlp: installed", "[OK]")
                    results.append(("yt-dlp", True, ""))
                except Exception as e:
                    self.log.emit(f"yt-dlp: {e}", "[FAIL]")
                    results.append(("yt-dlp", False, "pip install yt-dlp"))
                    all_ok = False

        # ---- common checks (both envs) ----
        # Network
        import requests
        network_ok = False
        for url in [
            "https://www.baidu.com",
            "https://www.youtube.com",
            "https://www.instagram.com",
            "https://x.com",
        ]:
            try:
                requests.head(url, timeout=3, allow_redirects=True)
                self.log.emit(f"Network: {url}", "[OK]")
                network_ok = True
                break
            except Exception:
                continue
        if not network_ok:
            self.log.emit("Network: unreachable", "[WARN]")
            results.append((t("init_check_network"), False, t("init_hint_network")))
            all_ok = False
        else:
            results.append((t("init_check_network"), True, ""))

        # File write permission
        test_file = dl_dir / ".lumio_write_test"
        try:
            test_file.write_text("test", encoding="utf-8")
            test_file.unlink()
            self.log.emit("File write permission", "[OK]")
            results.append((t("init_check_file_write"), True, ""))
        except Exception:
            self.log.emit("File write: permission denied", "[FAIL]")
            results.append((t("init_check_file_write"), False, t("init_hint_file_write")))
            all_ok = False

        if all_ok:
            self.finished_ok.emit()
        else:
            self.finished_fail.emit(results)


class InitPage(QWidget):
    check_completed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entered = False
        self._countdown_timer = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(60, 40, 60, 40)
        layout.setSpacing(16)

        # Title
        title = QLabel("Lumio")
        title.setObjectName("init_title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(t("init_title"))
        subtitle.setObjectName("muted")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
        self._status.setObjectName("status_msg")
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
        self._entered = False

    def _emit_complete(self):
        # 防止按钮点击 + 倒计时重复触发
        if self._entered:
            return
        self._entered = True
        if hasattr(self, "_countdown_timer"):
            self._countdown_timer.stop()
        self._enter_btn.setEnabled(False)
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
        self._set_status_state("success")

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

    def _set_status_state(self, state: str) -> None:
        """动态切换 self._status (QLabel#status_msg) 的 state 属性并刷新样式。

        Args:
            state: success / warning / error / neutral
        """
        self._status.setProperty("state", state)
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def _on_fail(self, results: list):
        self._progress.setMaximum(100)
        self._progress.setValue(0)
        self._status.setText(t("init_some_failed"))
        self._set_status_state("warning")

        # Show checklist dialog
        dlg = QDialog(self)
        dlg.setWindowTitle(t("init_checklist_title"))
        dlg.setMinimumWidth(420)
        lay = QVBoxLayout(dlg)
        lay.setSpacing(8)

        title = QLabel(t("init_checklist_title"))
        title.setObjectName("section_header")
        lay.addWidget(title)

        for name, passed, hint in results:
            icon = "✅" if passed else "❌"
            line = QLabel(f"{icon}  {name}")
            line.setObjectName("card_meta")
            lay.addWidget(line)
            if not passed and hint:
                hint_lbl = QLabel(f"      → {hint}")
                hint_lbl.setObjectName("muted")
                hint_lbl.setWordWrap(True)
                lay.addWidget(hint_lbl)

        ok_btn = QPushButton(t("init_ok"))
        ok_btn.setObjectName("accent_btn")
        ok_btn.setFixedWidth(80)
        ok_btn.clicked.connect(dlg.accept)
        lay.addWidget(ok_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        dlg.exec()

        # Show "enter anyway" button (non-critical failures)
        self._enter_btn.setText(t("enter_anyway"))
        self._enter_btn.show()
