"""Lumio 自定义绘制控件

QSS 无法实现的高级视觉效果：
- GradientLabel: 渐变文字（替代 CSS background-clip: text）
- FocusLineEdit / FocusPlainTextEdit: focus 光环（替代 CSS box-shadow focus ring）
- HoverButton / HoverCard: hover 上浮动画（替代 CSS transform: translateY）
"""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve, QPoint, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer,
)
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QLinearGradient, QPainter,
    QPainterPath, QPalette, QPen, QRadialGradient,
)
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QWidget,
)

from . import tokens as T

__all__ = [
    "GradientLabel",
    "FocusLineEdit",
    "FocusPlainTextEdit",
    "HoverButton",
    "HoverCard",
]


# ============================================================
# 颜色解析工具
# ============================================================
def _parse_color(color: str) -> QColor:
    """解析颜色字符串到 QColor。

    支持：
    - ``#rgb`` / ``#rrggbb`` / ``#rrggbbaa``
    - ``rgb(r, g, b)`` / ``rgba(r, g, b, a)``  (a 可为 0-1 小数或 0-255 整数)
    """
    if not color:
        return QColor()
    s = color.strip()

    # rgba(...) / rgb(...)
    if s.startswith(("rgba", "rgb")):
        try:
            inside = s[s.index("(") + 1: s.rindex(")")]
            parts = [p.strip() for p in inside.split(",")]
        except (ValueError, IndexError):
            return QColor()
        try:
            if len(parts) == 4:
                r, g, b, a = parts
                a_val = float(a)
                # 0-1 小数 → 0-255 整数（CSS 规范四舍五入）；>1 视为已是 0-255 整数
                if a_val <= 1.0:
                    a_val = round(a_val * 255)
                else:
                    a_val = int(a_val)
                return QColor(int(r), int(g), int(b), a_val)
            if len(parts) == 3:
                r, g, b = parts
                return QColor(int(r), int(g), int(b))
        except (ValueError, TypeError):
            return QColor()
        return QColor()

    # hex
    h = s.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) == 6:
        try:
            return QColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        except ValueError:
            return QColor()
    if len(h) == 8:
        try:
            return QColor(
                int(h[0:2], 16), int(h[2:4], 16),
                int(h[4:6], 16), int(h[6:8], 16),
            )
        except ValueError:
            return QColor()
    return QColor()


# ============================================================
# Focus ring 共享绘制
# ============================================================
def _draw_focus_ring(
    widget: QWidget,
    painter: QPainter,
    ring_color: str,
    ring_width: int = 3,
) -> None:
    """在 widget 边缘绘制 QRadialGradient focus 光环。

    光环为 ``ring_width`` 像素宽的圆角矩形描边，颜色按 QRadialGradient 从
    widget 中心向外渐淡。

    注意：Qt 会裁剪 widget rect 外的绘制，因此光环实际绘制在 widget rect
    内边缘（紧贴边缘）。如需完整的「外扩 3px」效果，应在父布局中为 widget
    预留 ``ring_width`` 的 margin，并将控件 rect 扩展相应像素。
    """
    w = ring_width
    half = w / 2.0
    # 描边中心紧贴 widget 边缘内侧
    rect = QRectF(widget.rect()).adjusted(half, half, -half, -half)
    # 圆角半径：取 height 的一半形成胶囊形，下限保护
    radius = max(0.0, (widget.height() - w) / 2.0)

    c = _parse_color(ring_color)
    if not c.isValid():
        c = QColor(10, 132, 255, 64)  # 兜底 accent_soft

    # QRadialGradient：中心在 widget 中心，半径到最远角
    cx = widget.rect().center().x()
    cy = widget.rect().center().y()
    dw = widget.width() / 2.0
    dh = widget.height() / 2.0
    grad_radius = max(1.0, (dw * dw + dh * dh) ** 0.5)
    gradient = QRadialGradient(cx, cy, grad_radius)
    gradient.setColorAt(0.0, c)
    c_edge = QColor(c)
    c_edge.setAlpha(0)
    gradient.setColorAt(1.0, c_edge)

    pen = QPen(QBrush(gradient), w)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(rect, radius, radius)


