// ============================================================
// LUMIO // Theme — Liquid Glass Design Tokens
// ------------------------------------------------------------
// 直接映射 design_preview/styles.css 的 :root 变量
// 使用 pragma Singleton 通过 `import Lumio` 全局访问
// ============================================================
pragma Singleton
import QtQuick

QtObject {
    // ============================================================
    // 当前主题（"dark" / "light"）— 切换时重绑定所有颜色
    // ============================================================
    property string theme: "dark"

    // ============================================================
    // Base surfaces
    // ============================================================
    readonly property color bgBase:       theme === "dark" ? "#07070d" : "#f5f5f8"
    readonly property color bgGrad1:      theme === "dark" ? "#0a0a1a" : "#ffffff"
    readonly property color bgGrad2:      theme === "dark" ? "#14141f" : "#ececf2"

    // ============================================================
    // Glass layers
    // ============================================================
    readonly property color glassBg:      theme === "dark" ? Qt.rgba(1, 1, 1, 0.045) : Qt.rgba(255, 255, 255, 0.7)
    readonly property color glassBgHi:    theme === "dark" ? Qt.rgba(1, 1, 1, 0.08)  : Qt.rgba(255, 255, 255, 0.9)
    readonly property color glassBgPress: theme === "dark" ? Qt.rgba(1, 1, 1, 0.12)  : Qt.rgba(255, 255, 255, 1.0)
    readonly property color glassBorder:  theme === "dark" ? Qt.rgba(1, 1, 1, 0.1)   : Qt.rgba(0, 0, 0, 0.08)
    readonly property color glassBorderHi:theme === "dark" ? Qt.rgba(1, 1, 1, 0.2)   : Qt.rgba(0, 0, 0, 0.15)

    // ============================================================
    // Text — iOS translucent hierarchy
    // ============================================================
    readonly property color textPrimary:  theme === "dark" ? Qt.rgba(1, 1, 1, 0.96) : Qt.rgba(0, 0, 0, 0.92)
    readonly property color textMute:     theme === "dark" ? Qt.rgba(235/255, 235/255, 245/255, 0.6) : Qt.rgba(0, 0, 0, 0.55)
    readonly property color textDim:      theme === "dark" ? Qt.rgba(235/255, 235/255, 245/255, 0.35) : Qt.rgba(0, 0, 0, 0.35)

    // ============================================================
    // Accent
    // ============================================================
    readonly property color accent:       "#0a84ff"
    readonly property color accent2:      "#5e5ce6"
    readonly property color accentPress:  "#0070e0"
    readonly property color accentSoft:   Qt.rgba(10/255, 132/255, 1, 0.25)

    // ============================================================
    // Status
    // ============================================================
    readonly property color success:      "#30d158"
    readonly property color warning:      "#ffd60a"
    readonly property color danger:       "#ff453a"
    readonly property color info:         "#64d2ff"

    // ============================================================
    // Platform colors
    // ============================================================
    readonly property color platYt:       "#ff3b5c"
    readonly property color platIg:       "#e1306c"
    readonly property color platX:        "#1d9bf0"
    readonly property color platBili:     "#fb7299"
    readonly property color platDouyin:   "#25f4ee"
    readonly property color platKuaishou: "#ff6a00"
    readonly property color platWeibo:    "#e6162d"
    readonly property color platXhs:      "#ff2442"
    readonly property color platTelegram: "#0088cc"

    // 平台色辅助函数
    function platformColor(name) {
        switch (name) {
            case "youtube":    return platYt
            case "instagram":  return platIg
            case "x":          return platX
            case "bilibili":   return platBili
            case "douyin":     return platDouyin
            case "kuaishou":   return platKuaishou
            case "weibo":      return platWeibo
            case "xiaohongshu":
            case "xhs":        return platXhs
            case "telegram":   return platTelegram
            default:           return accent
        }
    }

    // 平台显示名辅助函数
    // 国外平台用字母缩写（YT/IG/X/TG），国内平台用中文名（B站/抖音/快手/微博/小红书）
    function platformLabel(name) {
        switch (name) {
            case "youtube":    return "YT"
            case "instagram":  return "IG"
            case "x":          return "X"
            case "telegram":   return "TG"
            case "bilibili":   return "B站"
            case "douyin":     return "抖音"
            case "kuaishou":   return "快手"
            case "weibo":      return "微博"
            case "xiaohongshu":
            case "xhs":        return "小红书"
            default:           return (name || "").toUpperCase()
        }
    }

    // ============================================================
    // Typography
    // ============================================================
    readonly property string fontDisplay: "Manrope, 'Segoe UI', -apple-system, sans-serif"
    readonly property string fontBody:    "Manrope, 'Segoe UI', -apple-system, sans-serif"
    readonly property string fontMono:    "'JetBrains Mono', 'Consolas', ui-monospace, monospace"

    // 字号
    readonly property int fsDisplay: 44
    readonly property int fsH1:      26
    readonly property int fsH2:      19
    readonly property int fsH3:      14
    readonly property int fsBody:    14
    readonly property int fsSmall:   12
    readonly property int fsMicro:   11

    // ============================================================
    // Radius
    // ============================================================
    readonly property int rPill: 999
    readonly property int rXL:   24
    readonly property int rLG:   18
    readonly property int rMD:   14
    readonly property int rSM:   10
    readonly property int rXS:   6

    // ============================================================
    // Easing
    // ============================================================
    readonly property int easeDuration: 200
    readonly property int easeOutDuration: 250
}
