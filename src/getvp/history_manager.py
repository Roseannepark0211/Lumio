from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .utils.config import get_history_path


@dataclass
class HistoryRecord:
    record_id: str = ""
    title: str = ""
    author: str = ""
    platform: str = ""
    url: str = ""
    file_path: str = ""
    file_size: int = 0
    thumbnail_url: str = ""
    download_time: str = ""
    success: bool = True
    duration_seconds: float = 0.0
    batch_id: str = ""

    def __post_init__(self):
        if not self.record_id:
            self.record_id = uuid.uuid4().hex[:12]
        if not self.download_time:
            self.download_time = datetime.now().isoformat(timespec="seconds")


class HistoryManager:
    def __init__(self):
        self._records: list[HistoryRecord] = []
        self.load()

    def load(self):
        path = get_history_path()
        if not path.exists():
            self._records = []
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self._records = [HistoryRecord(**r) for r in data]
        except Exception:
            self._records = []

    def save(self):
        path = get_history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump([asdict(r) for r in self._records], f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)

    def add(self, record: HistoryRecord):
        self._records.insert(0, record)
        self.save()

    def delete(self, record_id: str):
        self._records = [r for r in self._records if r.record_id != record_id]
        self.save()

    def clear(self):
        self._records.clear()
        self.save()

    @property
    def records(self) -> list[HistoryRecord]:
        return list(self._records)
