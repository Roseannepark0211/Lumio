"""Lumio 缓存管理器。

统一管理所有缓存目录：
- thumbs/            — 缩略图缓存（Home/Library 预览缩略图）
- provider_cache/    — Provider MediaInfo 解析缓存
- cache/preview/     — X-Sou 视频预览缓存
- inbox_media/       — Telegram 媒体持久化存储（智能清理：仅清理已下载完成的）

不可清理的用户数据（不在本模块管理）：
- library.db / history.json / config.json / cookies.txt / notifications.json / queue.json

支持两种清理模式：
1. 手动清理：用户在设置页点击「立即清理」按钮
2. 定时清理：根据 config.cache_management 配置自动触发
   - "off"     — 不自动清理（默认）
   - "startup" — 每次启动时清理
   - "daily"   — 每天清理一次（按 last_cleaned 判断）
   - "weekly"  — 每周清理一次

清理策略：
- 默认保留最近 7 天的文件
- 超过 max_size_mb 上限时按 mtime 从旧到新删除直至达标
- 安全删除：只删除白名单扩展名文件，跳过子目录（避免误删）
- inbox_media/ 特殊策略：仅清理 InboxItem.status=downloaded/archived 对应的本地文件，
  保留 new/queued/failed 状态的文件（用户尚未下载到输出目录）
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from .config import load_config, save_config

logger = logging.getLogger(__name__)

_APP_DIR = Path.home() / ".lumio"

# 可管理的缓存目录（相对 ~/.lumio/）
_CACHE_DIRS = {
    "thumbs": _APP_DIR / "thumbs",
    "provider_cache": _APP_DIR / "provider_cache",
    "preview": _APP_DIR / "cache" / "preview",
    "inbox_media": _APP_DIR / "inbox_media",  # 智能清理（见 clean_inbox_media）
}

# 安全扩展名白名单（只清理这些文件类型，避免误删）
_SAFE_EXTS = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif",  # 图片
    ".mp4", ".webm", ".mov", ".avi", ".mkv",   # 视频
    ".mp3", ".m4a", ".aac", ".wav",             # 音频
    ".json",                                    # Provider/preview 元数据
    ".tmp",                                     # 临时文件
}

# 默认保留期（天）
DEFAULT_RETAIN_DAYS = 7
# 默认上限（MB）
DEFAULT_MAX_SIZE_MB = 500


def get_cache_dir(name: str) -> Path:
    """获取指定缓存目录的 Path（不存在则创建）。"""
    p = _CACHE_DIRS.get(name)
    if p is None:
        raise KeyError(f"未知缓存目录: {name}")
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_dir_size(path: Path) -> int:
    """递归计算目录大小（字节）。"""
    if not path.exists():
        return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                fp = Path(root) / f
                total += fp.stat().st_size
            except OSError:
                continue
    return total


def get_cache_stats() -> dict[str, dict]:
    """返回所有缓存目录的统计信息。

    Returns:
        {
            "thumbs": {"size_bytes": 2091234, "size_mb": 1.99, "file_count": 285},
            "provider_cache": {...},
            ...
            "_total": {"size_bytes": ..., "size_mb": ..., "file_count": ...}
        }
    """
    stats: dict[str, dict] = {}
    total_size = 0
    total_files = 0
    for name, path in _CACHE_DIRS.items():
        size = get_dir_size(path)
        file_count = 0
        if path.exists():
            for _root, _dirs, files in os.walk(path):
                file_count += len(files)
        stats[name] = {
            "size_bytes": size,
            "size_mb": round(size / (1024 * 1024), 2),
            "file_count": file_count,
            "path": str(path),
        }
        total_size += size
        total_files += file_count
    stats["_total"] = {
        "size_bytes": total_size,
        "size_mb": round(total_size / (1024 * 1024), 2),
        "file_count": total_files,
    }
    # 暴露总缓存根路径（~/.lumio），供设置页标题旁显示
    # 跟随用户 home 自动变化，无需硬编码
    stats["_root"] = str(_APP_DIR)
    return stats


def _is_safe_to_delete(path: Path) -> bool:
    """判断文件是否安全删除（白名单扩展名 + 不在子目录）。"""
    if not path.is_file():
        return False
    if path.suffix.lower() not in _SAFE_EXTS:
        return False
    return True


def clean_inbox_media(
    retain_days: int = DEFAULT_RETAIN_DAYS,
    max_size_mb: int | None = None,
    progress_cb: Callable[[int, int], None] | None = None,
    force: bool = False,
) -> dict:
    """智能清理 inbox_media/ 目录。

    策略：
    - 收集所有 InboxItem.direct_url 指向 inbox_media/ 内的本地路径
    - 仅清理 status=downloaded/archived 的 item 对应的文件（用户已下载到输出目录）
    - 保留 status=new/queued/failed 的 item 对应的文件（用户尚未下载）
    - force=True 时清空所有（含未下载的），但会先尝试保留最近 retain_days 天的
    - 同时清理孤儿文件（inbox_media/ 中未被任何 InboxItem 引用的文件）

    Returns:
        {"freed": bytes, "deleted": count, "total": count, "remaining": bytes}
    """
    path = _CACHE_DIRS["inbox_media"]
    if not path.exists():
        return {"freed": 0, "deleted": 0, "total": 0, "remaining": 0}

    # 收集所有 inbox_media/ 文件（含子目录 album_*/）
    all_files: list[tuple[Path, float, int]] = []
    for root, _dirs, fnames in os.walk(path):
        for fname in fnames:
            fp = Path(root) / fname
            try:
                stat = fp.stat()
                all_files.append((fp, stat.st_mtime, stat.st_size))
            except OSError:
                continue
    total = len(all_files)
    if total == 0:
        return {"freed": 0, "deleted": 0, "total": 0, "remaining": 0}

    # 查询数据库，建立 direct_url → status 映射
    # direct_url 可能是文件路径（单文件）或文件夹路径（相册）
    referenced: dict[str, str] = {}  # path_str → status
    downloadable_statuses = {"downloaded", "archived"}  # 可清理
    try:
        from ..models import InboxItem
        from .database import get_session_factory
        session = get_session_factory()()
        try:
            for item in session.query(InboxItem).all():
                if not item.direct_url:
                    continue
                # 只关注指向 inbox_media/ 的本地路径
                if "inbox_media" not in item.direct_url:
                    continue
                referenced[item.direct_url] = item.status or "new"
        finally:
            session.close()
    except Exception as e:
        logger.warning("查询 InboxItem 失败，仅清理孤儿文件: %s", e)
        # 失败时只清理明显是孤儿文件的（按时间策略）
        referenced = {}

    freed = 0
    deleted = 0
    cutoff_ts = time.time() - retain_days * 86400

    # 构建已下载完成的文件路径集合（用于快速判断）
    downloaded_paths = set()
    for p, status in referenced.items():
        if status in downloadable_statuses:
            downloaded_paths.add(p)

    for fp, mtime, size in all_files:
        should_delete = False
        # 检查此文件是否被某个 InboxItem 引用
        str_fp = str(fp)
        # 单文件场景：direct_url 直接等于文件路径
        if str_fp in referenced:
            status = referenced[str_fp]
            if force:
                should_delete = True
            elif status in downloadable_statuses:
                # 已下载完成：按保留期清理
                should_delete = mtime < cutoff_ts
            # new/queued/failed：保留
        else:
            # 检查是否属于某个相册文件夹（direct_url 指向父目录）
            parent = fp.parent
            parent_str = str(parent)
            if parent_str in referenced:
                status = referenced[parent_str]
                if force:
                    should_delete = True
                elif status in downloadable_statuses:
                    should_delete = mtime < cutoff_ts
            else:
                # 孤儿文件：未被任何 InboxItem 引用
                # 按 retain_days 清理（force=True 时立即清理）
                should_delete = force or mtime < cutoff_ts

        if should_delete:
            try:
                fp.unlink()
                freed += size
                deleted += 1
                if progress_cb:
                    progress_cb(deleted, total)
            except OSError as e:
                logger.warning("删除 inbox_media 文件失败 %s: %s", fp, e)

    # 阶段 2：如果仍超上限，按 mtime 从旧到新删除已下载完成的文件
    if max_size_mb is not None and not force:
        max_bytes = max_size_mb * 1024 * 1024
        current_size = 0
        remaining_files: list[tuple[Path, float, int]] = []
        for root, _dirs, fnames in os.walk(path):
            for fname in fnames:
                fp = Path(root) / fname
                try:
                    stat = fp.stat()
                    remaining_files.append((fp, stat.st_mtime, stat.st_size))
                    current_size += stat.st_size
                except OSError:
                    continue
        # 按 mtime 升序（最旧优先删）
        remaining_files.sort(key=lambda x: x[1])
        for fp, _mtime, size in remaining_files:
            if current_size <= max_bytes:
                break
            str_fp = str(fp)
            parent_str = str(fp.parent)
            # 仅清理已下载完成的文件，不清理未下载的
            if str_fp in downloaded_paths or parent_str in downloaded_paths:
                try:
                    fp.unlink()
                    freed += size
                    current_size -= size
                    deleted += 1
                    if progress_cb:
                        progress_cb(deleted, total)
                except OSError as e:
                    logger.warning("删除 inbox_media 文件失败 %s: %s", fp, e)

    # 清理空的 album_*/ 子目录
    for child in path.iterdir():
        if child.is_dir() and not any(child.iterdir()):
            try:
                child.rmdir()
            except OSError:
                pass

    # 统计剩余
    remaining_size = 0
    for root, _dirs, fnames in os.walk(path):
        for fname in fnames:
            fp = Path(root) / fname
            try:
                remaining_size += fp.stat().st_size
            except OSError:
                continue

    logger.info("清理 inbox_media: 删除 %d/%d 文件，释放 %.2f MB，剩余 %.2f MB",
                deleted, total, freed / 1024 / 1024, remaining_size / 1024 / 1024)
    return {"freed": freed, "deleted": deleted, "total": total, "remaining": remaining_size}


def clean_cache_dir(
    name: str,
    retain_days: int = DEFAULT_RETAIN_DAYS,
    max_size_mb: int | None = None,
    progress_cb: Callable[[int, int], None] | None = None,
    force: bool = False,
) -> dict:
    """清理单个缓存目录。

    Args:
        name: 缓存目录名（thumbs/provider_cache/preview/inbox_media）
        retain_days: 保留最近 N 天的文件（force=True 时忽略）
        max_size_mb: 目录上限（MB），超过则按 mtime 从旧到新删除（force=True 时忽略）
        progress_cb: 进度回调 (deleted_count, total_count)
        force: 强制清空所有白名单文件（忽略保留期和上限）
    Returns:
        {"freed": bytes, "deleted": count, "total": count, "remaining": bytes}

    注意：inbox_media 走智能清理策略（clean_inbox_media），只删已下载完成的文件，
    保留 new/queued/failed 状态的文件；force=True 时才清空所有。
    """
    path = _CACHE_DIRS.get(name)
    if path is None or not path.exists():
        return {"freed": 0, "deleted": 0, "total": 0, "remaining": 0}

    # inbox_media 走智能清理路径
    if name == "inbox_media":
        return clean_inbox_media(retain_days=retain_days, max_size_mb=max_size_mb,
                                  progress_cb=progress_cb, force=force)

    files: list[tuple[Path, float, int]] = []
    for root, _dirs, fnames in os.walk(path):
        for fname in fnames:
            fp = Path(root) / fname
            if not _is_safe_to_delete(fp):
                continue
            try:
                stat = fp.stat()
                files.append((fp, stat.st_mtime, stat.st_size))
            except OSError:
                continue

    total = len(files)
    if total == 0:
        return {"freed": 0, "deleted": 0, "total": 0, "remaining": 0}

    freed = 0
    deleted = 0

    if force:
        # 强制清空所有白名单文件
        for fp, _mtime, size in files:
            try:
                fp.unlink()
                freed += size
                deleted += 1
                if progress_cb:
                    progress_cb(deleted, total)
            except OSError as e:
                logger.warning("删除缓存文件失败 %s: %s", fp, e)
    else:
        cutoff_ts = time.time() - retain_days * 86400
        # 阶段 1：删除超过保留期的文件
        for fp, mtime, size in files:
            if mtime < cutoff_ts:
                try:
                    fp.unlink()
                    freed += size
                    deleted += 1
                    if progress_cb:
                        progress_cb(deleted, total)
                except OSError as e:
                    logger.warning("删除缓存文件失败 %s: %s", fp, e)

        # 阶段 2：如果仍超上限，按 mtime 从旧到新删除
        if max_size_mb is not None:
            max_bytes = max_size_mb * 1024 * 1024
            # 重新统计剩余文件
            remaining: list[tuple[Path, float, int]] = []
            current_size = 0
            for root, _dirs, fnames in os.walk(path):
                for fname in fnames:
                    fp = Path(root) / fname
                    if not _is_safe_to_delete(fp):
                        continue
                    try:
                        stat = fp.stat()
                        remaining.append((fp, stat.st_mtime, stat.st_size))
                        current_size += stat.st_size
                    except OSError:
                        continue
            # 按 mtime 升序（最旧优先删）
            remaining.sort(key=lambda x: x[1])
            for fp, _mtime, size in remaining:
                if current_size <= max_bytes:
                    break
                try:
                    fp.unlink()
                    freed += size
                    current_size -= size
                    deleted += 1
                    if progress_cb:
                        progress_cb(deleted, total)
                except OSError as e:
                    logger.warning("删除缓存文件失败 %s: %s", fp, e)

    # 统计剩余
    remaining_size = 0
    for root, _dirs, fnames in os.walk(path):
        for fname in fnames:
            fp = Path(root) / fname
            try:
                remaining_size += fp.stat().st_size
            except OSError:
                continue

    logger.info("清理缓存目录 %s: 删除 %d/%d 文件，释放 %.2f MB，剩余 %.2f MB",
                name, deleted, total, freed / 1024 / 1024, remaining_size / 1024 / 1024)
    return {"freed": freed, "deleted": deleted, "total": total, "remaining": remaining_size}


def clean_all_caches(
    retain_days: int = DEFAULT_RETAIN_DAYS,
    max_size_mb: int = DEFAULT_MAX_SIZE_MB,
    progress_cb: Callable[[str, int, int], None] | None = None,
    force: bool = False,
) -> dict[str, dict]:
    """清理所有缓存目录。

    Args:
        retain_days: 保留期（force=True 时忽略）
        max_size_mb: 单目录上限（force=True 时忽略）
        progress_cb: 进度回调 (dir_name, deleted, total)
        force: 强制清空所有白名单文件
    Returns:
        {dir_name: {"freed": bytes, "deleted": count, "total": count, "remaining": bytes}}
    """
    results: dict[str, dict] = {}
    for name in _CACHE_DIRS:
        def _cb(deleted: int, total: int, _name=name) -> None:
            if progress_cb:
                progress_cb(_name, deleted, total)
        results[name] = clean_cache_dir(name, retain_days, max_size_mb, _cb, force=force)
    return results


def should_auto_clean() -> bool:
    """根据配置判断是否应该触发自动清理。"""
    cfg = load_config()
    cm = cfg.get("cache_management", {})
    mode = cm.get("auto_clean", "off")
    if mode == "off":
        return False
    if mode == "startup":
        return True

    last_str = cm.get("last_cleaned", "")
    if not last_str:
        return True
    try:
        last = datetime.fromisoformat(last_str)
    except ValueError:
        return True

    now = datetime.now()
    if mode == "daily":
        return now - last >= timedelta(days=1)
    if mode == "weekly":
        return now - last >= timedelta(days=7)
    return False


def run_auto_clean_if_needed() -> bool:
    """启动时调用：若配置允许，后台执行一次自动清理。

    Returns:
        True 表示执行了清理
    """
    if not should_auto_clean():
        return False

    cfg = load_config()
    cm = cfg.get("cache_management", {})
    retain_days = cm.get("retain_days", DEFAULT_RETAIN_DAYS)
    max_size_mb = cm.get("max_size_mb", DEFAULT_MAX_SIZE_MB)

    logger.info("触发自动缓存清理 (mode=%s, retain_days=%d, max_size_mb=%d)",
                cm.get("auto_clean"), retain_days, max_size_mb)

    try:
        clean_all_caches(retain_days=retain_days, max_size_mb=max_size_mb)
        # 更新 last_cleaned
        cm["last_cleaned"] = datetime.now().isoformat()
        cfg["cache_management"] = cm
        save_config(cfg)
        return True
    except Exception as e:
        logger.warning("自动清理缓存失败: %s", e)
        return False


def clean_cache_by_rules(progress_cb: Callable[[str, int, int], None] | None = None) -> dict:
    """按配置规则清理所有缓存目录（供 QML bridge 调用）。

    读取 config.cache_management 中的 retain_days 和 max_size_mb，
    执行 clean_all_caches，并更新 last_cleaned 时间戳。

    Returns:
        各目录清理结果 {dir_name: {freed, deleted, total, remaining}}
    """
    cfg = load_config()
    cm = cfg.get("cache_management", {})
    retain_days = cm.get("retain_days", DEFAULT_RETAIN_DAYS)
    max_size_mb = cm.get("max_size_mb", DEFAULT_MAX_SIZE_MB)

    logger.info("按规则清理缓存 (retain_days=%d, max_size_mb=%d)",
                retain_days, max_size_mb)

    results = clean_all_caches(
        retain_days=retain_days,
        max_size_mb=max_size_mb,
        progress_cb=progress_cb,
        force=False,
    )

    # 更新 last_cleaned
    cm["last_cleaned"] = datetime.now().isoformat()
    cfg["cache_management"] = cm
    save_config(cfg)

    return results


def force_clear_cache(progress_cb: Callable[[str, int, int], None] | None = None) -> dict:
    """强制清空所有缓存目录（供 QML bridge 调用）。

    忽略保留期和上限，清空所有白名单文件。
    inbox_media 也强制清空（含未下载的文件）。

    Returns:
        各目录清理结果 {dir_name: {freed, deleted, total, remaining}}
    """
    logger.info("强制清空所有缓存目录")

    results = clean_all_caches(
        retain_days=DEFAULT_RETAIN_DAYS,
        max_size_mb=DEFAULT_MAX_SIZE_MB,
        progress_cb=progress_cb,
        force=True,
    )

    # 更新 last_cleaned
    cfg = load_config()
    cm = cfg.get("cache_management", {})
    cm["last_cleaned"] = datetime.now().isoformat()
    cfg["cache_management"] = cm
    save_config(cfg)

    return results


def get_preview_cache_path(url: str, ext: str = ".mp4") -> Path:
    """获取预览缓存文件路径（按 URL 的 MD5 命名）。

    供 home_page._preview_x_video 使用。
    """
    import hashlib
    url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:16]
    cache_dir = get_cache_dir("preview")
    return cache_dir / f"{url_hash}{ext}"


def download_to_preview_cache(
    url: str,
    progress_cb: Callable[[int, int], None] | None = None,
    cancel_event=None,
) -> Path | None:
    """下载 URL 到预览缓存。

    供 home_page._preview_x_video 使用。
    用 requests.Session(trust_env=True) 尊重系统代理。

    Returns:
        本地文件路径，失败返回 None
    """
    import requests
    dest = get_preview_cache_path(url)
    if dest.exists() and dest.stat().st_size > 0:
        # 缓存命中
        return dest

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    if "twimg.com" in url or "x.com" in url:
        headers["Referer"] = "https://x.com/"

    session = requests.Session()
    session.trust_env = True
    try:
        resp = session.get(url, stream=True, timeout=30, headers=headers)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(8192):
                if cancel_event and cancel_event.is_set():
                    tmp.unlink(missing_ok=True)
                    return None
                f.write(chunk)
                downloaded += len(chunk)
                if progress_cb and total:
                    progress_cb(downloaded, total)
        tmp.replace(dest)
        # 强制 emit 100% 进度（content-length 与实际 body 大小可能有偏差，
        # 导致最后一次 emit 不是 100%，前端进度条会卡在 99%）
        if progress_cb and total:
            progress_cb(total, total)
        return dest
    except Exception as e:
        logger.warning("下载预览缓存失败 %s: %s", url, e)
        return None
