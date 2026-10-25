"""批量下载重构阶段 3：主页预览 + 批量入队 + 分组进度（后端核心逻辑）。

api_fastapi.py 的 /api/batch/* 端点是薄封装，真实逻辑在这里，
便于 pytest 直接覆盖（不依赖 FastAPI 应用上下文与 Qt）。

设计要点：
- 预览复用阶段 1 的 listing：YouTube list_channel_works、抖音 enumerate_profile_posts。
  不支持的平台/链接类型抛 BatchPreviewError（code=profile_not_supported），
  绝不返回静默空列表；listing 本身失败则 code=preview_failed。
- 入队沿用现有单帖任务创建路径（manager.add_task_from_info）：
  每个作品一个任务、统一输出文件夹、同一 batch_id 分组。
  YouTube 不做逐条 extract_info（下载时 yt-dlp 本来就要重新提取），
  只按清晰度给 format 选择器；抖音沿用 extract_info 拿 CDN 直链，
  档位选择通过 DouyinProvider.resolve_quality_url 替换视频项 URL。
- 输出文件夹：前端已用 sanitizeFolderName 清洗过一次，后端再清洗一次
  （与前端同规则，见 sanitize_batch_folder_name），已存在则直接复用、
  绝不清空；单文件冲突走全局 file_conflict_policy（默认 rename）。
- 队列里已完成任务 1.5 秒后自动移除，所以分组进度不能只看队列：
  batch_summary() 用「队列任务 + 历史记录（batch_id 相同）」拼出 x/N，
  入队时即失败的作品记在 registry 里，同样计入失败名单。
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# 弹窗档位（与 BatchDownloadModal.tsx 的 BATCH_VIDEO_QUALITIES 对齐）
BATCH_QUALITIES = ("original", "1080p", "720p", "480p")

# 错误码：前端靠 detail 前缀识别（api.ts 的 throwHttpError 只透传 detail，
# HomePage 用 "profile_not_supported" 前缀判断是否回落到单帖解析）。
CODE_NOT_SUPPORTED = "profile_not_supported"
CODE_PREVIEW_FAILED = "preview_failed"


class BatchPreviewError(Exception):
    """批量预览失败：code 区分“不是批量链接”和“listing 拉取失败”。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# 文件夹名清洗（与前端 BatchDownloadModal.tsx 的 sanitizeFolderName 同规则）
# ---------------------------------------------------------------------------

_ILLEGAL_FOLDER_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def sanitize_batch_folder_name(raw: str) -> str:
    """清洗文件夹名：去掉各系统都不允许的字符及首尾空白与尾点。

    清洗后不含任何路径分隔符，因此结果恒为单个路径组件，不存在
    目录穿越；清洗后为空（或只剩 "."）时返回 ""，调用方用默认名兜底。
    """
    cleaned = _ILLEGAL_FOLDER_CHARS.sub("", raw or "")
    cleaned = cleaned.strip().rstrip(". ")
    if cleaned in ("", ".", ".."):
        return ""
    return cleaned


def default_batch_folder_name(author: str) -> str:
    """默认文件夹名：作者名-日期；作者名为空时回落到“批量下载-日期”。"""
    today = datetime.now().strftime("%Y%m%d")
    base = (author or "").strip() or "批量下载"
    return sanitize_batch_folder_name(f"{base}-{today}") or f"批量下载-{today}"


# ---------------------------------------------------------------------------
# 清晰度映射
# ---------------------------------------------------------------------------


def youtube_format_for_quality(quality: str) -> tuple[str, str]:
    """批量清晰度 → (format_id, format_type)，供 yt-dlp 路径使用。

    original → "best"，走 downloader 默认 bestvideo+bestaudio 分支
    （与收件箱入队固定 "best" 的做法一致，避免取到纯音频流）。
    具体档位 → 完整 format 选择器，format_type 传 "" 使 downloader
    原样使用选择器（format_type="video" 会被追加 "+bestaudio" 破坏选择器）；
    选择器末尾的 /best 兜底保证无此档位时回落到最高画质而非直接失败。
    """
    if quality == "original":
        return "best", "video"
    m = re.fullmatch(r"(\d+)p", quality or "")
    if not m:
        raise ValueError(f"不支持的清晰度：{quality}")
    h = m.group(1)
    return (
        f"bestvideo[height<={h}]+bestaudio/bestvideo+bestaudio/best",
        "",
    )


