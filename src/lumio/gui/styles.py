# Warm Editorial Theme Colors
WARM_PRIMARY = "#e85d75"  # Warm pink-red
WARM_ACCENT = "#6b46c1"   # Rich purple
WARM_BG_PAPER = "#fdf6f0" # Warm paper white (for light theme)
WARM_BG_DARK = "#1a1625"  # Warm dark background
WARM_TEXT_PRIMARY = "#2d3748"  # Primary text (light theme)
WARM_TEXT_DARK = "#f0e6d9"     # Primary text (dark theme)
WARM_BORDER = "#e2e8f0"   # Border color (light theme)
WARM_BORDER_DARK = "#3a3245"  # Border color (dark theme)

STYLESHEET = """
/* ---- Global ---- */
QMainWindow {
    background-color: """ + WARM_BG_DARK + """;
}

QWidget {
    color: """ + WARM_TEXT_DARK + """;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 13px;
}

QScrollArea > QWidget > QWidget {
    background-color: """ + WARM_BG_DARK + """;
}

/* ---- Labels ---- */
QLabel {
    color: """ + WARM_TEXT_DARK + """;
    font-size: 13px;
    background: transparent;
}

QLabel#accent {
    color: """ + WARM_PRIMARY + """;
    font-size: 15px;
    font-weight: 600;
}

QLabel#muted {
    color: #a89fb0;
    font-size: 12px;
}

QLabel#cache_path {
    color: #c8bfd0;
    font-size: 10px;
    font-family: Consolas, "Courier New", monospace;
}

QLabel#section_title {
    color: """ + WARM_ACCENT + """;
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
    background-color: #251f35;
    color: """ + WARM_TEXT_DARK + """;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    selection-background-color: #4a3a5a;
    min-height: 18px;
}

QLineEdit:focus {
    border: 1px solid """ + WARM_PRIMARY + """;
}

QLineEdit::placeholder {
    color: #8a7d95;
}

QTextEdit, QPlainTextEdit {
    background-color: #251f35;
    color: """ + WARM_TEXT_DARK + """;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 13px;
    font-family: "Cascadia Code", "Consolas", "Microsoft YaHei UI", monospace;
    selection-background-color: #4a3a5a;
}

QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid """ + WARM_PRIMARY + """;
}

/* ---- Buttons ---- */
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_PRIMARY + """, stop:1 """ + WARM_ACCENT + """);
    color: #ffffff;
    border: none;
    border-radius: 12px;
    padding: 8px 22px;
    font-size: 13px;
    font-weight: 600;
    min-height: 18px;
}

QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_ACCENT + """, stop:1 """ + WARM_PRIMARY + """);
    transform: translateY(-2px);
}

QPushButton:pressed {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_PRIMARY + """, stop:1 """ + WARM_ACCENT + """);
    transform: scale(0.98);
}

QPushButton:disabled {
    background-color: #2a2538;
    color: #8a7d95;
}

QPushButton#secondary {
    background-color: #2a2538;
    color: """ + WARM_TEXT_DARK + """;
    border: 2px solid """ + WARM_BORDER_DARK + """;
    border-radius: 12px;
    font-weight: 500;
}

QPushButton#secondary:hover {
    background-color: #352d48;
    border-color: """ + WARM_PRIMARY + """;
    transform: translateY(-2px);
}

QPushButton#secondary:pressed {
    background-color: #201b2d;
    transform: scale(0.98);
}

QPushButton#accent_btn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_PRIMARY + """, stop:1 """ + WARM_ACCENT + """);
    color: #ffffff;
    border: none;
    border-radius: 12px;
    font-weight: 700;
    font-size: 14px;
    padding: 10px 28px;
    min-width: 120px;
}

QPushButton#accent_btn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_ACCENT + """, stop:1 """ + WARM_PRIMARY + """);
    transform: translateY(-2px);
}

QPushButton#accent_btn:pressed {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_PRIMARY + """, stop:1 """ + WARM_ACCENT + """);
    transform: scale(0.98);
}

QPushButton#accent_btn:disabled {
    background-color: #2a2538;
    color: #8a7d95;
}

/* ---- ComboBox ---- */
QComboBox {
    background-color: #251f35;
    color: """ + WARM_TEXT_DARK + """;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 12px;
    padding: 7px 12px;
    font-size: 13px;
    min-height: 18px;
}

QComboBox:hover {
    border-color: """ + WARM_PRIMARY + """;
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
    selection-background-color: #3B5BDB;
    selection-color: #ffffff;
    padding: 4px;
}

