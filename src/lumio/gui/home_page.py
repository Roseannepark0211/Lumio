from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
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
from ..x_sou_client import x_sou_search
from ..i18n import t
from ..queue_manager import DownloadManager
from ..utils.config import get_download_dir
from ..utils.url_parser import Platform, parse_url
from .widgets import NoWheelComboBox


class _ThumbWorker(QThread):
    finished = Signal(bytes)

    def __init__(self, url: str):
        super().__init__()
        self._url = url

    def run(self):
        try:
            from urllib.request import urlopen
            data = urlopen(self._url, timeout=10).read()
            self.finished.emit(data)
        except Exception:
            self.finished.emit(b"")


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


class _SearchWorker(QThread):
    finished = Signal(object)

    def __init__(self, query: str, page: int, limit: int):
        super().__init__()
        self._query = query
        self._page = page
        self._limit = limit

    def run(self):
        try:
            result = x_sou_search(self._query, page=self._page, limit=self._limit)
            self.finished.emit(result)
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
    search_batch_added = Signal(int)  # count of tasks added

    def __init__(self, manager: DownloadManager, parent=None):
        super().__init__(parent)
        self.setObjectName("home_page")
        self._manager = manager
        self._current_info: VideoInfo | None = None
        self._download_dir = get_download_dir()
        # Search state
        self._search_query = ""
        self._search_page = 1
        self._search_total = 0
        self._search_limit = 15
        self._search_worker: _SearchWorker | None = None
        self._result_rows: list[dict] = []  # [{checkbox, data, thumb_label}]
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

        self._search_btn = QPushButton(t("search"))
        self._search_btn.clicked.connect(self._on_search)
        self._search_btn.setMinimumWidth(80)
        btn_row.addWidget(self._search_btn)

        self._reset_btn = QPushButton(t("reset"))
        self._reset_btn.setObjectName("secondary")
        self._reset_btn.clicked.connect(self._on_reset)
        btn_row.addWidget(self._reset_btn)

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

        # Single-item preview (normal URL parse)
        self._thumb_label = QLabel("")
        self._thumb_label.setObjectName("thumb_label")
        self._thumb_label.setMinimumHeight(120)
        self._thumb_label.setMaximumHeight(280)
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        root.addWidget(self._thumb_label, 1)

        # Search results (replaces thumb_label when searching)
        from PySide6.QtWidgets import QScrollArea, QCheckBox
        self._search_container = QWidget()
        self._search_container.hide()
        sc_layout = QVBoxLayout(self._search_container)
        sc_layout.setContentsMargins(0, 0, 0, 0)
        sc_layout.setSpacing(6)

        self._search_status = QLabel()
        self._search_status.setObjectName("muted")
        sc_layout.addWidget(self._search_status)

        # Scrollable result list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(200)
        scroll.setMaximumHeight(400)
        scroll.setObjectName("search_scroll")
        self._results_container = QWidget()
        self._results_layout = QVBoxLayout(self._results_container)
        self._results_layout.setContentsMargins(0, 0, 0, 0)
        self._results_layout.setSpacing(4)
        self._results_layout.addStretch()
        scroll.setWidget(self._results_container)
        sc_layout.addWidget(scroll, 1)

        # Action bar
        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        self._select_all_btn = QPushButton(t("select_all"))
        self._select_all_btn.setObjectName("secondary")
        self._select_all_btn.clicked.connect(self._on_select_all)
        action_row.addWidget(self._select_all_btn)

        self._add_selected_btn = QPushButton(t("add_to_queue"))
        self._add_selected_btn.setObjectName("accent_btn")
        self._add_selected_btn.setEnabled(False)
        self._add_selected_btn.clicked.connect(self._on_add_selected)
        action_row.addWidget(self._add_selected_btn)

        action_row.addStretch()

        self._prev_page_btn = QPushButton(t("prev_page"))
        self._prev_page_btn.setObjectName("secondary")
        self._prev_page_btn.setFixedHeight(26)
        self._prev_page_btn.setMinimumWidth(50)
        self._prev_page_btn.clicked.connect(self._on_prev_page)
        self._prev_page_btn.setEnabled(False)
        action_row.addWidget(self._prev_page_btn)

        self._page_label = QLabel("1")
        self._page_label.setObjectName("muted")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page_label.setFixedWidth(30)
        action_row.addWidget(self._page_label)

        self._next_page_btn = QPushButton(t("next_page"))
        self._next_page_btn.setObjectName("secondary")
        self._next_page_btn.setFixedHeight(26)
        self._next_page_btn.setMinimumWidth(50)
        self._next_page_btn.clicked.connect(self._on_next_page)
        self._next_page_btn.setEnabled(False)
        action_row.addWidget(self._next_page_btn)

        sc_layout.addLayout(action_row)
        root.addWidget(self._search_container, 1)

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
        self._format_combo = NoWheelComboBox()
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

        # Switch back to preview view (hide search results)
        self._search_container.hide()
        self._thumb_label.show()

        lines = [line.strip() for line in text.splitlines() if line.strip()]

        if len(lines) > 1:
            self._batch_parse(lines)
            return

        first_line = lines[0]
        parsed = parse_url(first_line)

        if parsed.platform == Platform.UNSUPPORTED:
            # Phase 1 Step 2: try domestic platforms before giving up
            from ..providers.detector import detect_domestic as _dd
            domestic_result = _dd(first_line)
            if not domestic_result:
                QMessageBox.warning(
                    self, t("unsupported"), t("unsupported_msg") + first_line
                )
                return
            # Phase 1 Step 3: domestic profile URL → batch dialog
            _dom_platform, _dom_kind = domestic_result
            if _dom_kind == "profile":
                import re as _re
                identifier = ""
                for _pat in [
                    r"weibo\.com/(\d+)",
                    r"m\.weibo\.cn/u/(\d+)",
                    r"xiaohongshu\.com/user/profile/([a-f0-9]+)",
                    r"bilibili\.com/space/(\d+)",
                    r"space\.bilibili\.com/(\d+)",
                    r"douyin\.com/user/([\w.]+)",
                ]:
                    _m = _re.search(_pat, first_line)
                    if _m:
                        identifier = _m.group(1)
                        break
                if not identifier:
                    identifier = first_line.rstrip("/").split("/")[-1]
                self.request_batch_dialog.emit(_dom_platform.value, identifier, "")
                return
            # Domestic post URL — continue to extraction below

        # Instagram profile -> batch dialog
        if parsed.platform == Platform.INSTAGRAM and parsed.kind == "profile":
            username = parsed.url.rstrip("/").split("/")[-1]
            self.request_batch_dialog.emit("instagram", username, "")
            return

        # YouTube channel/playlist -> batch dialog
        if parsed.platform == Platform.YOUTUBE and parsed.kind in ("channel", "playlist"):
            self.request_batch_dialog.emit("youtube", parsed.url, parsed.tab)
            return

        # X profile -> batch dialog
        if parsed.platform == Platform.X and parsed.kind == "profile":
            username = parsed.url.rstrip("/").split("/")[-1]
            self.request_batch_dialog.emit("x", username, "")
            return

        self._parse_btn.setEnabled(False)
        self._parse_btn.setText("...")
        self._title_label.setText(t("loading"))
        self._thumb_label.setText("")

        # Disconnect old worker if still running
        if hasattr(self, "_extract_worker") and self._extract_worker:
            try:
                self._extract_worker.finished.disconnect()
            except RuntimeError:
                pass

        self._extract_worker = _ExtractWorker(parsed.url)
        self._extract_worker.finished.connect(self._on_extract_done)
        self._extract_worker.start()

        # Overall timeout: 30 seconds
        QTimer.singleShot(30000, self._extract_timeout)

    def _extract_timeout(self):
        if hasattr(self, "_extract_worker") and self._extract_worker and self._extract_worker.isRunning():
            self._extract_worker.terminate()
            self._extract_worker.wait(1000)
            self._on_extract_done(TimeoutError(t("parse_timeout")))

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
        self._title_label.setText(f"{info.title}{dur}{time_str}{author_str}")
        self._title_label.style().unpolish(self._title_label)
        self._title_label.style().polish(self._title_label)

        raw_name = info.author if info.author else info.title
        safe_name = raw_name[:60].strip()
        for ch in '\\/:*?"<>|':
            safe_name = safe_name.replace(ch, "_")
        self._name_input.setText(safe_name)

        if info.thumbnail:
            self._thumb_label.setText(t("loading"))
            self._thumb_worker = _ThumbWorker(info.thumbnail)
            self._thumb_worker.finished.connect(self._on_thumb_loaded)
            self._thumb_worker.start()
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

    @Slot(bytes)
    def _on_thumb_loaded(self, data: bytes):
        if data:
            pix = QPixmap()
            pix.loadFromData(data)
            target_h = min(276, max(120, int(pix.height() * 0.6)))
            self._thumb_label.setPixmap(
                pix.scaledToHeight(target_h, Qt.TransformationMode.SmoothTransformation)
            )
        else:
            self._thumb_label.setText(t("thumbnail_unavail"))

    def _batch_parse(self, urls: list[str]):
        """Parse multiple URLs and add all to queue."""
        valid = []
        invalid = []
        for url in urls:
            parsed = parse_url(url)
            if parsed.platform == Platform.UNSUPPORTED:
                # Phase 1 Step 2: try domestic platforms
                from ..providers.detector import detect_domestic as _dd
                if not _dd(url):
                    invalid.append(url[:40])
                    continue
            valid.append(parsed.url)

        if invalid:
            QMessageBox.warning(
                self, t("unsupported"),
                t("batch_invalid", count=len(invalid), urls="\n".join(invalid[:5]))
            )
        if not valid:
            return

        reply = QMessageBox.question(
            self, t("batch_title"),
            t("batch_confirm", count=len(valid)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._batch_urls = valid
        self._batch_index = 0
        self._batch_added = 0
        self._parse_btn.setEnabled(False)
        self._parse_btn.setText("...")
        self._title_label.setText(t("batch_processing", current=1, total=len(valid)))
        self._start_batch_extract()

    def _start_batch_extract(self):
        if self._batch_index >= len(self._batch_urls):
            self._finish_batch()
            return
        url = self._batch_urls[self._batch_index]
        self._title_label.setText(t("batch_processing", current=self._batch_index + 1, total=len(self._batch_urls)))
        self._extract_worker = _ExtractWorker(url)
        self._extract_worker.finished.connect(self._on_batch_extract_done)
        self._extract_worker.start()

    @Slot(object)
    def _on_batch_extract_done(self, result):
        if not isinstance(result, Exception):
            info: VideoInfo = result
            self._manager.add_task_from_info(
                info=info,
                format_id="best",
                format_type="combined",
                custom_name="",
                output_dir=self._download_dir,
            )
            self._batch_added += 1
        self._batch_index += 1
        self._start_batch_extract()

    def _finish_batch(self):
        self._parse_btn.setEnabled(True)
        self._parse_btn.setText(t("parse"))
        self._title_label.setText(t("batch_import_done", count=self._batch_added))
        self._url_input.clear()

    @Slot()
    def _on_add_to_queue(self):
        if not self._current_info:
            return

        # Dedup check
        if self._manager.check_url_duplicate(self._current_info.url):
            reply = QMessageBox.question(
                self, t("dup_title"), t("dup_message"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
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
        self._reset_preview()

    def _reset_preview(self):
        self._current_info = None
        self._download_btn.setEnabled(False)
        self._format_combo.clear()
        self._title_label.setText(t("paste_hint"))
        self._title_label.setObjectName("muted")
        self._title_label.style().unpolish(self._title_label)
        self._title_label.style().polish(self._title_label)
        self._thumb_label.clear()
        self._thumb_label.setText("")
        self._name_input.clear()
        self._url_input.clear()

    @Slot()
    def _on_reset(self):
        self._reset_preview()
        self._search_container.hide()
        self._thumb_label.show()
        self._search_query = ""
        self._search_page = 1

    # ---- Search ----

    @Slot()
    def _on_search(self):
        text = self._url_input.toPlainText().strip()
        if not text:
            return
        self._search_query = text
        self._search_page = 1
        self._thumb_label.hide()
        self._search_container.show()
        self._run_search()

    def _run_search(self):
        self._search_status.setText(t("search_loading"))
        self._search_btn.setEnabled(False)
        self._add_selected_btn.setEnabled(False)
        self._clear_results()

        # Disconnect old worker if still running
        if self._search_worker and self._search_worker.isRunning():
            try:
                self._search_worker.finished.disconnect()
            except RuntimeError:
                pass

        self._search_worker = _SearchWorker(
            self._search_query, self._search_page, self._search_limit
        )
        self._search_worker.finished.connect(self._on_search_done)
        self._search_worker.start()

    @Slot(object)
    def _on_search_done(self, result):
        self._search_btn.setEnabled(True)
        if isinstance(result, Exception):
            self._search_status.setText(t("search_error", err=str(result)))
            return

        data = result.get("data", [])
        self._search_total = result.get("total", 0)
        if not data:
            self._search_status.setText(t("search_empty"))
            return

        self._show_results(data)

    # ---- Search results display ----

    def _show_results(self, data: list[dict]):
        """Populate results list with video items."""
        from PySide6.QtWidgets import QCheckBox

        self._search_status.setText(
            t("search_results_count", count=self._search_total, query=self._search_query)
        )
        self._clear_results()

        for item in data:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(4, 4, 4, 4)
            row_layout.setSpacing(8)

            cb = QCheckBox()
            cb.stateChanged.connect(self._update_add_btn)
            row_layout.addWidget(cb)

            thumb = QLabel()
            thumb.setFixedSize(80, 50)
            thumb.setObjectName("search_thumb")
            thumb.setStyleSheet("background-color: #1a1c28; border-radius: 4px;")
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb.setText("...")
            row_layout.addWidget(thumb)

            info_col = QVBoxLayout()
            info_col.setSpacing(2)
            title_lbl = QLabel(item.get("content", "")[:80])
            title_lbl.setWordWrap(True)
            title_lbl.setStyleSheet("font-size: 12px;")
            info_col.addWidget(title_lbl)

            meta = QLabel(f"@{item.get('screen_name', '')}  •  {item.get('name', '')}")
            meta.setObjectName("muted")
            meta.setStyleSheet("font-size: 11px;")
            info_col.addWidget(meta)
            row_layout.addLayout(info_col, 1)

            # Preview button
            preview_btn = QPushButton(t("preview"))
            preview_btn.setFixedHeight(26)
            preview_btn.setMinimumWidth(44)
            preview_btn.setObjectName("secondary")
            preview_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            preview_btn.setToolTip(t("preview"))
            video_url = item.get("video_url", "")
            preview_btn.clicked.connect(lambda checked=False, url=video_url: self._preview_x_video(url))
            row_layout.addWidget(preview_btn)

            self._results_layout.insertWidget(self._results_layout.count() - 1, row_widget)
            self._result_rows.append({"checkbox": cb, "data": item, "thumb_label": thumb})

            cover_url = item.get("video_cover", "")
            if cover_url:
                self._load_search_thumb(cover_url, thumb)

        self._update_page_btns()

    def _load_search_thumb(self, url: str, label: QLabel):
        class _Loader(QThread):
            finished = Signal(bytes)

            def __init__(self, u):
                super().__init__()
                self._url = u

            def run(self):
                try:
                    from urllib.request import urlopen
                    data = urlopen(self._url, timeout=10).read()
                    self.finished.emit(data)
                except Exception:
                    self.finished.emit(b"")

        loader = _Loader(url)
        loader.finished.connect(lambda data, lbl=label: self._on_search_thumb(data, lbl))
        loader.start()
        # Keep reference to prevent GC
        if not hasattr(self, "_thumb_loaders"):
            self._thumb_loaders = []
        self._thumb_loaders.append(loader)

    @Slot(bytes)
    def _on_search_thumb(self, data: bytes, label: QLabel):
        if not data:
            return
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                80, 50,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            label.setPixmap(scaled)
            label.setStyleSheet("border-radius: 4px;")

    def _preview_x_video(self, video_url: str):
        """Open video preview dialog for an X-Sou search result."""
        if not video_url:
            return
        from .preview_dialog import VideoPreviewDialog
        dlg = VideoPreviewDialog(video_url, self)
        dlg.exec()

    def _clear_results(self):
        # Remove all result widgets except the stretch at the end
        while self._results_layout.count() > 1:
            item = self._results_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._result_rows.clear()

    def _update_add_btn(self):
        any_checked = any(r["checkbox"].isChecked() for r in self._result_rows)
        self._add_selected_btn.setEnabled(any_checked)

    def _update_page_btns(self):
        total_pages = max(1, (self._search_total + self._search_limit - 1) // self._search_limit)
        self._page_label.setText(f"{self._search_page}/{total_pages}")
        self._prev_page_btn.setEnabled(self._search_page > 1)
        self._next_page_btn.setEnabled(self._search_page < total_pages)

    @Slot()
    def _on_select_all(self):
        all_checked = all(r["checkbox"].isChecked() for r in self._result_rows)
        for r in self._result_rows:
            r["checkbox"].setChecked(not all_checked)

    @Slot()
    def _on_prev_page(self):
        if self._search_page > 1:
            self._search_page -= 1
            self._run_search()

    @Slot()
    def _on_next_page(self):
        total_pages = max(1, (self._search_total + self._search_limit - 1) // self._search_limit)
        if self._search_page < total_pages:
            self._search_page += 1
            self._run_search()

    @Slot()
    def _on_add_selected(self):
        import uuid
        from ..queue_manager import QueueTask

        selected = [r for r in self._result_rows if r["checkbox"].isChecked()]
        if not selected:
            return

        batch_id = uuid.uuid4().hex[:12]
        tasks = []
        for r in selected:
            item = r["data"]
            tweet_id = item.get("tweet_id", "")
            author = item.get("screen_name", "")
            x_url = f"https://x.com/{author}/status/{tweet_id}" if author and tweet_id else ""
            if not x_url:
                continue

            task = QueueTask(
                url=x_url,
                output_dir=str(self._download_dir),
                author=author,
                platform="x",
                batch_id=batch_id,
            )
            tasks.append(task)

        if tasks:
            for qt in tasks:
                self._manager.add_task(qt)
            self.search_batch_added.emit(len(tasks))

