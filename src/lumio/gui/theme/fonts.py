"""Lumio 字体加载

从 assets/fonts/ 加载 Manrope 和 JetBrains Mono 字体文件。
如果字体文件不存在，静默回退到系统字体（Segoe UI / Microsoft YaHei UI）。

设计稿使用 Manrope（400/500/600/700/800）和 JetBrains Mono（400/500），
通过 Google Fonts 加载。Qt 需要本地 .ttf 文件或 QFontDatabase.addApplicationFont()。
"""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtGui import QFontDatabase

log = logging.getLogger(__name__)

# ============================================================
# 字体资源路径
# 与 icons.py 一致：src/lumio/gui/theme/fonts.py -> src/lumio/assets/
# ============================================================
_ASSETS = Path(__file__).parent.parent.parent / "assets"
_FONTS_DIR = _ASSETS / "fonts"

# 需要加载的字体文件清单
# Manrope: 400 / 500 / 600 / 700 / 800（对应设计稿 Google Fonts weight 列表）
# JetBrains Mono: 400 / 500
_FONT_FILES = [
    "Manrope-Regular.ttf",
    "Manrope-Medium.ttf",
    "Manrope-SemiBold.ttf",
    "Manrope-Bold.ttf",
    "Manrope-ExtraBold.ttf",
    "JetBrainsMono-Regular.ttf",
    "JetBrainsMono-Medium.ttf",
]

# 字体族名（addApplicationFont 成功后用于 QFontDatabase.hasFamily 校验）
# 留多个候选名应对不同 ttf 内嵌 family 命名
_MANROPE_FAMILIES = ("Manrope",)
_MONO_FAMILIES = ("JetBrains Mono", "JetBrainsMono")

# 系统回退字体（assets/fonts/ 不存在或加载失败时由 styles 使用）
FONT_FALLBACK_DISPLAY = '"Segoe UI", "Microsoft YaHei UI", sans-serif'
FONT_FALLBACK_BODY = '"Segoe UI", "Microsoft YaHei UI", sans-serif'
FONT_FALLBACK_MONO = '"Cascadia Code", Consolas, monospace'


def load_fonts() -> int:
    """从 assets/fonts/ 加载 Manrope 和 JetBrains Mono 字体文件。

    逐个尝试用 QFontDatabase.addApplicationFont() 注册字体。
    如果文件不存在，静默跳过（用户可能未安装这些字体）。

    Returns:
        成功加载的字体文件数量（0 表示未加载任何字体）
    """
    if not _FONTS_DIR.exists():
        return 0

    db = QFontDatabase()
    loaded = 0
    for fname in _FONT_FILES:
        path = _FONTS_DIR / fname
        if not path.exists():
            continue
        # addApplicationFont 返回 fontId >= 0 表示成功，-1 表示失败
        font_id = db.addApplicationFont(str(path))
        if font_id < 0:
            continue
        loaded += 1
    return loaded


def _has_manrope() -> bool:
    """检查 QFontDatabase 中是否已有 Manrope 字体族。"""
    return any(QFontDatabase.hasFamily(f) for f in _MANROPE_FAMILIES)


def _has_jetbrains_mono() -> bool:
    """检查 QFontDatabase 中是否已有 JetBrains Mono 字体族。"""
    return any(QFontDatabase.hasFamily(f) for f in _MONO_FAMILIES)


def ensure_fonts_available() -> bool:
    """确保 Manrope 和 JetBrains Mono 字体可用。

    流程：
    1. 先检查 QFontDatabase 中是否已注册（用户可能系统级安装过）
    2. 如未注册，调用 load_fonts() 从 assets/fonts/ 加载
    3. 如 assets/fonts/ 不存在或为空，打印 log 提示用户字体未安装，
       回退到系统字体（Segoe UI / Microsoft YaHei UI）

    Google Fonts 在线下载作为可选能力，当前实现不包含——网络不可用即跳过，
    由调用方使用 FONT_FALLBACK_* 常量回退。

    Returns:
        True 表示 Manrope 和 JetBrains Mono 均可用；
        False 表示至少一个缺失，将使用系统回退字体
    """
    # 1. 系统级已安装或之前已加载过
    if _has_manrope() and _has_jetbrains_mono():
        return True

    # 2. assets/fonts/ 不存在 → 直接提示并回退
    if not _FONTS_DIR.exists():
        log.info(
            "字体未安装：assets/fonts/ 目录不存在，回退到系统字体"
            "（Segoe UI / Microsoft YaHei UI）。"
        )
        return False

    # 3. 目录存在，尝试加载
    loaded = load_fonts()
    if loaded == 0:
        log.info(
            "字体未安装：assets/fonts/ 为空或加载失败，回退到系统字体"
            "（Segoe UI / Microsoft YaHei UI）。"
        )
        return False

    log.debug("从 assets/fonts/ 加载了 %d 个字体文件", loaded)

    # 4. 加载后再次校验（addApplicationFont 成功不一定代表 family 名匹配预期）
    if _has_manrope() and _has_jetbrains_mono():
        return True

    missing = []
    if not _has_manrope():
        missing.append("Manrope")
    if not _has_jetbrains_mono():
        missing.append("JetBrains Mono")
    log.info(
        "字体加载后仍缺失 %s，回退到系统字体。", ", ".join(missing)
    )
    return False


if __name__ == "__main__":
    # 调试用：直接运行查看加载情况（需先创建 QApplication）
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    count = load_fonts()
    print(f"Loaded {count} font files from {_FONTS_DIR}")
    print(f"Manrope available:       {_has_manrope()}")
    print(f"JetBrains Mono available: {_has_jetbrains_mono()}")
    print(f"ensure_fonts_available:   {ensure_fonts_available()}")