# ============================================================
# GradientLabel
# ============================================================
class GradientLabel(QLabel):
    """渐变文字 QLabel。

    用 QLinearGradient 绘制文字，替代 CSS ``background-clip: text``。
    QSS 仍控制字号、字重、对齐；paintEvent 只负责渐变着色。

    direction:
    - ``"vertical"``: 180deg，从上到下
    - ``"horizontal"``: 135deg，从左上到右下

    color_start / color_end 支持 ``#rrggbb`` 和 ``rgba(r,g,b,a)`` 字符串。
    """

    def __init__(
        self,
        text: str = "",
        direction: str = "vertical",
        color_start: str = "#ffffff",
        color_end: str = "rgba(255,255,255,0.75)",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self._direction = direction
        self._color_start = color_start
        self._color_end = color_end
        self._theme = "dark"
        # 不让 QLabel 默认绘制文字（paintEvent 完全自绘），并确保背景透明
        self.setAutoFillBackground(False)

    def set_theme(self, theme: str) -> None:
        """切换主题时刷新（默认仅触发重绘；如需变色请调用 set_colors）。"""
        self._theme = theme
        self.update()

    def set_colors(self, color_start: str, color_end: str) -> None:
        """更新渐变起止色。"""
        self._color_start = color_start
        self._color_end = color_end
        self.update()

    def set_direction(self, direction: str) -> None:
        """更新渐变方向：``'vertical'`` / ``'horizontal'``。"""
        self._direction = direction
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
        )

        # 先 clear 背景为透明（CompositionMode_Source 直接覆盖像素）
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        text = self.text()
        if not text:
            return

        font: QFont = self.font()
        fm = QFontMetrics(font)

        # 按 alignment 计算文字在 widget rect 内的位置
        flags = int(self.alignment()) | int(Qt.TextFlag.TextSingleLine)
        br = fm.boundingRect(self.rect(), flags, text)
        # addText 的 y 参数是 baseline；boundingRect.top() ≈ baseline - ascent
        x = br.left()
        y = br.top() + fm.ascent()

        # 构建文字路径
        path = QPainterPath()
        path.addText(x, y, font, text)

        # 构建渐变
        gradient = QLinearGradient()
        if self._direction == "vertical":
            # 180deg：上 → 下
            gradient.setStart(0, 0)
            gradient.setFinalStop(0, max(1, self.height()))
        else:
            # 135deg：左上 → 右下
            gradient.setStart(0, 0)
            gradient.setFinalStop(max(1, self.width()), max(1, self.height()))

        c_start = _parse_color(self._color_start)
        if not c_start.isValid():
            c_start = QColor(255, 255, 255)
        c_end = _parse_color(self._color_end)
        if not c_end.isValid():
            c_end = QColor(255, 255, 255, 191)
        gradient.setColorAt(0.0, c_start)
        gradient.setColorAt(1.0, c_end)

        # 用渐变同时填充和描边文字路径（pen + brush 都用 gradient）
        gradient_brush = QBrush(gradient)
        painter.setPen(QPen(gradient_brush, 0))
        painter.setBrush(gradient_brush)
        painter.drawPath(path)


