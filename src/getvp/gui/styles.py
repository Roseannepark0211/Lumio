STYLESHEET = """
/* ---- Global ---- */
QMainWindow {
    background-color: #0f1117;
}

QWidget {
    color: #e0e0e6;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 13px;
}

QScrollArea > QWidget > QWidget {
    background-color: #0f1117;
}

/* ---- Labels ---- */
QLabel {
    color: #e0e0e6;
    font-size: 13px;
    background: transparent;
}

QLabel#accent {
    color: #7c8fff;
    font-size: 15px;
    font-weight: 600;
}

QLabel#muted {
    color: #6b7084;
    font-size: 12px;
}

QLabel#section_title {
    color: #a0a8c8;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    background: transparent;
    padding: 0;
    margin: 0;
}

/* ---- Inputs ---- */
QLineEdit {
    background-color: #1a1d27;
    color: #e0e0e6;
    border: 1px solid #2a2e3a;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    selection-background-color: #3d4466;
    min-height: 18px;
}

QLineEdit:focus {
    border: 1px solid #5a6490;
}

QLineEdit::placeholder {
    color: #4a4e5e;
}

QTextEdit, QPlainTextEdit {
    background-color: #1a1d27;
    color: #e0e0e6;
    border: 1px solid #2a2e3a;
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 13px;
    font-family: "Cascadia Code", "Consolas", "Microsoft YaHei UI", monospace;
    selection-background-color: #3d4466;
}

QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #5a6490;
}

/* ---- Buttons ---- */
QPushButton {
    background-color: #2563eb;
    color: #ffffff;
    border: 1px solid #3b82f6;
    border-radius: 8px;
    padding: 8px 22px;
    font-size: 13px;
    font-weight: 600;
    min-height: 18px;
}

QPushButton:hover {
    background-color: #3b82f6;
}

QPushButton:pressed {
    background-color: #1d4ed8;
}

QPushButton:disabled {
    background-color: #1f2230;
    color: #4a4e5e;
}

QPushButton#secondary {
    background-color: #1e2130;
    color: #a0a8c8;
    border: 1px solid #2e3245;
    font-weight: 500;
}

QPushButton#secondary:hover {
    background-color: #282c40;
    border-color: #3e4460;
}

QPushButton#secondary:pressed {
    background-color: #151825;
}

QPushButton#accent_btn {
    background-color: #10b981;
    color: #ffffff;
    border: 1px solid #34d399;
    font-weight: 700;
    font-size: 14px;
    padding: 10px 28px;
    min-width: 120px;
}

QPushButton#accent_btn:hover {
    background-color: #34d399;
}

QPushButton#accent_btn:pressed {
    background-color: #059669;
}

QPushButton#accent_btn:disabled {
    background-color: #1f2230;
    color: #4a4e5e;
}

/* ---- ComboBox ---- */
QComboBox {
    background-color: #1a1d27;
    color: #e0e0e6;
    border: 1px solid #2a2e3a;
    border-radius: 8px;
    padding: 7px 12px;
    font-size: 13px;
    min-height: 18px;
}

QComboBox:hover {
    border-color: #3e4460;
}

QComboBox::drop-down {
    border: none;
    width: 28px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #6b7084;
    margin-right: 8px;
}

QComboBox QAbstractItemView {
    background-color: #1a1d27;
    color: #e0e0e6;
    border: 1px solid #2e3245;
    border-radius: 6px;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
    padding: 4px;
}

/* ---- Progress Bar ---- */
QProgressBar {
    background-color: #151822;
    border: none;
    border-radius: 4px;
    text-align: center;
    color: #e0e0e6;
    font-size: 10px;
    font-weight: 600;
    min-height: 14px;
    max-height: 14px;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #2563eb, stop:1 #7c3aed);
    border-radius: 6px;
}

/* ---- List Widget ---- */
QListWidget {
    background-color: #12141c;
    color: #c8ccd8;
    border: 1px solid #1e2130;
    border-radius: 8px;
    font-size: 13px;
    outline: none;
    padding: 4px;
}

QListWidget::item {
    padding: 8px 10px;
    border-radius: 5px;
    margin: 1px 0;
}

QListWidget::item:selected {
    background-color: #1e2440;
    color: #e0e0e6;
}

QListWidget::item:hover {
    background-color: #191d2a;
}

/* ---- Group Box (Card style) ---- */
QGroupBox {
    background-color: #161822;
    border: 1px solid #22253a;
    border-radius: 10px;
    margin-top: 0px;
    padding: 20px 18px 16px 18px;
    font-size: 12px;
    font-weight: 600;
    color: #7c8fff;
}

QGroupBox::title {
    subcontrol-origin: padding;
    subcontrol-position: top left;
    left: 18px;
    top: 6px;
    padding: 0 8px;
    color: #7c8fff;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
    background-color: #161822;
}

/* ---- ScrollBar ---- */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #2a2e3a;
    border-radius: 4px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: #3e4460;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}

/* ---- Tooltip ---- */
QToolTip {
    background-color: #1e2130;
    color: #e0e0e6;
    border: 1px solid #2e3245;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}

/* ---- Dialog / MessageBox ---- */
QDialog {
    background-color: #161822;
}

QMessageBox {
    background-color: #161822;
}

QMessageBox QLabel {
    color: #e0e0e6;
    font-size: 13px;
    background: transparent;
}

QMessageBox QPushButton {
    min-width: 80px;
    min-height: 30px;
}

/* ---- Init Page ---- */
QPlainTextEdit#init_log {
    background-color: #0d0f16;
    color: #a0a8c8;
    border: 1px solid #1e2130;
    border-radius: 8px;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 12px;
    padding: 10px;
}

/* ---- Cookie Banner ---- */
QFrame#cookie_banner {
    background-color: #1e293b;
    border-left: 3px solid #f59e0b;
    border-radius: 6px;
    padding: 8px 12px;
}

QLabel#banner_text {
    color: #fbbf24;
    font-size: 13px;
    background: transparent;
}

QPushButton#banner_close {
    background: transparent;
    color: #94a3b8;
    border: none;
    font-size: 16px;
    font-weight: bold;
    padding: 2px 6px;
}

QPushButton#banner_close:hover {
    color: #e2e8f0;
}

/* ---- Cookie Status Indicator ---- */
QLabel#cookie_ok {
    color: #10b981;
    font-size: 12px;
    font-weight: 600;
    background: transparent;
}

QLabel#cookie_missing {
    color: #f87171;
    font-size: 12px;
    font-weight: 600;
    background: transparent;
}

QLabel#cookie_expired {
    color: #fbbf24;
    font-size: 12px;
    font-weight: 600;
    background: transparent;
}

/* ---- Queue Drawer ---- */
QFrame#queue_header {
    background-color: #161822;
    border-top: 1px solid #22253a;
    border-radius: 0;
    padding: 6px 12px;
}

QLabel#queue_title {
    color: #a0a8c8;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
    background: transparent;
}

QLabel#queue_badge {
    background-color: #2563eb;
    color: #ffffff;
    font-size: 11px;
    font-weight: 700;
    border-radius: 10px;
    padding: 1px 8px;
    min-width: 20px;
}

/* ---- Queue Task Card ---- */
QFrame#task_card {
    background-color: #161822;
    border: 1px solid #22253a;
    border-radius: 6px;
    padding: 4px;
}

QLabel#task_title {
    color: #e0e0e6;
    font-size: 12px;
    font-weight: 500;
    background: transparent;
}

QLabel#task_speed {
    color: #6b7084;
    font-size: 10px;
    background: transparent;
}

/* ---- Status Badges ---- */
QLabel#badge_waiting {
    background-color: #374151;
    color: #9ca3af;
    font-size: 10px;
    font-weight: 600;
    border-radius: 3px;
    padding: 1px 6px;
}

QLabel#badge_retrying {
    background-color: #451a03;
    color: #f59e0b;
    font-size: 10px;
    font-weight: 600;
    border-radius: 3px;
    padding: 1px 6px;
}

QLabel#badge_interrupted {
    background-color: #1e1b4b;
    color: #a78bfa;
    font-size: 10px;
    font-weight: 600;
    border-radius: 3px;
    padding: 1px 6px;
}

QLabel#badge_downloading {
    background-color: #1e3a5f;
    color: #60a5fa;
    font-size: 10px;
    font-weight: 600;
    border-radius: 3px;
    padding: 1px 6px;
}

QLabel#badge_paused {
    background-color: #422006;
    color: #fbbf24;
    font-size: 10px;
    font-weight: 600;
    border-radius: 3px;
    padding: 1px 6px;
}

QLabel#badge_completed {
    background-color: #064e3b;
    color: #34d399;
    font-size: 10px;
    font-weight: 600;
    border-radius: 3px;
    padding: 1px 6px;
}

QLabel#badge_failed {
    background-color: #450a0a;
    color: #f87171;
    font-size: 10px;
    font-weight: 600;
    border-radius: 3px;
    padding: 1px 6px;
}

QLabel#badge_cancelled {
    background-color: #1f2937;
    color: #6b7280;
    font-size: 10px;
    font-weight: 600;
    border-radius: 3px;
    padding: 1px 6px;
}

/* ---- Platform Badge ---- */
QLabel#platform_yt {
    background-color: #2563eb;
    color: #ffffff;
    font-size: 9px;
    font-weight: 700;
    border-radius: 3px;
    padding: 0px 4px;
}

QLabel#platform_ig {
    background-color: #e1306c;
    color: #ffffff;
    font-size: 9px;
    font-weight: 700;
    border-radius: 3px;
    padding: 0px 4px;
}

QLabel#platform_x {
    background-color: #1d9bf0;
    color: #ffffff;
    font-size: 9px;
    font-weight: 700;
    border-radius: 3px;
    padding: 0px 4px;
}

/* ---- History Drawer ---- */
QFrame#history_header {
    background-color: #161822;
    border-top: 1px solid #22253a;
    border-radius: 0;
    padding: 6px 12px;
}

QLabel#history_badge {
    background-color: #7c8fff;
    color: #ffffff;
    font-size: 11px;
    font-weight: 700;
    border-radius: 10px;
    padding: 1px 8px;
    min-width: 20px;
}

QLineEdit#history_search {
    background-color: #1a1d27;
    color: #e0e0e6;
    border: 1px solid #2a2e3a;
    border-radius: 6px;
    padding: 3px 8px;
    font-size: 11px;
    min-height: 18px;
}

QLineEdit#history_search:focus {
    border: 1px solid #5a6490;
}

/* ---- History Card ---- */
QFrame#history_card {
    background-color: #161822;
    border: 1px solid #22253a;
    border-radius: 6px;
    padding: 4px;
}

QFrame#history_card:hover {
    border-color: #3e4460;
}

/* ---- Library Card ---- */
QFrame#library_card {
    background-color: #161822;
    border: 1px solid #22253a;
    border-radius: 6px;
    padding: 4px;
}

QFrame#library_card:hover {
    border-color: #3e4460;
}

QLabel#library_card_thumb {
    background-color: #12141c;
    border: 1px solid #1e2130;
    border-radius: 6px;
    color: #6b7084;
    font-size: 10px;
    font-weight: 600;
}

QPushButton#fav_btn {
    background: transparent;
    border: none;
    font-size: 16px;
    padding: 2px 4px;
    color: #6b7084;
}
QPushButton#fav_btn:hover {
    color: #ef4444;
}
QPushButton#fav_btn:checked {
    color: #ef4444;
}

QPushButton#pin_btn {
    background: transparent;
    border: none;
    font-size: 14px;
    padding: 2px 4px;
    color: #6b7084;
}
QPushButton#pin_btn:hover {
    color: #f59e0b;
}

QLabel#tag_chip {
    background-color: #22253a;
    color: #a0a4b8;
    font-size: 10px;
    font-weight: 600;
    border-radius: 8px;
    padding: 1px 8px;
}

QPushButton#tag_add_btn {
    background: transparent;
    border: 1px solid #3e4460;
    border-radius: 8px;
    color: #6b7084;
    font-size: 14px;
    font-weight: 700;
    padding: 0;
}
QPushButton#tag_add_btn:hover {
    border-color: #7c8fff;
    color: #7c8fff;
}

QPushButton#tag_del_btn {
    background: transparent;
    border: none;
    color: #6b7084;
    font-size: 10px;
    font-weight: 700;
    padding: 0;
}
QPushButton#tag_del_btn:hover {
    color: #ef4444;
}

QLineEdit#tag_input {
    background-color: #161822;
    border: 1px solid #3e4460;
    border-radius: 4px;
    color: #e0e0e6;
    font-size: 11px;
    padding: 1px 4px;
}

/* ---- Media Type Badges ---- */
QLabel#media_video {
    background-color: #7c3aed;
    color: #ffffff;
    font-size: 9px;
    font-weight: 700;
    border-radius: 3px;
    padding: 0px 4px;
}

QLabel#media_audio {
    background-color: #f59e0b;
    color: #ffffff;
    font-size: 9px;
    font-weight: 700;
    border-radius: 3px;
    padding: 0px 4px;
}

QLabel#media_image {
    background-color: #10b981;
    color: #ffffff;
    font-size: 9px;
    font-weight: 700;
    border-radius: 3px;
    padding: 0px 4px;
}

QLabel#media_mixed {
    background-color: #6366f1;
    color: #ffffff;
    font-size: 9px;
    font-weight: 700;
    border-radius: 3px;
    padding: 0px 4px;
}

/* ---- Task Action Buttons ---- */
QPushButton#task_btn {
    background-color: #1e2130;
    color: #a0a8c8;
    border: 1px solid #2e3245;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 10px;
    min-height: 20px;
}

QPushButton#task_btn:hover {
    background-color: #282c40;
    border-color: #3e4460;
}

QPushButton#task_btn_danger {
    background-color: #1e2130;
    color: #f87171;
    border: 1px solid #3b1111;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 10px;
    min-height: 20px;
}

QPushButton#task_btn_danger:hover {
    background-color: #2d1111;
}

/* ---- Toast Notification ---- */
QLabel#toast {
    background-color: #064e3b;
    color: #34d399;
    font-size: 13px;
    font-weight: 600;
    border-radius: 6px;
    padding: 8px 16px;
}

/* ---- Sidebar ---- */
QFrame#sidebar {
    background-color: #0c0e14;
    border-right: 1px solid #1a1d27;
}

QFrame#sidebar_sep_line {
    background-color: #1a1d27;
    border: none;
    max-width: 1px;
}

QStackedWidget#content_area {
    background-color: #0f1117;
}

QWidget#home_page, QWidget#downloads_page, QWidget#history_page,
QWidget#stats_page, QWidget#settings_page, QWidget#library_page {
    background-color: #0f1117;
}

QLabel#sidebar_logo {
    color: #7c8fff;
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 2px;
    padding: 4px 0;
    background: transparent;
}

QLabel#sidebar_sep {
    color: #3e4460;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    padding: 0 12px;
    background: transparent;
}

QLabel#sidebar_version {
    color: #2e3245;
    font-size: 10px;
    background: transparent;
}

QPushButton#nav_btn {
    background-color: transparent;
    color: #6b7084;
    border: none;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    font-weight: 500;
    text-align: left;
}

QPushButton#nav_btn:hover {
    background-color: #161822;
    color: #a0a8c8;
}

QPushButton#nav_btn:checked {
    background-color: #161822;
    color: #e0e0e6;
    border-left: 3px solid #7c8fff;
    padding-left: 9px;
}

QPushButton#nav_btn_disabled {
    background-color: transparent;
    color: #2e3245;
    border: none;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    font-weight: 500;
    text-align: left;
}

/* ---- Page Title ---- */
QLabel#page_title {
    color: #e0e0e6;
    font-size: 18px;
    font-weight: 700;
    background: transparent;
}

/* ---- Stat Card ---- */
QWidget#stat_card {
    background-color: #161822;
    border: 1px solid #22253a;
    border-radius: 10px;
}

QWidget#stat_card:hover {
    border-color: #3e4460;
}

/* ---- History Filter ---- */
QComboBox#history_filter {
    background-color: #1a1d27;
    color: #a0a8c8;
    border: 1px solid #2a2e3a;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 11px;
    min-height: 22px;
}

/* ---- Home Page ---- */
QLabel#thumb_label {
    background-color: #12141c;
    border: 1px solid #1e2130;
    border-radius: 8px;
}

QFrame#home_divider {
    color: #22253a;
    max-height: 1px;
}

/* ---- Stat Label ---- */
QLabel#stat_label {
    color: #6b7084;
    font-size: 12px;
    background: transparent;
}
"""

