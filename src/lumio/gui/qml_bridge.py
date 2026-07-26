"""Lumio QML UI 桥接层

将 Python 后端（DownloadManager / InboxManager / LibraryManager / HistoryManager /
NotificationManager）暴露给 QML UI。

所有 QML 端调用通过 QmlController 暴露。耗时操作（解析 URL）走后台线程，
通过信号回传结果给 QML。
"""
from __future__ import annotations

import json
import logging
import re
import sys
import threading
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot, QUrl, Qt, QSize, QThread, Property
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtQuick import QQuickImageProvider

from ..i18n import t, get_lang, set_lang
from ..utils.config import load_config, save_config

logger = logging.getLogger(__name__)

_ICONS_SVG_PATH = Path(__file__).parent.parent / "qml" / "Lumio" / "Assets" / "icons.svg"


# ============================================================
# IconProvider — SVG <symbol> 渲染器
# ============================================================

class IconProvider(QQuickImageProvider):
    """单文件 SVG <symbol> → QImage 渲染器。

    QML 调用形如：`"image://icons/i-home?color=%23ffffff&size=20"`
    """

    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.Image)
        self._symbols: dict[str, str] = {}
        self._load_symbols()

    def _load_symbols(self) -> None:
        if not _ICONS_SVG_PATH.exists():
            print(f"[IconProvider] icons.svg not found: {_ICONS_SVG_PATH}", file=sys.stderr)
            return
        xml = _ICONS_SVG_PATH.read_text(encoding="utf-8")
        import re
        pattern = re.compile(
            r'<symbol\s+id="([^"]+)"[^>]*>(.*?)</symbol>',
            re.DOTALL,
        )
        for match in pattern.finditer(xml):
            sid = match.group(1)
            inner = match.group(2)
            self._symbols[sid] = inner

    def requestImage(self, id: str, size: QSize, requestedSize: QSize) -> QImage:
        color_hex = "#ffffff"
        icon_size = 24
        icon_id = id

        if "?" in id:
            icon_id, query = id.split("?", 1)
            for kv in query.split("&"):
                if "=" not in kv:
                    continue
                k, v = kv.split("=", 1)
                if k == "color":
                    from urllib.parse import unquote
                    color_hex = unquote(v)
                elif k == "size":
                    try:
                        icon_size = int(v)
                    except ValueError:
                        pass

        if requestedSize.width() > 0:
            icon_size = requestedSize.width()

        inner = self._symbols.get(icon_id)
        if inner is None:
            img = QImage(icon_size, icon_size, QImage.Format_ARGB32)
            img.fill(Qt.transparent)  # type: ignore[name-defined]
            size.setWidth(icon_size)
            size.setHeight(icon_size)
            return img

        inner_colored = inner.replace("currentColor", color_hex)
        svg_xml = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 24 24" width="{icon_size}" height="{icon_size}">'
            f'{inner_colored}'
            f'</svg>'
        )

        renderer = QSvgRenderer(svg_xml.encode("utf-8"))
        if not renderer.isValid():
            img = QImage(icon_size, icon_size, QImage.Format_ARGB32)
            img.fill(0)
            size.setWidth(icon_size)
            size.setHeight(icon_size)
            return img

        img = QImage(icon_size, icon_size, QImage.Format_ARGB32)
        img.fill(0)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing, True)
        renderer.render(painter)
        painter.end()

        size.setWidth(icon_size)
        size.setHeight(icon_size)
        return img


# ============================================================
# ThumbnailProvider — 远程缩略图代理（带 Referer + 本地缓存）
# ============================================================

class ThumbnailProvider(QQuickImageProvider):
    """QML 调用形如：`image://thumb/<base64(url)>`

    用途：IG/sinaimg 等 CDN 需要 Referer/Cookie 才能访问，QML Image 无法加 header。
    此 provider 在 Python 端下载并缓存到 ~/.lumio/cache/thumbs/，返回 QImage。
    """

    _NEEDS_REFERER_DOMAINS = (
        "instagram.", "fbcdn.net", "sinaimg.cn", "twimg.com", "x.com",
    )

    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.Image)
        self._cache_dir = Path.home() / ".lumio" / "cache" / "thumbs_proxy"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _referer_for(self, url: str) -> str:
        for d in self._NEEDS_REFERER_DOMAINS:
            if d in url:
                if "instagram" in d or "fbcdn" in d:
                    return "https://www.instagram.com/"
                if "sinaimg" in d:
                    return "https://weibo.com/"
                if "twimg" in d or "x.com" in d:
                    return "https://x.com/"
        return ""

    def requestImage(self, id: str, size: QSize, requestedSize: QSize) -> QImage:
        import base64 as _b64
        import hashlib
        import requests

        try:
            url = _b64.urlsafe_b64decode(id.encode("ascii")).decode("utf-8")
        except Exception:
            url = id

        # URL hash 作为缓存文件名
        url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
        cached = self._cache_dir / f"{url_hash}.jpg"

        # 缓存命中直接返回
        if not cached.exists():
            headers = {"User-Agent": "Mozilla/5.0 Lumio/4.2"}
            ref = self._referer_for(url)
            if ref:
                headers["Referer"] = ref
            try:
                resp = requests.get(url, headers=headers, timeout=8, stream=True)
                resp.raise_for_status()
                cached.write_bytes(resp.content)
            except Exception:
                # 下载失败：返回透明占位图
                img = QImage(64, 64, QImage.Format_ARGB32)
                img.fill(Qt.transparent)  # type: ignore[name-defined]
                size.setWidth(64); size.setHeight(64)
                return img

        # 从缓存加载
        img = QImage(str(cached))
        if img.isNull():
            img = QImage(64, 64, QImage.Format_ARGB32)
            img.fill(Qt.transparent)  # type: ignore[name-defined]
            size.setWidth(64); size.setHeight(64)
            return img

        # 按 requestedSize 缩放（保持宽高比，不裁剪）
        # 注意：使用 KeepAspectRatio 而非 KeepAspectRatioByExpanding
        # 后者会返回超出 requestedSize 的图片，配合 QML 端 PreserveAspectFit 时
        # 仍可能因 size 提示与实际像素不一致导致边缘被裁剪（修复清单问题 5）
        if requestedSize.width() > 0 and requestedSize.height() > 0:
            img = img.scaled(
                requestedSize.width(), requestedSize.height(),
                Qt.KeepAspectRatio,  # type: ignore[name-defined]
                Qt.SmoothTransformation,  # type: ignore[name-defined]
            )
        size.setWidth(img.width()); size.setHeight(img.height())
        return img


# ============================================================
# ParseWorker — 后台解析 URL
# ============================================================

class _ParseWorker(QThread):
    """后台线程：调用 downloader.extract_info，避免阻塞 QML UI。"""
    finished = Signal(str)   # info_json
    failed = Signal(str)     # error_message

    def __init__(self, url: str, parent=None) -> None:
        super().__init__(parent)
        self._url = url

    def run(self) -> None:
        try:
            from ..downloader import extract_info
            info = extract_info(self._url)
            self.finished.emit(_video_info_to_json(info))
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(str(e))


# ============================================================
# SearchWorker — 后台 X-Sou 搜索
# ============================================================