/* ---- Progress Bar ---- */
QProgressBar {
    background-color: #2a2538;
    border: 2px solid """ + WARM_BORDER_DARK + """;
    border-radius: 12px;
    text-align: center;
    color: """ + WARM_TEXT_DARK + """;
    font-size: 10px;
    font-weight: 600;
    min-height: 24px;
    max-height: 24px;
    padding: 2px;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_PRIMARY + """, stop:1 """ + WARM_ACCENT + """);
    border-radius: 10px;
}

/* ---- Group Box (Card style) ---- */
QGroupBox {
    background-color: #251f35;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 16px;
    margin-top: 0px;
    padding: 20px 18px 16px 18px;
    font-size: 12px;
    font-weight: 600;
    color: """ + WARM_PRIMARY + """;
    min-width: 0;
}

QGroupBox::title {
    subcontrol-origin: padding;
    subcontrol-position: top left;
    left: 18px;
    top: 6px;
    padding: 0 8px;
    color: """ + WARM_PRIMARY + """;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
    background-color: #251f35;
}

/* ---- ScrollBar ---- */
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: """ + WARM_BORDER_DARK + """;
    border-radius: 5px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: """ + WARM_PRIMARY + """;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}

/* ---- Tooltip ---- */
QToolTip {
    background-color: #2a2538;
    color: """ + WARM_TEXT_DARK + """;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 12px;
}

/* ---- Dialog / MessageBox ---- */
QDialog {
    background-color: #251f35;
}

QMessageBox {
    background-color: #251f35;
}

QMessageBox QLabel {
    color: """ + WARM_TEXT_DARK + """;
    font-size: 13px;
    background: transparent;
}

QMessageBox QPushButton {
    min-width: 80px;
    min-height: 30px;
}

/* ---- Init Page ---- */
QPlainTextEdit#init_log {
    background-color: #1f192b;
    color: """ + WARM_TEXT_DARK + """;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 8px;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 12px;
    padding: 10px;
}

/* ---- Cookie Banner ---- */
QFrame#cookie_banner {
    background-color: #2a2538;
    border-left: 3px solid """ + WARM_PRIMARY + """;
    border-radius: 8px;
    padding: 8px 12px;
}

QLabel#banner_text {
    color: """ + WARM_PRIMARY + """;
    font-size: 13px;
    background: transparent;
}

QPushButton#banner_close {
    background: transparent;
    color: """ + WARM_TEXT_DARK + """;
    border: none;
    font-size: 16px;
    font-weight: bold;
    padding: 2px 6px;
}

QPushButton#banner_close:hover {
    color: #ffffff;
}

/* ---- Cookie Status Indicator ---- */
QLabel#cookie_ok {
    color: #34d399;
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
    color: """ + WARM_PRIMARY + """;
    font-size: 12px;
    font-weight: 600;
    background: transparent;
}

QLabel#queue_badge {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_PRIMARY + """, stop:1 """ + WARM_ACCENT + """);
    color: #ffffff;
    font-size: 11px;
    font-weight: 700;
    border-radius: 10px;
    padding: 1px 8px;
    min-width: 20px;
}

/* ---- Queue Task Card ---- */
QFrame#task_card {
    background-color: #251f35;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 12px;
    padding: 4px;
}

QLabel#task_title {
    color: """ + WARM_TEXT_DARK + """;
    font-size: 12px;
    font-weight: 500;
    background: transparent;
}

QLabel#task_speed {
    color: #a89fb0;
    font-size: 10px;
    background: transparent;
}

/* ---- Status Badges ---- */
QLabel#badge_waiting {
    background-color: #3a3245;
    color: #c8bfd0;
    font-size: 10px;
    font-weight: 600;
    border-radius: 6px;
    padding: 1px 6px;
}

QLabel#badge_retrying {
    background-color: #4a2d38;
    color: """ + WARM_PRIMARY + """;
    font-size: 10px;
    font-weight: 600;
    border-radius: 6px;
    padding: 1px 6px;
}

QLabel#badge_interrupted {
    background-color: #2d254a;
    color: """ + WARM_ACCENT + """;
    font-size: 10px;
    font-weight: 600;
    border-radius: 6px;
    padding: 1px 6px;
}

QLabel#badge_downloading {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_PRIMARY + """, stop:1 """ + WARM_ACCENT + """);
    color: #ffffff;
    font-size: 10px;
    font-weight: 600;
    border-radius: 6px;
    padding: 1px 6px;
}

QLabel#badge_paused {
    background-color: #4a2d38;
    color: """ + WARM_PRIMARY + """;
    font-size: 10px;
    font-weight: 600;
    border-radius: 6px;
    padding: 1px 6px;
}

QLabel#badge_completed {
    background-color: #1a3a2d;
    color: #34d399;
    font-size: 10px;
    font-weight: 600;
    border-radius: 6px;
    padding: 1px 6px;
}

QLabel#badge_failed {
    background-color: #4a2525;
    color: #ef4444;
    font-size: 10px;
    font-weight: 600;
    border-radius: 6px;
    padding: 1px 6px;
}

QLabel#badge_cancelled {
    background-color: #2a2538;
    color: #a89fb0;
    font-size: 10px;
    font-weight: 600;
    border-radius: 6px;
    padding: 1px 6px;
}

/* ---- Platform Badge ---- */
QLabel#platform_yt {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_PRIMARY + """, stop:1 """ + WARM_ACCENT + """);
    color: #ffffff;
    font-size: 9px;
    font-weight: 700;
    border-radius: 6px;
    padding: 0px 4px;
}

