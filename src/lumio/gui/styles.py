"""Lumio QSS 样式表生成器

基于 theme/tokens.py 中的设计 Token 生成 QSS，Dark/Light 共享同一份模板。
根治原项目两大顽疾：
1. 「YouTube 三套蓝打架」（#3B5BDB / #FF0000 / #2563eb）—— 所有平台色统一来自 tokens.PLATFORM_COLORS
2. 「深浅两份 QSS 手动镜像同步」—— 现在只需维护一份模板，主题切换走 Token 替换

兼容性策略：
- 保留旧 objectName（nav_btn / task_card / badge_downloading / platform_yt 等），
  现有页面无需改动即可在新样式下工作
- 同时新增 Liquid Glass 专属 objectName（glass_card / lg_btn / lg_badge 等），
  新页面用新名，便于后续清理

切换主题时调用 `get_stylesheet(theme)` 返回完整 QSS 字符串。
"""
from __future__ import annotations

from .theme import tokens as T
from .theme.tokens import (
    FONT_BODY, FONT_DISPLAY, FONT_MONO,
    FS_DISPLAY, FS_H1, FS_H2, FS_H3, FS_BODY, FS_SMALL, FS_MICRO,
    R_PILL, R_XL, R_LG, R_MD, R_SM, R_XS,
    EASE,
    PLATFORM_COLORS,
    STATUS_SUCCESS, STATUS_WARNING, STATUS_DANGER, STATUS_INFO,
    get_tokens,
)


def _platform_badge_qss(theme_tokens: dict) -> str:
    """生成所有平台徽章的 QSS 规则。

    平台色单一来源：全部来自 tokens.PLATFORM_COLORS。
    根治原项目 YouTube 三套蓝问题：所有 YouTube 徽章统一用 #ff3b5c。
    """
    text = theme_tokens["text_primary"]
    lines = []
    for plat, color in PLATFORM_COLORS.items():
        # 只生成主键（不生成 xhs 别名）
        if plat == "xhs":
            continue
        # 把颜色解析为 rgba 用于半透明背景
        h = color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        lines.append(f"""
QLabel#platform_{plat}, QLabel#badge_plat_{plat} {{
    background-color: rgba({r}, {g}, {b}, 0.15);
    color: {color};
    border: 1px solid rgba({r}, {g}, {b}, 0.35);
    font-size: {FS_MICRO}px;
    font-weight: 700;
    border-radius: {R_XS}px;
    padding: 2px 8px;
}}
QPushButton#pill_{plat} {{
    background-color: rgba({r}, {g}, {b}, 0.1);
    color: {color};
    border: 1px solid rgba({r}, {g}, {b}, 0.3);
    border-radius: {R_PILL}px;
    padding: 6px 14px;
    font-size: {FS_SMALL}px;
    font-weight: 600;
}}
QPushButton#pill_{plat}:hover {{
    background-color: rgba({r}, {g}, {b}, 0.18);
    border-color: {color};
}}""")
    return "\n".join(lines)


