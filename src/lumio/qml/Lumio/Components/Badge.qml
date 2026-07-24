import QtQuick
import Lumio

Rectangle {
    id: root

    property string badgeType: "default"
    property string text: ""

    radius: Theme.rPill
    border.width: 1

    readonly property bool _isPlatform: {
        var p = badgeType.toLowerCase()
        return p === "youtube" || p === "instagram" || p === "x" ||
               p === "bilibili" || p === "douyin" || p === "kuaishou" ||
               p === "weibo" || p === "xiaohongshu" || p === "xhs" ||
               p === "telegram"
    }
    readonly property bool _isStatus: {
        var p = badgeType.toLowerCase()
        return p === "success" || p === "warning" || p === "danger" || p === "info"
    }
    readonly property color _base: {
        var t = badgeType.toLowerCase()
        if (_isPlatform) return Theme.platformColor(t)
        if (t === "success") return Theme.success
        if (t === "warning") return Theme.warning
        if (t === "danger") return Theme.danger
        if (t === "info") return Theme.info
        return "transparent"
    }

    color: _isPlatform || _isStatus ? Qt.rgba(_base.r, _base.g, _base.b, 0.1) : Theme.glassBg
    border.color: _isPlatform || _isStatus ? Qt.rgba(_base.r, _base.g, _base.b, 0.3) : Theme.glassBorder

    implicitWidth: label.implicitWidth + 20
    implicitHeight: label.implicitHeight + 6

    Text {
        id: label
        anchors.centerIn: parent
        text: root.text
        color: root._isPlatform || root._isStatus ? root._base : Theme.textMute
        font.pixelSize: Theme.fsMicro
        font.weight: Font.DemiBold
    }
}
