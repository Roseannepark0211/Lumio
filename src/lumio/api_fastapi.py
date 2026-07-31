"""Lumio FastAPI 服务 — React + Electron 前端的后端 API。

架构原则（参见 AGENTS.md "架构迁移规则"）：
- **零侵入**：不修改任何现有业务代码（qml_bridge.py / queue_manager.py / providers/* 等）
- **共享数据**：与 QML 版共享 `~/.lumio/` 数据，schema 不变
- **独立启动**：`python -m lumio.api_fastapi` 单独启动，不依赖 QML UI
- **Signal 桥接**：现有 manager 的 Qt Signal 通过 DirectConnection 接到 EventBus，
  WebSocket 推送给前端

API 契约覆盖 QmlController 的 82 个 Slot，分 12 个模块：
1. 下载队列（queue）
2. URL 解析（async，结果走 WebSocket）
3. 历史记录（history）
4. 素材库（library）
5. 收件箱（inbox）
6. 通知（notifications）
7. 统计（stats）
8. 配置 / Cookie / Telegram / Apify（settings）
9. 主题 / 语言 / i18n（i18n）
10. 缓存（cache）
11. 系统操作（sys：剪贴板/打开文件/外部 URL/缩略图代理）
12. 版本检查（update）

WebSocket /ws/events 推送所有 Qt Signal 事件，前端按 type 字段分发。
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("lumio.api")

# ============================================================
# Qt / FastAPI 初始化
# ============================================================
# manager 是 QObject 子类，必须先有 QApplication 实例才能用 Signal
# 这里创建但不 exec() —— Signal emit 通过 DirectConnection 直接调用 callback，
# 不依赖 Qt event loop
from .utils.signal import Qt, QObject, Signal, QApplication

_qt_app: Optional[QApplication] = None


def _ensure_qt_app() -> QApplication:
    global _qt_app
    if _qt_app is None:
        _qt_app = QApplication.instance() or QApplication(sys.argv[:1])
    return _qt_app


# ============================================================
# Inbox ↔ Queue 任务映射
# ============================================================
# task_id → inbox_item_id，用于下载完成/失败/取消时同步更新 inbox 状态
# 仅在 inbox_download / inbox_batch_download 入队时记录，任务终态时清理
_INBOX_TASK_MAP: dict[str, str] = {}
_INBOX_TASK_LOCK = threading.Lock()


def _set_inbox_task_map(task_id: str, inbox_item_id: str) -> None:
    """记录 task_id → inbox_item_id 映射（inbox 入队时调用）。"""
    with _INBOX_TASK_LOCK:
        _INBOX_TASK_MAP[task_id] = inbox_item_id


def _pop_inbox_item_id(task_id: str) -> Optional[str]:
    """取出并移除映射（任务终态时调用）。"""
    with _INBOX_TASK_LOCK:
        return _INBOX_TASK_MAP.pop(task_id, None)


def _sync_inbox_on_task_status(app_ctx: "AppContext", bus: "EventBus",
                               task_id: str, status: str) -> None:
    """task_status_changed 回调中调用，根据任务终态同步更新 inbox 状态。

    - COMPLETED → inbox 标记 downloaded
    - FAILED    → inbox 标记 failed
    - CANCELLED → inbox 恢复为 new（让用户可重新下载）
    其他状态（DOWNLOADING/PAUSED/RETRYING/...）不处理，保留 queued。
    """
    inbox_item_id = _pop_inbox_item_id(task_id)
    if not inbox_item_id:
        return

    new_inbox_status: Optional[str] = None
    # TaskStatus.COMPLETED.value = "已完成"，TaskStatus.FAILED.value = "失败"，
    # TaskStatus.CANCELLED.value = "已取消"
    if status == "已完成":
        new_inbox_status = "downloaded"
    elif status == "失败":
        new_inbox_status = "failed"
    elif status == "已取消":
        new_inbox_status = "new"

    if not new_inbox_status:
        # 非终态，重新放回映射，等终态再处理
        _set_inbox_task_map(task_id, inbox_item_id)
        return

    try:
        # mark_status 会触发 item_updated 信号 → 已桥接到 inbox_changed 事件，
        # 前端会自动 reload，无需显式 publish
        app_ctx.inbox_manager.mark_status(inbox_item_id, new_inbox_status)
    except Exception as e:
        logger.warning("sync inbox status failed task=%s inbox=%s: %s",
                       task_id, inbox_item_id, e)


from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, Response
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from .utils.config import load_config, save_config, get_download_dir, get_cookie_path
from .i18n import t as _i18n_t, set_lang as _i18n_set_lang
from . import mobile_auth  # 移动端鉴权：JWT + 设备 + 配对 + 限流
from . import push_service  # M3: 推送通知服务（Expo Push Server 集成）

# 鉴权白名单：以下 /api/ 路径不需要 JWT/X-Lumio-Token
# - /api/health: 心跳，移动端 useNetworkStatus 用
# - /api/auth/pair-code: 生成配对码（无 JWT，单独限流）
# - /api/auth/pair: 配对（无 JWT，单独限流）
_AUTH_WHITELIST = {"/api/health", "/api/auth/pair-code", "/api/auth/pair", "/api/auth/refresh"}


# ============================================================
# Pydantic 请求模型
# ============================================================

class TaskFromInfoRequest(BaseModel):
    info: dict  # VideoInfo 字典
    format_id: str = ""
    format_type: str = ""
    custom_name: str = ""
    output_dir: str = ""


class TaskFromDirectRequest(BaseModel):
    url: str
    title: str
    platform: str = ""
    thumbnail: str = ""
    is_video: bool = False
    author: str = ""


class InboxBatchRequest(BaseModel):
    ids: list[str]


class ConfigUpdateRequest(BaseModel):
    value: Any


class NestedConfigUpdateRequest(BaseModel):
    updates: dict


class CookieImportRequest(BaseModel):
    paths: list[str]


class TelegramValidateRequest(BaseModel):
    token: str
    proxy: str = ""


class ApifyValidateRequest(BaseModel):
    token: str
    actor_id: str


class SetThemeRequest(BaseModel):
    theme: str  # "light" / "dark"


class SetLangRequest(BaseModel):
    lang: str  # "zh" / "en"


class CopyClipboardRequest(BaseModel):
    text: str


class OpenFileRequest(BaseModel):
    path: str
    source: str = ""  # "library" / "history" / ""


class PreviewTargetRequest(BaseModel):
    """请求预览主文件路径（对 mixed/目录型素材扫描文件夹找主视频/图片）。"""
    file_path: str
    media_type: str = ""


class OpenExternalUrlRequest(BaseModel):
    url: str


class ToastRequest(BaseModel):
    message: str


class PairRequest(BaseModel):
    """移动端配对请求（POST /api/auth/pair）。"""
    pair_code: str = Field(..., min_length=6, max_length=6)
    device_name: str = ""
    # 设备指纹：UA + IP hash（移动端生成）。强烈建议非空，用于 access token 防盗用比对。
    # 保持默认空字符串以兼容旧客户端，但会在日志中警告。
    device_fingerprint: str = ""


class RefreshRequest(BaseModel):
    """refresh token 旋转请求（POST /api/auth/refresh）。

    refresh_token 由客户端 body 提交（不再依赖中间件注入 device_id，
    因 refresh token 不走 access 中间件）。
    """
    refresh_token: str
    # 可选：客户端再次提交 fingerprint，用于服务端比对 JWT 内 fp
    device_fingerprint: str = ""


class MobileEnqueueRequest(BaseModel):
    """移动端入队请求（POST /api/mobile/enqueue）。"""
    url: str
    platform: str = ""
    device_id: str | None = None

class PushRegisterRequest(BaseModel):
    """移动端 push token 注册请求（POST /api/push/register）。"""
    push_token: str
    categories: list[str] = []  # 默认全部订阅


class DeviceRenameRequest(BaseModel):
    """设备重命名请求（PATCH /api/devices/{id}）。"""
    device_name: str


class ParseUrlRequest(BaseModel):
    url: str
    request_id: str = ""


class SearchXSouRequest(BaseModel):
    query: str
    page: int = 1
    limit: int = 20
    request_id: str = ""


class PreviewXVideoRequest(BaseModel):
    video_url: str


# ============================================================
# EventBus — Qt Signal → WebSocket 桥
# ============================================================

class EventBus:
    """跨线程事件总线：Qt Signal callback 写入 asyncio.Queue，WebSocket 消费。

    设计要点：
    - Qt Signal 跨线程 emit 时，DirectConnection 让 callback 在 emit 线程执行
    - callback 内部用 call_soon_threadsafe 把事件投递到 asyncio loop
    - 多个 WebSocket 客户端共享同一份事件流（broadcast）
    """

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._subscribers: list[asyncio.Queue] = []
        self._lock = threading.Lock()

    def publish(self, event_type: str, data: Any = None) -> None:
        """从任意线程发布事件。"""
        event = {"type": event_type, "data": data, "ts": time.time()}
        try:
            self._loop.call_soon_threadsafe(self._do_publish, event)
        except RuntimeError:
            # loop 已关闭（进程退出）
            pass

    def _do_publish(self, event: dict) -> None:
        with self._lock:
            dead: list[asyncio.Queue] = []
            for q in self._subscribers:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    dead.append(q)
            for q in dead:
                try:
                    self._subscribers.remove(q)
                except ValueError:
                    pass

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1024)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass


# ============================================================
# AppContext — 封装所有 manager 实例
# ============================================================

class AppContext:
    """启动时创建所有 manager，与 main.py 的 _init_app_components 等价但不启动 QML。"""

    def __init__(self):
        _ensure_qt_app()
        from .queue_manager import DownloadManager
        from .library_manager import LibraryManager
        from .history_manager import HistoryManager
        from .inbox_manager import InboxManager
        from .notification_manager import NotificationManager, set_notification_manager
        from .api_server import start_server, stop_server

        self.manager = DownloadManager()
        self.manager.load_queue()
        self.library_manager = LibraryManager()
        self.history_manager = HistoryManager()
        self.manager.set_history_manager(self.history_manager)
        self.manager.set_library_manager(self.library_manager)
        self.inbox_manager = InboxManager()
        self.notification_manager = NotificationManager()
        set_notification_manager(self.notification_manager)
        # X-Sou 视频预览的 PreviewWorker 引用（由 /api/preview-x-video 设置，
        # /api/preview-cancel 读取，worker 结束后清空）
        self.preview_worker = None

        cfg = load_config()
        # 浏览器扩展的 /capture API 仍由原 Flask 服务提供（端口 38900）
        # 传入 queue_manager 让 /stats 也能返回队列统计
        start_server(self.inbox_manager, self.manager, port=cfg.get("api_port", 38900))
        self._stop_flask = stop_server

        # Telegram Bot
        self.tg_service = None
        if cfg.get("telegram_enabled") and cfg.get("telegram_bot_token"):
            try:
                from .telegram_service import TelegramService
                self.tg_service = TelegramService(self.inbox_manager)
                self.tg_service.start_polling()
            except Exception as e:
                logger.warning("Telegram service start failed: %s", e)

        # 启动时检测环境（C4: 改后台线程，避免阻塞 startup event 让 /api/health 立即 ready）
        def _bg_check_all() -> None:
            try:
                self.notification_manager.check_all()
            except Exception:
                pass
        threading.Thread(target=_bg_check_all, daemon=True, name="notif-check").start()

        # 缓存自动清理
        threading.Thread(target=self._auto_clean_cache, daemon=True).start()

        # Apify 用量缓存（与 QmlController._apify_usage_cache 等价）
        self._apify_usage_cache: dict = {"_ts": 0}

    @staticmethod
    def _auto_clean_cache() -> None:
        try:
            from .utils.cache_manager import run_auto_clean_if_needed
            run_auto_clean_if_needed()
        except Exception:
            pass

    def shutdown(self) -> None:
        try:
            if self.tg_service:
                self.tg_service.stop_polling()
        except Exception:
            pass
        try:
            self._stop_flask()
        except Exception:
            pass
        try:
            self.manager.shutdown()
        except Exception:
            pass


# ============================================================
# 序列化辅助（与 qml_bridge.py 内部函数对齐）
# ============================================================

def _task_to_dict(qt) -> dict:
    return {
        "task_id": qt.task_id,
        "url": qt.url,
        "format_id": getattr(qt, "format_id", "") or "",
        "format_type": getattr(qt, "format_type", "") or "",
        "output_dir": qt.output_dir or "",
        "custom_name": getattr(qt, "custom_name", "") or "",
        "batch_id": getattr(qt, "batch_id", "") or "",
        "direct_url": getattr(qt, "direct_url", "") or "",
        "media_items_json": getattr(qt, "media_items_json", "") or "",
        "title": qt.title or "",
        "platform": qt.platform or "",
        "author": qt.author or "",
        "post_time": qt.post_time or "",
        "thumbnail_url": qt.thumbnail_url or "",
        "status": qt.status,
        "progress": getattr(qt, "progress", 0.0),
        "speed": getattr(qt, "speed", "") or "",
        "filename": getattr(qt, "filename", "") or "",
        "error": getattr(qt, "error", "") or "",
        "media_type": getattr(qt, "media_type", "") or "",
        "retry_count": getattr(qt, "retry_count", 0),
        "max_retries": getattr(qt, "max_retries", 3),
        "created_at": getattr(qt, "created_at", 0.0),
    }


def _history_to_dict(r) -> dict:
    return {
        "id": r.record_id,
        "url": r.url,
        "title": r.title or "",
        "platform": r.platform or "",
        "author": r.author or "",
        "file_path": r.file_path or "",
        "file_size": r.file_size,
        "thumbnail_url": r.thumbnail_url or "",
        "media_type": getattr(r, "media_type", "") or "",
        "success": r.success,
        "error": getattr(r, "error", "") or "",
        "download_time": r.download_time or "",
        "post_time": getattr(r, "post_time", "") or "",
        "batch_id": r.batch_id or "",
    }


def _library_item_to_dict(it, lib_mgr) -> dict:
    # 收集该素材已加入的 Collection id 列表（供前端按分类筛选）
    # 与 qml_bridge.py 保持一致（参考 AGENTS.md "Collection sidebar" 行为）
    collection_ids: list[int] = []
    if lib_mgr is not None:
        try:
            collection_ids = [c.id for c in lib_mgr.get_item_collections(it.id)]
        except Exception:
            pass
    return {
        "id": it.id,
        "title": it.title or "",
        "url": it.url or "",
        "platform": it.platform or "",
        "author": it.author or "",
        "file_path": it.file_path or "",
        "file_size": it.file_size,
        "media_type": it.media_type or "",
        "is_favorite": bool(it.is_favorite),
        "post_time": it.post_time or "",
        "created_at": it.created_at.isoformat() if it.created_at else "",
        "thumbnail_url": it.thumbnail_url or "",
        "thumbnail_path": it.local_thumbnail_path or "",
        "folder_path": it.folder_path or "",
        "batch_id": it.batch_id or "",
        "content_hash": it.content_hash or "",
        "duration": it.duration or 0,
        "collection_ids": collection_ids,
    }


def _inbox_item_to_dict(it) -> dict:
    # InboxItem 模型字段名为 `type`（url/video/image），不是 `media_type`
    # 时间字段名为 `captured_at`（QML InboxPage.qml 使用），不是 `created_at`
    return {
        "id": it.id,
        "url": it.url or "",
        "direct_url": it.direct_url or "",
        "title": it.title or "",
        "platform": it.platform or "",
        "author": it.author or "",
        "thumbnail_url": it.thumbnail_url or "",
        "type": it.type or "",
        "media_type": it.type or "",  # 兼容其他页面统一字段名
        "status": it.status or "new",
        "source": it.source or "",
        "post_time": it.post_time or "",
        "duration": getattr(it, "duration", 0) or 0,
        "captured_at": it.captured_at.isoformat() if it.captured_at else "",
        "created_at": it.created_at.isoformat() if it.created_at else "",
        "content": getattr(it, "content", "") or "",
        "error_message": getattr(it, "error_message", "") or "",
    }


def _notification_to_dict(n) -> dict:
    # 字段名与 Notification dataclass 对齐（notification_manager.py）
    # 旧版误用 level/body/action_label/action_url/is_read，实际字段是
    # type/message/action/action_text/read
    # 注意：created_at 在 dataclass 中是 str（ISO 格式字符串，由
    # datetime.now(timezone.utc).isoformat() 生成），不是 datetime 对象，
    # 不能调 .isoformat()，否则 AttributeError
    created_at = n.created_at
    if hasattr(created_at, "isoformat"):
        created_at = created_at.isoformat()
    return {
        "id": n.id,
        "category": n.category,
        "type": getattr(n, "type", "info"),
        "priority": getattr(n, "priority", "normal"),
        "title": n.title or "",
        "message": n.message or "",
        "action": n.action or "",
        "action_text": getattr(n, "action_text", "") or "",
        "source_key": getattr(n, "source_key", "") or "",
        "expires_at": getattr(n, "expires_at", "") or "",
        "group_key": getattr(n, "group_key", "") or "",
        "dismissable": bool(n.dismissable),
        "read": bool(n.read),
        # 向后兼容旧字段名（QML 旧版/其他客户端可能引用）
        "is_read": bool(n.read),
        "level": getattr(n, "type", "info"),
        "body": n.message or "",
        "action_label": getattr(n, "action_text", "") or "",
        "action_url": n.action or "",
        "created_at": created_at or "",
    }


# ============================================================
# 文件操作辅助（与 qml_bridge._openFileWithSource 等价）
# ============================================================

def _first_openable_media(folder: str) -> str | None:
    media_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp",
                  ".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv",
                  ".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg"}
    try:
        p = Path(folder)
        files = sorted(f for f in p.iterdir() if f.is_file() and f.suffix.lower() in media_exts)
        return str(files[0]) if files else None
    except OSError:
        return None


# 视频优先 → 图片 → 音频，用于 mixed 类型预览
_PREVIEW_VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".m4v"}
_PREVIEW_IMAGE_EXTS = {".jpg", ".jpeg", ".jfif", ".pjpeg", ".pjp", ".png", ".gif", ".webp", ".bmp", ".svg", ".avif", ".heic", ".heif"}
_PREVIEW_AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus"}


def _resolve_preview_target(file_path: str, media_type: str) -> tuple[str, str]:
    """对 mixed / 目录型素材，扫描文件夹返回 (主文件路径, 单一类型)。

    优先级：视频 > 图片 > 音频。若 file_path 是文件直接返回。
    返回的 media_type 为单一类型（video/image/audio），不再有 mixed。
    """
    if not file_path:
        return "", ""
    p = Path(file_path)
    if p.is_file():
        ext = p.suffix.lower()
        if ext in _PREVIEW_VIDEO_EXTS:
            return str(p), "video"
        if ext in _PREVIEW_IMAGE_EXTS:
            return str(p), "image"
        if ext in _PREVIEW_AUDIO_EXTS:
            return str(p), "audio"
        return str(p), media_type
    if p.is_dir():
        try:
            files = sorted(f for f in p.iterdir() if f.is_file())
        except OSError:
            return "", ""
        # 优先视频
        for f in files:
            if f.suffix.lower() in _PREVIEW_VIDEO_EXTS:
                return str(f), "video"
        # 其次图片
        for f in files:
            if f.suffix.lower() in _PREVIEW_IMAGE_EXTS:
                return str(f), "image"
        # 最后音频
        for f in files:
            if f.suffix.lower() in _PREVIEW_AUDIO_EXTS:
                return str(f), "audio"
        return "", ""
    return "", ""


def _list_preview_items(file_path: str) -> list[dict]:
    """列出文件夹内所有可预览媒体文件，按 video → image → audio 排序。

    用于 MediaPreviewDialog 上下项切换。返回 [{"path": "...", "media_type": "video"}]。
    单文件返回 [{"path": file_path, "media_type": 推断类型}]。
    """
    if not file_path:
        return []
    p = Path(file_path)
    if p.is_file():
        ext = p.suffix.lower()
        if ext in _PREVIEW_VIDEO_EXTS:
            return [{"path": str(p), "media_type": "video"}]
        if ext in _PREVIEW_IMAGE_EXTS:
            return [{"path": str(p), "media_type": "image"}]
        if ext in _PREVIEW_AUDIO_EXTS:
            return [{"path": str(p), "media_type": "audio"}]
        return []
    if p.is_dir():
        try:
            files = sorted(f for f in p.iterdir() if f.is_file())
        except OSError:
            return []
        items: list[dict] = []
        # 先视频，再图片，最后音频（与 _resolve_preview_target 优先级一致）
        for f in files:
            if f.suffix.lower() in _PREVIEW_VIDEO_EXTS:
                items.append({"path": str(f), "media_type": "video"})
        for f in files:
            if f.suffix.lower() in _PREVIEW_IMAGE_EXTS:
                items.append({"path": str(f), "media_type": "image"})
        for f in files:
            if f.suffix.lower() in _PREVIEW_AUDIO_EXTS:
                items.append({"path": str(f), "media_type": "audio"})
        return items
    return []


def _open_path(path: str, source: str = "") -> tuple[bool, str]:
    """打开文件 / 目录，返回 (success, error_msg)。
    source: "library" / "history" / "" — 缺失时通过 EventBus 推 file_missing 事件。
    """
    if not path:
        return False, "empty path"
    try:
        target = path
        if os.path.isdir(path):
            target = _first_openable_media(path) or path
        if not os.path.exists(target):
            return False, "not_found"
        if sys.platform == "win32":
            ext = os.path.splitext(target)[1].lower()
            if ext in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}:
                try:
                    subprocess.Popen(
                        ["cmd", "/c", "start", "", f"ms-photos:viewer?fileName={target}"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                    return True, ""
                except Exception:
                    os.startfile(target)  # type: ignore[attr-defined]
                    return True, ""
            os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
        return True, ""
    except Exception as e:
        return False, str(e)


def _open_folder(path: str, source: str = "") -> tuple[bool, str]:
    if not path:
        return False, "empty path"
    try:
        if not os.path.exists(path):
            return False, "not_found"
        folder = os.path.dirname(path) if os.path.isfile(path) else path
        if sys.platform == "win32":
            os.startfile(folder)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])
        return True, ""
    except Exception as e:
        return False, str(e)


# ============================================================
# FastAPI app + 路由
# ============================================================

def create_app() -> FastAPI:
    """创建 FastAPI 应用并绑定所有路由。"""
    app = FastAPI(
        title="Lumio API",
        description="React + Electron 前端的后端 API（覆盖 QmlController 全部 82 个 Slot）",
        version="3.2.0-api",
    )

    # 中间件顺序（Starlette 栈式：后添加的先执行/外层）：
    #   请求 → CORSMiddleware（外层）→ TokenAuthMiddleware（内层）→ 路由
    #   响应 → 路由 → TokenAuthMiddleware → CORSMiddleware → 返回
    # 关键：CORSMiddleware 必须在最外层，确保所有响应（包括 TokenAuth 的 401）
    #       都带 CORS 头，否则浏览器报 CORS 错误而非真实的 401
    expected_token = os.environ.get("LUMIO_FASTAPI_TOKEN", "")

    def _build_request_fingerprint(request: Request) -> str:
        """服务端基于请求生成设备指纹：SHA256(UA + "|" + IP) 取前 16 hex。

        与移动端约定一致（移动端在 pair 时提交相同算法的 fp，存入 device 记录）。
        用于 verify_token 比对：access token 内 fp 必须与当前请求 fp 匹配，
        防 token 被盗用到其他设备/网络。
        """
        ua = request.headers.get("User-Agent", "")
        ip = request.client.host if request.client else "unknown"
        import hashlib
        return hashlib.sha256(f"{ua}|{ip}".encode("utf-8")).hexdigest()[:16]

    class TokenAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # BaseHTTPMiddleware 对 WebSocket scope 处理有 bug：
            # Starlette 0.36+ 在 ws.accept() 前会先经过 BaseHTTPMiddleware，
            # 但 dispatch 拿到的 request 对 ws scope 不完整，
            # 任何对 request.headers / request.url 的访问都可能触发异常，
            # 异常被 Starlette 吞掉后 ws 被强制关闭 → 前端报
            # "WebSocket is closed before the connection is established"
            # 解决：WS 请求直接放行，不进入 HTTP 鉴权分支
            # WS 鉴权改在 ws_events 内部用 query token 检查
            if request.scope.get("type") == "websocket":
                return await call_next(request)
            # 鉴权策略：移动端 Bearer JWT 或 Electron X-Lumio-Token，任一通过即可
            # 白名单（/api/health / /api/auth/pair-code / /api/auth/pair / /api/auth/refresh）+ OPTIONS 不鉴权
            path = request.url.path
            if path.startswith("/api/") and request.method != "OPTIONS" \
                    and path not in _AUTH_WHITELIST:
                # 1. 移动端路径：Authorization: Bearer <access_jwt>
                bearer = mobile_auth.extract_bearer_token(
                    request.headers.get("Authorization", ""))
                if bearer:
                    # 服务端生成当前请求指纹，传给 verify_token 比对
                    # （旧 JWT 无 fp 字段时跳过比对，向后兼容）
                    req_fp = _build_request_fingerprint(request)
                    payload = mobile_auth.verify_token(bearer, expected_fp=req_fp)
                    if payload is None:
                        return JSONResponse(status_code=401,
                                            content={"detail": "invalid jwt"})
                    # 中间件已校验通过，把 device_id 注入 request.state 供 handler 使用
                    request.state.device_id = payload.get("device_id")
                    return await call_next(request)
                # 2. Electron 路径：X-Lumio-Token header 或 ?token= 兜底
                if expected_token:
                    token = request.headers.get("X-Lumio-Token", "") \
                        or request.query_params.get("token", "")
                    if token == expected_token:
                        return await call_next(request)
                    return JSONResponse(status_code=401,
                                        content={"detail": "invalid token"})
                # 3. 既无 Bearer 也无 X-Lumio-Token 配置：dev mode（无 LUMIO_FASTAPI_TOKEN），
                #    保留原 dev 行为允许通过
            return await call_next(request)

    # 始终注册 TokenAuthMiddleware：
    #   - 移动端 Bearer JWT 校验不依赖 LUMIO_FASTAPI_TOKEN（否则 dev mode 配对无法工作）
    #   - expected_token 仅决定 Electron 路径（X-Lumio-Token）校验严格度
    # 中间件内部三分支：Bearer JWT → X-Lumio-Token → dev mode 放行（无 token 配置时）
    app.add_middleware(TokenAuthMiddleware)

    # ============================================================
    # 阶段3传输加密：HSTS + 安全头 + HTTPS 重定向 + CORS 白名单
    # ============================================================
    # HSTS（HTTP Strict Transport Security）+ 安全响应头中间件
    # 仅在 HTTPS 请求响应中添加 HSTS（HTTP 响应添加 HSTS 会被中间人利用）
    # dev mode（本地 127.0.0.1）不添加 HSTS，避免开发时证书问题
    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            response = await call_next(request)
            # 仅 HTTPS 请求添加 HSTS（防中间人降级）
            if request.url.scheme == "https":
                response.headers["Strict-Transport-Security"] = \
                    "max-age=63072000; includeSubDomains; preload"  # 2 年
            # 通用安全头（HTTP/HTTPS 均添加）
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            return response

    app.add_middleware(SecurityHeadersMiddleware)

    # HTTPS 强制重定向（仅外网部署启用，dev mode 关闭）
    # 通过 LUMIO_FORCE_HTTPS=1 启用，Cloudflare Tunnel/Tailscale Funnel 部署时设置
    if os.environ.get("LUMIO_FORCE_HTTPS", "") == "1":
        app.add_middleware(HTTPSRedirectMiddleware)
        log.info("HTTPS redirect enabled (LUMIO_FORCE_HTTPS=1)")

    # CORS 白名单：从 LUMIO_CORS_ORIGINS 环境变量读取（逗号分隔）
    # 未设置时回退到 ["*"]（dev mode 兼容）
    # 外网部署示例：LUMIO_CORS_ORIGINS=https://lumio.example.com,https://app.lumio.io
    cors_env = os.environ.get("LUMIO_CORS_ORIGINS", "").strip()
    if cors_env:
        cors_origins = [o.strip() for o in cors_env.split(",") if o.strip()]
        log.info("CORS origins: %s", cors_origins)
    else:
        cors_origins = ["*"]  # dev mode 兼容
    # 后 add CORSMiddleware（外层）— 必须最后 add 才能在最外层
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # EventBus 需要 asyncio loop，延迟到 startup 创建
    ctx: dict[str, Any] = {}

    @app.on_event("startup")
    def _startup() -> None:
        loop = asyncio.get_event_loop()
        ctx["loop"] = loop
        ctx["bus"] = EventBus(loop)
        push_service.install_event_hook(ctx["bus"])  # M3: 安装 push 事件钩子
        ctx["app_ctx"] = AppContext()
        # 绑定 Qt Signal → EventBus
        _wire_signals(ctx["app_ctx"], ctx["bus"])
        logger.info("Lumio FastAPI started")
        # 后台启动缩略图补生成（local_thumbnail_path 缺失或文件被清理时）
        try:
            def _bg_backfill():
                import threading
                def _run():
                    try:
                        _ctx().library_manager.backfill_thumbnails()
                    except Exception as e:
                        logger.warning("backfill_thumbnails failed: %s", e)
                t = threading.Thread(target=_run, daemon=True, name="backfill-thumbs")
                t.start()
            _bg_backfill()
        except Exception:
            pass

    @app.on_event("shutdown")
    def _shutdown() -> None:
        if "app_ctx" in ctx:
            ctx["app_ctx"].shutdown()

    # -------- 辅助 getter --------
    def _ctx() -> AppContext:
        return ctx["app_ctx"]

    def _bus() -> EventBus:
        return ctx["bus"]

    # ============================================================
    # 1. 下载队列
    # ============================================================

    @app.get("/api/queue")
    async def get_queue() -> list[dict]:
        return [_task_to_dict(t) for t in _ctx().manager.get_all_tasks()]

    @app.post("/api/queue/task/from-info")
    async def add_task_from_info(req: TaskFromInfoRequest) -> dict:
        from .utils.media_utils import VideoInfo, MediaItem
        info_data = req.info
        items = [MediaItem(
            url=it.get("url", ""),
            is_video=it.get("is_video", False),
            media_type=it.get("media_type", ""),
            width=it.get("width", 0),
            height=it.get("height", 0),
            extension=it.get("extension", ""),
            size=it.get("size", 0),
            quality=it.get("quality", ""),
            filename=it.get("filename", ""),
        ) for it in info_data.get("items", [])]
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
        out_dir = req.output_dir or str(get_download_dir())
        try:
            task_id = _ctx().manager.add_task_from_info(
                info=info,
                format_id=req.format_id or None,
                format_type=req.format_type,
                custom_name=req.custom_name,
                output_dir=out_dir,
            )
            return {"task_id": task_id}
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(500, str(e))

    @app.post("/api/queue/task/from-direct")
    async def add_task_from_direct(req: TaskFromDirectRequest) -> dict:
        from .queue_manager import QueueTask
        thumb = req.thumbnail or ("" if req.is_video else req.url)
        qt = QueueTask(
            url=req.url,
            direct_url=req.url,
            title=req.title,
            platform=req.platform,
            author=req.author,
            custom_name=req.title,
            thumbnail_url=thumb or None,
            output_dir=str(get_download_dir()),
        )
        qt.media_items_json = json.dumps([{
            "url": req.url, "is_video": req.is_video, "index": 0,
        }])
        _ctx().manager.add_task(qt)
        return {"task_id": qt.task_id}

    @app.post("/api/queue/tasks/{task_id}/start")
    async def start_task(task_id: str) -> dict:
        _ctx().manager.start_task(task_id)
        return {"ok": True}

    @app.post("/api/queue/tasks/{task_id}/pause")
    async def pause_task(task_id: str) -> dict:
        _ctx().manager.pause_task(task_id)
        return {"ok": True}

    @app.post("/api/queue/tasks/{task_id}/resume")
    async def resume_task(task_id: str) -> dict:
        _ctx().manager.resume_task(task_id)
        return {"ok": True}

    @app.post("/api/queue/tasks/{task_id}/cancel")
    async def cancel_task(task_id: str) -> dict:
        _ctx().manager.cancel_task(task_id)
        return {"ok": True}

    @app.post("/api/queue/tasks/{task_id}/retry")
    async def retry_task(task_id: str) -> dict:
        _ctx().manager.retry_task(task_id)
        return {"ok": True}

    @app.delete("/api/queue/tasks/{task_id}")
    async def delete_task(task_id: str) -> dict:
        _ctx().manager.delete_task(task_id)
        return {"ok": True}

    @app.post("/api/queue/start-all")
    async def start_all() -> dict:
        _ctx().manager.start_all()
        return {"ok": True}

    @app.post("/api/queue/pause-all")
    async def pause_all() -> dict:
        _ctx().manager.pause_all()
        return {"ok": True}

    @app.post("/api/queue/resume-all")
    async def resume_all() -> dict:
        _ctx().manager.resume_all()
        return {"ok": True}

    @app.get("/api/queue/check-url-duplicate")
    async def check_url_duplicate(url: str = Query(...)) -> dict:
        return {"duplicate": bool(_ctx().manager.check_url_duplicate(url))}

    # ============================================================
    # 1.5. 移动端鉴权 / 配对 / 设备管理（新增，见联调验证.md）
    # ============================================================

    @app.post("/api/auth/pair-code")
    async def gen_pair_code(request: Request) -> dict:
        """生成 6 位配对码（5 分钟过期）。限流 5/min/IP。

        桌面端设置页/临时 API 调用，无需任何鉴权。
        """
        client_ip = request.client.host if request.client else "unknown"
        if not mobile_auth.rate_limit_check(f"pair-code:{client_ip}", 5):
            return JSONResponse(status_code=429, content={"detail": "rate limit"})
        code = mobile_auth.generate_pair_code()
        return {"pair_code": code, "expires_in": 300}

    @app.post("/api/auth/pair")
    async def pair(req: PairRequest, request: Request) -> dict:
        """配对：校验配对码 + 注册设备 + 签发 access + refresh 双 token。

        限流 5/min/IP。成功后返回：
        - access_token (2h) + access_expires_at
        - refresh_token (30d) + refresh_expires_at
        - device_id + host_version
        - [兼容] jwt / expires_at 字段（= access_token，供旧客户端使用）
        """
        client_ip = request.client.host if request.client else "unknown"
        if not mobile_auth.rate_limit_check(f"pair:{client_ip}", 5):
            return JSONResponse(status_code=429, content={"detail": "rate limit"})
        if not mobile_auth.validate_pair_code(req.pair_code):
            return JSONResponse(
                status_code=401,
                content={"detail": "invalid or expired pair code"},
            )
        # 设备指纹为空时记日志（不阻断，保持向后兼容）
        if not req.device_fingerprint:
            log.warning("pair: device_fingerprint empty, pair_code=%s", req.pair_code)
        device = mobile_auth.register_device(req.device_name, req.device_fingerprint)
        # 签发双 token
        access_token, access_exp = mobile_auth.issue_access_jwt(
            device["device_id"], req.device_fingerprint
        )
        refresh_token, _jti, refresh_exp = mobile_auth.issue_refresh_jwt(
            device["device_id"], req.device_fingerprint
        )
        return {
            # 新双 token 字段
            "access_token": access_token,
            "access_expires_at": access_exp,
            "refresh_token": refresh_token,
            "refresh_expires_at": refresh_exp,
            # 兼容旧客户端：jwt / expires_at（= access_token）
            "jwt": access_token,
            "expires_at": access_exp,
            "device_id": device["device_id"],
            "host_version": __import__("lumio").__version__,
        }

    @app.get("/api/auth/me")
    async def auth_me(request: Request) -> dict:
        """返回当前设备信息（device_id 由中间件注入 request.state）。"""
        device_id = getattr(request.state, "device_id", None)
        if not device_id:
            return JSONResponse(status_code=401, content={"detail": "no device"})
        device = mobile_auth.get_device(device_id)
        if not device:
            return JSONResponse(status_code=404, content={"detail": "device not found"})
        mobile_auth.touch_device_active(device_id)
        return {
            "device_id": device["device_id"],
            "device_name": device["device_name"],
            "device_fingerprint": device["device_fingerprint"],
            "paired_at": device["paired_at"],
            "last_active_at": device["last_active_at"],
            "is_current": True,
        }

    @app.post("/api/auth/refresh")
    async def auth_refresh(req: RefreshRequest, request: Request) -> dict:
        """refresh token 旋转：旧 refresh → 新 access + 新 refresh。

        此端点在 _AUTH_WHITELIST 中（不走 access 中间件），自行校验 refresh token。
        一次性使用：旧 refresh 的 jti 立即加入黑名单。

        成功返回 access_token + refresh_token + expires_at。
        失败返回 401（refresh token 无效/已旋转/已撤销/设备已撤销）。
        """
        client_ip = request.client.host if request.client else "unknown"
        if not mobile_auth.rate_limit_check(f"refresh:{client_ip}", 10):
            return JSONResponse(status_code=429, content={"detail": "rate limit"})
        result = mobile_auth.rotate_refresh_token(req.refresh_token, req.device_fingerprint)
        if result is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "invalid or expired refresh token"},
            )
        mobile_auth.touch_device_active(result["device_id"])
        return {
            "access_token": result["access_token"],
            "access_expires_at": result["access_expires_at"],
            "refresh_token": result["refresh_token"],
            "refresh_expires_at": result["refresh_expires_at"],
            # 兼容旧客户端
            "jwt": result["access_token"],
            "expires_at": result["access_expires_at"],
            "device_id": result["device_id"],
            "host_version": __import__("lumio").__version__,
        }

    @app.post("/api/auth/logout")
    async def auth_logout(request: Request) -> Response:
        """吊销当前设备的 JWT。"""
        device_id = getattr(request.state, "device_id", None)
        if device_id:
            mobile_auth.revoke_device(device_id)
        return Response(status_code=204)

    @app.get("/api/devices")
    async def list_devices_endpoint() -> list[dict]:
        """列出所有已配对设备（桌面端设置页用）。"""
        return mobile_auth.list_devices()

    @app.patch("/api/devices/{device_id}")
    async def rename_device_endpoint(device_id: str, req: DeviceRenameRequest) -> dict:
        """重命名设备。"""
        device = mobile_auth.rename_device(device_id, req.device_name)
        if not device:
            return JSONResponse(status_code=404, content={"detail": "device not found"})
        return device

    @app.delete("/api/devices/{device_id}")
    async def revoke_device_endpoint(device_id: str) -> Response:
        """撤销设备（吊销其 JWT）。"""
        if not mobile_auth.revoke_device(device_id):
            return JSONResponse(status_code=404, content={"detail": "device not found"})
        return Response(status_code=204)

    # ============================================================
    # 1.6. 移动端入队（核心，新增）
    # ============================================================

    @app.post("/api/mobile/enqueue")
    async def mobile_enqueue(req: MobileEnqueueRequest, request: Request) -> dict:
        """移动端 URL 入队：立即返回 request_id，异步解析+入队，结果走 WS。

        WS 事件流（移动端订阅 /ws/events 接收）：
        - 解析完成 -> parse_completed {request_id, info: VideoInfo}
        - 入队后   -> task_added（由 _wire_signals 自动 publish，含 task_id）
        - 解析失败 -> parse_failed {request_id, error}
        """
        import secrets as _secrets
        request_id = _secrets.token_hex(8)
        url = (req.url or "").strip()
        if not url:
            return JSONResponse(status_code=400, content={"detail": "empty url"})

        async def _run() -> None:
            try:
                from .downloader import extract_info
                info = await asyncio.to_thread(extract_info, url)
                _bus().publish("parse_completed", {
                    "request_id": request_id,
                    "info": _video_info_to_dict(info),
                })
                # 入队：默认最高画质（移动端不暴露格式选择，spec 规定）
                format_type = "image" if any(
                    not it.is_video for it in (info.items or [])
                ) else "video"
                format_id = "best"
                if info.formats:
                    f0 = info.formats[0]
                    if isinstance(f0, dict):
                        format_id = f0.get("format_id", "best") or "best"
                _ctx().manager.add_task_from_info(
                    info=info,
                    format_id=format_id,
                    format_type=format_type,
                    custom_name="",
                    output_dir=str(get_download_dir()),
                )
                # task_added 事件由 _wire_signals 自动 publish，不在此重复
            except Exception as e:
                logger.exception("mobile_enqueue failed url=%s", url)
                _bus().publish("parse_failed", {
                    "request_id": request_id, "error": str(e),
                })

        asyncio.create_task(_run())
        return {"request_id": request_id, "status": "parsing"}

# ============================================================
    # 1.7. 推送通知（M3，新增）
    # ============================================================

    @app.post("/api/push/register")
    async def push_register(req: PushRegisterRequest, request: Request) -> dict:
        """注册设备的 Expo Push Token。

        鉴权：JWT（device_id 从 Authorization Bearer 提取）。
        幂等：同一 device_id 多次注册覆盖旧 token。
        """
        device_id = request.state.device_id  # TokenAuthMiddleware 注入
        if not device_id:
            raise HTTPException(status_code=401, detail="unauthorized")
        ok = push_service.register_push_token(
            device_id=device_id,
            push_token=req.push_token,
            categories=req.categories,
        )
        if not ok:
            raise HTTPException(status_code=400, detail="invalid token")
        return {"registered": True, "device_id": device_id}

    @app.delete("/api/push/register")
    async def push_unregister(request: Request) -> dict:
        """注销 push token（关闭通知 / 解除配对时调用）。"""
        device_id = request.state.device_id
        if device_id:
            push_service.unregister_push_token(device_id)
        return {"unregistered": True}

    @app.post("/api/push/test")
    async def push_test(request: Request) -> dict:
        """发送测试推送（设置页"测试通知"按钮触发）。"""
        device_id = request.state.device_id
        if not device_id:
            raise HTTPException(status_code=401, detail="unauthorized")
        sent = push_service.send_test_push(device_id)
        if not sent:
            # 没注册 push token 或发送失败
            raise HTTPException(
                status_code=409,
                detail="no push token registered or send failed",
            )
        return {"sent": True}

    # ============================================================
    # 2. URL 解析（异步，结果走 WebSocket）
    # ============================================================

    @app.post("/api/parse-url")
    async def parse_url(req: ParseUrlRequest) -> dict:
        """异步解析 URL，结果通过 WS 事件 parse_completed / parse_failed 推送。"""
        from .utils.url_parser import extract_url_from_text, parse_url as _parse_url
        url = (req.url or "").strip()
        if not url:
            return {"ok": False, "error": "empty"}
        url = extract_url_from_text(url) or url
        rid = req.request_id or f"parse_{int(time.time()*1000)}"

        # 主页/频道/播放列表批量导入功能未迁移到 React 前端
        # 立即返回错误，避免 yt-dlp 在频道 URL 上挂起导致前端一直显示「解析中」
        try:
            parsed = _parse_url(url)
            if parsed.kind in ("profile", "channel", "playlist"):
                _bus().publish("parse_failed", {
                    "request_id": rid,
                    "error": "主页/频道/播放列表批量导入功能暂未实现，请使用单帖链接",
                })
                return {"ok": False, "error": "profile_not_supported"}
        except Exception:
            # 解析失败时让后续 extract_info 报具体错误
            pass

        async def _run() -> None:
            try:
                from .downloader import extract_info
                info = await asyncio.to_thread(extract_info, url)
                # 序列化 VideoInfo
                _bus().publish("parse_completed", {
                    "request_id": rid,
                    "info": _video_info_to_dict(info),
                })
            except Exception as e:
                _bus().publish("parse_failed", {
                    "request_id": rid, "error": str(e),
                })

        asyncio.create_task(_run())
        return {"ok": True, "request_id": rid}

    @app.post("/api/search-xsou")
    async def search_xsou(req: SearchXSouRequest) -> dict:
        rid = req.request_id or f"search_{int(time.time()*1000)}"
        q = (req.query or "").strip()
        if not q:
            return {"ok": False, "error": "empty"}

        async def _run() -> None:
            try:
                from .x_sou_client import x_sou_search
                results = await asyncio.to_thread(
                    x_sou_search, q, req.page or 1, req.limit or 20
                )
                _bus().publish("search_completed", {
                    "request_id": rid,
                    "results": results,
                })
            except Exception as e:
                _bus().publish("search_failed", {
                    "request_id": rid, "error": str(e),
                })

        asyncio.create_task(_run())
        return {"ok": True, "request_id": rid}

    @app.post("/api/preview-x-video")
    async def preview_x_video(req: PreviewXVideoRequest) -> dict:
        """X-Sou 视频预览：后台下载到 cache/preview，完成后 WS 推 preview_ready。

        可靠性设计：
        - worker 的 finished_ok/failed signal 用 DirectConnection 连接，理论上能在 worker
          线程内同步触发 callback。但 PySide6 signal 在 QThread 子线程 emit 时偶发丢失
          （特别是 emit 后立即 return，QThread 退出），导致前端 preview_ready 事件丢失，
          进度对话框卡在 99%。
        - 修复：保留 signal 连接（向后兼容 QML 版本），同时用 asyncio.to_thread(worker.wait)
          在线程池等待 worker 退出，根据 dest 文件是否存在手动 publish preview_ready/preview_failed。
          这条路径不依赖 signal，是可靠兜底。
        """
        if not req.video_url:
            return {"ok": False, "error": "empty"}

        async def _run() -> None:
            try:
                from .utils.preview_worker import PreviewWorker
                from .utils.cache_manager import get_preview_cache_path
                # PreviewWorker 用 threading.Thread，不依赖 QApplication
                worker = PreviewWorker(
                    req.video_url,
                    on_progress=lambda d, t: _bus().publish(
                        "preview_progress",
                        {"downloaded": d, "total": t},
                    ),
                    on_finished=lambda path: _bus().publish("preview_ready", {"path": path}),
                    on_failed=lambda err: _bus().publish("preview_failed", {"error": err}),
                )
                # 维护 worker 引用，供 /api/preview-cancel 取消
                _ctx().preview_worker = worker
                worker.start()
                # 不阻塞当前协程；在线程池等待 worker 退出，退出后用 dest 文件存在性兜底
                # publish preview_ready/preview_failed，避免回调丢失导致前端卡住
                await asyncio.to_thread(worker.wait)
                # worker 退出后检查 dest 文件是否存在（不依赖回调是否触发）
                # 仅在前端还没收到 preview_ready/preview_failed 时兜底
                # 这里没有简单方法判断"是否已 publish"，所以直接 publish 一次，
                # 前端收到重复 preview_ready 时 setPreviewDialogOpen(true) 是幂等的
                dest = get_preview_cache_path(req.video_url)
                if dest.exists() and dest.stat().st_size > 0:
                    _bus().publish("preview_ready", {"path": str(dest)})
                else:
                    # 文件不存在 → 下载失败或被取消
                    _bus().publish("preview_failed", {"error": "download failed"})
                # worker 退出后清理引用
                _ctx().preview_worker = None
            except Exception as e:
                _bus().publish("preview_failed", {"error": str(e)})
                _ctx().preview_worker = None

        asyncio.create_task(_run())
        return {"ok": True}

    @app.post("/api/preview-cancel")
    async def preview_cancel() -> dict:
        """取消 X-Sou 视频预览下载。"""
        worker = getattr(_ctx(), "preview_worker", None)
        if worker is not None and worker.is_alive():
            worker.cancel()
            return {"ok": True}
        return {"ok": False, "error": "no active preview"}

    # ============================================================
    # 3. 历史记录
    # ============================================================

    @app.get("/api/history")
    async def get_history() -> list[dict]:
        return [_history_to_dict(r) for r in _ctx().history_manager.records]

    @app.delete("/api/history/{record_id}")
    async def delete_history(record_id: str) -> dict:
        _ctx().history_manager.delete(record_id)
        _bus().publish("history_changed")
        return {"ok": True}

    @app.delete("/api/history")
    async def clear_history() -> dict:
        _ctx().history_manager.clear()
        _bus().publish("history_changed")
        return {"ok": True}

    # ============================================================
    # 4. 素材库
    # ============================================================

    @app.get("/api/library")
    async def get_library() -> list[dict]:
        return [_library_item_to_dict(it, _ctx().library_manager)
                for it in _ctx().library_manager.get_all_items()]

    @app.post("/api/library/items/{item_id}/favorite")
    async def toggle_favorite(item_id: str) -> dict:
        new_val = bool(_ctx().library_manager.toggle_favorite(item_id))
        return {"is_favorite": new_val}

    @app.delete("/api/library/items/{item_id}")
    async def delete_library_item(item_id: str) -> dict:
        _ctx().library_manager.delete_item(item_id)
        _bus().publish("library_changed")
        return {"ok": True}

    @app.get("/api/library/collections")
    async def get_collections() -> list[dict]:
        out = []
        for c in _ctx().library_manager.get_all_collections():
            count, _size = _ctx().library_manager.get_collection_stats(c.id)
            out.append({"id": c.id, "name": c.name, "icon": c.icon or "", "count": count})
        return out

    @app.post("/api/library/collections")
    async def create_collection(name: str = Query(...)) -> dict:
        cid = _ctx().library_manager.create_collection(name)
        _bus().publish("library_changed")
        return {"id": cid}

    @app.delete("/api/library/collections/{cid}")
    async def delete_collection(cid: int) -> dict:
        _ctx().library_manager.delete_collection(cid)
        _bus().publish("library_changed")
        return {"ok": True}

    @app.patch("/api/library/collections/{cid}")
    async def rename_collection(cid: int, name: str = Query(...)) -> dict:
        _ctx().library_manager.rename_collection(cid, name)
        _bus().publish("library_changed")
        return {"ok": True}

    @app.post("/api/library/items/{item_id}/collections/{cid}")
    async def add_to_collection(item_id: str, cid: int) -> dict:
        _ctx().library_manager.add_item_to_collection(item_id, cid)
        _bus().publish("library_changed")
        return {"ok": True}

    @app.delete("/api/library/items/{item_id}/collections/{cid}")
    async def remove_from_collection(item_id: str, cid: int) -> dict:
        _ctx().library_manager.remove_item_from_collection(item_id, cid)
        _bus().publish("library_changed")
        return {"ok": True}

    @app.get("/api/library/items/{item_id}/collections")
    async def get_item_collections(item_id: str) -> list[int]:
        try:
            return [c.id for c in _ctx().library_manager.get_item_collections(item_id)]
        except Exception:
            return []

    # ============================================================
    # 5. 收件箱
    # ============================================================

    @app.get("/api/inbox")
    async def get_inbox() -> list[dict]:
        return [_inbox_item_to_dict(it) for it in _ctx().inbox_manager.get_all()]

    @app.get("/api/inbox/unread-count")
    async def inbox_unread() -> dict:
        try:
            n = len(_ctx().inbox_manager.get_all(status_filter="new"))
        except Exception:
            n = 0
        return {"count": n}

    @app.post("/api/inbox/items/{item_id}/download")
    async def inbox_download(item_id: str) -> dict:
        """Inbox item → Download queue.

        流程（用户手动点击下载按钮触发）：
        1. 有 direct_url（浏览器扩展已提取直链）→ 直接入队
        2. 无 direct_url（抖音/小红书/快手/微博等国内平台）→
           调 extract_info 重新解析，填充 media_items_json，再入队
           （否则 downloader._run 的 else 分支会因 media_items_json 为空抛错）

        ★ CORS 注意：不能用 raise HTTPException，因为 BaseHTTPMiddleware + HTTPException
          组合下 CORSMiddleware 不会在异常响应上加 CORS header，浏览器会报 CORS 错误。
          改用 JSONResponse（正常走中间件链，带 CORS header）。
        """
        import asyncio
        from .downloader import extract_info

        ctx = _ctx()
        item = ctx.inbox_manager.get_item(item_id)
        if not item:
            return JSONResponse(status_code=404, content={"detail": "item not found"})

        try:
            # ★ 有 direct_url（浏览器扩展已提取直链），直接入队
            if item.direct_url:
                from .queue_manager import QueueTask
                qt = QueueTask(
                    url=item.url,
                    direct_url=item.direct_url,
                    title=item.title or "",
                    platform=item.platform or "",
                    author=item.author or "",
                    post_time=item.post_time or "",
                    thumbnail_url=item.thumbnail_url or None,
                    output_dir=str(get_download_dir()),
                )
                ctx.manager.add_task(qt)
                ctx.inbox_manager.mark_status(item_id, "queued")
                _set_inbox_task_map(qt.task_id, item_id)
                return {"ok": True, "task_id": qt.task_id}

            # ★ 无 direct_url：调 extract_info 重新解析（填充 media_items_json）
            # extract_info 是同步阻塞调用（网络请求），用 to_thread 避免阻塞事件循环
            info = await asyncio.to_thread(extract_info, item.url)

            # 判断 type：有图片项则为 image，否则 video
            format_type = "image" if any(
                not it.is_video for it in (info.items or [])
            ) else "video"
            # format_id：取 formats[0] 的 format_id（dict 访问，不是属性）
            # VideoInfo.formats 是 list[dict]，每个 dict 有 "format_id" 键
            format_id = "best"
            if info.formats:
                format_id = info.formats[0].get("format_id", "best") if isinstance(info.formats[0], dict) else "best"

            task_id = ctx.manager.add_task_from_info(
                info=info,
                format_id=format_id,
                format_type=format_type,
                custom_name="",
                output_dir=str(get_download_dir()),
            )
            ctx.inbox_manager.mark_status(item_id, "queued")
            _set_inbox_task_map(task_id, item_id)
            return {"ok": True, "task_id": task_id}
        except Exception as e:
            logger.exception("inbox_download failed item=%s", item_id)
            return JSONResponse(
                status_code=400,
                content={"detail": f"解析或入队失败: {e}"},
            )

    @app.post("/api/inbox/batch-download")
    async def inbox_batch_download(req: InboxBatchRequest) -> dict:
        """批量入队下载（用户手动点击批量下载按钮触发）。

        ★ 单项失败不影响其他项，失败项标记为 failed。
        """
        import asyncio
        from .downloader import extract_info

        ctx = _ctx()
        for iid in req.ids:
            item = ctx.inbox_manager.get_item(iid)
            if not item:
                continue
            try:
                # ★ 有 direct_url 直接入队
                if item.direct_url:
                    from .queue_manager import QueueTask
                    qt = QueueTask(
                        url=item.url,
                        direct_url=item.direct_url,
                        title=item.title or "",
                        platform=item.platform or "",
                        author=item.author or "",
                        post_time=item.post_time or "",
                        thumbnail_url=item.thumbnail_url or None,
                        output_dir=str(get_download_dir()),
                    )
                    ctx.manager.add_task(qt)
                    ctx.inbox_manager.mark_status(iid, "queued")
                    _set_inbox_task_map(qt.task_id, iid)
                    continue

                # ★ 无 direct_url，调 extract_info 重新解析
                info = await asyncio.to_thread(extract_info, item.url)
                format_type = "image" if any(
                    not it.is_video for it in (info.items or [])
                ) else "video"
                format_id = "best"
                if info.formats:
                    format_id = info.formats[0].get("format_id", "best") if isinstance(info.formats[0], dict) else "best"

                batch_task_id = ctx.manager.add_task_from_info(
                    info=info,
                    format_id=format_id,
                    format_type=format_type,
                    custom_name="",
                    output_dir=str(get_download_dir()),
                )
                ctx.inbox_manager.mark_status(iid, "queued")
                _set_inbox_task_map(batch_task_id, iid)
            except Exception as e:
                logger.warning("inbox_batch_download item=%s failed: %s", iid, e)
                ctx.inbox_manager.mark_status(iid, "failed")
        return {"ok": True}

    @app.post("/api/inbox/items/{item_id}/mark-downloaded")
    async def inbox_mark_downloaded(item_id: str) -> dict:
        _ctx().inbox_manager.mark_status(item_id, "downloaded")
        _bus().publish("inbox_changed")
        return {"ok": True}

    @app.post("/api/inbox/items/{item_id}/archive")
    async def inbox_archive(item_id: str) -> dict:
        _ctx().inbox_manager.mark_status(item_id, "archived")
        _bus().publish("inbox_changed")
        return {"ok": True}

    @app.delete("/api/inbox/items/{item_id}")
    async def inbox_delete(item_id: str) -> dict:
        _ctx().inbox_manager.delete_item(item_id)
        _bus().publish("inbox_changed")
        return {"ok": True}

    @app.post("/api/inbox/batch-delete")
    async def inbox_batch_delete(req: InboxBatchRequest) -> dict:
        _ctx().inbox_manager.delete_items(req.ids)
        _bus().publish("inbox_changed")
        return {"ok": True}

    @app.post("/api/inbox/clear-completed")
    async def inbox_clear_completed() -> dict:
        items = _ctx().inbox_manager.get_all()
        ids = [it.id for it in items if it.status in ("downloaded", "archived")]
        if ids:
            _ctx().inbox_manager.delete_items(ids)
            _bus().publish("inbox_changed")
        return {"ok": True, "deleted": len(ids)}

    # ============================================================
    # 6. 通知
    # ============================================================

    @app.get("/api/notifications")
    async def get_notifications() -> list[dict]:
        return [_notification_to_dict(n) for n in _ctx().notification_manager.get_all()]

    @app.get("/api/notifications/unread-count")
    async def notifications_unread() -> dict:
        return {"count": _ctx().notification_manager.unread_count()}

    @app.post("/api/notifications/read-all")
    async def notifications_read_all() -> dict:
        _ctx().notification_manager.mark_all_read()
        _bus().publish("notification_changed")
        return {"ok": True}

    @app.post("/api/notifications/{nid}/read")
    async def notification_read(nid: str) -> dict:
        _ctx().notification_manager.mark_read(nid)
        _bus().publish("notification_changed")
        return {"ok": True}

    @app.post("/api/notifications/clear-read")
    async def notifications_clear_read() -> dict:
        _ctx().notification_manager.clear_read()
        _bus().publish("notification_changed")
        return {"ok": True}

    @app.post("/api/notifications/{nid}/dismiss")
    async def notification_dismiss(nid: str) -> dict:
        _ctx().notification_manager.dismiss(nid)
        _bus().publish("notification_changed")
        return {"ok": True}

    # ============================================================
    # 7. 统计
    # ============================================================

    @app.get("/api/stats")
    async def get_stats() -> dict:
        from datetime import datetime, timezone
        records = _ctx().history_manager.records
        total = len(records)
        success = sum(1 for r in records if r.success)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        platforms: dict[str, int] = {}
        for r in records:
            p = r.platform or "unknown"
            platforms[p] = platforms.get(p, 0) + 1
        return {
            "total_downloads": total,
            "total_size": sum(r.file_size for r in records),
            "success_rate": (success / total * 100) if total else 0.0,
            "today_count": sum(1 for r in records
                               if r.download_time and r.download_time.startswith(today)),
            "platforms": platforms,
        }

    # ============================================================
    # 8. 配置 / Cookie
    # ============================================================

    @app.get("/api/config")
    async def get_config() -> dict:
        cfg = load_config()
        safe = dict(cfg)
        if safe.get("telegram_bot_token"):
            safe["telegram_bot_token"] = "***configured***"
        if safe.get("apify_token"):
            t = safe["apify_token"]
            safe["apify_token"] = ("apify_api_" + t[10:] + "...") if len(t) > 14 else t
        return safe

    @app.put("/api/config/{key}")
    async def set_config(key: str, req: ConfigUpdateRequest) -> dict:
        cfg = load_config()
        cfg[key] = req.value
        # Apify token/actor 变化时清除验证状态（与 qml_bridge 对齐）
        if key in ("apify_token", "apify_ig_actor"):
            cfg["apify_verified"] = False
            try:
                from .apify_client import reset_apify_client
                reset_apify_client()
            except Exception:
                pass
            ctx["app_ctx"]._apify_usage_cache = {"_ts": 0}
        save_config(cfg)
        _bus().publish("config_changed", {"key": key})
        return {"ok": True}

    @app.put("/api/config/nested/{parent_key}")
    async def set_nested_config(parent_key: str, req: NestedConfigUpdateRequest) -> dict:
        cfg = load_config()
        parent = cfg.setdefault(parent_key, {})
        if not isinstance(parent, dict):
            parent = {}
            cfg[parent_key] = parent
        parent.update(req.updates)
        save_config(cfg)
        _bus().publish("config_changed", {"key": parent_key})
        return {"ok": True}

    @app.get("/api/cookie/status")
    async def cookie_status() -> dict:
        try:
            from .utils.cookie_checker import check_all_cookies
            statuses = check_all_cookies()
            if "expired" in statuses.values():
                overall = "expired"
            elif "warning" in statuses.values():
                overall = "warning"
            elif "valid" in statuses.values():
                overall = "valid"
            else:
                overall = "missing"
            return {"overall": overall, "platforms": statuses}
        except Exception as e:
            return {"overall": "valid" if get_cookie_path() else "missing",
                    "error": str(e)}

    @app.post("/api/cookie/clear")
    async def cookie_clear() -> dict:
        try:
            p = get_cookie_path()
            if p and p.exists():
                p.write_text("", encoding="utf-8")
                return {"ok": True}
            return {"ok": False, "error": "no cookie file"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.post("/api/cookie/import")
    async def cookie_import(req: CookieImportRequest) -> dict:
        if not req.paths:
            return {"ok": False, "error": "no paths"}
        cfg = load_config()
        dest = Path(cfg.get("cookie_file", str(Path.home() / ".lumio" / "cookies.txt")))
        dest.parent.mkdir(parents=True, exist_ok=True)
        existing: set[str] = set()
        if dest.exists():
            with open(dest, encoding="utf-8") as f:
                existing = {l.strip() for l in f if l.strip()}
        imported = 0
        for sp in req.paths:
            if not sp or not Path(sp).exists():
                continue
            with open(sp, encoding="utf-8") as sf, open(dest, "a", encoding="utf-8") as df:
                for line in sf:
                    s = line.strip()
                    if s and s not in existing:
                        df.write(line)
                        existing.add(s)
            imported += 1
        return {"ok": imported > 0, "imported": imported}

    # ============================================================
    # 9. Telegram
    # ============================================================

    @app.post("/api/telegram/validate")
    async def telegram_validate(req: TelegramValidateRequest) -> dict:
        try:
            from .telegram_service import TelegramService
            result = TelegramService.validate_token(req.token, proxy=req.proxy)
            return result
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/telegram/pair-code")
    async def telegram_pair_code() -> dict:
        try:
            from .telegram_service import TelegramService
            svc = TelegramService(inbox_manager=None)
            return {"pair_code": svc.generate_pair_code()}
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/telegram/state")
    async def telegram_state() -> dict:
        try:
            from .telegram_service import TelegramService
            svc = TelegramService(inbox_manager=None)
            device = svc.get_bound_device()
            bound = None
            if device:
                bound = {
                    "telegram_user_id": device.telegram_user_id,
                    "username": getattr(device, "username", "") or "",
                    "first_name": getattr(device, "first_name", "") or "",
                }
            return {
                "pair_code": load_config().get("telegram_pair_code", ""),
                "bound_device": bound,
                "is_running": svc.is_running,
            }
        except Exception as e:
            return {"error": str(e)}

    @app.post("/api/telegram/unlink")
    async def telegram_unlink() -> dict:
        try:
            from .telegram_service import TelegramService
            svc = TelegramService(inbox_manager=None)
            device = svc.get_bound_device()
            if device:
                svc.unlink_device(device.telegram_user_id)
                return {"ok": True}
            return {"ok": False}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/telegram/api-base")
    async def telegram_api_base() -> dict:
        return {"base": load_config().get("telegram_api_base", "https://api.telegram.org")}

    # ============================================================
    # 10. Apify
    # ============================================================

    @app.post("/api/apify/validate")
    async def apify_validate(req: ApifyValidateRequest) -> dict:
        token = (req.token or "").strip()
        actor_id = (req.actor_id or "").strip()
        if not token:
            return {"ok": False, "error": "token empty"}
        if not actor_id:
            return {"ok": False, "error": "actor_id empty"}
        try:
            from .apify_client import ApifyIGClient, reset_apify_client
            client = ApifyIGClient(token=token, actor_id=actor_id)
            if client.test_connection():
                cfg = load_config()
                cfg["apify_token"] = token
                cfg["apify_ig_actor"] = actor_id
                cfg["apify_verified"] = True
                save_config(cfg)
                try:
                    reset_apify_client()
                except Exception:
                    pass
                ctx["app_ctx"]._apify_usage_cache = {"_ts": 0}
                _bus().publish("config_changed", {"key": "apify"})
                return {"ok": True}
            # 验证失败：清除 verified 状态，避免 UI 一直显示"已连接"
            cfg = load_config()
            if cfg.get("apify_verified"):
                cfg["apify_verified"] = False
                save_config(cfg)
                _bus().publish("config_changed", {"key": "apify"})
            return {"ok": False, "error": "validate failed"}
        except Exception as e:
            # 异常也清除 verified
            try:
                cfg = load_config()
                if cfg.get("apify_verified"):
                    cfg["apify_verified"] = False
                    save_config(cfg)
                    _bus().publish("config_changed", {"key": "apify"})
            except Exception:
                pass
            return {"ok": False, "error": str(e)}

    @app.get("/api/apify/status")
    async def apify_status() -> dict:
        cfg = load_config()
        token = cfg.get("apify_token", "")
        actor = cfg.get("apify_ig_actor", "")
        verified = cfg.get("apify_verified", False) is True
        enabled = cfg.get("instagram_mode", "cookie") == "api"
        cache = ctx["app_ctx"]._apify_usage_cache
        return {
            "token_configured": bool(token),
            "actor_configured": bool(actor),
            "connected": bool(token and actor and verified),
            "verified": verified,
            "enabled": enabled,
            "token_preview": ("apify_api_" + token[10:] + "...") if len(token) > 14 else (token or ""),
            "actor_id": actor,
            "usage_usd": cache.get("usage_usd"),
            "plan_credits_usd": cache.get("plan_credits_usd"),
            "plan_name": cache.get("plan_name"),
            "usage_updated": cache.get("usage_updated"),
        }

    @app.post("/api/apify/refresh-usage")
    async def apify_refresh_usage() -> dict:
        """后台刷新用量（5 分钟内不重复）。结果通过 WS apify_usage_updated 推送。"""
        cache = ctx["app_ctx"]._apify_usage_cache
        now = time.time()
        if now - cache.get("_ts", 0) < 300:
            return {"ok": True, "cached": True}

        async def _run() -> None:
            _do_refresh_apify_usage(ctx["app_ctx"], _bus())

        asyncio.create_task(_run())
        return {"ok": True}

    @app.post("/api/apify/force-refresh-usage")
    async def apify_force_refresh_usage() -> dict:
        async def _run() -> None:
            _do_refresh_apify_usage(ctx["app_ctx"], _bus())

        asyncio.create_task(_run())
        return {"ok": True}

    # ============================================================
    # 11. 主题 / 语言 / i18n
    # ============================================================

    @app.post("/api/theme/toggle")
    async def theme_toggle() -> dict:
        cfg = load_config()
        new = "light" if cfg.get("theme", "dark") == "dark" else "dark"
        cfg["theme"] = new
        save_config(cfg)
        _bus().publish("theme_changed", {"theme": new})
        return {"theme": new}

    @app.put("/api/theme")
    async def theme_set(req: SetThemeRequest) -> dict:
        new = "dark" if req.theme == "dark" else "light"
        cfg = load_config()
        cfg["theme"] = new
        save_config(cfg)
        _bus().publish("theme_changed", {"theme": new})
        return {"theme": new}

    @app.put("/api/lang")
    async def lang_set(req: SetLangRequest) -> dict:
        if req.lang not in ("zh", "en"):
            raise HTTPException(400, "lang must be zh or en")
        _i18n_set_lang(req.lang)
        cfg = load_config()
        cfg["lang"] = req.lang
        save_config(cfg)
        _bus().publish("lang_changed", {"lang": req.lang})
        return {"lang": req.lang}

    @app.get("/api/i18n/{key}")
    async def i18n_one(key: str) -> dict:
        try:
            return {"key": key, "value": _i18n_t(key)}
        except Exception:
            return {"key": key, "value": key}

    @app.get("/api/i18n")
    async def i18n_all() -> dict:
        """返回完整翻译字典（前端启动时一次性拉取，缓存到内存）。"""
        from .i18n import _TRANSLATIONS
        out: dict[str, dict[str, str]] = {}
        for lang, table in _TRANSLATIONS.items():
            out[lang] = dict(table)
        return out

    # ============================================================
    # 12. 缓存
    # ============================================================

    @app.get("/api/cache/stats")
    async def cache_stats() -> dict:
        try:
            from .utils.cache_manager import get_cache_stats
            return get_cache_stats()
        except Exception as e:
            return {"error": str(e)}

    @app.post("/api/cache/clean-by-rules")
    async def cache_clean_by_rules() -> dict:
        async def _run() -> None:
            try:
                from .utils.cache_manager import clean_cache_by_rules
                results = clean_cache_by_rules()
                total_files = sum(r.get("deleted", 0) for r in results.values())
                total_size = sum(r.get("freed", 0) for r in results.values())
                if total_files > 0:
                    try:
                        _ctx().notification_manager.notify_cache_cleaned(
                            total_files, total_size
                        )
                    except Exception:
                        pass
                    # Bug 7: 缓存清理结果改为 toast 通知（替代通知中心通知）
                    size_str = _format_size(total_size)
                    _bus().publish("toast", {"message": t("cache_cleaned_toast", total_files, size_str)})
                _bus().publish("cache_cleaned", {
                    "files": total_files, "size": total_size,
                })
            except Exception as e:
                _bus().publish("toast", {"message": f"Clean failed: {e}"})

        asyncio.create_task(_run())
        return {"ok": True}

    @app.post("/api/cache/force-clear")
    async def cache_force_clear() -> dict:
        async def _run() -> None:
            try:
                from .utils.cache_manager import force_clear_cache
                results = force_clear_cache()
                total_files = sum(r.get("deleted", 0) for r in results.values())
                total_size = sum(r.get("freed", 0) for r in results.values())
                if total_files > 0:
                    try:
                        _ctx().notification_manager.notify_cache_cleaned(
                            total_files, total_size
                        )
                    except Exception:
                        pass
                    # Bug 7: 缓存清理结果改为 toast 通知
                    size_str = _format_size(total_size)
                    _bus().publish("toast", {"message": t("cache_cleaned_toast", total_files, size_str)})
                _bus().publish("cache_cleaned", {
                    "files": total_files, "size": total_size,
                })
            except Exception as e:
                _bus().publish("toast", {"message": f"Clear failed: {e}"})

        asyncio.create_task(_run())
        return {"ok": True}

    # ============================================================
    # 13. 系统操作（剪贴板 / 打开文件 / 外部 URL / 缩略图代理 / Toast）
    # ============================================================

    @app.post("/api/clipboard/copy")
    async def clipboard_copy(req: CopyClipboardRequest) -> dict:
        try:
            from .utils.signal import _qgui_clipboard
            cb = _qgui_clipboard()
            cb.setText(req.text)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/clipboard/text")
    async def clipboard_text() -> dict:
        try:
            from .utils.signal import _qgui_clipboard
            cb = _qgui_clipboard()
            return {"text": cb.text()}
        except Exception:
            return {"text": ""}

    @app.post("/api/open-file")
    async def open_file(req: OpenFileRequest) -> dict:
        ok, err = _open_path(req.path, req.source)
        if not ok and err == "not_found" and req.source:
            _bus().publish("file_missing", {"path": req.path, "source": req.source})
        return {"ok": ok, "error": err if not ok else ""}

    @app.post("/api/open-folder")
    async def open_folder(req: OpenFileRequest) -> dict:
        ok, err = _open_folder(req.path, req.source)
        if not ok and err == "not_found" and req.source:
            _bus().publish("file_missing", {"path": req.path, "source": req.source})
        return {"ok": ok, "error": err if not ok else ""}

    @app.post("/api/library/preview-target")
    async def library_preview_target(req: PreviewTargetRequest) -> dict:
        """对 mixed / 目录型素材，扫描文件夹返回主视频/图片路径 + 单一 media_type。

        前端 MediaPreviewDialog 在打开前调用此端点解析真实播放目标：
          - file_path 是文件 → 直接返回 (path, 单一类型)
          - file_path 是目录（mixed）→ 扫描目录返回第一个视频/图片/音频
        """
        path, mt = _resolve_preview_target(req.file_path, req.media_type)
        return {"path": path, "media_type": mt}

    @app.post("/api/library/preview-items")
    async def library_preview_items(req: PreviewTargetRequest) -> dict:
        """列出文件夹内所有可预览媒体（按 video → image → audio 排序）。

        前端 MediaPreviewDialog 用此列表实现上下项切换。
        单文件返回 [{path, media_type}]。

        文件不存在时推 file_missing 事件（source="library"），让前端
        弹「是否删除本条记录」对话框。修复 Bug 2：原来仅显示「文件不存在」
        但用户无法直接删除记录，需手动找到素材再删除。
        """
        # 文件不存在 → 推 file_missing 事件让前端弹删除确认对话框
        if req.file_path and not os.path.exists(req.file_path):
            _bus().publish("file_missing", {"path": req.file_path, "source": "library"})
            return {"items": []}
        items = _list_preview_items(req.file_path)
        # 目录存在但内部无可预览文件（空目录或文件被外部删除）→ 同样推 file_missing
        if not items and req.file_path and os.path.isdir(req.file_path):
            # 仅当原本应是 library 来源时触发（路径非空）
            _bus().publish("file_missing", {"path": req.file_path, "source": "library"})
        return {"items": items}

    @app.post("/api/open-external-url")
    async def open_external_url(req: OpenExternalUrlRequest) -> dict:
        if not req.url:
            return {"ok": False, "error": "empty"}
        try:
            from .utils.signal import QDesktopServices, QUrl as _QUrl
            return {"ok": bool(QDesktopServices.openUrl(_QUrl(req.url)))}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/thumb-proxy")
    async def thumb_proxy(
        url: str = Query(...),
        w: int = Query(0, ge=0, le=1024),
        h: int = Query(0, ge=0, le=1024),
        persist: int = Query(0, ge=0, le=1),
        request: Request = None,
    ) -> Response:
        """代理远程缩略图下载，附加 Referer/Cookie（与 ThumbnailProvider 等价）。

        新增：
        - 服务端本地缓存（~/.lumio/cache/thumb_proxy/，7 天 TTL）
        - ETag + If-None-Match 条件请求（远程 304 + 浏览器 304 双层）
        - w/h 参数：用 PIL 缩放到指定尺寸，节省带宽与内存
        - persist=1：写 .bin+.meta 磁盘缓存（仅用于素材库/历史等已下载完成的封面）
          persist=0（默认）：仅内存缓存，避免 Home 预览/搜索结果等临时场景导致磁盘膨胀
        - 失败时返回 1x1 透明 GIF（200）而非 raise HTTPException：
          Starlette BaseHTTPMiddleware + HTTPException 组合下 CORSMiddleware
          不会在异常响应上加 CORS header，会导致浏览器控制台报 CORS 错误。
          改为永远返回 200 让前端 fetch 不阻塞、不报错。
        """
        import requests as _requests
        # 1x1 透明 GIF（最小有效图片，前端 <img>/canvas 都能处理）
        _TRANSPARENT_GIF = bytes.fromhex(
            "4749463839610100010080000000000000ffffff21f9040100000000"
            "2c00000000010001000002024401003b"
        )
        try:
            from .utils.thumb_proxy import fetch_thumbnail_bytes
            content, content_type, etag = fetch_thumbnail_bytes(
                url, timeout=15, target_w=w, target_h=h, persist=bool(persist)
            )
            headers_out = {
                "Cache-Control": "public, max-age=604800, immutable",
                "Content-Type": content_type,
            }
            if etag:
                headers_out["ETag"] = etag
                # 浏览器发 If-None-Match 且匹配 → 返回 304
                inm = request.headers.get("if-none-match") if request else None
                if inm and etag in inm:
                    return Response(status_code=304, headers=headers_out)
            return Response(content=content, headers=headers_out)
        except _requests.HTTPError as e:
            # 远程 CDN 返回 4xx/5xx — 返回透明 GIF 而非 raise，避免 CORS header 缺失
            status = e.response.status_code if e.response is not None else 0
            logger.warning("thumb-proxy HTTPError url=%s status=%s", url, status)
            return Response(
                content=_TRANSPARENT_GIF,
                media_type="image/gif",
                headers={"Cache-Control": "no-store"},
            )
        except Exception as e:
            logger.warning("thumb-proxy error url=%s err=%s: %s", url, type(e).__name__, e)
            return Response(
                content=_TRANSPARENT_GIF,
                media_type="image/gif",
                headers={"Cache-Control": "no-store"},
            )

    @app.post("/api/toast")
    async def toast(req: ToastRequest) -> dict:
        _bus().publish("toast", {"message": req.message})
        return {"ok": True}

    # ============================================================
    # 14. 版本检查
    # ============================================================

    @app.get("/api/check-update")
    async def check_update() -> dict:
        """检查 GitHub Releases 最新版本。

        统一仓库地址：Roseannepark0211/Lumio（之前误用 Azad-slack/Lumio）。
        返回 release body（更新内容）供前端展示 release notes。
        """
        try:
            from . import __version__
            import urllib.request
            api_url = "https://api.github.com/repos/Roseannepark0211/Lumio/releases/latest"
            req = urllib.request.Request(api_url, headers={"User-Agent": "Lumio"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            latest = data.get("tag_name", "").lstrip("v")
            return {
                "current": __version__,
                "latest": latest,
                "has_update": _version_lt(__version__, latest),
                "release_url": data.get("html_url", ""),
                "release_name": data.get("name", ""),
                "release_body": data.get("body", ""),  # 更新内容（markdown）
                "published_at": data.get("published_at", ""),
            }
        except Exception as e:
            return {"error": str(e)}

    # ============================================================
    # 15. 健康检查
    # ============================================================

    @app.get("/api/health")
    async def health() -> dict:
        return {
            "ok": True,
            "version": __import__("lumio").__version__,
            "managers": {
                "download": _ctx().manager is not None,
                "inbox": _ctx().inbox_manager is not None,
                "library": _ctx().library_manager is not None,
                "history": _ctx().history_manager is not None,
                "notification": _ctx().notification_manager is not None,
            },
        }

    # ============================================================
    # 16. 优雅关闭（Electron 主进程退出时调用）
    # ============================================================

    @app.post("/api/shutdown")
    async def shutdown() -> dict:
        """Electron 退出前调用，触发 manager.shutdown() 后退出进程。
        token 鉴权由 middleware 处理。
        """
        import threading

        def _do_shutdown():
            import time
            time.sleep(0.5)  # 让响应先返回
            try:
                _ctx().shutdown()
            except Exception:
                pass
            # 给 uvicorn 发 SIGINT
            import os
            import signal
            os.kill(os.getpid(), signal.SIGINT)

        threading.Thread(target=_do_shutdown, daemon=True).start()
        return {"ok": True}

    # ============================================================
    # WebSocket /ws/events
    # ============================================================

    @app.websocket("/ws/events")
    async def ws_events(ws: WebSocket) -> None:
        # JWT 校验：?token=<jwt>（移动端）或 ?token=<x-lumio-token>（Electron 浏览器 WS）
        # 失败 -> 关闭码 4401（移动端 ws/client.ts 据此停止重连）
        # WS 鉴权放在 accept 之前：close(code=4401) 拒绝握手
        token = ws.query_params.get("token", "")
        if not token:
            await ws.close(code=4401)
            return
        # 优先尝试作为 JWT 校验
        payload = mobile_auth.verify_token(token)
        if payload is None:
            # 不是有效 JWT，回退到 X-Lumio-Token 校验
            if not (expected_token and token == expected_token):
                await ws.close(code=4401)
                return
        await ws.accept()
        q = _bus().subscribe()
        # 心跳：每 25 秒发送应用层 ping 帧。
        # 浏览器 WebSocket API 不暴露 ping/pong 帧给 JS，需要应用层自实现：
        # 长时间下载时网络中间设备（NAT/路由器）会切断空闲连接，心跳保活。
        # 心跳间隔 < 30s 可穿大多数 NAT。
        HEARTBEAT_INTERVAL = 25.0
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=HEARTBEAT_INTERVAL)
                except asyncio.TimeoutError:
                    # 队列空闲超时：发心跳
                    try:
                        await ws.send_json({"type": "ping", "data": None, "ts": time.time()})
                    except (WebSocketDisconnect, RuntimeError):
                        break
                    continue
                try:
                    await ws.send_json(event)
                except (WebSocketDisconnect, RuntimeError):
                    # 客户端断开：send_json 抛 RuntimeError "Cannot call send..."
                    # 或 WebSocketDisconnect。跳出循环走 finally 退订。
                    break
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            _bus().unsubscribe(q)

    return app


# ============================================================
# Signal 桥接：Qt Signal → EventBus
# ============================================================

def _wire_signals(app_ctx: AppContext, bus: EventBus) -> None:
    """把 DownloadManager / InboxManager 的 Qt Signal 接到 EventBus。
    使用 DirectConnection 强制 callback 在 emit 线程执行，避免依赖 Qt event loop。

    InboxManager 的 item_added/item_updated/items_deleted 必须桥接，
    否则 Flask /capture 端点写入 inbox 后前端 WS 收不到 inbox_changed 事件，
    导致用户需要手动刷新页面才能看到新内容。
    """
    m = app_ctx.manager

    def _wrap(event_type: str, extractor=None):
        def cb(*args):
            data = extractor(*args) if extractor else (args[0] if args else None)
            bus.publish(event_type, data)
        return cb

    m.task_added.connect(
        _wrap("task_added", lambda qt: _task_to_dict(qt)),
        Qt.DirectConnection,
    )
    m.task_started.connect(_wrap("task_started"), Qt.DirectConnection)
    m.task_progress.connect(
        _wrap("task_progress",
              lambda tid, p, s, fn: {"task_id": tid, "progress": p, "speed": s, "filename": fn}),
        Qt.DirectConnection,
    )
    m.task_finished.connect(
        _wrap("task_finished",
              lambda tid, ok, err: {"task_id": tid, "success": ok, "error": err}),
        Qt.DirectConnection,
    )
    def _on_task_status_changed(tid: str, st: str):
        # 先同步 inbox 状态（task_id → inbox_item_id 映射存在时）
        _sync_inbox_on_task_status(app_ctx, bus, tid, st)
        # 再推 task_status_changed 事件给前端
        bus.publish("task_status_changed", {"task_id": tid, "status": st})

    m.task_status_changed.connect(_on_task_status_changed, Qt.DirectConnection)
    m.queue_changed.connect(_wrap("queue_changed"), Qt.DirectConnection)
    m.batch_progress.connect(
        _wrap("batch_progress",
              lambda c, f, t: {"completed": c, "failed": f, "total": t}),
        Qt.DirectConnection,
    )
    m.history_record_added.connect(
        _wrap("history_record_added",
              lambda r: _history_to_dict(r)),
        Qt.DirectConnection,
    )
    m.library_record_added.connect(
        _wrap("library_record_added",
              lambda it: _library_item_to_dict(it, app_ctx.library_manager)),
        Qt.DirectConnection,
    )
    m.library_thumbnail_ready.connect(
        _wrap("library_thumbnail_ready",
              lambda item_id, local_path: {"item_id": item_id, "thumbnail_path": local_path}),
        Qt.DirectConnection,
    )
    m.conflict_ask.connect(
        _wrap("conflict_ask",
              lambda p: {"file_path": p}),
        Qt.DirectConnection,
    )

    # —— InboxManager signal → inbox_changed 事件 ——
    # Flask /capture 端点写入 inbox 后通过此桥接推送 WS 事件，
    # 否则前端需要手动刷新页面才能看到新内容。
    inbox = app_ctx.inbox_manager
    inbox.item_added.connect(_wrap("inbox_changed"), Qt.DirectConnection)
    inbox.item_updated.connect(_wrap("inbox_changed"), Qt.DirectConnection)
    inbox.items_deleted.connect(_wrap("inbox_changed"), Qt.DirectConnection)

    # NotificationManager 的状态变化（它不发 Signal，但 add/dismiss 时需通知前端）
    # 通过包装关键方法实现
    _wrap_notification_manager(app_ctx.notification_manager, bus)


def _wrap_notification_manager(nm, bus: EventBus) -> None:
    """NotificationManager 没有 Signal，包装关键方法发事件。"""
    orig_add = nm.add_notification
    orig_dismiss = nm.dismiss
    orig_mark_read = nm.mark_read
    orig_mark_all_read = nm.mark_all_read
    orig_clear_read = nm.clear_read

    def _add(*a, **kw):
        r = orig_add(*a, **kw)
        bus.publish("notification_changed", {"action": "add"})
        return r

    def _dismiss(*a, **kw):
        r = orig_dismiss(*a, **kw)
        bus.publish("notification_changed", {"action": "dismiss"})
        return r

    def _mark_read(*a, **kw):
        r = orig_mark_read(*a, **kw)
        bus.publish("notification_changed", {"action": "mark_read"})
        return r

    def _mark_all_read(*a, **kw):
        r = orig_mark_all_read(*a, **kw)
        bus.publish("notification_changed", {"action": "mark_all_read"})
        return r

    def _clear_read(*a, **kw):
        r = orig_clear_read(*a, **kw)
        bus.publish("notification_changed", {"action": "clear_read"})
        return r

    nm.add_notification = _add
    nm.dismiss = _dismiss
    nm.mark_read = _mark_read
    nm.mark_all_read = _mark_all_read
    nm.clear_read = _clear_read


def _do_refresh_apify_usage(app_ctx: AppContext, bus: EventBus) -> None:
    """与 QmlController._do_refresh_apify_usage 等价（后台线程执行）。"""
    try:
        from .apify_client import get_apify_client as _get_apify_client
        client = _get_apify_client()
    except Exception as e:
        app_ctx._apify_usage_cache["_ts"] = time.time()
        bus.publish("apify_usage_updated", {"error": str(e)})
        return

    def _fetch():
        try:
            user_client = client._client.user()
            user_data = user_client.get()
            usage_data = user_client.monthly_usage()
            if not user_data:
                bus.publish("apify_usage_updated", {"error": "user get() returned empty"})
                return
            udata = user_data if isinstance(user_data, dict) else {}
            plan = udata.get("plan", {}) or {}
            plan_credits = float(plan.get("monthlyUsageCreditsUsd", 0) or 0)
            plan_name = plan.get("id", "") or udata.get("tier", "") or ""
            usage_total = 0.0
            if usage_data and isinstance(usage_data, dict):
                usage_total = float(
                    usage_data.get("totalUsageCreditsUsdAfterVolumeDiscount")
                    or usage_data.get("totalUsageCreditsUsdBeforeVolumeDiscount")
                    or 0
                )
                if usage_total == 0.0:
                    daily = usage_data.get("dailyServiceUsages") or []
                    if daily:
                        usage_total = sum(
                            float(d.get("totalUsageCreditsUsd", 0) or 0) for d in daily
                        )
            app_ctx._apify_usage_cache.update({
                "usage_usd": usage_total,
                "plan_credits_usd": plan_credits,
                "plan_name": plan_name,
                "usage_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                "_ts": time.time(),
            })
            app_ctx._apify_usage_cache.pop("error", None)
            bus.publish("apify_usage_updated", dict(app_ctx._apify_usage_cache))
            try:
                app_ctx.notification_manager.notify_apify_quota(usage_total, plan_credits)
            except Exception:
                pass
        except Exception as e:
            app_ctx._apify_usage_cache["_ts"] = time.time()
            bus.publish("apify_usage_updated", {"error": str(e)})

    threading.Thread(target=_fetch, daemon=True).start()


def _video_info_to_dict(info) -> dict:
    """VideoInfo → dict（与 qml_bridge 的 _info_to_json 对齐）。"""
    return {
        "title": info.title,
        "url": info.url,
        "thumbnail": info.thumbnail or "",
        "duration": info.duration,
        "formats": info.formats,
        "platform": info.platform,
        "author": info.author,
        "items": [
            {
                "url": it.url,
                "is_video": it.is_video,
                "media_type": it.media_type,
                "width": it.width,
                "height": it.height,
                "extension": it.extension,
                "size": it.size,
                "quality": it.quality,
                "filename": it.filename,
                "live_photo": getattr(it, "live_photo", None),
            }
            for it in (info.items or [])
        ],
        "post_time": info.post_time or "",
    }


def _version_lt(a: str, b: str) -> bool:
    """语义版本对比：a < b 返回 True。"""
    try:
        pa = [int(x) for x in a.split(".")[:3]]
        pb = [int(x) for x in b.split(".")[:3]]
        while len(pa) < 3: pa.append(0)
        while len(pb) < 3: pb.append(0)
        return pa < pb
    except Exception:
        return False


# ============================================================
# 入口
# ============================================================

def main() -> None:
    """启动 FastAPI 服务（uvicorn）。
    端口和 token 从环境变量读取（由 Electron 主进程注入）。
    """
    import uvicorn
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    # 优先用环境变量（Electron 注入），否则回退到 config
    host = os.environ.get("LUMIO_FASTAPI_HOST", "0.0.0.0")  # 默认 0.0.0.0 让移动端可连
    port = int(os.environ.get("LUMIO_FASTAPI_PORT", "0")) or 38910
    logger.info("Starting FastAPI on %s:%d (token=%s)",
                host, port,
                "yes" if os.environ.get("LUMIO_FASTAPI_TOKEN") else "no")
    app = create_app()
    # 桌面单用户场景：强制单 worker，避免多 worker 导致 SQLite 连接复制（+200MB 内存）
    # 和 manager 状态在多进程间不同步；禁用 access_log 减少日志开销
    uvicorn.run(
        app,
        host=host,
        port=port,
        workers=1,
        reload=False,
        access_log=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
