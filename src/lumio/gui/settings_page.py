from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QClipboard
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..i18n import get_lang, set_lang, t
from ..utils.config import get_download_dir, load_config, save_config
from ..telegram_service import TelegramService
from .widgets import NoWheelComboBox


class _CacheCleanWorker(QThread):
    """后台执行缓存清理，避免阻塞 UI。"""
    progress = Signal(str, int, int)  # (dir_name, deleted, total)
    finished_ok = Signal(dict)        # results: {dir: {freed, deleted, total, remaining}}
    failed = Signal(str)              # error message

    def __init__(self, retain_days: int, max_size_mb: int, force: bool = False):
        super().__init__()
        self._retain_days = retain_days
        self._max_size_mb = max_size_mb
        self._force = force

    def run(self):
        try:
            from ..utils.cache_manager import clean_all_caches
            results = clean_all_caches(
                retain_days=self._retain_days,
                max_size_mb=self._max_size_mb,
                progress_cb=lambda name, deleted, total: self.progress.emit(name, deleted, total),
                force=self._force,
            )
            self.finished_ok.emit(results)
        except Exception as e:
            self.failed.emit(str(e))


class _TgValidateWorker(QThread):
    """后台验证 Telegram Bot Token。

    用 QThread + Signal 替代 threading + QTimer.singleShot，
    确保跨线程 UI 更新在 PySide6 事件循环中正确触发。
    finished 信号携带 {"ok": bool, "username": str} 或 {"ok": False, "error": str}。
    """
    finished = Signal(dict)

    def __init__(self, token: str, proxy: str, api_base: str, parent=None):
        super().__init__(parent)
        self._token = token
        self._proxy = proxy
        self._api_base = api_base

    def run(self):
        try:
            from ..telegram_service import TelegramService
            result = TelegramService.validate_token(self._token, proxy=self._proxy)
        except Exception as e:
            result = {"ok": False, "error": str(e)}
        self.finished.emit(result)


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

        # ---- Cache Management section ----
        self._build_cache_group(inner)

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
            # ===== 折叠头（QToolButton + 箭头） =====
            toggle_btn = QToolButton()
            toggle_btn.setText(label)
            toggle_btn.setCheckable(True)
            toggle_btn.setArrowType(Qt.ArrowType.RightArrow)
            toggle_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            toggle_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            toggle_btn.setStyleSheet(
                "QToolButton { border: none; text-align: left; "
                "font-weight: 600; padding: 6px 2px; }"
                "QToolButton:hover { color: #5b8cff; }"
            )
            cg.addWidget(toggle_btn)

            # ===== 内容容器（包裹模式选择器 + cookie + api 面板） =====
            content = QWidget()
            cl = QVBoxLayout(content)
            cl.setContentsMargins(16, 2, 0, 6)
            cl.setSpacing(6)

            # Header row: mode selector
            header = QHBoxLayout()
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
            header.addWidget(QLabel(t("credential_mode_label")))
            header.addWidget(mode_combo)
            header.addStretch()
            cl.addLayout(header)

            # Cookie panel
            cookie_panel = QWidget()
            cp_layout = QVBoxLayout(cookie_panel)
            cp_layout.setContentsMargins(0, 4, 0, 4)
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

            cl.addWidget(cookie_panel)

            # API panel
            api_panel = QWidget()
            ap_layout = QVBoxLayout(api_panel)
            ap_layout.setContentsMargins(0, 4, 0, 4)
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
            cl.addWidget(api_panel)

            # 默认折叠；若已配置 cookie 或处于 api 模式则默认展开
            cookie_configured = bool(cfg_cred.get(f"{platform_key}_cookie"))
            default_expanded = cookie_configured or saved_mode == "api"
            content.setVisible(default_expanded)
            toggle_btn.setChecked(default_expanded)
            if default_expanded:
                toggle_btn.setArrowType(Qt.ArrowType.DownArrow)

            def _on_toggle(checked, b=toggle_btn, c=content):
                c.setVisible(checked)
                b.setArrowType(
                    Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
                )
            toggle_btn.toggled.connect(_on_toggle)

            cg.addWidget(content)

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
        self._dy_cred = _add_platform_block(
            "抖音 (Douyin):", "douyin", False,
            t("douyin_cookie_hint"), "check_douyin_cookie_status",
        )
        self._xhs_cred = _add_platform_block(
            "小红书 (Xiaohongshu):", "xiaohongshu", False,
            t("xiaohongshu_cookie_hint"), "check_xiaohongshu_cookie_status",
        )
        self._bili_cred = _add_platform_block(
            "Bilibili:", "bilibili", False,
            t("bilibili_cookie_hint"), "check_bilibili_cookie_status",
        )
        self._ks_cred = _add_platform_block(
            "快手 (Kuaishou):", "kuaishou", False,
            t("kuaishou_cookie_hint"), "check_kuaishou_cookie_status",
        )
 
        # Wire cookie status updates + import
        self._update_ig_cookie_status()
        self._update_x_cookie_status()
        self._update_yt_cookie_status()
        self._update_wb_cookie_status()
        self._update_dy_cookie_status()
        self._update_xhs_cookie_status()
        self._update_bili_cookie_status()
        self._update_ks_cookie_status()
        self._ig_cred["import_btn"].clicked.connect(self._on_import_cookie)
        self._x_cred["import_btn"].clicked.connect(self._on_import_cookie)
        self._yt_cred["import_btn"].clicked.connect(self._on_import_cookie)
        self._wb_cred["import_btn"].clicked.connect(self._on_import_cookie)
        self._dy_cred["import_btn"].clicked.connect(self._on_import_cookie)
        self._xhs_cred["import_btn"].clicked.connect(self._on_import_cookie)
        self._bili_cred["import_btn"].clicked.connect(self._on_import_cookie)
        self._ks_cred["import_btn"].clicked.connect(self._on_import_cookie)
        self._ig_cred["reset_btn"].clicked.connect(lambda: self._on_reset_cookie("instagram"))
        self._x_cred["reset_btn"].clicked.connect(lambda: self._on_reset_cookie("x"))
        self._yt_cred["reset_btn"].clicked.connect(lambda: self._on_reset_cookie("youtube"))
        self._wb_cred["reset_btn"].clicked.connect(lambda: self._on_reset_cookie("weibo"))
        self._dy_cred["reset_btn"].clicked.connect(lambda: self._on_reset_cookie("douyin"))
        self._xhs_cred["reset_btn"].clicked.connect(lambda: self._on_reset_cookie("xiaohongshu"))
        self._bili_cred["reset_btn"].clicked.connect(lambda: self._on_reset_cookie("bilibili"))
        self._ks_cred["reset_btn"].clicked.connect(lambda: self._on_reset_cookie("kuaishou"))

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


    def _build_cache_group(self, inner):
        """缓存管理分组：统计 + 立即清理 + 自动清理配置。"""
        from ..utils.cache_manager import get_cache_stats

        cache_group = QGroupBox(t("settings_cache"))
        cg = QVBoxLayout(cache_group)
        cg.setSpacing(12)

        cfg = load_config()
        cm = cfg.get("cache_management", {})
        if not isinstance(cm, dict):
            cm = {}

        # === A. 缓存统计 ===
        self._cache_stats = get_cache_stats()
        stats_box = QGroupBox(t("cache_total_size"))
        sb = QFormLayout(stats_box)
        sb.setSpacing(4)

        total = self._cache_stats.get("_total", {})
        self._cache_total_lbl = QLabel(
            f"{total.get('size_mb', 0):.2f} MB  ·  {total.get('file_count', 0)} {t('cache_file_count')}"
        )
        self._cache_total_lbl.setObjectName("muted")
        sb.addRow("", self._cache_total_lbl)

        # 各子目录（仅可清理的缓存）+ 路径显示
        self._cache_dir_lbls: dict[str, QLabel] = {}
        self._cache_path_lbls: dict[str, QLabel] = {}
        from pathlib import Path as _P
        from ..utils.cache_manager import _CACHE_DIRS as _ALL_CACHE_DIRS
        for key, label_key in [
            ("thumbs", "cache_thumbs"),
            ("provider_cache", "cache_provider_cache"),
            ("preview", "cache_preview"),
            ("inbox_media", "cache_inbox_media"),
        ]:
            info = self._cache_stats.get(key, {})
            lbl = QLabel(
                f"{t(label_key)}: {info.get('size_mb', 0):.2f} MB  ·  {info.get('file_count', 0)} {t('cache_file_count')}"
            )
            lbl.setObjectName("muted")
            lbl.setContentsMargins(16, 0, 0, 0)
            # inbox_media 智能清理提示
            if key == "inbox_media":
                note = QLabel(f"  ({t('cache_inbox_smart_clean')})")
                note.setObjectName("muted")
                row = QHBoxLayout()
                row.setContentsMargins(0, 0, 0, 0)
                row.addWidget(lbl)
                row.addWidget(note)
                row.addStretch()
                container = QWidget()
                container.setLayout(row)
                sb.addRow("", container)
            else:
                sb.addRow("", lbl)
            self._cache_dir_lbls[key] = lbl

            # 路径显示（灰色小字）
            dir_path = _ALL_CACHE_DIRS.get(key)
            if dir_path:
                path_lbl = QLabel(str(dir_path))
                path_lbl.setObjectName("cache_path")
                path_lbl.setContentsMargins(32, 0, 0, 4)
                path_lbl.setWordWrap(False)
                path_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                self._cache_path_lbls[key] = path_lbl
                sb.addRow("", path_lbl)

        cg.addWidget(stats_box)

        # 立即清理按钮 + 状态
        clean_row = QHBoxLayout()
        clean_row.setSpacing(10)
        self._cache_clean_btn = QPushButton(t("cache_clean_now"))
        self._cache_clean_btn.setObjectName("secondary")
        self._cache_clean_btn.setFixedHeight(30)
        self._cache_clean_btn.setMinimumWidth(110)
        self._cache_clean_btn.clicked.connect(self._on_clean_cache_now)
        clean_row.addWidget(self._cache_clean_btn)

        self._cache_progress = QProgressBar()
        self._cache_progress.setFixedHeight(20)
        self._cache_progress.setRange(0, 100)
        self._cache_progress.hide()
        clean_row.addWidget(self._cache_progress, 1)

        self._cache_status_lbl = QLabel()
        self._cache_status_lbl.setObjectName("muted")
        clean_row.addWidget(self._cache_status_lbl)
        clean_row.addStretch()
        cg.addLayout(clean_row)

        # === B. 自动清理配置 ===
        cg.addSpacing(4)
        auto_row = QHBoxLayout()
        auto_row.setSpacing(12)
        auto_row.addWidget(QLabel(t("cache_auto_clean") + ":"))
        self._cache_auto_combo = NoWheelComboBox()
        self._cache_auto_combo.addItem(t("cache_auto_off"), "off")
        self._cache_auto_combo.addItem(t("cache_auto_startup"), "startup")
        self._cache_auto_combo.addItem(t("cache_auto_daily"), "daily")
        self._cache_auto_combo.addItem(t("cache_auto_weekly"), "weekly")
        cur_mode = cm.get("auto_clean", "off")
        idx = self._cache_auto_combo.findData(cur_mode)
        if idx >= 0:
            self._cache_auto_combo.setCurrentIndex(idx)
        self._cache_auto_combo.setFixedWidth(160)
        auto_row.addWidget(self._cache_auto_combo)
        auto_row.addStretch()
        cg.addLayout(auto_row)

        # 保留天数 + 上限
        param_row = QHBoxLayout()
        param_row.setSpacing(24)
        param_row.addWidget(QLabel(t("cache_retain_days") + ":"))
        self._cache_retain_spin = QSpinBox()
        self._cache_retain_spin.setRange(1, 365)
        self._cache_retain_spin.setValue(cm.get("retain_days", 7))
        self._cache_retain_spin.setFixedWidth(80)
        self._cache_retain_spin.setSuffix(" d")
        param_row.addWidget(self._cache_retain_spin)

        param_row.addSpacing(12)
        param_row.addWidget(QLabel(t("cache_max_size") + ":"))
        self._cache_maxsize_spin = QSpinBox()
        self._cache_maxsize_spin.setRange(50, 10000)
        self._cache_maxsize_spin.setValue(cm.get("max_size_mb", 500))
        self._cache_maxsize_spin.setFixedWidth(100)
        self._cache_maxsize_spin.setSuffix(" MB")
        param_row.addWidget(self._cache_maxsize_spin)
        param_row.addStretch()
        cg.addLayout(param_row)

        # 上次清理时间
        last_str = cm.get("last_cleaned", "")
        if last_str:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(last_str)
                last_display = dt.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                last_display = t("cache_never")
        else:
            last_display = t("cache_never")
        self._cache_last_lbl = QLabel(f"{t('cache_last_cleaned')}: {last_display}")
        self._cache_last_lbl.setObjectName("muted")
        cg.addWidget(self._cache_last_lbl)

        # 缓存清理 worker
        self._cache_worker: _CacheCleanWorker | None = None

        # 即时保存：控件变更时立即写入 config，无需点「保存设置」
        self._cache_auto_combo.currentIndexChanged.connect(self._save_cache_config)
        self._cache_retain_spin.valueChanged.connect(self._save_cache_config)
        self._cache_maxsize_spin.valueChanged.connect(self._save_cache_config)

        inner.addWidget(cache_group)

    def _save_cache_config(self):
        """缓存设置即时保存（不依赖下载设置的「保存设置」按钮）。"""
        if not hasattr(self, "_cache_auto_combo"):
            return  # 控件尚未创建
        cfg = load_config()
        old_cm = cfg.get("cache_management", {}) or {}
        cfg["cache_management"] = {
            "auto_clean": self._cache_auto_combo.currentData() or "off",
            "retain_days": self._cache_retain_spin.value(),
            "max_size_mb": self._cache_maxsize_spin.value(),
            "last_cleaned": old_cm.get("last_cleaned", ""),
        }
        save_config(cfg)



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

    def _update_dy_cookie_status(self):
        from .cookie_checker import check_douyin_cookie_status
        self._set_cookie_label(self._dy_cred["status_lbl"], check_douyin_cookie_status())

    def _update_xhs_cookie_status(self):
        from .cookie_checker import check_xiaohongshu_cookie_status
        self._set_cookie_label(self._xhs_cred["status_lbl"], check_xiaohongshu_cookie_status())

    def _update_bili_cookie_status(self):
        from .cookie_checker import check_bilibili_cookie_status
        self._set_cookie_label(self._bili_cred["status_lbl"], check_bilibili_cookie_status())

    def _update_ks_cookie_status(self):
        from .cookie_checker import check_kuaishou_cookie_status
        self._set_cookie_label(self._ks_cred["status_lbl"], check_kuaishou_cookie_status())

    def _on_check_cookies(self):
        self._update_ig_cookie_status()
        self._update_x_cookie_status()
        self._update_yt_cookie_status()
        self._update_wb_cookie_status()
        self._update_dy_cookie_status()
        self._update_xhs_cookie_status()
        self._update_bili_cookie_status()
        self._update_ks_cookie_status()
        self._hint_label.setText(t("cookie_check_done"))

    # ---- Actions ----

    def _on_save(self):
        cfg = load_config()
        cfg["max_concurrent"] = self._concurrent_spin.value()
        cfg["max_retries"] = self._retry_spin.value()
        cfg["storage_mode"] = "organized" if self._organized_radio.isChecked() else "simple"
        cfg["file_conflict_policy"] = self._conflict_combo.currentData()
        cfg["auto_download_inbox"] = self._auto_dl_check.isChecked()
        # 记录 telegram 配置变更，用于判断是否需要重启轮询
        old_tg_token = cfg.get("telegram_bot_token", "")
        old_tg_api_base = cfg.get("telegram_api_base", "https://api.telegram.org")
        cfg["telegram_enabled"] = self._tg_enable.isChecked()
        cfg["telegram_bot_token"] = self._tg_token_input.text().strip()
        cfg["telegram_api_base"] = self._tg_api_input.text().strip() or "https://api.telegram.org"
        # Platform credentials
        cfg["instagram_mode"] = self._ig_cred["mode_combo"].currentData() or "cookie"
        cfg["x_mode"] = self._x_cred["mode_combo"].currentData() or "cookie"
        cfg["youtube_mode"] = self._yt_cred["mode_combo"].currentData() or "cookie"
        cfg["weibo_mode"] = self._wb_cred["mode_combo"].currentData() or "cookie"
        cfg["douyin_mode"] = self._dy_cred["mode_combo"].currentData() or "cookie"
        cfg["xiaohongshu_mode"] = self._xhs_cred["mode_combo"].currentData() or "cookie"
        cfg["bilibili_mode"] = self._bili_cred["mode_combo"].currentData() or "cookie"
        cfg["kuaishou_mode"] = self._ks_cred["mode_combo"].currentData() or "cookie"
        old_token = cfg.get("apify_token", "")
        new_token = self._ig_cred["token_input"].text().strip() if self._ig_cred["token_input"] else ""
        cfg["apify_token"] = new_token
        cfg["apify_ig_actor"] = self._ig_cred["actor_input"].text().strip()
        # Cache management 由 _save_cache_config() 即时保存，这里不再重复处理
        save_config(cfg)
        # Reset cached Apify client if token or actor changed
        if old_token != new_token:
            try:
                from ..downloader import reset_apify_client
                reset_apify_client()
            except Exception:
                pass
        # Telegram: 若 token/api_base 变更或已启用但未运行，重启轮询让新配置立即生效
        tg_token_changed = old_tg_token != cfg["telegram_bot_token"]
        tg_api_changed = old_tg_api_base != cfg["telegram_api_base"]
        if cfg.get("telegram_enabled") and cfg.get("telegram_bot_token"):
            if tg_token_changed or tg_api_changed:
                self._restart_tg_polling()
            else:
                # token 没变但可能 proxy 变了（_poll_loop 已支持热加载，这里仅确保运行）
                self._auto_start_tg_service()
        self._hint_label.setText(t("settings_saved"))
        self.saved.emit()

    def _restart_tg_polling(self):
        """重启 Telegram 轮询，让新 token/api_base/proxy 立即生效。"""
        app = QApplication.instance()
        tg_svc = getattr(app, '_lumio_tg_service', None)
        if tg_svc:
            tg_svc.restart_polling()
        else:
            self._auto_start_tg_service()

    def _on_check_update(self):
        self._update_btn.setEnabled(False)
        self._update_result.setText(t("update_checking"))
        from ..notification_manager import get_notification_manager
        from .. import __version__
        import threading

        def _check():
            # 修复双实例 bug：复用全局单例，不再 new NotificationManager()
            mgr = get_notification_manager()
            result = mgr.check_version_manual()
            self._update_btn.setEnabled(True)
            if result == "latest":
                self._update_result.setText(f"✅ {t('update_latest')}")
                self._update_result.setStyleSheet("color: #4ADE80;")
            elif result.startswith("new:"):
                ver = result.split(":", 1)[1]
                self._update_result.setText(f"🆕 {t('update_found', ver=ver)}")
                self._update_result.setStyleSheet("color: #FFB84D;")
                # 通知已由 check_version_manual() 内部添加，无需重复
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

    # ---- Cache management handlers ----

    def _on_clean_cache_now(self):
        """立即清理：弹出确认对话框（按规则清理 / 强制清空 / 取消），然后后台执行。"""
        if self._cache_worker and self._cache_worker.isRunning():
            return  # 已在清理中
        retain = self._cache_retain_spin.value()

        # 自定义确认对话框：三个按钮
        box = QMessageBox(self)
        box.setWindowTitle(t("cache_confirm_title"))
        box.setText(t("cache_confirm_msg", days=retain))
        box.setIcon(QMessageBox.Icon.Question)

        btn_rule = box.addButton(t("cache_clean_rule"), QMessageBox.ButtonRole.AcceptRole)
        btn_force = box.addButton(t("cache_clean_force"), QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = box.addButton(t("close"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(btn_rule)

        choice = box.exec()
        if box.clickedButton() is btn_cancel:
            return

        force = (box.clickedButton() is btn_force)
        # 强制清空需二次确认
        if force:
            confirm = QMessageBox.question(
                self, t("cache_confirm_title"),
                t("cache_force_confirm"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return

        # 启动 worker
        self._cache_clean_btn.setEnabled(False)
        self._cache_clean_btn.setText(t("cache_cleaning"))
        self._cache_progress.setRange(0, 0)  # indeterminate
        self._cache_progress.show()
        self._cache_status_lbl.setText(t("cache_clean_force_status") if force else "")

        self._cache_worker = _CacheCleanWorker(
            retain_days=retain,
            max_size_mb=self._cache_maxsize_spin.value(),
            force=force,
        )
        self._cache_worker.progress.connect(self._on_cache_clean_progress)
        self._cache_worker.finished_ok.connect(self._on_cache_clean_done)
        self._cache_worker.failed.connect(self._on_cache_clean_failed)
        # 记录本次模式供完成回调使用
        self._cache_clean_force = force
        self._cache_worker.start()

    @Slot(str, int, int)
    def _on_cache_clean_progress(self, dir_name: str, deleted: int, total: int):
        """清理进度回调。"""
        from ..i18n import t as _t
        label_map = {
            "thumbs": "cache_thumbs",
            "provider_cache": "cache_provider_cache",
            "preview": "cache_preview",
        }
        label = _t(label_map.get(dir_name, dir_name))
        self._cache_status_lbl.setText(f"{label}: {deleted}/{total}")

    @Slot(dict)
    def _on_cache_clean_done(self, results: dict):
        """清理完成：显示详细前后对比。"""
        self._cache_clean_btn.setEnabled(True)
        self._cache_clean_btn.setText(t("cache_clean_now"))
        self._cache_progress.hide()

        # 更新 last_cleaned
        from datetime import datetime
        cfg = load_config()
        cm = cfg.get("cache_management", {}) or {}
        cm["last_cleaned"] = datetime.now().isoformat()
        cfg["cache_management"] = cm
        save_config(cfg)

        # 刷新统计
        self._refresh_cache_stats()

        # 汇总：删除文件数 / 释放空间 / 剩余空间
        total_deleted = sum(r.get("deleted", 0) for r in results.values())
        total_freed = sum(r.get("freed", 0) for r in results.values())
        total_remaining = sum(r.get("remaining", 0) for r in results.values())

        def _fmt_size(b: int) -> str:
            mb = b / 1024 / 1024
            if mb >= 1:
                return f"{mb:.2f} MB"
            return f"{b / 1024:.1f} KB"

        # 构造详细结果文本
        from ..i18n import t as _t
        label_map = {
            "thumbs": "cache_thumbs",
            "provider_cache": "cache_provider_cache",
            "preview": "cache_preview",
        }
        lines = [_t("cache_result_header")]
        for name, r in results.items():
            label = _t(label_map.get(name, name))
            lines.append(
                f"  • {label}: {r.get('deleted', 0)}/{r.get('total', 0)} "
                f"{_t('cache_file_count')}, {_fmt_size(r.get('freed', 0))}"
            )
        lines.append("")
        lines.append(f"{_t('cache_result_total')}: {total_deleted} {_t('cache_file_count')}, "
                     f"{_fmt_size(total_freed)}")
        lines.append(f"{_t('cache_result_remaining')}: {_fmt_size(total_remaining)}")
        detail = "\n".join(lines)

        # 状态栏简要提示
        self._cache_status_lbl.setText(
            _t("cache_cleaned", size=_fmt_size(total_freed)) +
            f"  ·  {total_deleted} {_t('cache_file_count')}"
        )

        # 弹出详细结果对话框（让用户看到清理效果）
        QMessageBox.information(self, t("settings_cache"), detail)

        # 更新上次清理时间显示
        self._cache_last_lbl.setText(
            f"{t('cache_last_cleaned')}: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

    @Slot(str)
    def _on_cache_clean_failed(self, err: str):
        """清理失败。"""
        self._cache_clean_btn.setEnabled(True)
        self._cache_clean_btn.setText(t("cache_clean_now"))
        self._cache_progress.hide()
        self._cache_status_lbl.setText(f"❌ {t('cache_clean_failed')}: {err}")

    def _refresh_cache_stats(self):
        """重新获取缓存统计并更新 UI 标签。"""
        from ..utils.cache_manager import get_cache_stats
        self._cache_stats = get_cache_stats()
        total = self._cache_stats.get("_total", {})
        self._cache_total_lbl.setText(
            f"{total.get('size_mb', 0):.2f} MB  ·  {total.get('file_count', 0)} {t('cache_file_count')}"
        )
        for key, label_key in [
            ("thumbs", "cache_thumbs"),
            ("provider_cache", "cache_provider_cache"),
            ("preview", "cache_preview"),
        ]:
            info = self._cache_stats.get(key, {})
            lbl = self._cache_dir_lbls.get(key)
            if lbl:
                lbl.setText(
                    f"{t(label_key)}: {info.get('size_mb', 0):.2f} MB  ·  {info.get('file_count', 0)} {t('cache_file_count')}"
                )

    def refresh_cache_ui(self):
        """供外部调用刷新缓存统计（如切换页面时）。"""
        if hasattr(self, "_cache_total_lbl"):
            self._refresh_cache_stats()

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
            "douyin": ["douyin.com"],
            "xiaohongshu": ["xiaohongshu.com", "xhslink.com"],
            "bilibili": ["bilibili.com", "b23.tv"],
            "kuaishou": ["kuaishou.com"],
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
        self._update_dy_cookie_status()
        self._update_xhs_cookie_status()
        self._update_bili_cookie_status()
        self._update_ks_cookie_status()
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

            from .cookie_checker import (
                check_ig_cookie_status, check_x_cookie_status, check_weibo_cookie_status,
                check_douyin_cookie_status, check_xiaohongshu_cookie_status,
                check_bilibili_cookie_status, check_kuaishou_cookie_status,
            )
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
            self._update_dy_cookie_status()
            self._update_xhs_cookie_status()
            self._update_bili_cookie_status()
            self._update_ks_cookie_status()
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
        self._update_dy_cookie_status()
        self._update_xhs_cookie_status()
        self._update_bili_cookie_status()
        self._update_ks_cookie_status()

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
        self._tg_validating = True  # 标记验证进行中，防止 _tg_apply_validate_result 重复触发

        # 从 config 读取代理（中国大陆访问 api.telegram.org 必需）
        cfg = load_config()
        proxy = cfg.get("http_proxy", "")
        api_base = cfg.get("telegram_api_base", "https://api.telegram.org").rstrip("/")

        # 用 QThread + Signal 替代 threading + QTimer.singleShot
        # 这是 PySide6 跨线程 UI 更新的标准做法，避免事件循环阻塞问题
        self._tg_validate_worker = _TgValidateWorker(token, proxy, api_base, self)
        self._tg_validate_worker.finished.connect(
            lambda result: self._tg_apply_validate_result(result, token, proxy)
        )
        self._tg_validate_worker.start()

        # Watchdog：15 秒后若线程仍未完成，强制恢复 UI 并提示
        from PySide6.QtCore import QTimer

        def _watchdog():
            if self._tg_validate_worker.isRunning():
                err = f"验证超时（15s）。代理: {proxy or '未配置'}，API: {api_base}"
                self._tg_validate_worker.terminate()
                self._tg_apply_validate_result({"ok": False, "error": err}, token, proxy)

        QTimer.singleShot(15000, _watchdog)

    def _tg_apply_validate_result(self, result: dict, token: str, proxy: str):
        """应用验证结果到 UI（必须在主线程调用）。"""
        # 防止重复触发（watchdog + 线程完成可能都调用）
        if not getattr(self, "_tg_validating", False):
            return
        self._tg_validating = False
        self._tg_validate_btn.setEnabled(True)
        if result.get("ok"):
            self._tg_status.setText(f"🟢 @{result.get('username','')} — {t('telegram_connected')}")
            self._tg_status.setStyleSheet("color: #4ADE80;")
            cfg2 = load_config()
            cfg2["telegram_bot_token"] = token
            save_config(cfg2)
            self._tg_generate_pair_code()
            self._tg_refresh_state()
            # 自动启动轮询
            self._auto_start_tg_service()
        else:
            err = result.get('error', '')
            # 友好提示：常见错误附加代理状态
            if proxy and ('proxy' in err.lower() or 'connection' in err.lower() or 'timeout' in err.lower() or 'ssl' in err.lower()):
                err = f"{err}（代理: {proxy}）"
            elif not proxy and ('connection' in err.lower() or 'timeout' in err.lower() or 'ssl' in err.lower()):
                err = f"{err}（未配置代理，中国大陆需在 config.json 设置 http_proxy）"
            self._tg_status.setText(f"🔴 {t('telegram_validate_fail')}: {err}")
            self._tg_status.setStyleSheet("color: #FF6B6B;")

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
