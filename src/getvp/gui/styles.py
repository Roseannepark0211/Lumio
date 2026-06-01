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
"""
