// ============================================================
// LUMIO // Textarea — 多行文本输入
// ------------------------------------------------------------
// 还原 .url-textarea 样式：mono 字体 + focus ring
// ============================================================
import QtQuick
import QtQuick.Controls
import Lumio

TextArea {
    id: root

    implicitHeight: 76
    padding: 14
    color: Theme.textPrimary
    placeholderTextColor: Theme.textDim
    selectByMouse: true
    wrapMode: TextArea.Wrap
    font.family: Theme.fontMono
    font.pixelSize: 13
    font.weight: Font.Medium

    background: Rectangle {
        radius: Theme.rMD
        color: root.activeFocus ? Qt.rgba(0, 0, 0, 0.35) : Qt.rgba(0, 0, 0, 0.25)
        border.width: 1
        border.color: root.activeFocus ? Theme.accent : Theme.glassBorder

        Rectangle {
            anchors.fill: parent
            anchors.margins: -3
            radius: parent.radius + 3
            color: "transparent"
            border.width: 3
            border.color: Theme.accentSoft
            visible: root.activeFocus
            z: -1
        }

        Behavior on color { ColorAnimation { duration: 200 } }
        Behavior on border.color { ColorAnimation { duration: 200 } }
    }
}
