from __future__ import annotations

import re
import uuid

from PySide6.QtCore import Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..downloader import VideoInfo, _build_format_options, extract_info
from ..x_sou_client import x_sou_search
from ..i18n import t
from ..queue_manager import DownloadManager, QueueTask
from ..utils.config import get_download_dir
from ..utils.url_parser import Platform, parse_url
from .widgets import NoWheelComboBox


# ========== Workers ==========

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


class _MediaItemCard(QFrame):
    """可点击的媒体预览卡片 — 点击卡片主体选中（在中间预览区显示），
    点击底部「加入下载队列」按钮才入队。"""

    # 点击卡片主体（非按钮区域）— 选中并显示到中间预览区
    selected = Signal(int)
    # 点击底部按钮 — 加入下载队列
    add_requested = Signal(int)

    def __init__(self, index: int, parent=None):
        super().__init__(parent)
        self._index = index
        self._added = False
        self._selected = False
        self.setObjectName("media_item_card")
        self.setFixedSize(160, 188)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        # 点击卡片任意空白区域都触发「选中」（入队由按钮自己处理）
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self._index)
        super().mousePressEvent(event)

    def set_selected(self, selected: bool):
        self._selected = selected
        self.setProperty("selected", "true" if selected else "")
        # 强制刷新样式
        self.style().unpolish(self)
        self.style().polish(self)

    def mark_added(self):
        self._added = True
        self.setProperty("added", True)
        # 按钮文字由调用方更新
        self.style().unpolish(self)
        self.style().polish(self)


# ========== Constants ==========

_PILL_COLORS = {
    "YouTube": "#FF0000",
    "Instagram": "#E1306C",
    "X": "#000000",
    "TikTok": "#25F4EE",
    "\u0042\u7ad9": "#00A1D6",
    "\u5feb\u624b": "#FF5000",
    "\u6296\u97f3": "#000000",
}

PLATFORM_PILLS = [
    ("YouTube", "\u25b6"),
    ("Instagram", "\u25c9"),
    ("X", "\U0001d54f"),
    ("TikTok", "\u266a"),
    ("\u0042\u7ad9", "B"),
    ("\u5feb\u624b", "\u25d6"),
    ("\u6296\u97f3", "\u266a"),
]

CAPABILITY_TAGS = ["MP4", "WEBM", "MP3", "4K", "1080P", "\u5b57\u5e55", "\u5c01\u9762"]