QLabel#platform_ig {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_PRIMARY + """, stop:1 #e1306c);
    color: #ffffff;
    font-size: 9px;
    font-weight: 700;
    border-radius: 6px;
    padding: 0px 4px;
}

QLabel#platform_x {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_ACCENT + """, stop:1 #1d9bf0);
    color: #ffffff;
    font-size: 9px;
    font-weight: 700;
    border-radius: 6px;
    padding: 0px 4px;
}

QLabel#history_badge {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_PRIMARY + """, stop:1 """ + WARM_ACCENT + """);
    color: #ffffff;
    font-size: 11px;
    font-weight: 700;
    border-radius: 10px;
    padding: 1px 8px;
    min-width: 20px;
}

QLineEdit#history_search {
    background-color: #251f35;
    color: """ + WARM_TEXT_DARK + """;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 8px;
    padding: 3px 8px;
    font-size: 11px;
    min-height: 18px;
}

QLineEdit#history_search:focus {
    border: 1px solid """ + WARM_PRIMARY + """;
}

/* ---- History Card ---- */
QFrame#history_card {
    background-color: #251f35;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 12px;
    padding: 4px;
}

QFrame#history_card:hover {
    border-color: """ + WARM_PRIMARY + """;
    transform: translateY(-2px);
}

/* ---- Library Card ---- */
QFrame#library_card {
    background-color: #251f35;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 12px;
    padding: 4px;
}

QFrame#library_card:hover {
    border-color: """ + WARM_PRIMARY + """;
    transform: translateY(-2px);
}

QLabel#library_card_thumb {
    background-color: #1f192b;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 8px;
    color: #a89fb0;
    font-size: 10px;
    font-weight: 600;
}

QPushButton#fav_btn {
    background: transparent;
    border: none;
    font-size: 16px;
    padding: 2px 4px;
    color: #a89fb0;
}
QPushButton#fav_btn:hover {
    color: """ + WARM_PRIMARY + """;
}
QPushButton#fav_btn:checked {
    color: """ + WARM_PRIMARY + """;
}

QPushButton#icon_add_btn {
    background: transparent;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 8px;
    color: #a89fb0;
    font-size: 14px;
    font-weight: 700;
    padding: 0;
}
QPushButton#icon_add_btn:hover {
    border-color: """ + WARM_PRIMARY + """;
    color: """ + WARM_PRIMARY + """;
}

/* ---- Media Type Badges ---- */
QLabel#media_video {
    background-color: """ + WARM_ACCENT + """;
    color: #ffffff;
    font-size: 9px;
    font-weight: 700;
    border-radius: 6px;
    padding: 0px 4px;
}

QLabel#media_audio {
    background-color: #fbbf24;
    color: #ffffff;
    font-size: 9px;
    font-weight: 700;
    border-radius: 6px;
    padding: 0px 4px;
}

QLabel#media_image {
    background-color: #34d399;
    color: #ffffff;
    font-size: 9px;
    font-weight: 700;
    border-radius: 6px;
    padding: 0px 4px;
}

QLabel#media_mixed {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_PRIMARY + """, stop:1 """ + WARM_ACCENT + """);
    color: #ffffff;
    font-size: 9px;
    font-weight: 700;
    border-radius: 6px;
    padding: 0px 4px;
}

/* ---- Task Action Buttons ---- */
QPushButton#task_btn {
    background-color: #2a2538;
    color: """ + WARM_TEXT_DARK + """;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 10px;
    min-height: 20px;
}

QPushButton#task_btn:hover {
    background-color: #352d48;
    border-color: """ + WARM_PRIMARY + """;
}

QPushButton#task_btn_danger {
    background-color: #2a2538;
    color: #ef4444;
    border: 1px solid #4a2525;
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 10px;
    min-height: 20px;
}

QPushButton#task_btn_danger:hover {
    background-color: #3a2020;
}

/* ---- Toast Notification ---- */
QLabel#toast {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_PRIMARY + """, stop:1 """ + WARM_ACCENT + """);
    color: #ffffff;
    font-size: 13px;
    font-weight: 600;
    border-radius: 8px;
    padding: 8px 16px;
}

/* ---- Sidebar ---- */
QFrame#sidebar {
    background-color: #1f192b;
    border-right: 1px solid """ + WARM_BORDER_DARK + """;
}

QFrame#sidebar_sep_line {
    background-color: """ + WARM_BORDER_DARK + """;
    border: none;
    max-width: 1px;
}

QStackedWidget#content_area {
    background-color: """ + WARM_BG_DARK + """;
}

QWidget#home_page, QWidget#downloads_page, QWidget#history_page,
QWidget#stats_page, QWidget#settings_page, QWidget#library_page {
    background-color: """ + WARM_BG_DARK + """;
}

QLabel#sidebar_logo {
    color: """ + WARM_PRIMARY + """;
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 2px;
    padding: 4px 0;
    background: transparent;
}

