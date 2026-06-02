from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..downloader import VideoInfo, _build_format_options, extract_info
from ..i18n import t
from ..queue_manager import DownloadManager
from ..utils.config import get_download_dir
from ..utils.url_parser import Platform, parse_url


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
    line.setObjectName("home_divider")
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    line.setFixedHeight(1)
    return line


class HomePage(QWidget):
    request_batch_dialog = Signal(str, str, str)  # dialog_type, url, tab

    def __init__(self, manager: DownloadManager, parent=None):
        super().__init__(parent)
        self.setObjectName("home_page")
        self._manager = manager
        self._current_info: VideoInfo | None = None
        self._download_dir = get_download_dir()
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(14)

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
        self._thumb_label.setObjectName("thumb_label")
        self._thumb_label.setMinimumHeight(120)
        self._thumb_label.setMaximumHeight(280)
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
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

        # Stretch preview area
        root.setStretch(4, 1)

    # ---- Slots ----

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

        # Instagram profile -> batch dialog
        if parsed.platform == Platform.INSTAGRAM and parsed.kind == "profile":
            username = parsed.url.rstrip("/").split("/")[-1]
            self.request_batch_dialog.emit("instagram", username, "")
            return

        # YouTube channel/playlist -> batch dialog
        if parsed.platform == Platform.YOUTUBE and parsed.kind in ("channel", "playlist"):
            self.request_batch_dialog.emit("youtube", parsed.url, parsed.tab)
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

        self._manager.add_task_from_info(
            info=self._current_info,
            format_id=fmt_id,
            format_type=fmt_type,
            custom_name=custom,
            output_dir=self._download_dir,
        )

        # Clear preview
        self._current_info = None
        self._download_btn.setEnabled(False)
        self._format_combo.clear()
        self._title_label.setText(t("paste_hint"))
        self._title_label.setStyleSheet("color: #6b7084; font-size: 13px;")
        self._thumb_label.clear()
        self._thumb_label.setText("")
        self._name_input.clear()
        self._url_input.clear()
