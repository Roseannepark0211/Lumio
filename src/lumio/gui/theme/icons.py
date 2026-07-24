"""Lumio SVG 图标系统

从 `assets/icons.svg` 加载 SVG sprite，提供 QColor-aware 的 QIcon / QPixmap 接口。

设计原则：
- SVG 文件中所有 symbol 用 `stroke="currentColor"`，可通过 setColor 动态变色
- 单次加载，全局缓存（避免每次渲染都解析 SVG）
- QtSvg 的 QSvgRenderer 渲染到 QPixmap，再用 QPainter 着色

替代原项目「全靠 Unicode 字符和 emoji 当图标」的方案（跨平台渲染不一致）。

用法：
    from lumio.gui.theme.icons import icon

    # 在 QLabel 上显示图标
    lbl = IconLabel("i-download", size=16, color="#0a84ff")

    # 获取 QPixmap 自己用
    pm = icon("i-home", size=20, color="#ffffff")

    # QPushButton 设置图标
    btn = QPushButton("Download")
    btn.setIcon(icon("i-download", size=14, color=accent_color))
"""
from __future__ import annotations

import re
from pathlib import Path
from xml.etree import ElementTree as ET

from PySide6.QtCore import QByteArray, QRectF, Qt, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# ============================================================
# SVG 资源路径
# ============================================================
_ASSETS = Path(__file__).parent.parent.parent / "assets"
_ICONS_FILE = _ASSETS / "icons.svg"

# 全局缓存：name -> 原始 SVG bytes（已替换 currentColor 为 {{COLOR}} 占位）
_SYMBOLS_CACHE: dict[str, bytes] = {}

# QPixmap 二级缓存：(name, size, color_rgb) -> QPixmap
# 避免 hover / press 反复重渲同色同尺寸图标
_PIXMAP_CACHE: dict[tuple[str, int, str], QPixmap] = {}

_SVG_WRAP_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" '
    'xmlns:xlink="http://www.w3.org/1999/xlink" '
    'width="{size}" height="{size}" viewBox="{viewbox}">'
    '{body}'
    '</svg>'
)


def _load_symbols() -> dict[str, bytes]:
    """解析 icons.svg，提取所有 <symbol>，预处理为带 COLOR 占位的 SVG bytes。

    将 stroke="currentColor" / fill="currentColor" 替换为 stroke="{{COLOR}}"
    以便后续动态着色（QSS 不支持 currentColor，必须 render-time 替换）。
    """
    global _SYMBOLS_CACHE
    if _SYMBOLS_CACHE:
        return _SYMBOLS_CACHE

    if not _ICONS_FILE.exists():
        raise FileNotFoundError(f"icons.svg not found: {_ICONS_FILE}")

    tree = ET.parse(_ICONS_FILE)
    root = tree.getroot()
    ns = {"svg": "http://www.w3.org/2000/svg"}

    for sym in root.findall(".//svg:symbol", ns):
        sym_id = sym.get("id", "").lstrip("i-")  # "i-home" -> "home"
        if not sym_id:
            continue
        # 保留 "i-" 前缀的两种用法
        viewbox = sym.get("viewBox", "0 0 24 24")
        # 复制 symbol 的所有子元素（path/circle/rect 等）
        body = "".join(ET.tostring(child, encoding="unicode") for child in sym)
        # 把 currentColor 替换为占位符 {{COLOR}}，渲染时再替换
        body = body.replace("currentColor", "{{COLOR}}")
        # 缓存两种 key（"home" 和 "i-home"）方便调用
        svg = _SVG_WRAP_TEMPLATE.format(size=24, viewbox=viewbox, body=body)
        _SYMBOLS_CACHE[sym_id] = svg.encode("utf-8")
        _SYMBOLS_CACHE[f"i-{sym_id}"] = svg.encode("utf-8")

    return _SYMBOLS_CACHE