QLabel#sidebar_sep {
    color: """ + WARM_ACCENT + """;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    padding: 0 12px;
    background: transparent;
}

QLabel#sidebar_version {
    color: #a89fb0;
    font-size: 10px;
    background: transparent;
}

QPushButton#nav_btn {
    background-color: transparent;
    color: """ + WARM_TEXT_DARK + """;
    border: none;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    font-weight: 500;
    text-align: left;
}

QPushButton#nav_btn:hover {
    background-color: #251f35;
    color: #ffffff;
}

QPushButton#nav_btn:checked {
    background-color: #251f35;
    color: #ffffff;
    border-left: 3px solid """ + WARM_PRIMARY + """;
    padding-left: 9px;
}

QPushButton#nav_btn_disabled {
    background-color: transparent;
    color: #a89fb0;
    border: none;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    font-weight: 500;
    text-align: left;
}

/* ---- Page Title ---- */
QLabel#page_title {
    color: """ + WARM_TEXT_DARK + """;
    font-size: 18px;
    font-weight: 700;
    background: transparent;
}

/* ---- Stat Card ---- */
QWidget#stat_card {
    background-color: #251f35;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 16px;
}

QWidget#stat_card:hover {
    border-color: """ + WARM_PRIMARY + """;
    transform: translateY(-2px);
}

/* ---- History Filter ---- */
QComboBox#history_filter {
    background-color: #251f35;
    color: """ + WARM_TEXT_DARK + """;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 8px;
    padding: 4px 8px 4px 16px;
    font-size: 11px;
    min-height: 22px;
}

/* ---- Home Page ---- */
QLabel#thumb_label {
    background-color: #1f192b;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 12px;
}

QFrame#home_divider {
    color: """ + WARM_BORDER_DARK + """;
    max-height: 1px;
}

/* ---- Home Page Hero ---- */
QFrame#home_hero {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #2a2538, stop:0.5 #251f35, stop:1 """ + WARM_BG_DARK + """);
    border: none;
    border-radius: 0px;
}

QLabel#hero_title {
    color: """ + WARM_TEXT_DARK + """;
    font-size: 28px;
    font-weight: 800;
    background: transparent;
}

QLabel#hero_subtitle {
    color: #a89fb0;
    font-size: 13px;
    background: transparent;
}

/* ---- Platform Pills ---- */
QPushButton#platform_pill {
    background-color: #251f35;
    color: """ + WARM_TEXT_DARK + """;
    border: 2px solid """ + WARM_BORDER_DARK + """;
    border-radius: 20px;
    padding: 6px 16px;
    font-size: 12px;
    font-weight: 600;
    min-height: 18px;
}

QPushButton#platform_pill:hover {
    border-color: """ + WARM_PRIMARY + """;
    color: #ffffff;
}

/* ---- Input Card ---- */
QFrame#input_card {
    background-color: #251f35;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 16px;
}

QPlainTextEdit#home_url_input {
    background-color: #1f192b;
    color: """ + WARM_TEXT_DARK + """;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 12px;
    padding: 12px 16px;
    font-size: 14px;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
}

QPlainTextEdit#home_url_input:focus {
    border: 1px solid """ + WARM_PRIMARY + """;
}

QPushButton#home_parse_btn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_PRIMARY + """, stop:1 """ + WARM_ACCENT + """);
    color: #ffffff;
    border: none;
    border-radius: 12px;
    padding: 10px 22px;
    font-size: 13px;
    font-weight: 700;
}

QPushButton#home_parse_btn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_ACCENT + """, stop:1 """ + WARM_PRIMARY + """);
    transform: translateY(-2px);
}

QPushButton#home_parse_btn:pressed {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_PRIMARY + """, stop:1 """ + WARM_ACCENT + """);
    transform: scale(0.98);
}

/* ---- Capability Tags ---- */
QLabel#capability_tag {
    background-color: #251f35;
    color: #a89fb0;
    font-size: 11px;
    border-radius: 12px;
    padding: 3px 12px;
}

/* ---- Preview Empty State ---- */
QFrame#preview_empty {
    background-color: #1f192b;
    border: 2px dashed """ + WARM_BORDER_DARK + """;
    border-radius: 16px;
}

QLabel#preview_empty_icon {
    color: """ + WARM_ACCENT + """;
    font-size: 32px;
    background: transparent;
}

QLabel#preview_empty_text {
    color: #a89fb0;
    font-size: 13px;
    background: transparent;
}

QLabel#preview_info_title {
    color: """ + WARM_TEXT_DARK + """;
    font-size: 14px;
    font-weight: 600;
    background: transparent;
}

QLabel#preview_info_meta {
    color: #a89fb0;
    font-size: 12px;
    background: transparent;
}

