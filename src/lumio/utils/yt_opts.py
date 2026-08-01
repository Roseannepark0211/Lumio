"""yt-dlp 选项构造 + ffmpeg 定位（跨平台共享）。

历史上有 3 份 `_yt_opts` 重复实现（downloader.py / providers/youtube.py / providers/x.py），
各自字段略有差异（proxy / merge_output_format / socket_timeout / 字幕开关 等），
本模块合并为单一来源，所有调用方按需 import。

字段取并集，行为对齐：
- 静默模式：quiet / no_warnings / noprogress / no_color
- 断点续传：continuedl / keep_fragments
- 合并输出：merge_output_format="mp4"（视频+音频合并到 mp4 容器）
- ffmpeg：_find_ffmpeg() 优先系统 PATH，否则用 imageio_ffmpeg 内置二进制
- 网络超时：socket_timeout=15（避免 yt-dlp 在网络异常时挂死）
- 代理：从 config.proxy 读取（yt-dlp 原生支持）
- 元数据/字幕：默认不嵌入、不下载（YouTube 走 extractor 时也无副作用）
- Cookie：调用方传入 cookie_path，存在则启用 cookiefile
"""

from __future__ import annotations

import shutil
from pathlib import Path


def find_ffmpeg() -> str | None:
    """Locate ffmpeg: system PATH first, then imageio-ffmpeg bundle.

    跨平台行为：
    - Windows / macOS / Linux 均先用 shutil.which("ffmpeg") 找系统 PATH
    - 找不到则回退到 imageio_ffmpeg.get_ffmpeg_exe()（内置 Windows 二进制）
    - 都失败返回 None，调用方应处理 None 情况
    """
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def yt_opts(cookie_path: Path | str | None = None) -> dict:
    """构造 yt-dlp 选项字典（统一所有调用方）。

    Args:
        cookie_path: Netscape 格式 cookie 文件路径；None 或不存在则不启用 cookiefile。

    Returns:
        yt-dlp 选项字典，可直接传给 YoutubeDL(opts)。
    """
    from .config import load_config

    ffmpeg_bin = find_ffmpeg() or "ffmpeg"
    cfg = load_config()
    proxy = cfg.get("proxy", "")

    opts: dict = {
        # 静默模式
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "no_color": True,
        # 合并输出（视频+音频合并到 mp4）
        "merge_output_format": "mp4",
        # ffmpeg 位置（系统 PATH 优先，否则用内置二进制）
        "ffmpeg_location": ffmpeg_bin,
        # 断点续传
        "continuedl": True,
        "keep_fragments": True,
        # 网络超时（秒）
        "socket_timeout": 15,
        # 重试次数：默认 10 对 4K 大文件不够（SSL EOF 常见），加到 30
        # YouTube 反爬会主动关闭 SSL 连接，4K 文件下载时间长易触发
        "retries": 30,
        "fragment_retries": 30,
        # 重试退避：指数退避，避免短时间内重复请求触发更严限流
        # yt-dlp 选项 retry_sleep_functions，值为函数：入参 n=第几次重试，返回等待秒数
        # http/fragment 分别对应整体请求和 DASH 分片请求
        # 5s -> 10s -> 20s -> 40s -> 60s（封顶 60s）
        "retry_sleep_functions": {
            "http": lambda n: min(5 * (2 ** (n - 1)), 60),
            "fragment": lambda n: min(5 * (2 ** (n - 1)), 60),
        },
        # 不嵌入元数据 / 不下载字幕（默认行为，YouTube extractor 无副作用）
        "embedmetadata": False,
        "writesubtitles": False,
        "writeautomaticsub": False,
        # 防 YouTube 限流：连续下载多个视频时在请求间添加延迟
        # yt-dlp 推荐 --sleep-requests 避免 "This content isn't available" 错误
        # https://github.com/yt-dlp/yt-dlp/wiki/Extractors#this-content-isnt-available-try-again-later
        "sleep_interval_requests": 1,    # 每次请求间隔至少 1 秒
        "max_sleep_interval_requests": 3, # 最多随机延迟到 3 秒
        "sleep_interval": 0,             # 单视频下载内部不延迟（不影响正常速度）
        "max_sleep_interval": 0,
    }
    if proxy:
        opts["proxy"] = proxy
    if cookie_path:
        cookie_path = Path(cookie_path)
        if cookie_path.exists():
            opts["cookiefile"] = str(cookie_path)
    return opts
