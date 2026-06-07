"""通知管理器 — 持久化通知 + 启动环境检测。"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from . import __version__

logger = logging.getLogger(__name__)

_NOTIF_FILE = Path.home() / ".lumio" / "notifications.json"


@dataclass
class Notification:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    category: str = "env"         # deps / env / update
    type: str = "info"            # warning / info / update / tip
    title: str = ""
    message: str = ""
    action: str = ""              # "open_page:settings" / "open_url:xxx"
    action_text: str = ""         # 按钮文字
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    read: bool = False
    source_key: str = ""          # 去重标识（如 "cookie_missing"）
    dismissable: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Notification:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class NotificationManager(QObject):
    """管理全局通知，支持持久化 + 启动检测。"""

    notifications_changed = Signal(int)  # unread count

    def __init__(self, parent=None):
        super().__init__(parent)
        self._notifications: list[Notification] = []
        self._load()

    # ── CRUD ────────────────────────────────────────────────────────

    def get_all(self, category: str | None = None) -> list[Notification]:
        if category:
            return [n for n in self._notifications if n.category == category]
        return list(self._notifications)

    def unread_count(self) -> int:
        return len([n for n in self._notifications if not n.read])

    def mark_read(self, notif_id: str) -> None:
        for n in self._notifications:
            if n.id == notif_id:
                n.read = True
                break
        self._save()
        self.notifications_changed.emit(self.unread_count())

    def mark_all_read(self) -> None:
        for n in self._notifications:
            n.read = True
        self._save()
        self.notifications_changed.emit(0)

    def dismiss(self, notif_id: str) -> None:
        self._notifications = [n for n in self._notifications if n.id != notif_id]
        self._save()
        self.notifications_changed.emit(self.unread_count())

    def clear_read(self) -> None:
        """清除已读通知（永久通知保留）。"""
        self._notifications = [n for n in self._notifications if not n.read or not n.dismissable]
        self._save()
        self.notifications_changed.emit(self.unread_count())

    def add_notification(self, notif: Notification) -> None:
        # 按 source_key 去重：已存在则跳过
        if notif.source_key and any(n.source_key == notif.source_key for n in self._notifications):
            return
        self._notifications.append(notif)
        self._save()
        self.notifications_changed.emit(self.unread_count())

    # ── 检测 ────────────────────────────────────────────────────────

    def check_all(self) -> None:
        """启动时调用。"""
        self._check_cookies()
        self._check_extension_tip()
        self._check_ffmpeg()
        self._check_ig_risk()

    def check_version(self) -> str:
        """手动检查版本。返回: "latest" / "new:X.X.X" / "error:message"。"""
        try:
            from packaging.version import Version
        except ImportError:
            # fallback: 简单 tuple 比较
            def _ver_tuple(v: str):
                return tuple(int(x) for x in v.split(".") if x.isdigit())
            class _SimpleVersion:
                def __init__(self, v): self._v = _ver_tuple(v)
                def __gt__(self, o): return self._v > o._v
                def __eq__(self, o): return self._v == o._v
                def __le__(self, o): return self._v <= o._v
            Version = _SimpleVersion  # type: ignore

        try:
            result = subprocess.run(
                ["git", "fetch", "--tags", "origin"],
                capture_output=True, text=True, timeout=10,
                cwd=str(Path(__file__).parent.parent.parent),
            )
            result = subprocess.run(
                ["git", "tag", "-l", "v*", "--sort=-v:refname"],
                capture_output=True, text=True, timeout=5,
                cwd=str(Path(__file__).parent.parent.parent),
            )
            tags = [t.strip().lstrip("v") for t in result.stdout.strip().split("\n") if t.strip()]
            if not tags:
                return "error:未找到版本标签"
            latest = tags[0]
            if Version(latest) <= Version(__version__):
                return "latest"
            return f"new:{latest}"
        except Exception as e:
            return f"error:{e}"

    # ── 检查逻辑 ────────────────────────────────────────────────────

    def _check_cookies(self) -> None:
        try:
            from .gui.cookie_checker import check_ig_cookie_status, check_x_cookie_status, check_yt_cookie_status
            missing = []
            for name, checker in [("Instagram", check_ig_cookie_status),
                                  ("X", check_x_cookie_status),
                                  ("YouTube", check_yt_cookie_status)]:
                status = checker()
                if status in ("missing", "expired"):
                    missing.append(name)
            if missing:
                self.add_notification(Notification(
                    category="env",
                    type="warning",
                    title="Cookie 未配置或已过期",
                    message=f"以下平台 Cookie 缺失或已过期：{', '.join(missing)}",
                    action="open_page:settings",
                    action_text="去设置",
                    source_key="cookie_missing",
                ))
        except Exception as e:
            logger.debug("Cookie check failed: %s", e)

    def _check_extension_tip(self) -> None:
        try:
            from .utils.config import load_config
            cfg = load_config()
            shown = cfg.get("shown_tips", [])
            if "install_extension" not in shown:
                self.add_notification(Notification(
                    category="deps",
                    type="tip",
                    title="安装浏览器插件",
                    message="从浏览器一键发送链接到 Lumio，支持 YouTube、X 等平台。插件可在 GitHub 仓库下载。",
                    action="open_url:https://github.com/Roseannepark0211/Lumio",
                    action_text="了解",
                    source_key="install_extension",
                ))
        except Exception as e:
            logger.debug("Extension tip check failed: %s", e)

    def _check_ffmpeg(self) -> None:
        try:
            from .downloader import _find_ffmpeg
            if not _find_ffmpeg():
                self.add_notification(Notification(
                    category="deps",
                    type="warning",
                    title="FFmpeg 未安装",
                    message="视频合并功能依赖 FFmpeg，当前未检测到。",
                    action="",
                    action_text="",
                    source_key="ffmpeg_missing",
                ))
        except Exception as e:
            logger.debug("FFmpeg check failed: %s", e)

    def _check_ig_risk(self) -> None:
        """永久通知：Instagram 下载风险提示。"""
        self.add_notification(Notification(
            category="env",
            type="warning",
            title="Instagram 下载风险提示",
            message=(
                "Instagram 对自动化行为检测严格，频繁下载可能导致账号受限或封禁。\n\n"
                "建议：\n"
                "· 不要频繁批量抓取主页帖子\n"
                "· 单个帖子不要连续重复下载\n"
                "· 建议使用小号 Cookie，不要用主号\n"
                "· 插件发送 IG 链接时走浏览器直链，不调用 IG API，风险较低"
            ),
            source_key="ig_risk_warning",
            dismissable=False,
        ))

    # ── 持久化 ──────────────────────────────────────────────────────

    def _load(self) -> None:
        if not _NOTIF_FILE.exists():
            return
        try:
            data = json.loads(_NOTIF_FILE.read_text(encoding="utf-8"))
            self._notifications = [Notification.from_dict(d) for d in data]
        except Exception as e:
            logger.debug("Load notifications failed: %s", e)

    def _save(self) -> None:
        try:
            _NOTIF_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = [n.to_dict() for n in self._notifications]
            tmp = _NOTIF_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(_NOTIF_FILE)
        except Exception as e:
            logger.debug("Save notifications failed: %s", e)
