// ============================================================
// LUMIO // LumioComboBox — 统一 ComboBox 样式
// ------------------------------------------------------------
// 玻璃底 + 圆角 + 适配 dark/light
// 用法：
//   LumioComboBox {
//       model: [{value:"a", label:"A"}, {value:"b", label:"B"}]
//       textRole: "label"; valueRole: "value"
//       onActivated: console.log(currentValue)
//   }
// ============================================================
import QtQuick
import QtQuick.Controls
import Lumio

ComboBox {
    id: control

    // placeholder：currentIndex 无效时显示，让用户知道此下拉框用途
    property string placeholder: ""

    readonly property color _textColor: Theme.textPrimary
    readonly property color _bgColor: Theme.glassBg
    readonly property color _bgHoverColor: Theme.glassBgHi
    readonly property color _borderColor: Theme.glassBorder
    readonly property color _borderFocusColor: Theme.accent

    implicitHeight: 36
    padding: 10

    font.family: Theme.fontBody
    font.pixelSize: Theme.fsBody

    // 工具函数：从 modelData 提取显示文本（兼容对象/字符串/数字）
    function _labelText(md, role) {
        if (md === null || md === undefined) return ""
        if (role === undefined || role === null || role === "") return String(md)
        if (typeof md === "object") {
            var v = md[role]
            return v === undefined || v === null ? "" : String(v)
        }
        return String(md)
    }

    // ===== 输入框 =====
    background: Rectangle {
        implicitWidth: 120
        implicitHeight: 36
        radius: Theme.rSM
        color: control.pressed ? Theme.glassBgPress
              : (control.hovered ? _bgHoverColor : _bgColor)
        border.width: 1
        border.color: control.pressed ? _borderFocusColor : _borderColor
        Behavior on color { ColorAnimation { duration: 150 } }
        Behavior on border.color { ColorAnimation { duration: 150 } }
    }

    contentItem: Text {
        leftPadding: 6
        rightPadding: control.indicator.width + 8
        // 使用 Qt 内置 currentText（自动根据 currentIndex + textRole 计算）
        // 避免 Array.isArray 对 QVariantList 失效导致收起时无文本
        text: {
            if (control.currentIndex < 0 || control.currentIndex === undefined) {
                return control.placeholder || ""
            }
            var txt = control.currentText
            return (txt && txt.length > 0) ? txt : (control.placeholder || "")
        }
        font: control.font
        // 显示 placeholder 时用灰色，让用户知道未选中
        color: (control.currentIndex < 0 && control.placeholder.length > 0)
               ? Theme.textDim
               : _textColor
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    // 下拉箭头
    indicator: Canvas {
        x: control.width - width - 10
        y: (control.height - height) / 2
        width: 12; height: 12
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            ctx.strokeStyle = Theme.textMute
            ctx.lineWidth = 1.5
            ctx.lineCap = "round"
            ctx.lineJoin = "round"
            ctx.beginPath()
            ctx.moveTo(2, 4)
            ctx.lineTo(6, 8)
            ctx.lineTo(10, 4)
            ctx.stroke()
        }
    }

    // ===== 弹出列表 =====
    popup: Popup {
        y: control.height + 4
        width: Math.max(control.width, 160)
        implicitHeight: contentItem.implicitHeight + 8
        padding: 4

        background: Rectangle {
            radius: Theme.rMD
            color: Theme.theme === "dark" ? "#1a1a2a" : "#ffffff"
            border.width: 1
            border.color: Theme.glassBorderHi
        }

        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.delegateModel
            spacing: 2
            ScrollIndicator.vertical: ScrollIndicator {}
        }
    }

    // ===== 列表项 =====
    delegate: ItemDelegate {
        width: control.popup.width - 8
        height: 32
        padding: 0

        background: Rectangle {
            radius: Theme.rXS
            color: highlighted ? Theme.accentSoft
                  : (hovered ? Theme.glassBgHi : "transparent")
            Behavior on color { ColorAnimation { duration: 100 } }
        }

        contentItem: Text {
            leftPadding: 10
            rightPadding: 10
            text: control._labelText(modelData, control.textRole)
            font: control.font
            color: highlighted ? Theme.accent : _textColor
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }

        highlighted: control.highlightedIndex === index
    }
}