# ============================================================
# FocusLineEdit
# ============================================================
class FocusLineEdit(QLineEdit):
    """带 focus 光环的 QLineEdit。

    QSS :focus 负责边框 + 背景变化，此处额外在边缘绘制 3px QRadialGradient
    光环，替代 CSS ``box-shadow: 0 0 0 3px var(--accent-soft)``。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ring_color: str = T.DARK.get("accent_soft", "rgba(10, 132, 255, 0.25)")
        self._ring_width: int = 3

    def set_theme(self, theme: str) -> None:
        """切换主题时刷新光环色。"""
        tokens = T.get_tokens(theme)
        self._ring_color = tokens.get("accent_soft", self._ring_color)
        self.update()

    def set_ring_color(self, color: str) -> None:
        self._ring_color = color
        self.update()

    def set_ring_width(self, width: int) -> None:
        self._ring_width = max(1, width)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().paintEvent(event)
        if not self.hasFocus():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        _draw_focus_ring(self, painter, self._ring_color, self._ring_width)


# ============================================================
# FocusPlainTextEdit
# ============================================================
class FocusPlainTextEdit(QPlainTextEdit):
    """带 focus 光环的 QPlainTextEdit（多行 URL 输入框）。

    同 FocusLineEdit，用于多行文本编辑。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ring_color: str = T.DARK.get("accent_soft", "rgba(10, 132, 255, 0.25)")
        self._ring_width: int = 3

    def set_theme(self, theme: str) -> None:
        """切换主题时刷新光环色。"""
        tokens = T.get_tokens(theme)
        self._ring_color = tokens.get("accent_soft", self._ring_color)
        self.update()

    def set_ring_color(self, color: str) -> None:
        self._ring_color = color
        self.update()

    def set_ring_width(self, width: int) -> None:
        self._ring_width = max(1, width)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().paintEvent(event)
        if not self.hasFocus():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        _draw_focus_ring(self, painter, self._ring_color, self._ring_width)


# ============================================================
# Hover 动画 mixin（HoverButton / HoverCard 共享）
# ============================================================
class _HoverAnimMixin:
    """Hover 上浮 + 阴影动画共享逻辑。

    被 HoverButton / HoverCard 通过多继承复用。假定宿主类是 QWidget 子类，
    拥有 pos() / setGraphicsEffect() / underMouse() 等 QWidget 接口。

    设计稿：
        .btn-primary:hover { transform: translateY(-Npx); box-shadow: ... }

    enterEvent: pos.y() 上移 hover_offset，阴影 blurRadius 增大。
    leaveEvent: 回到 original_pos，阴影恢复为 0。

    注意：动画 pos 可能与父布局重排冲突；建议在父布局中为控件预留少量边距，
    或在不被布局频繁重排的容器中使用。
    """

    # 宿主类在 _setup_hover 中赋值的实例属性（类型提示，供静态检查）
    _hover_offset: int
    _shadow_color: str | None
    _shadow_blur: int
    _original_pos: QPoint | None
    _pos_anim: QPropertyAnimation | None
    _blur_anim: QPropertyAnimation | None
    _shadow_effect: QGraphicsDropShadowEffect | None

    def _setup_hover(
        self,
        hover_offset: int,
        shadow_color: str | None,
        shadow_blur: int,
        fallback_shadow_color: QColor,
    ) -> None:
        """初始化 hover 动画状态。需在宿主 __init__ 的 super().__init__ 之后调用。"""
        self._hover_offset = hover_offset
        self._shadow_color = shadow_color
        self._shadow_blur = shadow_blur
        self._original_pos = None
        self._pos_anim = None
        self._blur_anim = None
        self._shadow_effect = None

        if shadow_color is not None:
            self._shadow_effect = QGraphicsDropShadowEffect(self)  # type: ignore[arg-type]
            c = _parse_color(shadow_color)
            self._shadow_effect.setColor(c if c.isValid() else fallback_shadow_color)
            self._shadow_effect.setBlurRadius(0)
            self._shadow_effect.setOffset(0, 0)
            self.setGraphicsEffect(self._shadow_effect)  # type: ignore[attr-defined]

    def _update_shadow_color(self, color: QColor) -> None:
        if self._shadow_effect is not None and color.isValid():
            self._shadow_effect.setColor(color)

    def _ensure_original_pos(self) -> None:
        if self._original_pos is None:
            self._original_pos = self.pos()  # type: ignore[attr-defined]

    def _animate_pos(self, target: QPoint) -> None:
        if self._pos_anim is not None:
            self._pos_anim.stop()
        anim = QPropertyAnimation(self, b"pos", self)  # type: ignore[arg-type]
        anim.setDuration(150)
        anim.setStartValue(self.pos())  # type: ignore[attr-defined]
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._pos_anim = anim

    def _animate_blur(self, target: int) -> None:
        if self._shadow_effect is None:
            return
        if self._blur_anim is not None:
            self._blur_anim.stop()
        anim = QPropertyAnimation(self._shadow_effect, b"blurRadius", self)
        anim.setDuration(150)
        anim.setStartValue(self._shadow_effect.blurRadius())
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._blur_anim = anim

    def _on_enter(self) -> None:
        self._ensure_original_pos()
        if self._original_pos is not None:
            self._animate_pos(self._original_pos + QPoint(0, -self._hover_offset))
        if self._shadow_effect is not None:
            self._animate_blur(self._shadow_blur)

    def _on_leave(self) -> None:
        if self._original_pos is not None:
            self._animate_pos(self._original_pos)
        if self._shadow_effect is not None:
            self._animate_blur(0)

    def _on_move(self) -> None:
        # 非悬停时布局移动控件 → 更新原位（避免动画结束回到旧坐标）
        if not self.underMouse():  # type: ignore[attr-defined]
            self._original_pos = self.pos()  # type: ignore[attr-defined]