# ---------------------------------------------------------------------------
# 预览：复用阶段 1 listing
# ---------------------------------------------------------------------------


def preview_batch(
    url: str,
    limit: int = 30,
    page: int = 1,
    youtube_lister: Optional[Callable] = None,
    douyin_enumerator: Optional[Callable] = None,
) -> dict:
    """拉取主页/频道的一页作品列表。

    返回 {platform, author, works[], has_more, page, page_size}，
    works 每项符合 BatchDownloadModal 的 BatchWork 契约。
    youtube_lister / douyin_enumerator 供测试注入，默认走真实 provider。
    """
    url = (url or "").strip()
    if not url:
        raise BatchPreviewError(CODE_NOT_SUPPORTED, "链接为空")
    limit = max(1, min(int(limit or 30), 100))
    page = max(1, int(page or 1))

    # —— YouTube 频道/主页 ——
    from .providers.youtube import is_channel_url

    if is_channel_url(url):
        if youtube_lister is None:
            from .providers.youtube import list_channel_works

            youtube_lister = list_channel_works
        try:
            result = youtube_lister(url, limit=limit, page=page)
        except Exception as e:
            raise BatchPreviewError(
                CODE_PREVIEW_FAILED, f"YouTube 频道列表拉取失败：{e}"
            ) from e
        works = [
            {
                "url": w.url,
                "title": w.title or "",
                "thumbnail": w.thumbnail or "",
                "type": "video",
                "duration_seconds": w.duration,
                "post_time": w.upload_date or "",
            }
            for w in (result.works or [])
        ]
        return {
            "platform": "youtube",
            "author": getattr(result, "author", "") or "",
            "works": works,
            "has_more": bool(result.has_more),
            "page": page,
            "page_size": limit,
        }

    # —— 抖音个人主页 ——
    from .providers.douyin import _PROFILE_RE

    if _PROFILE_RE.search(url):
        if douyin_enumerator is None:
            from .providers.douyin import DouyinProvider

            douyin_enumerator = DouyinProvider().enumerate_profile_posts
        # 翻页：拉到本页末尾再切片（limit+1 探针判断 has_more），
        # 前端 v1 只用第 1 页，浏览器翻页成本由 limit 控制。
        fetch_limit = page * limit + 1
        try:
            items = douyin_enumerator(url, limit=fetch_limit)
        except Exception as e:
            raise BatchPreviewError(
                CODE_PREVIEW_FAILED, f"抖音主页作品列表拉取失败：{e}"
            ) from e
        items = items or []
        page_items = items[(page - 1) * limit: page * limit]
        works = []
        for it in page_items:
            is_video = (it.get("media_type") or "") == "video"
            works.append({
                "url": it.get("url") or "",
                "title": it.get("title") or "",
                "thumbnail": it.get("thumbnail") or "",
                "type": "video" if is_video else "image",
                "duration_seconds": it.get("duration") if is_video else None,
                "image_count": it.get("image_count") if not is_video else None,
                "post_time": it.get("post_time") or "",
            })
        author = ""
        if items:
            author = items[0].get("author") or ""
        return {
            "platform": "douyin",
            "author": author,
            "works": works,
            "has_more": len(items) > page * limit,
            "page": page,
            "page_size": limit,
        }

    raise BatchPreviewError(
        CODE_NOT_SUPPORTED,
        "该链接不是支持的主页/多帖链接（目前支持抖音个人主页与 YouTube 频道）",
    )


# ---------------------------------------------------------------------------
# 入队：每个作品一个任务，统一输出文件夹，同一 batch_id
# ---------------------------------------------------------------------------