QLabel#preview_thumb {
    background-color: #1f192b;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 12px;
}
/* ---- Media Items Preview Strip ---- */
QScrollArea#media_items_scroll {
    background-color: transparent;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 8px;
}
QScrollArea#media_items_scroll > QWidget > QWidget {
    background-color: transparent;
}
QFrame#media_item_card {
    background-color: #251f35;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 12px;
}
QFrame#media_item_card:hover {
    border: 1px solid """ + WARM_PRIMARY + """;
    background-color: #352d48;
    transform: translateY(-2px);
}
QFrame#media_item_card[selected="true"] {
    border: 1px solid """ + WARM_PRIMARY + """;
    background-color: #3a284d;
}
QFrame#media_item_card[added="true"] {
    border: 1px solid #34d399;
    background-color: #1a3a2d;
}
QLabel#media_item_thumb {
    background-color: #1f192b;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 8px;
    color: #a89fb0;
    font-size: 28px;
}
QLabel#media_item_type_label {
    color: """ + WARM_TEXT_DARK + """;
    font-size: 11px;
    font-weight: 600;
    background: transparent;
}
QPushButton#media_item_add_btn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_PRIMARY + """, stop:1 """ + WARM_ACCENT + """);
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 11px;
    font-weight: 600;
}
QPushButton#media_item_add_btn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_ACCENT + """, stop:1 """ + WARM_PRIMARY + """);
    transform: translateY(-2px);
}
QPushButton#media_item_add_btn:disabled {
    background-color: #34d399;
    color: #ffffff;
}
QFrame#media_item_card[added="true"] QPushButton#media_item_add_btn {
    background-color: #34d399;
}

/* ---- Format Download Row ---- */
QFrame#format_row {
    background-color: #251f35;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 16px;
}

QLineEdit#home_name_input {
    background-color: #251f35;
    color: """ + WARM_TEXT_DARK + """;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 12px;
    padding: 10px 14px;
    font-size: 13px;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
}

QLineEdit#home_name_input:focus {
    border: 1px solid """ + WARM_PRIMARY + """;
}

QPushButton#home_download_btn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_PRIMARY + """, stop:1 """ + WARM_ACCENT + """);
    color: #ffffff;
    border: none;
    border-radius: 12px;
    padding: 10px 22px;
    font-size: 13px;
    font-weight: 700;
    min-width: 120px;
}

QPushButton#home_download_btn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_ACCENT + """, stop:1 """ + WARM_PRIMARY + """);
    transform: translateY(-2px);
}

QPushButton#home_download_btn:disabled {
    background-color: #2a2538;
    color: #8a7d95;
}


/* ---- Search Results ---- */
QScrollArea#search_scroll {
    background-color: #1f192b;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 8px;
}

QLabel#search_thumb {
    background-color: #251f35;
    border-radius: 6px;
}



/* ---- Toolbar Buttons (Dark) ---- */
QPushButton#tool_btn {
    background-color: transparent;
    color: #a89fb0;
    border: none;
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 12px;
}

QPushButton#tool_btn:hover {
    color: #ffffff;
    background-color: #2a2538;
}

QPushButton#paste_btn {
    background-color: transparent;
    color: """ + WARM_TEXT_DARK + """;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 12px;
    padding: 8px 16px;
    font-size: 12px;
    font-weight: 600;
}

QPushButton#paste_btn:hover {
    color: #ffffff;
    border-color: """ + WARM_PRIMARY + """;
    background-color: #2a2538;
}

QPushButton#search_btn {
    background-color: transparent;
    color: """ + WARM_TEXT_DARK + """;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 12px;
    padding: 8px 16px;
    font-size: 12px;
    font-weight: 600;
}

QPushButton#search_btn:hover {
    color: #ffffff;
    border-color: """ + WARM_PRIMARY + """;
    background-color: #2a2538;
}

/* ---- Toolbar Hint (Dark) ---- */
QLabel#toolbar_hint {
    color: #a89fb0;
    font-size: 11px;
    background: transparent;
}

/* ---- Section Header (Dark) ---- */
QLabel#section_header {
    color: """ + WARM_ACCENT + """;
    font-size: 11px;
    font-weight: 700;
    background: transparent;
}

/* ---- Stat Label ---- */
QLabel#stat_label {
    color: #a89fb0;
    font-size: 12px;
    background: transparent;
}

QSpinBox {
    background: #251f35;
    border: 1px solid """ + WARM_BORDER_DARK + """;
    border-radius: 6px;
    color: """ + WARM_TEXT_DARK + """;
    font-size: 12px;
    padding: 2px 6px;
}
QSpinBox:focus {
    border: 1px solid """ + WARM_PRIMARY + """;
}
QSpinBox::up-button, QSpinBox::down-button {
    width: 16px;
    border: none;
    background: transparent;
    color: """ + WARM_TEXT_DARK + """;
}

/* ---- URL Link Label ---- */
QLabel#url_link {
    color: """ + WARM_PRIMARY + """;
    font-size: 11px;
}

/* ---- Batch Progress ---- */
QLabel#batch_progress {
    font-size: 11px;
    margin-left: 4px;
    color: #a89fb0;
}

QLabel#batch_progress_done {
    font-size: 11px;
    margin-left: 4px;
    color: #34d399;
}
"""

LIGHT_STYLESHEET = """
/* ---- Global ---- */
QMainWindow {
    background-color: """ + WARM_BG_PAPER + """;
}

