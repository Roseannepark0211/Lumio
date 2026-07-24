"""收件箱页面 — 展示浏览器采集的内容，支持下载/归档/删除。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..i18n import t
from ..inbox_manager import InboxManager
from ..models import InboxItem
from ..queue_manager import DownloadManager, QueueTask
from ..utils.config import get_download_dir
from .theme.paint import GradientLabel


# ── 单条卡片 ────────────────────────────────────────────────────────

_STATUS_COLORS = {
    "new": "#4A9EFF",
    "queued": "#FFB84D",
    "downloaded": "#4ADE80",
    "archived": "#888888",
    "failed": "#FF6B6B",
}


class InboxItemWidget(QWidget):
    """收件箱中一条采集记录的卡片。"""

    action_requested = Signal(str, str)  # (item_id, action)

    def __init__(self, item: InboxItem, parent=None):
        super().__init__(parent)
        self.item = item
        self._net = QNetworkAccessManager(self)
        self._build_ui()
        self._load_thumbnail()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        # Checkbox
        self._cb = QCheckBox()
        self._cb.setFixedWidth(20)
        layout.addWidget(self._cb)

        # Thumbnail
        self._thumb = QLabel()
        self._thumb.setFixedSize(80, 60)
        self._thumb.setObjectName("search_thumb")
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._thumb)

        # Info column
        info = QVBoxLayout()
        info.setSpacing(2)

        full_title = self.item.title or self.item.url
        # title 截断从 80 收紧到 60，与 library/history 卡片对齐，避免文本过长挤压按钮
        short_title = full_title[:60] + "..." if len(full_title) > 60 else full_title
        self._title = QLabel(short_title)
        self._title.setWordWrap(True)
        # Ignored 水平 sizePolicy：title 不参与水平宽度请求，按钮先按 sizeHint 分配，
        # 剩余空间才给 title，从根本上避免 wordWrap 的 QLabel 挤压同行按钮
        from PySide6.QtWidgets import QSizePolicy
        self._title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._title.setObjectName("card_title")
        self._title.setToolTip(full_title)
        info.addWidget(self._title)

        meta_text = self.item.author or ""
        if self.item.platform:
            meta_text += f"  ·  {self.item.platform}" if meta_text else self.item.platform
        if getattr(self.item, "source", "") == "telegram":
            meta_text += "  ·  📱 Telegram"
        if self.item.captured_at:
            meta_text += f"  ·  {self.item.captured_at:%Y-%m-%d %H:%M}"
        self._meta = QLabel(meta_text)
        self._meta.setObjectName("card_meta")
        info.addWidget(self._meta)

        layout.addLayout(info, 1)

        # Status badge — 色值动态（按 status 切换），保留内联 color+border
        self._status_label = QLabel(self._status_text(self.item.status))
        color = _STATUS_COLORS.get(self.item.status, "#888")
        self._status_label.setStyleSheet(
            f"QLabel {{ color: {color}; border: 1px solid {color}; "
            f"border-radius: 4px; padding: 2px 8px; font-size: 11px; }}"
        )
        self._status_label.setFixedWidth(64)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_label)

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        # 按钮加 setMinimumWidth 防止被 wordWrap 的 title 挤压变形
        # 中文按钮文本（下载/打开链接/归档/删除）按最长项 72px 保守设置
        self._btn_download = QPushButton(t("inbox_download"))
        self._btn_download.setFixedHeight(28)
        self._btn_download.setMinimumWidth(64)
        self._btn_download.clicked.connect(lambda: self.action_requested.emit(self.item.id, "download"))
        btn_layout.addWidget(self._btn_download)

        self._btn_link = QPushButton(t("inbox_open_link"))
        self._btn_link.setFixedHeight(28)
        self._btn_link.setMinimumWidth(72)
        self._btn_link.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.item.url)))
        btn_layout.addWidget(self._btn_link)

        self._btn_archive = QPushButton(t("inbox_archive"))
        self._btn_archive.setFixedHeight(28)
        self._btn_archive.setMinimumWidth(56)
        self._btn_archive.clicked.connect(lambda: self.action_requested.emit(self.item.id, "archive"))
        btn_layout.addWidget(self._btn_archive)

        self._btn_del = QPushButton(t("inbox_delete"))
        self._btn_del.setFixedHeight(28)
        self._btn_del.setMinimumWidth(56)
        self._btn_del.clicked.connect(lambda: self.action_requested.emit(self.item.id, "delete"))
        btn_layout.addWidget(self._btn_del)

        layout.addLayout(btn_layout)

    def _load_thumbnail(self):
        url = self.item.thumbnail_url
        if not url or not url.startswith("http"):
            return
        request = QNetworkRequest(QUrl(url))
        # X/Twitter 缩略图需要 Referer
        if "twimg.com" in url or "x.com" in url:
            request.setRawHeader(b"Referer", b"https://x.com/")
        reply = self._net.get(request)
        reply.finished.connect(lambda r=reply: self._on_thumb(r))

    def _on_thumb(self, reply: QNetworkReply):
        if reply.error() == QNetworkReply.NetworkError.NoError:
            data = reply.readAll()
            pm = QPixmap()
            pm.loadFromData(data)
            if not pm.isNull():
                self._thumb.setPixmap(pm.scaled(
                    80, 60, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
        reply.deleteLater()

    def is_checked(self) -> bool:
        return self._cb.isChecked()

    def set_checked(self, v: bool):
        self._cb.setChecked(v)

    def update_status(self, status: str):
        self.item.status = status
        self._status_label.setText(self._status_text(status))
        color = _STATUS_COLORS.get(status, "#888")
        self._status_label.setStyleSheet(
            f"QLabel {{ color: {color}; border: 1px solid {color}; "
            f"border-radius: 4px; padding: 2px 8px; font-size: 11px; }}"
        )
        # 下载完成后禁用下载按钮
        if status in ("downloaded", "queued", "archived"):
            self._btn_download.setEnabled(False)

    @staticmethod
    def _status_text(status: str) -> str:
        return t(f"inbox_status_{status}") if t(f"inbox_status_{status}") != f"inbox_status_{status}" else status


# ── 主页面 ──────────────────────────────────────────────────────────

class InboxPage(QWidget):
    """收件箱页面 — 展示浏览器/Telegram 采集的内容。"""

    def __init__(self, inbox_manager: InboxManager, download_manager: DownloadManager, parent=None):
        super().__init__(parent)
        self._inbox = inbox_manager
        self._dm = download_manager
        self._widgets: dict[str, InboxItemWidget] = {}  # item_id → widget
        self._task_to_inbox: dict[str, str] = {}         # task_id → inbox_item_id
        self._build_ui()
        self._connect_signals()
        self.refresh()

    # ── UI ──────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # Header row
        header = QHBoxLayout()
        self._title_label = GradientLabel(t("inbox"), direction="vertical")
        self._title_label.setObjectName("page_title")
        header.addWidget(self._title_label)

        self._badge = QLabel("0")
        self._badge.setObjectName("history_badge")
        self._badge.setVisible(False)
        header.addWidget(self._badge)
        header.addStretch()

        self._filter = QComboBox()
        self._filter.setObjectName("history_filter")
        self._filter.addItems([
            t("inbox_status_new"),
            t("inbox_status_queued"),
            t("inbox_status_downloaded"),
            t("inbox_status_archived"),
            t("inbox_status_failed"),
        ])
        self._filter.currentIndexChanged.connect(self._apply_filter)
        header.addWidget(self._filter)
        root.addLayout(header)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._btn_refresh = QPushButton(t("inbox_refresh"))
        self._btn_refresh.clicked.connect(self.refresh)
        toolbar.addWidget(self._btn_refresh)

        self._btn_download_sel = QPushButton(t("inbox_download_selected"))
        self._btn_download_sel.clicked.connect(self._download_selected)
        toolbar.addWidget(self._btn_download_sel)

        self._btn_clear_done = QPushButton(t("inbox_clear_completed"))
        self._btn_clear_done.clicked.connect(self._clear_completed)
        toolbar.addWidget(self._btn_clear_done)

        self._btn_delete_sel = QPushButton(t("inbox_delete_selected"))
        self._btn_delete_sel.clicked.connect(self._delete_selected)
        toolbar.addWidget(self._btn_delete_sel)

        toolbar.addStretch()

        self._btn_select_all = QPushButton(t("select_all"))
        self._btn_select_all.clicked.connect(self._toggle_select_all)
        toolbar.addWidget(self._btn_select_all)

        root.addLayout(toolbar)

        # Scrollable list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("search_scroll")
        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_container)
        root.addWidget(scroll, 1)

        # Empty state — 使用 EmptyState 组件替代裸 QLabel
        from .widgets import EmptyState
        self._empty_state = EmptyState(
            icon="i-inbox",
            title=t("inbox_empty"),
            hint="",
        )
        self._empty_state.setObjectName("inbox_empty_state")
        self._empty_state.hide()
        root.addWidget(self._empty_state)

    def _connect_signals(self):
        self._inbox.item_added.connect(self._on_item_added)
        self._inbox.item_updated.connect(self._on_item_updated)
        self._inbox.items_deleted.connect(self._on_items_deleted)
        self._dm.task_finished.connect(self._on_task_finished)

    # ── 数据刷新 ────────────────────────────────────────────────────

    def refresh(self):
        self._apply_filter()

    def _rebuild_list(self, items: list[InboxItem]):
        # 清空
        for w in self._widgets.values():
            w.setParent(None)
            w.deleteLater()
        self._widgets.clear()

        for item in items:
            w = InboxItemWidget(item, self._list_container)
            w.action_requested.connect(self._on_action)
            self._list_layout.insertWidget(self._list_layout.count() - 1, w)
            self._widgets[item.id] = w

        self._badge.setText(str(len(items)))
        self._badge.setVisible(len(items) > 0)
        self._empty_state.setVisible(len(items) == 0)

    def _apply_filter(self):
        status_map = {
            0: "new",
            1: "queued",
            2: "downloaded",
            3: "archived",
            4: "failed",
        }
        status = status_map.get(self._filter.currentIndex(), "new")
        items = self._inbox.get_all(status_filter=status)
        self._rebuild_list(items)

    # ── 信号处理 ────────────────────────────────────────────────────

    @Slot(str)
    def _on_item_added(self, item_id: str):
        """API/Telegram 写入新记录时刷新当前筛选视图。"""
        self.refresh()

    @Slot(str)
    def _on_item_updated(self, item_id: str):
        w = self._widgets.get(item_id)
        if w:
            item = self._inbox.get_item(item_id)
            if item:
                w.update_status(item.status)

    @Slot(list)
    def _on_items_deleted(self, item_ids: list):
        for iid in item_ids:
            w = self._widgets.pop(iid, None)
            if w:
                w.setParent(None)
                w.deleteLater()
        self._badge.setText(str(len(self._widgets)))
        self._empty_state.setVisible(len(self._widgets) == 0)

    # ── 任务桥接 ────────────────────────────────────────────────────

    def _start_download_for_item(self, item_id: str):
        """批量下载：最高画质，不弹格式选择。

        分两条路径：
        1. 本地文件类型（Telegram 媒体 direct_url 是本地路径）→ add_task + direct_url 直链下载
        2. 页面 URL 类型（浏览器采集）→ extract_info + add_task_from_info（携带 media_items_json）
           国内平台（B站/抖音/快手/微博/小红书）必须携带 media_items_json 才能下载
        """
        item = self._inbox.get_item(item_id)
        if not item:
            return

        # 判断是否为直链类型（本地文件路径 或 HTTP URL）
        # 浏览器扩展提取的 IG/X CDN 直链是 HTTP URL，Telegram 媒体是本地文件路径
        direct_url = getattr(item, "direct_url", "") or ""
        is_direct = False
        if direct_url:
            if direct_url.startswith(("http://", "https://")):
                is_direct = True
            else:
                try:
                    from pathlib import Path
                    if Path(direct_url).exists():
                        is_direct = True
                except Exception:
                    pass

        # 路径 1：直链 → 直接下载（跳过 Provider 系统解析）
        if is_direct:
            custom = item.title if not item.author else ""
            if not custom and not item.author:
                custom = "download"
            qt = QueueTask(
                url=item.url,
                title=item.title,
                author=item.author,
                platform=item.platform or "auto",
                output_dir=str(get_download_dir()),
                thumbnail_url=item.thumbnail_url or "",
                direct_url=direct_url,
                custom_name=custom,
                post_time=getattr(item, "post_time", "") or "",
            )
            self._dm.add_task(qt)
            self._task_to_inbox[qt.task_id] = item_id
            self._dm.start_task(qt.task_id)
            self._inbox.mark_status(item_id, "queued")
            return

        # 路径 2：页面 URL → extract_info + add_task_from_info
        try:
            from ..downloader import extract_info
            info = extract_info(item.url)
        except Exception as e:
            self._inbox.mark_status(item_id, "failed", error_message=str(e))
            self._show_toast(f"{t('parse_failed')}: {e}")
            return

        if not info:
            self._inbox.mark_status(item_id, "failed", error_message="解析失败")
            return

        # 更新 inbox 元数据
        self._update_inbox_info(item_id, info)

        custom = info.title if not info.author else ""
        if not custom and not info.author:
            custom = "download"
        task_id = self._dm.add_task_from_info(
            info=info,
            format_id="best",
            format_type="",
            custom_name=custom,
            output_dir=str(get_download_dir()),
        )
        self._task_to_inbox[task_id] = item_id
        self._dm.start_task(task_id)
        self._inbox.mark_status(item_id, "queued")

    @Slot(str, bool, str)
    def _on_task_finished(self, task_id: str, success: bool, error: str):
        inbox_id = self._task_to_inbox.pop(task_id, None)
        if not inbox_id:
            return
        if success:
            self._inbox.mark_status(inbox_id, "downloaded")
        else:
            self._inbox.mark_status(inbox_id, "failed", error_message=error)

    # ── 操作 ────────────────────────────────────────────────────────

    @Slot(str, str)
    def _on_action(self, item_id: str, action: str):
        if action == "download":
            self._show_format_and_download(item_id)
        elif action == "archive":
            self._inbox.mark_status(item_id, "archived")
        elif action == "delete":
            self._inbox.delete_item(item_id)

    def _show_format_and_download(self, item_id: str):
        """单个下载：弹出格式选择框，选完再入队。

        分两条路径：
        1. 本地文件类型（Telegram 媒体）→ 直接直链下载，不弹格式选择
        2. 页面 URL 类型（浏览器采集）→ 弹 FormatSelectDialog（内部 extract_info）→
           用 add_task_from_info 入队（携带 media_items_json）
        """
        item = self._inbox.get_item(item_id)
        if not item:
            return

        # 判断是否为直链类型（本地文件路径 或 HTTP URL）
        # 浏览器扩展提取的 IG/X CDN 直链是 HTTP URL，Telegram 媒体是本地文件路径
        direct_url = getattr(item, "direct_url", "") or ""
        is_direct = False
        if direct_url:
            if direct_url.startswith(("http://", "https://")):
                is_direct = True
            else:
                try:
                    from pathlib import Path
                    if Path(direct_url).exists():
                        is_direct = True
                except Exception:
                    pass

        # 路径 1：直链 → 直接下载，不弹格式选择（跳过 Provider 系统解析）
        if is_direct:
            self._start_local_file_download(item_id, direct_url)
            return

        # 路径 2：页面 URL → 弹格式选择
        # 图片类型直接下载（无需格式选择），但仍需 extract_info 拿 media_items
        if self._is_image_item(item):
            self._start_url_download_best(item_id)
            return

        from .format_dialog import FormatSelectDialog
        dlg = FormatSelectDialog(item.url, self)
        if dlg.exec() == FormatSelectDialog.DialogCode.Accepted:
            result = dlg.get_result()
            info = dlg.get_info()
            fmt_id = result[0] if result else "best"
            fmt_type = result[1] if result else ""
            if info:
                self._update_inbox_info(item_id, info)
                self._start_url_download_with_format(item_id, info, fmt_id, fmt_type)
            else:
                QMessageBox.warning(self, t("error"), t("parse_failed"))

    def _start_local_file_download(self, item_id: str, direct_url: str):
        """本地文件类型下载（Telegram 媒体）。"""
        item = self._inbox.get_item(item_id)
        if not item:
            return
        custom = item.title if not item.author else ""
        if not custom and not item.author:
            custom = "download"
        qt = QueueTask(
            url=item.url,
            title=item.title,
            author=item.author,
            platform=item.platform or "auto",
            output_dir=str(get_download_dir()),
            thumbnail_url=item.thumbnail_url or "",
            direct_url=direct_url,
            custom_name=custom,
            post_time=getattr(item, "post_time", "") or "",
        )
        self._dm.add_task(qt)
        self._task_to_inbox[qt.task_id] = item_id
        self._dm.start_task(qt.task_id)
        self._inbox.mark_status(item_id, "queued")

    def _start_url_download_best(self, item_id: str):
        """页面 URL 类型 — 最高画质下载（图片/无需格式选择的场景）。

        内部调用 extract_info 拿到 media_items_json，再用 add_task_from_info 入队。
        """
        item = self._inbox.get_item(item_id)
        if not item:
            return
        try:
            from ..downloader import extract_info
            info = extract_info(item.url)
        except Exception as e:
            self._inbox.mark_status(item_id, "failed", error_message=str(e))
            QMessageBox.warning(self, t("error"), f"{t('parse_failed')}: {e}")
            return
        if not info:
            self._inbox.mark_status(item_id, "failed", error_message="解析失败")
            return
        self._update_inbox_info(item_id, info)
        self._start_url_download_with_format(item_id, info, "best", "")

    def _start_url_download_with_format(self, item_id: str, info, fmt_id: str, fmt_type: str):
        """页面 URL 类型 — 用指定格式 + media_items_json 入队下载。

        关键：使用 add_task_from_info 而非 add_task，确保 QueueTask 携带
        media_items_json，这样国内平台（B站/抖音/快手/微博/小红书）的
        _items_download_with_pause 才能正确下载。
        """
        item = self._inbox.get_item(item_id)
        if not item:
            return
        custom = info.title if not info.author else ""
        if not custom and not info.author:
            custom = "download"
        task_id = self._dm.add_task_from_info(
            info=info,
            format_id=fmt_id,
            format_type=fmt_type,
            custom_name=custom,
            output_dir=str(get_download_dir()),
        )
        self._task_to_inbox[task_id] = item_id
        self._dm.start_task(task_id)
        self._inbox.mark_status(item_id, "queued")

    def _is_image_item(self, item) -> bool:
        """判断是否为图片（不需要格式选择）。"""
        if item.type in ("image", "photo"):
            return True
        url = item.url.lower()
        return any(ext in url for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"))

    def _update_inbox_info(self, item_id: str, info):
        """用 extract_info 结果更新 InboxItem。"""
        self._inbox.update_item_info(
            item_id,
            title=info.title,
            author=info.author,
            thumbnail_url=info.thumbnail or "",
        )

    def _download_selected(self):
        to_download = []
        for iid, w in self._widgets.items():
            if w.is_checked() and w.item.status in ("new", "failed"):
                to_download.append(iid)
        for iid in to_download:
            self._start_download_for_item(iid)
        if to_download:
            self._show_toast(t("batch_added", n=len(to_download)))

    def _clear_completed(self):
        ids = [iid for iid, w in self._widgets.items() if w.item.status == "downloaded"]
        if ids:
            self._inbox.delete_items(ids)

    def _delete_selected(self):
        ids = [iid for iid, w in self._widgets.items() if w.is_checked()]
        if not ids:
            return
        reply = QMessageBox.question(
            self, t("inbox_delete"), t("inbox_confirm_delete", n=len(ids)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._inbox.delete_items(ids)

    def _toggle_select_all(self):
        all_checked = all(w.is_checked() for w in self._widgets.values())
        for w in self._widgets.values():
            w.set_checked(not all_checked)

    def _show_toast(self, msg: str):
        from PySide6.QtCore import QTimer
        toast = QLabel(msg, self)
        toast.setObjectName("toast")
        toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toast.setFixedHeight(36)
        toast.setMinimumWidth(200)
        toast.adjustSize()
        toast.move((self.width() - toast.width()) // 2, self.height() - 60)
        toast.show()
        QTimer.singleShot(2000, toast.deleteLater)
