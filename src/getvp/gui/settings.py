from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..i18n import get_lang, set_lang, t
from ..utils.config import get_cookie_path, load_config, save_config


class SettingsDialog(QDialog):
    restart_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(t("settings"))
        self.setMinimumWidth(420)
        self.setModal(True)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        # ---- Cookie section ----
        cookie_group = QGroupBox(t("cookie_mgmt"))
        cg = QVBoxLayout(cookie_group)

        status_row = QHBoxLayout()
        status_row.addWidget(QLabel(t("cookie_status")))
        self._cookie_status = QLabel()
        self._update_cookie_status()
        status_row.addWidget(self._cookie_status)
        status_row.addStretch()
        cg.addLayout(status_row)

        self._import_btn = QPushButton(t("cookie_import"))
        self._import_btn.clicked.connect(self._on_import_cookie)
        cg.addWidget(self._import_btn)

        root.addWidget(cookie_group)

        # ---- Language section ----
        lang_group = QGroupBox(t("language"))
        lg = QHBoxLayout(lang_group)

        lg.addWidget(QLabel(t("language") + ":"))
        self._lang_combo = QComboBox()
        self._lang_combo.addItem("中文", "zh")
        self._lang_combo.addItem("English", "en")
        current = get_lang()
        idx = self._lang_combo.findData(current)
        if idx >= 0:
            self._lang_combo.setCurrentIndex(idx)
        self._lang_combo.currentIndexChanged.connect(self._on_lang_changed)
        lg.addWidget(self._lang_combo, 1)

        root.addWidget(lang_group)

        # ---- Download settings section ----
        dl_group = QGroupBox(t("download_settings"))
        dg = QVBoxLayout(dl_group)

        cfg = load_config()

        mc_row = QHBoxLayout()
        mc_row.addWidget(QLabel(t("max_concurrent") + ":"))
        self._concurrent_spin = QSpinBox()
        self._concurrent_spin.setRange(1, 10)
        self._concurrent_spin.setValue(cfg.get("max_concurrent", 3))
        mc_row.addWidget(self._concurrent_spin)
        mc_row.addStretch()
        dg.addLayout(mc_row)

        mr_row = QHBoxLayout()
        mr_row.addWidget(QLabel(t("max_retries") + ":"))
        self._retry_spin = QSpinBox()
        self._retry_spin.setRange(0, 10)
        self._retry_spin.setValue(cfg.get("max_retries", 3))
        mr_row.addWidget(self._retry_spin)
        mr_row.addStretch()
        dg.addLayout(mr_row)

        root.addWidget(dl_group)

        self._hint_label = QLabel("")
        self._hint_label.setObjectName("muted")
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._hint_label)

        # Close button
        close_row = QHBoxLayout()
        close_row.addStretch()
        self._close_btn = QPushButton(t("close"))
        self._close_btn.setObjectName("secondary")
        self._close_btn.clicked.connect(self._on_close)
        close_row.addWidget(self._close_btn)
        root.addLayout(close_row)

    def _update_cookie_status(self):
        p = get_cookie_path()
        if p:
            self._cookie_status.setText(t("cookie_valid"))
            self._cookie_status.setStyleSheet("color: #10b981; font-weight: 600;")
        else:
            self._cookie_status.setText(t("cookie_missing"))
            self._cookie_status.setStyleSheet("color: #f87171; font-weight: 600;")

    def _on_close(self):
        cfg = load_config()
        cfg["max_concurrent"] = self._concurrent_spin.value()
        cfg["max_retries"] = self._retry_spin.value()
        save_config(cfg)
        self.accept()

    @Slot()
    def _on_import_cookie(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            t("cookie_import"),
            "",
            "Cookie Files (*.txt);;All Files (*)",
        )
        if not path:
            return

        try:
            cfg = load_config()
            dest = Path(cfg["cookie_file"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)

            # Validate after import
            from .cookie_checker import check_ig_cookie_status
            status = check_ig_cookie_status()
            if status == "已配置":
                self._hint_label.setText(t("cookie_imported"))
                self._hint_label.setStyleSheet("color: #10b981;")
            elif status == "已失效":
                self._hint_label.setText(f"{t('cookie_imported')} — {t('cookie_expired')}")
                self._hint_label.setStyleSheet("color: #fbbf24;")
            else:
                self._hint_label.setText(t("cookie_imported"))
                self._hint_label.setStyleSheet("color: #10b981;")
            self._update_cookie_status()
        except Exception as e:
            QMessageBox.critical(
                self, t("error"), t("cookie_import_fail", err=str(e))
            )

    @Slot(int)
    def _on_lang_changed(self, index: int):
        lang = self._lang_combo.currentData()
        if lang and lang != get_lang():
            set_lang(lang)
            self._confirm_restart()

    def _confirm_restart(self):
        box = QMessageBox(self)
        box.setWindowTitle(t("settings"))
        box.setText(t("restart_hint"))
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.button(QMessageBox.StandardButton.Yes).setText(t("restart_now"))
        box.button(QMessageBox.StandardButton.No).setText(t("restart_later"))
        box.setIcon(QMessageBox.Icon.Question)

        if box.exec() == QMessageBox.StandardButton.Yes:
            self.accept()
            self.restart_requested.emit()