def _status_badge_qss(theme_tokens: dict) -> str:
    """生成 8 种下载状态徽章的 QSS。"""
    text = theme_tokens["text_primary"]
    return f"""
/* ---- Status Badges (Liquid Glass) ---- */
QLabel#badge_waiting {{
    background-color: rgba(255, 255, 255, 0.08);
    color: {theme_tokens['text_mute']};
    border: 1px solid {theme_tokens['glass_border']};
    font-size: {FS_MICRO}px;
    font-weight: 600;
    border-radius: {R_XS}px;
    padding: 2px 8px;
}}
QLabel#badge_downloading {{
    background-color: rgba(10, 132, 255, 0.15);
    color: {theme_tokens['accent']};
    border: 1px solid rgba(10, 132, 255, 0.35);
    font-size: {FS_MICRO}px;
    font-weight: 600;
    border-radius: {R_XS}px;
    padding: 2px 8px;
}}
QLabel#badge_paused, QLabel#badge_retrying {{
    background-color: rgba(255, 214, 10, 0.15);
    color: {STATUS_WARNING};
    border: 1px solid rgba(255, 214, 10, 0.35);
    font-size: {FS_MICRO}px;
    font-weight: 600;
    border-radius: {R_XS}px;
    padding: 2px 8px;
}}
QLabel#badge_interrupted {{
    background-color: rgba(94, 92, 230, 0.15);
    color: {theme_tokens['accent_2']};
    border: 1px solid rgba(94, 92, 230, 0.35);
    font-size: {FS_MICRO}px;
    font-weight: 600;
    border-radius: {R_XS}px;
    padding: 2px 8px;
}}
QLabel#badge_completed {{
    background-color: rgba(48, 209, 88, 0.15);
    color: {STATUS_SUCCESS};
    border: 1px solid rgba(48, 209, 88, 0.35);
    font-size: {FS_MICRO}px;
    font-weight: 600;
    border-radius: {R_XS}px;
    padding: 2px 8px;
}}
QLabel#badge_failed {{
    background-color: rgba(255, 69, 58, 0.15);
    color: {STATUS_DANGER};
    border: 1px solid rgba(255, 69, 58, 0.35);
    font-size: {FS_MICRO}px;
    font-weight: 600;
    border-radius: {R_XS}px;
    padding: 2px 8px;
}}
QLabel#badge_cancelled {{
    background-color: rgba(255, 255, 255, 0.05);
    color: {theme_tokens['text_dim']};
    border: 1px solid {theme_tokens['glass_border']};
    font-size: {FS_MICRO}px;
    font-weight: 600;
    border-radius: {R_XS}px;
    padding: 2px 8px;
}}
/* Media type badges */
QLabel#media_video {{
    background-color: rgba(10, 132, 255, 0.15);
    color: {theme_tokens['accent']};
    border: 1px solid rgba(10, 132, 255, 0.35);
    font-size: {FS_MICRO}px;
    font-weight: 700;
    border-radius: {R_XS}px;
    padding: 1px 6px;
}}
QLabel#media_audio {{
    background-color: rgba(48, 209, 88, 0.15);
    color: {STATUS_SUCCESS};
    border: 1px solid rgba(48, 209, 88, 0.35);
    font-size: {FS_MICRO}px;
    font-weight: 700;
    border-radius: {R_XS}px;
    padding: 1px 6px;
}}
QLabel#media_image {{
    background-color: rgba(255, 214, 10, 0.15);
    color: {STATUS_WARNING};
    border: 1px solid rgba(255, 214, 10, 0.35);
    font-size: {FS_MICRO}px;
    font-weight: 700;
    border-radius: {R_XS}px;
    padding: 1px 6px;
}}
QLabel#media_mixed {{
    background-color: rgba(94, 92, 230, 0.15);
    color: {theme_tokens['accent_2']};
    border: 1px solid rgba(94, 92, 230, 0.35);
    font-size: {FS_MICRO}px;
    font-weight: 700;
    border-radius: {R_XS}px;
    padding: 1px 6px;
}}
"""