QWidget {
    color: """ + WARM_TEXT_PRIMARY + """;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 13px;
}

QScrollArea > QWidget > QWidget {
    background-color: """ + WARM_BG_PAPER + """;
}

/* ---- Labels ---- */
QLabel {
    color: """ + WARM_TEXT_PRIMARY + """;
    font-size: 13px;
    background: transparent;
}

QLabel#accent {
    color: """ + WARM_PRIMARY + """;
    font-size: 15px;
    font-weight: 600;
}

QLabel#muted {
    color: #6b7280;
    font-size: 12px;
}

QLabel#cache_path {
    color: #4a5568;
    font-size: 10px;
    font-family: Consolas, "Courier New", monospace;
}

QLabel#section_title {
    color: """ + WARM_ACCENT + """;
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
    color: """ + WARM_TEXT_PRIMARY + """;
    border: 1px solid """ + WARM_BORDER + """;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    selection-background-color: #f0e6f5;
    min-height: 18px;
}

QLineEdit:focus {
    border: 1px solid """ + WARM_PRIMARY + """;
}

QLineEdit::placeholder {
    color: #94a3b8;
}

QTextEdit, QPlainTextEdit {
    background-color: #ffffff;
    color: """ + WARM_TEXT_PRIMARY + """;
    border: 1px solid """ + WARM_BORDER + """;
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 13px;
    font-family: "Cascadia Code", "Consolas", "Microsoft YaHei UI", monospace;
    selection-background-color: #f0e6f5;
}

QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid """ + WARM_PRIMARY + """;
}

/* ---- Buttons ---- */
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_PRIMARY + """, stop:1 """ + WARM_ACCENT + """);
    color: #ffffff;
    border: none;
    border-radius: 12px;
    padding: 8px 22px;
    font-size: 13px;
    font-weight: 600;
    min-height: 18px;
}

QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_ACCENT + """, stop:1 """ + WARM_PRIMARY + """);
    transform: translateY(-2px);
}

QPushButton:pressed {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_PRIMARY + """, stop:1 """ + WARM_ACCENT + """);
    transform: scale(0.98);
}

QPushButton:disabled {
    background-color: #f1f2f6;
    color: #94a3b8;
}

QPushButton#secondary {
    background-color: #f1f2f6;
    color: """ + WARM_TEXT_PRIMARY + """;
    border: 2px solid """ + WARM_BORDER + """;
    border-radius: 12px;
    font-weight: 500;
}

QPushButton#secondary:hover {
    background-color: #e2e3e8;
    border-color: """ + WARM_PRIMARY + """;
    transform: translateY(-2px);
}

QPushButton#secondary:pressed {
    background-color: #d8d9de;
    transform: scale(0.98);
}

QPushButton#accent_btn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_PRIMARY + """, stop:1 """ + WARM_ACCENT + """);
    color: #ffffff;
    border: none;
    border-radius: 12px;
    font-weight: 700;
    font-size: 14px;
    padding: 10px 28px;
    min-width: 120px;
}

QPushButton#accent_btn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_ACCENT + """, stop:1 """ + WARM_PRIMARY + """);
    transform: translateY(-2px);
}

QPushButton#accent_btn:pressed {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_PRIMARY + """, stop:1 """ + WARM_ACCENT + """);
    transform: scale(0.98);
}

QPushButton#accent_btn:disabled {
    background-color: #f1f2f6;
    color: #94a3b8;
}

/* ---- ComboBox ---- */
QComboBox {
    background-color: #ffffff;
    color: """ + WARM_TEXT_PRIMARY + """;
    border: 1px solid """ + WARM_BORDER + """;
    border-radius: 12px;
    padding: 7px 12px;
    font-size: 13px;
    min-height: 18px;
}

QComboBox:hover {
    border-color: """ + WARM_PRIMARY + """;
}

QComboBox::drop-down {
    border: none;
    width: 28px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #6b7280;
    margin-right: 8px;
}

QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: """ + WARM_TEXT_PRIMARY + """;
    border: 1px solid """ + WARM_BORDER + """;
    border-radius: 6px;
    selection-background-color: """ + WARM_PRIMARY + """;
    selection-color: #ffffff;
    padding: 4px;
}

/* ---- Progress Bar ---- */
QProgressBar {
    background-color: #f1f2f6;
    border: 2px solid """ + WARM_BORDER + """;
    border-radius: 12px;
    text-align: center;
    color: """ + WARM_TEXT_PRIMARY + """;
    font-size: 10px;
    font-weight: 600;
    min-height: 24px;
    max-height: 24px;
    padding: 2px;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 """ + WARM_PRIMARY + """, stop:1 """ + WARM_ACCENT + """);
    border-radius: 10px;
}

/* ---- Group Box (Card style) ---- */
QGroupBox {
    background-color: #ffffff;
    border: 1px solid """ + WARM_BORDER + """;
    border-radius: 16px;
    margin-top: 0px;
    padding: 20px 18px 16px 18px;
    font-size: 12px;
    font-weight: 600;
    color: """ + WARM_PRIMARY + """;
}

