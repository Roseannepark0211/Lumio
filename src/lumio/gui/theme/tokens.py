"""Lumio 设计 Token 系统

Liquid Glass 风格的核心视觉常量。所有 QSS 由 styles.py 基于这些 Token 生成，
彻底消除原项目「YouTube 三套蓝打架」(#3B5BDB / #FF0000 / #2563eb) 和
「深浅两份 QSS 手动镜像同步」两大顽疾。

移植自 design_preview/styles.css，Token 名称与 CSS 变量一一对应。
新增主题只需添加一个 Token dict 即可，无需改 styles.py。
"""
from __future__ import annotations

# ============================================================
# 字体（跨主题共享）
# ============================================================
FONT_DISPLAY = 'Manrope, "Segoe UI", "Microsoft YaHei UI", sans-serif'
FONT_BODY = 'Manrope, "Segoe UI", "Microsoft YaHei UI", sans-serif'
FONT_MONO = '"JetBrains Mono", "Cascadia Code", Consolas, monospace'

# 字号（7 级语义，跨主题共享）
FS_DISPLAY = 44
FS_H1 = 26
FS_H2 = 19
FS_H3 = 14
FS_BODY = 14
FS_SMALL = 12
FS_MICRO = 11

# 圆角（跨主题共享）
R_PILL = 999
R_XL = 24
R_LG = 18
R_MD = 14
R_SM = 10
R_XS = 6

# 缓动函数（跨主题共享）
EASE = "cubic-bezier(0.4, 0, 0.2, 1)"
EASE_OUT = "cubic-bezier(0.16, 1, 0.3, 1)"

# ============================================================
# 平台色（单一来源，跨主题共享）
# 根治原项目 YouTube #3B5BDB / #FF0000 / #2563eb 多套色打架问题
# ============================================================
PLATFORM_COLORS = {
    "youtube":    "#ff3b5c",
    "instagram":  "#e1306c",
    "x":          "#1d9bf0",
    "bilibili":   "#fb7299",
    "douyin":     "#25f4ee",
    "kuaishou":   "#ff6a00",
    "weibo":      "#e6162d",
    "xiaohongshu": "#ff2442",
    "xhs":        "#ff2442",  # alias
    "telegram":   "#0088cc",
}

# 状态色（跨主题共享）
STATUS_SUCCESS = "#30d158"
STATUS_WARNING = "#ffd60a"
STATUS_DANGER = "#ff453a"
STATUS_INFO = "#64d2ff"


# ============================================================
# Dark 主题 Token（Liquid Glass 主基调）
# ============================================================
DARK = {
    # 表面三层
    "bg_base":      "#07070d",
    "bg_grad_1":    "#0a0a1a",
    "bg_grad_2":    "#14141f",

    # 玻璃材质（半透明）
    "glass_bg":      "rgba(255, 255, 255, 0.045)",
    "glass_bg_hi":   "rgba(255, 255, 255, 0.08)",
    "glass_bg_press":"rgba(255, 255, 255, 0.12)",
    "glass_border":  "rgba(255, 255, 255, 0.1)",
    "glass_border_hi":"rgba(255, 255, 255, 0.2)",

    # 输入框背景（半透明黑，让玻璃材质显出来）
    "input_bg":      "rgba(0, 0, 0, 0.25)",
    "input_bg_focus":"rgba(0, 0, 0, 0.35)",

    # 文字（iOS 半透明层级）
    "text_primary":  "rgba(255, 255, 255, 0.96)",
    "text_mute":     "rgba(235, 235, 245, 0.6)",
    "text_dim":      "rgba(235, 235, 245, 0.35)",
    "text_on_accent":"#ffffff",

    # 强调色（iOS 蓝，单一来源）
    "accent":        "#0a84ff",
    "accent_2":      "#5e5ce6",
    "accent_soft":   "rgba(10, 132, 255, 0.25)",
    "accent_press":  "#0070e0",

    # 侧边栏
    "sidebar_bg":    "rgba(10, 10, 20, 0.55)",

    # 卡片背景（用于 QFrame，不能用半透明 rgba 否则子控件看不到背景）
    "card_bg":       "#12141c",
    "card_bg_hover": "#181a24",
    "card_border":   "#22253a",
    "card_border_hi":"#3e4460",

    # 分组容器
    "group_bg":      "#161822",
    "group_border":  "#22253a",

    # 阴影（QSS 不支持多层 inset 阴影，这里仅用于 reference）
    # 实际阴影通过 QGraphicsDropShadowEffect 实现
    "shadow_rgb":   "0, 0, 0",

    # 占位符色
    "placeholder":  "rgba(235, 235, 245, 0.35)",
}


