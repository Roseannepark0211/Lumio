"""Lumio 大气背景渲染器

在 paintEvent 中用 QPainter 绘制 Liquid Glass 风格的多层径向光球 + 噪点纹理，
完整还原 design_preview/styles.css 中的 body background 效果。

QSS 不支持多重径向渐变叠加，所以必须用自定义 paintEvent 实现。
"""
from __future__ import annotations

import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPaintEvent,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from . import tokens as T


# ============================================================
# 光球配置（与 design_preview/styles.css body background 完全一致）
# 每项: (cx%, cy%, rx%, ry%, r, g, b, alpha, fade_stop)
#   cx/cy     = 椭圆中心在 widget 中的比例位置（对应 CSS "at X% Y%"）
#   rx/ry     = 椭圆半轴占 widget 宽/高的比例（对应 CSS "ellipse W% H%"）
#   r/g/b/a   = 光球颜色（对应 CSS rgba(r, g, b, a)）
#   fade_stop = 颜色衰减为完全透明时的归一化位置（对应 CSS "transparent N%"）
# ============================================================
_DARK_ORBS = [
    # radial-gradient(ellipse 80% 60% at 15% 0%, rgba(94,92,230,0.28) 0%, transparent 60%)
    (0.15, 0.00, 0.80, 0.60, 94, 92, 230, 0.28, 0.60),
    # radial-gradient(ellipse 70% 50% at 85% 20%, rgba(255,55,92,0.18) 0%, transparent 55%)
    (0.85, 0.20, 0.70, 0.50, 255, 55, 92, 0.18, 0.55),
    # radial-gradient(ellipse 60% 80% at 80% 100%, rgba(10,132,255,0.22) 0%, transparent 60%)
    (0.80, 1.00, 0.60, 0.80, 10, 132, 255, 0.22, 0.60),
    # radial-gradient(ellipse 50% 50% at 30% 90%, rgba(255,159,10,0.12) 0%, transparent 60%)
    (0.30, 0.90, 0.50, 0.50, 255, 159, 10, 0.12, 0.60),
]

# Light 主题：光球更淡（alpha 减半），背景从 #ebebf0 到 #f5f5f7（由 tokens 提供）
_LIGHT_ORBS = [
    (0.15, 0.00, 0.80, 0.60, 94, 92, 230, 0.14, 0.60),
    (0.85, 0.20, 0.70, 0.50, 255, 55, 92, 0.09, 0.55),
    (0.80, 1.00, 0.60, 0.80, 10, 132, 255, 0.11, 0.60),
    (0.30, 0.90, 0.50, 0.50, 255, 159, 10, 0.06, 0.60),
]

_NOISE_SIZE = 200
_NOISE_OPACITY = 0.025


class AtmosphericBackground(QWidget):
    """Liquid Glass 风格的大气背景 Widget。

    paintEvent 绘制三层：
    1. 底层竖直线性渐变（bg_grad_1 → bg_grad_2）
    2. 4 层椭圆径向光球（颜色/位置与 styles.css 一致）
    3. 噪点纹理（200×200 随机灰度，opacity 0.025 叠加）

    用法：
        bg = AtmosphericBackground(theme="dark", parent=...)
        bg.set_theme("light")  # 切换主题
    """

    def __init__(self, theme: str = "dark", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._orbs = _LIGHT_ORBS if theme == "light" else _DARK_ORBS
        # 噪点纹理只生成一次，跨主题复用（性能优化）
        self._noise = self._generate_noise()

    def set_theme(self, theme: str) -> None:
        """切换主题并触发重绘。"""
        if theme == self._theme:
            return
        self._theme = theme
        self._orbs = _LIGHT_ORBS if theme == "light" else _DARK_ORBS
        self.update()

    @staticmethod
    def _generate_noise() -> QImage:
        """生成 200×200 随机灰度噪点图（只调用一次，缓存复用）。

        使用固定种子保证每次启动噪点纹理一致（与 CSS feTurbulence 确定性一致），
        不影响全局 random 状态。
        """
        rng = random.Random(42)
        data = rng.randbytes(_NOISE_SIZE * _NOISE_SIZE)
        img = QImage(data, _NOISE_SIZE, _NOISE_SIZE, _NOISE_SIZE,
                     QImage.Format.Format_Grayscale8)
        # copy() 使 QImage 脱离源 bytes，避免 data 被回收后悬空引用
        return img.copy()

    def paintEvent(self, event: QPaintEvent) -> None:
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

        tokens = T.get_tokens(self._theme)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # ---- 1. 底层：竖直线性渐变 bg_grad_1 → bg_grad_2 ----
        base_grad = QLinearGradient(0, 0, 0, h)
        base_grad.setColorAt(0.0, QColor(tokens["bg_grad_1"]))
        base_grad.setColorAt(1.0, QColor(tokens["bg_grad_2"]))
        p.fillRect(QRectF(0, 0, w, h), base_grad)

        # ---- 2. 4 层椭圆径向光球 ----
        # QRadialGradient 本身是圆形，通过 painter scale 变成椭圆：
        # 在归一化坐标（中心 0,0，半径 1.0）中定义圆形渐变，
        # 再 translate 到光球中心 + scale(rx, ry) 映射为椭圆（半轴 rx, ry）。
        # 这样归一化距离 sqrt((dx/rx)² + (dy/ry)²) 与 CSS 椭圆渐变一致。
        p.setPen(Qt.PenStyle.NoPen)
        for cx_p, cy_p, rx_p, ry_p, r, g, b, a, fade in self._orbs:
            cx = w * cx_p
            cy = h * cy_p
            rx = w * rx_p
            ry = h * ry_p
            if rx <= 0 or ry <= 0:
                continue

            orb_grad = QRadialGradient(QPointF(0.0, 0.0), 1.0)
            orb_grad.setColorAt(0.0, QColor(r, g, b, int(a * 255)))
            orb_grad.setColorAt(fade, QColor(r, g, b, 0))

            p.save()
            p.translate(cx, cy)
            p.scale(rx, ry)
            p.setBrush(orb_grad)
            # 在 scaled 坐标系中画覆盖整个椭圆（半径 1.0）的矩形；
            # 渐变在 fade 位置已透明，超出部分 PadSpread 保持透明。
            p.drawRect(QRectF(-1.0, -1.0, 2.0, 2.0))
            p.restore()

        # ---- 3. 噪点纹理：缩放到 widget 尺寸后以 opacity 0.025 叠加 ----
        p.setOpacity(_NOISE_OPACITY)
        p.drawImage(QRectF(0, 0, w, h), self._noise,
                    QRectF(0, 0, _NOISE_SIZE, _NOISE_SIZE))
        p.setOpacity(1.0)
        p.end()
