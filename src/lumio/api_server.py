"""本地 HTTP API — 接收浏览器扩展采集的内容，写入 Inbox。"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict

from flask import Flask, jsonify, request

from . import __version__

logger = logging.getLogger(__name__)

app = Flask(__name__)

# 过滤 /health 请求日志（浏览器插件每 5s 轮询，不需输出）
_werkzeug_logger = logging.getLogger("werkzeug")
_werkzeug_logger.addFilter(type("NoHealthFilter", (logging.Filter,), {
    "filter": lambda _, rec: "/health" not in rec.getMessage()
})())

_inbox_manager = None  # type: ignore
_server_thread: threading.Thread | None = None

# ── 简易限流 ────────────────────────────────────────────────────────
_rate_lock = threading.Lock()
_rate_counts: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT = 60        # 每分钟最多请求数
_RATE_WINDOW = 60.0     # 窗口（秒）
_rate_last_cleanup = 0.0


def _check_rate_limit(ip: str) -> bool:
    """返回 True 表示允许，False 表示限流。"""
    global _rate_last_cleanup
    now = time.monotonic()
    with _rate_lock:
        # 定期清理过期 IP（每 5 分钟）
        if now - _rate_last_cleanup > 300:
            _rate_last_cleanup = now
            expired_ips = [k for k, v in _rate_counts.items()
                           if not v or now - v[-1] > _RATE_WINDOW]
            for k in expired_ips:
                del _rate_counts[k]

        timestamps = _rate_counts[ip]
        _rate_counts[ip] = [t for t in timestamps if now - t < _RATE_WINDOW]
        if len(_rate_counts[ip]) >= _RATE_LIMIT:
            return False
        _rate_counts[ip].append(now)
        return True


# ── CORS ────────────────────────────────────────────────────────────

_ALLOWED_PREFIXES = ("chrome-extension://", "moz-extension://")


@app.after_request
def _add_cors(response):
    origin = request.headers.get("Origin", "")
    if any(origin.startswith(p) for p in _ALLOWED_PREFIXES) or origin == "http://127.0.0.1:38900":
        response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


# ── 路由 ────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "version": __version__})


@app.route("/capture", methods=["POST", "OPTIONS"])
def capture():
    if request.method == "OPTIONS":
        return "", 204

    ip = request.remote_addr or "unknown"
    if not _check_rate_limit(ip):
        return jsonify({"success": False, "error": "Rate limit exceeded"}), 429

    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"success": False, "error": "url is required"}), 400
    if len(url) > 2048:
        return jsonify({"success": False, "error": "url too long"}), 400
    if not url.startswith(("http://", "https://")):
        return jsonify({"success": False, "error": "invalid url scheme"}), 400

    if _inbox_manager is None:
        return jsonify({"success": False, "error": "Inbox not ready"}), 503

    item_id = _inbox_manager.add_item(
        url=url,
        source=data.get("source", "browser"),
        type_=data.get("type", "url"),
        title=data.get("title", ""),
        author=data.get("author", ""),
        platform=data.get("platform", ""),
        thumbnail_url=data.get("thumbnail", ""),
        duration=data.get("duration"),
        direct_url=data.get("direct_url", ""),
    )
    return jsonify({"success": True, "inbox_id": item_id})


# ── 生命周期 ────────────────────────────────────────────────────────

_srv = None  # werkzeug BaseWSGIServer instance


def start_server(inbox_manager, port: int = 38900) -> bool:
    """启动 API 服务（daemon thread）。返回 True 表示成功。"""
    global _inbox_manager, _server_thread, _srv
    _inbox_manager = inbox_manager

    # 端口预检
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        sock.close()
    except OSError:
        logger.warning("端口 %d 被占用，API 服务未启动", port)
        return False

    from werkzeug.serving import make_server
    try:
        _srv = make_server("127.0.0.1", port, app, threaded=True)
    except OSError:
        logger.warning("端口 %d 被占用，API 服务未启动", port)
        return False

    _server_thread = threading.Thread(target=_srv.serve_forever, daemon=True)
    _server_thread.start()
    logger.info("本地 API 已启动: http://127.0.0.1:%d", port)
    return True


def stop_server() -> None:
    """优雅关闭 API 服务，释放端口。"""
    global _srv, _server_thread
    if _srv:
        _srv.shutdown()
        _srv = None
    if _server_thread and _server_thread.is_alive():
        _server_thread.join(timeout=3)
        _server_thread = None
    logger.info("本地 API 已关闭")