QGroupBox::title {
    subcontrol-origin: padding;
    subcontrol-position: top left;
    left: 18px;
    top: 6px;
    padding: 0 8px;
    color: """ + WARM_PRIMARY + """;
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

QLabel#queue_badge {
    background-color: #3B5BDB;
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
    color: #3B5BDB;
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
    background-color: #3B5BDB;
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
    color: #3B5BDB;
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
    border-left: 3px solid #3B5BDB;
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
    border-color: #3B5BDB;
}

QLabel#history_badge {
    background-color: #3B5BDB;
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
    border: 1px solid #3B5BDB;
}

/* ---- History Card ---- */
QFrame#history_card {
    background-color: #ffffff;
    border: 1px solid #e0e0e6;
    border-radius: 6px;
    padding: 4px;
}

QFrame#history_card:hover {
    border-color: #3B5BDB;
}

/* ---- Library Card (Light) ---- */
QFrame#library_card {
    background-color: #ffffff;
    border: 1px solid #e0e0e6;
    border-radius: 6px;
    padding: 4px;
}

QFrame#library_card:hover {
    border-color: #3B5BDB;
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

QPushButton#icon_add_btn {
    background: transparent;
    border: 1px solid #d4d4dc;
    border-radius: 8px;
    color: #8e8ea0;
    font-size: 14px;
    font-weight: 700;
    padding: 0;
}
QPushButton#icon_add_btn:hover {
    border-color: #3B5BDB;
    color: #3B5BDB;
}

/* ---- History Filter ---- */
QComboBox#history_filter {
    background-color: #ffffff;
    color: #555568;
    border: 1px solid #d4d4dc;
    border-radius: 6px;
    padding: 4px 8px 4px 16px;
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

/* ---- Home Page Hero ---- */
QFrame#home_hero {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #EEF1F8, stop:0.5 #F8F9FC, stop:1 #FFFFFF);
    border: none;
    border-radius: 0px;
}

QLabel#hero_title {
    color: #1a1a2e;
    font-size: 28px;
    font-weight: 800;
    background: transparent;
}

QLabel#hero_subtitle {
    color: #6b7280;
    font-size: 13px;
    background: transparent;
}

/* ---- Platform Pills ---- */
QPushButton#platform_pill {
    background-color: #ffffff;
    color: #1a1d27;
    border: 2px solid #d4d4dc;
    border-radius: 20px;
    padding: 6px 16px;
    font-size: 12px;
    font-weight: 600;
    min-height: 18px;
}

QPushButton#platform_pill:hover {
    border-color: #3B5BDB;
    color: #1a1d27;
}

/* ---- Input Card ---- */
QFrame#input_card {
    background-color: #ffffff;
    border: 1px solid #d4d4dc;
    border-radius: 16px;
}

QPlainTextEdit#home_url_input {
    background-color: #f5f5f7;
    color: #1a1a2e;
    border: 1px solid #d4d4dc;
    border-radius: 12px;
    padding: 12px 16px;
    font-size: 14px;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
}

QPlainTextEdit#home_url_input:focus {
    border: 1px solid #3B5BDB;
}

QPushButton#home_parse_btn {
    background-color: #1a1a2e;
    color: #ffffff;
    border: 1px solid #2a2e3a;
    border-radius: 12px;
    padding: 10px 22px;
    font-size: 13px;
    font-weight: 700;
}

QPushButton#home_parse_btn:hover {
    background-color: #2a2e3a;
}

QPushButton#home_parse_btn:pressed {
    background-color: #0f1117;
}

/* ---- Capability Tags ---- */
QLabel#capability_tag {
    background-color: #e8e8ee;
    color: #8e8ea0;
    font-size: 11px;
    border-radius: 12px;
    padding: 3px 12px;
}

/* ---- Preview Empty State ---- */
QFrame#preview_empty {
    background-color: #f5f5f7;
    border: 2px dashed #d4d4dc;
    border-radius: 16px;
}

QLabel#preview_empty_icon {
    color: #b0b0c0;
    font-size: 32px;
    background: transparent;
}

QLabel#preview_empty_text {
    color: #8e8ea0;
    font-size: 13px;
    background: transparent;
}

QLabel#preview_info_title {
    color: #1a1a2e;
    font-size: 14px;
    font-weight: 600;
    background: transparent;
}

QLabel#preview_info_meta {
    color: #8e8ea0;
    font-size: 12px;
    background: transparent;
}

