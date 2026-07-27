"""通知管理器 — 持久化通知 + 启动环境检测 + 事件总线。

重构要点（v2）：
- 加 threading.Lock 保证线程安全（参考 queue_manager 设计）
- Notification 数据模型扩展：priority / expires_at / group_key
- check_all 重构为分类检查：Python deps / 网络代理 / FFmpeg / Cookie 7天预警 / 插件
- check_all 改为后台异步执行，不阻塞启动
- 接入事件源：Apify 配额 / Cookie 7天预警 / 缓存清理完成 / 版本检查 7天周期
- dismiss 加 dismissable 防护
- TTL 自动清理（保留永久通知 + 未读通知）
- 单例模式，settings_page 不再 new 新实例
- 所有文案走 i18n
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .utils.signal import QObject, Signal

from . import __version__
from .i18n import t

logger = logging.getLogger(__name__)

_NOTIF_FILE = Path.home() / ".lumio" / "notifications.json"

# 版本检查周期：7 天
_VERSION_CHECK_INTERVAL = 7 * 24 * 3600  # seconds

# Python 运行时依赖（程序打包时的依赖）
# 注意：dict 的 key 必须是 Python import 名，不是 pip 包名
#   - yt-dlp 包的 import 名是 yt_dlp（连字符在 import 语法中非法）
#   - python-telegram-bot 包的 import 名是 telegram
_PYTHON_DEPS = {
    "yt_dlp": "YouTube/X 视频解析与下载",
    "instaloader": "Instagram 下载（逐步弃用）",
    "PySide6": "GUI 框架",
    "flask": "本地 API 服务",
    "sqlalchemy": "素材库 + 收件箱 ORM",
    "PIL": "缩略图生成",
    "apify_client": "Apify Actor 代理",
    "imageio_ffmpeg": "内置 ffmpeg 二进制",
    "requests": "HTTP 请求",
    "packaging": "版本号对比",
}

# 可选依赖：仅当用户启用对应功能时才检测，缺失时降级为 low priority 提示
# telegram（python-telegram-bot）→ Telegram Bot 跨设备采集功能
_OPTIONAL_DEPS = {
    "telegram": ("Telegram Bot 跨设备采集", "recommend_telegram"),
}


@dataclass
class Notification:
    """通知数据模型（schema v2）。

    新增字段（带默认值，旧 JSON 自动兼容）：
    - priority: critical / high / normal / low
    - expires_at: ISO 时间戳，空=永久；TTL 清理依据
    - group_key: 批次聚合 key（如同一批次下载）
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    category: str = "env"         # deps / env / update / system / inbox
    type: str = "info"            # warning / info / update / tip
    title: str = ""
    message: str = ""
    action: str = ""              # "open_page:settings" / "open_url:xxx" / "retry_task:id"
    action_text: str = ""         # 按钮文字
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    read: bool = False
    source_key: str = ""          # 去重标识（如 "cookie_missing"）
    dismissable: bool = True
    # v2 新增
    priority: str = "normal"      # critical / high / normal / low
    expires_at: str = ""          # ISO 时间戳，空=永久
    group_key: str = ""           # 批次聚合 key

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Notification:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ── 单例 ──────────────────────────────────────────────────────────────
_global_instance: NotificationManager | None = None
_global_lock = threading.Lock()


def get_notification_manager() -> NotificationManager:
    """获取全局唯一 NotificationManager 实例。"""
    global _global_instance
    if _global_instance is None:
        with _global_lock:
            if _global_instance is None:
                _global_instance = NotificationManager()
    return _global_instance


def set_notification_manager(mgr: NotificationManager) -> None:
    """注入已创建的实例（main.py 启动时调用）。"""
    global _global_instance
    with _global_lock:
        _global_instance = mgr


