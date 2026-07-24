from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize, QPointF, QRectF
from PySide6.QtGui import (
    QColor, QLinearGradient, QPainter, QPaintEvent, QPen, QBrush,
    QRadialGradient, QIcon,
)
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout, QWidget
)

from ..i18n import t
from .theme import icons as _icons
from .theme import tokens as T


# ============================================================
# NavButton — 带 SVG 图标的导航按钮
# ============================================================
class NavButton(QPushButton):
    """侧边栏导航按钮，使用 SVG 图标替代 Unicode 字符。

    图标 + 文字布局由 QSS 控制，选中态显示左侧 accent 条 + 玻璃高亮。
    支持 badge 数字（用于通知）。
    """

    def __init__(self, icon_name: str, label: str, page_id: str, parent=None):
        super().__init__(parent)
        self.page_id = page_id
        self._label_text = label
        self._icon_name = icon_name
        self._badge_count = 0
        self.setObjectName("nav_btn")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self.setFixedHeight(40)
        self.setText(label)
        self._refresh_icon()

    def _refresh_icon(self):
        """根据 checked 状态切换图标颜色（选中=主色，未选中=mute）。"""
        # QSS 控制文字颜色，但 QIcon 颜色需要 Python 端切换
        # 用 mute 色作为默认，选中时主色由 stylesheet 视觉强调（左侧条 + 背景）
        color = "#ffffff"  # placeholder, 实际颜色根据主题动态计算
        try:
            from ..utils.config import load_config
            theme = load_config().get("theme", "dark")
            tokens = T.get_tokens(theme)
            color = tokens["text_primary"] if self.isChecked() else tokens["text_mute"]
        except Exception:
            pass
        self.setIcon(_icons.icon(self._icon_name, size=18, color=color))
        self.setIconSize(QSize(18, 18))

    def set_badge(self, count: int):
        """设置数字 badge（用于通知）。"""
        self._badge_count = count
        # 用文字后缀简单实现，QSS 中已支持 (N) 样式
        if count > 0:
            self.setText(f"{self._label_text}  {count}")
        else:
            self.setText(self._label_text)

    def setChecked(self, checked: bool):
        """重写以触发图标颜色刷新。"""
        super().setChecked(checked)
        self._refresh_icon()

    def paintEvent(self, event: QPaintEvent):
        """重写 paintEvent：选中态绘制 3px 渐变竖条 + accent 辉光。"""
        super().paintEvent(event)
        if not self.isChecked():
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # 指示器参数（与设计稿 .nav-item.active::before 一致）
        bar_x = 5          # left: 4px (从边缘缩进)
        bar_w = 3          # width: 3px
        bar_h = 16         # height: 16px
        bar_y = (h - bar_h) / 2

        # 绘制辉光（box-shadow: 0 0 8px accent-soft）
        glow_radius = 8
        glow_grad = QRadialGradient(
            QPointF(bar_x + bar_w / 2, bar_y + bar_h / 2),
            glow_radius,
        )
        glow_grad.setColorAt(0.0, QColor(10, 132, 255, 80))
        glow_grad.setColorAt(1.0, QColor(10, 132, 255, 0))
        p.setBrush(QBrush(glow_grad))
        p.setPen(QPen(Qt.PenStyle.NoPen))
        p.drawEllipse(
            QRectF(
                bar_x + bar_w / 2 - glow_radius,
                bar_y + bar_h / 2 - glow_radius,
                glow_radius * 2,
                glow_radius * 2,
            )
        )

        # 绘制渐变竖条（linear-gradient(180deg, accent, accent_2)）
        bar_grad = QLinearGradient(bar_x, bar_y, bar_x, bar_y + bar_h)
        bar_grad.setColorAt(0.0, QColor(T.DARK["accent"]))
        bar_grad.setColorAt(1.0, QColor(T.DARK["accent_2"]))
        p.setBrush(QBrush(bar_grad))
        p.setPen(QPen(Qt.PenStyle.NoPen))
        # 圆角矩形（border-radius: 2px）
        p.drawRoundedRect(
            QRectF(bar_x, bar_y, bar_w, bar_h),
            2, 2,
        )


