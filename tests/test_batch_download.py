"""批量下载阶段 3：batch_download 模块 pytest。

覆盖：文件夹清洗、YouTube 清晰度映射、抖音档位收集与挑选、
预览分发（成功/拒绝/失败）、入队分组（同一 batch_id、统一文件夹、
单项 override、图片原图、单项失败隔离）、分组进度汇总。
不依赖 FastAPI 应用上下文与 Qt；listing 与入队均注入 fake。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, "src")

from lumio.batch_download import (  # noqa: E402
    BatchPreviewError,
    batch_summary,
    default_batch_folder_name,
    enqueue_batch,
    preview_batch,
    register_batch,
    sanitize_batch_folder_name,
    youtube_format_for_quality,
)
from lumio.providers.douyin import (  # noqa: E402
    collect_douyin_formats,
    pick_douyin_quality_url,
)
from lumio.providers.youtube import ChannelWork, ChannelWorksPage  # noqa: E402


# ---------------------------------------------------------------------------
# 文件夹清洗（与前端 sanitizeFolderName 同规则）
# ---------------------------------------------------------------------------


def test_sanitize_removes_illegal_chars():
    assert sanitize_batch_folder_name('a/b\\c:d*e?f"g<h>i|j') == "abcdefghij"


def test_sanitize_trims_and_strips_trailing_dots():
    assert sanitize_batch_folder_name("  作者名-20261025...  ") == "作者名-20261025"


def test_sanitize_empty_and_dot_only():
    assert sanitize_batch_folder_name("") == ""
    assert sanitize_batch_folder_name("..") == ""
    assert sanitize_batch_folder_name("...") == ""


def test_sanitize_never_contains_separator():
    # 目录穿越输入清洗后仍为单个路径组件
    cleaned = sanitize_batch_folder_name("a/../../etc")
    assert "/" not in cleaned and "\\" not in cleaned
    assert cleaned == "a....etc"


def test_default_folder_name():
    name = default_batch_folder_name("杨超越")
    assert name.startswith("杨超越-") and len(name) == len("杨超越-") + 8
    assert default_batch_folder_name("") .startswith("批量下载-")


# ---------------------------------------------------------------------------
# YouTube 清晰度映射
# ---------------------------------------------------------------------------


def test_youtube_format_original_is_best():
    assert youtube_format_for_quality("original") == ("best", "video")


def test_youtube_format_height_cap():
    fmt, ftype = youtube_format_for_quality("1080p")
    assert "height<=1080" in fmt and ftype == ""
    fmt720, _ = youtube_format_for_quality("720p")
    assert "height<=720" in fmt720


def test_youtube_format_invalid():
    with pytest.raises(ValueError):
        youtube_format_for_quality("4k")


# ---------------------------------------------------------------------------
# 抖音档位收集与挑选
# ---------------------------------------------------------------------------

_FAKE_VIDEO_INFO = {
    "bit_rate": [
        {"gear_name": "normal_1080_0", "bit_rate": 3000000,
         "play_addr": {"url_list": ["https://cdn/1080-high"], "width": 1080, "height": 1920, "data_size": 100}},
        {"gear_name": "normal_1080_0", "bit_rate": 2000000,
         "play_addr": {"url_list": ["https://cdn/1080-low"], "width": 1080, "height": 1920, "data_size": 80}},
        {"gear_name": "normal_720_0", "bit_rate": 1500000,
         "play_addr": {"url_list": ["https://cdn/720"], "width": 720, "height": 1280, "data_size": 60}},
        {"gear_name": "normal_540_0", "bit_rate": 800000,
         "play_addr": {"url_list": ["https://cdn/540"], "width": 540, "height": 960, "data_size": 40}},
        {"gear_name": "weird_no_res", "bit_rate": 100,
         "play_addr": {"url_list": ["https://cdn/weird"], "width": 0, "height": 0, "data_size": 1}},
        {"gear_name": "normal_720_0", "bit_rate": 900000,
         "play_addr": {"url_list": [], "width": 720, "height": 1280, "data_size": 0}},
    ]
}


def test_collect_douyin_formats_dedup_by_bitrate():
    formats = collect_douyin_formats(_FAKE_VIDEO_INFO)
    assert set(formats) == {"1080p", "720p", "540p"}
    # 同分辨率保留码率最高的那条
    assert formats["1080p"]["url"] == "https://cdn/1080-high"
    assert formats["720p"]["url"] == "https://cdn/720"


def test_pick_douyin_quality_exact_and_fallback():
    formats = collect_douyin_formats(_FAKE_VIDEO_INFO)
    assert pick_douyin_quality_url(formats, "original") is None
    assert pick_douyin_quality_url(formats, "1080p") == "https://cdn/1080-high"
    # 480p 无精确档：回落到不高于目标的最高档——540 高于 480，故取最低档 540p
    assert pick_douyin_quality_url(formats, "480p") == "https://cdn/540"
    # 720p 精确
    assert pick_douyin_quality_url(formats, "720p") == "https://cdn/720"
    assert pick_douyin_quality_url({}, "720p") is None


# ---------------------------------------------------------------------------
# 预览分发
# ---------------------------------------------------------------------------


def _yt_page():
    return ChannelWorksPage(
        works=[
            ChannelWork(video_id="vid1", url="https://www.youtube.com/watch?v=vid1",
                        title="视频一", thumbnail="https://th/1.jpg", duration=168,
                        upload_date="20250101"),
            ChannelWork(video_id="vid2", url="https://www.youtube.com/watch?v=vid2",
                        title="视频二", thumbnail="", duration=None),
        ],
        has_more=True, page=1, page_size=30, author="CHUANG ASIA",
    )


def test_preview_youtube_success():
    res = preview_batch("https://www.youtube.com/@CHUANGASIA",
                        youtube_lister=lambda url, limit, page: _yt_page())
    assert res["platform"] == "youtube"
    assert res["author"] == "CHUANG ASIA"
    assert res["has_more"] is True
    assert len(res["works"]) == 2
    w = res["works"][0]
    assert w["url"] == "https://www.youtube.com/watch?v=vid1"
    assert w["type"] == "video" and w["duration_seconds"] == 168
    assert w["post_time"] == "20250101"


def test_preview_youtube_failure_is_not_silent_empty():
    def boom(url, limit, page):
        raise RuntimeError("Sign in to confirm you're not a bot")

    with pytest.raises(BatchPreviewError) as ei:
        preview_batch("https://www.youtube.com/@CHUANGASIA", youtube_lister=boom)
    assert ei.value.code == "preview_failed"


def test_preview_douyin_success_maps_types():
    def enumerator(identifier, limit):
        assert limit == 31  # page1 limit30 + 1 探针
        return [
            {"url": "https://www.douyin.com/video/111", "title": "视频",
             "thumbnail": "https://th/v.jpg", "media_type": "video",
             "duration": 15, "post_time": "20261001", "author": "杨超越"},
            {"url": "https://www.douyin.com/note/222", "title": "图文",
             "thumbnail": "https://th/n.jpg", "media_type": "image",
             "image_count": 9, "post_time": "20261002", "author": "杨超越"},
        ]

    res = preview_batch("https://www.douyin.com/user/MS4wLjABAAAAxxx",
                        douyin_enumerator=enumerator)
    assert res["platform"] == "douyin"
    assert res["author"] == "杨超越"
    assert res["works"][0]["type"] == "video"
    assert res["works"][0]["duration_seconds"] == 15
    assert res["works"][1]["type"] == "image"
    assert res["works"][1]["image_count"] == 9


def test_preview_douyin_failure_is_not_silent_empty():
    def boom(identifier, limit):
        raise RuntimeError("列表接口返回空体（可能需要登录态）")

    with pytest.raises(BatchPreviewError) as ei:
        preview_batch("https://www.douyin.com/user/MS4wLjABAAAAxxx",
                      douyin_enumerator=boom)
    assert ei.value.code == "preview_failed"


def test_preview_rejects_non_homepage():
    for url in ("https://www.youtube.com/watch?v=abc123",
                "https://www.douyin.com/video/123456",
                "https://www.instagram.com/p/ABC/",
                "not a url"):
        with pytest.raises(BatchPreviewError) as ei:
            preview_batch(url)
        assert ei.value.code == "profile_not_supported"


# ---------------------------------------------------------------------------
# 入队分组
# ---------------------------------------------------------------------------


class _FakeManager:
    def __init__(self):
        self.calls = []

    def add_task(self, info, format_id, format_type, custom_name, output_dir, batch_id):
        self.calls.append({
            "info": info, "format_id": format_id, "format_type": format_type,
            "custom_name": custom_name, "output_dir": output_dir,
            "batch_id": batch_id,
        })
        return f"task-{len(self.calls)}"


def _no_extract(url):
    raise AssertionError("unexpected extract")


def _run_enqueue(tmp_path, works, **kw):
    mgr = _FakeManager()
    kw.setdefault("global_quality", "original")
    kw.setdefault("per_item_quality", {})
    kw.setdefault("author", "CHUANG ASIA")
    result = enqueue_batch(
        works, kw.pop("folder_name", "CHUANG ASIA-20261025"),
        kw.pop("global_quality"), kw.pop("per_item_quality"),
        kw.pop("author"),
        extract_info_fn=kw.pop("extract_info_fn", None) or _no_extract,
        douyin_quality_fn=kw.pop("douyin_quality_fn", lambda url, q: None),
        add_task_fn=mgr.add_task,
        download_dir=str(tmp_path),
    )
    return mgr, result


def test_enqueue_youtube_grouping_and_folder_cleaning(tmp_path):
    works = [
        {"url": "https://www.youtube.com/watch?v=vid1", "title": "视频一",
         "thumbnail": "https://th/1.jpg"},
        {"url": "https://www.youtube.com/watch?v=vid2", "title": "视频二"},
    ]
    mgr, res = _run_enqueue(tmp_path, works, folder_name="CHUANG/ASIA:精选*")
    assert res["folder_name"] == "CHUANGASIA精选"
    assert res["output_dir"] == str(tmp_path / "CHUANGASIA精选")
    assert Path(res["output_dir"]).is_dir()
    assert res["task_ids"] == ["task-1", "task-2"]
    assert res["failed"] == []
    assert len({c["batch_id"] for c in mgr.calls}) == 1
    assert all(c["output_dir"] == res["output_dir"] for c in mgr.calls)
    assert all(c["format_id"] == "best" for c in mgr.calls)  # original
    assert mgr.calls[0]["custom_name"] == "视频一"


def test_enqueue_per_item_quality_overrides_global(tmp_path):
    works = [
        {"url": "https://www.youtube.com/watch?v=vid1", "title": "视频一"},
        {"url": "https://www.youtube.com/watch?v=vid2", "title": "视频二"},
    ]
    mgr, _ = _run_enqueue(
        tmp_path, works, global_quality="720p",
        per_item_quality={"https://www.youtube.com/watch?v=vid2": "1080p"})
    assert "height<=720" in mgr.calls[0]["format_id"]
    assert "height<=1080" in mgr.calls[1]["format_id"]


def test_enqueue_invalid_quality_rejected(tmp_path):
    with pytest.raises(ValueError):
        _run_enqueue(tmp_path, [{"url": "https://www.youtube.com/watch?v=v", "title": "t"}],
                     global_quality="4k")


def test_enqueue_existing_folder_is_reused_not_cleared(tmp_path):
    folder = tmp_path / "已有文件夹"
    folder.mkdir()
    (folder / "keep.txt").write_text("keep")
    mgr, res = _run_enqueue(
        tmp_path, [{"url": "https://www.youtube.com/watch?v=v", "title": "t"}],
        folder_name="已有文件夹")
    assert (folder / "keep.txt").read_text() == "keep"
    assert res["output_dir"] == str(folder)


def test_enqueue_item_failure_isolated(tmp_path):
    from lumio.providers.base import MediaInfo, MediaItem, Platform

    def extract(url):
        if "100001" in url:
            raise RuntimeError("boom")
        return MediaInfo(platform=Platform.DOUYIN, url=url, title="好视频",
                         author="杨超越",
                         media_items=[MediaItem(url="https://cdn/best", is_video=True, index=0)])

    works = [
        {"url": "https://www.douyin.com/video/100001", "title": "坏"},
        {"url": "https://www.douyin.com/video/100002", "title": "好"},
    ]
    mgr, res = _run_enqueue(tmp_path, works, extract_info_fn=extract)
    assert len(res["task_ids"]) == 1
    assert len(res["failed"]) == 1
    assert res["failed"][0]["url"] == "https://www.douyin.com/video/100001"
    assert mgr.calls[0]["batch_id"] == res["batch_id"]


def test_enqueue_douyin_quality_replaces_video_url_not_cover(tmp_path):
    from lumio.providers.base import MediaInfo, MediaItem, Platform

    def extract(url):
        return MediaInfo(
            platform=Platform.DOUYIN, url=url, title="视频", author="杨超越",
            media_items=[
                MediaItem(url="https://cdn/best", is_video=True, index=0),
                MediaItem(url="https://cdn/cover.jpg", is_video=False, index=1),
            ])

    quality_calls = []

    def resolve(url, q):
        quality_calls.append((url, q))
        return "https://cdn/720p"

    works = [{"url": "https://www.douyin.com/video/123", "title": "视频"}]
    mgr, _ = _run_enqueue(tmp_path, works, global_quality="720p",
                          extract_info_fn=extract, douyin_quality_fn=resolve)
    assert quality_calls == [("https://www.douyin.com/video/123", "720p")]
    info = mgr.calls[0]["info"]
    assert info.media_items[0].url == "https://cdn/720p"
    assert info.media_items[1].url == "https://cdn/cover.jpg"  # 封面不动


def test_enqueue_douyin_image_ignores_quality(tmp_path):
    from lumio.providers.base import MediaInfo, MediaItem, Platform

    def extract(url):
        return MediaInfo(
            platform=Platform.DOUYIN, url=url, title="图文", author="杨超越",
            media_items=[MediaItem(url="https://cdn/img1.jpg", is_video=False, index=0),
                         MediaItem(url="https://cdn/img2.jpg", is_video=False, index=1)])

    calls = []

    def resolve(url, q):
        calls.append(url)
        return "https://cdn/720p"

    works = [{"url": "https://www.douyin.com/note/123", "title": "图文"}]
    mgr, _ = _run_enqueue(tmp_path, works, global_quality="720p",
                          extract_info_fn=extract, douyin_quality_fn=resolve)
    assert calls == []  # 图片一律原图，不调档位解析
    assert mgr.calls[0]["format_type"] == "image"


# ---------------------------------------------------------------------------
# 分组进度汇总
# ---------------------------------------------------------------------------


def test_batch_summary_counts_queue_plus_history():
    # 5 个作品：1 入队失败 + 1 下载中 + 1 队列失败 + 2 已完成（进历史）
    register_batch("b1", "作者-20261025", 5,
                   [{"url": "u0", "title": "入队失败", "error": "解析失败"}])
    queue = [
        {"task_id": "t1", "title": "进行中", "status": "downloading", "error": ""},
        {"task_id": "t2", "title": "失败项", "status": "failed", "error": "网络错误"},
    ]
    history = [object(), object()]  # 2 个已完成（已从队列移除）
    s = batch_summary("b1", queue, history)
    assert s is not None
    assert s["total"] == 5
    assert s["done"] == 2
    assert s["failed_count"] == 2  # 队列失败 1 + 入队失败 1
    assert s["downloading"] == 1
    assert s["status"] == "active"  # 已定局 4 < 5，仍有 1 项下载中

    # 全部定局：2 历史 + 1 队列失败 + 1 入队失败 + 1 取消 = 5
    queue2 = [
        {"task_id": "t2", "title": "失败项", "status": "failed", "error": "网络错误"},
        {"task_id": "t3", "title": "取消项", "status": "cancelled", "error": ""},
    ]
    s2 = batch_summary("b1", queue2, history)
    assert s2["status"] == "done"
    assert s2["cancelled"] == 1


def test_batch_summary_active_and_unknown():
    register_batch("b2", "作者-20261025", 2, [])
    s = batch_summary("b2", [{"task_id": "t1", "title": "等", "status": "waiting", "error": ""}], [])
    assert s["status"] == "active" and s["waiting"] == 1
    assert batch_summary("no-such-batch", [], []) is None


def test_batch_summary_deleted_item_counts_as_removed():
    # 3 个作品：1 已完成（历史）+ 1 失败项被用户从队列删除 → removed=2，批次仍可 done
    register_batch("b3", "作者-20261025", 3, [])
    s = batch_summary("b3", [], [object()])
    assert s["done"] == 1 and s["removed"] == 2 and s["status"] == "done"
