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
from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtWidgets import QApplication

_qt_app: Optional[QApplication] = None


def _ensure_qt_app() -> QApplication:
    global _qt_app
    if _qt_app is None:
        _qt_app = QApplication.instance() or QApplication(sys.argv[:1])
    return _qt_app


from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, Response
from pydantic import BaseModel, Field

from .utils.config import load_config, save_config, get_download_dir, get_cookie_path
from .i18n import t as _i18n_t, set_lang as _i18n_set_lang


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


class OpenExternalUrlRequest(BaseModel):
    url: str


class ToastRequest(BaseModel):
    message: str


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

        cfg = load_config()
        # 浏览器扩展的 /capture API 仍由原 Flask 服务提供（端口 38900）
        # 这里启动它，不阻塞
        start_server(self.inbox_manager, port=cfg.get("api_port", 38900))
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

        # 启动时检测环境（后台异步）
        try:
            self.notification_manager.check_all()
        except Exception:
            pass

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
        "direct_url": getattr(qt, "direct_url", "") or "",
        "title": qt.title or "",
        "status": qt.status,
        "progress": getattr(qt, "progress", 0.0),
        "speed": getattr(qt, "speed", "") or "",
        "filename": getattr(qt, "filename", "") or "",
        "thumbnail_url": qt.thumbnail_url or "",
        "platform": qt.platform or "",
        "author": qt.author or "",
        "post_time": qt.post_time or "",
        "output_dir": qt.output_dir or "",
        "custom_name": getattr(qt, "custom_name", "") or "",
        "error": getattr(qt, "error", "") or "",
        "media_type": getattr(qt, "media_type", "") or "",
        "retry_count": getattr(qt, "retry_count", 0),
        "media_items_json": getattr(qt, "media_items_json", "") or "",
        "batch_id": getattr(qt, "batch_id", "") or "",
    }


def _history_to_dict(r) -> dict:
    return {
        "id": r.id,
        "url": r.url,
        "title": r.title or "",
        "platform": r.platform or "",
        "author": r.author or "",
        "file_path": r.file_path or "",
        "file_size": r.file_size,
        "media_type": r.media_type or "",
        "success": r.success,
        "error": r.error or "",
        "download_time": r.download_time or "",
        "post_time": r.post_time or "",
        "batch_id": r.batch_id or "",
    }


def _library_item_to_dict(it, lib_mgr) -> dict:
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
    }


def _inbox_item_to_dict(it) -> dict:
    return {
        "id": it.id,
        "url": it.url or "",
        "direct_url": it.direct_url or "",
        "title": it.title or "",
        "platform": it.platform or "",
        "author": it.author or "",
        "thumbnail_url": it.thumbnail_url or "",
        "media_type": it.media_type or "",
        "status": it.status or "new",
        "source": it.source or "",
        "post_time": it.post_time or "",
        "duration": getattr(it, "duration", 0) or 0,
        "created_at": it.created_at.isoformat() if it.created_at else "",
    }