# ============================================================
# Light 主题 Token
# 沿用 Liquid Glass 设计语言，但用浅色基底
# ============================================================
LIGHT = {
    # 表面三层
    "bg_base":      "#f5f5f7",
    "bg_grad_1":    "#ebebf0",
    "bg_grad_2":    "#f5f5f7",

    # 玻璃材质（白色半透明，对应 Dark 的白色半透明）
    "glass_bg":      "rgba(255, 255, 255, 0.65)",
    "glass_bg_hi":   "rgba(255, 255, 255, 0.85)",
    "glass_bg_press":"rgba(255, 255, 255, 0.95)",
    "glass_border":  "rgba(0, 0, 0, 0.08)",
    "glass_border_hi":"rgba(0, 0, 0, 0.15)",

    # 输入框背景
    "input_bg":      "rgba(255, 255, 255, 0.9)",
    "input_bg_focus":"rgba(255, 255, 255, 1.0)",

    # 文字
    "text_primary":  "rgba(0, 0, 0, 0.92)",
    "text_mute":     "rgba(60, 60, 67, 0.6)",
    "text_dim":      "rgba(60, 60, 67, 0.3)",
    "text_on_accent":"#ffffff",

    # 强调色（与 Dark 一致，iOS 蓝单一来源）
    "accent":        "#0a84ff",
    "accent_2":      "#5e5ce6",
    "accent_soft":   "rgba(10, 132, 255, 0.18)",
    "accent_press":  "#0070e0",

    # 侧边栏
    "sidebar_bg":    "rgba(255, 255, 255, 0.55)",

    # 卡片背景
    "card_bg":       "#ffffff",
    "card_bg_hover": "#f0f0f5",
    "card_border":   "#e0e0e6",
    "card_border_hi":"#c0c0cc",

    # 分组容器
    "group_bg":      "#ffffff",
    "group_border":  "#e0e0e6",

    # 阴影
    "shadow_rgb":   "0, 0, 0",

    # 占位符
    "placeholder":  "rgba(60, 60, 67, 0.3)",
}


THEMES = {
    "dark":  DARK,
    "light": LIGHT,
}


def get_tokens(theme: str = "dark") -> dict:
    """获取指定主题的 Token dict。

    Args:
        theme: "dark" 或 "light"

    Returns:
        Token dict，所有键值可直接用于 QSS 模板插值
    """
    return THEMES.get(theme, DARK)


def platform_color(platform: str) -> str:
    """获取平台色（单一来源）。

    用于：徽章背景、缩略图渐变、平台 pill 高亮等所有平台相关配色。
    根治原项目「YouTube 三套蓝打架」问题。

    Args:
        platform: youtube / instagram / x / bilibili / douyin / kuaishou / weibo / xiaohongshu / telegram

    Returns:
        16 进制色值字符串，如 "#ff3b5c"
    """
    return PLATFORM_COLORS.get(platform.lower(), "#0a84ff")


def rgba(hex_color: str, alpha: float = 1.0) -> str:
    """将 #rrggbb 转为 rgba(r, g, b, alpha) 字符串，用于 QSS。

    QSS 不支持 hex+alpha 写法，必须转 rgba。
    """
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"
