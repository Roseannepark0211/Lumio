"""格式选择对话框 — 从 URL 提取信息后让用户选择下载格式。"""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ..downloader import VideoInfo, _build_format_options, extract_info
from ..i18n import t
from .widgets import NoWheelComboBox


class _InfoWorker(QThread):
    """后台线程提取视频信息。"""
    finished = Signal(object)  # VideoInfo or None
    error = Signal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self):
        try:
            info = extract_info(self._url)
            self.finished.emit(info)
        except Exception as e:
            self.error.emit(str(e))


class FormatSelectDialog(QDialog):
    """格式选择弹框 — 给定 URL，提取信息后选择格式。"""

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("format_download"))
        self.setMinimumWidth(400)
        self._info: VideoInfo | None = None
        self._url = url
        self._result: tuple[str, str] | None = None  # (format_id, format_type)
        self._build_ui()
        self._start_extract()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Info label
        self._info_label = QLabel(t("loading"))
        self._info_label.setObjectName("status_msg")
        self._info_label.setWordWrap(True)
        layout.addWidget(self._info_label)

        # Format combo
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel(t("format_label")))
        self._format_combo = NoWheelComboBox()
        self._format_combo.setEnabled(False)
        fmt_row.addWidget(self._format_combo, 1)
        layout.addLayout(fmt_row)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._cancel_btn = QPushButton(t("cancel"))
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._cancel_btn)
        self._ok_btn = QPushButton(t("download"))
        self._ok_btn.setObjectName("accent_btn")
        self._ok_btn.setEnabled(False)
        self._ok_btn.clicked.connect(self._on_accept)
        btn_row.addWidget(self._ok_btn)
        layout.addLayout(btn_row)

    def _start_extract(self):
        self._worker = _InfoWorker(self._url, self)
        self._worker.finished.connect(self._on_info)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._cleanup_worker)
        self._worker.error.connect(self._cleanup_worker)
        self._worker.start()

    def _cleanup_worker(self):
        if hasattr(self, "_worker") and self._worker:
            self._worker.deleteLater()
            self._worker = None

    def reject(self):
        if hasattr(self, "_worker") and self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(1000)
        super().reject()

    def _on_info(self, info: VideoInfo):
        self._info = info
        self._info_label.setText(f"{info.title}\n{info.author}" if info.author else info.title)

        # Populate formats
        self._format_combo.clear()
        if info.platform == "youtube":
            # YouTube：用 _build_format_options 构建详细格式列表（含音视频分离流）
            opts = _build_format_options(info)
            for opt in opts:
                self._format_combo.addItem(opt["label"], (opt["id"], opt.get("_type", "")))
            self._format_combo.setEnabled(True)
        elif info.formats:
            # 国内平台多清晰度（抖音/快手等）：info.formats 来自 Provider 的 FormatOption
            # 先加「全部下载」选项（用于多图/多视频混合内容）
            all_label = t("download_all").format(
                video=f" {len(info.items)}" if info.items else "",
                sep="" if not info.items else "",
                image="",
            )
            self._format_combo.addItem(all_label, ("best", ""))
            # 再加各清晰度选项
            seen_labels = set()
            for fmt in info.formats:
                fid = fmt.get("format_id", "")
                label = fmt.get("format_note", "") or fmt.get("height", "") or fid
                if not fid or fid == "best" or label in seen_labels:
                    continue
                seen_labels.add(label)
                height = fmt.get("height", 0)
                display = f"{label}" if not height else f"{label} ({height}P)"
                self._format_combo.addItem(display, (fid, "video"))
            self._format_combo.setEnabled(True)
        else:
            # 无格式选项（如 X 图片/IG 图片/单一直链）：只有「全部下载」
            self._format_combo.addItem(t("download_all").format(
                video=f" {len(info.items)}" if info.items else "",
                sep="" if not info.items else "",
                image="",
            ), ("best", ""))
            self._format_combo.setEnabled(False)

        self._ok_btn.setEnabled(True)

    def _on_error(self, err: str):
        self._info_label.setText(f"{t('parse_failed')}: {err}")
        self._info_label.setProperty("state", "error")
        self._info_label.style().unpolish(self._info_label)
        self._info_label.style().polish(self._info_label)

    def _on_accept(self):
        fmt_data = self._format_combo.currentData()
        if isinstance(fmt_data, tuple):
            self._result = fmt_data
        else:
            self._result = (fmt_data, "")
        self.accept()

    def get_result(self) -> tuple[str, str] | None:
        """返回 (format_id, format_type) 或 None。"""
        return self._result

    def get_info(self) -> VideoInfo | None:
        return self._info