def _render_pixmap(name: str, size: int, color: str) -> QPixmap:
    """渲染指定图标的 QPixmap。

    Args:
        name: 图标名，去掉 "i-" 前缀（如 "home"），也接受带前缀的 "i-home"
        size: 输出像素尺寸（正方形）
        color: 颜色值，支持 #rrggbb 或 rgba() 字符串

    Returns:
        透明背景的 QPixmap，已用指定颜色着色
    """
    symbols = _load_symbols()
    if name not in symbols:
        # 找不到时返回空 pixmap，避免 crash
        return QPixmap(size, size)

    # 把 {{COLOR}} 占位符替换为实际颜色
    # 注意：QSvgRenderer 不支持 rgba()，需要先转 #rrggbb
    color_hex = _normalize_color(color)
    svg_bytes = symbols[name].replace(b"{{COLOR}}", color_hex.encode("utf-8"))

    renderer = QSvgRenderer(QByteArray(svg_bytes))
    if not renderer.isValid():
        return QPixmap(size, size)

    # 用 devicePixelRatio 保持高清
    dpr = 1
    try:
        from PySide6.QtGui import QGuiApplication
        if QGuiApplication.primaryScreen():
            dpr = QGuiApplication.primaryScreen().devicePixelRatio()
    except Exception:
        pass
    dpr = min(dpr, 2.0)  # 限制 DPR ≤2 避免大图标浪费内存

    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pm


def _normalize_color(color: str) -> str:
    """把 rgba() 或 #rgb 颜色规范化为 QSvgRenderer 支持的 #rrggbb。

    QSvgRenderer 对 rgba() 支持不稳定，统一转 #rrggbb。
    """
    color = color.strip()
    # rgba(r, g, b, a) -> #rrggbb
    m = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", color)
    if m:
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"#{r:02x}{g:02x}{b:02x}"
    # #rgb -> #rrggbb
    if color.startswith("#") and len(color) == 4:
        return "#" + "".join(c * 2 for c in color[1:])
    return color


def icon(name: str, size: int = 16, color: str = "#ffffff") -> QIcon:
    """获取 QIcon。

    Args:
        name: 图标名（"home" 或 "i-home" 均可）
        size: 像素尺寸
        color: 颜色值，默认白色

    Returns:
        QIcon 实例
    """
    return QIcon(_pixmap_cached(name, size, color))


def pixmap(name: str, size: int = 16, color: str = "#ffffff") -> QPixmap:
    """获取 QPixmap（带缓存）。"""
    return _pixmap_cached(name, size, color)


def _pixmap_cached(name: str, size: int, color: str) -> QPixmap:
    color_norm = _normalize_color(color)
    key = (name, size, color_norm)
    pm = _PIXMAP_CACHE.get(key)
    if pm is None or pm.isNull():
        pm = _render_pixmap(name, size, color_norm)
        _PIXMAP_CACHE[key] = pm
    return pm


def clear_cache():
    """清理 pixmap 缓存。

    在主题切换 / 强制重绘时调用，确保新颜色立即生效。
    """
    _PIXMAP_CACHE.clear()


def available_icons() -> list[str]:
    """列出所有可用图标名（去 "i-" 前缀）。"""
    symbols = _load_symbols()
    return sorted({k for k in symbols if not k.startswith("i-")})


# ============================================================
# IconLabel - 直接显示 SVG 图标的 QLabel 子类
# ============================================================
from PySide6.QtWidgets import QLabel


class IconLabel(QLabel):
    """显示 SVG 图标的 QLabel。

    用法：
        lbl = IconLabel("i-download", size=16, color="#0a84ff")
        # 主题切换时改色
        lbl.set_color("#000000")

    比 QLabel + setText(unicode 字符) 方案的优势：
    - 跨平台渲染一致（Unicode 在 Win/Mac/Linux 渲染完全不同）
    - 矢量缩放无锯齿
    - 可动态变色
    """

    def __init__(self, name: str, size: int = 16, color: str = "#ffffff", parent=None):
        super().__init__(parent)
        self._name = name
        self._size = size
        self._color = color
        self._refresh()

    def set_icon(self, name: str):
        if name != self._name:
            self._name = name
            self._refresh()

    def set_color(self, color: str):
        if color != self._color:
            self._color = color
            self._refresh()

    def set_size(self, size: int):
        if size != self._size:
            self._size = size
            self._refresh()

    def _refresh(self):
        pm = pixmap(self._name, self._size, self._color)
        self.setPixmap(pm)
        self.setFixedSize(self._size, self._size)


# ============================================================
# 列出可用图标（调试用）
# ============================================================
if __name__ == "__main__":
    icons = available_icons()
    print(f"Loaded {len(icons)} icons:")
    for i in icons:
        print(f"  {i}")