# ============================================================
# SidebarWidget — Liquid Glass 风格侧边栏
# ============================================================
class SidebarWidget(QFrame):
    """侧边栏：Logo + 导航 + Collections + 主题切换 + 版本号。

    保留所有原 signal 接口，window.py 无需改动：
        - navigation_changed(str)
        - theme_toggle_requested()
        - notification_clicked()
        - collection_selected(int)
        - collection_create_requested()
        - collection_rename_requested(int)
        - collection_delete_requested(int)
    """

    navigation_changed = Signal(str)               # page_id
    theme_toggle_requested = Signal()
    notification_clicked = Signal()                # bell clicked
    collection_selected = Signal(int)              # collection_id
    collection_create_requested = Signal()
    collection_rename_requested = Signal(int)      # collection_id
    collection_delete_requested = Signal(int)      # collection_id

    # 导航项：(icon_name, i18n_key, page_id)
    NAV_ITEMS = [
        ("i-home",          "home",          "home"),
        ("i-inbox",         "inbox",         "inbox"),
        ("i-download",      "downloads",     "downloads"),
        ("i-history",       "history",       "history"),
        ("i-library",       "library",       "library"),
        ("i-stats",         "stats",         "stats"),
        ("i-bell",          "notifications", "notifications"),
        ("i-settings",      "settings",      "settings"),
    ]

    def __init__(self, theme: str = "dark", parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(220)
        self._theme = theme
        self._nav_buttons: dict[str, NavButton] = {}
        self._collection_buttons: dict[int, QPushButton] = {}
        self._collections_list = QVBoxLayout()
        self._build_ui()

    # ---------- UI 构建 ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 20, 12, 16)
        root.setSpacing(4)

        # ---- Logo ----
        root.addWidget(self._build_logo())
        root.addSpacing(24)

        # ---- Nav items ----
        for icon_name, label_key, page_id in self.NAV_ITEMS:
            btn = NavButton(icon_name, t(label_key), page_id)
            btn.clicked.connect(lambda checked, pid=page_id: self._on_nav(pid))
            self._nav_buttons[page_id] = btn
            root.addWidget(btn)

            # 在 Library 之后插入 Collections section
            if page_id == "library":
                root.addWidget(self._build_collections_section())

        root.addSpacing(16)
        root.addStretch()

        # ---- Theme toggle ----
        self._theme_btn = QPushButton()
        self._theme_btn.setObjectName("nav_btn")
        self._theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_btn.setFixedHeight(36)
        self._theme_btn.clicked.connect(self.theme_toggle_requested.emit)
        self._update_theme_btn_icon()
        root.addWidget(self._theme_btn)

        # ---- Version ----
        from .. import __version__
        ver = QLabel(f"v{__version__}")
        ver.setObjectName("sidebar_version")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(ver)

        # ---- 默认选中 Home ----
        self._nav_buttons["home"].setChecked(True)

    def _build_logo(self) -> QWidget:
        """Logo 区域：图标 + 文字。"""
        wrap = QWidget()
        wrap.setObjectName("sidebar_logo_wrap")
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(8)

        # Logo 图标（用 sparkles 图标代替，未来可换成真实 logo）
        logo_icon = _icons.IconLabel("i-sparkles", size=22,
                                       color=self._theme_token("accent"))
        lay.addWidget(logo_icon)
        self._logo_icon = logo_icon

        # Logo 文字
        text = QLabel("Lumio")
        text.setObjectName("sidebar_logo")
        lay.addWidget(text)
        lay.addStretch()
        return wrap

    def _build_collections_section(self) -> QWidget:
        """Collections 分组：标题 + 添加按钮 + 列表容器。"""
        wrap = QWidget()
        cs_layout = QVBoxLayout(wrap)
        cs_layout.setContentsMargins(8, 8, 4, 4)
        cs_layout.setSpacing(4)

        # Header: 标题 + 添加按钮
        cs_header = QHBoxLayout()
        cs_header.setContentsMargins(0, 0, 0, 0)
        cs_label = QLabel(t("collections").upper())
        cs_label.setObjectName("sidebar_sep")
        cs_header.addWidget(cs_label)
        cs_header.addStretch()

        cs_add_btn = QPushButton()
        cs_add_btn.setObjectName("icon_add_btn")
        cs_add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cs_add_btn.setFixedSize(24, 20)
        cs_add_btn.setIcon(_icons.icon("i-plus", size=12, color=self._theme_token("text_mute")))
        cs_add_btn.clicked.connect(self.collection_create_requested.emit)
        cs_header.addWidget(cs_add_btn)
        cs_layout.addLayout(cs_header)

        # Collection 按钮容器
        self._collections_list = QVBoxLayout()
        self._collections_list.setSpacing(2)
        cs_layout.addLayout(self._collections_list)
        return wrap

    # ---------- 导航 ----------
    def _on_nav(self, page_id: str):
        for pid, btn in self._nav_buttons.items():
            btn.setChecked(pid == page_id)
        # 取消所有 Collection 选中
        for btn in self._collection_buttons.values():
            btn.setChecked(False)
        self.navigation_changed.emit(page_id)

    def set_active(self, page_id: str):
        for pid, btn in self._nav_buttons.items():
            btn.setChecked(pid == page_id)

    # ---------- Collections ----------
    def add_collection_nav(self, collection_id: int, name: str, icon: str = "📁",
                            count: int = 0, total_size: int = 0):
        if collection_id in self._collection_buttons:
            self.update_collection_nav(collection_id, name, icon, count, total_size)
            return
        btn = QPushButton()
        btn.setObjectName("nav_btn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setCheckable(True)
        btn.setFixedHeight(32)
        # 用 SVG 图标替代原 emoji icon
        btn.setIcon(_icons.icon("i-folder", size=16, color=self._theme_token("text_mute")))
        btn.setIconSize(QSize(16, 16))
        self._update_collection_btn_text(btn, name, count, total_size)
        btn.clicked.connect(lambda checked, cid=collection_id: self._on_collection_nav(cid))
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        btn.customContextMenuRequested.connect(
            lambda pos, b=btn, cid=collection_id: self._show_collection_menu(pos, b, cid))
        self._collection_buttons[collection_id] = btn
        self._collections_list.addWidget(btn)

    def update_collection_nav(self, collection_id: int, name: str = "", icon: str = "📁",
                                count: int = 0, total_size: int = 0):
        btn = self._collection_buttons.get(collection_id)
        if btn:
            self._update_collection_btn_text(btn, name, count, total_size)

    def _update_collection_btn_text(self, btn: QPushButton, name: str,
                                      count: int, total_size: int):
        if count > 0:
            btn.setText(f"  {name}  ({count})")
        else:
            btn.setText(f"  {name}")

    def _show_collection_menu(self, pos, btn, collection_id: int):
        menu = QMenu(self)
        menu.addAction(_icons.icon("i-edit", size=14, color=self._theme_token("text_mute")),
                        t("collection_rename"))
        menu.addAction(_icons.icon("i-trash", size=14, color=self._theme_token("danger")),
                        t("collection_delete"))
        action = menu.exec(btn.mapToGlobal(pos))
        if action.text() == t("collection_rename"):
            self.collection_rename_requested.emit(collection_id)
        elif action.text() == t("collection_delete"):
            self.collection_delete_requested.emit(collection_id)

    def remove_collection_nav(self, collection_id: int):
        btn = self._collection_buttons.pop(collection_id, None)
        if btn:
            btn.deleteLater()

    def _on_collection_nav(self, collection_id: int):
        for pid, btn in self._nav_buttons.items():
            btn.setChecked(pid == "library")
        for cid, btn in self._collection_buttons.items():
            btn.setChecked(cid == collection_id)
        self.collection_selected.emit(collection_id)

    # ---------- 主题 ----------
    def _theme_token(self, key: str) -> str:
        """从当前主题 token 取值。"""
        try:
            tokens = T.get_tokens(self._theme)
            # 处理状态色别名
            if key == "success":
                return T.STATUS_SUCCESS
            if key == "warning":
                return T.STATUS_WARNING
            if key == "danger":
                return T.STATUS_DANGER
            return tokens.get(key, "#ffffff")
        except Exception:
            return "#ffffff"

    def _update_theme_btn_icon(self):
        """根据主题切换图标（太阳/月亮）+ 文字。"""
        if self._theme == "dark":
            # 在暗色主题下显示「切换到亮色」按钮（太阳图标）
            self._theme_btn.setIcon(_icons.icon("i-sun", size=16,
                                                  color=self._theme_token("text_mute")))
            self._theme_btn.setText(t("theme_light"))
        else:
            self._theme_btn.setIcon(_icons.icon("i-moon", size=16,
                                                  color=self._theme_token("text_mute")))
            self._theme_btn.setText(t("theme_dark"))
        self._theme_btn.setIconSize(QSize(16, 16))

    def update_theme(self, theme: str):
        """主题切换时刷新所有依赖主题的图标颜色。"""
        self._theme = theme
        self._update_theme_btn_icon()
        # 刷新 logo 图标颜色
        self._logo_icon.set_color(self._theme_token("accent"))
        # 刷新 nav 按钮图标颜色
        for btn in self._nav_buttons.values():
            btn._refresh_icon()
        # 刷新 collection 按钮图标颜色
        for btn in self._collection_buttons.values():
            btn.setIcon(_icons.icon("i-folder", size=16, color=self._theme_token("text_mute")))

    # ---------- 通知 badge ----------
    def update_notification_badge(self, count: int):
        """更新通知导航按钮的 badge 数字。"""
        btn = self._nav_buttons.get("notifications")
        if not btn:
            return
        btn.set_badge(count)