_BATCH_REGISTRY: dict[str, dict] = {}


def register_batch(
    batch_id: str,
    folder_name: str,
    total: int,
    failed_enqueue: list[dict],
) -> None:
    """记录一批次的元数据（供 batch_summary 拼 x/N 用，进程内有效）。"""
    _BATCH_REGISTRY[batch_id] = {
        "folder_name": folder_name,
        "total": total,
        "failed_enqueue": list(failed_enqueue),
    }


def list_batch_ids() -> list[str]:
    """所有已知批次 id（registry 进程内有效，供 GET /api/batch 列表用）。"""
    return list(_BATCH_REGISTRY)


def _youtube_video_id(url: str) -> str:
    """从 watch / youtu.be 链接取视频 id（仅作无标题时的文件名兜底）。"""
    from urllib.parse import parse_qs, urlparse

    try:
        parsed = urlparse(url)
        if "youtu.be" in (parsed.netloc or ""):
            return parsed.path.strip("/").split("/")[0]
        return parse_qs(parsed.query).get("v", [""])[0]
    except Exception:
        return ""


def enqueue_batch(
    works: list[dict],
    folder_name: str,
    global_quality: str,
    per_item_quality: dict[str, str],
    author: str = "",
    *,
    extract_info_fn: Callable,
    douyin_quality_fn: Callable,
    add_task_fn: Callable,
    download_dir: str,
) -> dict:
    """批量入队。works: [{url, title?}]；返回
    {batch_id, folder_name, output_dir, task_ids, failed:[{url, title, error}]}。

    单项失败不影响其他项（失败项记入 failed，不建任务）；
    图片一律原图（不调档位解析）；单项清晰度优先于全局。
    """
    if not works:
        raise ValueError("未选择任何作品")
    if global_quality not in BATCH_QUALITIES:
        raise ValueError(f"不支持的全局清晰度：{global_quality}")
    per_item_quality = per_item_quality or {}
    for q in per_item_quality.values():
        if q not in BATCH_QUALITIES:
            raise ValueError(f"不支持的单项清晰度：{q}")

    cleaned = sanitize_batch_folder_name(folder_name or "")
    if not cleaned:
        cleaned = default_batch_folder_name(author)
    out_dir = Path(download_dir) / cleaned
    # 已存在则直接复用、绝不清空（追加不覆盖）；单文件冲突走全局策略
    out_dir.mkdir(parents=True, exist_ok=True)

    batch_id = uuid.uuid4().hex
    task_ids: list[str] = []
    failed: list[dict] = []

    from .providers.base import MediaInfo, Platform
    from .providers.douyin import DouyinProvider
    from .providers.youtube import YouTubeProvider

    yt_provider = YouTubeProvider()
    dy_provider = DouyinProvider()

    for work in works:
        work_url = (work.get("url") or "").strip()
        work_title = work.get("title") or ""
        if not work_url:
            failed.append({"url": "", "title": work_title, "error": "作品链接为空"})
            continue
        try:
            quality = per_item_quality.get(work_url, global_quality)
            if yt_provider.match(work_url):
                # YouTube：下载时 yt-dlp 本来就要重新提取，不逐条 extract；
                # 标题/作者/缩略图来自预览结果，直接进任务元数据。
                format_id, format_type = youtube_format_for_quality(quality)
                info = MediaInfo(
                    platform=Platform.YOUTUBE,
                    url=work_url,
                    title=work_title,
                    author=author,
                    thumbnail=work.get("thumbnail") or "",
                )
                custom_name = work_title or _youtube_video_id(work_url) or ""
                task_id = add_task_fn(
                    info, format_id, format_type, custom_name,
                    str(out_dir), batch_id,
                )
                task_ids.append(task_id)
            elif dy_provider.match(work_url):
                # 抖音：沿用单帖解析拿 CDN 直链（media_items），再按档位替换
                info = extract_info_fn(work_url)
                if not info.media_items:
                    desc = (info.description or "").strip()
                    raise ValueError(desc or (info.title or "解析失败"))
                has_video = any(it.is_video for it in info.media_items)
                if has_video and quality != "original":
                    resolved = douyin_quality_fn(work_url, quality)
                    if resolved:
                        for it in info.media_items:
                            if it.is_video:
                                it.url = resolved
                                break
                # 图片（图文）一律原图：media_items 已是原图直链，不动
                format_type = "video" if has_video else "image"
                task_id = add_task_fn(
                    info, "best", format_type,
                    work_title or info.title or "",
                    str(out_dir), batch_id,
                )
                task_ids.append(task_id)
            else:
                raise ValueError("不支持的作品链接（目前支持抖音与 YouTube）")
        except Exception as e:
            logger.warning("batch enqueue item failed url=%s: %s", work_url, e)
            failed.append({"url": work_url, "title": work_title, "error": str(e)})

    register_batch(batch_id, cleaned, len(works), failed)
    return {
        "batch_id": batch_id,
        "folder_name": cleaned,
        "output_dir": str(out_dir),
        "task_ids": task_ids,
        "failed": failed,
    }


