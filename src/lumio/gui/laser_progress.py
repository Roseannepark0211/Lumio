"""Lumio 激光粒子进度条

移植自 design_preview/downloads.html 的 Canvas 实现。
PySide6 中重写 paintEvent，QTimer 16ms 驱动 + QPainter 画粒子和激光头。

设计要点（与 HTML 原型一致）：
- 双层结构：底色填充渐变（紫→蓝→浅蓝）+ 粒子覆盖层
- 激光头：白色 4px + 三层光晕，永远在进度最前沿
- 粒子：从激光头 180° 后向扇形喷射（±63°）
- 颜色：蓝青色相 200-240
- 粒子上限 80，超出不再生成
- DPR ≤2 限制
- 60fps QTimer + dt 帧率插值
- 隐藏时自动暂停 timer，避免无意义绘制

用法：
    bar = LaserProgress()
    bar.set_value(0.5)  # 0.0 ~ 1.0
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from PySide6.QtCore import (
    QElapsedTimer, QPointF, QRectF, QSize, Qt, QTimer,
)
from PySide6.QtGui import (
    QColor, QLinearGradient, QPainter, QPaintEvent, QPen, QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from .theme import tokens as T


# ============================================================
# Particle
# ============================================================
@dataclass(slots=True)
class _Particle:
    """单个粒子状态。slots=True 减少内存占用。"""
    x: float
    y: float
    vx: float
    vy: float
    life: float           # 1.0 → 0.0
    decay: float
    size: float
    hue: float            # 200~240


# ============================================================
# LaserProgress
# ============================================================
class LaserProgress(QWidget):
    """激光粒子进度条。

    厚度由 setFixedHeight / setMinimumHeight 控制，建议 6~14px。
    粒子会从激光头喷出向后方扇形扩散。
    """

    # 视觉常量（与 HTML 原型一致）
    _MAX_PARTICLES = 80
    _SPAWN_PROB = 0.6         # 每帧 60% 概率生成 1 个粒子
    _HEAD_LERP = 0.08         # 激光头插值系数
    _GRAVITY = 0.015          # 粒子轻微下坠
    _DT_CLAMP = 3.0           # dt 上限，防止暂停后大跳

    # 颜色
    _HUE_MIN = 200.0
    _HUE_MAX = 240.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("laser_progress")
        self.setFixedHeight(10)
        # 启用鼠标跟踪不需要；启用 WA_OpaquePaintEvent 会跳过背景绘制，但我们用透明背景
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        # 状态
        self._value: float = 0.0
        self._display_value: float = 0.0  # 平滑显示值
        self._head_x: float = 0.0
        self._track_w: float = float(self.width() or 100)
        self._particles: list[_Particle] = []
        self._last_tick_ms: int = 0

        # 帧率计时
        self._elapsed = QElapsedTimer()
        self._elapsed.start()
        self._last_tick_ms = self._elapsed.elapsed()

        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60fps
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        # 减少动效（Windows 系统设置）
        self._reduced_motion = self._detect_reduced_motion()

    # ---------- 公共 API ----------
    def set_value(self, value: float):
        """设置进度值 0.0~1.0。"""
        self._value = max(0.0, min(1.0, float(value)))
        # 更新不会立即重画，下一帧 _tick 会处理

    def value(self) -> float:
        return self._value

    def sizeHint(self) -> QSize:
        return QSize(200, 10)

    # ---------- 内部 ----------
    def _detect_reduced_motion(self) -> bool:
        """检测用户是否在系统层关闭了动画。

        Windows: 通过 SystemParametersInfo(SPI_GETCLIENTAREAANIMATION) 检查
        简单起见，先看环境变量 LUMIO_REDUCED_MOTION
        """
        import os
        if os.environ.get("LUMIO_REDUCED_MOTION"):
            return True
        # Windows 系统级检测比较复杂，需要 ctypes；先返回 False
        return False

    def _tick(self):
        """每帧更新粒子状态 + 触发重画。"""
        now = self._elapsed.elapsed()
        dt = (now - self._last_tick_ms) / 16.67  # 归一化到 60fps
        self._last_tick_ms = now
        dt = min(dt, self._DT_CLAMP)
        if dt <= 0:
            return

        # 同步 track 宽度（resize 后立即生效）
        w = self.width()
        if w > 0:
            self._track_w = float(w)

        # 平滑进度值（避免数值跳变导致激光头跳动）
        self._display_value += (self._value - self._display_value) * 0.15 * dt
        if abs(self._value - self._display_value) < 0.001:
            self._display_value = self._value

        # 激光头位置插值
        target_x = self._display_value * self._track_w
        self._head_x += (target_x - self._head_x) * self._HEAD_LERP * dt
        # 避免极小值时 head_x 抖动
        if abs(target_x - self._head_x) < 0.5:
            self._head_x = target_x

        # 喷射粒子（进度在中间区域时）
        if not self._reduced_motion and 0.01 < self._display_value < 0.99:
            if len(self._particles) < self._MAX_PARTICLES:
                if random.random() < self._SPAWN_PROB * dt:
                    self._spawn_particle()

        # 更新粒子
        for p in self._particles:
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vy += self._GRAVITY * dt
            p.life -= p.decay * dt

        # 移除死亡粒子
        self._particles = [p for p in self._particles if p.life > 0]

        # 触发重画
        self.update()

    def _spawn_particle(self):
        """从激光头位置后向扇形喷射粒子。"""
        # 角度：±63° 后向（与 HTML 原型一致：(rand - 0.5) * π * 0.7 + π）
        angle = (random.random() - 0.5) * math.pi * 0.7 + math.pi
        speed = 0.4 + random.random() * 1.5
        self._particles.append(_Particle(
            x=self._head_x,
            y=(random.random() - 0.5) * 3,  # 中心线附近微小抖动
            vx=math.cos(angle) * speed,
            vy=math.sin(angle) * speed * 0.5,
            life=1.0,
            decay=0.015 + random.random() * 0.02,
            size=0.8 + random.random() * 1.6,
            hue=random.uniform(self._HUE_MIN, self._HUE_MAX),
        ))

    # ---------- 绘制 ----------
    def paintEvent(self, event: QPaintEvent):
        """绘制进度条 + 粒子 + 激光头。"""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w = self.width()
        h = self.height()
        # 更新 track 宽度（处理 resize）
        if abs(w - self._track_w) > 1:
            self._track_w = float(w)
            # resize 后重置激光头位置
            self._head_x = self._display_value * self._track_w

        # ---- 1. 背景轨道（深色细线） ----
        track_rect = QRectF(0, (h - 6) / 2, w, 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 100))
        p.drawRoundedRect(track_rect, 3, 3)

        # ---- 2. 填充渐变（紫→蓝→浅蓝） ----
        fill_w = self._display_value * w
        if fill_w > 1:
            fill_rect = QRectF(0, (h - 6) / 2, fill_w, 6)
            grad = QLinearGradient(0, 0, w, 0)
            grad.setColorAt(0.0, QColor("#5e5ce6"))
            grad.setColorAt(0.5, QColor("#0a84ff"))
            grad.setColorAt(1.0, QColor("#4cc2ff"))
            p.setBrush(grad)
            p.drawRoundedRect(fill_rect, 3, 3)

        # ---- 3. 粒子（先绘制以便在激光头之下） ----
        if not self._reduced_motion:
            for pt in self._particles:
                self._draw_particle(p, pt, h / 2)

        # ---- 4. 激光头（白色 + 三层光晕） ----
        if 0.005 < self._display_value < 0.995:
            self._draw_laser_head(p, self._head_x, h / 2)

        # ---- 5. 边框微光（轨道顶部内嵌光晕） ----
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(track_rect, 3, 3)

    def _draw_particle(self, p: QPainter, pt: _Particle, center_y: float):
        """画单个粒子：外圈 radial gradient + 内核高亮。"""
        alpha = pt.life * 0.85
        radius = pt.size * pt.life
        if radius < 0.1 or alpha < 0.02:
            return

        # 颜色：HSL → RGB（PySide6 QColor 支持 setHslF）
        color = QColor.fromHslF(pt.hue / 360.0, 1.0, 0.7, alpha)
        outer = QColor.fromHslF(pt.hue / 360.0, 1.0, 0.5, 0)
        core = QColor.fromHslF(pt.hue / 360.0, 1.0, 0.9, alpha)

        # 外圈光晕
        glow = QRadialGradient(QPointF(pt.x, center_y + pt.y), radius * 4)
        glow.setColorAt(0.0, color)
        glow.setColorAt(0.4, QColor.fromHslF(pt.hue / 360.0, 1.0, 0.6, alpha * 0.4))
        glow.setColorAt(1.0, outer)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(pt.x, center_y + pt.y), radius * 4, radius * 4)

        # 内核高亮
        p.setBrush(core)
        p.drawEllipse(QPointF(pt.x, center_y + pt.y), radius, radius)

    def _draw_laser_head(self, p: QPainter, x: float, y: float):
        """画激光头：白色 4px 核心 + 三层光晕。"""
        # 最外层光晕 (10px, 蓝色淡)
        g1 = QRadialGradient(QPointF(x, y), 12)
        g1.setColorAt(0.0, QColor(255, 255, 255, 230))
        g1.setColorAt(0.3, QColor(120, 180, 255, 130))
        g1.setColorAt(1.0, QColor(10, 132, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g1)
        p.drawEllipse(QPointF(x, y), 12, 12)

        # 中层光晕 (5px, 蓝色更亮)
        g2 = QRadialGradient(QPointF(x, y), 5)
        g2.setColorAt(0.0, QColor(255, 255, 255, 255))
        g2.setColorAt(1.0, QColor(180, 220, 255, 0))
        p.setBrush(g2)
        p.drawEllipse(QPointF(x, y), 5, 5)

        # 核心 (2px, 纯白)
        p.setBrush(QColor(255, 255, 255, 255))
        p.drawEllipse(QPointF(x, y), 2, 2)

    # ---------- 事件 ----------
    def hideEvent(self, event):
        """隐藏时暂停 timer，避免无意义绘制。"""
        self._timer.stop()
        super().hideEvent(event)

    def showEvent(self, event):
        """重新显示时恢复 timer。"""
        if not self._timer.isActive():
            self._last_tick_ms = self._elapsed.elapsed()
            self._timer.start()
        super().showEvent(event)

    def resizeEvent(self, event):
        """resize 时更新 track 宽度。"""
        self._track_w = float(self.width())
        self._head_x = self._display_value * self._track_w
        super().resizeEvent(event)
