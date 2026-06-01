from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..downloader import VideoInfo, _build_format_options, extract_info
from ..i18n import t
from ..queue_manager import DownloadManager
from ..utils.config import get_download_dir, load_config, save_config
from ..utils.url_parser import Platform, parse_url
from .cookie_checker import CookieCheckWorker
from .queue_panel import QueueDrawer
from .settings import SettingsDialog
from .styles import STYLESHEET

_ASSETS = Path(__file__).parent.parent / "assets"


class _ExtractWorker(QThread):
    finished = Signal(object)

    def __init__(self, url: str):
        super().__init__()
        self._url = url

    def run(self):
        try:
            info = extract_info(self._url)
            self.finished.emit(info)
        except Exception as e:
            self.finished.emit(e)


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("section_title")
    return lbl


def _divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    line.setStyleSheet("color: #22253a; max-height: 1px;")
    return line


class MainWindow(QMainWindow):
    def __init__(self, manager: DownloadManager):
        super().__init__()
        self.setWindowTitle(t("app_title"))
        self.setMinimumSize(780, 640)
        self.resize(820, 680)
        self.setStyleSheet(STYLESHEET)

        from PySide6.QtGui import QIcon
        logo = _ASSETS / "logo.png"
        if logo.exists():
            self.setWindowIcon(QIcon(str(logo)))

        self._manager = manager
        self._current_info: VideoInfo | None = None
        self._download_dir = get_download_dir()

        self._build_ui()
        self._check_cookie_status()
        self._maybe_show_cookie_banner()

    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.setCentralWidget(scroll)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        root = QVBoxLayout(container)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        # ======== Top bar ========
        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        app_title = QLabel("Lumio")
        app_title.setObjectName("accent")
        top_row.addWidget(app_title)

        self._cookie_indicator = QLabel("")
        self._cookie_indicator.setVisible(False)
        top_row.addWidget(self._cookie_indicator)

        top_row.addStretch()

        self._settings_btn = QPushButton(t("settings"))
        self._settings_btn.setObjectName("secondary")
        self._settings_btn.setFixedHeight(34)
        self._settings_btn.clicked.connect(self._on_settings)
        top_row.addWidget(self._settings_btn)
        root.addLayout(top_row)

        # ======== Cookie banner (hidden by default) ========
        self._cookie_banner = QFrame()
        self._cookie_banner.setObjectName("cookie_banner")
        banner_layout = QHBoxLayout(self._cookie_banner)
        banner_layout.setContentsMargins(12, 8, 12, 8)
        banner_layout.setSpacing(10)

        banner_text = QLabel(t("cookie_guide"))
        banner_text.setObjectName("banner_text")
        banner_text.setCursor(Qt.CursorShape.PointingHandCursor)
        banner_text.mousePressEvent = lambda e: self._on_settings()
        banner_layout.addWidget(banner_text, 1)

        banner_close = QPushButton("×")
        banner_close.setObjectName("banner_close")
        banner_close.setFixedSize(28, 28)
        banner_close.clicked.connect(lambda: self._cookie_banner.hide())
        banner_layout.addWidget(banner_close)

        self._cookie_banner.hide()
        root.addWidget(self._cookie_banner)

        # ======== Input section ========
        root.addWidget(_section_label(t("url_input")))
        self._url_input = QPlainTextEdit()
        self._url_input.setPlaceholderText(t("url_placeholder"))
        self._url_input.setMaximumHeight(72)
        self._url_input.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        root.addWidget(self._url_input)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._parse_btn = QPushButton(t("parse"))
        self._parse_btn.clicked.connect(self._on_parse)
        self._parse_btn.setMinimumWidth(100)
        btn_row.addWidget(self._parse_btn)

        self._path_btn = QPushButton(t("save_to"))
        self._path_btn.setObjectName("secondary")
        self._path_btn.clicked.connect(self._on_choose_dir)
        btn_row.addWidget(self._path_btn)

        self._dir_label = QLabel(str(self._download_dir))
        self._dir_label.setObjectName("muted")
        btn_row.addWidget(self._dir_label, 1)
        root.addLayout(btn_row)

        root.addWidget(_divider())

        # ======== Preview section ========
        root.addWidget(_section_label(t("preview")))

        self._title_label = QLabel(t("paste_hint"))
        self._title_label.setObjectName("muted")
        self._title_label.setWordWrap(True)
        root.addWidget(self._title_label)

        self._thumb_label = QLabel("")
        self._thumb_label.setMinimumHeight(120)
        self._thumb_label.setMaximumHeight(280)
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setStyleSheet(
            "background-color: #12141c; border: 1px solid #1e2130; border-radius: 8px;"
        )
        self._thumb_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        root.addWidget(self._thumb_label, 1)

        root.addWidget(_divider())

        # ======== Download controls ========
        root.addWidget(_section_label(t("format_download")))

        name_row = QHBoxLayout()
        name_row.setSpacing(10)
        self._name_label = QLabel(t("name_label"))
        name_row.addWidget(self._name_label)
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText(t("leave_empty"))
        self._name_input.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        name_row.addWidget(self._name_input, 1)
        root.addLayout(name_row)

        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(10)
        self._fmt_label = QLabel(t("format_label"))
        fmt_row.addWidget(self._fmt_label)
        self._format_combo = QComboBox()
        self._format_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        fmt_row.addWidget(self._format_combo, 1)

        self._download_btn = QPushButton(t("add_to_queue"))
        self._download_btn.setObjectName("accent_btn")
        self._download_btn.setEnabled(False)
        self._download_btn.clicked.connect(self._on_add_to_queue)
        fmt_row.addWidget(self._download_btn)
        root.addLayout(fmt_row)

        root.addWidget(_divider())

        # ======== Queue drawer ========
        root.addWidget(_section_label(t("queue_title")))

        self._queue_drawer = QueueDrawer(self._manager)
        root.addWidget(self._queue_drawer)

        # Stretch: preview gets space
        root.setStretch(0, 0)   # top bar
        root.setStretch(1, 0)   # banner
        root.setStretch(2, 0)   # section label
        root.setStretch(3, 0)   # url input
        root.setStretch(4, 0)   # btn row
        root.setStretch(5, 0)   # divider
        root.setStretch(6, 0)   # section label
        root.setStretch(7, 0)   # title
        root.setStretch(8, 1)   # thumbnail
        root.setStretch(9, 0)   # divider
        root.setStretch(10, 0)  # section label
        root.setStretch(11, 0)  # name row
        root.setStretch(12, 0)  # format row
        root.setStretch(13, 0)  # divider
        root.setStretch(14, 0)  # section label
        root.setStretch(15, 0)  # queue drawer

        scroll.setWidget(container)

    # ---- Cookie ----

    def _check_cookie_status(self):
        self._cookie_worker = CookieCheckWorker()
        self._cookie_worker.result.connect(self._on_cookie_result)
        self._cookie_worker.start()

    @Slot(str)
    def _on_cookie_result(self, status: str):
        self._cookie_indicator.setVisible(True)
        if status == "已配置":
            self._cookie_indicator.setText("IG ✓")
            self._cookie_indicator.setObjectName("cookie_ok")
        elif status == "已失效":
            self._cookie_indicator.setText("IG !")
            self._cookie_indicator.setObjectName("cookie_expired")
        else:
            self._cookie_indicator.setText("IG ✗")
            self._cookie_indicator.setObjectName("cookie_missing")
        # Re-polish to apply style
        self._cookie_indicator.style().unpolish(self._cookie_indicator)
        self._cookie_indicator.style().polish(self._cookie_indicator)

    def _maybe_show_cookie_banner(self):
        cfg = load_config()
        if cfg.get("cookie_banner_shown"):
            return
        from .cookie_checker import check_ig_cookie_status
        if check_ig_cookie_status() == "未配置":
            QTimer.singleShot(500, self._cookie_banner.show)
            QTimer.singleShot(10500, self._cookie_banner.hide)
            cfg["cookie_banner_shown"] = True
            save_config(cfg)

    # ---- Slots ----

    @Slot()
    def _on_settings(self):
        dlg = SettingsDialog(self)
        dlg.restart_requested.connect(self._restart_app)
        dlg.exec()
        # Apply concurrency changes
        cfg = load_config()
        self._manager.set_max_workers(cfg.get("max_concurrent", 3))
        # Refresh cookie status
        self._check_cookie_status()

    @Slot()
    def _restart_app(self):
        program = sys.executable
        args = ["-m", "getvp.main"]
        import os
        QProcess.startDetached(program, args, os.getcwd())
        QApplication.instance().quit()

    @Slot()
    def _on_choose_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, t("save_to"), str(self._download_dir)
        )
        if d:
            self._download_dir = Path(d)
            self._dir_label.setText(d)

    @Slot()
    def _on_parse(self):
        text = self._url_input.toPlainText().strip()
        if not text:
            return

        first_line = text.splitlines()[0].strip()
        parsed = parse_url(first_line)

        if parsed.platform == Platform.UNSUPPORTED:
            QMessageBox.warning(
                self, t("unsupported"), t("unsupported_msg") + first_line
            )
            return

        self._parse_btn.setEnabled(False)
        self._parse_btn.setText("...")
        self._title_label.setText(t("loading"))
        self._thumb_label.setText("")

        self._extract_worker = _ExtractWorker(parsed.url)
        self._extract_worker.finished.connect(self._on_extract_done)
        self._extract_worker.start()

    @Slot(object)
    def _on_extract_done(self, result):
        self._parse_btn.setEnabled(True)
        self._parse_btn.setText(t("parse"))

        if isinstance(result, Exception):
            self._title_label.setText(t("parse_failed"))
            QMessageBox.critical(self, t("parse_failed"), str(result))
            return

        info: VideoInfo = result
        self._current_info = info
        self._is_ig = bool(info.items)

        dur = ""
        if info.duration:
            m, s = divmod(int(info.duration), 60)
            dur = f"  ({m}:{s:02d})"
        time_str = f"  [{info.post_time}]" if info.post_time else ""
        author_str = f"  @{info.author}" if info.author else ""
        self._title_label.setStyleSheet("color: #e0e0e6; font-size: 14px;")
        self._title_label.setText(f"{info.title}{dur}{time_str}{author_str}")

        raw_name = info.author if info.author else info.title
        safe_name = raw_name[:60].strip()
        for ch in '\\/:*?"<>|':
            safe_name = safe_name.replace(ch, "_")
        self._name_input.setText(safe_name)

        if info.thumbnail:
            from urllib.request import urlopen
            try:
                data = urlopen(info.thumbnail).read()
                pix = QPixmap()
                pix.loadFromData(data)
                target_h = min(276, max(120, int(pix.height() * 0.6)))
                self._thumb_label.setPixmap(
                    pix.scaledToHeight(target_h, Qt.TransformationMode.SmoothTransformation)
                )
            except Exception:
                self._thumb_label.setText(t("thumbnail_unavail"))
        else:
            self._thumb_label.setText(t("no_thumbnail"))

        self._format_combo.clear()
        if self._is_ig:
            n_img = sum(1 for it in info.items if not it.is_video)
            n_vid = sum(1 for it in info.items if it.is_video)
            parts = []
            if n_vid:
                parts.append(t("videos", n=n_vid))
            if n_img:
                parts.append(t("images", n=n_img))
            sep = " + " if len(parts) == 2 else ""
            label = t("download_all", video=parts[0] if n_vid else "",
                       sep=sep, image=parts[-1] if n_img else "")
            self._format_combo.addItem(label.strip(), ("all", ""))
            self._format_combo.setEnabled(False)
        else:
            opts = _build_format_options(info)
            for opt in opts:
                if opt.get("disabled"):
                    continue
                self._format_combo.addItem(opt["label"], (opt["id"], opt.get("_type", "")))
            self._format_combo.setEnabled(True)

        self._download_btn.setEnabled(True)

    @Slot()
    def _on_add_to_queue(self):
        if not self._current_info:
            return

        fmt_data = self._format_combo.currentData()
        if isinstance(fmt_data, tuple):
            fmt_id, fmt_type = fmt_data
        else:
            fmt_id, fmt_type = fmt_data, ""

        custom = self._name_input.text().strip()

        task_id = self._manager.add_task_from_info(
            info=self._current_info,
            format_id=fmt_id,
            format_type=fmt_type,
            custom_name=custom,
            output_dir=self._download_dir,
        )

        # Show toast
        self._show_toast(t("added_to_queue"))

        # Clear preview for next URL
        self._current_info = None
        self._download_btn.setEnabled(False)
        self._format_combo.clear()
        self._title_label.setText(t("paste_hint"))
        self._title_label.setStyleSheet("color: #6b7084; font-size: 13px;")
        self._thumb_label.clear()
        self._thumb_label.setText("")
        self._name_input.clear()
        self._url_input.clear()

    def _show_toast(self, msg: str):
        toast = QLabel(msg, self)
        toast.setObjectName("toast")
        toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toast.setFixedHeight(36)
        toast.setMinimumWidth(200)
        toast.move(
            (self.width() - toast.width()) // 2,
            self.height() - 100,
        )
        toast.show()
        QTimer.singleShot(2000, toast.deleteLater)
