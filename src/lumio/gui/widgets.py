"""Lumio Liquid Glass 通用组件库

所有组件遵循设计 Token 体系（theme/tokens.py），不写死颜色值。
组件间通过 objectName + property 触发 styles.py 中的 QSS 规则，
保证主题切换时只需刷新全局 stylesheet 即可生效。

包含：
- NoWheelComboBox     — 禁用滚轮的 ComboBox（保留原项目兼容）
- GlassCard           — 磨砂玻璃卡片，带柔和阴影
- Badge               — 状态/平台徽章，type 属性驱动样式
- Pill                — 平台选择按钮（可选中）
- Led                 — 状态指示灯小圆点
- Toggle              — iOS 风格开关
- IconText            — 图标+文字水平组合
- Divider             — 柔和分割线
- EmptyState          — 空状态占位
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .theme import icons as _icons
from .theme import tokens as T


# ============================================================
# NoWheelComboBox — 保留原项目兼容
# ============================================================
class NoWheelComboBox(QComboBox):
    """QComboBox that ignores mouse wheel events to prevent accidental changes."""

    def wheelEvent(self, event):
        event.ignore()


# ============================================================
# GlassCard — 磨砂玻璃卡片
# ============================================================
class GlassCard(QFrame):
    """磨砂玻璃风格卡片容器。

    QSS 不支持 backdrop-filter，所以「磨砂」效果通过半透明背景色 +
    QGraphicsDropShadowEffect 柔和阴影模拟。在大背景渐变上视觉上
    接近 Liquid Glass 设计稿的层次感。

    用法：
        card = GlassCard(parent)
        layout = QVBoxLayout(card)
        layout.addWidget(...)
    """

    def __init__(self, parent=None, *, radius: int = T.R_XL, padding: int = 24):
        super().__init__(parent)
        self.setObjectName("glass_card")
        # 通过 setProperty 注入自定义半径（QSS 中可选用 [radius="..."] 选择器扩展）
        self._radius = radius
        self._padding = padding
        # 内部边距让内容不贴边
        if self.layout() is None:
            lay = QVBoxLayout(self)
            lay.setContentsMargins(padding, padding, padding, padding)
            lay.setSpacing(8)
        # 柔和分层阴影
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(40)
        self._shadow.setColor(QColor(0, 0, 0, 110))
        self._shadow.setOffset(0, 8)
        self.setGraphicsEffect(self._shadow)

    def set_radius(self, radius: int):
        self._radius = radius
        # 半径通过 QSS border-radius 控制，这里只触发刷新
        self.style().unpolish(self)
        self.style().polish(self)


# ============================================================
# Badge — 状态/平台徽章
# ============================================================
class Badge(QLabel):
    """通用徽章组件。

    通过切换 objectName 复用 styles.py 中已存在的 QSS 规则
    （badge_downloading / platform_youtube / media_video 等）。
    优点：无需 Python 端写颜色，主题切换自动跟随。

    支持类型（与 styles.py 中 QSS 选择器一一对应）：
        状态: waiting / downloading / paused / retrying / interrupted / completed / failed / cancelled
        媒体: video / audio / image / mixed
        平台: youtube / instagram / x / bilibili / douyin / kuaishou / weibo / xiaohongshu / telegram
        通用: default（lg_badge）/ accent / success / warning / danger
    """

    # 类型 → objectName 映射
    _TYPE_OBJECT_NAMES = {
        # 状态
        "waiting": "badge_waiting",
        "downloading": "badge_downloading",
        "paused": "badge_paused",
        "retrying": "badge_retrying",
        "interrupted": "badge_interrupted",
        "completed": "badge_completed",
        "failed": "badge_failed",
        "cancelled": "badge_cancelled",
        # 媒体
        "video": "media_video",
        "audio": "media_audio",
        "image": "media_image",
        "mixed": "media_mixed",
        # 平台
        "youtube": "platform_youtube",
        "instagram": "platform_instagram",
        "x": "platform_x",
        "bilibili": "platform_bilibili",
        "douyin": "platform_douyin",
        "kuaishou": "platform_kuaishou",
        "weibo": "platform_weibo",
        "xiaohongshu": "platform_xiaohongshu",
        "telegram": "platform_telegram",
    }

    def __init__(self, text: str = "", badge_type: str = "default", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_type(badge_type)

    def set_type(self, badge_type: str):
        """切换徽章类型，自动应用对应配色。"""
        obj_name = self._TYPE_OBJECT_NAMES.get(badge_type, "lg_badge")
        if self.objectName() != obj_name:
            self.setObjectName(obj_name)
        # 切换 objectName 必须重新 polish 才能让 QSS 选择器生效
        self.style().unpolish(self)
        self.style().polish(self)


# ============================================================
# Pill — 平台选择按钮
# ============================================================
class Pill(QPushButton):
    """胶囊形可选中按钮，用于平台筛选、能力 tag 等。

    用法：
        pill = Pill("YouTube", platform="youtube")
        pill.setCheckable(True)
    """

    clicked_with_data = Signal(str)  # platform

    def __init__(self, text: str, platform: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("lg_pill")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._platform = platform
        if platform:
            self.setProperty("platform", platform)
        self.clicked.connect(self._on_clicked)

    def _on_clicked(self):
        if self._platform:
            self.clicked_with_data.emit(self._platform)


# ============================================================
# Led — 状态指示灯
# ============================================================
class Led(QLabel):
    """状态指示灯（6px 圆点 + 平台色辉光）。

    用法：
        led = Led(color="green")
        led.set_color("blue")
    """

    VALID_COLORS = {"green", "blue", "yellow", "red", "pink", "dim"}

    def __init__(self, color: str = "dim", parent=None):
        super().__init__(parent)
        self.setObjectName("lg_led")
        self.setFixedSize(8, 8)
        self.set_color(color)

    def set_color(self, color: str):
        if color not in self.VALID_COLORS:
            color = "dim"
        self.setProperty("led", color)
        self.style().unpolish(self)
        self.style().polish(self)


# ============================================================
# Toggle — iOS 风格开关
# ============================================================
class Toggle(QPushButton):
    """iOS 风格滑动开关。

    setCheckable(True) + checked 状态由 QSS 控制，
    动画通过 property 切换 + QSS transition 实现（Qt 6 部分支持）。

    用法：
        toggle = Toggle()
        toggle.setChecked(True)
        toggle.toggled.connect(callback)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("lg_toggle")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(44, 24)
        # 隐藏文字，仅显示开关
        self.setText("")


