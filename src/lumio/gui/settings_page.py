from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QClipboard
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
from ..telegram_service import TelegramService
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
        self._build_general_group(inner)

        # ---- Download section ----
        self._build_download_group(inner)

        # ---- Platform Credentials section ----
        self._build_cred_group(inner)

        # ---- Telegram section ----
        self._build_tg_group(inner)

        # ---- About section ----
        self._build_about_group(inner)

        inner.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

    def _build_general_group(self, inner):
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


    def _build_download_group(self, inner):
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

        # --- E: 自动下载采集内容 ---
        self._auto_dl_check = QCheckBox(t("auto_download_inbox"))
        self._auto_dl_check.setChecked(cfg.get("auto_download_inbox", False))
        dl_inner.addWidget(self._auto_dl_check)
        auto_dl_desc = QLabel(t("auto_download_inbox_desc"))
        auto_dl_desc.setObjectName("muted")
        auto_dl_desc.setWordWrap(True)
        auto_dl_desc.setContentsMargins(24, 0, 0, 0)
        dl_inner.addWidget(auto_dl_desc)
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


    def _build_cred_group(self, inner):
        # ---- Platform Credentials section ----
        cred_group = QGroupBox(t("platform_credentials"))
        cg = QVBoxLayout(cred_group)
        cg.setSpacing(14)

        cfg_cred = load_config()

        # Helper to build a platform credential block
        def _add_platform_block(
            label: str,
            platform_key: str,
            has_api: bool,
            cookie_hint: str,
            cookie_check_fn: str,
        ):
            # Header row: platform name + mode selector
            header = QHBoxLayout()
            name_lbl = QLabel(label)
            name_lbl.setMinimumWidth(110)
            header.addWidget(name_lbl)
            header.addStretch()

            mode_combo = NoWheelComboBox()
            mode_combo.addItem(t("mode_cookie"), "cookie")
            if has_api:
                mode_combo.addItem(t("mode_api"), "api")
            else:
                mode_combo.addItem(t("mode_api_soon"), "api")
                mode_combo.model().item(1).setEnabled(False)
            # Restore saved mode
            saved_mode = cfg_cred.get(f"{platform_key}_mode", "cookie")
            idx = mode_combo.findData(saved_mode)
            if idx >= 0:
                mode_combo.setCurrentIndex(idx)
            header.addWidget(mode_combo)
            cg.addLayout(header)

            # Cookie panel
            cookie_panel = QWidget()
            cp_layout = QVBoxLayout(cookie_panel)
            cp_layout.setContentsMargins(16, 4, 0, 4)
            cp_layout.setSpacing(6)

            status_row = QHBoxLayout()
            status_lbl = QLabel()
            status_lbl.setMinimumWidth(150)
            status_lbl.setContentsMargins(4, 0, 4, 0)
            status_row.addWidget(status_lbl)
            status_row.addStretch()

            import_btn = QPushButton(t("cookie_import"))
            import_btn.setObjectName("secondary")
            import_btn.setFixedHeight(28)
            status_row.addWidget(import_btn)
            reset_btn = QPushButton(t("cookie_reset"))
            reset_btn.setObjectName("secondary")
            reset_btn.setFixedHeight(28)
            status_row.addWidget(reset_btn)
            cp_layout.addLayout(status_row)

            hint = QLabel(cookie_hint)
            hint.setObjectName("muted")
            hint.setContentsMargins(4, 0, 0, 0)
            cp_layout.addWidget(hint)

            cg.addWidget(cookie_panel)

            # API panel
            api_panel = QWidget()
            ap_layout = QVBoxLayout(api_panel)
            ap_layout.setContentsMargins(16, 4, 0, 4)
            ap_layout.setSpacing(8)

            if has_api:
                # Token input
                token_row = QHBoxLayout()
                token_row.addWidget(QLabel(f"{t('apify_token')}:"))
                token_input = QLineEdit()
                token_input.setEchoMode(QLineEdit.EchoMode.Password)
                token_input.setPlaceholderText("apify_api_...")
                token_input.setText(cfg_cred.get("apify_token", ""))
                token_row.addWidget(token_input, 1)
                ap_layout.addLayout(token_row)

                # Actor ID input
                actor_row = QHBoxLayout()
                actor_row.addWidget(QLabel(f"{t('apify_actor_id')}:"))
                actor_input = QLineEdit()
                actor_input.setPlaceholderText("shu8hvrXbJbY3Eb9W")
                actor_input.setText(cfg_cred.get("apify_ig_actor", ""))
                actor_row.addWidget(actor_input, 1)
                ap_layout.addLayout(actor_row)

                # Validate button + status
                val_row = QHBoxLayout()
                val_row.addStretch()
                conn_status = QLabel()
                conn_status.setObjectName("muted")
                val_row.addWidget(conn_status)
                val_btn = QPushButton(t("apify_validate"))
                val_btn.setFixedHeight(28)
                val_row.addWidget(val_btn)
                ap_layout.addLayout(val_row)
            else:
                coming = QLabel(t("mode_api_soon"))
                coming.setObjectName("muted")
                coming.setAlignment(Qt.AlignmentFlag.AlignCenter)
                ap_layout.addWidget(coming)

            api_panel.setVisible(saved_mode == "api")
            cookie_panel.setVisible(saved_mode != "api")
            cg.addWidget(api_panel)

            # Wire mode switch
            def _on_mode_changed(idx, cp=cookie_panel, ap=api_panel):
                mode = mode_combo.currentData()
                cp.setVisible(mode == "cookie")
                ap.setVisible(mode == "api")

            mode_combo.currentIndexChanged.connect(_on_mode_changed)

            return {
                "mode_combo": mode_combo,
                "status_lbl": status_lbl,
                "import_btn": import_btn,
                "reset_btn": reset_btn,
                "cookie_panel": cookie_panel,
                "api_panel": api_panel,
                "token_input": token_input if has_api else None,
                "actor_input": actor_input if has_api else None,
                "val_btn": val_btn if has_api else None,
                "conn_status": "conn_status" if has_api else None,
            }

        self._ig_cred = _add_platform_block(
            "Instagram:", "instagram", True,
            t("ig_cookie_hint"), "check_ig_cookie_status",
        )
        self._x_cred = _add_platform_block(
            "X (Twitter):", "x", False,
            t("x_cookie_hint"), "check_x_cookie_status",
        )
        self._yt_cred = _add_platform_block(
            "YouTube:", "yt", False,
            t("yt_cookie_hint"), "check_yt_cookie_status",
        )
        self._wb_cred = _add_platform_block(
            "微博 (Weibo):", "weibo", False,
            t("weibo_cookie_hint"), "check_weibo_cookie_status",
        )

        # Wire cookie status updates + import
        self._update_ig_cookie_status()
        self._update_x_cookie_status()
        self._update_yt_cookie_status()
        self._update_wb_cookie_status()
        self._ig_cred["import_btn"].clicked.connect(self._on_import_cookie)
        self._x_cred["import_btn"].clicked.connect(self._on_import_cookie)
        self._yt_cred["import_btn"].clicked.connect(self._on_import_cookie)
        self._wb_cred["import_btn"].clicked.connect(self._on_import_cookie)
        self._ig_cred["reset_btn"].clicked.connect(lambda: self._on_reset_cookie("instagram"))
        self._x_cred["reset_btn"].clicked.connect(lambda: self._on_reset_cookie("x"))
        self._yt_cred["reset_btn"].clicked.connect(lambda: self._on_reset_cookie("youtube"))
        self._wb_cred["reset_btn"].clicked.connect(lambda: self._on_reset_cookie("weibo"))

        # Wire IG API validation
        def _on_validate_apify():
            from ..utils.config import get_apify_token
            token = self._ig_cred["token_input"].text().strip()
            actor_id = self._ig_cred["actor_input"].text().strip()
            if not token:
                self._ig_cred_val_status.setText(f"⚠ {t('apify_token_empty')}")
                return
            if not actor_id:
                self._ig_cred_val_status.setText(f"⚠ {t('apify_actor_empty')}")
                return
            self._ig_cred["val_btn"].setEnabled(False)
            self._ig_cred_val_status.setText(f"⏳ {t('apify_validating')}")

            def _do():
                try:
                    # Temporarily save token so client can read it
                    cfg_tmp = load_config()
                    cfg_tmp["apify_token"] = token
                    cfg_tmp["apify_ig_actor"] = actor_id
                    save_config(cfg_tmp)
                    from ..apify_client import ApifyIGClient
                    client = ApifyIGClient(token, actor_id)
                    ok = client.test_connection()
                    self._ig_cred["val_btn"].setEnabled(True)
                    if ok:
                        self._ig_cred_val_status.setText(f"✅ {t('apify_connected')}")
                    else:
                        self._ig_cred_val_status.setText(f"❌ {t('apify_validate_fail')}")
                except Exception:
                    self._ig_cred["val_btn"].setEnabled(True)
                    self._ig_cred_val_status.setText(f"❌ {t('apify_validate_fail')}")

            import threading
            threading.Thread(target=_do, daemon=True).start()

        self._ig_cred_val_status = self._ig_cred["conn_status"]
        self._ig_cred["val_btn"].clicked.connect(_on_validate_apify)

        # Check all button
        check_row = QHBoxLayout()
        check_row.addStretch()
        check_btn = QPushButton(t("cookie_check"))
        check_btn.setObjectName("secondary")
        check_btn.clicked.connect(self._on_check_cookies)
        check_row.addWidget(check_btn)
        cg.addLayout(check_row)

        self._hint_label = QLabel("")
        self._hint_label.setObjectName("muted")
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cg.addWidget(self._hint_label)

        inner.addWidget(cred_group)


    def _build_tg_group(self, inner):
        # ---- Telegram section ----
        tg_group = QGroupBox(t("telegram_integration"))
        tg_outer = QVBoxLayout(tg_group)
        tg_outer.setSpacing(12)
        tg_outer.setContentsMargins(16, 16, 16, 16)

        cfg_tg = load_config()

        # Row 1: Enable toggle
        self._tg_enable = QCheckBox(t("telegram_enable"))
        self._tg_enable.setChecked(cfg_tg.get("telegram_enabled", False))
        self._tg_enable.stateChanged.connect(self._on_tg_toggle)
        tg_outer.addWidget(self._tg_enable)

        # Collapsible content
        self._tg_content = QWidget()
        tg_inner = QVBoxLayout(self._tg_content)
        tg_inner.setContentsMargins(20, 8, 0, 4)
        tg_inner.setSpacing(12)

        # Bot Token
        token_row = QHBoxLayout()
        token_row.setSpacing(8)
        token_row.addWidget(QLabel(t("telegram_bot_token") + ":"))
        self._tg_token_input = QLineEdit()
        self._tg_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._tg_token_input.setPlaceholderText("123456:ABC-DEF...")
        self._tg_token_input.setText(cfg_tg.get("telegram_bot_token", ""))
        token_row.addWidget(self._tg_token_input, 1)
        self._tg_validate_btn = QPushButton(t("telegram_validate"))
        self._tg_validate_btn.setFixedHeight(28)
        self._tg_validate_btn.clicked.connect(self._on_tg_validate)
        token_row.addWidget(self._tg_validate_btn)
        tg_inner.addLayout(token_row)

        # API Base URL (optional, for local Bot API server)
        api_row = QHBoxLayout()
        api_row.setSpacing(8)
        api_row.addWidget(QLabel(t("telegram_api_base") + ":"))
        self._tg_api_input = QLineEdit()
        self._tg_api_input.setPlaceholderText("https://api.telegram.org")
        self._tg_api_input.setText(cfg_tg.get("telegram_api_base", "https://api.telegram.org"))
        api_row.addWidget(self._tg_api_input, 1)
        tg_inner.addLayout(api_row)

        api_hint = QLabel(t("telegram_api_base_hint"))
        api_hint.setObjectName("muted")
        api_hint.setWordWrap(True)
        tg_inner.addWidget(api_hint)

        # Connection status
        self._tg_status = QLabel()
        self._tg_status.setObjectName("muted")
        tg_inner.addWidget(self._tg_status)

        # Pair code area (visible when token valid + not bound)
        self._tg_pair_area = QWidget()
        pair_v = QVBoxLayout(self._tg_pair_area)
        pair_v.setContentsMargins(0, 0, 0, 0)
        pair_v.setSpacing(4)

        pair_row1 = QHBoxLayout()
        pair_row1.setSpacing(8)
        pair_row1.addWidget(QLabel(t("telegram_pair_code") + ":"))
        self._tg_pair_code = QLabel()
        self._tg_pair_code.setStyleSheet("font-size: 16px; font-weight: bold; color: #4A9EFF;")
        pair_row1.addWidget(self._tg_pair_code)
        self._tg_copy_btn = QPushButton(t("telegram_copy"))
        self._tg_copy_btn.setStyleSheet("QPushButton { background:none; border:none; color:#4A9EFF; } QPushButton:hover { text-decoration:underline; }")
        self._tg_copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tg_copy_btn.clicked.connect(self._on_tg_copy)
        pair_row1.addWidget(self._tg_copy_btn)
        self._tg_regen_btn = QPushButton(t("telegram_regen"))
        self._tg_regen_btn.setFixedHeight(26)
        self._tg_regen_btn.clicked.connect(self._on_tg_regen)
        pair_row1.addWidget(self._tg_regen_btn)
        pair_row1.addStretch()
        pair_v.addLayout(pair_row1)

        self._tg_pair_hint = QLabel(t("telegram_pair_hint"))
        self._tg_pair_hint.setObjectName("muted")
        self._tg_pair_hint.setWordWrap(True)
        pair_v.addWidget(self._tg_pair_hint)

        tg_inner.addWidget(self._tg_pair_area)

        # Bound device area (visible when bound)
        self._tg_bound_area = QWidget()
        bound_v = QVBoxLayout(self._tg_bound_area)
        bound_v.setContentsMargins(0, 4, 0, 4)
        bound_v.setSpacing(8)

        self._tg_bound_label = QLabel()
        self._tg_bound_label.setStyleSheet("font-size: 13px;")
        bound_v.addWidget(self._tg_bound_label)

        bound_row = QHBoxLayout()
        bound_row.setSpacing(12)
        self._tg_unlink_btn = QPushButton(t("telegram_unlink"))
        self._tg_unlink_btn.setFixedHeight(28)
        self._tg_unlink_btn.setObjectName("secondary")
        self._tg_unlink_btn.clicked.connect(self._on_tg_unlink)
        bound_row.addWidget(self._tg_unlink_btn)
        bound_row.addStretch()
        bound_v.addLayout(bound_row)

        tg_inner.addWidget(self._tg_bound_area)

        tg_outer.addWidget(self._tg_content)

        # Initial state
        self._tg_content.setVisible(cfg_tg.get("telegram_enabled", False))
        self._tg_refresh_state()

        inner.addWidget(tg_group)


    def _build_about_group(self, inner):
        # ---- About section ----
        about_group = QGroupBox("About")
        ag = QVBoxLayout(about_group)

        ver_row = QHBoxLayout()
        ver_row.addWidget(QLabel(t("settings_version") + ":"))
        from .. import __version__
        ver_val = QLabel(__version__)
        ver_val.setObjectName("muted")
        ver_row.addWidget(ver_val)
        ver_row.addSpacing(12)

        self._update_btn = QPushButton(t("check_update"))
        self._update_btn.setObjectName("secondary")
        self._update_btn.setFixedHeight(28)
        self._update_btn.clicked.connect(self._on_check_update)
        ver_row.addWidget(self._update_btn)

        self._update_result = QLabel()
        self._update_result.setObjectName("muted")
        ver_row.addWidget(self._update_result)

        ver_row.addStretch()
        ag.addLayout(ver_row)

        inner.addWidget(about_group)



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
        self._set_cookie_label(self._ig_cred["status_lbl"], check_ig_cookie_status())

    def _update_x_cookie_status(self):
        from .cookie_checker import check_x_cookie_status
        self._set_cookie_label(self._x_cred["status_lbl"], check_x_cookie_status())

    def _update_yt_cookie_status(self):
        from .cookie_checker import check_yt_cookie_status
        self._set_cookie_label(self._yt_cred["status_lbl"], check_yt_cookie_status())

    def _update_wb_cookie_status(self):
        from .cookie_checker import check_weibo_cookie_status
        self._set_cookie_label(self._wb_cred["status_lbl"], check_weibo_cookie_status())

    def _on_check_cookies(self):
        self._update_ig_cookie_status()
        self._update_x_cookie_status()
        self._update_yt_cookie_status()
        self._update_wb_cookie_status()
        self._hint_label.setText(t("cookie_check_done"))

    # ---- Actions ----

    def _on_save(self):
        cfg = load_config()
        cfg["max_concurrent"] = self._concurrent_spin.value()
        cfg["max_retries"] = self._retry_spin.value()
        cfg["storage_mode"] = "organized" if self._organized_radio.isChecked() else "simple"
        cfg["file_conflict_policy"] = self._conflict_combo.currentData()
        cfg["auto_download_inbox"] = self._auto_dl_check.isChecked()
        cfg["telegram_enabled"] = self._tg_enable.isChecked()
        cfg["telegram_bot_token"] = self._tg_token_input.text().strip()
        cfg["telegram_api_base"] = self._tg_api_input.text().strip() or "https://api.telegram.org"
        # Platform credentials
        cfg["instagram_mode"] = self._ig_cred["mode_combo"].currentData() or "cookie"
        cfg["x_mode"] = self._x_cred["mode_combo"].currentData() or "cookie"
        cfg["youtube_mode"] = self._yt_cred["mode_combo"].currentData() or "cookie"
        cfg["weibo_mode"] = self._wb_cred["mode_combo"].currentData() or "cookie"
        old_token = cfg.get("apify_token", "")
        new_token = self._ig_cred["token_input"].text().strip() if self._ig_cred["token_input"] else ""
        cfg["apify_token"] = new_token
        cfg["apify_ig_actor"] = self._ig_cred["actor_input"].text().strip()
        save_config(cfg)
        # Reset cached Apify client if token or actor changed
        if old_token != new_token:
            try:
                from ..downloader import reset_apify_client
                reset_apify_client()
            except Exception:
                pass
        self._hint_label.setText(t("settings_saved"))
        self.saved.emit()

    def _on_check_update(self):
        self._update_btn.setEnabled(False)
        self._update_result.setText(t("update_checking"))
        from ..notification_manager import Notification, NotificationManager
        from .. import __version__
        import threading

        def _check():
            mgr = NotificationManager()
            result = mgr.check_version()
            self._update_btn.setEnabled(True)
            if result == "latest":
                self._update_result.setText(f"✅ {t('update_latest')}")
                self._update_result.setStyleSheet("color: #4ADE80;")
            elif result.startswith("new:"):
                ver = result.split(":", 1)[1]
                self._update_result.setText(f"🆕 {t('update_found', ver=ver)}")
                self._update_result.setStyleSheet("color: #FFB84D;")
                # 同时写入通知
                mgr.add_notification(Notification(
                    category="update", type="update",
                    title=f"发现新版本 v{ver}",
                    message=f"当前版本 v{__version__}，最新版本 v{ver}",
                    action="open_url:https://github.com/Roseannepark0211/Lumio/releases",
                    action_text="前往下载",
                    source_key=f"update_{ver}",
                ))
            else:
                err = result.split(":", 1)[1] if ":" in result else result
                self._update_result.setText(f"⚠ {t('update_error', err=err)}")
                self._update_result.setStyleSheet("color: #888;")

        threading.Thread(target=_check, daemon=True).start()

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
    def _on_reset_cookie(self, platform: str = ""):
        from pathlib import Path as _Path
        from ..utils.config import load_config as _lc
        cfg = _lc()
        cookie_file = cfg.get("cookie_file") or str(_Path.home() / ".lumio" / "cookies.txt")
        p = _Path(cookie_file)
        if not p.exists():
            self._hint_label.setText(t("cookie_reset_done"))
            return

        # Platform → domain substrings to match in cookie file
        domain_map = {
            "instagram": ["instagram.com"],
            "x": ["x.com", "twitter.com"],
            "youtube": ["youtube.com"],
            "weibo": ["weibo.cn", "weibo.com"],
        }
        domains = domain_map.get(platform, [])
        if not domains:
            return

        lines = p.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        kept = []
        for line in lines:
            # Keep header/comment lines and lines not matching target domains
            if line.startswith("#") or not line.strip():
                kept.append(line)
                continue
            parts = line.split("\t")
            if len(parts) >= 1 and any(d in parts[0] for d in domains):
                continue  # skip this platform's cookies
            kept.append(line)

        if kept:
            p.write_text("".join(kept), encoding="utf-8")
        else:
            p.unlink()

        self._update_ig_cookie_status()
        self._update_x_cookie_status()
        self._update_yt_cookie_status()
        self._update_wb_cookie_status()
        self._hint_label.setText(t("cookie_reset_done"))

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

            from .cookie_checker import check_ig_cookie_status, check_x_cookie_status, check_weibo_cookie_status
            ig_status = check_ig_cookie_status()
            x_status = check_x_cookie_status()
            wb_status = check_weibo_cookie_status()
            if ig_status == "valid" or x_status == "valid" or wb_status == "valid":
                self._hint_label.setText(t("cookie_imported"))
            elif ig_status == "expired" or x_status == "expired" or wb_status == "expired":
                self._hint_label.setText(f"{t('cookie_imported')} — {t('cookie_expired')}")
            else:
                self._hint_label.setText(t("cookie_imported"))
            self._update_ig_cookie_status()
            self._update_x_cookie_status()
            self._update_yt_cookie_status()
            self._update_wb_cookie_status()
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
        self._update_wb_cookie_status()

    # ---- Telegram handlers ----

    def _on_tg_toggle(self, state):
        enabled = state == 2  # Qt.CheckState.Checked
        self._tg_content.setVisible(enabled)
        cfg = load_config()
        cfg["telegram_enabled"] = enabled
        cfg["telegram_bot_token"] = self._tg_token_input.text().strip()
        save_config(cfg)
        # 自动启停同步
        app = QApplication.instance()
        tg_svc = getattr(app, '_lumio_tg_service', None)
        if enabled:
            token = cfg.get("telegram_bot_token", "")
            if token:
                inbox_mgr = getattr(app, '_lumio_inbox_manager', None)
                if inbox_mgr:
                    if not tg_svc:
                        from ..telegram_service import TelegramService
                        tg_svc = TelegramService(inbox_mgr)
                        app._lumio_tg_service = tg_svc
                    # item_added 信号已由 InboxManager 连接到 inbox_page
                    if not tg_svc.is_running:
                        tg_svc.start_polling()
        else:
            if tg_svc and tg_svc.is_running:
                tg_svc.stop_polling()

    def _on_tg_validate(self):
        token = self._tg_token_input.text().strip()
        if not token:
            self._tg_status.setText("❌ " + t("telegram_token_empty"))
            return
        self._tg_validate_btn.setEnabled(False)
        self._tg_status.setText(t("telegram_validating"))

        import threading
        from PySide6.QtCore import QTimer

        def _check():
            result = TelegramService.validate_token(token)
            # UI 更新回到主线程
            def _update_ui():
                self._tg_validate_btn.setEnabled(True)
                if result["ok"]:
                    self._tg_status.setText(f"🟢 @{result['username']} — {t('telegram_connected')}")
                    self._tg_status.setStyleSheet("color: #4ADE80;")
                    cfg = load_config()
                    cfg["telegram_bot_token"] = token
                    save_config(cfg)
                    self._tg_generate_pair_code()
                    self._tg_refresh_state()
                    # 自动启动轮询
                    self._auto_start_tg_service()
                else:
                    self._tg_status.setText(f"🔴 {t('telegram_validate_fail')}: {result['error']}")
                    self._tg_status.setStyleSheet("color: #FF6B6B;")
            QTimer.singleShot(0, _update_ui)

        threading.Thread(target=_check, daemon=True).start()

    def _tg_generate_pair_code(self):
        cfg = load_config()
        if cfg.get("telegram_pair_code"):
            return  # 已有配对码，不重新生成
        self._on_tg_regen()

    def _auto_start_tg_service(self):
        """自动启动 Telegram 轮询服务。"""
        app = QApplication.instance()
        tg_svc = getattr(app, '_lumio_tg_service', None)
        inbox_mgr = getattr(app, '_lumio_inbox_manager', None)
        if not inbox_mgr:
            return
        if not tg_svc:
            tg_svc = TelegramService(inbox_mgr)
            app._lumio_tg_service = tg_svc
        # item_added 信号已由 InboxManager 连接到 inbox_page
        if not tg_svc.is_running:
            tg_svc.start_polling()

    def _on_tg_regen(self):
        svc = TelegramService(inbox_manager=None)
        code = svc.generate_pair_code()
        self._tg_pair_code.setText(code)
        self._tg_pair_hint.setText(t("telegram_pair_hint"))

    def _on_tg_copy(self):
        code = self._tg_pair_code.text()
        if code and code != "—":
            QApplication.clipboard().setText(code)
            self._tg_copy_btn.setText("✅ " + t("telegram_copied"))
            self._tg_copy_btn.setStyleSheet("QPushButton { background: none; border: none; color: #4ADE80; font-size: 13px; }")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(1500, self._tg_reset_copy_btn)

    def _tg_reset_copy_btn(self):
        self._tg_copy_btn.setText(t("telegram_copy"))
        self._tg_copy_btn.setStyleSheet("QPushButton { background: none; border: none; color: #4A9EFF; font-size: 13px; } QPushButton:hover { text-decoration: underline; }")

    def _tg_update_status(self):
        cfg = load_config()
        token = cfg.get("telegram_bot_token", "")
        if not token:
            self._tg_status.setText(t("telegram_no_token"))
            self._tg_status.setStyleSheet("color: #888;")
        else:
            self._tg_status.setText(t("telegram_token_saved"))
            self._tg_status.setStyleSheet("color: #888;")

    def _tg_update_pair_code(self):
        cfg = load_config()
        code = cfg.get("telegram_pair_code", "")
        if code:
            self._tg_pair_code.setText(code)
            self._tg_pair_hint.setText(t("telegram_pair_hint"))
        else:
            self._tg_pair_code.setText("—")
            self._tg_pair_hint.setText("")

    def _tg_refresh_state(self):
        """统一刷新 Telegram 区域可见性。"""
        cfg = load_config()
        token = cfg.get("telegram_bot_token", "")
        code = cfg.get("telegram_pair_code", "")

        # Status
        if not token:
            self._tg_status.setText(t("telegram_no_token"))
            self._tg_status.setStyleSheet("color: #888;")
        else:
            self._tg_status.setText(t("telegram_token_saved"))
            self._tg_status.setStyleSheet("color: #888;")

        # Pair code: token 有效时始终显示
        if token:
            self._tg_pair_area.setVisible(True)
            self._tg_pair_code.setText(code if code else "—")
            self._tg_pair_hint.setText(t("telegram_pair_hint"))
        else:
            self._tg_pair_area.setVisible(False)

        # Bound device
        svc = TelegramService(inbox_manager=None)
        device = svc.get_bound_device()
        if device:
            self._tg_bound_area.setVisible(True)
            self._tg_bound_label.setText(
                f"✅ {t('telegram_bound')} @{device.telegram_username or 'unknown'}（ID: {device.telegram_user_id}）"
            )
        else:
            self._tg_bound_area.setVisible(False)

    def _on_tg_unlink(self):
        svc = TelegramService(inbox_manager=None)
        device = svc.get_bound_device()
        if device:
            svc.unlink_device(device.telegram_user_id)
            self._tg_refresh_state()
