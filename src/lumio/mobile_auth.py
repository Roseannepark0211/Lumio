"""移动端鉴权工具：JWT 签发/校验 + 设备存储 + 配对码 + 限流。

设计原则（对齐 AGENTS.md "L2 目录隔离"）：
- 仅新增模块，不修改 queue_manager / providers / library_manager 等业务层
- JWT 用 stdlib (hmac/hashlib/base64/json) 实现 HS256，避免新增 PyJWT 依赖
- 限流用内存令牌桶，避免新增 slowapi 依赖
- 设备数据存 ~/.lumio/devices.json（独立文件，不污染现有 SQLite/JSON）

安全注意事项：
- SECRET_KEY 持久化到 ~/.lumio/mobile_secret.key，权限 0600
- 配对码 6 位数字，5 分钟过期，使用后失效
- 双 token：access 2h + refresh 30d（refresh 旋转时旧 jti 加入黑名单）
- JWT payload 含 device_id / type(access|refresh) / fp / jti(refresh) / exp / iat
- 设备撤销后所有 JWT 立即失效（每次受保护请求查 devices.json）
- jti 黑名单持久化到 devices.json 的 revoked_jtis 字段
- 向后兼容：旧 JWT（无 type 字段）视为 access，仅校验 exp + device_id
- 阶段4：JWT payload 含 session_secret（32 字节），HKDF 派生 per-session AES-GCM key
  - 敏感路径请求/响应用 AES-256-GCM 加密（防中间人嗅探）
  - 加密格式：base64url(nonce).base64url(ciphertext+tag)
  - session_secret 在 payload 中明文（base64 可解码），但 HTTPS 已加密传输
  - 防护层级：HTTPS 防网络嗅探 → 应用层加密防 HTTPS 降级/日志泄露
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
# AES-256-GCM 加密（阶段4敏感数据加密）
# ============================================================
# cryptography 是必需依赖（stdlib 无 AES-GCM）
# 延迟导入：仅敏感路径才触发，避免 dev mode 无 cryptography 启动失败
_AESGCM = None
_HKDF = None
_hashes = None


def _load_crypto():
    """延迟加载 cryptography 模块。仅敏感路径调用时触发。"""
    global _AESGCM, _HKDF, _hashes
    if _AESGCM is not None:
        return
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from cryptography.hazmat.primitives import hashes
        _AESGCM = AESGCM
        _HKDF = HKDF
        _hashes = hashes
    except ImportError as e:
        raise RuntimeError(
            "cryptography package required for sensitive path encryption. "
            "Install: pip install cryptography"
        ) from e


def _b64url_encode(data: bytes) -> str:
    """base64url 编码（无 padding）。"""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    """base64url 解码（自动补 padding）。"""
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def derive_session_key(session_secret: str, purpose: str) -> bytes:
    """从 session_secret 派生 AES-256 key（32 字节）。

    purpose 区分请求/响应方向：
    - "req" 客户端加密请求 / 服务端解密请求
    - "resp" 服务端加密响应 / 客户端解密响应

    HKDF 输入：
    - IKM: session_secret（base64url 解码为 32 字节）
    - salt: 固定 "lumio-v1"（版本化，便于未来密钥轮换）
    - info: purpose.encode()
    - length: 32（AES-256）
    """
    _load_crypto()
    # session_secret 是 base64url 编码的 32 字节随机数
    ikm = _b64url_decode(session_secret) if isinstance(session_secret, str) else session_secret
    hkdf = _HKDF(
        algorithm=_hashes.SHA256(),
        length=32,
        salt=b"lumio-v1",
        info=purpose.encode("utf-8"),
    )
    return hkdf.derive(ikm)


def aes_gcm_encrypt(key: bytes, plaintext: bytes) -> str:
    """AES-256-GCM 加密，返回 base64url(nonce).base64url(ciphertext+tag)。"""
    _load_crypto()
    aesgcm = _AESGCM(key)
    nonce = os.urandom(12)  # GCM 推荐 96 位 nonce
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)  # None = 不带 AAD
    return f"{_b64url_encode(nonce)}.{_b64url_encode(ciphertext)}"


def aes_gcm_decrypt(key: bytes, body: str) -> bytes:
    """AES-256-GCM 解密，输入 base64url(nonce).base64url(ciphertext+tag)。

    失败抛 ValueError（tag 不匹配 / 格式错误）。
    """
    _load_crypto()
    from cryptography.exceptions import InvalidTag
    if "." not in body:
        raise ValueError("invalid encrypted body format (missing '.')")
    nonce_b64, ct_b64 = body.split(".", 1)
    nonce = _b64url_decode(nonce_b64)
    ciphertext = _b64url_decode(ct_b64)
    aesgcm = _AESGCM(key)
    try:
        return aesgcm.decrypt(nonce, ciphertext, None)
    except InvalidTag as e:
        raise ValueError("GCM tag mismatch (wrong key or corrupted data)") from e


def generate_session_secret() -> str:
    """生成 32 字节随机 session_secret，返回 base64url 编码字符串。"""
    return _b64url_encode(os.urandom(32))


def encrypt_payload(session_secret: str, purpose: str, plaintext: bytes) -> str:
    """便捷封装：从 session_secret 派生 key + 加密。"""
    key = derive_session_key(session_secret, purpose)
    return aes_gcm_encrypt(key, plaintext)


def decrypt_payload(session_secret: str, purpose: str, body: str) -> bytes:
    """便捷封装：从 session_secret 派生 key + 解密。"""
    key = derive_session_key(session_secret, purpose)
    return aes_gcm_decrypt(key, body)

# ============================================================
# 路径常量
# ============================================================
_APP_DIR = Path.home() / ".lumio"
_SECRET_FILE = _APP_DIR / "mobile_secret.key"
_DEVICES_FILE = _APP_DIR / "devices.json"

# JWT 配置（双 token）
_JWT_ALG = "HS256"
_JWT_ACCESS_TTL = 2 * 3600          # access token: 2 小时
_JWT_REFRESH_TTL = 30 * 24 * 3600   # refresh token: 30 天
_JWT_LEEWAY = 5                     # 时钟漂移容忍（秒）
# 向后兼容：旧单 token TTL（issue_jwt 保留为兼容入口，不推荐使用）
_JWT_LEGACY_TTL = 30 * 24 * 3600

# 配对码配置
_PAIR_CODE_TTL = 5 * 60  # 5 分钟
_PAIR_CODE_LEN = 6  # 6 位数字

# 限流配置
_RATE_LIMIT_PAIR = 5  # /api/auth/pair: 5 次/min/IP

# jti 黑名单自动清理：超过 refresh TTL 的 jti 不再需要保留
_JTI_CLEANUP_THRESHOLD = _JWT_REFRESH_TTL

# 全局锁（保护 devices.json + pair_codes + rate_limiter + jti 黑名单）
_lock = threading.RLock()

# 缓存 SECRET_KEY（启动时加载一次）
_secret_key_cache: Optional[bytes] = None

# 内存中的配对码列表（运行时生成，重启后失效）
_pair_codes: list[dict] = []

# 内存限流桶：{key: [timestamp, ...]}
_rate_buckets: dict[str, list[float]] = {}

# 内存 jti 黑名单缓存（启动时从 devices.json 加载，避免每次请求读盘）
# 结构：{jti: revoked_at_unix}
_jti_blacklist_cache: dict[str, float] = {}
_jti_blacklist_loaded = False


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
    """[向后兼容] 为设备签发旧式单 JWT（无 type/fp/jti），返回 (token, expires_at_unix)。

    新代码应使用 issue_access_jwt / issue_refresh_jwt。
    保留此函数仅为兼容历史调用方（如已部署的旧客户端）。
    """
    exp = int(time.time()) + _JWT_LEGACY_TTL
    payload = {
        "device_id": device_id,
        "exp": exp,
        "iat": int(time.time()),
    }
    return jwt_encode(payload), exp


def issue_access_jwt(device_id: str, fingerprint: str = "", session_secret: str = "") -> tuple[str, int]:
    """签发 access token（2h 有效）。payload 含 type=access + fp + session_secret。

    session_secret 用于阶段4敏感路径 AES-GCM 加解密（HKDF 派生 per-session key）。
    pair 时生成，refresh 时沿用（rotate_refresh_token 传入）。
    """
    now = int(time.time())
    exp = now + _JWT_ACCESS_TTL
    payload = {
        "device_id": device_id,
        "type": "access",
        "fp": fingerprint or "",
        "exp": exp,
        "iat": now,
    }
    # session_secret 可选（向后兼容：旧客户端无此字段时跳过加密）
    if session_secret:
        payload["ss"] = session_secret
    return jwt_encode(payload), exp


def issue_refresh_jwt(device_id: str, fingerprint: str = "", session_secret: str = "") -> tuple[str, str, int]:
    """签发 refresh token（30d 有效），返回 (token, jti, expires_at_unix)。

    jti 用于旋转黑名单：refresh 一次后旧 jti 立即失效。
    session_secret 同 access token，便于 refresh 后继续加密通信。
    """
    now = int(time.time())
    exp = now + _JWT_REFRESH_TTL
    jti = secrets.token_hex(16)  # 32 位 hex
    payload = {
        "device_id": device_id,
        "type": "refresh",
        "jti": jti,
        "fp": fingerprint or "",
        "exp": exp,
        "iat": now,
    }
    if session_secret:
        payload["ss"] = session_secret
    return jwt_encode(payload), jti, exp


# ============================================================
# devices.json 存储与查询
# ============================================================

def _load_devices() -> dict:
    """加载 devices.json。结构：{"devices": [...], "revoked_jtis": {...}}"""
    if not _DEVICES_FILE.exists():
        return {"devices": [], "revoked_jtis": {}}
    try:
        with open(_DEVICES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"devices": [], "revoked_jtis": {}}
        # 兼容旧格式（无 revoked_jtis 字段）
        if "devices" not in data:
            data["devices"] = []
        if "revoked_jtis" not in data:
            data["revoked_jtis"] = {}
        return data
    except Exception:
        return {"devices": [], "revoked_jtis": {}}


def _save_devices(data: dict) -> None:
    _APP_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _DEVICES_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, _DEVICES_FILE)  # 原子替换


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_jti_blacklist_loaded() -> None:
    """懒加载 jti 黑名单到内存（首次调用后缓存，避免每次请求读盘）。"""
    global _jti_blacklist_loaded
    if _jti_blacklist_loaded:
        return
    with _lock:
        if _jti_blacklist_loaded:
            return
        data = _load_devices()
        revoked = data.get("revoked_jtis", {})
        if isinstance(revoked, dict):
            _jti_blacklist_cache.update(revoked)
        _jti_blacklist_loaded = True


def _is_jti_revoked(jti: str) -> bool:
    """jti 是否在黑名单中。同时清理过期条目（超过 refresh TTL）。"""
    if not jti:
        return False
    _ensure_jti_blacklist_loaded()
    return jti in _jti_blacklist_cache


def _revoke_jti(jti: str) -> None:
    """将 jti 加入黑名单并持久化。refresh 旋转时调用。"""
    if not jti:
        return
    _ensure_jti_blacklist_loaded()
    now = time.time()
    with _lock:
        # 清理过期 jti（超过 refresh TTL 的不再需要保留）
        cutoff = now - _JTI_CLEANUP_THRESHOLD
        expired = [k for k, v in _jti_blacklist_cache.items() if v < cutoff]
        for k in expired:
            del _jti_blacklist_cache[k]
        # 加入新 jti
        _jti_blacklist_cache[jti] = now
        # 持久化
        data = _load_devices()
        data["revoked_jtis"] = dict(_jti_blacklist_cache)
        _save_devices(data)


def register_device(device_name: str, device_fingerprint: str) -> dict:
    """注册新设备，返回设备信息 dict。

    device_fingerprint 必填（移动端指纹：UA+IP+设备名 hash），
    用于 access token 校验时比对（防 token 被盗用到其他设备）。
    """
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
    """撤销设备（吊销其 JWT）。已签发的 JWT 在下次请求时因 revoked=true 失效。

    注意：撤销设备不会撤销该设备的 jti 黑名单（jti 是 refresh token 的一次性 ID，
    设备已撤销后所有 refresh token 也失效，无需单独清理 jti）。
    """
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

def verify_token(token: str, expected_fp: str = "") -> Optional[dict]:
    """校验 access token（中间件用）。返回 payload 或 None。

    校验项：
    1. JWT 签名 + exp（jwt_decode）
    2. device_id 存在 + 设备未撤销
    3. type == "access"（拒绝 refresh token 用于访问 API）
       向后兼容：旧 JWT 无 type 字段视为 access
    4. jti 不在黑名单（access token 无 jti，跳过；refresh token 走 verify_refresh_token）
    5. fp 比对（可选）：expected_fp 非空时，payload.fp 必须匹配
       防止 token 被盗用到其他设备（fp = UA+IP hash）

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
    # type 校验：拒绝 refresh token 用于访问 API
    token_type = payload.get("type", "access")  # 向后兼容：无 type 视为 access
    if token_type != "access":
        return None
    # fp 强制校验（expected_fp 非空时）
    if expected_fp:
        token_fp = payload.get("fp", "")
        # 旧 JWT 无 fp 字段时跳过比对（向后兼容）
        if token_fp and token_fp != expected_fp:
            return None
    return payload


