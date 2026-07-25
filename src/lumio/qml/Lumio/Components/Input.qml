// ============================================================
// LUMIO // Input — 文本输入框
// ------------------------------------------------------------
// 还原 .input 样式：暗底 + 玻璃边框 + focus 蓝色 ring
// ============================================================
import QtQuick
import QtQuick.Controls
import Lumio

TextField {
    id: root

    property bool multiline: false  // 多行切换 Textarea

    implicitHeight: 38
    padding: 10
    leftPadding: 14
    rightPadding: 14
    color: Theme.textPrimary
    placeholderTextColor: Theme.textDim
    selectByMouse: true
    font.family: Theme.fontBody
    font.pixelSize: Theme.fsBody
    font.weight: Font.Medium

    background: Rectangle {
        radius: Theme.rMD
        // 浅色模式用半透明白底（跟随主题），暗色模式用玻璃黑底
        color: root.activeFocus ? Theme.glassBgPress : Theme.glassBgHi
        border.width: 1
        border.color: root.activeFocus ? Theme.accent : Theme.glassBorder

        // Focus ring
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
