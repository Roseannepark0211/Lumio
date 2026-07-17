"""重试处理器 — 指数退避 + 抖动。

所有网络请求统一通过 RetryHandler 重试。
"""

from __future__ import annotations

import random
import time
from typing import Optional


class RetryHandler:
    """指数退避重试处理器。

    用法:
        rh = RetryHandler(max_retries=3, base_delay=5.0)
        for attempt in rh:
            try:
                resp = client.get(url)
                rh.on_success()
                break
            except Exception as e:
                rh.on_error(e)
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 5.0,
        max_delay: float = 60.0,
        jitter: float = 0.5,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self.attempt = 0
        self.last_error: Optional[Exception] = None

    def __iter__(self) -> "RetryHandler":
        self.attempt = 0
        return self

    def __next__(self) -> int:
        if self.attempt >= self.max_retries:
            raise StopIteration
        if self.attempt > 0:
            delay = min(self.base_delay * (2 ** (self.attempt - 1)), self.max_delay)
            jitter_amount = random.uniform(-self.jitter * delay, self.jitter * delay)
            time.sleep(delay + jitter_amount)
        self.attempt += 1
        return self.attempt

    def on_success(self) -> None:
        self.attempt = self.max_retries

    def on_error(self, error: Exception) -> bool:
        self.last_error = error
        return self.attempt < self.max_retries

    def reset(self) -> None:
        self.attempt = 0
        self.last_error = None

    @property
    def remaining(self) -> int:
        return max(0, self.max_retries - self.attempt)

    @property
    def is_exhausted(self) -> bool:
        return self.attempt >= self.max_retries