def _notification_to_dict(n) -> dict:
    return {
        "id": n.id,
        "category": n.category,
        "level": n.level,
        "title": n.title or "",
        "body": n.body or "",
        "action_label": n.action_label or "",
        "action_url": n.action_url or "",
        "dismissable": bool(n.dismissable),
        "is_read": bool(n.is_read),
        "created_at": n.created_at.isoformat() if n.created_at else "",
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

    # CORS：允许 Electron 渲染进程（file:// 或 http://localhost:5173）跨域调用
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 桌面应用本地调用，无敏感风险
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
        ctx["app_ctx"] = AppContext()
        # 绑定 Qt Signal → EventBus
        _wire_signals(ctx["app_ctx"], ctx["bus"])
        logger.info("Lumio FastAPI started")

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
    # 2. URL 解析（异步，结果走 WebSocket）
    # ============================================================

    @app.post("/api/parse-url")
    async def parse_url(req: ParseUrlRequest) -> dict:
        """异步解析 URL，结果通过 WS 事件 parse_completed / parse_failed 推送。"""
        from .gui.qml_bridge import _extract_url_from_text
        url = (req.url or "").strip()
        if not url:
            return {"ok": False, "error": "empty"}
        url = _extract_url_from_text(url) or url
        rid = req.request_id or f"parse_{int(time.time()*1000)}"

        async def _run() -> None:
            try:
                from .downloader import resolve_via_providers
                info = await asyncio.to_thread(resolve_via_providers, url)
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
                from .x_sou_client import XSouClient
                client = XSouClient()
                results = await asyncio.to_thread(
                    client.search, q, req.page or 1, req.limit or 20
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
        """X-Sou 视频预览：后台下载到 cache/preview，完成后 WS 推 preview_ready。"""
        if not req.video_url:
            return {"ok": False, "error": "empty"}

        async def _run() -> None:
            try:
                from .gui.qml_bridge import _PreviewCacheWorker
                # _PreviewCacheWorker 是 QThread，需要 QApplication（已创建）
                worker = _PreviewCacheWorker(req.video_url)
                worker.progress.connect(
                    lambda p: _bus().publish("preview_progress", {"progress": p}),
                    Qt.DirectConnection,
                )
                worker.finished_ok.connect(
                    lambda path: _bus().publish("preview_ready", {"path": path}),
                    Qt.DirectConnection,
                )
                worker.failed.connect(
                    lambda err: _bus().publish("preview_failed", {"error": err}),
                    Qt.DirectConnection,
                )
                worker.start()
                # 不阻塞，worker 结束时自己 deleteLater
            except Exception as e:
                _bus().publish("preview_failed", {"error": str(e)})

        asyncio.create_task(_run())
        return {"ok": True}

    @app.post("/api/preview-cancel")
    async def preview_cancel() -> dict:
        # 简化：取消逻辑依赖客户端不再订阅事件
        return {"ok": True}

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
        item = _ctx().inbox_manager.get_item(item_id)
        if not item:
            raise HTTPException(404, "item not found")
        from .queue_manager import QueueTask
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
        _ctx().manager.add_task(qt)
        _ctx().inbox_manager.mark_status(item_id, "queued")
        return {"ok": True, "task_id": qt.task_id}

    @app.post("/api/inbox/batch-download")
    async def inbox_batch_download(req: InboxBatchRequest) -> dict:
        for iid in req.ids:
            item = _ctx().inbox_manager.get_item(iid)
            if not item:
                continue
            from .queue_manager import QueueTask
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
            _ctx().manager.add_task(qt)
            _ctx().inbox_manager.mark_status(iid, "queued")
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
            from .gui.cookie_checker import check_all_cookies
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
            return {"ok": False, "error": "validate failed"}
        except Exception as e:
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
            from PySide6.QtGui import QGuiApplication
            cb = QGuiApplication.clipboard()
            if cb:
                cb.setText(req.text)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/clipboard/text")
    async def clipboard_text() -> dict:
        try:
            from PySide6.QtGui import QGuiApplication
            cb = QGuiApplication.clipboard()
            return {"text": cb.text() if cb else ""}
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

    @app.post("/api/open-external-url")
    async def open_external_url(req: OpenExternalUrlRequest) -> dict:
        if not req.url:
            return {"ok": False, "error": "empty"}
        try:
            from PySide6.QtGui import QDesktopServices, QUrl as _QUrl
            return {"ok": bool(QDesktopServices.openUrl(_QUrl(req.url)))}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/thumb-proxy")
    async def thumb_proxy(url: str = Query(...)) -> Response:
        """代理远程缩略图下载，附加 Referer/Cookie（与 ThumbnailProvider 等价）。
        返回原始图片字节，前端用 <img src="/api/thumb-proxy?url=..."> 直接渲染。
        """
        try:
            from .gui.qml_bridge import ThumbnailProvider
            # 复用现有 ThumbnailProvider 的下载逻辑（带 Referer/Cookie）
            provider = ThumbnailProvider.__new__(ThumbnailProvider)
            provider._cache: dict = {}
            provider._cache_lock = threading.Lock()
            # 调用 requestPixmap 内部的下载逻辑
            from PySide6.QtCore import QUrl, QSize
            from PySide6.QtGui import QImage
            # 简化实现：直接用 requests 下载，附加通用 Referer
            import requests
            headers = {"User-Agent": "Mozilla/5.0 Lumio"}
            if "sinaimg" in url:
                headers["Referer"] = "https://weibo.com/"
            elif "twimg" in url or "x.com" in url:
                headers["Referer"] = "https://x.com/"
            elif "instagram" in url or "cdninstagram" in url:
                headers["Referer"] = "https://www.instagram.com/"
            # 加 cookie
            cookie_path = get_cookie_path()
            if cookie_path and cookie_path.exists():
                try:
                    from .providers.network.cookie import load_cookie_string
                    headers["Cookie"] = load_cookie_string(str(cookie_path))
                except Exception:
                    pass
            session = requests.Session(trust_env=True)
            r = session.get(url, headers=headers, timeout=15, stream=False)
            r.raise_for_status()
            return Response(content=r.content, media_type=r.headers.get("Content-Type", "image/jpeg"))
        except Exception as e:
            raise HTTPException(502, f"thumb fetch failed: {e}")

    @app.post("/api/toast")
    async def toast(req: ToastRequest) -> dict:
        _bus().publish("toast", {"message": req.message})
        return {"ok": True}

    # ============================================================
    # 14. 版本检查
    # ============================================================

    @app.get("/api/check-update")
    async def check_update() -> dict:
        try:
            from . import __version__
            import urllib.request
            api_url = "https://api.github.com/repos/Azad-slack/Lumio/releases/latest"
            req = urllib.request.Request(api_url, headers={"User-Agent": "Lumio"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            latest = data.get("tag_name", "").lstrip("v")
            return {
                "current": __version__,
                "latest": latest,
                "has_update": _version_lt(__version__, latest),
                "release_url": data.get("html_url", ""),
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
    # WebSocket /ws/events
    # ============================================================

    @app.websocket("/ws/events")
    async def ws_events(ws: WebSocket) -> None:
        await ws.accept()
        q = _bus().subscribe()
        try:
            while True:
                event = await q.get()
                await ws.send_json(event)
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
    """把 DownloadManager 的 Qt Signal 接到 EventBus。
    使用 DirectConnection 强制 callback 在 emit 线程执行，避免依赖 Qt event loop。
    """
    m = app_ctx.manager

    def _wrap(event_type: str, extractor=None):
        def cb(*args):
            data = extractor(*args) if extractor else (args[0] if args else None)
            bus.publish(event_type, data)
        return cb

    m.task_added.connect(_wrap("task_added"), Qt.DirectConnection)
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
    m.task_status_changed.connect(
        _wrap("task_status_changed",
              lambda tid, st: {"task_id": tid, "status": st}),
        Qt.DirectConnection,
    )
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
    m.conflict_ask.connect(
        _wrap("conflict_ask",
              lambda p: {"file_path": p}),
        Qt.DirectConnection,
    )

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
    """启动 FastAPI 服务（uvicorn）。"""
    import uvicorn
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    cfg = load_config()
    host = cfg.get("fastapi_host", "127.0.0.1")
    port = cfg.get("fastapi_port", 38910)
    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
