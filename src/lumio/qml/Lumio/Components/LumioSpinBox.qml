// ============================================================
// LUMIO // LumioSpinBox — 统一 SpinBox 样式（跟随主题）
// ------------------------------------------------------------
// 修复清单问题 2：原生 SpinBox 不跟随主题切换，浅色模式下割裂
// 用法与原生 SpinBox 完全相同：
//   LumioSpinBox { from: 1; to: 10; value: 3; onValueModified: ... }
// ============================================================
import QtQuick
import QtQuick.Controls
import Lumio

SpinBox {
    id: control

    // 主题色绑定（避免硬编码）
    readonly property color _textColor: Theme.textPrimary
    readonly property color _bgColor: Theme.glassBgHi
    readonly property color _bgPressColor: Theme.glassBgPress
    readonly property color _borderColor: Theme.glassBorder
    readonly property color _borderFocusColor: Theme.accent

    font.family: Theme.fontBody
    font.pixelSize: Theme.fsBody
    color: _textColor

    // ===== 输入框背景 =====
    background: Rectangle {
        implicitWidth: 140
        implicitHeight: 36
        radius: Theme.rSM
        color: control.activeFocus ? _bgPressColor : _bgColor
        border.width: 1
        border.color: control.activeFocus ? _borderFocusColor : _borderColor
        Behavior on color { ColorAnimation { duration: 150 } }
        Behavior on border.color { ColorAnimation { duration: 150 } }
    }

    // ===== 文本 =====
    contentItem: TextInput {
        z: 2
        text: control.displayText
        font: control.font
        color: _textColor
        selectionColor: Theme.accentSoft
        selectedTextColor: _textColor
        horizontalAlignment: Qt.AlignHCenter
        verticalAlignment: Qt.AlignVCenter
        readOnly: !control.editable
        validator: control.validator
        inputMethodHints: Qt.ImhFormattedNumbersOnly
    }

    // ===== 上下箭头 =====
    up.indicator: Rectangle {
        x: control.mirrored ? 0 : parent.width - width
        height: parent.height
        implicitWidth: 28
        radius: Theme.rSM
        color: control.up.pressed ? Theme.glassBgPress
              : (control.up.hovered ? Theme.glassBgPress : "transparent")
        border.width: 0

        Text {
            anchors.centerIn: parent
            text: "+"
            font.family: Theme.fontBody
            font.pixelSize: 16
            font.weight: Font.Bold
            color: control.up.pressed ? Theme.accent
                  : (control.up.hovered ? Theme.accent : Theme.textMute)
        }
    }

    down.indicator: Rectangle {
        x: control.mirrored ? parent.width - width : 0
        height: parent.height
        implicitWidth: 28
        radius: Theme.rSM
        color: control.down.pressed ? Theme.glassBgPress
              : (control.down.hovered ? Theme.glassBgPress : "transparent")
        border.width: 0

        Text {
            anchors.centerIn: parent
            text: "−"
            font.family: Theme.fontBody
            font.pixelSize: 16
            font.weight: Font.Bold
            color: control.down.pressed ? Theme.accent
                  : (control.down.hovered ? Theme.accent : Theme.textMute)
        }
    }
}
