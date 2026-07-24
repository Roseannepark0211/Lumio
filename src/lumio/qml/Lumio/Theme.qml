// ============================================================
// LUMIO // LIQUID GLASS — QML Design Token Singleton
// ------------------------------------------------------------
// 整个 QML UI 的颜色 / 字号 / 圆角单一来源。
// 移植自 design_preview/styles.css 的 :root CSS 变量。
// 与 src/lumio/gui/theme/tokens.py (QSS 版) 并行存在，Token 值一一对应。
// ------------------------------------------------------------
// 用法：
//   import Lumio
//   Rectangle { color: Theme.glassBg }
//   Text { color: Theme.textPrimary; font.pixelSize: Theme.fsH1 }
// 切换主题：
//   Theme.theme = "light"   // 全局响应式刷新
// ============================================================

pragma Singleton
import QtQuick

QtObject {
    // ============================================================
    // 当前主题（"dark" / "light"）—— 改此属性即全局刷新所有引用
    // ============================================================
    property string theme: "dark"

    // ============================================================
    // 字体（跨主题）
    // ============================================================
    readonly property string fontDisplay: "Manrope"
    readonly property string fontBody: "Manrope"
    readonly property string fontMono: "JetBrains Mono"

    // ============================================================
    // 字号（7 级语义，跨主题共享）
    // ============================================================
    readonly property int fsDisplay: 44
    readonly property int fsH1: 26
    readonly property int fsH2: 19
    readonly property int fsH3: 14
    readonly property int fsBody: 14
    readonly property int fsSmall: 12
    readonly property int fsMicro: 11

    // ============================================================
    // 圆角（跨主题共享）
    // ============================================================
    readonly property int rPill: 999
    readonly property int rXL: 24
    readonly property int rLG: 18
    readonly property int rMD: 14
    readonly property int rSM: 10
    readonly property int rXS: 6

    // ============================================================
    // 布局
    // ============================================================
    readonly property int sidebarWidth: 220
    readonly property int mainPaddingTop: 40
    readonly property int mainPaddingLeft: 56
    readonly property int mainPaddingBottom: 48
    readonly property int mainMaxWidth: 1200

    // ============================================================
    // 基础表面
    // ============================================================
    readonly property color bgBase: theme === "dark" ? "#07070d" : "#f5f5f7"
    readonly property color bgGrad1: theme === "dark" ? "#0a0a1a" : "#ebebf0"
    readonly property color bgGrad2: theme === "dark" ? "#14141f" : "#f5f5f7"

    // ============================================================
    // Glass 玻璃层
    // ============================================================
    readonly property color glassBg: theme === "dark" ? Qt.rgba(1, 1, 1, 0.045) : Qt.rgba(1, 1, 1, 0.65)
    readonly property color glassBgHi: theme === "dark" ? Qt.rgba(1, 1, 1, 0.08) : Qt.rgba(1, 1, 1, 0.85)
    readonly property color glassBgPress: theme === "dark" ? Qt.rgba(1, 1, 1, 0.12) : Qt.rgba(1, 1, 1, 0.95)
    readonly property color glassBorder: theme === "dark" ? Qt.rgba(1, 1, 1, 0.1) : Qt.rgba(0, 0, 0, 0.08)
    readonly property color glassBorderHi: theme === "dark" ? Qt.rgba(1, 1, 1, 0.2) : Qt.rgba(0, 0, 0, 0.15)

    // ============================================================
    // Text — iOS 半透明层级
    // ============================================================
    readonly property color textPrimary: theme === "dark" ? Qt.rgba(1, 1, 1, 0.96) : Qt.rgba(0, 0, 0, 0.92)
    readonly property color textMute: theme === "dark" ? Qt.rgba(235/255, 235/255, 245/255, 0.6) : Qt.rgba(60/255, 60/255, 67/255, 0.6)
    readonly property color textDim: theme === "dark" ? Qt.rgba(235/255, 235/255, 245/255, 0.35) : Qt.rgba(60/255, 60/255, 67/255, 0.3)

    // ============================================================
    // Accent 强调色（跨主题一致）
    // ============================================================
    readonly property color accent: "#0a84ff"
    readonly property color accent2: "#5e5ce6"
    readonly property color accentSoft: Qt.rgba(10/255, 132/255, 1, 0.25)
    readonly property color accentPress: "#0070e0"
    readonly property color textOnAccent: "#ffffff"

    // ============================================================
    // Status 状态色（跨主题共享）
    // ============================================================
    readonly property color success: "#30d158"
    readonly property color warning: "#ffd60a"
    readonly property color danger: "#ff453a"
    readonly property color info: "#64d2ff"

    // ============================================================
    // Platform 平台色（单一来源，根治多套色打架）
    // ============================================================
    readonly property var platformColors: ({
        "youtube":     "#ff3b5c",
        "instagram":   "#e1306c",
        "x":           "#1d9bf0",
        "bilibili":    "#fb7299",
        "douyin":      "#25f4ee",
        "kuaishou":    "#ff6a00",
        "weibo":       "#e6162d",
        "xiaohongshu": "#ff2442",
        "xhs":         "#ff2442",
        "telegram":    "#0088cc"
    })

    // ============================================================
    // Card / Input / Sidebar（QFrame 兼容色）
    // ============================================================
    readonly property color cardBg: theme === "dark" ? "#12141c" : "#ffffff"
    readonly property color cardBorder: theme === "dark" ? "#22253a" : "#e0e0e6"
    readonly property color sidebarBg: theme === "dark" ? Qt.rgba(10/255, 10/255, 20/255, 0.55) : Qt.rgba(1, 1, 1, 0.55)
    readonly property color inputBg: theme === "dark" ? Qt.rgba(0, 0, 0, 0.25) : Qt.rgba(1, 1, 1, 0.9)
    readonly property color inputBgFocus: theme === "dark" ? Qt.rgba(0, 0, 0, 0.35) : Qt.rgba(1, 1, 1, 1.0)

    // ============================================================
    // 助手函数
    // ============================================================

    // 按平台 key 取色，未知平台回退到 accent
    function platformColor(plat) {
        return platformColors[plat] || accent
    }
}