def _build_qss(t: dict) -> str:
    """根据 Token dict 生成完整 QSS。Dark/Light 共用此模板。"""
    return f"""/* ============================================================
   LUMIO // LIQUID GLASS QSS — {t['bg_base']}
   由 styles.py 从 tokens 自动生成，勿手动修改
   ============================================================ */

/* ---- Global ---- */
QMainWindow, QWidget {{
    background-color: {t['bg_base']};
    color: {t['text_primary']};
    font-family: {FONT_BODY};
    font-size: {FS_BODY}px;
}}

QScrollArea > QWidget > QWidget {{
    background-color: {t['bg_base']};
}}

/* ---- Labels ---- */
QLabel {{
    color: {t['text_primary']};
    font-size: {FS_BODY}px;
    background: transparent;
}}

QLabel#accent, QLabel#section_title {{
    color: {t['accent']};
    font-size: {FS_H2}px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}

QLabel#muted {{
    color: {t['text_mute']};
    font-size: {FS_SMALL}px;
}}

QLabel#cache_path {{
    color: {t['text_dim']};
    font-size: {FS_MICRO}px;
    font-family: {FONT_MONO};
}}

QLabel#page_title {{
    color: {t['text_primary']};
    font-size: {FS_H1}px;
    font-weight: 700;
    background: transparent;
}}

QLabel#init_title {{
    color: {t['accent_2']};
    font-size: 28px;
    font-weight: 700;
    background: transparent;
}}

QLabel#section_header {{
    color: {t['text_mute']};
    font-size: {FS_MICRO}px;
    font-weight: 700;
    letter-spacing: 1px;
    background: transparent;
}}

QLabel#stat_label {{
    color: {t['text_mute']};
    font-size: {FS_SMALL}px;
    background: transparent;
}}

/* Stats page 数值标签 — color 由 QPalette 动态设置（每张卡片色值不同） */
QLabel#stat_value {{
    font-size: 28px;
    font-weight: 700;
    background: transparent;
}}

QLabel#toolbar_hint {{
    color: {t['text_dim']};
    font-size: {FS_MICRO}px;
    background: transparent;
}}

QLabel#url_link {{
    color: {t['accent']};
    font-size: {FS_MICRO}px;
}}

QLabel#batch_progress {{
    font-size: {FS_MICRO}px;
    margin-left: 4px;
    color: {t['text_mute']};
}}

QLabel#batch_progress_done {{
    font-size: {FS_MICRO}px;
    margin-left: 4px;
    color: {STATUS_SUCCESS};
}}

/* ---- Inputs ---- */
QLineEdit {{
    background-color: {t['input_bg']};
    color: {t['text_primary']};
    border: 1px solid {t['glass_border']};
    border-radius: {R_MD}px;
    padding: 9px 14px;
    font-size: {FS_BODY}px;
    font-family: {FONT_BODY};
    font-weight: 500;
    selection-background-color: {t['accent_soft']};
    min-height: 20px;
}}

QLineEdit:focus {{
    border: 1px solid {t['accent']};
    background-color: {t['input_bg_focus']};
}}

QLineEdit::placeholder {{
    color: {t['placeholder']};
}}

QTextEdit, QPlainTextEdit {{
    background-color: {t['input_bg']};
    color: {t['text_primary']};
    border: 1px solid {t['glass_border']};
    border-radius: {R_MD}px;
    padding: 10px 14px;
    font-size: {FS_BODY}px;
    font-family: {FONT_MONO};
    selection-background-color: {t['accent_soft']};
}}

QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {t['accent']};
}}

QSpinBox, QDoubleSpinBox {{
    background: {t['input_bg']};
    border: 1px solid {t['glass_border']};
    border-radius: {R_SM}px;
    color: {t['text_primary']};
    font-size: {FS_SMALL}px;
    padding: 4px 8px;
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {t['accent']};
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 16px;
    border: none;
    background: transparent;
}}

/* ---- ComboBox ---- */
QComboBox {{
    background-color: {t['input_bg']};
    color: {t['text_primary']};
    border: 1px solid {t['glass_border']};
    border-radius: {R_MD}px;
    padding: 8px 14px;
    font-size: {FS_BODY}px;
    font-weight: 500;
    min-height: 20px;
    min-width: 80px;
}}

QComboBox:hover {{
    border-color: {t['glass_border_hi']};
}}

QComboBox:focus {{
    border: 1px solid {t['accent']};
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {t['text_mute']};
    margin-right: 8px;
}}

QComboBox QAbstractItemView {{
    background-color: {t['card_bg']};
    color: {t['text_primary']};
    border: 1px solid {t['card_border']};
    border-radius: {R_SM}px;
    selection-background-color: {t['accent_soft']};
    selection-color: {t['text_primary']};
    padding: 4px;
    outline: none;
}}

/* ---- Buttons ---- */
QPushButton {{
    background-color: {t['glass_bg']};
    color: {t['text_mute']};
    border: 1px solid {t['glass_border']};
    border-radius: {R_SM}px;
    padding: 8px 14px;
    font-size: {FS_SMALL}px;
    font-weight: 600;
    font-family: {FONT_BODY};
    min-height: 20px;
}}

QPushButton:hover {{
    background-color: {t['glass_bg_hi']};
    color: {t['text_primary']};
    border-color: {t['glass_border_hi']};
}}

QPushButton:pressed {{
    background-color: {t['glass_bg_press']};
}}

QPushButton:disabled {{
    background-color: {t['glass_bg']};
    color: {t['text_dim']};
    border-color: {t['glass_border']};
}}

/* Primary button (accent blue, single source) */
QPushButton#accent_btn, QPushButton#lg_btn_primary {{
    background-color: {t['accent']};
    color: {t['text_on_accent']};
    border: 1px solid {t['accent']};
    border-radius: {R_SM}px;
    padding: 9px 18px;
    font-size: {FS_SMALL}px;
    font-weight: 700;
    min-width: 100px;
}}

QPushButton#accent_btn:hover, QPushButton#lg_btn_primary:hover {{
    background-color: {t['accent_press']};
    border-color: {t['accent_press']};
}}

QPushButton#accent_btn:pressed, QPushButton#lg_btn_primary:pressed {{
    background-color: {t['accent_press']};
}}

QPushButton#accent_btn:disabled, QPushButton#lg_btn_primary:disabled {{
    background-color: {t['glass_bg']};
    color: {t['text_dim']};
    border-color: {t['glass_border']};
}}

/* Secondary button (legacy name preserved) */
QPushButton#secondary, QPushButton#lg_btn_secondary {{
    background-color: {t['glass_bg']};
    color: {t['text_mute']};
    border: 1px solid {t['glass_border']};
    border-radius: {R_SM}px;
    font-weight: 500;
}}

QPushButton#secondary:hover, QPushButton#lg_btn_secondary:hover {{
    background-color: {t['glass_bg_hi']};
    color: {t['text_primary']};
    border-color: {t['glass_border_hi']};
}}

/* Danger button */
QPushButton#lg_btn_danger {{
    background-color: {t['glass_bg']};
    color: {STATUS_DANGER};
    border: 1px solid rgba(255, 69, 58, 0.3);
    border-radius: {R_SM}px;
    padding: 8px 14px;
    font-size: {FS_SMALL}px;
    font-weight: 600;
}}
QPushButton#lg_btn_danger:hover {{
    background-color: rgba(255, 69, 58, 0.12);
    border-color: {STATUS_DANGER};
}}

/* Icon button (square) */
QPushButton#lg_btn_icon {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: {R_SM}px;
    padding: 4px;
    min-width: 32px;
    min-height: 32px;
    max-width: 32px;
    max-height: 32px;
}}
QPushButton#lg_btn_icon:hover {{
    background-color: {t['glass_bg']};
    border-color: {t['glass_border']};
}}

/* Tool button (transparent, for toolbars) */
QPushButton#tool_btn {{
    background-color: transparent;
    color: {t['text_mute']};
    border: none;
    border-radius: {R_SM}px;
    padding: 6px 10px;
    font-size: {FS_SMALL}px;
}}
QPushButton#tool_btn:hover {{
    color: {t['text_primary']};
    background-color: {t['glass_bg']};
}}

/* Paste / Search buttons */
QPushButton#paste_btn, QPushButton#search_btn {{
    background-color: transparent;
    color: {t['text_mute']};
    border: 1px solid {t['glass_border']};
    border-radius: {R_MD}px;
    padding: 8px 16px;
    font-size: {FS_SMALL}px;
    font-weight: 600;
}}
QPushButton#paste_btn:hover, QPushButton#search_btn:hover {{
    color: {t['text_primary']};
    border-color: {t['accent']};
    background-color: {t['accent_soft']};
}}

/* ---- Progress Bar ---- */
QProgressBar {{
    background-color: rgba(0, 0, 0, 0.35);
    border: 1px solid {t['glass_border']};
    border-radius: {R_PILL}px;
    text-align: center;
    color: {t['text_primary']};
    font-size: {FS_MICRO}px;
    font-weight: 600;
    min-height: 6px;
    max-height: 14px;
}}

QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {t['accent_2']}, stop:0.5 {t['accent']}, stop:1 #4cc2ff);
    border-radius: {R_PILL}px;
}}

/* ---- Group Box (Card style) ---- */
QGroupBox {{
    background-color: {t['group_bg']};
    border: 1px solid {t['group_border']};
    border-radius: {R_LG}px;
    margin-top: 0px;
    padding: 20px 18px 16px 18px;
    font-size: {FS_SMALL}px;
    font-weight: 600;
    color: {t['text_mute']};
    min-width: 0;
}}

QGroupBox::title {{
    subcontrol-origin: padding;
    subcontrol-position: top left;
    left: 18px;
    top: 6px;
    padding: 0 8px;
    color: {t['text_mute']};
    font-size: {FS_SMALL}px;
    font-weight: 600;
    letter-spacing: 0.5px;
    background-color: {t['group_bg']};
}}

/* ---- ScrollBar ---- */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {t['glass_border']};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {t['glass_border_hi']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {t['glass_border']};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {t['glass_border_hi']};
}}

/* ---- Tooltip ---- */
QToolTip {{
    background-color: {t['card_bg']};
    color: {t['text_primary']};
    border: 1px solid {t['card_border']};
    border-radius: {R_SM}px;
    padding: 6px 10px;
    font-size: {FS_SMALL}px;
}}

/* ---- Dialog ---- */
QDialog {{
    background-color: {t['bg_base']};
}}

QMessageBox {{
    background-color: {t['card_bg']};
}}

QMessageBox QLabel {{
    color: {t['text_primary']};
    font-size: {FS_BODY}px;
    background: transparent;
}}

QMessageBox QPushButton {{
    min-width: 80px;
    min-height: 30px;
}}

/* ============================================================
   SIDEBAR (Liquid Glass)
   ============================================================ */
QFrame#sidebar {{
    background-color: {t['sidebar_bg']};
    border-right: 1px solid {t['glass_border']};
}}

QFrame#sidebar_sep_line {{
    background-color: {t['glass_border']};
    border: none;
    max-width: 1px;
}}

QStackedWidget#content_area {{
    background-color: {t['bg_base']};
}}

QWidget#home_page, QWidget#downloads_page, QWidget#history_page,
QWidget#stats_page, QWidget#settings_page, QWidget#library_page,
QWidget#inbox_page, QWidget#notification_page {{
    background-color: {t['bg_base']};
}}

QLabel#sidebar_logo {{
    color: {t['text_primary']};
    font-size: {FS_H2}px;
    font-weight: 800;
    letter-spacing: 1px;
    padding: 4px 0;
    background: transparent;
}}

QLabel#sidebar_sep {{
    color: {t['text_dim']};
    font-size: {FS_MICRO}px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    padding: 0 12px;
    background: transparent;
}}

QLabel#sidebar_version {{
    color: {t['text_dim']};
    font-size: {FS_MICRO}px;
    font-family: {FONT_MONO};
    background: transparent;
}}

QPushButton#nav_btn {{
    background-color: transparent;
    color: {t['text_mute']};
    border: none;
    border-radius: {R_MD}px;
    padding: 9px 14px;
    font-size: {FS_BODY}px;
    font-weight: 500;
    text-align: left;
}}

QPushButton#nav_btn:hover {{
    background-color: {t['glass_bg']};
    color: {t['text_primary']};
}}

QPushButton#nav_btn:checked {{
    background-color: {t['glass_bg_hi']};
    color: {t['text_primary']};
    border-left: 3px solid {t['accent']};
    padding-left: 11px;
}}

QPushButton#nav_btn_disabled {{
    background-color: transparent;
    color: {t['text_dim']};
    border: none;
    border-radius: {R_MD}px;
    padding: 9px 14px;
    font-size: {FS_BODY}px;
    font-weight: 500;
    text-align: left;
}}

/* ============================================================
   LIQUID GLASS NEW COMPONENTS
   ============================================================ */

/* ---- Glass Card ---- */
QFrame#glass_card, QFrame#lg_card {{
    background-color: {t['card_bg']};
    border: 1px solid {t['card_border']};
    border-radius: {R_XL}px;
}}

QFrame#glass_card:hover, QFrame#lg_card:hover {{
    border-color: {t['card_border_hi']};
}}

/* Legacy card aliases (preserved for compatibility) */
QFrame#task_card, QFrame#history_card, QFrame#library_card, QFrame#stat_card {{
    background-color: {t['card_bg']};
    border: 1px solid {t['card_border']};
    border-radius: {R_MD}px;
    padding: 4px;
}}
QFrame#task_card:hover, QFrame#history_card:hover,
QFrame#library_card:hover, QFrame#stat_card:hover {{
    border-color: {t['card_border_hi']};
}}

/* ---- Queue / History badge (numeric pill) ---- */
QLabel#queue_badge, QLabel#history_badge {{
    background-color: {t['accent']};
    color: {t['text_on_accent']};
    font-size: {FS_MICRO}px;
    font-weight: 700;
    border-radius: {R_PILL}px;
    padding: 2px 10px;
    min-width: 20px;
}}

/* ============================================================
   TASK / HISTORY / LIBRARY CARDS CONTENT
   ============================================================ */
QLabel#task_title {{
    color: {t['text_primary']};
    font-size: {FS_SMALL}px;
    font-weight: 600;
    background: transparent;
}}

QLabel#task_speed {{
    color: {t['text_dim']};
    font-size: {FS_MICRO}px;
    font-family: {FONT_MONO};
    background: transparent;
}}

/* ---- Card title / meta (inbox / notification 卡片内容) ---- */
QLabel#card_title {{
    color: {t['text_primary']};
    font-size: {FS_SMALL}px;
    font-weight: 700;
    background: transparent;
}}
QLabel#card_meta {{
    color: {t['text_mute']};
    font-size: {FS_SMALL}px;
    background: transparent;
}}

/* ---- Notification category tag ---- */
QLabel#notif_cat_tag {{
    background-color: {t['glass_bg_hi']};
    color: {t['text_mute']};
    border: 1px solid {t['glass_border']};
    border-radius: {R_XS}px;
    padding: 1px 8px;
    font-size: {FS_MICRO}px;
    font-weight: 600;
}}

/* ---- Notification close button ---- */
QPushButton#card_close_btn {{
    background: transparent;
    border: none;
    color: {t['text_dim']};
    font-size: {FS_BODY}px;
    padding: 0;
    min-width: 20px;
    min-height: 20px;
}}
QPushButton#card_close_btn:hover {{
    color: {t['text_primary']};
}}

/* ---- Settings page — collapsible toggle button ---- */
QToolButton#settings_toggle {{
    background: transparent;
    border: none;
    color: {t['text_primary']};
    text-align: left;
    font-weight: 600;
    font-size: {FS_BODY}px;
    padding: 6px 2px;
}}
QToolButton#settings_toggle:hover {{
    color: {t['accent']};
}}

/* ---- Settings page — Telegram pair code (large mono accent) ---- */
QLabel#tg_pair_code {{
    color: {t['accent']};
    font-size: 16px;
    font-weight: 700;
    font-family: {FONT_MONO};
    background: transparent;
}}

/* ---- Link-style button (Telegram copy, etc.) ---- */
QPushButton#link_btn {{
    background: transparent;
    border: none;
    color: {t['accent']};
    font-size: {FS_SMALL}px;
    padding: 0;
}}
QPushButton#link_btn:hover {{
    text-decoration: underline;
    color: {t['accent']};
}}
QPushButton#link_btn[state="success"] {{ color: {STATUS_SUCCESS}; }}
QPushButton#link_btn[state="error"]   {{ color: {STATUS_DANGER}; }}

/* ---- Dynamic status message label (success/warning/error/neutral) ----
   使用方式：label.setProperty("state", "success"); polish */
QLabel#status_msg {{
    background: transparent;
    font-size: {FS_SMALL}px;
}}
QLabel#status_msg[state="success"] {{ color: {STATUS_SUCCESS}; }}
QLabel#status_msg[state="warning"] {{ color: {STATUS_WARNING}; }}
QLabel#status_msg[state="error"]   {{ color: {STATUS_DANGER}; }}
QLabel#status_msg[state="neutral"] {{ color: {t['text_dim']}; }}

/* ---- Cookie Banner ---- */
QFrame#cookie_banner {{
    background-color: rgba(255, 214, 10, 0.08);
    border-left: 3px solid {STATUS_WARNING};
    border-radius: {R_SM}px;
    padding: 8px 12px;
}}

QLabel#banner_text {{
    color: {STATUS_WARNING};
    font-size: {FS_SMALL}px;
    background: transparent;
}}

QPushButton#banner_close {{
    background: transparent;
    color: {t['text_mute']};
    border: none;
    font-size: 16px;
    font-weight: bold;
    padding: 2px 6px;
}}
QPushButton#banner_close:hover {{
    color: {t['text_primary']};
}}

/* ---- Cookie Status Indicator ---- */
QLabel#cookie_ok {{
    color: {STATUS_SUCCESS};
    font-size: {FS_SMALL}px;
    font-weight: 600;
    background: transparent;
}}
QLabel#cookie_missing {{
    color: {STATUS_DANGER};
    font-size: {FS_SMALL}px;
    font-weight: 600;
    background: transparent;
}}
QLabel#cookie_expired {{
    color: {STATUS_WARNING};
    font-size: {FS_SMALL}px;
    font-weight: 600;
    background: transparent;
}}

/* ---- Toast ---- */
QLabel#toast {{
    background-color: rgba(48, 209, 88, 0.15);
    color: {STATUS_SUCCESS};
    font-size: {FS_BODY}px;
    font-weight: 600;
    border: 1px solid rgba(48, 209, 88, 0.35);
    border-radius: {R_MD}px;
    padding: 10px 18px;
}}

/* ============================================================
   PLATFORM & STATUS BADGES (auto-generated)
   ============================================================ """
    + _platform_badge_qss(t)
    + """
/* ============================================================
   MEDIA TYPE & STATUS BADGES (auto-generated)
   ============================================================ """
    + _status_badge_qss(t)
    + f"""
/* ============================================================
   TASK ACTION BUTTONS
   ============================================================ */
QPushButton#task_btn {{
    background-color: {t['glass_bg']};
    color: {t['text_mute']};
    border: 1px solid {t['glass_border']};
    border-radius: {R_SM}px;
    padding: 4px 10px;
    font-size: {FS_MICRO}px;
    font-weight: 600;
    min-height: 22px;
}}
QPushButton#task_btn:hover {{
    background-color: {t['glass_bg_hi']};
    color: {t['text_primary']};
    border-color: {t['glass_border_hi']};
}}

QPushButton#task_btn_danger {{
    background-color: {t['glass_bg']};
    color: {STATUS_DANGER};
    border: 1px solid rgba(255, 69, 58, 0.3);
    border-radius: {R_SM}px;
    padding: 4px 10px;
    font-size: {FS_MICRO}px;
    font-weight: 600;
    min-height: 22px;
}}
QPushButton#task_btn_danger:hover {{
    background-color: rgba(255, 69, 58, 0.12);
}}

/* Favorite button (heart) */
QPushButton#fav_btn {{
    background: transparent;
    border: none;
    padding: 2px 4px;
    color: {t['text_dim']};
}}
QPushButton#fav_btn:hover {{
    color: {STATUS_DANGER};
}}
QPushButton#fav_btn:checked {{
    color: {STATUS_DANGER};
}}

QPushButton#icon_add_btn {{
    background: transparent;
    border: 1px solid {t['glass_border']};
    border-radius: {R_SM}px;
    color: {t['text_mute']};
    font-size: 14px;
    font-weight: 700;
    padding: 0;
}}
QPushButton#icon_add_btn:hover {{
    border-color: {t['accent']};
    color: {t['accent']};
}}

/* ============================================================
   HOME PAGE
   ============================================================ */
QFrame#home_hero {{
    background-color: transparent;
    border: none;
    border-radius: 0px;
}}

QLabel#hero_title {{
    color: {t['text_primary']};
    font-size: {FS_DISPLAY}px;
    font-weight: 800;
    background: transparent;
}}

QLabel#hero_subtitle {{
    color: {t['text_mute']};
    font-size: {FS_BODY}px;
    background: transparent;
}}

QLabel#thumb_label, QLabel#preview_thumb, QLabel#library_card_thumb {{
    background-color: {t['card_bg']};
    border: 1px solid {t['card_border']};
    border-radius: {R_MD}px;
    color: {t['text_dim']};
    font-size: {FS_MICRO}px;
    font-weight: 600;
}}

QFrame#home_divider {{
    color: {t['card_border']};
    max-height: 1px;
}}

QFrame#input_card, QFrame#format_row {{
    background-color: {t['card_bg']};
    border: 1px solid {t['card_border']};
    border-radius: {R_LG}px;
}}

QPlainTextEdit#home_url_input {{
    background-color: {t['input_bg']};
    color: {t['text_primary']};
    border: 1px solid {t['glass_border']};
    border-radius: {R_MD}px;
    padding: 12px 16px;
    font-size: {FS_BODY}px;
    font-family: {FONT_BODY};
    selection-background-color: {t['accent_soft']};
}}
QPlainTextEdit#home_url_input:focus {{
    border: 1px solid {t['accent']};
}}

QPushButton#home_parse_btn, QPushButton#home_download_btn {{
    background-color: {t['accent']};
    color: {t['text_on_accent']};
    border: 1px solid {t['accent']};
    border-radius: {R_MD}px;
    padding: 10px 22px;
    font-size: {FS_SMALL}px;
    font-weight: 700;
    min-width: 120px;
}}
QPushButton#home_parse_btn:hover, QPushButton#home_download_btn:hover {{
    background-color: {t['accent_press']};
}}
QPushButton#home_parse_btn:pressed, QPushButton#home_download_btn:pressed {{
    background-color: {t['accent_press']};
}}
QPushButton#home_parse_btn:disabled, QPushButton#home_download_btn:disabled {{
    background-color: {t['glass_bg']};
    color: {t['text_dim']};
    border-color: {t['glass_border']};
}}

QLineEdit#home_name_input, QLineEdit#history_search {{
    background-color: {t['input_bg']};
    color: {t['text_primary']};
    border: 1px solid {t['glass_border']};
    border-radius: {R_MD}px;
    padding: 9px 14px;
    font-size: {FS_SMALL}px;
    font-family: {FONT_BODY};
    selection-background-color: {t['accent_soft']};
}}
QLineEdit#home_name_input:focus, QLineEdit#history_search:focus {{
    border: 1px solid {t['accent']};
}}

/* Capability tag */
QLabel#capability_tag {{
    background-color: {t['glass_bg']};
    color: {t['text_mute']};
    font-size: {FS_MICRO}px;
    border-radius: {R_PILL}px;
    padding: 4px 12px;
}}

/* Preview empty state */
QFrame#preview_empty {{
    background-color: {t['card_bg']};
    border: 2px dashed {t['card_border']};
    border-radius: {R_LG}px;
}}
QLabel#preview_empty_icon {{
    color: {t['text_dim']};
    font-size: 32px;
    background: transparent;
}}
QLabel#preview_empty_text {{
    color: {t['text_mute']};
    font-size: {FS_SMALL}px;
    background: transparent;
}}
QLabel#preview_info_title {{
    color: {t['text_primary']};
    font-size: {FS_H3}px;
    font-weight: 600;
    background: transparent;
}}
QLabel#preview_info_meta {{
    color: {t['text_mute']};
    font-size: {FS_SMALL}px;
    background: transparent;
}}

/* Media items strip */
QScrollArea#media_items_scroll {{
    background-color: transparent;
    border: 1px solid {t['card_border']};
    border-radius: {R_SM}px;
}}
QScrollArea#media_items_scroll > QWidget > QWidget {{
    background-color: transparent;
}}
QFrame#media_item_card {{
    background-color: {t['card_bg']};
    border: 1px solid {t['card_border']};
    border-radius: {R_SM}px;
}}
QFrame#media_item_card:hover {{
    border: 1px solid {t['accent']};
    background-color: {t['card_bg_hover']};
}}
QFrame#media_item_card[selected="true"] {{
    border: 1px solid {t['accent']};
    background-color: {t['accent_soft']};
}}
QFrame#media_item_card[added="true"] {{
    border: 1px solid {STATUS_SUCCESS};
    background-color: rgba(48, 209, 88, 0.08);
}}
QLabel#media_item_thumb {{
    background-color: {t['card_bg']};
    border: 1px solid {t['card_border']};
    border-radius: {R_SM}px;
    color: {t['text_mute']};
    font-size: 28px;
}}
QLabel#media_item_type_label {{
    color: {t['text_mute']};
    font-size: {FS_MICRO}px;
    font-weight: 600;
    background: transparent;
}}
QPushButton#media_item_add_btn {{
    background-color: {t['accent']};
    color: {t['text_on_accent']};
    border: none;
    border-radius: {R_XS}px;
    padding: 4px 8px;
    font-size: {FS_MICRO}px;
    font-weight: 600;
}}
QPushButton#media_item_add_btn:hover {{
    background-color: {t['accent_press']};
}}
QPushButton#media_item_add_btn:disabled {{
    background-color: {STATUS_SUCCESS};
    color: {t['text_on_accent']};
}}
QFrame#media_item_card[added="true"] QPushButton#media_item_add_btn {{
    background-color: {STATUS_SUCCESS};
}}

/* Search results */
QScrollArea#search_scroll {{
    background-color: transparent;
    border: 1px solid {t['card_border']};
    border-radius: {R_SM}px;
}}

/* History / Library page scroll — 透明无边框，背景跟随页面 */
QScrollArea#history_scroll,
QScrollArea#library_scroll {{
    background-color: transparent;
    border: none;
}}
QScrollArea#history_scroll > QWidget > QWidget,
QScrollArea#library_scroll > QWidget > QWidget {{
    background-color: transparent;
}}
QLabel#search_thumb {{
    background-color: {t['card_bg']};
    border-radius: {R_XS}px;
}}
QLabel#search_result_title {{
    font-size: {FS_SMALL}px;
    color: {t['text_primary']};
    background: transparent;
}}

/* Init page log */
QPlainTextEdit#init_log {{
    background-color: {t['card_bg']};
    color: {t['text_mute']};
    border: 1px solid {t['card_border']};
    border-radius: {R_MD}px;
    font-family: {FONT_MONO};
    font-size: {FS_SMALL}px;
    padding: 10px;
}}

/* ============================================================
   LIQUID GLASS — NEW WIDGETS (lg_ prefix)
   ============================================================ */

/* Glass badge (replaces QLabel#badge_*) */
QLabel#lg_badge {{
    background-color: {t['glass_bg']};
    color: {t['text_mute']};
    border: 1px solid {t['glass_border']};
    font-size: {FS_MICRO}px;
    font-weight: 600;
    border-radius: {R_PILL}px;
    padding: 3px 10px;
}}

/* Glass pill (platform selector) */
QPushButton#lg_pill {{
    background-color: {t['glass_bg']};
    color: {t['text_mute']};
    border: 1px solid {t['glass_border']};
    border-radius: {R_PILL}px;
    padding: 7px 14px;
    font-size: {FS_SMALL}px;
    font-weight: 600;
    min-height: 20px;
}}
QPushButton#lg_pill:hover {{
    background-color: {t['glass_bg_hi']};
    color: {t['text_primary']};
    border-color: {t['glass_border_hi']};
}}

/* LED (status indicator dot) */
QLabel#lg_led {{
    background-color: {t['text_dim']};
    border-radius: 3px;
    min-width: 6px;
    max-width: 6px;
    min-height: 6px;
    max-height: 6px;
}}
QLabel#lg_led[led="green"]  {{ background-color: {STATUS_SUCCESS}; }}
QLabel#lg_led[led="blue"]   {{ background-color: {t['accent']}; }}
QLabel#lg_led[led="yellow"] {{ background-color: {STATUS_WARNING}; }}
QLabel#lg_led[led="red"]    {{ background-color: {STATUS_DANGER}; }}
QLabel#lg_led[led="pink"]   {{ background-color: {PLATFORM_COLORS['instagram']}; }}

/* Toggle switch (off state) */
QPushButton#lg_toggle {{
    background-color: {t['glass_bg_press']};
    border: 1px solid {t['glass_border']};
    border-radius: {R_PILL}px;
    padding: 2px;
    min-width: 44px;
    min-height: 24px;
    max-width: 44px;
    max-height: 24px;
}}
QPushButton#lg_toggle:checked {{
    background-color: {t['accent']};
    border-color: {t['accent']};
}}
QPushButton#lg_toggle::menu-indicator {{
    image: none;
    width: 0;
    height: 0;
}}

/* ---- Status Bar ---- */
QFrame#lg_status_bar {{
    background-color: {t['glass_bg']};
    border: 1px solid {t['glass_border']};
    border-radius: {R_LG}px;
    padding: 12px 22px;
}}
QLabel#lg_status_item {{
    color: {t['text_dim']};
    font-size: {FS_MICRO}px;
    background: transparent;
}}

/* ---- Empty State ---- */
QFrame#lg_empty {{
    background-color: transparent;
    border: none;
}}
QLabel#lg_empty_icon {{
    color: {t['text_dim']};
    background: transparent;
}}
QLabel#lg_empty_title {{
    color: {t['text_mute']};
    font-size: {FS_H3}px;
    font-weight: 600;
    background: transparent;
}}
QLabel#lg_empty_hint {{
    color: {t['text_dim']};
    font-size: {FS_MICRO}px;
    background: transparent;
}}

/* ---- Profile pic (round avatar placeholder in dialog header) ---- */
QLabel#profile_pic {{
    background-color: {t['card_bg']};
    border: 2px solid {t['glass_border']};
    border-radius: 32px;
}}

/* ---- Video widget (always black canvas) ---- */
QVideoWidget#video_widget {{
    background-color: #000;
}}

/* ---- Audio icon (large note glyph in audio preview) ---- */
QLabel#audio_icon {{
    color: {t['accent']};
    font-size: 48px;
    background: transparent;
}}
"""


# ============================================================
# 公共 API
# ============================================================
_STYLESHEET_CACHE: dict[str, str] = {}


def get_stylesheet(theme: str = "dark") -> str:
    """获取指定主题的完整 QSS。

    与原 styles.py 接口兼容，window.py 无需改动。
    内部缓存，多次调用不重复生成。

    Args:
        theme: "dark" 或 "light"

    Returns:
        完整 QSS 字符串
    """
    if theme not in _STYLESHEET_CACHE:
        t = get_tokens(theme)
        _STYLESHEET_CACHE[theme] = _build_qss(t)
    return _STYLESHEET_CACHE[theme]


def clear_cache():
    """清理 stylesheet 缓存。

    在主题 Token 修改后调用，重新生成 QSS。
    """
    _STYLESHEET_CACHE.clear()


# 向后兼容：保留旧的 STYLESHEET / LIGHT_STYLESHEET 模块级常量
# 这些是早期 styles.py 暴露的接口，少数代码可能直接 import 使用
STYLESHEET = get_stylesheet("dark")
LIGHT_STYLESHEET = get_stylesheet("light")