LIGHT_STYLESHEET = """
/* ---- Global ---- */
QMainWindow {
    background-color: #f5f5f7;
}

QWidget {
    color: #1a1a2e;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 13px;
}

QScrollArea > QWidget > QWidget {
    background-color: #f5f5f7;
}

/* ---- Labels ---- */
QLabel {
    color: #1a1a2e;
    font-size: 13px;
    background: transparent;
}

QLabel#accent {
    color: #2563eb;
    font-size: 15px;
    font-weight: 600;
}

QLabel#muted {
    color: #8e8ea0;
    font-size: 12px;
}

QLabel#section_title {
    color: #555568;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    background: transparent;
    padding: 0;
    margin: 0;
}

/* ---- Inputs ---- */
QLineEdit {
    background-color: #ffffff;
    color: #1a1a2e;
    border: 1px solid #d4d4dc;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    selection-background-color: #bfcfff;
    min-height: 18px;
}

QLineEdit:focus {
    border: 1px solid #2563eb;
}

QLineEdit::placeholder {
    color: #b0b0c0;
}

QTextEdit, QPlainTextEdit {
    background-color: #ffffff;
    color: #1a1a2e;
    border: 1px solid #d4d4dc;
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 13px;
    font-family: "Cascadia Code", "Consolas", "Microsoft YaHei UI", monospace;
    selection-background-color: #bfcfff;
}

QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #2563eb;
}

/* ---- Buttons ---- */
QPushButton {
    background-color: #2563eb;
    color: #ffffff;
    border: 1px solid #3b82f6;
    border-radius: 8px;
    padding: 8px 22px;
    font-size: 13px;
    font-weight: 600;
    min-height: 18px;
}

QPushButton:hover {
    background-color: #3b82f6;
}

QPushButton:pressed {
    background-color: #1d4ed8;
}

QPushButton:disabled {
    background-color: #e8e8ee;
    color: #b0b0c0;
}

QPushButton#secondary {
    background-color: #e8e8ee;
    color: #555568;
    border: 1px solid #d4d4dc;
    font-weight: 500;
}

QPushButton#secondary:hover {
    background-color: #dcdce4;
    border-color: #c0c0cc;
}

QPushButton#secondary:pressed {
    background-color: #d0d0da;
}

QPushButton#accent_btn {
    background-color: #10b981;
    color: #ffffff;
    border: 1px solid #34d399;
    font-weight: 700;
    font-size: 14px;
    padding: 10px 28px;
    min-width: 120px;
}

QPushButton#accent_btn:hover {
    background-color: #34d399;
}

QPushButton#accent_btn:pressed {
    background-color: #059669;
}

QPushButton#accent_btn:disabled {
    background-color: #e8e8ee;
    color: #b0b0c0;
}

/* ---- ComboBox ---- */
QComboBox {
    background-color: #ffffff;
    color: #1a1a2e;
    border: 1px solid #d4d4dc;
    border-radius: 8px;
    padding: 7px 12px;
    font-size: 13px;
    min-height: 18px;
}

QComboBox:hover {
    border-color: #2563eb;
}

QComboBox::drop-down {
    border: none;
    width: 28px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #8e8ea0;
    margin-right: 8px;
}

QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #1a1a2e;
    border: 1px solid #d4d4dc;
    border-radius: 6px;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
    padding: 4px;
}

/* ---- Progress Bar ---- */
QProgressBar {
    background-color: #e8e8ee;
    border: none;
    border-radius: 4px;
    text-align: center;
    color: #1a1a2e;
    font-size: 10px;
    font-weight: 600;
    min-height: 14px;
    max-height: 14px;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #2563eb, stop:1 #7c3aed);
    border-radius: 6px;
}

/* ---- Group Box (Card style) ---- */
QGroupBox {
    background-color: #ffffff;
    border: 1px solid #e0e0e6;
    border-radius: 10px;
    margin-top: 0px;
    padding: 20px 18px 16px 18px;
    font-size: 12px;
    font-weight: 600;
    color: #2563eb;
}

QGroupBox::title {
    subcontrol-origin: padding;
    subcontrol-position: top left;
    left: 18px;
    top: 6px;
    padding: 0 8px;
    color: #2563eb;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
    background-color: #ffffff;
}

/* ---- ScrollBar ---- */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #c0c0cc;
    border-radius: 4px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: #a0a0b0;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}

/* ---- Tooltip ---- */
QToolTip {
    background-color: #ffffff;
    color: #1a1a2e;
    border: 1px solid #d4d4dc;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}

/* ---- Dialog / MessageBox ---- */
QDialog {
    background-color: #ffffff;
}

QMessageBox {
    background-color: #ffffff;
}

QMessageBox QLabel {
    color: #1a1a2e;
    font-size: 13px;
    background: transparent;
}

QMessageBox QPushButton {
    min-width: 80px;
    min-height: 30px;
}

/* ---- Init Page ---- */
QPlainTextEdit#init_log {
    background-color: #f0f0f4;
    color: #555568;
    border: 1px solid #e0e0e6;
    border-radius: 8px;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 12px;
    padding: 10px;
}

/* ---- Cookie Banner ---- */
QFrame#cookie_banner {
    background-color: #fef3c7;
    border-left: 3px solid #f59e0b;
    border-radius: 6px;
    padding: 8px 12px;
}

QLabel#banner_text {
    color: #92400e;
    font-size: 13px;
    background: transparent;
}

QPushButton#banner_close {
    background: transparent;
    color: #8e8ea0;
    border: none;
    font-size: 16px;
    font-weight: bold;
    padding: 2px 6px;
}

QPushButton#banner_close:hover {
    color: #555568;
}

/* ---- Cookie Status Indicator ---- */
QLabel#cookie_ok {
    color: #10b981;
    font-size: 12px;
    font-weight: 600;
    background: transparent;
}

QLabel#cookie_missing {
    color: #ef4444;
    font-size: 12px;
    font-weight: 600;
    background: transparent;
}

QLabel#cookie_expired {
    color: #f59e0b;
    font-size: 12px;
    font-weight: 600;
    background: transparent;
}

/* ---- Queue Drawer ---- */
QFrame#queue_header {
    background-color: #ffffff;
    border-top: 1px solid #e0e0e6;
    border-radius: 0;
    padding: 6px 12px;
}

QLabel#queue_title {
    color: #555568;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
    background: transparent;
}

QLabel#queue_badge {
    background-color: #2563eb;
    color: #ffffff;
    font-size: 11px;
    font-weight: 700;
    border-radius: 10px;
    padding: 1px 8px;
    min-width: 20px;
}

/* ---- Queue Task Card ---- */
QFrame#task_card {
    background-color: #ffffff;
    border: 1px solid #e0e0e6;
    border-radius: 6px;
    padding: 4px;
}

QLabel#task_title {
    color: #1a1a2e;
    font-size: 12px;
    font-weight: 500;
    background: transparent;
}

QLabel#task_speed {
    color: #8e8ea0;
    font-size: 10px;
    background: transparent;
}

/* ---- Status Badges ---- */
QLabel#badge_waiting {
    background-color: #e8e8ee;
    color: #555568;
    font-size: 10px;
    font-weight: 600;
    border-radius: 3px;
    padding: 1px 6px;
}

QLabel#badge_retrying {
    background-color: #fef3c7;
    color: #b45309;
    font-size: 10px;
    font-weight: 600;
    border-radius: 3px;
    padding: 1px 6px;
}

QLabel#badge_interrupted {
    background-color: #ede9fe;
    color: #7c3aed;
    font-size: 10px;
    font-weight: 600;
    border-radius: 3px;
    padding: 1px 6px;
}

QLabel#badge_downloading {
    background-color: #dbeafe;
    color: #2563eb;
    font-size: 10px;
    font-weight: 600;
    border-radius: 3px;
    padding: 1px 6px;
}

QLabel#badge_paused {
    background-color: #fef3c7;
    color: #92400e;
    font-size: 10px;
    font-weight: 600;
    border-radius: 3px;
    padding: 1px 6px;
}

QLabel#badge_completed {
    background-color: #d1fae5;
    color: #065f46;
    font-size: 10px;
    font-weight: 600;
    border-radius: 3px;
    padding: 1px 6px;
}

QLabel#badge_failed {
    background-color: #fee2e2;
    color: #991b1b;
    font-size: 10px;
    font-weight: 600;
    border-radius: 3px;
    padding: 1px 6px;
}

QLabel#badge_cancelled {
    background-color: #e8e8ee;
    color: #8e8ea0;
    font-size: 10px;
    font-weight: 600;
    border-radius: 3px;
    padding: 1px 6px;
}

/* ---- Platform Badge ---- */
QLabel#platform_yt {
    background-color: #2563eb;
    color: #ffffff;
    font-size: 9px;
    font-weight: 700;
    border-radius: 3px;
    padding: 0px 4px;
}

QLabel#platform_ig {
    background-color: #e1306c;
    color: #ffffff;
    font-size: 9px;
    font-weight: 700;
    border-radius: 3px;
    padding: 0px 4px;
}

QLabel#platform_x {
    background-color: #1d9bf0;
    color: #ffffff;
    font-size: 9px;
    font-weight: 700;
    border-radius: 3px;
    padding: 0px 4px;
}

/* ---- Media Type Badges ---- */
QLabel#media_video {
    background-color: #7c3aed;
    color: #ffffff;
    font-size: 9px;
    font-weight: 700;
    border-radius: 3px;
    padding: 0px 4px;
}

QLabel#media_audio {
    background-color: #f59e0b;
    color: #ffffff;
    font-size: 9px;
    font-weight: 700;
    border-radius: 3px;
    padding: 0px 4px;
}

QLabel#media_image {
    background-color: #10b981;
    color: #ffffff;
    font-size: 9px;
    font-weight: 700;
    border-radius: 3px;
    padding: 0px 4px;
}

QLabel#media_mixed {
    background-color: #6366f1;
    color: #ffffff;
    font-size: 9px;
    font-weight: 700;
    border-radius: 3px;
    padding: 0px 4px;
}

/* ---- Task Action Buttons ---- */
QPushButton#task_btn {
    background-color: #e8e8ee;
    color: #555568;
    border: 1px solid #d4d4dc;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 10px;
    min-height: 20px;
}

QPushButton#task_btn:hover {
    background-color: #dcdce4;
    border-color: #c0c0cc;
}

QPushButton#task_btn_danger {
    background-color: #e8e8ee;
    color: #ef4444;
    border: 1px solid #fecaca;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 10px;
    min-height: 20px;
}

QPushButton#task_btn_danger:hover {
    background-color: #fee2e2;
}

/* ---- Toast Notification ---- */
QLabel#toast {
    background-color: #d1fae5;
    color: #065f46;
    font-size: 13px;
    font-weight: 600;
    border-radius: 6px;
    padding: 8px 16px;
}

/* ---- Sidebar ---- */
QFrame#sidebar {
    background-color: #ebebf0;
    border-right: 1px solid #d4d4dc;
}

QFrame#sidebar_sep_line {
    background-color: #d4d4dc;
    border: none;
    max-width: 1px;
}

QStackedWidget#content_area {
    background-color: #f5f5f7;
}

QWidget#home_page, QWidget#downloads_page, QWidget#history_page,
QWidget#stats_page, QWidget#settings_page, QWidget#library_page {
    background-color: #f5f5f7;
}

QLabel#sidebar_logo {
    color: #2563eb;
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 2px;
    padding: 4px 0;
    background: transparent;
}

QLabel#sidebar_sep {
    color: #b0b0c0;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    padding: 0 12px;
    background: transparent;
}

QLabel#sidebar_version {
    color: #c0c0cc;
    font-size: 10px;
    background: transparent;
}

QPushButton#nav_btn {
    background-color: transparent;
    color: #8e8ea0;
    border: none;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    font-weight: 500;
    text-align: left;
}

QPushButton#nav_btn:hover {
    background-color: #ffffff;
    color: #555568;
}

QPushButton#nav_btn:checked {
    background-color: #ffffff;
    color: #1a1a2e;
    border-left: 3px solid #2563eb;
    padding-left: 9px;
}

QPushButton#nav_btn_disabled {
    background-color: transparent;
    color: #d4d4dc;
    border: none;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    font-weight: 500;
    text-align: left;
}

/* ---- Page Title ---- */
QLabel#page_title {
    color: #1a1a2e;
    font-size: 18px;
    font-weight: 700;
    background: transparent;
}

/* ---- Stat Card ---- */
QWidget#stat_card {
    background-color: #ffffff;
    border: 1px solid #e0e0e6;
    border-radius: 10px;
}

QWidget#stat_card:hover {
    border-color: #2563eb;
}

/* ---- History Drawer ---- */
QFrame#history_header {
    background-color: #ffffff;
    border-top: 1px solid #e0e0e6;
    border-radius: 0;
    padding: 6px 12px;
}

QLabel#history_badge {
    background-color: #2563eb;
    color: #ffffff;
    font-size: 11px;
    font-weight: 700;
    border-radius: 10px;
    padding: 1px 8px;
    min-width: 20px;
}

QLineEdit#history_search {
    background-color: #ffffff;
    color: #1a1a2e;
    border: 1px solid #d4d4dc;
    border-radius: 6px;
    padding: 3px 8px;
    font-size: 11px;
    min-height: 18px;
}

QLineEdit#history_search:focus {
    border: 1px solid #2563eb;
}

/* ---- History Card ---- */
QFrame#history_card {
    background-color: #ffffff;
    border: 1px solid #e0e0e6;
    border-radius: 6px;
    padding: 4px;
}

QFrame#history_card:hover {
    border-color: #2563eb;
}

/* ---- Library Card (Light) ---- */
QFrame#library_card {
    background-color: #ffffff;
    border: 1px solid #e0e0e6;
    border-radius: 6px;
    padding: 4px;
}

QFrame#library_card:hover {
    border-color: #2563eb;
}

QLabel#library_card_thumb {
    background-color: #f0f0f5;
    border: 1px solid #d4d4dc;
    border-radius: 6px;
    color: #8e8ea0;
    font-size: 10px;
    font-weight: 600;
}

QPushButton#fav_btn {
    background: transparent;
    border: none;
    font-size: 16px;
    padding: 2px 4px;
    color: #8e8ea0;
}
QPushButton#fav_btn:hover {
    color: #ef4444;
}
QPushButton#fav_btn:checked {
    color: #ef4444;
}

QPushButton#pin_btn {
    background: transparent;
    border: none;
    font-size: 14px;
    padding: 2px 4px;
    color: #8e8ea0;
}
QPushButton#pin_btn:hover {
    color: #f59e0b;
}

QLabel#tag_chip {
    background-color: #e8e8f0;
    color: #555568;
    font-size: 10px;
    font-weight: 600;
    border-radius: 8px;
    padding: 1px 8px;
}

QPushButton#tag_add_btn {
    background: transparent;
    border: 1px solid #d4d4dc;
    border-radius: 8px;
    color: #8e8ea0;
    font-size: 14px;
    font-weight: 700;
    padding: 0;
}
QPushButton#tag_add_btn:hover {
    border-color: #2563eb;
    color: #2563eb;
}

QPushButton#tag_del_btn {
    background: transparent;
    border: none;
    color: #8e8ea0;
    font-size: 10px;
    font-weight: 700;
    padding: 0;
}
QPushButton#tag_del_btn:hover {
    color: #ef4444;
}

QLineEdit#tag_input {
    background-color: #ffffff;
    border: 1px solid #d4d4dc;
    border-radius: 4px;
    color: #1a1a2e;
    font-size: 11px;
    padding: 1px 4px;
}

/* ---- History Filter ---- */
QComboBox#history_filter {
    background-color: #ffffff;
    color: #555568;
    border: 1px solid #d4d4dc;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 11px;
    min-height: 22px;
}

/* ---- Home Page ---- */
QLabel#thumb_label {
    background-color: #f0f0f4;
    border: 1px solid #e0e0e6;
    border-radius: 8px;
}

QFrame#home_divider {
    color: #e0e0e6;
    max-height: 1px;
}

/* ---- Stat Label ---- */
QLabel#stat_label {
    color: #8e8ea0;
    font-size: 12px;
    background: transparent;
}
"""


def get_stylesheet(theme: str = "dark") -> str:
    if theme == "light":
        return LIGHT_STYLESHEET
    return STYLESHEET
