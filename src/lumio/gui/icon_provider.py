"""Lumio QML UI 桥接层

将 Python 后端（DownloadManager / InboxManager / LibraryManager 等）暴露给 QML UI。
所有 QML 调用的方法、信号都通过 QmlController 暴露。
"""
from __future__ import annotations

import json
import os
import sys
import threading
import traceback
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QObject, Signal, Slot, QUrl, QTimer, Qt, QSize
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtQuick import QQuickImageProvider

_ICONS_SVG_PATH = Path(__file__).parent.parent / "qml" / "Lumio" / "Assets" / "icons.svg"


class IconProvider(QQuickImageProvider):
    """单文件 SVG <symbol> → QImage 渲染器。

    QML 调用形如：`"image://icons/i-home?color=%23ffffff&size=20"`
    """

    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.Image)
        self._symbols: dict[str, str] = {}
        self._load_symbols()

    def _load_symbols(self) -> None:
        """解析 icons.svg，提取每个 <symbol id="...">...</symbol> 的内部 XML。"""
        if not _ICONS_SVG_PATH.exists():
            print(f"[IconProvider] icons.svg not found: {_ICONS_SVG_PATH}", file=sys.stderr)
            return
        xml = _ICONS_SVG_PATH.read_text(encoding="utf-8")
        # 简单解析 <symbol id="...">...</symbol>
        import re
        pattern = re.compile(
            r'<symbol\s+id="([^"]+)"[^>]*>(.*?)</symbol>',
            re.DOTALL,
        )
        for match in pattern.finditer(xml):
            sid = match.group(1)
            inner = match.group(2)
            self._symbols[sid] = inner

    def requestImage(self, id: str, size: QSize, requestedSize: QSize) -> QImage:
        """QQuickImageProvider 接口：返回渲染后的 QImage。

        Args:
            id: "icon_id?color=%23ffffff&size=20" 形式（QML source 的 authority+query）
            size: 输出参数，回填实际图片尺寸
            requestedSize: QML 端 Image 的 width/height
        """
        # 解析 id 和 query
        color_hex = "#ffffff"
        icon_size = 24
        icon_id = id

        if "?" in id:
            icon_id, query = id.split("?", 1)
            for kv in query.split("&"):
                if "=" not in kv:
                    continue
                k, v = kv.split("=", 1)
                if k == "color":
                    # URL-decode（%23 → #）
                    from urllib.parse import unquote
                    color_hex = unquote(v)
                elif k == "size":
                    try:
                        icon_size = int(v)
                    except ValueError:
                        pass

        # 如果 QML 端指定了 width/height，优先使用
        if requestedSize.width() > 0:
            icon_size = requestedSize.width()

        # 取 symbol 内部 XML
        inner = self._symbols.get(icon_id)
        if inner is None:
            # 找不到图标，返回透明占位
            img = QImage(icon_size, icon_size, QImage.Format_ARGB32)
            img.fill(Qt.transparent)  # type: ignore[name-defined]
            size.setWidth(icon_size)
            size.setHeight(icon_size)
            return img

        # 替换 currentColor → 实际颜色
        inner_colored = inner.replace("currentColor", color_hex)

        # 构造完整 SVG
        svg_xml = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 24 24" width="{icon_size}" height="{icon_size}">'
            f'{inner_colored}'
            f'</svg>'
        )

        # 用 QSvgRenderer 渲染
        renderer = QSvgRenderer(svg_xml.encode("utf-8"))
        if not renderer.isValid():
            img = QImage(icon_size, icon_size, QImage.Format_ARGB32)
            img.fill(0)  # 透明
            size.setWidth(icon_size)
            size.setHeight(icon_size)
            return img

        img = QImage(icon_size, icon_size, QImage.Format_ARGB32)
        img.fill(0)  # 透明背景
        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing, True)
        renderer.render(painter)
        painter.end()

        size.setWidth(icon_size)
        size.setHeight(icon_size)
        return img
