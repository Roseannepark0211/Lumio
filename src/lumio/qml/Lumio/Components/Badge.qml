// ============================================================
// LUMIO // Badge — 徽章
// ------------------------------------------------------------
// 还原 .badge 样式：圆角 pill + 微边框 + 半透明背景
// 用法：
//   Badge { text: "YouTube"; plat: "youtube" }
//   Badge { text: "Video"; media: "video" }
//   Badge { text: "Completed"; status: "completed" }
// ============================================================
import QtQuick
import Lumio

Rectangle {
    id: root

    property string text: ""
    property string plat: ""      // youtube/instagram/x/bilibili/douyin/kuaishou/weibo/xhs/telegram
    property string media: ""     // video/audio/image/mixed
    property string status: ""    // waiting/downloading/paused/retrying/interrupted/completed/failed/cancelled

    implicitWidth: _text.implicitWidth + 20
    implicitHeight: 22
    radius: Theme.rPill
    border.width: 1
    color: _bgColor
    border.color: _borderColor

    Text {
        id: _text
        anchors.centerIn: parent
        text: root.text
        color: _textColor
        font.family: Theme.fontBody
        font.pixelSize: Theme.fsMicro
        font.weight: Font.DemiBold
        font.letterSpacing: 0.3
    }

    // ---------- 颜色映射 ----------
    readonly property color _textColor: {
        if (plat.length > 0)   return Theme.platformColor(plat)
        if (media === "video") return Theme.accent
        if (media === "audio") return Theme.success
        if (media === "image") return Theme.warning
        if (media === "mixed") return Theme.accent2
        if (status === "downloading") return Theme.accent
        if (status === "paused" || status === "retrying" || status === "warning") return Theme.warning
        if (status === "completed") return Theme.success
        if (status === "failed")    return Theme.danger
        if (status === "default")   return Theme.textMute
        return Theme.textMute
    }

    readonly property color _borderColor: {
        if (plat.length > 0 || media.length > 0 || status.length > 0) {
            return Qt.rgba(_textColor.r, _textColor.g, _textColor.b, 0.3)
        }
        return Theme.glassBorder
    }

    readonly property color _bgColor: {
        if (plat.length > 0 || media.length > 0 || status.length > 0) {
            return Qt.rgba(_textColor.r, _textColor.g, _textColor.b, 0.1)
        }
        return Theme.glassBg
    }
}
