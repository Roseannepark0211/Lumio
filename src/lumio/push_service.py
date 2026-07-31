"""Lumio 推送通知服务 — Expo Push Server 集成。

[部署说明]
此文件需复制到主仓库：~/Desktop/Lumio/src/lumio/push_service.py
对应移动端 M3 任务（Lumio_Mobile/docs/07-迁移计划.md §6）。

设计原则（对齐 AGENTS.md "L2 目录隔离"）：
- 独立模块，不修改 queue_manager / library_manager / inbox_manager 业务层
- push token 存 ~/.lumio/push_tokens.json（与 devices.json 隔离）
- 调用 Expo Push Server 公开 API（无需凭证），后台线程异步发送
- 事件订阅：通过 install_event_hook(bus) 注入 EventBus，对业务层零侵入

关键事件 → 推送分类映射（对齐 docs/07-迁移计划.md M3 §6.4）：
- task_finished (success) → default：下载完成
- task_finished (failed)   → critical：下载失败（声音+震动）
- queue_drained             → critical：队列空（提示用户）
- inbox_changed (add)       → default：Inbox 新增
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
import urllib.request

logger = logging.getLogger("lumio.push")

# ============================================================
# 路径常量
# ============================================================
_APP_DIR = Path.home() / ".lumio"
_TOKENS_FILE = _APP_DIR / "push_tokens.json"

# Expo Push Server API（公开，无需鉴权；建议加 Authorization header 提高限额）
_EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
_EXPO_REQUEST_TIMEOUT = 10  # 秒

# 全局锁（保护 push_tokens.json）
_lock = threading.RLock()

# 已注册的 push token 缓存：device_id → token dict
_tokens_cache: Optional[dict[str, dict]] = None

# 支持的事件分类（与移动端 usePush.ts categories 对齐）
SUPPORTED_CATEGORIES = {
    "task_finished_success",
    "task_finished_failed",
    "queue_drained",
    "inbox_new",
}

# 事件 → 分类映射
_EVENT_CATEGORY_MAP = {
    "task_finished_success": "default",
    "task_finished_failed": "critical",
    "queue_drained": "critical",
    "inbox_new": "default",
}


# ============================================================
# push_tokens.json 持久化
# ============================================================

def _load_tokens() -> dict[str, dict]:
    """加载 push_tokens.json。结构：{"tokens": {device_id: {...}}}"""
    global _tokens_cache
    if _tokens_cache is not None:
        return _tokens_cache
    result: dict[str, dict] = {}
    if _TOKENS_FILE.exists():
        try:
            with open(_TOKENS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            tokens = data.get("tokens", {}) if isinstance(data, dict) else {}
            if isinstance(tokens, dict):
                result = {k: v for k, v in tokens.items() if isinstance(v, dict)}
        except Exception as e:
            logger.warning("加载 push_tokens.json 失败: %s", e)
    _tokens_cache = result
    return result


def _save_tokens(tokens: dict[str, dict]) -> None:
    _APP_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _TOKENS_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"tokens": tokens}, f, indent=2, ensure_ascii=False)
    os.replace(tmp, _TOKENS_FILE)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# 注册 / 注销 / 查询
# ============================================================

def register_push_token(device_id: str, push_token: str,
                        categories: Optional[list] = None) -> bool:
    """注册设备的 push token。覆盖旧 token（同一 device_id）。"""
    if not device_id or not push_token:
        return False
    cats = [c for c in (categories or []) if c in SUPPORTED_CATEGORIES]
    if not cats:
        cats = list(SUPPORTED_CATEGORIES)  # 默认全订阅
    with _lock:
        tokens = _load_tokens()
        tokens[device_id] = {
            "push_token": push_token,
            "categories": cats,
            "registered_at": _now_iso(),
        }
        _save_tokens(tokens)
    logger.info("注册 push token device=%s cats=%s", device_id[:8], cats)
    return True


def unregister_push_token(device_id: str) -> bool:
    """注销设备的 push token（解除配对 / 关闭通知时调用）。"""
    if not device_id:
        return False
    with _lock:
        tokens = _load_tokens()
        if device_id in tokens:
            del tokens[device_id]
            _save_tokens(tokens)
            logger.info("注销 push token device=%s", device_id[:8])
            return True
        return False


def get_push_token(device_id: str) -> Optional[str]:
    """查询单设备的 push token。"""
    with _lock:
        tokens = _load_tokens()
        entry = tokens.get(device_id)
        return entry.get("push_token") if entry else None


def list_subscribers(category: str) -> list:
    """查询订阅了某分类的所有 (device_id, push_token)。"""
    with _lock:
        tokens = _load_tokens()
        return [
            (did, t["push_token"])
            for did, t in tokens.items()
            if category in t.get("categories", []) and t.get("push_token")
        ]


# ============================================================
# Expo Push Server 调用
# ============================================================

def _send_one(push_token: str, title: str, body: str,
              data: Optional[dict] = None,
              category: str = "default") -> bool:
    """向单个 push_token 发送一条通知。失败返回 False。"""
    payload = {
        "to": push_token,
        "title": title,
        "body": body,
        "sound": "default" if category == "critical" else None,
        "badge": 1 if category == "critical" else 0,
        "channelId": category,  # Android：critical / default
        "priority": "high" if category == "critical" else "default",
        "data": data or {},
    }
    payload = {k: v for k, v in payload.items() if v is not None}

    try:
        req = urllib.request.Request(
            _EXPO_PUSH_URL,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=_EXPO_REQUEST_TIMEOUT) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
        if isinstance(resp_data, dict):
            if resp_data.get("data", {}).get("status") == "ok":
                return True
            details = resp_data.get("data", {}).get("details", {})
            if details.get("error") in ("DeviceNotRegistered", "InvalidCredentials"):
                logger.warning("push token 失效，自动注销: %s... %s",
                               push_token[:20], details.get("error"))
                _unregister_by_token(push_token)
        return False
    except Exception as e:
        logger.warning("发送 push 失败 token=%s...: %s", push_token[:20], e)
        return False


def _unregister_by_token(push_token: str) -> None:
    """通过 token 字符串反查 device_id 并注销（Expo 返回 DeviceNotRegistered 时用）。"""
    with _lock:
        tokens = _load_tokens()
        for did, t in list(tokens.items()):
            if t.get("push_token") == push_token:
                del tokens[did]
                _save_tokens(tokens)
                logger.info("自动注销失效 push token device=%s", did[:8])
                return


def send_to_device(device_id: str, title: str, body: str,
                    data: Optional[dict] = None,
                    category: str = "default") -> bool:
    """向指定设备发送推送。"""
    push_token = get_push_token(device_id)
    if not push_token:
        return False
    return _send_one(push_token, title, body, data, category)


def broadcast(category: str, title: str, body: str,
              data: Optional[dict] = None) -> int:
    """向订阅某分类的所有设备广播。返回成功发送数量。"""
    subscribers = list_subscribers(category)
    if not subscribers:
        return 0
    success = 0
    for device_id, push_token in subscribers:
        enriched_data = {**(data or {}), "device_id": device_id}
        if _send_one(push_token, title, body, enriched_data, category):
            success += 1
    logger.info("broadcast cat=%s sent=%d/%d", category, success, len(subscribers))
    return success


# ============================================================
# 事件 → 推送 转换
# ============================================================

def _task_status_to_event(status: str, success: Optional[bool]) -> Optional[str]:
    """桌面端任务终态 → push 事件分类键。"""
    if status == "已完成" or (success is True):
        return "task_finished_success"
    if status == "失败" or (success is False):
        return "task_finished_failed"
    return None


def notify_event(event_key: str, data: dict) -> None:
    """通用事件通知入口。在后台线程异步广播。"""
    category = _EVENT_CATEGORY_MAP.get(event_key)
    if not category:
        return
    title, body = _build_message(event_key, data)
    enriched_data = {
        "category": category,
        "route": _route_for_event(event_key),
        "event": event_key,
        **(data or {}),
    }
    threading.Thread(
        target=broadcast,
        args=(category, title, body, enriched_data),
        daemon=True,
        name=f"push-{event_key}",
    ).start()


def _build_message(event_key: str, data: dict) -> tuple:
    """根据事件类型构建通知标题 + 正文。"""
    title = "Lumio"
    body = ""
    if event_key == "task_finished_success":
        title = "下载完成"
        body = (data.get("title") or "任务")[:80]
    elif event_key == "task_finished_failed":
        title = "下载失败"
        err = data.get("error") or "未知错误"
        body = f"{(data.get('title') or '任务')[:60]} · {err[:40]}"
    elif event_key == "queue_drained":
        title = "队列已清空"
        body = "所有下载任务已完成"
    elif event_key == "inbox_new":
        title = "Inbox 新增"
        body = (data.get("title") or "新内容")[:80]
    return title, body


def _route_for_event(event_key: str) -> str:
    """通知点击跳转路由（对齐移动端 usePush.resolveRoute 白名单）。"""
    if event_key.startswith("task_finished"):
        return "/(tabs)/downloads"
    if event_key == "inbox_new":
        return "/(tabs)/inbox"
    if event_key == "queue_drained":
        return "/(tabs)/downloads"
    return "/(tabs)/downloads"


# ============================================================
# EventBus 钩子（对业务零侵入）
# ============================================================

def install_event_hook(bus: Any) -> None:
    """给 EventBus 包装 publish 方法，过滤关键事件并触发推送。

    调用时机：api_fastapi.create_app 内，EventBus 创建后立即调用。
    """
    original_publish = bus.publish

    def patched_publish(event_type: str, data: Any = None) -> None:
        try:
            original_publish(event_type, data)
        except Exception as e:
            logger.warning("原 publish 异常: %s", e)
        try:
            _dispatch_push_hook(event_type, data)
        except Exception as e:
            logger.warning("push hook 异常 event=%s: %s", event_type, e)

    bus.publish = patched_publish
    logger.info("已安装 push event hook")


def _dispatch_push_hook(event_type: str, data: Any) -> None:
    """根据 WS 事件类型分发到 push_service.notify_event。"""
    if not isinstance(data, dict):
        return

    if event_type == "task_finished":
        success = bool(data.get("success", False))
        event_key = _task_status_to_event("", success)
        if event_key:
            notify_event(event_key, {
                "task_id": data.get("task_id", ""),
                "title": data.get("title", ""),
                "error": data.get("error", ""),
            })
    elif event_type == "task_status_changed":
        status = data.get("status", "")
        event_key = _task_status_to_event(status, None)
        if event_key:
            notify_event(event_key, {
                "task_id": data.get("task_id", ""),
                "title": data.get("title", ""),
                "error": data.get("error", ""),
            })
    elif event_type == "queue_drained":
        notify_event("queue_drained", data)
    elif event_type == "inbox_changed":
        action = data.get("action", "")
        if action == "add":
            notify_event("inbox_new", {
                "inbox_id": data.get("inbox_id", ""),
                "title": data.get("title", ""),
            })


# ============================================================
# 测试入口
# ============================================================

def send_test_push(device_id: str) -> bool:
    """向指定设备发送测试推送（设置页"测试通知"按钮触发）。"""
    return send_to_device(
        device_id,
        title="Lumio · 测试通知",
        body="推送通道已连通 ✓",
        data={"category": "default", "route": "/(tabs)/settings", "test": True},
        category="default",
    )
