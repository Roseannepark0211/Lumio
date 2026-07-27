"""X-Sou 视频预览缓存下载 worker。

从 qml_bridge._PreviewCacheWorker 迁移而来，去除 QThread 依赖，
改用 threading.Thread + threading.Event。

api_fastapi.py 的 /api/preview-x-video 端点用此模块在后台线程下载
video.twimg.com 直链到 cache/preview/，通过 progress_cb 回调推送
WS preview_progress / preview_ready / preview_failed 事件。
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional

from .cache_manager import download_to_preview_cache, get_preview_cache_path


class PreviewWorker:
    """后台线程下载 X-Sou 视频到 preview 缓存。

    用 requests.Session(trust_env=True) 走系统代理（在 cache_manager 内部完成），
    避开 QMediaPlayer 无法使用代理的限制。

    用法：
        worker = PreviewWorker(url,
            on_progress=lambda d, t: ...,
            on_finished=lambda path: ...,
            on_failed=lambda err: ...)
        worker.start()           # 非阻塞
        worker.cancel()          # 取消（幂等）
        worker.wait()            # 阻塞等待结束（可选）
    """

    def __init__(
        self,
        url: str,
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_finished: Optional[Callable[[str], None]] = None,
        on_failed: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._url = url
        self._on_progress = on_progress
        self._on_finished = on_finished
        self._on_failed = on_failed
        self._cancel = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # —— cancel_event 协议（cache_manager 调用 is_set() 检查取消）——
    def cancel(self) -> None:
        self._cancel.set()

    def is_set(self) -> bool:
        return self._cancel.is_set()

    # —— 线程控制 ——
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run, name=f"PreviewWorker({self._url[:48]})", daemon=True
        )
        self._thread.start()

    def wait(self, timeout: Optional[float] = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        try:
            cached = get_preview_cache_path(self._url)
            if cached.exists() and cached.stat().st_size > 0:
                if self._on_finished:
                    self._on_finished(str(cached))
                return
            result = download_to_preview_cache(
                self._url,
                progress_cb=self._on_progress,
                cancel_event=self,
            )
            if result is None:
                if self._cancel.is_set():
                    if self._on_failed:
                        self._on_failed("cancelled")
                else:
                    if self._on_failed:
                        self._on_failed("download failed")
            else:
                if self._on_finished:
                    self._on_finished(str(result))
        except Exception as e:
            import traceback
            traceback.print_exc()
            if self._on_failed:
                self._on_failed(str(e))
