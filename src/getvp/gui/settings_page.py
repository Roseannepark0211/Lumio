from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
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


class SettingsPage(QWidget):
    restart_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settings_page")
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(20)

        # Title
        title = QLabel(t("settings"))
        title.setObjectName("page_title")
        root.addWidget(title)

        # ---- General section ----
        general_group = QGroupBox(t("settings_general"))
        gg = QVBoxLayout(general_group)

        # Language
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel(t("language") + ":"))
        self._lang_combo = QComboBox()
        self._lang_combo.addItem("中文", "zh")
        self._lang_combo.addItem("English", "en")
        current = get_lang()
        idx = self._lang_combo.findData(current)
        if idx >= 0:
            self._lang_combo.setCurrentIndex(idx)
        self._lang_combo.currentIndexChanged.connect(self._on_lang_changed)
        lang_row.addWidget(self._lang_combo, 1)
        lang_row.addStretch()
        gg.addLayout(lang_row)

        root.addWidget(general_group)

        # ---- Download section ----
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

        # Save button
        save_row = QHBoxLayout()
        save_row.addStretch()
        save_btn = QPushButton(t("settings_save"))
        save_btn.setObjectName("accent_btn")
        save_btn.setFixedHeight(32)
        save_btn.clicked.connect(self._on_save)
        save_row.addWidget(save_btn)
        dg.addLayout(save_row)

        root.addWidget(dl_group)

        # ---- Cookie section ----
        cookie_group = QGroupBox(t("cookie_mgmt"))
        cg = QVBoxLayout(cookie_group)

        # Instagram
        ig_row = QHBoxLayout()
        ig_row.addWidget(QLabel("Instagram:"))
        self._ig_cookie_status = QLabel()
        self._update_ig_cookie_status()
        ig_row.addWidget(self._ig_cookie_status)
        ig_row.addStretch()
        cg.addLayout(ig_row)

        # X
        x_row = QHBoxLayout()
        x_row.addWidget(QLabel("X (Twitter):"))
        self._x_cookie_status = QLabel()
        self._update_x_cookie_status()
        x_row.addWidget(self._x_cookie_status)
        x_row.addStretch()
        cg.addLayout(x_row)

        # YouTube
        yt_row = QHBoxLayout()
        yt_row.addWidget(QLabel("YouTube:"))
        self._yt_cookie_status = QLabel()
        self._update_yt_cookie_status()
        yt_row.addWidget(self._yt_cookie_status)
        yt_row.addStretch()
        cg.addLayout(yt_row)

        import_row = QHBoxLayout()
        import_row.addStretch()
        self._import_btn = QPushButton(t("cookie_import"))
        self._import_btn.setObjectName("secondary")
        self._import_btn.clicked.connect(self._on_import_cookie)
        import_row.addWidget(self._import_btn)
        cg.addLayout(import_row)

        self._hint_label = QLabel("")
        self._hint_label.setObjectName("muted")
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cg.addWidget(self._hint_label)

        root.addWidget(cookie_group)

        # ---- About section ----
        about_group = QGroupBox("About")
        ag = QVBoxLayout(about_group)

        ver_row = QHBoxLayout()
        ver_row.addWidget(QLabel(t("settings_version") + ":"))
        ver_val = QLabel("1.5.0")
        ver_val.setObjectName("muted")
        ver_row.addWidget(ver_val)
        ver_row.addStretch()
        ag.addLayout(ver_row)

        root.addWidget(about_group)

        root.addStretch()

    # ---- Cookie status ----

    def _update_ig_cookie_status(self):
        from .cookie_checker import check_ig_cookie_status
        status = check_ig_cookie_status()
        if status == "已配置":
            self._ig_cookie_status.setText(t("cookie_valid"))
            self._ig_cookie_status.setStyleSheet("color: #10b981; font-weight: 600;")
        elif status == "已失效":
            self._ig_cookie_status.setText(t("cookie_expired"))
            self._ig_cookie_status.setStyleSheet("color: #f87171; font-weight: 600;")
        else:
            self._ig_cookie_status.setText(t("cookie_missing"))
            self._ig_cookie_status.setStyleSheet("color: #f87171; font-weight: 600;")

    def _update_x_cookie_status(self):
        from .cookie_checker import check_x_cookie_status
        status = check_x_cookie_status()
        if status == "已配置":
            self._x_cookie_status.setText(t("cookie_valid"))
            self._x_cookie_status.setStyleSheet("color: #10b981; font-weight: 600;")
        elif status == "已失效":
            self._x_cookie_status.setText(t("cookie_expired"))
            self._x_cookie_status.setStyleSheet("color: #f87171; font-weight: 600;")
        else:
            self._x_cookie_status.setText(t("cookie_missing"))
            self._x_cookie_status.setStyleSheet("color: #f87171; font-weight: 600;")

    def _update_yt_cookie_status(self):
        from .cookie_checker import check_yt_cookie_status
        status = check_yt_cookie_status()
        if status == "已配置":
            self._yt_cookie_status.setText(t("cookie_valid"))
            self._yt_cookie_status.setStyleSheet("color: #10b981; font-weight: 600;")
        elif status == "已失效":
            self._yt_cookie_status.setText(t("cookie_expired"))
            self._yt_cookie_status.setStyleSheet("color: #f87171; font-weight: 600;")
        else:
            self._yt_cookie_status.setText(t("cookie_missing"))
            self._yt_cookie_status.setStyleSheet("color: #f87171; font-weight: 600;")

    # ---- Actions ----

    def _on_save(self):
        cfg = load_config()
        cfg["max_concurrent"] = self._concurrent_spin.value()
        cfg["max_retries"] = self._retry_spin.value()
        save_config(cfg)
        self._hint_label.setText(t("settings_saved"))
        self._hint_label.setStyleSheet("color: #10b981;")

    @Slot()
    def _on_import_cookie(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t("cookie_import"), "",
            "Cookie Files (*.txt);;All Files (*)",
        )
        if not path:
            return
        try:
            cfg = load_config()
            dest = Path(cfg["cookie_file"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)

            from .cookie_checker import check_ig_cookie_status, check_x_cookie_status
            ig_status = check_ig_cookie_status()
            x_status = check_x_cookie_status()
            if ig_status == "已配置" or x_status == "已配置":
                self._hint_label.setText(t("cookie_imported"))
                self._hint_label.setStyleSheet("color: #10b981;")
            elif ig_status == "已失效" or x_status == "已失效":
                self._hint_label.setText(f"{t('cookie_imported')} — {t('cookie_expired')}")
                self._hint_label.setStyleSheet("color: #fbbf24;")
            else:
                self._hint_label.setText(t("cookie_imported"))
                self._hint_label.setStyleSheet("color: #10b981;")
            self._update_ig_cookie_status()
            self._update_x_cookie_status()
            self._update_yt_cookie_status()
        except Exception as e:
            QMessageBox.critical(self, t("error"), t("cookie_import_fail", err=str(e)))

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
            self.restart_requested.emit()

    def refresh_cookie_status(self):
        self._update_ig_cookie_status()
        self._update_x_cookie_status()
        self._update_yt_cookie_status()
