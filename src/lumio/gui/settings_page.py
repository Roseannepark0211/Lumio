from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..i18n import get_lang, set_lang, t
from ..utils.config import get_download_dir, load_config, save_config
from .widgets import NoWheelComboBox


class SettingsPage(QWidget):
    restart_requested = Signal()
    saved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settings_page")
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("settings_content")
        inner = QVBoxLayout(content)
        inner.setContentsMargins(32, 24, 32, 24)
        inner.setSpacing(20)

        # Title
        title = QLabel(t("settings"))
        title.setObjectName("page_title")
        inner.addWidget(title)

        # ---- General section ----
        general_group = QGroupBox(t("settings_general"))
        gg = QVBoxLayout(general_group)

        # Language
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel(t("language") + ":"))
        self._lang_combo = NoWheelComboBox()
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

        inner.addWidget(general_group)

        # ---- Download section ----
        dl_group = QGroupBox(t("download_settings"))
        dl_inner = QVBoxLayout(dl_group)
        dl_inner.setSpacing(0)

        cfg = load_config()

        # --- A: 并发 + 重试 ---
        ab_row = QHBoxLayout()
        ab_row.setSpacing(24)

        ab_row.addWidget(QLabel(t("max_concurrent") + ":"))
        self._concurrent_spin = QSpinBox()
        self._concurrent_spin.setRange(1, 10)
        self._concurrent_spin.setValue(cfg.get("max_concurrent", 3))
        self._concurrent_spin.setFixedWidth(64)
        ab_row.addWidget(self._concurrent_spin)

        ab_row.addSpacing(12)
        ab_row.addWidget(QLabel(t("max_retries") + ":"))
        self._retry_spin = QSpinBox()
        self._retry_spin.setRange(0, 10)
        self._retry_spin.setValue(cfg.get("max_retries", 3))
        self._retry_spin.setFixedWidth(64)
        ab_row.addWidget(self._retry_spin)

        ab_row.addStretch()
        dl_inner.addLayout(ab_row)
        dl_inner.addSpacing(20)

        # --- B: 存储模式 ---
        dl_inner.addWidget(QLabel(t("storage_mode") + ":"))
        dl_inner.addSpacing(6)

        self._mode_group = QButtonGroup(self)
        self._simple_radio = QRadioButton()  # no text — label separate
        self._organized_radio = QRadioButton()
        self._mode_group.addButton(self._simple_radio, 0)
        self._mode_group.addButton(self._organized_radio, 1)
        current_mode = cfg.get("storage_mode", "simple")
        if current_mode == "organized":
            self._organized_radio.setChecked(True)
        else:
            self._simple_radio.setChecked(True)

        mode_col = QVBoxLayout()
        mode_col.setSpacing(2)
        mode_col.setContentsMargins(8, 0, 0, 0)

        simple_row = QHBoxLayout()
        simple_row.setSpacing(6)
        simple_row.addWidget(self._simple_radio)
        simple_lbl = QLabel(t("storage_simple"))
        simple_lbl.setObjectName("muted")
        simple_row.addWidget(simple_lbl)
        simple_row.addStretch()
        mode_col.addLayout(simple_row)

        organized_row = QHBoxLayout()
        organized_row.setSpacing(6)
        organized_row.addWidget(self._organized_radio)
        organized_lbl = QLabel(t("storage_organized"))
        organized_lbl.setObjectName("muted")
        organized_row.addWidget(organized_lbl)
        organized_row.addStretch()
        mode_col.addLayout(organized_row)

        dl_inner.addLayout(mode_col)
        dl_inner.addSpacing(4)

        sm_desc = QLabel()
        sm_desc.setObjectName("muted")
        sm_desc.setWordWrap(True)
        self._simple_radio.toggled.connect(
            lambda on: sm_desc.setText(t("storage_simple_desc") if on else t("storage_organized_desc"))
        )
        sm_desc.setText(t("storage_simple_desc") if current_mode != "organized" else t("storage_organized_desc"))
        dl_inner.addWidget(sm_desc)
        dl_inner.addSpacing(20)

        # --- C: 文件冲突策略 ---
        cp_row = QHBoxLayout()
        cp_row.setSpacing(12)
        cp_row.addWidget(QLabel(t("file_conflict_policy") + ":"))
        self._conflict_combo = NoWheelComboBox()
        self._conflict_combo.addItem(t("conflict_rename"), "rename")
        self._conflict_combo.addItem(t("conflict_skip"), "skip")
        self._conflict_combo.addItem(t("conflict_overwrite"), "overwrite")
        self._conflict_combo.addItem(t("conflict_ask"), "ask")
        current_policy = cfg.get("file_conflict_policy", "rename")
        idx = self._conflict_combo.findData(current_policy)
        if idx >= 0:
            self._conflict_combo.setCurrentIndex(idx)
        self._conflict_combo.setFixedWidth(280)
        cp_row.addWidget(self._conflict_combo)
        cp_row.addStretch()
        dl_inner.addLayout(cp_row)
        dl_inner.addSpacing(4)

        cp_desc = QLabel(t("file_conflict_policy_desc"))
        cp_desc.setObjectName("muted")
        cp_desc.setWordWrap(True)
        dl_inner.addWidget(cp_desc)
        dl_inner.addSpacing(20)

        # --- D: 默认下载目录 ---
        dl_inner.addWidget(QLabel(t("default_download_dir") + ":"))
        dl_inner.addSpacing(6)

        self._dir_label = QLabel(str(get_download_dir()))
        self._dir_label.setObjectName("muted")
        self._dir_label.setWordWrap(True)
        dl_inner.addWidget(self._dir_label)
        dl_inner.addSpacing(10)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.setContentsMargins(0, 0, 0, 0)
        browse_btn = QPushButton(t("browse"))
        browse_btn.setObjectName("secondary")
        browse_btn.setMinimumWidth(90)
        browse_btn.clicked.connect(self._on_browse_dir)
        btn_row.addWidget(browse_btn)
        restore_btn = QPushButton(t("restore_default"))
        restore_btn.setObjectName("secondary")
        restore_btn.setMinimumWidth(90)
        restore_btn.clicked.connect(self._on_restore_dir)
        btn_row.addWidget(restore_btn)
        open_btn = QPushButton(t("open_folder"))
        open_btn.setObjectName("secondary")
        open_btn.setMinimumWidth(90)
        open_btn.clicked.connect(self._on_open_dir)
        btn_row.addWidget(open_btn)
        btn_row.addStretch()
        save_btn = QPushButton(t("settings_save"))
        save_btn.setObjectName("accent_btn")
        save_btn.setFixedHeight(32)
        save_btn.setMinimumWidth(120)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)
        dl_inner.addLayout(btn_row)

        inner.addWidget(dl_group)

        # ---- Cookie section ----
        cookie_group = QGroupBox(t("cookie_mgmt"))
        cg = QVBoxLayout(cookie_group)

        # Instagram
        ig_row = QHBoxLayout()
        ig_row.addWidget(QLabel("Instagram:"))
        self._ig_cookie_status = QLabel()
        self._ig_cookie_status.setMinimumWidth(150)
        self._ig_cookie_status.setContentsMargins(4, 0, 4, 0)
        self._update_ig_cookie_status()
        ig_row.addWidget(self._ig_cookie_status)
        ig_row.addStretch()
        cg.addLayout(ig_row)

        # X
        x_row = QHBoxLayout()
        x_row.addWidget(QLabel("X (Twitter):"))
        self._x_cookie_status = QLabel()
        self._x_cookie_status.setMinimumWidth(150)
        self._x_cookie_status.setContentsMargins(4, 0, 4, 0)
        self._update_x_cookie_status()
        x_row.addWidget(self._x_cookie_status)
        x_row.addStretch()
        cg.addLayout(x_row)

        # YouTube
        yt_row = QHBoxLayout()
        yt_row.addWidget(QLabel("YouTube:"))
        self._yt_cookie_status = QLabel()
        self._yt_cookie_status.setMinimumWidth(150)
        self._yt_cookie_status.setContentsMargins(4, 0, 4, 0)
        self._update_yt_cookie_status()
        yt_row.addWidget(self._yt_cookie_status)
        yt_row.addStretch()
        cg.addLayout(yt_row)

        import_row = QHBoxLayout()
        import_row.addStretch()
        check_btn = QPushButton(t("cookie_check"))
        check_btn.setObjectName("secondary")
        check_btn.clicked.connect(self._on_check_cookies)
        import_row.addWidget(check_btn)
        self._import_btn = QPushButton(t("cookie_import"))
        self._import_btn.setObjectName("secondary")
        self._import_btn.clicked.connect(self._on_import_cookie)
        import_row.addWidget(self._import_btn)
        cg.addLayout(import_row)

        self._hint_label = QLabel("")
        self._hint_label.setObjectName("muted")
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cg.addWidget(self._hint_label)

        inner.addWidget(cookie_group)

        # ---- About section ----
        about_group = QGroupBox("About")
        ag = QVBoxLayout(about_group)

        ver_row = QHBoxLayout()
        ver_row.addWidget(QLabel(t("settings_version") + ":"))
        from .. import __version__
        ver_val = QLabel(__version__)
        ver_val.setObjectName("muted")
        ver_row.addWidget(ver_val)
        ver_row.addStretch()
        ag.addLayout(ver_row)

        inner.addWidget(about_group)

        inner.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

    # ---- Cookie status ----

    def _set_cookie_label(self, label: QLabel, status: str):
        if status == "valid":
            label.setText(f"🟢 {t('cookie_valid')}")
            label.setObjectName("cookie_ok")
        elif status == "warning":
            label.setText(f"🟡 {t('cookie_warning')}")
            label.setObjectName("cookie_expired")
        elif status == "expired":
            label.setText(f"🔴 {t('cookie_expired')}")
            label.setObjectName("cookie_missing")
        else:
            label.setText(f"🔴 {t('cookie_missing')}")
            label.setObjectName("cookie_missing")
        label.style().unpolish(label)
        label.style().polish(label)

    def _update_ig_cookie_status(self):
        from .cookie_checker import check_ig_cookie_status
        self._set_cookie_label(self._ig_cookie_status, check_ig_cookie_status())

    def _update_x_cookie_status(self):
        from .cookie_checker import check_x_cookie_status
        self._set_cookie_label(self._x_cookie_status, check_x_cookie_status())

    def _update_yt_cookie_status(self):
        from .cookie_checker import check_yt_cookie_status
        self._set_cookie_label(self._yt_cookie_status, check_yt_cookie_status())

    def _on_check_cookies(self):
        self._update_ig_cookie_status()
        self._update_x_cookie_status()
        self._update_yt_cookie_status()
        self._hint_label.setText(t("cookie_check_done"))

    # ---- Actions ----

    def _on_save(self):
        cfg = load_config()
        cfg["max_concurrent"] = self._concurrent_spin.value()
        cfg["max_retries"] = self._retry_spin.value()
        cfg["storage_mode"] = "organized" if self._organized_radio.isChecked() else "simple"
        cfg["file_conflict_policy"] = self._conflict_combo.currentData()
        save_config(cfg)
        self._hint_label.setText(t("settings_saved"))
        self.saved.emit()

    def _on_browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, t("default_download_dir"), str(get_download_dir()))
        if d:
            cfg = load_config()
            cfg["download_dir"] = d
            save_config(cfg)
            self._dir_label.setText(d)

    def _on_restore_dir(self):
        default = str(Path.home() / "Downloads" / "Lumio")
        cfg = load_config()
        cfg["download_dir"] = default
        save_config(cfg)
        self._dir_label.setText(default)

    def _on_open_dir(self):
        import os
        p = str(get_download_dir())
        os.makedirs(p, exist_ok=True)
        os.startfile(p)

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
            cookie_file = cfg.get("cookie_file") or str(Path.home() / ".lumio" / "cookies.txt")
            dest = Path(cookie_file)
            dest.parent.mkdir(parents=True, exist_ok=True)

            # Merge: read existing + new, deduplicate by (domain, name)
            def _parse_cookies(filepath: Path) -> dict[tuple[str, str], str]:
                """Parse Netscape cookie file → {(domain, name): line}."""
                cookies = {}
                if filepath.exists():
                    for line in filepath.read_text(encoding="utf-8", errors="replace").splitlines():
                        line = line.rstrip("\n")
                        if not line or line.startswith("#"):
                            continue
                        parts = line.split("\t")
                        if len(parts) >= 6:
                            key = (parts[0], parts[5])
                            cookies[key] = line
                return cookies

            existing = _parse_cookies(dest)
            new = _parse_cookies(Path(path))
            existing.update(new)  # new cookies override existing with same (domain, name)

            # Preserve header comments from source file
            header_lines = []
            src_text = Path(path).read_text(encoding="utf-8", errors="replace")
            for line in src_text.splitlines():
                if line.startswith("#"):
                    header_lines.append(line)
                else:
                    break

            merged = "\n".join(header_lines + list(existing.values())) + "\n"
            dest.write_text(merged, encoding="utf-8")

            from .cookie_checker import check_ig_cookie_status, check_x_cookie_status
            ig_status = check_ig_cookie_status()
            x_status = check_x_cookie_status()
            if ig_status == "valid" or x_status == "valid":
                self._hint_label.setText(t("cookie_imported"))
            elif ig_status == "expired" or x_status == "expired":
                self._hint_label.setText(f"{t('cookie_imported')} — {t('cookie_expired')}")
            else:
                self._hint_label.setText(t("cookie_imported"))
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
