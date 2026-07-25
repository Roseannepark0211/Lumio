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
        // 浅色模式用纯白底（用户反馈半透明白会透出灰底，看起来像灰色）
        // 暗色模式用玻璃黑底（跟随主题）
        color: Theme.theme === "light"
               ? (root.activeFocus ? "#ffffff" : "#ffffff")
               : (root.activeFocus ? Theme.glassBgPress : Theme.glassBgHi)
        border.width: 1
        border.color: root.activeFocus ? Theme.accent
                      : (Theme.theme === "light" ? Qt.rgba(0, 0, 0, 0.12) : Theme.glassBorder)

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