class HomePage(QWidget):
    request_batch_dialog = Signal(str, str, str)
    search_batch_added = Signal(int)

    def __init__(self, manager: DownloadManager, parent=None):
        super().__init__(parent)
        self.setObjectName("home_page")
        self._manager = manager
        self._current_info: VideoInfo | None = None
        self._download_dir = get_download_dir()
        self._search_query = ""
        self._search_page = 1
        self._search_total = 0
        self._search_limit = 15
        self._search_worker: _SearchWorker | None = None
        self._result_rows: list[dict] = []
        self._media_cards: list[_MediaItemCard] = []
        self._added_item_indices: set[int] = set()
        self._item_thumb_workers: list = []
        self._selected_item_index: int = -1
        self._best_audio_fmt_id: str = ""
        self._quality_url_map: dict[str, str] = {}
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ===== Scroll area wrapping everything =====
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("home_scroll")

        scroll_widget = QWidget()
        scroll_widget.setObjectName("home_scroll_widget")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(0)

        # ========== Hero ==========
        hero = QFrame()
        hero.setObjectName("home_hero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(48, 48, 48, 40)
        hero_layout.setSpacing(12)
        hero_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._hero_title = QLabel("Lumio")
        self._hero_title.setObjectName("hero_title")
        self._hero_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(self._hero_title)

        hero_sub = QLabel(t("hero_subtitle"))
        hero_sub.setObjectName("hero_subtitle")
        hero_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(hero_sub)

        pills_row = QHBoxLayout()
        pills_row.setSpacing(10)
        pills_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for name, icon in PLATFORM_PILLS:
            pill = QPushButton(f"  {icon}  {name}")
            pill.setObjectName("platform_pill")
            pill.setCursor(Qt.CursorShape.PointingHandCursor)
            color = _PILL_COLORS.get(name, "#666666")
            pill.setStyleSheet(
                f"QPushButton {{ border: 2px solid {color}; }} "
                f"QPushButton:hover {{ border-color: {color}; }}"
            )
            pills_row.addWidget(pill)
        hero_layout.addLayout(pills_row)
        scroll_layout.addWidget(hero)

        # ===== Content area (constrained) =====
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(48, 24, 48, 40)
        content_layout.setSpacing(24)

        # ========== Input Card ==========
        input_card = QFrame()
        input_card.setObjectName("input_card")
        card_layout = QVBoxLayout(input_card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(12)

        self._url_input = QPlainTextEdit()
        self._url_input.setObjectName("home_url_input")
        self._url_input.setPlaceholderText(t("url_placeholder"))
        self._url_input.setMinimumHeight(100)
        self._url_input.setMaximumHeight(160)
        card_layout.addWidget(self._url_input)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        hint = QLabel(t("url_input_hint"))
        hint.setObjectName("toolbar_hint")
        toolbar.addWidget(hint)

        toolbar.addStretch()

        clear_btn = QPushButton(t("clear"))
        clear_btn.setObjectName("tool_btn")
        clear_btn.clicked.connect(self._on_reset)
        toolbar.addWidget(clear_btn)

        paste_btn = QPushButton(t("paste"))
        paste_btn.setObjectName("paste_btn")
        paste_btn.clicked.connect(self._on_paste)
        toolbar.addWidget(paste_btn)

        self._search_btn = QPushButton(t("search"))
        self._search_btn.setObjectName("search_btn")
        self._search_btn.clicked.connect(self._on_search)
        toolbar.addWidget(self._search_btn)

        self._parse_btn = QPushButton(t("parse"))
        self._parse_btn.setObjectName("home_parse_btn")
        self._parse_btn.clicked.connect(self._on_parse)
        toolbar.addWidget(self._parse_btn)

        card_layout.addLayout(toolbar)
        content_layout.addWidget(input_card)

        # ========== Capability Tags ==========
        caps_row = QHBoxLayout()
        caps_row.setSpacing(8)
        caps_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for tag in CAPABILITY_TAGS:
            tag_lbl = QLabel(tag)
            tag_lbl.setObjectName("capability_tag")
            caps_row.addWidget(tag_lbl)
        caps_row.addStretch()
        content_layout.addLayout(caps_row)

        # ========== Preview Section ==========
        preview_header = QLabel(t("preview"))
        preview_header.setObjectName("section_header")
        content_layout.addWidget(preview_header)

        # Empty state
        self._preview_empty = QFrame()
        self._preview_empty.setObjectName("preview_empty")
        empty_layout = QVBoxLayout(self._preview_empty)
        empty_layout.setContentsMargins(0, 48, 0, 48)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setSpacing(12)

        empty_icon = QLabel("\U0001f3ac")
        empty_icon.setObjectName("preview_empty_icon")
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_icon)

        empty_hint = QLabel(t("paste_hint"))
        empty_hint.setObjectName("preview_empty_text")
        empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_hint)

        empty_sub = QLabel(t("preview_empty_hint"))
        empty_sub.setObjectName("preview_empty_text")
        empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_sub)
        content_layout.addWidget(self._preview_empty)

        # Filled state
        self._preview_filled = QWidget()
        self._preview_filled.hide()
        filled_layout = QVBoxLayout(self._preview_filled)
        filled_layout.setContentsMargins(0, 0, 0, 0)
        filled_layout.setSpacing(8)

        self._platform_badge = QLabel()
        filled_layout.addWidget(self._platform_badge)

        self._preview_title = QLabel()
        self._preview_title.setObjectName("preview_info_title")
        self._preview_title.setWordWrap(True)
        filled_layout.addWidget(self._preview_title)

        self._preview_meta = QLabel()
        self._preview_meta.setObjectName("preview_info_meta")
        filled_layout.addWidget(self._preview_meta)

        self._preview_thumb = QLabel()
        self._preview_thumb.setObjectName("preview_thumb")
        self._preview_thumb.setMinimumHeight(120)
        self._preview_thumb.setMaximumHeight(280)
        self._preview_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_thumb.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        filled_layout.addWidget(self._preview_thumb)

        # Media items preview strip (multi-item posts: videos + images)
        self._media_items_scroll = QScrollArea()
        self._media_items_scroll.setObjectName("media_items_scroll")
        self._media_items_scroll.setWidgetResizable(True)
        self._media_items_scroll.setFixedHeight(196)
        self._media_items_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._media_items_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._media_items_scroll.hide()
        self._media_items_container = QWidget()
        self._media_items_layout = QHBoxLayout(self._media_items_container)
        self._media_items_layout.setContentsMargins(6, 8, 6, 8)
        self._media_items_layout.setSpacing(10)
        self._media_items_layout.addStretch()
        self._media_items_scroll.setWidget(self._media_items_container)
        filled_layout.addWidget(self._media_items_scroll)
        content_layout.addWidget(self._preview_filled)

        # ========== Search Results Container ==========
        self._search_container = QWidget()
        self._search_container.hide()
        sc_layout = QVBoxLayout(self._search_container)
        sc_layout.setContentsMargins(0, 0, 0, 0)
        sc_layout.setSpacing(6)

        self._search_status = QLabel()
        self._search_status.setObjectName("preview_info_meta")
        sc_layout.addWidget(self._search_status)


        scroll2 = QScrollArea()
        scroll2.setWidgetResizable(True)
        scroll2.setMinimumHeight(200)
        scroll2.setMaximumHeight(400)
        scroll2.setObjectName("search_scroll")
        self._results_container = QWidget()
        self._results_layout = QVBoxLayout(self._results_container)
        self._results_layout.setContentsMargins(0, 0, 0, 0)
        self._results_layout.setSpacing(4)
        self._results_layout.addStretch()
        scroll2.setWidget(self._results_container)
        sc_layout.addWidget(scroll2, 1)

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
        self._page_label.setObjectName("preview_info_meta")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page_label.setFixedWidth(40)
        action_row.addWidget(self._page_label)

        self._next_page_btn = QPushButton(t("next_page"))
        self._next_page_btn.setObjectName("secondary")
        self._next_page_btn.setFixedHeight(26)
        self._next_page_btn.setMinimumWidth(50)
        self._next_page_btn.clicked.connect(self._on_next_page)
        self._next_page_btn.setEnabled(False)
        action_row.addWidget(self._next_page_btn)
        sc_layout.addLayout(action_row)
        content_layout.addWidget(self._search_container)

        # ========== Format & Download Section ==========
        fmt_header = QLabel(t("format_download"))
        fmt_header.setObjectName("section_header")
        content_layout.addWidget(fmt_header)

        format_row = QFrame()
        format_row.setObjectName("format_row")
        fr_layout = QHBoxLayout(format_row)
        fr_layout.setContentsMargins(20, 20, 20, 20)
        fr_layout.setSpacing(12)

        name_col = QVBoxLayout()
        name_col.setSpacing(6)
        name_lbl = QLabel(t("name_label"))
        name_lbl.setObjectName("preview_info_meta")
        name_col.addWidget(name_lbl)
        self._name_input = QLineEdit()
        self._name_input.setObjectName("home_name_input")
        self._name_input.setPlaceholderText(t("leave_empty"))
        name_col.addWidget(self._name_input)
        fr_layout.addLayout(name_col, 1)

        # 清晰度选择列（位于「名称」与「格式」之间）
        # 仅当存在视频格式档位时显示；图片/混合贴直链下载时隐藏
        self._quality_col = QFrame()
        qual_col = QVBoxLayout(self._quality_col)
        qual_col.setContentsMargins(0, 0, 0, 0)
        qual_col.setSpacing(6)
        self._quality_lbl = QLabel(t("quality_label"))
        self._quality_lbl.setObjectName("preview_info_meta")
        qual_col.addWidget(self._quality_lbl)
        self._quality_combo = NoWheelComboBox()
        self._quality_combo.setMinimumWidth(120)
        qual_col.addWidget(self._quality_combo)
        fr_layout.addWidget(self._quality_col)
        self._quality_col.hide()
        # 格式切换时联动启用/禁用清晰度（音频档位下禁用清晰度）
        self._format_combo = None  # 占位，下面立即赋值
        self._quality_combo.currentIndexChanged.connect(self._on_quality_changed)

        fmt_col = QVBoxLayout()
        fmt_col.setSpacing(6)
        fmt_lbl = QLabel(t("format_label"))
        fmt_lbl.setObjectName("preview_info_meta")
        fmt_col.addWidget(fmt_lbl)
        self._format_combo = NoWheelComboBox()
        self._format_combo.setMinimumWidth(140)
        fmt_col.addWidget(self._format_combo)
        fr_layout.addLayout(fmt_col)
        # 格式切换 → 联动清晰度可用性（选音频时禁用清晰度）
        self._format_combo.currentIndexChanged.connect(self._on_format_changed)

        self._download_btn = QPushButton(t("add_to_queue"))
        self._download_btn.setObjectName("home_download_btn")
        self._download_btn.setEnabled(False)
        self._download_btn.clicked.connect(self._on_add_to_queue)
        fr_layout.addWidget(self._download_btn, 0, Qt.AlignmentFlag.AlignBottom)

        content_layout.addWidget(format_row)

        # ===== Finish layout =====
        scroll_layout.addWidget(content)
        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        root.addWidget(scroll)


    # ========== Preview State Switching ==========

    def _show_preview_empty(self):
        self._preview_empty.show()
        self._preview_filled.hide()
        self._search_container.hide()

    def _show_preview_filled(self):
        self._preview_empty.hide()
        self._preview_filled.show()
        self._search_container.hide()

    def _show_preview_search(self):
        self._preview_empty.hide()
        self._preview_filled.hide()
        self._search_container.show()

    def _update_platform_badge(self, platform_str: str):
        color_map = {"youtube": "#FF0000", "instagram": "#E1306C", "x": "#000000"}
        color = color_map.get(platform_str.lower(), "#666666")
        label_map = {"youtube": "YouTube", "instagram": "Instagram", "x": "X"}
        label = label_map.get(platform_str.lower(), platform_str)
        self._platform_badge.setText(f"  {label}  ")
        self._platform_badge.setStyleSheet(
            "QLabel {{ background-color: transparent; color: {c}; "
            "border: 1px solid {c}; border-radius: 12px; "
            "padding: 2px 8px; font-size: 11px; font-weight: 600; }}".format(c=color)
        )

    # ========== Paste ==========

    @Slot()
    def _on_paste(self):
        clipboard = QApplication.clipboard()
        if clipboard:
            text = clipboard.text()
            if text:
                self._url_input.setPlainText(text)

    # ========== Parse ==========

    # 匹配分享文字中的 URL（含中文描述、emoji、提取码前后缀等场景）
    _URL_EXTRACT_RE = re.compile(r"https?://[^\s\u4e00-\u9fff\uff00-\uffef]+", re.IGNORECASE)

    def _extract_url_from_text(self, text: str) -> str:
        """从分享文字中提取纯 URL。

        小红书/微博等 App 分享时会把 URL 嵌在描述文字里，例如:
          "61 【✈️出差啦～💼 - 杨超越 | 小红书】 😆 Av8nz3 😆 https://..."
        直接 parse_url 会因为前缀描述识别失败，这里先抽 URL。
        如果没有 http(s):// 前缀（如 @username 或纯 ID），返回原文本。
        """
        # 多行时取第一行非空行处理
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = self._URL_EXTRACT_RE.search(line)
            if m:
                return m.group(0).rstrip(",.;!?，。；！？)】")
        # 没有 http(s):// 前缀（@username / 纯 URL 无协议 / ID）
        return text.strip()

    @Slot()
    def _on_parse(self):
        text = self._url_input.toPlainText().strip()
        if not text:
            return

        self._show_preview_empty()
        self._search_container.hide()

        lines = [line.strip() for line in text.splitlines() if line.strip()]

        if len(lines) > 1:
            self._batch_parse(lines)
            return

        first_line = lines[0]
        # 分享文字里可能含描述（如"61 【标题】 😆 提取码 😆 https://..."），
        # 先抽出纯 URL 再解析
        first_line = self._extract_url_from_text(first_line)
        parsed = parse_url(first_line)

        if parsed.platform == Platform.UNSUPPORTED:
            from ..providers.detector import detect_domestic as _dd
            domestic_result = _dd(first_line)
            if not domestic_result:
                QMessageBox.warning(
                    self, t("unsupported"), t("unsupported_msg") + first_line
                )
                return
            _dom_platform, _dom_kind = domestic_result
            if _dom_kind == "profile":
                identifier = ""
                for _pat in [
                    r"weibo\.com/(\d+)", r"m\.weibo\.cn/u/(\d+)",
                    r"xiaohongshu\.com/user/profile/([a-f0-9]+)",
                    r"bilibili\.com/space/(\d+)", r"space\.bilibili\.com/(\d+)",
                    r"douyin\.com/user/([\w.]+)",
                ]:
                    _m = re.search(_pat, first_line)
                    if _m:
                        identifier = _m.group(1)
                        break
                if not identifier:
                    identifier = first_line.rstrip("/").split("/")[-1]
                self.request_batch_dialog.emit(_dom_platform.value, identifier, "")
                return

        if parsed.platform == Platform.INSTAGRAM and parsed.kind == "profile":
            username = parsed.url.rstrip("/").split("/")[-1]
            self.request_batch_dialog.emit("instagram", username, "")
            return

        if parsed.platform == Platform.YOUTUBE and parsed.kind in ("channel", "playlist"):
            self.request_batch_dialog.emit("youtube", parsed.url, parsed.tab)
            return

        if parsed.platform == Platform.X and parsed.kind == "profile":
            username = parsed.url.rstrip("/").split("/")[-1]
            self.request_batch_dialog.emit("x", username, "")
            return

        self._parse_btn.setEnabled(False)
        self._parse_btn.setText("...")
        self._preview_title.setText(t("loading"))
        self._preview_thumb.setText("")

        if hasattr(self, "_extract_worker") and self._extract_worker:
            try:
                self._extract_worker.finished.disconnect()
            except RuntimeError:
                pass

        self._extract_worker = _ExtractWorker(parsed.url)
        self._extract_worker.finished.connect(self._on_extract_done)
        self._extract_worker.start()
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
            self._preview_title.setText(t("parse_failed"))
            self._show_preview_filled()
            QMessageBox.critical(self, t("parse_failed"), str(result))
            return

        info: VideoInfo = result
        # 合并多清晰度视频项：抖音等平台把每个清晰度当成独立 MediaItem，
        # 这里合并为1个最佳视频 + 清晰度下拉选择，避免横向列表出现多个视频
        self._merge_quality_video_items(info)
        self._current_info = info
        # _is_ig 仅对真正的 Instagram 混合贴生效（走 IG 专用格式分支）；
        # 抖音等 provider 架构的 info.items 也非空，但应走非 IG 分支显示清晰度选择
        self._is_ig = (info.platform or "").lower() == "instagram" and bool(info.items)

        dur = ""
        if info.duration:
            m, s = divmod(int(info.duration), 60)
            dur = f"  ({m}:{s:02d})"
        time_str = f"  [{info.post_time}]" if info.post_time else ""
        author_str = f"  @{info.author}" if info.author else ""
        self._preview_title.setText(f"{info.title}{dur}{time_str}{author_str}")

        self._preview_meta.setText(
            f"{info.platform or ''}  |  {info.author or ''}"
        )

        if info.platform:
            self._update_platform_badge(str(info.platform).lower())

        raw_name = info.author if info.author else info.title
        safe_name = raw_name[:60].strip()
        for ch in '\\/:*?"<>|':
            safe_name = safe_name.replace(ch, "_")
        self._name_input.setText(safe_name)

        if info.thumbnail:
            self._preview_thumb.setText(t("loading"))
            self._thumb_worker = _ThumbWorker(info.thumbnail)
            self._thumb_worker.finished.connect(self._on_thumb_loaded)
            self._thumb_worker.start()
        else:
            self._preview_thumb.setText(t("no_thumbnail"))

        self._format_combo.clear()
        self._quality_combo.clear()
        self._best_audio_fmt_id = ""

        # 拆分 _build_format_options 结果：best / 视频档位 / 音频档位
        # 清晰度档位填入 _quality_combo；格式类型填入 _format_combo
        video_opts: list[dict] = []
        audio_opts: list[dict] = []
        has_best = False
        if info.formats:
            for opt in _build_format_options(info):
                if opt.get("disabled"):
                    continue
                fid = opt.get("id", "")
                ftype = opt.get("_type", "")
                if fid == "best":
                    has_best = True
                elif ftype == "audio":
                    audio_opts.append(opt)
                else:
                    # combined / video → 视频清晰度档位
                    video_opts.append(opt)
            # 记录最佳音频档位（供「音频」格式使用）
            if audio_opts:
                self._best_audio_fmt_id = audio_opts[0]["id"]

        if self._is_ig:
            n_img = sum(1 for it in info.items if not it.is_video)
            n_vid = sum(1 for it in info.items if it.is_video)
            # 混合贴（视频+图片）→ 格式：全部 / 仅视频 / 仅图片；清晰度不适用
            if n_vid and n_img:
                vid_label = t("videos", n=n_vid)
                img_label = t("images", n=n_img)
                self._format_combo.addItem(
                    t("all_items", video=vid_label, image=img_label),
                    ("all", ""),
                )
                self._format_combo.addItem(
                    t("videos_only", n=n_vid),
                    ("videos", ""),
                )
                self._format_combo.addItem(
                    t("images_only", n=n_img),
                    ("images", ""),
                )
                self._format_combo.setEnabled(True)
                self._quality_col.hide()
            elif n_vid and not n_img:
                # 纯视频帖 — 有清晰度档位则显示清晰度选择，格式固定为「视频」
                if video_opts or has_best:
                    self._populate_quality_combo(has_best, video_opts)
                    self._quality_col.show()
                    self._quality_combo.setEnabled(True)
                    self._format_combo.addItem(t("fmt_video"), ("video", ""))
                    self._format_combo.setEnabled(False)
                else:
                    self._format_combo.addItem(t("videos_only", n=n_vid), ("videos", ""))
                    self._format_combo.setEnabled(False)
                    self._quality_col.hide()
            elif n_img and not n_vid:
                self._format_combo.addItem(t("all_images", n=n_img), ("images", ""))
                self._format_combo.setEnabled(False)
                self._quality_col.hide()
            else:
                self._format_combo.addItem(t("add_to_queue"), ("all", ""))
                self._format_combo.setEnabled(False)
                self._quality_col.hide()
        else:
            # 非 IG（YouTube / X 等）— 清晰度与格式分离
            if video_opts or has_best:
                self._populate_quality_combo(has_best, video_opts)
                self._quality_col.show()
                self._quality_combo.setEnabled(True)
                if audio_opts:
                    self._format_combo.addItem(t("fmt_video"), ("video", ""))
                    self._format_combo.addItem(t("fmt_audio"), ("audio", ""))
                    self._format_combo.setEnabled(True)
                else:
                    self._format_combo.addItem(t("fmt_video"), ("video", ""))
                    self._format_combo.setEnabled(False)
            elif audio_opts:
                self._format_combo.addItem(t("fmt_audio"), ("audio", ""))
                self._format_combo.setEnabled(False)
                self._quality_col.hide()
            else:
                self._format_combo.addItem(t("add_to_queue"), ("all", ""))
                self._format_combo.setEnabled(False)
                self._quality_col.hide()

        self._download_btn.setEnabled(True)
        # 多内容帖子用「全部加入队列」，单条用「加入下载队列」
        if info.items:
            self._download_btn.setText(t("add_all_to_queue"))
        else:
            self._download_btn.setText(t("add_to_queue"))

        # Populate media items preview strip (videos first, images below)
        self._build_media_items_preview(info)
        if info.items:
            self._media_items_scroll.show()
        else:
            self._media_items_scroll.hide()

        self._show_preview_filled()

    @Slot(bytes)
    def _on_thumb_loaded(self, data: bytes):
        if data:
            pix = QPixmap()
            pix.loadFromData(data)
            target_h = min(276, max(120, int(pix.height() * 0.6)))
            self._preview_thumb.setPixmap(
                pix.scaledToHeight(target_h, Qt.TransformationMode.SmoothTransformation)
            )
        else:
            self._preview_thumb.setText(t("thumbnail_unavail"))


    # ========== Batch Parse ==========

    def _batch_parse(self, urls: list[str]):
        valid = []
        invalid = []
        for url in urls:
            parsed = parse_url(url)
            if parsed.platform == Platform.UNSUPPORTED:
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
        self._preview_title.setText(t("batch_processing", current=1, total=len(valid)))
        self._show_preview_filled()
        self._start_batch_extract()

    def _start_batch_extract(self):
        if self._batch_index >= len(self._batch_urls):
            self._finish_batch()
            return
        url = self._batch_urls[self._batch_index]
        self._preview_title.setText(
            t("batch_processing", current=self._batch_index + 1, total=len(self._batch_urls))
        )
        self._extract_worker = _ExtractWorker(url)
        self._extract_worker.finished.connect(self._on_batch_extract_done)
        self._extract_worker.start()

    @Slot(object)
    def _on_batch_extract_done(self, result):
        if not isinstance(result, Exception):
            info: VideoInfo = result
            self._manager.add_task_from_info(
                info=info, format_id="best", format_type="combined",
                custom_name="", output_dir=self._download_dir,
            )
            self._batch_added += 1
        self._batch_index += 1
        self._start_batch_extract()

    def _finish_batch(self):
        self._parse_btn.setEnabled(True)
        self._parse_btn.setText(t("parse"))
        self._preview_title.setText(t("batch_import_done", count=self._batch_added))
        self._url_input.clear()

    # ========== Add to Queue ==========

    @Slot()
    def _on_add_to_queue(self):
        if not self._current_info:
            return

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

        # 格式为「视频」时，从清晰度下拉取实际档位 (format_id, format_type)
        # 格式为「音频」时，使用预先记录的最佳音频档位
        if fmt_id == "video":
            q_data = self._quality_combo.currentData()
            if isinstance(q_data, tuple):
                fmt_id, fmt_type = q_data
            else:
                fmt_id, fmt_type = q_data or "best", "combined"
        elif fmt_id == "audio":
            fmt_id = self._best_audio_fmt_id or "best"
            fmt_type = "audio"

        custom = self._name_input.text().strip()

        # 如果选了特定清晰度（非 best），从 _quality_url_map 取对应 URL 替换视频项
        # 这样下载器拿到的 media_items 就是选中清晰度的 URL
        selected_quality_url = ""
        if fmt_id != "best" and self._quality_url_map:
            selected_quality_url = self._quality_url_map.get(fmt_id, "")

        # 对于混合贴的「仅视频」/「仅图片」选项，过滤 info.items
        info_to_queue = self._current_info
        if self._is_ig and fmt_id in ("videos", "images"):
            from ..utils.media_utils import VideoInfo as _VI
            want_video = (fmt_id == "videos")
            filtered_items = [
                it for it in self._current_info.items
                if it.is_video == want_video
            ]
            if filtered_items and len(filtered_items) < len(self._current_info.items):
                # 创建过滤后的 VideoInfo 副本（重新索引）
                reindexed = []
                for i, it in enumerate(filtered_items):
                    from ..utils.media_utils import MediaItem as _MI
                    reindexed.append(_MI(
                        url=it.url, is_video=it.is_video, index=i,
                        media_type=getattr(it, "media_type", ""),
                        width=getattr(it, "width", 0),
                        height=getattr(it, "height", 0),
                        extension=getattr(it, "extension", ""),
                        size=getattr(it, "size", 0),
                        quality=getattr(it, "quality", ""),
                        mime=getattr(it, "mime", ""),
                        id=getattr(it, "id", ""),
                        filename=getattr(it, "filename", ""),
                        live_photo=getattr(it, "live_photo", None),
                        original_url=getattr(it, "original_url", ""),
                    ))
                info_to_queue = _VI(
                    title=self._current_info.title,
                    url=self._current_info.url,
                    thumbnail=self._current_info.thumbnail,
                    duration=self._current_info.duration,
                    formats=self._current_info.formats,
                    platform=self._current_info.platform,
                    author=self._current_info.author,
                    items=reindexed,
                    post_time=self._current_info.post_time,
                )
            # 过滤后 fmt_id 重置为 "all"（下载器不需要再过滤）
            fmt_id = "all"
            fmt_type = ""

        # 选了特定清晰度时，替换视频项的 URL 为选中清晰度的直链
        if selected_quality_url:
            for it in info_to_queue.items:
                if it.is_video:
                    it.url = selected_quality_url

        self._manager.add_task_from_info(
            info=info_to_queue, format_id=fmt_id,
            format_type=fmt_type, custom_name=custom,
            output_dir=self._download_dir,
        )
        self._reset_preview()

    # ========== Reset ==========

    def _build_media_items_preview(self, info):
        self._clear_media_items_preview()
        if not info.items:
            return
        # 保留原索引用于下载定位；显示时视频在前、再按原顺序排图片
        indexed_items = list(enumerate(info.items))
        indexed_items.sort(key=lambda pair: (0 if pair[1].is_video else 1, pair[0]))
        total = len(indexed_items)

        for display_pos, (orig_idx, it) in enumerate(indexed_items):
            card = _MediaItemCard(orig_idx)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 8, 8, 8)
            card_layout.setSpacing(4)

            thumb_label = QLabel()
            thumb_label.setObjectName("media_item_thumb")
            thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb_label.setFixedSize(144, 104)
            if it.is_video:
                thumb_label.setText(chr(0x1f3ac))
            else:
                thumb_label.setText("...")
                self._load_item_thumbnail(it.url, thumb_label)

            type_text = t("media_item_video") if it.is_video else t("media_item_image")
            type_label = QLabel(
                t("media_item_label", type=type_text, n=display_pos + 1, total=total)
            )
            type_label.setObjectName("media_item_type_label")
            type_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # 底部「加入下载队列」按钮（作用域只在按钮上）
            add_btn = QPushButton(t("add_to_queue"))
            add_btn.setObjectName("media_item_add_btn")
            add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            # 关键：按钮点击事件不要冒泡到卡片的 mousePressEvent
            add_btn.clicked.connect(
                lambda _checked=False, idx=orig_idx: self._add_single_item_to_queue(idx)
            )

            card_layout.addWidget(thumb_label)
            card_layout.addWidget(type_label)
            card_layout.addWidget(add_btn)

            card._add_btn = add_btn

            # 点击卡片主体（非按钮）— 选中并显示到中间预览区
            card.selected.connect(self._on_card_selected)
            # 按钮入队信号（备用，当前直接在按钮 clicked 里处理）
            card.add_requested.connect(self._add_single_item_to_queue)

            self._media_items_layout.insertWidget(
                self._media_items_layout.count() - 1, card
            )
            self._media_cards.append(card)

        # 默认选中第一个，让中间预览区有内容
        if self._media_cards:
            first_idx = self._media_cards[0]._index
            self._on_card_selected(first_idx)

    def _clear_media_items_preview(self):
        # 停止缩略图加载线程
        for w in self._item_thumb_workers:
            try:
                if w.isRunning():
                    w.wait(500)
            except Exception:
                pass
        self._item_thumb_workers.clear()
        self._media_cards.clear()
        self._added_item_indices.clear()
        while self._media_items_layout.count() > 1:
            item = self._media_items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _load_item_thumbnail(self, url: str, label: QLabel):
        worker = _ThumbWorker(url)
        worker.finished.connect(
            lambda data, lbl=label: self._on_item_thumb_loaded(data, lbl)
        )
        worker.start()
        self._item_thumb_workers.append(worker)

    @Slot(bytes, object)
    def _on_item_thumb_loaded(self, data: bytes, label: QLabel):
        if not data:
            label.setText(chr(0x1f5bc))
            return
        pix = QPixmap()
        pix.loadFromData(data)
        if pix.isNull():
            label.setText(chr(0x1f5bc))
            return
        scaled = pix.scaled(
            144, 104, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        label.setPixmap(scaled)

    def _add_single_item_to_queue(self, item_index: int):
        """单击预览卡片 — 将该项单独加入下载队列（走 direct_url 直链下载）。"""
        if not self._current_info:
            return
        if item_index < 0 or item_index >= len(self._current_info.items):
            return
        if item_index in self._added_item_indices:
            return
        item = self._current_info.items[item_index]

        # 自定义名称加序号后缀，避免多图/多视频文件名冲突
        custom = self._name_input.text().strip()
        if custom:
            custom = f"{custom}_{item_index + 1}"

        qt = QueueTask(
            url=self._current_info.url,
            direct_url=item.url,
            output_dir=str(self._download_dir),
            custom_name=custom,
            title=self._current_info.title,
            platform=self._current_info.platform,
            author=self._current_info.author,
            post_time=self._current_info.post_time,
            thumbnail_url=self._current_info.thumbnail,
            format_id=None,
            format_type="",
        )
        self._manager.add_task(qt)
        self._added_item_indices.add(item_index)

        # 标记卡片为已加入（按钮文字改为「已加入」并禁用）
        for card in self._media_cards:
            if card._index == item_index:
                card.mark_added()
                if hasattr(card, "_add_btn"):
                    card._add_btn.setText(t("item_added"))
                    card._add_btn.setEnabled(False)
                break

    def _on_card_selected(self, item_index: int):
        """点击卡片主体 — 选中该项并显示到中间预览区。

        把选中项的大图/视频标识显示在 _preview_thumb，更新 meta 信息。
        不会触发入队，入队只能点按钮。
        """
        if not self._current_info:
            return
        if item_index < 0 or item_index >= len(self._current_info.items):
            return

        # 更新卡片选中状态
        for card in self._media_cards:
            card.set_selected(card._index == item_index)
        self._selected_item_index = item_index

        item = self._current_info.items[item_index]

        # 中间预览区显示选中项的大图
        self._preview_thumb.clear()
        if item.is_video:
            self._preview_thumb.setText(chr(0x1f3ac) + "  " + t("media_item_video"))
        else:
            # 加载大图到中间预览区
            self._preview_thumb.setText(t("loading"))
            self._load_main_preview_image(item.url)

        # 更新 meta：显示选中项序号/类型
        type_text = t("media_item_video") if item.is_video else t("media_item_image")
        total = len(self._current_info.items)
        self._preview_meta.setText(
            f"{type_text}  {item_index + 1}/{total}"
        )

    def _load_main_preview_image(self, url: str):
        """加载图片 URL 到中间预览区（大图，区别于缩略图条的小图）。"""
        worker = _ThumbWorker(url)
        worker.finished.connect(self._on_main_preview_image_loaded)
        worker.start()
        # 复用缩略图 worker 列表管理生命周期
        self._item_thumb_workers.append(worker)

    @Slot(bytes)
    def _on_main_preview_image_loaded(self, data: bytes):
        if not data:
            self._preview_thumb.setText(chr(0x1f5bc))
            return
        pix = QPixmap()
        pix.loadFromData(data)
        if pix.isNull():
            self._preview_thumb.setText(chr(0x1f5bc))
            return
        target_h = min(276, max(120, int(pix.height() * 0.6)))
        self._preview_thumb.setPixmap(
            pix.scaledToHeight(target_h, Qt.TransformationMode.SmoothTransformation)
        )

    def _reset_preview(self):
        self._current_info = None
        self._download_btn.setEnabled(False)
        self._download_btn.setText(t("add_to_queue"))
        self._format_combo.clear()
        self._quality_combo.clear()
        self._quality_col.hide()
        self._best_audio_fmt_id = ""
        self._quality_url_map = {}
        self._preview_title.setText(t("paste_hint"))
        self._preview_meta.setText("")
        self._preview_thumb.clear()
        self._preview_thumb.setText("")
        self._clear_media_items_preview()
        self._media_items_scroll.hide()
        self._name_input.clear()
        self._url_input.clear()
        self._platform_badge.clear()
        self._show_preview_empty()

    # ========== Quality / Format Combos ==========

    def _merge_quality_video_items(self, info: VideoInfo):
        """合并同一视频的多个清晰度档位。

        抖音等平台把每个清晰度当成独立 MediaItem（5个清晰度 = 5个视频项），
        导致横向列表出现多个视频卡片且无法显示清晰度选择。

        本方法检测这种情况后：
        - 保留最佳清晰度（第一个）的视频项作为可下载项
        - 把所有清晰度档位转为 formats（供清晰度下拉显示）
        - 保存 quality→url 映射，供下载时根据选中清晰度替换 URL
        """
        self._quality_url_map = {}
        if not info.items:
            return

        video_items = [it for it in info.items if it.is_video]
        # 封面图（quality=="cover"）已在 info.thumbnail 里，不作为独立媒体项
        non_video_items = [
            it for it in info.items
            if not it.is_video and it.quality != "cover"
        ]

        # 仅当多个视频项且带有 quality 标签时才合并
        if len(video_items) <= 1:
            return
        qualities = [it.quality for it in video_items if it.quality]
        if len(qualities) < len(video_items):
            return

        # 保存 quality → url 映射（供下载时替换）
        for it in video_items:
            self._quality_url_map[it.quality] = it.url

        # 保留最佳清晰度（第一个，抖音按分辨率降序排列）
        best_video = video_items[0]

        # 如果 info.formats 为空，从 media_items 构建 formats
        if not info.formats:
            from ..providers.base import FormatOption as _FO
            info.formats = [
                _FO(
                    format_id=it.quality,
                    label=it.quality,
                    type="video",
                    ext=it.extension or "mp4",
                    width=it.width,
                    height=it.height,
                )
                for it in video_items
            ]

        # 重建 items：最佳视频 + 非视频项（封面等）
        new_items = [best_video] + non_video_items
        for i, it in enumerate(new_items):
            it.index = i
        info.items = new_items

    def _populate_quality_combo(self, has_best: bool, video_opts: list[dict]):
        """填充清晰度下拉：Best Quality + 各分辨率档位。"""
        self._quality_combo.clear()
        if has_best:
            self._quality_combo.addItem("Best Quality", ("best", "combined"))
        for opt in video_opts:
            self._quality_combo.addItem(opt["label"], (opt["id"], opt.get("_type", "")))
        # 默认选第一项（最高优先档位）

    @Slot(int)
    def _on_quality_changed(self, _index: int):
        """清晰度切换 — 当前仅用于未来扩展（如刷新预览）。"""
        pass

    @Slot(int)
    def _on_format_changed(self, _index: int):
        """格式切换 — 选「音频」时禁用清晰度下拉；选「视频」时恢复。"""
        fmt_data = self._format_combo.currentData()
        if isinstance(fmt_data, tuple):
            fmt_id = fmt_data[0]
        else:
            fmt_id = fmt_data
        if fmt_id == "audio":
            self._quality_combo.setEnabled(False)
        elif fmt_id == "video":
            self._quality_combo.setEnabled(True)

    @Slot()
    def _on_reset(self):
        self._reset_preview()
        self._search_query = ""
        self._search_page = 1


    # ========== Search ==========

    @Slot()
    def _on_search(self):
        text = self._url_input.toPlainText().strip()
        if not text:
            return
        self._search_query = text
        self._search_page = 1
        self._show_preview_search()
        self._run_search()

    def _run_search(self):
        self._search_status.setText(t("search_loading"))
        self._search_btn.setEnabled(False)
        self._add_selected_btn.setEnabled(False)
        self._clear_results()

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

    # ========== Search Results Display ==========

    def _show_results(self, data: list[dict]):
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
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb.setText("...")
            row_layout.addWidget(thumb)

            info_col = QVBoxLayout()
            info_col.setSpacing(2)
            title_lbl = QLabel(item.get("content", "")[:80])
            title_lbl.setWordWrap(True)
            title_lbl.setStyleSheet(
                "font-size: 12px; color: inherit; background: transparent;"
            )
            info_col.addWidget(title_lbl)

            meta = QLabel(
                f"@{item.get('screen_name', '')}  \u2022  {item.get('name', '')}"
            )
            meta.setObjectName("preview_info_meta")
            info_col.addWidget(meta)
            row_layout.addLayout(info_col, 1)

            preview_btn = QPushButton(t("preview"))
            preview_btn.setFixedHeight(26)
            preview_btn.setMinimumWidth(44)
            preview_btn.setObjectName("secondary")
            preview_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            preview_btn.setToolTip(t("preview"))
            # X-Sou video_url 可用于流式预览（VideoPreviewDialog 支持 URL 播放）
            video_url = item.get("video_url", "")
            if video_url:
                preview_btn.setEnabled(True)
                preview_btn.clicked.connect(
                    lambda checked, v=video_url: self._preview_x_video(v)
                )
            else:
                preview_btn.setEnabled(False)
                preview_btn.setToolTip(t("video_not_available"))
            row_layout.addWidget(preview_btn)

            self._results_layout.insertWidget(
                self._results_layout.count() - 1, row_widget
            )
            self._result_rows.append(
                {"checkbox": cb, "data": item, "thumb_label": thumb}
            )

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
        loader.finished.connect(
            lambda data, lbl=label: self._on_search_thumb(data, lbl)
        )
        loader.start()
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
                80, 50, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            label.setPixmap(scaled)


    def _preview_x_video(self, video_url: str):
        if not video_url:
            return
        # X-Sou 直链 (video.twimg.com) 需要鉴权头，Qt 内置播放器无法发送，
        # 直接流式播放会触发 TLS 握手失败；改为提示用户走下载队列后本地预览
        QMessageBox.information(self, t("preview"), t("x_sou_preview_unsupported"))

    def _clear_results(self):
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
        total_pages = max(
            1, (self._search_total + self._search_limit - 1) // self._search_limit
        )
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
        total_pages = max(
            1, (self._search_total + self._search_limit - 1) // self._search_limit
        )
        if self._search_page < total_pages:
            self._search_page += 1
            self._run_search()

    @Slot()
    def _on_add_selected(self):
        selected = [r for r in self._result_rows if r["checkbox"].isChecked()]
        if not selected:
            return

        batch_id = uuid.uuid4().hex[:12]
        tasks = []
        for r in selected:
            item = r["data"]
            tweet_id = item.get("tweet_id", "")
            author = item.get("screen_name", "")
            x_url = (
                f"https://x.com/{author}/status/{tweet_id}"
                if author and tweet_id else ""
            )
            if not x_url:
                continue

            task = QueueTask(
                url=x_url, output_dir=str(self._download_dir),
                author=author, platform="x", batch_id=batch_id,
                title=item.get("content", ""),
                format_id=None, format_type="",
            )
            tasks.append(task)

        if tasks:
            for qt in tasks:
                self._manager.add_task(qt)
            self.search_batch_added.emit(len(tasks))