# ============================================================
# IconText — 图标 + 文字水平组合
# ============================================================
class IconText(QWidget):
    """图标 + 文字水平排列的复合控件。

    用法：
        item = IconText("i-download", "下载", icon_size=16, color="#0a84ff")
        item.set_text("已完成")
        item.set_color("#30d158")
    """

    def __init__(
        self,
        icon_name: str = "",
        text: str = "",
        icon_size: int = 16,
        color: str = "#ffffff",
        spacing: int = 6,
        parent=None,
    ):
        super().__init__(parent)
        self._color = color
        self._icon_name = icon_name
        self._icon_size = icon_size

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(spacing)

        self._icon_lbl = _icons.IconLabel(icon_name, size=icon_size, color=color)
        lay.addWidget(self._icon_lbl)

        self._text_lbl = QLabel(text)
        self._text_lbl.setStyleSheet(f"color: {color}; background: transparent;")
        lay.addWidget(self._text_lbl)
        lay.addStretch()

    def set_text(self, text: str):
        self._text_lbl.setText(text)

    def set_color(self, color: str):
        self._color = color
        self._icon_lbl.set_color(color)
        self._text_lbl.setStyleSheet(f"color: {color}; background: transparent;")

    def set_icon(self, name: str):
        self._icon_name = name
        self._icon_lbl.set_icon(name)


# ============================================================
# Divider — 柔和分割线
# ============================================================
class Divider(QFrame):
    """柔和的分割线，颜色取自 token 的 glass_border。"""

    def __init__(self, orientation: str = "horizontal", parent=None):
        super().__init__(parent)
        self.setObjectName("home_divider")
        if orientation == "vertical":
            self.setFrameShape(QFrame.Shape.VLine)
            self.setFixedWidth(1)
        else:
            self.setFrameShape(QFrame.Shape.HLine)
            self.setFixedHeight(1)
        # 颜色由 QSS 控制


# ============================================================
# EmptyState — 空状态占位
# ============================================================
class EmptyState(QWidget):
    """空状态占位组件（大图标 + 标题 + 提示）。

    用法：
        empty = EmptyState(icon="i-inbox", title="收件箱为空", hint="从浏览器扩展发送内容")
    """

    def __init__(
        self,
        icon: str = "i-info",
        title: str = "",
        hint: str = "",
        icon_size: int = 48,
        icon_color: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("lg_empty")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 40, 40, 40)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 默认用浅灰，避免在 Light 主题下不可见
        color = icon_color or self._default_icon_color()
        self._icon_lbl = _icons.IconLabel(icon, size=icon_size, color=color)
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._icon_lbl)

        self._title_lbl = QLabel(title)
        self._title_lbl.setObjectName("lg_empty_title")
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._title_lbl)

        self._hint_lbl = QLabel(hint)
        self._hint_lbl.setObjectName("lg_empty_hint")
        self._hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._hint_lbl)

    @staticmethod
    def _default_icon_color() -> str:
        """根据当前 config 主题返回默认图标色，避免 Light 主题下白色图标不可见。"""
        try:
            from ..utils.config import load_config
            theme = load_config().get("theme", "dark")
            tokens = T.get_tokens(theme)
            return tokens["text_dim"]
        except Exception:
            return "rgba(255,255,255,0.18)"

    def set_icon(self, name: str, color: str = ""):
        if color:
            self._icon_lbl.set_color(color)
        self._icon_lbl.set_icon(name)

    def set_title(self, text: str):
        self._title_lbl.setText(text)

    def set_hint(self, text: str):
        self._hint_lbl.setText(text)
