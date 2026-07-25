// ============================================================
// LUMIO // Pill — 平台选择 pill
// ------------------------------------------------------------
// 还原 .pill 样式：圆角胶囊 + 平台色点 + hover 抬升
// 用法：
//   Pill { plat: "youtube"; label: "YouTube"; onClicked: ... }
// ============================================================
import QtQuick
import Lumio

Rectangle {
    id: root

    property string plat: ""
    property string label: ""
    property bool active: false

    signal clicked()

    implicitWidth: _row.implicitWidth + 28
    implicitHeight: 32
    radius: Theme.rPill
    color: active ? Theme.glassBgHi : Theme.glassBg
    border.width: 1
    border.color: active ? _platColor : Theme.glassBorder

    // hover 抬升
    transform: Translate {
        y: _mouse.containsMouse ? -2 : 0
        Behavior on y { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
    }

    // hover glow（可后续加 MultiEffect glow）
    layer.enabled: _mouse.containsMouse
    layer.effect: null

    Row {
        id: _row
        anchors.centerIn: parent
        spacing: 8

        // 平台色点
        Rectangle {
            width: 6; height: 6
            radius: 3
            anchors.verticalCenter: parent.verticalCenter
            color: _platColor
            opacity: 1
        }

        Text {
            text: root.label
            color: _mouse.containsMouse ? Theme.textPrimary : Theme.textMute
            font.family: Theme.fontBody
            font.pixelSize: Theme.fsSmall
            font.weight: Font.DemiBold
            anchors.verticalCenter: parent.verticalCenter
            Behavior on color { ColorAnimation { duration: 200 } }
        }
    }

    readonly property color _platColor: Theme.platformColor(plat)

    MouseArea {
        id: _mouse
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        hoverEnabled: true
        onClicked: root.clicked()
    }
}
