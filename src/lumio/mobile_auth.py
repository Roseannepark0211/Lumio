"""移动端鉴权工具：JWT 签发/校验 + 设备存储 + 配对码 + 限流。

设计原则（对齐 AGENTS.md "L2 目录隔离"）：
- 仅新增模块，不修改 queue_manager / providers / library_manager 等业务层
- JWT 用 stdlib (hmac/hashlib/base64/json) 实现 HS256，避免新增 PyJWT 依赖
- 限流用内存令牌桶，避免新增 slowapi 依赖
- 设备数据存 ~/.lumio/devices.json（独立文件，不污染现有 SQLite/JSON）

安全注意事项：
- SECRET_KEY 持久化到 ~/.lumio/mobile_secret.key，权限 0600
- 配对码 6 位数字，5 分钟过期，使用后失效
- JWT 有效期 30 天，含 device_id + exp + iat
- 设备撤销后 JWT 立即失效（黑名单机制，每次请求查 devices.json）
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ============================================================
# 路径常量
# ============================================================
_APP_DIR = Path.home() / ".lumio"
_SECRET_FILE = _APP_DIR / "mobile_secret.key"
_DEVICES_FILE = _APP_DIR / "devices.json"

# JWT 配置
_JWT_ALG = "HS256"
_JWT_TTL = 30 * 24 * 3600  # 30 天
_JWT_LEEWAY = 5  # 时钟漂移容忍（秒）

# 配对码配置
_PAIR_CODE_TTL = 5 * 60  # 5 分钟
_PAIR_CODE_LEN = 6  # 6 位数字

# 限流配置
_RATE_LIMIT_PAIR = 5  # /api/auth/pair: 5 次/min/IP

# 全局锁（保护 devices.json + pair_codes + rate_limiter）
_lock = threading.RLock()

# 缓存 SECRET_KEY（启动时加载一次）
_secret_key_cache: Optional[bytes] = None

# 内存中的配对码列表（运行时生成，重启后失效）
_pair_codes: list[dict] = []

# 内存限流桶：{key: [timestamp, ...]}
_rate_buckets: dict[str, list[float]] = {}


# ============================================================
# SECRET_KEY 管理
# ============================================================

def _get_secret_key() -> bytes:
    """加载或生成 JWT 签名密钥（持久化到 ~/.lumio/mobile_secret.key）。

    文件权限 0600，仅当前用户可读。重启后保持同一密钥，已签发的 JWT 不失效。
    """
    global _secret_key_cache
    if _secret_key_cache is not None:
        return _secret_key_cache
    _APP_DIR.mkdir(parents=True, exist_ok=True)
    if _SECRET_FILE.exists():
        try:
            key = _SECRET_FILE.read_bytes().strip()
            if len(key) >= 32:
                _secret_key_cache = key
                return key
        except Exception:
            pass
    # 生成 32 字节随机密钥
    key = secrets.token_bytes(32)
    _SECRET_FILE.write_bytes(key)
    try:
        os.chmod(_SECRET_FILE, 0o600)
    except OSError:
        pass  # Windows 上 chmod 部分无效，忽略
    _secret_key_cache = key
    return key


# ============================================================
# JWT 签发 / 校验（HS256，stdlib 实现）
# ============================================================

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _jwt_sign(header_b64: str, payload_b64: str) -> str:
    msg = f"{header_b64}.{payload_b64}".encode("ascii")
    sig = hmac.new(_get_secret_key(), msg, hashlib.sha256).digest()
    return _b64url_encode(sig)


def jwt_encode(payload: dict) -> str:
    """签发 JWT。payload 自动附加 iat，调用方需传 exp + device_id。"""
    header = {"alg": _JWT_ALG, "typ": "JWT"}
    if "iat" not in payload:
        payload = {**payload, "iat": int(time.time())}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    sig = _jwt_sign(header_b64, payload_b64)
    return f"{header_b64}.{payload_b64}.{sig}"


class JWTError(Exception):
    """JWT 校验失败基类。"""


def jwt_decode(token: str) -> dict:
    """校验并解码 JWT。失败抛 JWTError。

    校验项：格式（3 段 base64url）+ 签名（HMAC-SHA256）+ exp（允许 leeway）。
    """
    if not token or not isinstance(token, str):
        raise JWTError("empty token")
    parts = token.split(".")
    if len(parts) != 3:
        raise JWTError("invalid format")
    header_b64, payload_b64, sig_b64 = parts
    expected_sig = _jwt_sign(header_b64, payload_b64)
    if not hmac.compare_digest(sig_b64, expected_sig):
        raise JWTError("invalid signature")
    try:
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception as e:
        raise JWTError(f"decode error: {e}")
    if header.get("alg") != _JWT_ALG:
        raise JWTError(f"unexpected alg: {header.get('alg')}")
    now = int(time.time())
    exp = payload.get("exp")
    if exp is not None and now > int(exp) + _JWT_LEEWAY:
        raise JWTError("expired")
    return payload


def issue_jwt(device_id: str) -> tuple[str, int]:
    """为设备签发新 JWT，返回 (token, expires_at_unix)。"""
    exp = int(time.time()) + _JWT_TTL
    payload = {
        "device_id": device_id,
        "exp": exp,
        "iat": int(time.time()),
    }
    return jwt_encode(payload), exp


# ============================================================
# devices.json 存储与查询
# ============================================================

def _load_devices() -> dict:
    """加载 devices.json。结构：{"devices": [...]}"""
    if not _DEVICES_FILE.exists():
        return {"devices": []}
    try:
        with open(_DEVICES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "devices" not in data:
            return {"devices": []}
        return data
    except Exception:
        return {"devices": []}


def _save_devices(data: dict) -> None:
    _APP_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _DEVICES_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, _DEVICES_FILE)  # 原子替换


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def register_device(device_name: str, device_fingerprint: str) -> dict:
    """注册新设备，返回设备信息 dict。"""
    with _lock:
        data = _load_devices()
        device_id = secrets.token_hex(8)  # 16 位 hex
        now = _now_iso()
        device = {
            "device_id": device_id,
            "device_name": device_name or "未命名设备",
            "device_fingerprint": device_fingerprint or "",
            "paired_at": now,
            "last_active_at": now,
            "revoked": False,
        }
        data["devices"].append(device)
        _save_devices(data)
        return device


def get_device(device_id: str) -> Optional[dict]:
    with _lock:
        data = _load_devices()
        for d in data["devices"]:
            if d["device_id"] == device_id:
                return dict(d)
        return None


def list_devices() -> list[dict]:
    with _lock:
        data = _load_devices()
        return [dict(d) for d in data["devices"]]


def touch_device_active(device_id: str) -> None:
    """更新设备 last_active_at 时间戳。仅在 /api/auth/me / refresh 等低频端点调用。"""
    with _lock:
        data = _load_devices()
        for d in data["devices"]:
            if d["device_id"] == device_id:
                d["last_active_at"] = _now_iso()
                break
        _save_devices(data)


def rename_device(device_id: str, new_name: str) -> Optional[dict]:
    with _lock:
        data = _load_devices()
        for d in data["devices"]:
            if d["device_id"] == device_id:
                d["device_name"] = new_name
                _save_devices(data)
                return dict(d)
        return None


def revoke_device(device_id: str) -> bool:
    """撤销设备（吊销其 JWT）。已签发的 JWT 在下次请求时因 revoked=true 失效。"""
    with _lock:
        data = _load_devices()
        for d in data["devices"]:
            if d["device_id"] == device_id:
                d["revoked"] = True
                _save_devices(data)
                return True
        return False


def is_device_revoked(device_id: str) -> bool:
    """设备是否已撤销（或不存在）。每次受保护请求都查（性能可接受）。"""
    with _lock:
        d = get_device(device_id)
        return d is None or d.get("revoked", False)


# ============================================================
# 配对码生成与校验
# ============================================================

def generate_pair_code() -> str:
    """生成 6 位数字配对码，5 分钟过期。"""
    code = "".join(secrets.choice("0123456789") for _ in range(_PAIR_CODE_LEN))
    with _lock:
        # 清理过期码
        now = time.time()
        _pair_codes[:] = [
            c for c in _pair_codes if c["expires_at"] > now and not c["used"]
        ]
        _pair_codes.append({
            "code": code,
            "created_at": now,
            "expires_at": now + _PAIR_CODE_TTL,
            "used": False,
        })
    return code


def validate_pair_code(code: str) -> bool:
    """校验配对码：未过期 + 未使用。成功后标记为已使用（一次性）。"""
    if not code or not isinstance(code, str):
        return False
    code = code.strip()
    with _lock:
        now = time.time()
        for c in _pair_codes:
            if c["code"] == code and not c["used"] and c["expires_at"] > now:
                c["used"] = True
                return True
        return False


# ============================================================
# 限流（内存滑动窗口）
# ============================================================

def rate_limit_check(key: str, max_count: int, window_sec: int = 60) -> bool:
    """检查 key 在 window_sec 窗口内是否未超 max_count。

    返回 True 表示允许通过（未超限），False 表示已超限。
    滑动窗口：记录每次请求时间戳，清理过期。
    """
    with _lock:
        now = time.time()
        bucket = _rate_buckets.setdefault(key, [])
        cutoff = now - window_sec
        bucket[:] = [ts for ts in bucket if ts > cutoff]
        if len(bucket) >= max_count:
            return False
        bucket.append(now)
        return True


# ============================================================
# 综合校验：JWT 解码 + 设备未撤销
# ============================================================

def verify_token(token: str) -> Optional[dict]:
    """解码 JWT + 检查设备未撤销。返回 payload 或 None。

    不在此处更新 last_active_at（避免每次受保护请求都写盘）；
    last_active_at 仅在 /api/auth/me / /api/auth/refresh 等低频端点显式调用
    touch_device_active 更新。
    """
    try:
        payload = jwt_decode(token)
    except JWTError:
        return None
    device_id = payload.get("device_id")
    if not device_id:
        return None
    if is_device_revoked(device_id):
        return None
    return payload


def extract_bearer_token(auth_header: str) -> Optional[str]:
    """从 Authorization 头提取 Bearer token。"""
    if not auth_header:
        return None
    parts = auth_header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None
