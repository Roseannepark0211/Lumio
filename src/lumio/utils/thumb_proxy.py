"""缩略图代理下载 — 服务端本地缓存 + ETag + 条件请求。

api_fastapi.py 的 /api/thumb-proxy 端点用此模块下载远程缩略图，
附加 Referer/Cookie 处理 IG/sinaimg/twimg 等 CDN 鉴权要求。

缓存策略：
- 缓存目录：~/.lumio/cache/thumb_proxy/<sha1(url)>.bin + .meta（json）
- 命中缓存且 <7 天：直接读本地文件返回，不访问远程
- 缓存过期：发 If-None-Match / If-Modified-Since 条件请求
  - 远程返回 304：刷新本地 mtime 后返回缓存
  - 远程返回 200：用新内容覆盖缓存
- 失败回退：远程不可达但缓存存在 → 返回旧缓存（best effort）

尺寸转换（可选）：
- 传 w/h 参数时，命中缓存后用 PIL 缩放到指定尺寸再返回
- 缩放结果另存 .thumb.png/.jpg，避免每次请求都重算
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Optional

import requests
from PIL import Image


# 需要 Referer 的 CDN 域名
_NEEDS_REFERER_DOMAINS = (
    "instagram.",
    "fbcdn.net",
    "sinaimg.cn",
    "twimg.com",
    "x.com",
)

# 缓存有效期 7 天
_CACHE_TTL = 7 * 24 * 3600


def _referer_for(url: str) -> str:
    """根据 URL 域名返回对应 Referer，无匹配返回空串。"""
    for d in _NEEDS_REFERER_DOMAINS:
        if d in url:
            if "instagram" in d or "fbcdn" in d:
                return "https://www.instagram.com/"
            if "sinaimg" in d:
                return "https://weibo.com/"
            if "twimg" in d or "x.com" in d:
                return "https://x.com/"
    return ""


def _load_cookie_header() -> str:
    """加载用户 cookie 文件内容作为 Cookie 请求头。无 cookie 返回空串。"""
    try:
        from .config import get_cookie_path
        cookie_path = get_cookie_path()
    except Exception:
        return ""
    if not cookie_path or not cookie_path.exists():
        return ""
    try:
        from ..providers.network.cookie import load_cookie_string
        return load_cookie_string(str(cookie_path))
    except Exception:
        return ""


def _cache_dir() -> Path:
    """返回缓存目录 Path，不存在则创建。"""
    try:
        from .config import get_lumio_dir
        base = Path(get_lumio_dir())
    except Exception:
        base = Path.home() / ".lumio"
    d = base / "cache" / "thumb_proxy"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_key(url: str) -> str:
    """URL → sha1 文件名前缀。"""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


def _read_meta(meta_path: Path) -> dict:
    try:
        with meta_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_meta(meta_path: Path, meta: dict) -> None:
    try:
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f)
    except Exception:
        pass


def _is_expired(meta: dict) -> bool:
    """缓存是否过期（超过 _CACHE_TTL）。"""
    ts = meta.get("fetched_at", 0)
    return (time.time() - ts) > _CACHE_TTL


def _build_headers(extra: dict | None = None) -> dict:
    headers = {"User-Agent": "Mozilla/5.0 Lumio/4.2"}
    if extra:
        headers.update(extra)
    return headers


def _remote_fetch(
    url: str,
    timeout: int,
    etag: Optional[str] = None,
    last_modified: Optional[str] = None,
) -> tuple[bytes, str, Optional[str], Optional[str], int]:
    """发起远程请求，返回 (content, content_type, etag, last_modified, status_code)。

    命中 304 时 content 为空字节。
    """
    headers = _build_headers()
    ref = _referer_for(url)
    if ref:
        headers["Referer"] = ref
    cookie = _load_cookie_header()
    if cookie:
        headers["Cookie"] = cookie
    # 条件请求
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    session = requests.Session()
    session.trust_env = True
    r = session.get(url, headers=headers, timeout=timeout, stream=False)
    if r.status_code == 304:
        return b"", r.headers.get("Content-Type", "image/jpeg"), etag, last_modified, 304
    r.raise_for_status()
    content_type = r.headers.get("Content-Type", "image/jpeg")
    return r.content, content_type, r.headers.get("ETag"), r.headers.get("Last-Modified"), r.status_code


def _resize_bytes(content: bytes, target_w: int, target_h: int) -> tuple[bytes, str]:
    """用 PIL 把图片字节缩放到 target_w × target_h（保持比例填充），返回 (jpeg_bytes, content_type)。"""
    from io import BytesIO
    img = Image.open(BytesIO(content))
    # 转 RGB（PNG 透明通道 JPEG 不支持）
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGB")
    # contain 模式：缩放到目标框内（不裁剪）
    img.thumbnail((target_w, target_h))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue(), "image/jpeg"


def fetch_thumbnail_bytes(
    url: str,
    timeout: int = 15,
    target_w: int = 0,
    target_h: int = 0,
) -> tuple[bytes, str, Optional[str]]:
    """下载远程缩略图（带服务端缓存），返回 (content_bytes, content_type, etag)。

    Args:
        url: 远程图片 URL
        timeout: 请求超时秒数
        target_w: > 0 时用 PIL 缩放到该宽度
        target_h: > 0 时用 PIL 缩放到该高度

    Returns:
        (content_bytes, content_type, etag)
        - etag 用于响应头，让浏览器也能发 304
        - 失败但缓存存在 → 返回旧缓存
        - 失败且无缓存 → 抛 requests.HTTPError / RequestException
    """
    cache_d = _cache_dir()
    key = _cache_key(url)
    bin_path = cache_d / f"{key}.bin"
    meta_path = cache_d / f"{key}.meta"

    meta = _read_meta(meta_path)
    has_cache = bin_path.exists() and meta
    need_revalidate = has_cache and _is_expired(meta)

    # 1. 缓存未过期 → 直接返回（可选缩放）
    if has_cache and not need_revalidate:
        content = bin_path.read_bytes()
        content_type = meta.get("content_type", "image/jpeg")
        etag = meta.get("etag")
        if target_w > 0 or target_h > 0:
            content, content_type = _apply_resize(content, content_type, cache_d, key, target_w, target_h)
        return content, content_type, etag

    # 2. 缓存过期或无缓存 → 发条件请求
    try:
        content, content_type, etag, last_modified, status = _remote_fetch(
            url,
            timeout,
            etag=meta.get("etag") if has_cache else None,
            last_modified=meta.get("last_modified") if has_cache else None,
        )
    except Exception:
        # 远程不可达但有旧缓存 → best-effort 返回旧缓存
        if has_cache:
            content = bin_path.read_bytes()
            content_type = meta.get("content_type", "image/jpeg")
            ret_etag = meta.get("etag")
            if target_w > 0 or target_h > 0:
                content, content_type = _apply_resize(content, content_type, cache_d, key, target_w, target_h)
            return content, content_type, ret_etag
        raise

    if status == 304:
        # 远程确认未变 → 刷新本地 mtime + fetched_at
        meta["fetched_at"] = time.time()
        _write_meta(meta_path, meta)
        content = bin_path.read_bytes()
        if target_w > 0 or target_h > 0:
            content, content_type = _apply_resize(content, content_type, cache_d, key, target_w, target_h)
        return content, content_type, meta.get("etag")

    # 3. 远程返回新内容 → 覆盖缓存
    try:
        bin_path.write_bytes(content)
        new_meta = {
            "url": url,
            "content_type": content_type,
            "etag": etag,
            "last_modified": last_modified,
            "fetched_at": time.time(),
        }
        _write_meta(meta_path, new_meta)
        # 缩放版本如有则失效（原内容变了）
        for suffix in (".thumb.jpg", ".thumb.png"):
            p = cache_d / f"{key}{suffix}"
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass
    except Exception:
        # 写缓存失败不影响返回
        pass

    if target_w > 0 or target_h > 0:
        content, content_type = _apply_resize(content, content_type, cache_d, key, target_w, target_h)
    return content, content_type, etag


def _apply_resize(
    content: bytes,
    content_type: str,
    cache_d: Path,
    key: str,
    target_w: int,
    target_h: int,
) -> tuple[bytes, str]:
    """命中缓存后做尺寸转换，缩放结果单独缓存。"""
    # 缩放缓存文件名：{key}.thumb_{w}x{h}.jpg
    thumb_name = f"{key}.thumb_{target_w}x{target_h}.jpg"
    thumb_path = cache_d / thumb_name
    if thumb_path.exists():
        try:
            return thumb_path.read_bytes(), "image/jpeg"
        except Exception:
            pass
    try:
        resized, _ = _resize_bytes(content, target_w, target_h)
        try:
            thumb_path.write_bytes(resized)
        except Exception:
            pass
        return resized, "image/jpeg"
    except Exception:
        # PIL 处理失败 → 返回原图
        return content, content_type