# ============================================================
# HoverButton
# ============================================================
class HoverButton(QPushButton, _HoverAnimMixin):
    """带 hover 上浮动画的 QPushButton。

    设计稿：
        .btn-primary:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 16px -2px rgba(10, 132, 255, 0.65);
        }

    Args:
        hover_offset: hover 时上移像素数（默认 1）。
        shadow_color: 阴影色；为 None 时不创建阴影效果。
        shadow_blur: hover 时阴影 blurRadius（默认 16）。
    """

    def __init__(
        self,
        hover_offset: int = 1,
        shadow_color: str | None = None,
        shadow_blur: int = 16,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        # accent_soft 兜底色（设计稿 0.65 alpha ≈ 166/255）
        self._setup_hover(
            hover_offset, shadow_color, shadow_blur,
            QColor(10, 132, 255, 166),
        )

    def set_theme(self, theme: str) -> None:
        """切换主题时刷新阴影色（如已配置）。"""
        tokens = T.get_tokens(theme)
        self._update_shadow_color(_parse_color(tokens.get("accent", "#0a84ff")))

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self._on_enter()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self._on_leave()
        super().leaveEvent(event)

    def moveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self._on_move()
        super().moveEvent(event)


# ============================================================
# HoverCard
# ============================================================
class HoverCard(QFrame, _HoverAnimMixin):
    """带 hover 上浮动画的 QFrame（媒体卡片等）。

    设计稿：
        .media-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 30px 60px -20px rgba(0,0,0,0.7);
        }

    同 HoverButton，默认 hover_offset=3。

    Args:
        hover_offset: hover 时上移像素数（默认 3）。
        shadow_color: 阴影色；为 None 时不创建阴影效果。
        shadow_blur: hover 时阴影 blurRadius（默认 16）。
    """

    def __init__(
        self,
        hover_offset: int = 3,
        shadow_color: str | None = None,
        shadow_blur: int = 16,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        # 卡片阴影兜底用深色黑（设计稿 rgba(0,0,0,0.7) ≈ 178/255）
        self._setup_hover(
            hover_offset, shadow_color, shadow_blur,
            QColor(0, 0, 0, 178),
        )

    def set_theme(self, theme: str) -> None:
        """切换主题时刷新阴影色（如已配置）。"""
        tokens = T.get_tokens(theme)
        self._update_shadow_color(_parse_color(tokens.get("accent", "#0a84ff")))

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self._on_enter()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self._on_leave()
        super().leaveEvent(event)

    def moveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self._on_move()
        super().moveEvent(event)