def verify_refresh_token(token: str, expected_fp: str = "") -> Optional[dict]:
    """校验 refresh token（仅 /api/auth/refresh 用）。

    校验项：
    1. JWT 签名 + exp
    2. type == "refresh"
    3. jti 存在且不在黑名单
    4. device_id 存在 + 设备未撤销
    5. fp 比对（可选）

    成功后调用方应调用 _revoke_jti(jti) 旋转（旧 refresh 一次性失效）。
    """
    try:
        payload = jwt_decode(token)
    except JWTError:
        return None
    if payload.get("type") != "refresh":
        return None
    jti = payload.get("jti", "")
    if not jti or _is_jti_revoked(jti):
        return None
    device_id = payload.get("device_id")
    if not device_id or is_device_revoked(device_id):
        return None
    if expected_fp:
        token_fp = payload.get("fp", "")
        if token_fp and token_fp != expected_fp:
            return None
    return payload


def rotate_refresh_token(old_token: str, expected_fp: str = "") -> Optional[dict]:
    """refresh token 旋转：校验旧 token → 撤销旧 jti → 签发新 access + refresh。

    返回 {access_token, refresh_token, access_expires_at, refresh_expires_at, device_id, session_secret}
    或 None（校验失败）。

    session_secret 沿用旧 refresh token 的 ss 字段（保持加密会话连续性）。
    """
    payload = verify_refresh_token(old_token, expected_fp)
    if payload is None:
        return None
    device_id = payload["device_id"]
    old_jti = payload["jti"]
    fp = payload.get("fp", "")
    ss = payload.get("ss", "")  # 沿用 session_secret
    # 撤销旧 jti（一次性使用）
    _revoke_jti(old_jti)
    # 签发新 access + refresh（沿用 session_secret）
    access_token, access_exp = issue_access_jwt(device_id, fp, ss)
    refresh_token, new_jti, refresh_exp = issue_refresh_jwt(device_id, fp, ss)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "access_expires_at": access_exp,
        "refresh_expires_at": refresh_exp,
        "device_id": device_id,
        "session_secret": ss,
    }


def extract_bearer_token(auth_header: str) -> Optional[str]:
    """从 Authorization 头提取 Bearer token。"""
    if not auth_header:
        return None
    parts = auth_header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None