class NotificationManager(QObject):
    """管理全局通知，支持持久化 + 启动检测 + 事件接入。

    线程安全：所有公开方法对 _notifications 加锁。
    信号在锁外发射（参考 queue_manager 设计，避免 QML slot 同步回调死锁）。
    """

    notifications_changed = Signal(int)  # unread count

    def __init__(self, parent=None):
        super().__init__(parent)
        self._notifications: list[Notification] = []
        # 修复：用 RLock（可重入锁）替代 Lock
        # 原因：add_notification / mark_read / dismiss / clear_read / _cleanup_expired
        # 等方法在持锁状态下会调用 self.unread_count()，后者再次 with self._lock。
        # threading.Lock 不可重入 → 同线程二次 acquire 永久阻塞 → 后台 _check_all_sync
        # 线程死锁，锁永不释放，UI 线程调 getNotificationsJson 时永久卡死。
        # RLock 允许同线程多次 acquire，彻底修复此死锁。
        self._lock = threading.RLock()
        self._checking = False  # check_all 防重入
        self._load()

    # ── CRUD ────────────────────────────────────────────────────────

    def get_all(self, category: str | None = None) -> list[Notification]:
        with self._lock:
            if category:
                return [n for n in self._notifications if n.category == category]
            return list(self._notifications)

    def unread_count(self) -> int:
        with self._lock:
            return len([n for n in self._notifications if not n.read])

    def mark_read(self, notif_id: str) -> None:
        with self._lock:
            for n in self._notifications:
                if n.id == notif_id:
                    n.read = True
                    break
            self._save_locked()
            count = self.unread_count()
        self.notifications_changed.emit(count)

    def mark_all_read(self) -> None:
        with self._lock:
            for n in self._notifications:
                n.read = True
            self._save_locked()
        self.notifications_changed.emit(0)

    def dismiss(self, notif_id: str) -> None:
        """关闭通知。永久通知（dismissable=False）不可关闭。"""
        with self._lock:
            # 防护：dismissable=False 的永久通知不允许 dismiss
            target = None
            for n in self._notifications:
                if n.id == notif_id:
                    target = n
                    break
            if target is None:
                return
            if not target.dismissable:
                logger.debug("Cannot dismiss permanent notification: %s", notif_id)
                return
            self._notifications = [n for n in self._notifications if n.id != notif_id]
            self._save_locked()
            count = self.unread_count()
        self.notifications_changed.emit(count)

    def clear_read(self) -> None:
        """清除已读通知（永久通知即使已读也保留）。"""
        with self._lock:
            self._notifications = [
                n for n in self._notifications
                if not n.read or not n.dismissable
            ]
            self._save_locked()
            count = self.unread_count()
        self.notifications_changed.emit(count)

    def add_notification(self, notif: Notification) -> None:
        """添加通知。按 source_key 去重（已存在则跳过）。"""
        with self._lock:
            if notif.source_key and any(
                n.source_key == notif.source_key for n in self._notifications
            ):
                return
            self._notifications.append(notif)
            self._save_locked()
            count = self.unread_count()
        self.notifications_changed.emit(count)

    def _remove_by_source_key(self, source_key: str) -> None:
        """按 source_key 清理通知（用于修复历史误报后清理过时通知）。

        清理成功后触发 notifications_changed 信号让 UI 刷新。
        """
        with self._lock:
            before = len(self._notifications)
            self._notifications = [
                n for n in self._notifications if n.source_key != source_key
            ]
            if len(self._notifications) != before:
                self._save_locked()
                count = self.unread_count()
            else:
                return
        self.notifications_changed.emit(count)

    # ── 启动检测（后台异步） ────────────────────────────────────────

    def check_all(self, async_run: bool = True) -> None:
        """启动时调用。默认后台异步执行，不阻塞 GUI。

        重构后分类检查：
        1. Python 依赖（yt-dlp/PySide6/Flask 等）
        2. 网络代理（国外平台需 VPN/系统代理）
        3. FFmpeg（imageio-ffmpeg 内置二进制）
        4. Cookie 状态（missing/expired/warning 7天预警）
        5. 浏览器插件提示（一次性 tip）
        6. IG 风险提示（永久通知）
        7. 版本检查（7 天周期，非每次启动）
        """
        if async_run:
            threading.Thread(target=self._check_all_sync, daemon=True).start()
        else:
            self._check_all_sync()

    def _check_all_sync(self) -> None:
        """实际执行检查（同步，应在后台线程跑）。"""
        with self._lock:
            if self._checking:
                return
            self._checking = True

        try:
            self._check_python_deps()
            self._check_network_proxy()
            self._check_ffmpeg()
            self._check_cookies()
            self._check_extension_tip()
            self._check_ig_risk()
            self._check_software_recommendations()  # 新增：配套软件建议永久通知
            self._check_version_periodic()
            self._check_cache_status()    # 新增：系统分类始终有缓存概览通知
            self._cleanup_expired()
        finally:
            with self._lock:
                self._checking = False

    # ── 检查逻辑 ────────────────────────────────────────────────────

    def _check_python_deps(self) -> None:
        """检查 Python 运行时依赖是否完整。

        必需依赖缺失 → critical 通知；
        可选依赖缺失 → 不发通知（已有 recommend_telegram 永久提示引导用户安装）。
        之前发的过时通知（如 yt-dlp 误报）自动清理，避免历史污染。
        """
        missing = []
        for mod, desc in _PYTHON_DEPS.items():
            try:
                __import__(mod)
            except ImportError:
                missing.append(f"{mod} ({desc})")

        if missing:
            self.add_notification(Notification(
                category="deps",
                type="warning",
                priority="critical",
                title=t("notif_python_deps_missing_title"),
                message=t("notif_python_deps_missing_msg", ", ".join(missing)),
                action="open_url:https://github.com/Roseannepark0211/Lumio",
                action_text=t("notif_action_install"),
                source_key="python_deps_missing",
            ))
        else:
            # 必需依赖齐全 → 清理之前发的过时通知（如修复 import 名后 yt-dlp 不再误报）
            self._remove_by_source_key("python_deps_missing")

        # 可选依赖缺失不发通知（避免噪音），已有 recommend_* 永久通知引导用户

    def _check_network_proxy(self) -> None:
        """检查系统代理配置（国外平台需 VPN/代理）。

        国内平台（B站/抖音/快手/微博/小红书）不需要代理；
        国外平台（YouTube/Instagram/X/Twitter CDN）必须代理。
        检测 HTTP_PROXY/HTTPS_PROXY 环境变量 + Windows 注册表代理。
        """
        import os
        import urllib.request

        proxy_configured = False
        # 1. 环境变量
        if os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY"):
            proxy_configured = True
        # 2. 系统代理（Windows/macOS）
        if not proxy_configured:
            try:
                proxies = urllib.request.getproxies()
                if proxies:
                    proxy_configured = True
            except Exception:
                pass

        if not proxy_configured:
            self.add_notification(Notification(
                category="deps",
                type="warning",
                priority="high",
                title=t("notif_proxy_missing_title"),
                message=t("notif_proxy_missing_msg"),
                action="open_page:settings",
                action_text=t("notif_action_configure"),
                source_key="proxy_missing",
            ))

    def _check_ffmpeg(self) -> None:
        try:
            from .downloader import _find_ffmpeg
            if not _find_ffmpeg():
                self.add_notification(Notification(
                    category="deps",
                    type="warning",
                    priority="high",
                    title=t("notif_ffmpeg_missing_title"),
                    message=t("notif_ffmpeg_missing_msg"),
                    action="",
                    action_text="",
                    source_key="ffmpeg_missing",
                ))
        except Exception as e:
            logger.debug("FFmpeg check failed: %s", e)

    def _check_cookies(self) -> None:
        """检查 Cookie 状态：missing / expired / warning（7天内过期）。

        重构后增加 warning 状态检测，提前 7 天预警。
        """
        try:
            from .gui.cookie_checker import (
                check_ig_cookie_status,
                check_x_cookie_status,
                check_yt_cookie_status,
                check_douyin_cookie_status,
                check_xiaohongshu_cookie_status,
                check_bilibili_cookie_status,
                check_kuaishou_cookie_status,
            )

            missing = []
            expiring = []
            for name, checker in [("Instagram", check_ig_cookie_status),
                                  ("X", check_x_cookie_status),
                                  ("YouTube", check_yt_cookie_status),
                                  ("抖音", check_douyin_cookie_status),
                                  ("小红书", check_xiaohongshu_cookie_status),
                                  ("B站", check_bilibili_cookie_status),
                                  ("快手", check_kuaishou_cookie_status)]:
                status = checker()
                if status in ("missing", "expired"):
                    missing.append(name)
                elif status == "warning":
                    expiring.append(name)

            if missing:
                self.add_notification(Notification(
                    category="env",
                    type="warning",
                    priority="high",
                    title=t("notif_cookie_missing_title"),
                    message=t("notif_cookie_missing_msg", ", ".join(missing)),
                    action="open_page:settings",
                    action_text=t("notif_action_configure"),
                    source_key="cookie_missing",
                ))

            # 新增：Cookie 即将过期预警（7 天内）
            if expiring:
                self.add_notification(Notification(
                    category="env",
                    type="warning",
                    priority="high",
                    title=t("notif_cookie_expiring_title"),
                    message=t("notif_cookie_expiring_msg", ", ".join(expiring)),
                    action="open_page:settings",
                    action_text=t("notif_action_update"),
                    source_key="cookie_expiring",
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
                    priority="low",
                    title=t("notif_extension_tip_title"),
                    message=t("notif_extension_tip_msg"),
                    action="open_url:https://github.com/Roseannepark0211/Lumio",
                    action_text=t("notif_action_learn"),
                    source_key="install_extension",
                ))
        except Exception as e:
            logger.debug("Extension tip check failed: %s", e)

    def _check_ig_risk(self) -> None:
        """永久通知：Instagram 下载风险提示 + Apify 替代方案（已合并）。

        文案更新时需强制覆盖旧通知（add_notification 按 source_key 去重会跳过），
        否则用户重启后看不到新内容。
        """
        # 先清理旧版本的 ig_risk_warning（让 add_notification 重新写入新文案）
        self._remove_by_source_key("ig_risk_warning")
        self.add_notification(Notification(
            category="env",
            type="warning",
            priority="normal",
            title=t("notif_ig_risk_title"),
            message=t("notif_ig_risk_msg"),
            source_key="ig_risk_warning",
            dismissable=False,
        ))

    def _check_software_recommendations(self) -> None:
        """永久通知：配套软件建议。

        帮助新用户了解：
        - 国外平台必需 VPN/代理
        - 推荐浏览器扩展、媒体播放器
        - 可选高级功能：Telegram Bot、Apify Token

        所有通知 dismissable=False（永久保留），按 priority 排序：
        - VPN（high）> 扩展/播放器（normal）> Telegram/Apify（low）
        """
        # 1. VPN/代理（必需，high priority）
        self.add_notification(Notification(
            category="system",
            type="warning",
            priority="high",
            title=t("recommend_vpn_title"),
            message=t("recommend_vpn_msg"),
            action="open_page:settings",
            action_text=t("notif_action_configure"),
            source_key="recommend_vpn",
            dismissable=False,
        ))

        # 2. 浏览器扩展（强烈推荐，normal priority）
        self.add_notification(Notification(
            category="system",
            type="tip",
            priority="normal",
            title=t("recommend_extension_title"),
            message=t("recommend_extension_msg"),
            action="open_url:https://github.com/Roseannepark0211/Lumio",
            action_text=t("notif_action_download"),
            source_key="recommend_extension",
            dismissable=False,
        ))

        # 3. 媒体播放器（推荐，normal priority）
        self.add_notification(Notification(
            category="system",
            type="tip",
            priority="normal",
            title=t("recommend_player_title"),
            message=t("recommend_player_msg"),
            source_key="recommend_player",
            dismissable=False,
        ))

        # 4. Telegram Bot（可选，low priority）
        self.add_notification(Notification(
            category="system",
            type="tip",
            priority="low",
            title=t("recommend_telegram_title"),
            message=t("recommend_telegram_msg"),
            action="open_page:settings",
            action_text=t("notif_action_configure"),
            source_key="recommend_telegram",
            dismissable=False,
        ))

        # 5. Apify Token 已合并到 IG 风险提示（notif_ig_risk）
        # 不再单独发 recommend_apify 通知，避免重复。
        # 清理之前发的 recommend_apify 通知（如果存在）
        self._remove_by_source_key("recommend_apify")

        # 6. 版权与使用声明（critical priority，最显眼，不可关闭）
        # 放在所有 system 永久通知最前（按 priority 排序时 critical 高于 high/normal/low）
        self.add_notification(Notification(
            category="system",
            type="warning",
            priority="critical",
            title=t("copyright_notice_title"),
            message=t("copyright_notice_msg"),
            source_key="copyright_notice",
            dismissable=False,
        ))

    def _check_version_periodic(self) -> None:
        """周期性版本检查（7 天一次）。

        持久化 last_version_check_at 到 config，避免每次启动都查 git。
        7 天内已检查：跳过网络请求，但保留已有通知（不主动清理）。
        """
        try:
            from .utils.config import load_config, save_config
            cfg = load_config()
            last_check = cfg.get("last_version_check_at", 0)
            now = time.time()
            if last_check and (now - last_check) < _VERSION_CHECK_INTERVAL:
                # 7 天内已检查：跳过网络请求
                # 已有的 version_latest/version_new 通知会从磁盘加载，无需重新生成
                return

            result = self._do_version_check()
            cfg["last_version_check_at"] = now
            save_config(cfg)

            if result.startswith("new:"):
                new_version = result[4:]
                # 移除旧的"已是最新"通知（如有），添加新版本通知
                with self._lock:
                    self._remove_by_source_key("version_new")
                    self._remove_by_source_key("version_latest")
                self.add_notification(Notification(
                    category="update",
                    type="update",
                    priority="normal",
                    title=t("notif_version_new_title"),
                    message=t("notif_version_new_msg", __version__, new_version),
                    action="open_url:https://github.com/Roseannepark0211/Lumio/releases",
                    action_text=t("notif_action_download"),
                    source_key="version_new",
                ))
            elif result == "latest":
                # 移除旧通知（如有），添加新的"已是最新"
                # 修复：去掉 expires_at=now，让 version_latest 持久保留
                # 否则下次启动 _cleanup_expired 会清掉（如果用户已读），
                # 再加上 7 天内跳过检查，版本分类就永远空了
                with self._lock:
                    self._remove_by_source_key("version_new")
                    self._remove_by_source_key("version_latest")
                self.add_notification(Notification(
                    category="update",
                    type="info",
                    priority="low",
                    title=t("notif_version_latest_title"),
                    message=t("notif_version_latest_msg", __version__),
                    source_key="version_latest",
                    # 不设 expires_at，持久保留
                ))
            # error 不发通知，仅日志
            elif result.startswith("error:"):
                logger.debug("Version check error: %s", result[6:])
        except Exception as e:
            logger.debug("Version periodic check failed: %s", e)

    def _check_cache_status(self) -> None:
        """检查缓存状态，生成/更新一条系统分类的缓存概览通知。

        确保 system 分类始终有内容（避免"系统通知消失了"的体验）。
        每次 check_all 调用时刷新统计，复用同一 source_key。
        """
        try:
            from .utils.cache_manager import get_cache_stats
            stats = get_cache_stats()

            # get_cache_stats 返回格式：
            #   {name: {"size_bytes", "size_mb", "file_count", "path"},
            #    "_total": {...}, "_root": str}
            total = stats.get("_total", {})
            total_size = total.get("size_bytes", 0)
            total_files = total.get("file_count", 0)

            # 格式化总体积
            if total_size >= 1024 ** 3:
                size_str = f"{total_size / (1024 ** 3):.2f} GB"
            elif total_size >= 1024 ** 2:
                size_str = f"{total_size / (1024 ** 2):.1f} MB"
            elif total_size >= 1024:
                size_str = f"{total_size / 1024:.1f} KB"
            else:
                size_str = f"{total_size} B"

            # 各子目录明细
            dir_labels = {
                "inbox_media": "收件箱媒体",
                "thumbs": "缩略图",
                "provider_cache": "Provider 缓存",
                "preview": "预览缓存",
            }
            details = []
            for dkey, label in dir_labels.items():
                dval = stats.get(dkey, {})
                d_size = dval.get("size_bytes", 0)
                d_files = dval.get("file_count", 0)
                if d_size == 0 and d_files == 0:
                    continue
                if d_size >= 1024 ** 2:
                    d_size_str = f"{d_size / (1024 ** 2):.1f} MB"
                elif d_size >= 1024:
                    d_size_str = f"{d_size / 1024:.1f} KB"
                else:
                    d_size_str = f"{d_size} B"
                details.append(f"{label}: {d_size_str} ({d_files} 文件)")

            detail_str = " · ".join(details) if details else "无缓存"

            # 替换旧的同 source_key 通知（刷新统计）
            with self._lock:
                self._remove_by_source_key("cache_status")
            self.add_notification(Notification(
                category="system",
                type="info",
                priority="low",
                title=t("notif_cache_status_title"),
                message=t("notif_cache_status_msg", size_str, total_files, detail_str),
                action="open_page:settings",
                action_text=t("notif_action_configure"),
                source_key="cache_status",
            ))
        except Exception as e:
            logger.debug("Cache status check failed: %s", e)

    def _do_version_check(self) -> str:
        """实际执行版本检查。返回: "latest" / "new:X.X.X" / "error:message"。"""
        try:
            from packaging.version import Version
        except ImportError:
            def _ver_tuple(v: str):
                return tuple(int(x) for x in v.split(".") if x.isdigit())

            class _SimpleVersion:
                def __init__(self, v):
                    self._v = _ver_tuple(v)

                def __gt__(self, o):
                    return self._v > o._v

                def __eq__(self, o):
                    return self._v == o._v

                def __le__(self, o):
                    return self._v <= o._v

            Version = _SimpleVersion  # type: ignore

        try:
            subprocess.run(
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

    def check_version_manual(self) -> str:
        """手动触发版本检查（Settings 页面"检查更新"按钮）。

        复用单例，不创建新实例（修复原 settings_page.py 双实例 bug）。
        返回: "latest" / "new:X.X.X" / "error:message"。
        """
        result = self._do_version_check()

        # 更新 last_version_check_at
        try:
            from .utils.config import load_config, save_config
            cfg = load_config()
            cfg["last_version_check_at"] = time.time()
            save_config(cfg)
        except Exception:
            pass

        if result.startswith("new:"):
            new_version = result[4:]
            # 移除旧的新版本通知（如有），添加新的
            self._remove_by_source_key("version_new")
            self._remove_by_source_key("version_latest")
            self.add_notification(Notification(
                category="update",
                type="update",
                priority="normal",
                title=t("notif_version_new_title"),
                message=t("notif_version_new_msg", __version__, new_version),
                action="open_url:https://github.com/Roseannepark0211/Lumio/releases",
                action_text=t("notif_action_download"),
                source_key="version_new",
            ))
        elif result == "latest":
            self._remove_by_source_key("version_new")
            self._remove_by_source_key("version_latest")
            self.add_notification(Notification(
                category="update",
                type="info",
                priority="low",
                title=t("notif_version_latest_title"),
                message=t("notif_version_latest_msg", __version__),
                source_key="version_latest",
            ))
        return result

    def _remove_by_source_key(self, source_key: str) -> None:
        """按 source_key 移除通知（内部用，不加锁，调用方需持锁）。"""
        self._notifications = [
            n for n in self._notifications if n.source_key != source_key
        ]

    # ── 事件接入 API ────────────────────────────────────────────────

    def notify_apify_quota(self, usage_usd: float, plan_credits_usd: float) -> None:
        """Apify 配额通知。

        - usage >= plan_credits: critical（耗尽）
        - usage >= plan_credits * 0.8: high（80% 告警）
        - 其他: 不通知
        """
        if plan_credits_usd <= 0:
            return

        ratio = usage_usd / plan_credits_usd

        if ratio >= 1.0:
            # 配额耗尽：移除 80% 告警，添加 critical
            with self._lock:
                self._remove_by_source_key("apify_quota_warning")
            self.add_notification(Notification(
                category="system",
                type="warning",
                priority="critical",
                title=t("notif_apify_exhausted_title"),
                message=t("notif_apify_exhausted_msg",
                          f"${usage_usd:.2f}", f"${plan_credits_usd:.2f}"),
                action="open_page:settings",
                action_text=t("notif_action_configure"),
                source_key="apify_quota_exhausted",
            ))
        elif ratio >= 0.8:
            # 80% 告警：移除耗尽通知（如有），添加 high
            with self._lock:
                self._remove_by_source_key("apify_quota_exhausted")
            self.add_notification(Notification(
                category="system",
                type="warning",
                priority="high",
                title=t("notif_apify_warning_title"),
                message=t("notif_apify_warning_msg",
                          f"${usage_usd:.2f}", f"${plan_credits_usd:.2f}",
                          f"{ratio * 100:.0f}%"),
                action="open_page:settings",
                action_text=t("notif_action_view"),
                source_key="apify_quota_warning",
            ))
        else:
            # 配额正常：清理告警通知
            with self._lock:
                self._remove_by_source_key("apify_quota_warning")
                self._remove_by_source_key("apify_quota_exhausted")
                self._save_locked()
                count = self.unread_count()
            if count > 0 or True:  # 始终 emit 一次，让 UI 刷新
                self.notifications_changed.emit(count)

    def notify_cache_cleaned(self, files_cleaned: int, size_freed: int) -> None:
        """缓存清理完成通知。

        只有当确实清理了文件时才通知（files_cleaned > 0），避免频繁点击产生噪音。
        """
        if files_cleaned <= 0:
            return  # 没清理任何东西，静默

        # 格式化 size
        if size_freed >= 1024 * 1024:
            size_str = f"{size_freed / 1024 / 1024:.1f} MB"
        elif size_freed >= 1024:
            size_str = f"{size_freed / 1024:.1f} KB"
        else:
            size_str = f"{size_freed} B"

        # 移除旧的清理通知，添加新的（每次清理只保留最新一条）
        with self._lock:
            self._remove_by_source_key("cache_cleaned")
        self.add_notification(Notification(
            category="system",
            type="info",
            priority="low",
            title=t("notif_cache_cleaned_title"),
            message=t("notif_cache_cleaned_msg", files_cleaned, size_str),
            source_key="cache_cleaned",
        ))

    def notify_inbox_new(self, count: int = 1) -> None:
        """Inbox 新内容到达通知。

        注意：Inbox 新内容只走 sidebar 红点，不进通知中心。
        此方法仅用于更新未读计数，实际不入库。
        """
        # 不添加通知，仅 emit signal 让 sidebar 刷新红点
        self.notifications_changed.emit(self.unread_count())

    # ── TTL 自动清理 ────────────────────────────────────────────────

    def _cleanup_expired(self) -> None:
        """清理过期通知（expires_at 已过期的）。

        保留：
        - 永久通知（expires_at 为空）
        - 未读通知（避免误删用户未看到的重要通知）
        - dismissable=False 的通知
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            before = len(self._notifications)
            self._notifications = [
                n for n in self._notifications
                if not n.expires_at  # 永久通知保留
                or n.read is False  # 未读保留
                or not n.dismissable  # 永久通知保留
                or n.expires_at > now_iso  # 未过期保留
            ]
            after = len(self._notifications)
            if before != after:
                self._save_locked()
                count = self.unread_count()
            else:
                count = None
        if count is not None:
            self.notifications_changed.emit(count)

    # ── 持久化 ──────────────────────────────────────────────────────

    def _load(self) -> None:
        if not _NOTIF_FILE.exists():
            return
        try:
            data = json.loads(_NOTIF_FILE.read_text(encoding="utf-8"))
            with self._lock:
                self._notifications = [Notification.from_dict(d) for d in data]
        except Exception as e:
            logger.debug("Load notifications failed: %s", e)

    def _save_locked(self) -> None:
        """保存到磁盘（调用方需持锁）。原子写入：先 .tmp 再 replace。"""
        try:
            _NOTIF_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = [n.to_dict() for n in self._notifications]
            tmp = _NOTIF_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(_NOTIF_FILE)
        except Exception as e:
            logger.debug("Save notifications failed: %s", e)