QLabel#preview_thumb {
    background-color: #f0f0f4;
    border: 1px solid #e0e0e6;
    border-radius: 12px;
}
/* ---- Media Items Preview Strip ---- */
QScrollArea#media_items_scroll {
    background-color: transparent;
    border: 1px solid #e0e0e6;
    border-radius: 8px;
}
QScrollArea#media_items_scroll > QWidget > QWidget {
    background-color: transparent;
}
QFrame#media_item_card {
    background-color: #f8f8fa;
    border: 1px solid #e0e0e6;
    border-radius: 8px;
}
QFrame#media_item_card:hover {
    border: 1px solid #3B5BDB;
    background-color: #EDF2FF;
}
QFrame#media_item_card[selected="true"] {
    border: 1px solid #3B5BDB;
    background-color: #DDE6FF;
}
QFrame#media_item_card[added="true"] {
    border: 1px solid #10b981;
    background-color: #ECFDF5;
}
QLabel#media_item_thumb {
    background-color: #e8e8ee;
    border: 1px solid #d4d4dc;
    border-radius: 6px;
    color: #666680;
    font-size: 28px;
}
QLabel#media_item_type_label {
    color: #555568;
    font-size: 11px;
    font-weight: 600;
    background: transparent;
}
QPushButton#media_item_add_btn {
    background-color: #3B5BDB;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 11px;
    font-weight: 600;
}
QPushButton#media_item_add_btn:hover {
    background-color: #2c47b8;
}
QPushButton#media_item_add_btn:disabled {
    background-color: #10b981;
    color: #ffffff;
}
QFrame#media_item_card[added="true"] QPushButton#media_item_add_btn {
    background-color: #10b981;
}

/* ---- Format Download Row ---- */
QFrame#format_row {
    background-color: #ffffff;
    border: 1px solid #d4d4dc;
    border-radius: 16px;
}

QLineEdit#home_name_input {
    background-color: #f5f5f7;
    color: #1a1a2e;
    border: 1px solid #d4d4dc;
    border-radius: 12px;
    padding: 10px 14px;
    font-size: 13px;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
}

QLineEdit#home_name_input:focus {
    border: 1px solid #3B5BDB;
}

QPushButton#home_download_btn {
    background-color: #3B5BDB;
    color: #ffffff;
    border: 1px solid #4F6FEF;
    border-radius: 12px;
    padding: 10px 22px;
    font-size: 13px;
    font-weight: 700;
    min-width: 120px;
}

QPushButton#home_download_btn:hover {
    background-color: #4F6FEF;
}

QPushButton#home_download_btn:disabled {
    background-color: #e8e8ee;
    color: #b0b0c0;
}


/* ---- Search Results ---- */
QScrollArea#search_scroll {
    background-color: #f8f8fa;
    border: 1px solid #e0e0e6;
    border-radius: 8px;
}

QLabel#search_thumb {
    background-color: #e8e8ee;
    border-radius: 4px;
}



/* ---- Toolbar Buttons (Light) ---- */
QPushButton#tool_btn {
    background-color: transparent;
    color: #8e8ea0;
    border: none;
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 12px;
}

QPushButton#tool_btn:hover {
    color: #1a1a2e;
    background-color: #f0f0f4;
}

QPushButton#paste_btn {
    background-color: transparent;
    color: #6b7280;
    border: 1px solid #d4d4dc;
    border-radius: 12px;
    padding: 8px 16px;
    font-size: 12px;
    font-weight: 600;
}

QPushButton#paste_btn:hover {
    color: #1a1a2e;
    border-color: #3B5BDB;
    background-color: #EDF2FF;
}

QPushButton#search_btn {
    background-color: transparent;
    color: #6b7280;
    border: 1px solid #d4d4dc;
    border-radius: 12px;
    padding: 8px 16px;
    font-size: 12px;
    font-weight: 600;
}

QPushButton#search_btn:hover {
    color: #1a1a2e;
    border-color: #3B5BDB;
    background-color: #EDF2FF;
}

/* ---- Toolbar Hint (Light) ---- */
QLabel#toolbar_hint {
    color: #8e8ea0;
    font-size: 11px;
    background: transparent;
}

/* ---- Section Header (Light) ---- */
QLabel#section_header {
    color: #8e8ea0;
    font-size: 11px;
    font-weight: 700;
    background: transparent;
}

/* ---- Stat Label ---- */
QLabel#stat_label {
    color: #8e8ea0;
    font-size: 12px;
    background: transparent;
}

QSpinBox {
    background: #ffffff;
    border: 1px solid #d4d4dc;
    border-radius: 4px;
    color: #1a1a2e;
    font-size: 12px;
    padding: 2px 6px;
}
QSpinBox:focus {
    border: 1px solid #3B5BDB;
}
QSpinBox::up-button, QSpinBox::down-button {
    width: 16px;
    border: none;
    background: transparent;
}

/* ---- URL Link Label ---- */
QLabel#url_link {
    color: #3B5BDB;
    font-size: 11px;
}

/* ---- Batch Progress ---- */
QLabel#batch_progress {
    font-size: 11px;
    margin-left: 4px;
    color: #555568;
}

QLabel#batch_progress_done {
    font-size: 11px;
    margin-left: 4px;
    color: #065f46;
}
"""


def get_stylesheet(theme: str = "dark") -> str:
    if theme == "light":
        return LIGHT_STYLESHEET
    return STYLESHEET
