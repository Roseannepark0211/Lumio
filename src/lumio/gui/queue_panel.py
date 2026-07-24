from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..i18n import t
from ..queue_manager import DownloadManager, QueueTask, TaskStatus
from .laser_progress import LaserProgress

_ERROR_MESSAGES = {
    "cookie_expired": "error_cookie",
    "network": "error_network",
    "rate_limited": "error_rate_limited",
    "content_removed": "error_content_removed",
    "parse_failed": "error_parse_failed",
}


_STATUS_BADGE_MAP = {
    TaskStatus.WAITING.value: "badge_waiting",
    TaskStatus.DOWNLOADING.value: "badge_downloading",
    TaskStatus.PAUSED.value: "badge_paused",
    TaskStatus.RETRYING.value: "badge_retrying",
    TaskStatus.INTERRUPTED.value: "badge_interrupted",
    TaskStatus.COMPLETED.value: "badge_completed",
    TaskStatus.FAILED.value: "badge_failed",
    TaskStatus.CANCELLED.value: "badge_cancelled",
}


class QueueTaskWidget(QFrame):
    action_requested = Signal(str, str)  # task_id, action

    def __init__(self, qt: QueueTask, parent=None):
        super().__init__(parent)
        self.task_id = qt.task_id
        self.setObjectName("task_card")
        self._build_ui(qt)

    def _build_ui(self, qt: QueueTask):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 4)
        root.setSpacing(3)

        # Row 1: thumbnail + info + status
        top = QHBoxLayout()
        top.setSpacing(8)

        # Thumbnail
        self._thumb = QLabel()
        self._thumb.setFixedSize(36, 36)
        self._thumb.setObjectName("library_card_thumb")
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setText(qt.platform[:2].upper())
        top.addWidget(self._thumb)

        # Info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(0)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self._title = QLabel(qt.title[:50])
        self._title.setObjectName("task_title")
        title_row.addWidget(self._title, 1)

        # Platform badge
        plat_text, plat_obj = self._platform_info(qt.platform)
        plat = QLabel(plat_text)
        plat.setObjectName(plat_obj)
        plat.setFixedHeight(16)
        title_row.addWidget(plat)

        # Media type badge
        media_label, media_obj = self._media_type_info(qt)
        if media_label:
            media_badge = QLabel(media_label)
            media_badge.setObjectName(media_obj)
            media_badge.setFixedHeight(16)
            title_row.addWidget(media_badge)

        info_layout.addLayout(title_row)

        self._speed_label = QLabel("")
        self._speed_label.setObjectName("task_speed")
        info_layout.addWidget(self._speed_label)

        top.addLayout(info_layout, 1)

        # Status badge
        self._badge = QLabel(self._status_text(qt.status))
        badge_obj = _STATUS_BADGE_MAP.get(qt.status, "badge_waiting")
        self._badge.setObjectName(badge_obj)
        self._badge.setFixedHeight(18)
        top.addWidget(self._badge)

        root.addLayout(top)

        # Row 2: progress bar (Liquid Glass static bar + 激光粒子动态覆盖层)
        # 双层结构：默认显示 QProgressBar；下载中状态切换为 LaserProgress 激光粒子
        self._progress = QProgressBar()
        self._progress.setTextVisible(True)
        self._progress.setFormat("%p%")
        self._progress.setValue(int(qt.progress))
        self._progress.setFixedHeight(14)
        root.addWidget(self._progress)

        # 激光粒子进度条（下载中状态显示）
        self._laser = LaserProgress()
        self._laser.set_value(qt.progress / 100.0)
        self._laser.setFixedHeight(14)
        self._laser.hide()
        root.addWidget(self._laser)

        # Row 3: action buttons
        self._btn_row = QHBoxLayout()
        self._btn_row.setSpacing(4)
        self._btn_row.setContentsMargins(0, 0, 0, 0)
        self._btn_row.addStretch()
        self._update_buttons(qt.status)
        root.addLayout(self._btn_row)

    @staticmethod
    def _platform_info(platform: str) -> tuple[str, str]:
        if platform == "youtube":
            return "YT", "platform_yt"
        if platform == "instagram":
            return "IG", "platform_ig"
        if platform == "x":
            return "X", "platform_x"
        return platform[:2].upper(), ""

    @staticmethod
    def _media_type_info(qt: QueueTask) -> tuple[str, str]:
        ft = qt.format_type
        if ft == "audio":
            return "Audio", "media_audio"
        if ft in ("video", "combined"):
            return "Video", "media_video"
        if ft == "image":
            return "Image", "media_image"
        # IG: format_type is empty, can't determine type until download
        return "", ""

    def _status_text(self, status: str) -> str:
        mapping = {
            TaskStatus.WAITING.value: t("status_waiting"),
            TaskStatus.DOWNLOADING.value: t("status_downloading"),
            TaskStatus.PAUSED.value: t("status_paused"),
            TaskStatus.RETRYING.value: t("status_retrying"),
            TaskStatus.INTERRUPTED.value: t("status_interrupted"),
            TaskStatus.COMPLETED.value: t("status_completed"),
            TaskStatus.FAILED.value: t("status_failed"),
            TaskStatus.CANCELLED.value: t("status_cancelled"),
        }
        return mapping.get(status, status)

    def _clear_buttons(self):
        while self._btn_row.count() > 1:  # keep the stretch
            item = self._btn_row.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

    def _add_btn(self, text: str, action: str, danger: bool = False):
        btn = QPushButton(text)
        btn.setObjectName("task_btn_danger" if danger else "task_btn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self.action_requested.emit(self.task_id, action))
        self._btn_row.addWidget(btn)

    def _update_buttons(self, status: str):
        self._clear_buttons()
        if status == TaskStatus.WAITING.value:
            self._add_btn(t("start"), "start")
            self._add_btn(t("cancel"), "cancel")
            self._add_btn(t("delete"), "delete", danger=True)
        elif status == TaskStatus.DOWNLOADING.value:
            self._add_btn(t("pause"), "pause")
            self._add_btn(t("cancel"), "cancel", danger=True)
        elif status == TaskStatus.RETRYING.value:
            self._add_btn(t("cancel"), "cancel", danger=True)
        elif status == TaskStatus.INTERRUPTED.value:
            self._add_btn(t("resume"), "resume")
            self._add_btn(t("cancel"), "cancel")
            self._add_btn(t("delete"), "delete", danger=True)
        elif status == TaskStatus.PAUSED.value:
            self._add_btn(t("resume"), "resume")
            self._add_btn(t("cancel"), "cancel")
            self._add_btn(t("delete"), "delete", danger=True)
        elif status == TaskStatus.COMPLETED.value:
            self._add_btn(t("open_file"), "open_file")
            self._add_btn(t("open_dir"), "open_dir")
            self._add_btn(t("delete"), "delete", danger=True)
        elif status in (TaskStatus.FAILED.value, TaskStatus.CANCELLED.value):
            self._add_btn(t("retry"), "retry")
            self._add_btn(t("delete"), "delete", danger=True)

    # ---- Public update methods ----

    def update_progress(self, progress: float, speed: str, filename: str):
        self._progress.setValue(int(progress))
        # 同步激光粒子进度条
        self._laser.set_value(progress / 100.0)
        if speed:
            self._speed_label.setText(speed)

    def update_status(self, status: str, retry_info: str = ""):
        text = self._status_text(status) + retry_info
        self._badge.setText(text)
        badge_obj = _STATUS_BADGE_MAP.get(status, "badge_waiting")
        self._badge.setObjectName(badge_obj)
        self._badge.style().unpolish(self._badge)
        self._badge.style().polish(self._badge)
        # 下载中状态切换为激光粒子进度条
        if status == TaskStatus.DOWNLOADING.value:
            self._progress.hide()
            self._laser.show()
        else:
            self._progress.show()
            self._laser.hide()
        self._update_buttons(status)

    def update_finished(self, success: bool, error: str, error_category: str = ""):
        if success:
            self.update_status(TaskStatus.COMPLETED.value)
            self._speed_label.setText(t("pct_done"))
        else:
            self.update_status(TaskStatus.FAILED.value)
            friendly = _ERROR_MESSAGES.get(error_category, "")
            if friendly:
                self._speed_label.setText(t(friendly))
            else:
                self._speed_label.setText(f"{t('error')}: {error[:40]}")