class _SearchWorker(QThread):
    """后台线程：调用 x_sou_client.x_sou_search，避免阻塞 QML UI。"""
    finished = Signal(str)   # results_json
    failed = Signal(str)     # error_message

    def __init__(self, query: str, page: int = 1, limit: int = 20, parent=None) -> None:
        super().__init__(parent)
        self._query = query
        self._page = page
        self._limit = limit

    def run(self) -> None:
        try:
            from ..x_sou_client import x_sou_search
            result = x_sou_search(self._query, page=self._page, limit=self._limit)
            self.finished.emit(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(str(e))


# ============================================================
# PreviewCacheWorker — 后台下载 X-Sou 视频到本地预览缓存
# ============================================================

class _PreviewCacheWorker(QThread):
    """下载 X-Sou 视频（video.twimg.com 直链）到 cache/preview/，用于 QML 端预览。

    用 requests.Session(trust_env=True) 走系统代理（HTTP_PROXY/HTTPS_PROXY/
    Windows 注册表），避开 QMediaPlayer 无法使用代理的限制（参考老版本
    home_page._PreviewCacheWorker）。
    """
    progress = Signal(int, int)   # (downloaded_bytes, total_bytes)
    finished_ok = Signal(str)     # local file path
    failed = Signal(str)          # error message

    def __init__(self, url: str, parent=None) -> None:
        super().__init__(parent)
        self._url = url
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def is_set(self) -> bool:
        """cancel_event 协议：cache_manager 调用 is_set() 检查取消。"""
        return self._cancel

    def run(self) -> None:
        try:
            from ..utils.cache_manager import (
                download_to_preview_cache,
                get_preview_cache_path,
            )
            cached = get_preview_cache_path(self._url)
            if cached.exists() and cached.stat().st_size > 0:
                self.finished_ok.emit(str(cached))
                return
            result = download_to_preview_cache(
                self._url,
                progress_cb=lambda d, t: self.progress.emit(d, t),
                cancel_event=self,
            )
            if result is None:
                if self._cancel:
                    self.failed.emit("cancelled")
                else:
                    self.failed.emit("download failed")
            else:
                self.finished_ok.emit(str(result))
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(str(e))


def _video_info_to_json(info) -> str:
    """将 VideoInfo 序列化为 JSON 供 QML 消费。"""
    items = []
    for it in info.items:
        items.append({
            "url": it.url,
            "is_video": it.is_video,
            "media_type": it.media_type,
            "width": it.width,
            "height": it.height,
            "extension": it.extension,
            "size": it.size,
            "quality": it.quality,
            "filename": it.filename,
        })
    payload = {
        "title": info.title,
        "url": info.url,
        "thumbnail": info.thumbnail or "",
        "duration": info.duration or 0,
        "platform": info.platform,
        "author": info.author or "",
        "post_time": info.post_time or "",
        "items": items,
        "formats": info.formats or [],
    }
    return json.dumps(payload, ensure_ascii=False)


def _task_to_dict(qt) -> dict:
    """QueueTask → dict（仅 UI 需要的字段）。"""
    return {
        "task_id": qt.task_id,
        "url": qt.url,
        "title": qt.title,
        "platform": qt.platform,
        "author": qt.author,
        "post_time": qt.post_time,
        "thumbnail_url": qt.thumbnail_url or "",
        "status": qt.status,
        "progress": qt.progress,
        "speed": qt.speed,
        "filename": qt.filename,
        "error": qt.error,
        "error_category": qt.error_category,
        "format_type": qt.format_type,
        "custom_name": qt.custom_name,
        "retry_count": qt.retry_count,
        "max_retries": qt.max_retries,
        "created_at": qt.created_at,
    }


def _history_to_dict(rec) -> dict:
    return {
        "record_id": rec.record_id,
        "title": rec.title,
        "author": rec.author,
        "platform": rec.platform,
        "url": rec.url,
        "file_path": rec.file_path,
        "file_size": rec.file_size,
        "thumbnail_url": rec.thumbnail_url,
        "download_time": rec.download_time,
        "success": rec.success,
        "duration_seconds": rec.duration_seconds,
        "batch_id": rec.batch_id,
    }


def _library_item_to_dict(item, library_manager=None) -> dict:
    # 本地缩略图路径转 file:/// URL（处理 ~ 展开 + Windows 反斜杠）
    thumb_path = item.local_thumbnail_path or ""
    thumb_url = ""
    if thumb_path:
        from pathlib import Path
        try:
            p = Path(thumb_path).expanduser()
            if p.exists():
                thumb_url = p.as_uri()
        except Exception:
            thumb_url = ""
    # 收集该素材已加入的 Collection id 列表（供 QML 按分类筛选）
    # 注意：原先用 `from .database import get_session_factory` 路径错误
    # （lumio.gui.database 不存在），导致 collection_ids 永远为空，
    # 分类筛选失效。改为复用 LibraryManager.get_item_collections()（修复清单问题 6）
    collection_ids: list[int] = []
    if library_manager is not None:
        try:
            cols = library_manager.get_item_collections(item.id)
            collection_ids = [c.id for c in cols]
        except Exception:
            pass
    return {
        "id": item.id,
        "title": item.title,
        "author": item.author,
        "platform": item.platform,
        "url": item.url,
        "file_path": item.file_path,
        "file_size": item.file_size,
        "media_type": item.media_type,
        "duration": item.duration or 0,
        "post_time": item.post_time,
        "thumbnail_url": item.thumbnail_url or "",
        "local_thumbnail_path": thumb_url,  # 已转为 file:/// URL
        "is_favorite": bool(item.is_favorite),
        "batch_id": item.batch_id or "",
        "collection_ids": collection_ids,
        "created_at": item.created_at.isoformat() if item.created_at else "",
    }


def _inbox_item_to_dict(item) -> dict:
    return {
        "id": item.id,
        "source": item.source,
        "type": item.type,
        "url": item.url,
        "title": item.title,
        "author": item.author,
        "platform": item.platform,
        "thumbnail_url": item.thumbnail_url or "",
        "direct_url": item.direct_url or "",
        "content": item.content or "",
        "post_time": item.post_time or "",
        "duration": item.duration or 0,
        "status": item.status,
        "error_message": item.error_message or "",
        "captured_at": item.captured_at.isoformat() if item.captured_at else "",
    }


def _notification_to_dict(n) -> dict:
    return {
        "id": n.id,
        "category": n.category,
        "type": n.type,
        "title": n.title,
        "message": n.message,
        "action": n.action,
        "action_text": n.action_text,
        "created_at": n.created_at,
        "read": n.read,
        "dismissable": n.dismissable,
        "priority": getattr(n, "priority", "normal"),
        "source_key": getattr(n, "source_key", ""),
        "expires_at": getattr(n, "expires_at", ""),
        "group_key": getattr(n, "group_key", ""),
    }


# URL 提取正则：匹配 http(s):// 开头直到遇到中文/空格/反引号/引号/全角字符为止
# 覆盖场景：
#   - 纯 URL：https://www.xiaohongshu.com/explore/xxx
#   - 微信分享混合文本：64 【描述】 😆 xxx 😆 `https://...`
#   - QQ 分享：描述 https://... 描述
#   - 多行文本：第一行 URL，第二行描述
_URL_EXTRACT_RE = re.compile(
    r"https?://[^\s\u4e00-\u9fff\u3000-\u303f\uff00-\uffef`'\"<>]+",
    re.IGNORECASE,
)


def _extract_url_from_text(text: str) -> str:
    """从混合文本中提取纯 URL。

    处理用户从微信/QQ/小红书分享按钮复制的混合文本：
    - 中文描述 + 反引号包裹的 URL
    - 多行文本中的 URL
    - 纯 URL 直接返回

    Returns:
        提取出的 URL 字符串；无 URL 时返回空字符串。
    """
    if not text:
        return ""
    text = text.strip()
    # 快速路径：纯 URL（无中文/空格）
    if text.startswith(("http://", "https://")) and " " not in text and "\n" not in text:
        # 仍需检查无中文/全角字符
        if not re.search(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]", text):
            return text
    # 提取第一个匹配的 URL
    m = _URL_EXTRACT_RE.search(text)
    if m:
        url = m.group(0)
        # 去掉末尾可能粘连的标点（中文标点已被正则排除，但英文标点可能粘在末尾）
        url = url.rstrip(".,;:!?)")
        return url
    return ""


# ============================================================
# QmlController — QML 端的全局控制器
# ============================================================

class QmlController(QObject):
    """QML 全局控制器 — Python 后端的 QML 入口

    所有耗时操作走后台线程 + 信号回传。配置变更通过 setConfig 持久化。
    """

    # ---------- 信号 ----------
    infoExtracted = Signal(str, arguments=["info_json"])
    parseFailed = Signal(str, arguments=["error_message"])
    downloadProgressChanged = Signal(str, float, arguments=["task_id", "progress"])
    toastRequested = Signal(str, arguments=["message"])
    themeChanged = Signal(str, arguments=["theme"])
    langChanged = Signal(str, arguments=["lang"])
    configChanged = Signal()
    queueChanged = Signal()
    taskStatusChanged = Signal(str, str, arguments=["task_id", "status"])
    historyChanged = Signal()
    libraryChanged = Signal()
    inboxChanged = Signal()
    notificationsChanged = Signal(int, arguments=["unread_count"])
    # X-Sou 搜索结果
    searchCompleted = Signal(str, arguments=["results_json"])
    searchFailed = Signal(str, arguments=["error_message"])
    # X-Sou 视频预览（先下载到 cache/preview 再用 QML Dialog 播放）
    previewProgress = Signal(int, int, arguments=["downloaded", "total"])  # bytes
    previewReady = Signal(str, arguments=["local_path"])
    previewFailed = Signal(str, arguments=["error_message"])
    # Apify 月度用量查询完成（异步）
    apifyUsageUpdated = Signal(str, arguments=["usage_json"])
    # 文件缺失（被外部删除）— QML 弹确认对话框「是否删除本条记录？」
    # source: "library" / "history"，由调用方传入
    fileMissing = Signal(str, str, arguments=["path", "source"])

    def __init__(self, manager=None, inbox_manager=None, library_manager=None,
                 history_manager=None, notification_manager=None, parent=None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._inbox_manager = inbox_manager
        self._library_manager = library_manager
        self._history_manager = history_manager
        self._notification_manager = notification_manager
        self._parse_workers: list[_ParseWorker] = []
        self._search_workers: list[_SearchWorker] = []
        self._preview_worker: _PreviewCacheWorker | None = None
        # Apify 月度用量缓存（避免每次切页面都打 API）
        self._apify_usage_cache: dict = {}

        # 初始主题与语言
        cfg = load_config()
        self._theme = cfg.get("theme", "dark")
        self._lang = get_lang()

        # 连接后端信号
        if self._manager:
            self._manager.queue_changed.connect(self.queueChanged)
            self._manager.task_status_changed.connect(self.taskStatusChanged)
            self._manager.task_progress.connect(self._on_task_progress)
            self._manager.history_record_added.connect(lambda _: self.historyChanged.emit())
            self._manager.library_record_added.connect(lambda _: self.libraryChanged.emit())
            if self._history_manager:
                self._manager.set_history_manager(self._history_manager)
            if self._library_manager:
                self._manager.set_library_manager(self._library_manager)

        if self._inbox_manager:
            self._inbox_manager.item_added.connect(lambda _: self.inboxChanged.emit())
            self._inbox_manager.item_updated.connect(lambda _: self.inboxChanged.emit())
            self._inbox_manager.items_deleted.connect(lambda _: self.inboxChanged.emit())
            # Inbox 新内容只走 sidebar 红点（不进通知中心）
            self._inbox_manager.item_added.connect(
                lambda _: self._on_inbox_new_item()
            )

        if self._notification_manager:
            self._notification_manager.notifications_changed.connect(
                lambda c: self.notificationsChanged.emit(c)
            )

    def _on_inbox_new_item(self) -> None:
        """Inbox 收到新内容时，触发 sidebar 红点刷新。

        Inbox 新内容只走 sidebar 红点，不进通知中心。
        通过 notifications_changed 信号让 sidebar 刷新（badge 会读取 inbox 未读数）。
        """
        if self._notification_manager:
            try:
                self._notification_manager.notify_inbox_new(1)
            except Exception:
                pass

    # ============================================================
    # 属性
    # ============================================================

    @Property(str, notify=themeChanged)
    def theme(self):
        return self._theme

    @Property(str, notify=langChanged)
    def lang(self):
        return self._lang

    # ============================================================
    # URL 解析
    # ============================================================

    @Slot(str)
    def parseUrl(self, url: str) -> None:
        """解析 URL（后台线程），完成后发射 infoExtracted 信号。

        自动从混合文本中提取纯 URL：
        - 微信/QQ 分享按钮复制的链接常带中文描述+反引号包裹的 URL
          例："64 【✈️出差啦 - 杨超越 | 小红书】 😆 xxx 😆 `https://...`"
        - 用户也可能直接粘贴带前后空格/换行的 URL
        - 项目硬约束：小红书 PC 分享链接需从含中文描述文本中提取纯 URL
        """
        url = (url or "").strip()
        if not url:
            self.parseFailed.emit("URL is empty")
            return

        # 从混合文本中提取纯 URL（处理微信/QQ 分享格式）
        url = _extract_url_from_text(url)
        if not url:
            self.parseFailed.emit(self._tr("parse_empty"))
            return

        worker = _ParseWorker(url, parent=self)
        worker.finished.connect(self.infoExtracted)
        worker.failed.connect(self.parseFailed)
        worker.finished.connect(lambda _: self._cleanup_worker(worker))
        worker.failed.connect(lambda _: self._cleanup_worker(worker))
        self._parse_workers.append(worker)
        worker.start()

    def _cleanup_worker(self, worker: _ParseWorker) -> None:
        try:
            self._parse_workers.remove(worker)
        except ValueError:
            pass
        worker.deleteLater()

    def _on_task_progress(self, task_id: str, progress: float, speed: str, filename: str) -> None:
        self.downloadProgressChanged.emit(task_id, progress)

    # ============================================================
    # X-Sou 搜索
    # ============================================================

    @Slot(str, int, int)
    def searchXSou(self, query: str, page: int, limit: int) -> None:
        """X-Sou 视频搜索（后台线程），完成后发射 searchCompleted 信号。"""
        query = (query or "").strip()
        if not query:
            self.searchFailed.emit(self._tr("parse_empty"))
            return
        worker = _SearchWorker(query, page=page or 1, limit=limit or 20, parent=self)
        worker.finished.connect(self.searchCompleted)
        worker.failed.connect(self.searchFailed)
        worker.finished.connect(lambda _: self._cleanup_search_worker(worker))
        worker.failed.connect(lambda _: self._cleanup_search_worker(worker))
        self._search_workers.append(worker)
        worker.start()

    def _cleanup_search_worker(self, worker: _SearchWorker) -> None:
        try:
            self._search_workers.remove(worker)
        except ValueError:
            pass
        worker.deleteLater()

    # ============================================================
    # X-Sou 视频预览（先下载到 cache/preview，再用 QML Dialog 播放本地文件）
    # ============================================================

    @Slot(str)
    def previewXVideo(self, video_url: str) -> None:
        """X-Sou 视频预览：后台下载到 cache/preview，完成后发射 previewReady 信号。

        QML 端用 QtMultimedia MediaPlayer 播放本地文件，避开 QMediaPlayer
        无法使用系统代理的限制（参考老版本 home_page._preview_x_video）。
        """
        if not video_url:
            return
        # 已有 worker 在跑，忽略重复点击
        if self._preview_worker and self._preview_worker.isRunning():
            self.toastRequested.emit(self._tr("x_sou_preview_caching"))
            return
        self._preview_worker = _PreviewCacheWorker(video_url, parent=self)
        self._preview_worker.progress.connect(self.previewProgress)
        self._preview_worker.finished_ok.connect(self.previewReady)
        self._preview_worker.failed.connect(self.previewFailed)
        self._preview_worker.finished_ok.connect(lambda _: self._cleanup_preview_worker())
        self._preview_worker.failed.connect(lambda _: self._cleanup_preview_worker())
        self._preview_worker.start()

    @Slot()
    def cancelPreview(self) -> None:
        """取消正在进行的预览下载。"""
        if self._preview_worker and self._preview_worker.isRunning():
            self._preview_worker.cancel()

    def _cleanup_preview_worker(self) -> None:
        if self._preview_worker:
            w = self._preview_worker
            self._preview_worker = None
            w.deleteLater()

    # ============================================================
    # 下载队列
    # ============================================================

    @Slot(result=str)
    def getQueueJson(self) -> str:
        """返回当前队列所有任务的 JSON 数组字符串。"""
        if not self._manager:
            return "[]"
        tasks = self._manager.get_all_tasks()
        return json.dumps([_task_to_dict(t) for t in tasks], ensure_ascii=False)

    @Slot(str, str, str, str, str)
    def addDownloadTask(self, info_json: str, format_id: str, format_type: str,
                        custom_name: str, output_dir: str) -> None:
        """从解析信息+格式入队下载任务。"""
        if not self._manager:
            self.toastRequested.emit("Download manager not ready")
            return
        try:
            info_data = json.loads(info_json)
        except Exception as e:
            self.toastRequested.emit(f"Invalid info JSON: {e}")
            return

        # 构造 VideoInfo-like 对象供 add_task_from_info 使用
        from ..utils.media_utils import VideoInfo, MediaItem
        items = []
        for it in info_data.get("items", []):
            items.append(MediaItem(
                url=it.get("url", ""),
                is_video=it.get("is_video", False),
                media_type=it.get("media_type", ""),
                width=it.get("width", 0),
                height=it.get("height", 0),
                extension=it.get("extension", ""),
                size=it.get("size", 0),
                quality=it.get("quality", ""),
                filename=it.get("filename", ""),
            ))
        info = VideoInfo(
            title=info_data.get("title", ""),
            url=info_data.get("url", ""),
            thumbnail=info_data.get("thumbnail", ""),
            duration=info_data.get("duration", 0),
            formats=info_data.get("formats", []),
            platform=info_data.get("platform", ""),
            author=info_data.get("author", ""),
            items=items,
            post_time=info_data.get("post_time", ""),
        )

        from ..utils.config import get_download_dir
        out_dir = output_dir or str(get_download_dir())
        try:
            task_id = self._manager.add_task_from_info(
                info=info,
                format_id=format_id or None,
                format_type=format_type,
                custom_name=custom_name,
                output_dir=out_dir,
            )
            self.toastRequested.emit(self._tr("added_to_queue"))
        except Exception as e:
            traceback.print_exc()
            self.toastRequested.emit(f"{self._tr('enqueue_failed')}: {e}")

    @Slot(str, str, str, str, bool, str)
    def addDirectDownloadTask(self, url: str, title: str, platform: str, thumbnail: str,
                              is_video: bool = False, author: str = "") -> None:
        """X-Sou 等已知直链场景：仅 URL 入队，跳过解析。

        Args:
            url: 媒体直链 URL
            title: 任务标题（同时作为文件名 stem）
            platform: 平台标识
            thumbnail: 远程缩略图 URL（单项下载时优先用 url 本身）
            is_video: 是否视频（决定文件扩展名默认值 .mp4/.jpg，
                      当 URL 无扩展名时使用）
            author: 作者名（用于 organized 存储模式子目录命名）
        """
        if not self._manager:
            return
        from ..queue_manager import QueueTask
        from ..utils.config import get_download_dir
        # 单项下载：用所选 item 的 url 作为 thumbnail_url（前端 previewInfo.thumbnail
        # 永远是帖子第一项，单项下载时不应使用）
        thumb = thumbnail or ("" if is_video else url)
        qt = QueueTask(
            url=url,
            direct_url=url,
            title=title,
            platform=platform,
            author=author,
            custom_name=title,  # 显式 custom_name 避免 _effective_name 返回 %(title)s
            thumbnail_url=thumb or None,
            output_dir=str(get_download_dir()),
        )
        # 用 media_items_json 记录 is_video，让 _direct_download_with_pause
        # 能正确推断扩展名（URL 无后缀时不再默认 .mp4）
        import json as _json
        qt.media_items_json = _json.dumps([{
            "url": url,
            "is_video": is_video,
            "index": 0,
        }])
        self._manager.add_task(qt)
        self.toastRequested.emit(self._tr("added_to_queue"))

    @Slot(str)
    def startTask(self, task_id: str) -> None:
        if self._manager:
            self._manager.start_task(task_id)

    @Slot(str)
    def pauseTask(self, task_id: str) -> None:
        if self._manager:
            self._manager.pause_task(task_id)

    @Slot(str)
    def resumeTask(self, task_id: str) -> None:
        if self._manager:
            self._manager.resume_task(task_id)

    @Slot(str)
    def cancelTask(self, task_id: str) -> None:
        if self._manager:
            self._manager.cancel_task(task_id)

    @Slot(str)
    def retryTask(self, task_id: str) -> None:
        if self._manager:
            self._manager.retry_task(task_id)

    @Slot(str)
    def deleteTask(self, task_id: str) -> None:
        if self._manager:
            self._manager.delete_task(task_id)

    @Slot()
    def startAll(self) -> None:
        if self._manager:
            self._manager.start_all()

    @Slot()
    def pauseAll(self) -> None:
        if self._manager:
            self._manager.pause_all()

    @Slot()
    def resumeAll(self) -> None:
        if self._manager:
            self._manager.resume_all()

    # ============================================================
    # 历史记录
    # ============================================================

    @Slot(result=str)
    def getHistoryJson(self) -> str:
        if not self._history_manager:
            return "[]"
        records = self._history_manager.records
        return json.dumps([_history_to_dict(r) for r in records], ensure_ascii=False)

    @Slot(str, str, result=bool)
    def searchHistory(self, query: str, platform: str) -> bool:
        """占位：搜索由 QML 端在客户端做（数据量小）。"""
        return True

    @Slot(str)
    def deleteHistory(self, record_id: str) -> None:
        if self._history_manager:
            self._history_manager.delete(record_id)
            self.historyChanged.emit()

    @Slot()
    def clearHistory(self) -> None:
        if self._history_manager:
            self._history_manager.clear()
            self.historyChanged.emit()

    @Slot(str, result=bool)
    def openFile(self, path: str) -> bool:
        """打开文件（无 source 版本，向后兼容）。"""
        return self._openFileWithSource(path, "")

    @Slot(str, str, result=bool)
    def openFileFromSource(self, path: str, source: str) -> bool:
        """打开文件 — 带数据源标识。

        source: "library" / "history" / "" — 文件缺失时发 fileMissing 信号，
        QML 据此弹「是否删除本条记录」对话框。
        """
        return self._openFileWithSource(path, source)

    def _openFileWithSource(self, path: str, source: str) -> bool:
        """打开文件 — 调用系统默认程序。

        - 单文件：直接 os.startfile（视频→系统播放器，文档→默认程序）
        - 图片文件 / 目录中的第一张图片：
          Windows 优先调用 Microsoft 照片（UWP，ms-photos: 协议），
          避免 .jpg 关联到 PotPlayer 等第三方播放器；
          若 Microsoft 照片不可用则回退到 os.startfile（系统默认）
        - 目录（多图帖/视频+图片混合）：找第一张图片/视频文件打开
        - 路径不存在时：发 fileMissing 信号（若有 source）让 QML 弹删除确认对话框
        """
        if not path:
            self.toastRequested.emit("Open failed: empty path")
            return False
        try:
            import os
            import subprocess
            target = path
            # 如果是目录，找第一张图片/视频文件作为打开目标
            if os.path.isdir(path):
                target = self._first_openable_media(path) or path
            # 路径不存在时：发信号让 QML 弹删除确认（而非只 toast）
            if not os.path.exists(target):
                if source:
                    self.fileMissing.emit(path, source)
                else:
                    self.toastRequested.emit(f"Open failed: file not found — {target}")
                return False
            # 图片类型用 Microsoft 照片（UWP），避免 .jpg 被关联到 PotPlayer
            if sys.platform == "win32":
                ext = os.path.splitext(target)[1].lower()
                if ext in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}:
                    photos_uri = f"ms-photos:viewer?fileName={target}"
                    try:
                        subprocess.Popen(
                            ["cmd", "/c", "start", "", photos_uri],
                            shell=False,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        return True
                    except Exception:
                        os.startfile(target)  # type: ignore[attr-defined]
                        return True
                os.startfile(target)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", target])
            else:
                subprocess.Popen(["xdg-open", target])
            return True
        except Exception as e:
            self.toastRequested.emit(f"Open failed: {e}")
            return False

    @staticmethod
    def _first_openable_media(folder: str) -> str | None:
        """目录内第一个图片/视频文件路径（按文件名排序）。"""
        from pathlib import Path
        media_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp",
                      ".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv",
                      ".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg"}
        try:
            p = Path(folder)
            files = sorted(f for f in p.iterdir() if f.is_file() and f.suffix.lower() in media_exts)
            return str(files[0]) if files else None
        except OSError:
            return None

    @Slot(str, result=bool)
    def openFolder(self, path: str) -> bool:
        """打开文件夹（无 source 版本，向后兼容）。"""
        return self._openFolderWithSource(path, "")

    @Slot(str, str, result=bool)
    def openFolderFromSource(self, path: str, source: str) -> bool:
        """打开文件夹 — 带数据源标识。文件缺失时发 fileMissing 信号。"""
        return self._openFolderWithSource(path, source)

    def _openFolderWithSource(self, path: str, source: str) -> bool:
        if not path:
            return False
        try:
            import os
            import subprocess
            # 路径完全不存在时：发信号让 QML 弹删除确认
            if not os.path.exists(path):
                if source:
                    self.fileMissing.emit(path, source)
                else:
                    self.toastRequested.emit(f"Open folder failed: path not found — {path}")
                return False
            folder = os.path.dirname(path) if os.path.isfile(path) else path
            if sys.platform == "win32":
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
            return True
        except Exception as e:
            self.toastRequested.emit(f"Open folder failed: {e}")
            return False

    # ============================================================
    # 素材库
    # ============================================================

    @Slot(result=str)
    def getLibraryJson(self) -> str:
        if not self._library_manager:
            return "[]"
        items = self._library_manager.get_all_items()
        return json.dumps(
            [_library_item_to_dict(it, self._library_manager) for it in items],
            ensure_ascii=False,
        )

    @Slot(str, result=bool)
    def toggleFavorite(self, item_id: str) -> bool:
        """切换收藏状态，返回新的 is_favorite 值。

        不发 libraryChanged 信号——只改了一个布尔字段，全量 reload 会导致
        所有卡片 Repeater 重建闪烁。QML 端用返回值直接更新本地 isFav property。
        """
        if self._library_manager:
            return bool(self._library_manager.toggle_favorite(item_id))
        return False

    @Slot(str)
    def deleteLibraryItem(self, item_id: str) -> None:
        if self._library_manager:
            self._library_manager.delete_item(item_id)
            self.libraryChanged.emit()

    @Slot(result=str)
    def getCollectionsJson(self) -> str:
        if not self._library_manager:
            return "[]"
        cols = self._library_manager.get_all_collections()
        out = []
        for c in cols:
            count, _size = self._library_manager.get_collection_stats(c.id)
            out.append({
                "id": c.id,
                "name": c.name,
                "icon": c.icon or "",
                "count": count,
            })
        return json.dumps(out, ensure_ascii=False)

    @Slot(str, result=int)
    def createCollection(self, name: str) -> int:
        if self._library_manager:
            cid = self._library_manager.create_collection(name)
            self.libraryChanged.emit()
            return cid
        return -1

    @Slot(int)
    def deleteCollection(self, collection_id: int) -> None:
        if self._library_manager:
            self._library_manager.delete_collection(collection_id)
            self.libraryChanged.emit()

    @Slot(int, str)
    def renameCollection(self, collection_id: int, new_name: str) -> None:
        """重命名 Collection（修复清单问题 2：右键菜单缺失）。"""
        if self._library_manager:
            self._library_manager.rename_collection(collection_id, new_name)
            self.libraryChanged.emit()

    @Slot(str, int)
    def addItemToCollection(self, item_id: str, collection_id: int) -> None:
        """添加素材到 Collection。"""
        if self._library_manager:
            self._library_manager.add_item_to_collection(item_id, collection_id)
            self.libraryChanged.emit()

    @Slot(str, int)
    def removeItemFromCollection(self, item_id: str, collection_id: int) -> None:
        """从 Collection 移除素材（仅解除关联，不删除素材本身）。"""
        if self._library_manager:
            self._library_manager.remove_item_from_collection(item_id, collection_id)
            self.libraryChanged.emit()

    @Slot(str, result=str)
    def getItemCollectionsJson(self, item_id: str) -> str:
        """获取某素材已加入的 Collection id 列表（JSON 数组）。"""
        if not self._library_manager:
            return "[]"
        try:
            cols = self._library_manager.get_item_collections(item_id)
            return json.dumps([c.id for c in cols], ensure_ascii=False)
        except Exception:
            return "[]"

    # ============================================================
    # 收件箱
    # ============================================================

    @Slot(result=str)
    def getInboxJson(self) -> str:
        if not self._inbox_manager:
            return "[]"
        items = self._inbox_manager.get_all()
        return json.dumps([_inbox_item_to_dict(it) for it in items], ensure_ascii=False)

    @Slot(result=int)
    def unreadInbox(self) -> int:
        """返回 Inbox 中 status='new' 的未读数量（供 Sidebar 红点徽章使用）。"""
        if not self._inbox_manager:
            return 0
        try:
            return len(self._inbox_manager.get_all(status_filter="new"))
        except Exception:
            return 0

    @Slot(str)
    def inboxDownload(self, item_id: str) -> None:
        """从收件箱项目启动下载。

        - 有 direct_url（浏览器/Telegram 抓取的直链）→ 走通用直链下载
        - 仅有 page URL → 入队后由队列系统解析下载
        下载启动后将 inbox item 标记为 queued。
        """
        if not self._manager or not self._inbox_manager:
            return
        item = self._inbox_manager.get_item(item_id)
        if not item:
            self.toastRequested.emit(self._tr("enqueue_failed"))
            return

        from ..queue_manager import QueueTask
        from ..utils.config import get_download_dir

        qt = QueueTask(
            url=item.url,
            direct_url=item.direct_url or "",
            title=item.title or "",
            platform=item.platform or "",
            author=item.author or "",
            post_time=item.post_time or "",
            thumbnail_url=item.thumbnail_url or None,
            output_dir=str(get_download_dir()),
        )
        self._manager.add_task(qt)
        self._inbox_manager.mark_status(item_id, "queued")
        self.toastRequested.emit(self._tr("added_to_queue"))

    @Slot(str)
    def inboxBatchDownload(self, item_ids_json: str) -> None:
        """批量下载收件箱项目。item_ids_json 为 JSON 编码的 ID 数组。"""
        try:
            ids = json.loads(item_ids_json)
        except Exception as e:
            self.toastRequested.emit(f"Invalid ids: {e}")
            return
        for iid in ids:
            self.inboxDownload(iid)

    @Slot(str)
    def inboxMarkDownloaded(self, item_id: str) -> None:
        if self._inbox_manager:
            self._inbox_manager.mark_status(item_id, "downloaded")
            self.inboxChanged.emit()

    @Slot(str)
    def inboxArchive(self, item_id: str) -> None:
        if self._inbox_manager:
            self._inbox_manager.mark_status(item_id, "archived")
            self.inboxChanged.emit()

    @Slot(str)
    def inboxDelete(self, item_id: str) -> None:
        if self._inbox_manager:
            self._inbox_manager.delete_item(item_id)
            self.inboxChanged.emit()

    @Slot(str)
    def inboxBatchDelete(self, item_ids_json: str) -> None:
        """批量删除收件箱项目。"""
        if not self._inbox_manager:
            return
        try:
            ids = json.loads(item_ids_json)
        except Exception as e:
            self.toastRequested.emit(f"Invalid ids: {e}")
            return
        self._inbox_manager.delete_items(ids)
        self.inboxChanged.emit()

    @Slot()
    def inboxClearCompleted(self) -> None:
        """清空已下载/已归档的收件箱项目。"""
        if not self._inbox_manager:
            return
        items = self._inbox_manager.get_all()
        ids = [it.id for it in items if it.status in ("downloaded", "archived")]
        if ids:
            self._inbox_manager.delete_items(ids)
            self.inboxChanged.emit()

    @Slot(str, result=bool)
    def openExternalUrl(self, url: str) -> bool:
        """用系统默认浏览器打开 URL。"""
        if not url:
            return False
        try:
            from PySide6.QtGui import QDesktopServices
            return QDesktopServices.openUrl(QUrl(url))
        except Exception as e:
            self.toastRequested.emit(f"Open URL failed: {e}")
            return False

    @Slot(str, result=str)
    def thumbUrl(self, url: str) -> str:
        """把远程缩略图 URL 包装成 image://thumb/<base64> 形式，
        由 ThumbnailProvider 代理下载（带 Referer/Cookie）并缓存。

        QML 端用法：`Image { source: controller.thumbUrl(remoteUrl) }`
        对空 URL 或本地 file:// URL 直接返回原值。
        """
        if not url:
            return ""
        if url.startswith("file://") or url.startswith("image://"):
            return url
        import base64 as _b64
        encoded = _b64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii")
        return f"image://thumb/{encoded}"

    # ============================================================
    # 通知
    # ============================================================

    @Slot(result=str)
    def getNotificationsJson(self) -> str:
        if not self._notification_manager:
            return "[]"
        ns = self._notification_manager.get_all()
        return json.dumps([_notification_to_dict(n) for n in ns], ensure_ascii=False)

    @Slot(result=int)
    def unreadNotifications(self) -> int:
        if not self._notification_manager:
            return 0
        return self._notification_manager.unread_count()

    @Slot()
    def markAllNotificationsRead(self) -> None:
        if self._notification_manager:
            self._notification_manager.mark_all_read()

    @Slot(str)
    def markNotificationRead(self, notif_id: str) -> None:
        """单条标记已读（修复：原 QML 版缺此 API，只能全部已读或关闭）。"""
        if self._notification_manager:
            self._notification_manager.mark_read(notif_id)

    @Slot()
    def clearReadNotifications(self) -> None:
        """清除已读通知（永久通知保留）。

        修复：原 QML 版用逐条 dismissNotification 实现，存在循环中操作过期数据
        和 dismiss 不检查 dismissable 的双重 bug。改为后端一次性 clear_read()。
        """
        if self._notification_manager:
            self._notification_manager.clear_read()

    @Slot(str)
    def dismissNotification(self, notif_id: str) -> None:
        if self._notification_manager:
            self._notification_manager.dismiss(notif_id)

    # ============================================================
    # 统计
    # ============================================================

    @Slot(result=str)
    def getStatsJson(self) -> str:
        """聚合统计：总下载数/体积/成功率/今日/各平台数量。"""
        stats = {
            "total_downloads": 0,
            "total_size": 0,
            "success_rate": 0.0,
            "today_count": 0,
            "platforms": {},
        }
        if self._history_manager:
            records = self._history_manager.records
            stats["total_downloads"] = len(records)
            success = sum(1 for r in records if r.success)
            stats["success_rate"] = (success / len(records) * 100) if records else 0.0
            stats["total_size"] = sum(r.file_size for r in records)
            from datetime import datetime, timezone
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            stats["today_count"] = sum(
                1 for r in records
                if r.download_time and r.download_time.startswith(today)
            )
            for r in records:
                p = r.platform or "unknown"
                stats["platforms"][p] = stats["platforms"].get(p, 0) + 1
        return json.dumps(stats, ensure_ascii=False)

    # ============================================================
    # 配置 / 设置
    # ============================================================

    @Slot(result=str)
    def getConfigJson(self) -> str:
        """返回完整 config.json 内容。"""
        cfg = load_config()
        # 隐私字段：cookie/token 不返回明文，只返回是否配置
        safe = dict(cfg)
        if "telegram_bot_token" in safe and safe["telegram_bot_token"]:
            safe["telegram_bot_token"] = "***configured***"
        return json.dumps(safe, ensure_ascii=False, indent=2)

    @Slot(str, str)
    def setConfig(self, key: str, value_json: str) -> None:
        """更新单个配置项并持久化。value_json 是 JSON 编码的值。"""
        try:
            value = json.loads(value_json)
        except Exception:
            value = value_json
        cfg = load_config()
        cfg[key] = value
        # Apify token/actor 变化时清除验证状态 + 重置 client 缓存 + 清空用量缓存
        # 避免假 token 输入后 connected 仍显示 true，或刷新用量仍用旧的有效 client
        if key in ("apify_token", "apify_ig_actor"):
            cfg["apify_verified"] = False
            try:
                from ..apify_client import reset_apify_client
                reset_apify_client()
            except Exception:
                pass
            # 清空用量缓存，强制下次查询用新 token
            self._apify_usage_cache = {"_ts": 0}
        save_config(cfg)
        self.configChanged.emit()
        self.toastRequested.emit(self._tr("settings_saved"))

    @Slot(str, str)
    def setNestedConfig(self, parent_key: str, key_value_json: str) -> None:
        """更新嵌套配置（如 cache_management.auto_clean）。

        key_value_json: '{"auto_clean":"daily"}' 可一次更新多个键。
        """
        try:
            updates = json.loads(key_value_json)
        except Exception as e:
            self.toastRequested.emit(f"Invalid JSON: {e}")
            return
        cfg = load_config()
        parent = cfg.setdefault(parent_key, {})
        if not isinstance(parent, dict):
            parent = {}
            cfg[parent_key] = parent
        parent.update(updates)
        save_config(cfg)
        self.configChanged.emit()

    @Slot(str, result=bool)
    def checkUrlDuplicate(self, url: str) -> bool:
        """检查 URL 是否已存在于 Library。"""
        if self._manager and self._manager.check_url_duplicate(url):
            return True
        return False

    @Slot(result=str)
    def browseFolder(self) -> str:
        """打开文件夹选择对话框，返回所选路径（取消则空串）。"""
        from PySide6.QtWidgets import QFileDialog
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            return ""
        folder = QFileDialog.getExistingDirectory(None, "Select Folder", "")
        return folder or ""

    @Slot(result=str)
    def browseCookieFile(self) -> str:
        """打开 cookie 文件选择对话框（支持多选）。

        返回 JSON 编码的路径数组字符串，如 '["path1","path2"]'。
        单选时返回单元素数组。取消返回 '[]'。
        """
        from PySide6.QtWidgets import QFileDialog, QApplication
        app = QApplication.instance()
        if app is None:
            return "[]"
        paths, _ = QFileDialog.getOpenFileNames(
            None, "Select Cookie File(s)", "", "Cookie Files (*.txt);;All Files (*)"
        )
        return json.dumps(paths or [], ensure_ascii=False)

    @Slot(str, result=str)
    def importCookieFile(self, source_paths_json: str) -> str:
        """合并导入用户选择的 cookie 文件（支持多个）到 Lumio 的 cookie 文件。

        source_paths_json: JSON 编码的路径数组，如 '["path1","path2"]'
        返回 "ok" 或错误信息。
        """
        try:
            paths = json.loads(source_paths_json) if source_paths_json else []
        except Exception as e:
            return f"Invalid paths JSON: {e}"

        if not paths:
            return "No file selected"

        try:
            from ..utils.config import load_config
            cfg = load_config()
            dest = Path(cfg.get("cookie_file", str(Path.home() / ".lumio" / "cookies.txt")))
            dest.parent.mkdir(parents=True, exist_ok=True)

            # 合并模式：读取已有 cookie，去重追加
            existing_lines: set[str] = set()
            if dest.exists():
                with open(dest, encoding="utf-8") as f:
                    existing_lines = {l.strip() for l in f if l.strip()}

            imported_count = 0
            for source_path in paths:
                if not source_path or not Path(source_path).exists():
                    continue
                with open(source_path, encoding="utf-8") as src_f, \
                     open(dest, "a", encoding="utf-8") as dest_f:
                    for line in src_f:
                        s = line.strip()
                        if s and s not in existing_lines:
                            dest_f.write(line)
                            existing_lines.add(s)
                imported_count += 1

            if imported_count > 0:
                self.toastRequested.emit(self._tr("cookie_imported"))
                return "ok"
            return "No valid cookie file"
        except Exception as e:
            traceback.print_exc()
            return f"Import failed: {e}"

    @Slot(result=str)
    def getCookieStatus(self) -> str:
        """返回 cookie 总体状态：missing / valid / warning / expired。

        修复清单问题 4：原版本只返回 missing/valid，丢失 expired/warning。
        现在遍历所有平台，取最严重状态作为总体状态。
        """
        try:
            from .cookie_checker import check_all_cookies
            statuses = check_all_cookies()
            # 严重程度排序：expired > warning > valid > missing
            if "expired" in statuses.values():
                return "expired"
            if "warning" in statuses.values():
                return "warning"
            if "valid" in statuses.values():
                return "valid"
            return "missing"
        except Exception:
            from ..utils.config import get_cookie_path
            return "valid" if get_cookie_path() else "missing"

    @Slot(result=str)
    def getCookieStatusesJson(self) -> str:
        """返回所有平台 cookie 状态 JSON。

        格式: {"instagram":"valid","x":"missing","youtube":"missing",...}
        修复清单问题 4：让用户知道哪个平台已导入、哪个还没导入。
        """
        try:
            from .cookie_checker import check_all_cookies
            return json.dumps(check_all_cookies(), ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    @Slot(result=bool)
    def clearCookie(self) -> bool:
        """清除所有 cookie（清空 cookie 文件内容）。

        修复清单问题 4：原版本只有导入按钮，没有清除按钮。
        """
        try:
            from ..utils.config import get_cookie_path
            cookie_path = get_cookie_path()
            if cookie_path and cookie_path.exists():
                # 清空文件内容（保留文件本身，避免路径失效）
                cookie_path.write_text("", encoding="utf-8")
                self.toastRequested.emit(self._tr("cookie_cleared"))
                return True
            return False
        except Exception as e:
            self.toastRequested.emit(f"Clear failed: {e}")
            return False

    # ============================================================
    # Telegram 集成（修复清单问题 3：恢复老版本功能）
    # ============================================================

    @Slot(str, str, result=str)
    def validateTelegramToken(self, token: str, proxy: str = "") -> str:
        """验证 Telegram Bot Token。

        返回 JSON: {"ok": true, "username": "..."} 或 {"ok": false, "error": "..."}
        """
        try:
            from ..telegram_service import TelegramService
            result = TelegramService.validate_token(token, proxy=proxy)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

    @Slot(result=str)
    def generateTelegramPairCode(self) -> str:
        """生成 Telegram 配对码（格式 XXXX-XXXX）。"""
        try:
            from ..telegram_service import TelegramService
            svc = TelegramService(inbox_manager=None)
            return svc.generate_pair_code()
        except Exception as e:
            return f"Error: {e}"

    @Slot(result=str)
    def getTelegramStateJson(self) -> str:
        """返回 Telegram 当前状态 JSON。

        包含：pair_code、bound_device（telegram_user_id/username/first_name）。
        """
        try:
            from ..telegram_service import TelegramService
            svc = TelegramService(inbox_manager=None)
            device = svc.get_bound_device()
            bound = None
            if device:
                bound = {
                    "telegram_user_id": device.telegram_user_id,
                    "username": getattr(device, "username", "") or "",
                    "first_name": getattr(device, "first_name", "") or "",
                }
            return json.dumps({
                "pair_code": load_config().get("telegram_pair_code", ""),
                "bound_device": bound,
                "is_running": svc.is_running,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    @Slot(result=bool)
    def unlinkTelegramDevice(self) -> bool:
        """解除 Telegram 设备绑定。"""
        try:
            from ..telegram_service import TelegramService
            svc = TelegramService(inbox_manager=None)
            device = svc.get_bound_device()
            if device:
                svc.unlink_device(device.telegram_user_id)
                self.toastRequested.emit(self._tr("telegram_unlinked"))
                return True
            return False
        except Exception as e:
            self.toastRequested.emit(f"Unlink failed: {e}")
            return False

    @Slot(str)
    def copyToClipboard(self, text: str) -> None:
        """复制文本到系统剪贴板。"""
        try:
            from PySide6.QtGui import QGuiApplication
            QGuiApplication.clipboard().setText(text)
        except Exception as e:
            self.toastRequested.emit(f"Copy failed: {e}")

    @Slot(result=str)
    def getClipboardText(self) -> str:
        """读取系统剪贴板文本。

        QML 端无法直接访问 QClipboard.text（QClipboard 未将 text 暴露为
        Q_PROPERTY，且 text() 非 Q_INVOKABLE），故由此 Slot 转发。
        """
        try:
            from PySide6.QtGui import QGuiApplication
            cb = QGuiApplication.clipboard()
            return cb.text() if cb else ""
        except Exception:
            return ""

    # ============================================================
    # Apify IG 代理（恢复老版本功能）
    # ------------------------------------------------------------
    # 通过 Apify Actor 代理提取 IG 数据，避免直接调用 IG 移动 API
    # 导致账号风控。用户需在 https://console.apify.io 注册并创建
    # Instagram Scraper Actor，获取 token + actor_id 填入设置。
    # ============================================================

    @Slot(str, str, result=str)
    def validateApifyToken(self, token: str, actor_id: str) -> str:
        """验证 Apify Token + Actor ID 是否可用。

        返回 JSON: {"ok": true, "username": "..."} 或 {"ok": false, "error": "..."}
        验证成功后自动保存配置并重置缓存的 Apify client。
        """
        token = (token or "").strip()
        actor_id = (actor_id or "").strip()
        if not token:
            return json.dumps({"ok": False, "error": self._tr("apify_token_empty")},
                              ensure_ascii=False)
        if not actor_id:
            return json.dumps({"ok": False, "error": self._tr("apify_actor_empty")},
                              ensure_ascii=False)
        try:
            from ..apify_client import ApifyIGClient
            client = ApifyIGClient(token=token, actor_id=actor_id)
            ok = client.test_connection()
            if ok:
                # 保存到 config 并标记为已验证 + 重置缓存
                cfg = load_config()
                cfg["apify_token"] = token
                cfg["apify_ig_actor"] = actor_id
                cfg["apify_verified"] = True  # 验证成功，标记有效
                save_config(cfg)
                try:
                    from ..apify_client import reset_apify_client
                    reset_apify_client()
                except Exception:
                    pass
                # 清空用量缓存时间戳，允许立即查询用量
                self._apify_usage_cache = {"_ts": 0}
                self.configChanged.emit()
                return json.dumps({"ok": True}, ensure_ascii=False)
            else:
                return json.dumps({"ok": False, "error": self._tr("apify_validate_fail")},
                                  ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

    @Slot(result=str)
    def getApifyStatusJson(self) -> str:
        """返回 Apify 配置状态 JSON。

        持久状态字段（不依赖验证瞬态结果，切页面回来自动恢复）：
        - token_configured / actor_configured: bool
        - connected: token + actor 都已配置（不代表网络可达，仅表示「已配置可调用」）
        - enabled: instagram_mode == "api"（当前是否真正走 Apify 路径）
        - token_preview / actor_id: 脱敏显示

        额度字段（额度数据走后台异步刷新，初始为空）：
        - usage_usd: 当月已用金额（USD）
        - plan_credits_usd: 月度免费额度（Free 通常 $5）
        - usage_updated: 数据更新时间戳（ISO）
        """
        try:
            cfg = load_config()
            token = cfg.get("apify_token", "")
            actor = cfg.get("apify_ig_actor", "")
            verified = cfg.get("apify_verified", False) is True
            enabled = cfg.get("instagram_mode", "cookie") == "api"

            payload = {
                "token_configured": bool(token),
                "actor_configured": bool(actor),
                # connected = 已配置且已验证有效（输入框变化时自动清除 verified）
                "connected": bool(token and actor and verified),
                "verified": verified,  # 是否已验证（供 UI 区分"待验证"/"已验证"）
                "enabled": enabled,
                "token_preview": ("apify_api_" + token[10:] + "...") if len(token) > 14 else (token or ""),
                "actor_id": actor,
                # 额度数据从缓存读，避免每次切页面都打 API
                "usage_usd": self._apify_usage_cache.get("usage_usd"),
                "plan_credits_usd": self._apify_usage_cache.get("plan_credits_usd"),
                "plan_name": self._apify_usage_cache.get("plan_name"),
                "usage_updated": self._apify_usage_cache.get("usage_updated"),
            }
            return json.dumps(payload, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    @Slot()
    def refreshApifyUsage(self) -> None:
        """后台查询 Apify 月度用量（GET /v2/users/me）。

        通过 apify_client.ApifyClient.user().get() 调用，返回 plan 和 currentUsageUsd。
        结果缓存到 self._apify_usage_cache，并通过 apifyUsageUpdated 信号通知 QML 刷新。
        频率限制：5 分钟内不重复查询。
        """
        import time as _time
        now = _time.time()
        # 5 分钟内不重复查询
        if now - self._apify_usage_cache.get("_ts", 0) < 300:
            return
        self._do_refresh_apify_usage()

    @Slot()
    def forceRefreshApifyUsage(self) -> None:
        """强制刷新 Apify 用量（绕过 5 分钟缓存）。

        供设置页「刷新」按钮调用：用户主动点击时不应该被缓存限制。
        """
        self._do_refresh_apify_usage()

    def _do_refresh_apify_usage(self) -> None:
        """实际执行 Apify 用量查询（后台线程）。

        正确的查询方式（apify-client 已通过 pluck_data 剥掉 {"data": ...} 外壳）：
        - client.user().get() → 直接返回 user dict（含 plan.monthlyUsageCreditsUsd 总额度）
        - client.user().monthly_usage() → 直接返回 usage dict（含 totalUsageCreditsUsdAfterVolumeDiscount 当前用量）

        旧实现错误：用错字段名 totalUsageUsd（不存在），导致 usage_usd 永远是 0
        （真实余额 0.02/5.00 显示成 0.00/5.00）。
        """
        import time as _time
        try:
            from ..apify_client import get_apify_client as _get_apify_client
            client = _get_apify_client()
        except Exception as e:
            # token/actor 未配置等
            self._apify_usage_cache["_ts"] = _time.time()
            self.apifyUsageUpdated.emit(json.dumps({"error": str(e)}, ensure_ascii=False))
            return

        def _fetch():
            try:
                user_client = client._client.user()
                # 1. GET /v2/users/me — 拿 plan（总额度）+ tier
                user_data = user_client.get()
                # 2. GET /v2/users/me/usage/monthly — 拿月度用量明细
                usage_data = user_client.monthly_usage()

                if not user_data:
                    self.apifyUsageUpdated.emit(json.dumps(
                        {"error": "user get() returned empty"}, ensure_ascii=False))
                    return

                # apify-client 已 pluck_data，直接是 user dict（无 {"data": ...} 外壳）
                udata = user_data if isinstance(user_data, dict) else {}
                plan = udata.get("plan", {}) or {}
                plan_credits = float(plan.get("monthlyUsageCreditsUsd", 0) or 0)
                plan_name = plan.get("id", "") or udata.get("tier", "") or ""

                # monthly_usage() 同样已 pluck_data，直接是 usage dict
                # 正确字段名：totalUsageCreditsUsdAfterVolumeDiscount（当前周期已用额度）
                # 兜底字段：totalUsageCreditsUsdBeforeVolumeDiscount / dailyServiceUsages 末项
                usage_total = 0.0
                if usage_data and isinstance(usage_data, dict):
                    usage_total = float(
                        usage_data.get("totalUsageCreditsUsdAfterVolumeDiscount")
                        or usage_data.get("totalUsageCreditsUsdBeforeVolumeDiscount")
                        or 0
                    )
                    # 兜底：从 dailyServiceUsages 末项取 totalUsageCreditsUsd 累加
                    if usage_total == 0.0:
                        daily = usage_data.get("dailyServiceUsages") or []
                        if daily:
                            usage_total = sum(
                                float(d.get("totalUsageCreditsUsd", 0) or 0)
                                for d in daily
                            )

                self._apify_usage_cache.update({
                    "usage_usd": usage_total,
                    "plan_credits_usd": plan_credits,
                    "plan_name": plan_name,
                    "usage_updated": _time.strftime("%Y-%m-%d %H:%M:%S"),
                    "_ts": _time.time(),
                })
                # 清掉旧的 error 标记（如果有的话）
                self._apify_usage_cache.pop("error", None)
                self.apifyUsageUpdated.emit(json.dumps(self._apify_usage_cache,
                                                      ensure_ascii=False))

                # 接入通知系统：配额 >80% / 耗尽时发通知
                try:
                    from ..notification_manager import get_notification_manager
                    get_notification_manager().notify_apify_quota(
                        usage_total, plan_credits
                    )
                except Exception as _e:
                    logger.debug("notify_apify_quota failed: %s", _e)
            except Exception as e:
                self._apify_usage_cache["_ts"] = _time.time()
                self.apifyUsageUpdated.emit(json.dumps(
                    {"error": str(e)}, ensure_ascii=False))

        threading.Thread(target=_fetch, daemon=True).start()

    # ============================================================
    # 主题 / 语言
    # ============================================================

    @Slot()
    def toggleTheme(self) -> None:
        self._theme = "light" if self._theme == "dark" else "dark"
        cfg = load_config()
        cfg["theme"] = self._theme
        save_config(cfg)
        self.themeChanged.emit(self._theme)

    @Slot(str)
    def setTheme(self, theme: str) -> None:
        self._theme = "dark" if theme == "dark" else "light"
        cfg = load_config()
        cfg["theme"] = self._theme
        save_config(cfg)
        self.themeChanged.emit(self._theme)

    @Slot(str)
    def setLang(self, lang: str) -> None:
        if lang not in ("zh", "en"):
            return
        set_lang(lang)
        self._lang = lang
        self.langChanged.emit(lang)

    @Slot(str, result=str)
    def tr(self, key: str) -> str:
        """QML 端通过 controller.tr("key") 调用 i18n。"""
        return self._tr(key)

    def _tr(self, key: str) -> str:
        try:
            return t(key)
        except Exception:
            return key

    # ============================================================
    # 杂项
    # ============================================================

    @Slot(str)
    def showToast(self, message: str) -> None:
        self.toastRequested.emit(message)

    @Slot(result=str)
    def getCacheStatsJson(self) -> str:
        """返回 4 个缓存目录的统计信息。"""
        try:
            from ..utils.cache_manager import get_cache_stats
            return json.dumps(get_cache_stats(), ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @Slot()
    def cleanCacheByRules(self) -> None:
        """按规则清理缓存（后台线程）。"""
        import threading
        def _do():
            try:
                from ..utils.cache_manager import clean_cache_by_rules
                results = clean_cache_by_rules()
                # 汇总清理结果：仅当确实清理了文件时发通知
                total_files = sum(r.get("deleted", 0) for r in results.values())
                total_size = sum(r.get("freed", 0) for r in results.values())
                self.toastRequested.emit(self._tr("cache_cleaned"))
                if total_files > 0:
                    try:
                        from ..notification_manager import get_notification_manager
                        get_notification_manager().notify_cache_cleaned(
                            total_files, total_size
                        )
                    except Exception as _e:
                        logger.debug("notify_cache_cleaned failed: %s", _e)
            except Exception as e:
                traceback.print_exc()
                self.toastRequested.emit(f"Clean failed: {e}")
        threading.Thread(target=_do, daemon=True).start()

    @Slot()
    def forceClearCache(self) -> None:
        """强制清空全部缓存（后台线程）。"""
        import threading
        def _do():
            try:
                from ..utils.cache_manager import force_clear_cache
                results = force_clear_cache()
                total_files = sum(r.get("deleted", 0) for r in results.values())
                total_size = sum(r.get("freed", 0) for r in results.values())
                self.toastRequested.emit(self._tr("cache_cleaned"))
                if total_files > 0:
                    try:
                        from ..notification_manager import get_notification_manager
                        get_notification_manager().notify_cache_cleaned(
                            total_files, total_size
                        )
                    except Exception as _e:
                        logger.debug("notify_cache_cleaned failed: %s", _e)
            except Exception as e:
                traceback.print_exc()
                self.toastRequested.emit(f"Clear failed: {e}")
        threading.Thread(target=_do, daemon=True).start()

    @Slot(result=str)
    def getApiBase(self) -> str:
        """Telegram API base URL。"""
        return load_config().get("telegram_api_base", "https://api.telegram.org")

    @Slot(result=str)
    def checkUpdate(self) -> str:
        """检查 GitHub release 最新版本（同步执行，QML 端可在 worker 中调用）。"""
        try:
            from .. import __version__
            import urllib.request
            url = "https://api.github.com/repos/Azad-slack/Lumio/releases/latest"
            req = urllib.request.Request(url, headers={"User-Agent": "Lumio"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            latest = data.get("tag_name", "").lstrip("v")
            return json.dumps({
                "current": __version__,
                "latest": latest,
                "has_update": _version_lt(__version__, latest),
                "release_url": data.get("html_url", ""),
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)


def _version_lt(a: str, b: str) -> bool:
    """Return True if a < b in semver."""
    try:
        pa = [int(x) for x in a.split(".") if x.isdigit()]
        pb = [int(x) for x in b.split(".") if x.isdigit()]
        for i in range(max(len(pa), len(pb))):
            va = pa[i] if i < len(pa) else 0
            vb = pb[i] if i < len(pb) else 0
            if va < vb:
                return True
            if va > vb:
                return False
        return False
    except Exception:
        return False


# ============================================================
# launch_qml — QML 入口
# ============================================================

def launch_qml(manager=None, inbox_manager=None, library_manager=None,
               history_manager=None, notification_manager=None) -> None:
    """启动 QML UI"""
    import os
    os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    app.setApplicationName("Lumio")

    from PySide6.QtGui import QIcon
    logo = Path(__file__).parent / "assets" / "logo.png"
    if logo.exists():
        app.setWindowIcon(QIcon(str(logo)))

    controller = QmlController(
        manager=manager,
        inbox_manager=inbox_manager,
        library_manager=library_manager,
        history_manager=history_manager,
        notification_manager=notification_manager,
    )

    engine = QQmlApplicationEngine()
    engine.addImageProvider("icons", IconProvider())
    engine.addImageProvider("thumb", ThumbnailProvider())
    engine.rootContext().setContextProperty("controller", controller)

    qml_dir = Path(__file__).parent.parent / "qml"
    engine.addImportPath(str(qml_dir.parent))
    engine.addImportPath(str(qml_dir))

    def on_warnings(warnings):
        for w in warnings:
            print(f"[QML WARNING] {w.toString()}", file=sys.stderr, flush=True)
    engine.warnings.connect(on_warnings)

    main_qml = qml_dir / "Main.qml"
    print(f"[QML] Loading: {main_qml}", flush=True)
    engine.load(QUrl.fromLocalFile(str(main_qml)))

    if not engine.rootObjects():
        print("[QML] FATAL: engine.rootObjects() is empty", file=sys.stderr, flush=True)
        sys.exit(1)

    print(f"[QML] Loaded {len(engine.rootObjects())} root object(s)", flush=True)

    app._lumio_controller = controller
    app._lumio_engine = engine

    app.exec()


# 引入 QmlApplicationEngine 必须的 import（避免循环依赖警告）
from PySide6.QtQml import QQmlApplicationEngine