# ---------------------------------------------------------------------------
# 分组进度：队列任务 + 历史记录拼 x/N
# ---------------------------------------------------------------------------

# 终态（计入“已定局”）：完成 / 失败 / 取消。队列任务状态来自 _task_to_dict。
_TERMINAL_FAILED = {"failed", "失败"}
_TERMINAL_CANCELLED = {"cancelled", "已取消"}


def batch_summary(
    batch_id: str,
    queue_tasks: list[dict],
    history_records: list,
) -> Optional[dict]:
    """拼一批次的进度与汇总。

    queue_tasks: _task_to_dict 后的任务 dict（仅本 batch）；
    history_records: HistoryRecord 对象（仅本 batch，已完成任务的归宿）。
    registry 里没有、队列与历史里也没有时返回 None（未知 batch）。
    """
    record = _BATCH_REGISTRY.get(batch_id)
    done = len(history_records)
    failed: list[dict] = []
    cancelled = 0
    waiting = 0
    downloading = 0
    for t in queue_tasks:
        status = (t.get("status") or "").strip()
        if status in ("completed", "done", "已完成"):
            done += 1
        elif status in _TERMINAL_FAILED:
            failed.append({
                "task_id": t.get("task_id") or "",
                "title": t.get("title") or t.get("url") or "",
                "error": t.get("error") or "",
            })
        elif status in _TERMINAL_CANCELLED:
            cancelled += 1
        elif status in ("waiting", "等待"):
            waiting += 1
        else:
            # downloading / parsing / merging / retrying / paused / interrupted
            downloading += 1
    failed_enqueue = list(record["failed_enqueue"]) if record else []
    total = record["total"] if record else (len(queue_tasks) + len(history_records))
    if record is None and not queue_tasks and not history_records:
        return None
    failed_total = failed + [
        {"task_id": "", "title": f.get("title") or f.get("url") or "",
         "error": f.get("error") or ""}
        for f in failed_enqueue
    ]
    # 已删除的任务既不在队列也不在历史里：总数减去各项计数即为 removed；
    # 计入已定局，否则删掉失败项后批次永远到不了 done（组头一直挂着 x/N）。
    # 注意：settled 只含已定局项（不含 waiting/downloading），否则下载中的
    # 批次会被误判为 done。
    accounted = done + len(failed_total) + cancelled + waiting + downloading
    removed = max(0, total - accounted)
    settled = done + len(failed_total) + cancelled + removed
    status = "done" if total > 0 and settled >= total else "active"
    return {
        "batch_id": batch_id,
        "folder_name": record["folder_name"] if record else "",
        "total": total,
        "done": done,
        "failed": failed_total,
        "failed_count": len(failed_total),
        "cancelled": cancelled,
        "waiting": waiting,
        "downloading": downloading,
        "removed": removed,
        "status": status,
    }
