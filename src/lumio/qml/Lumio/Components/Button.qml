// ============================================================
// LUMIO // Button — 按钮
// ------------------------------------------------------------
// variant: "default" / "primary" / "danger" / "ghost"
// 还原 .btn / .btn-primary / .btn-danger 样式
// ============================================================
import QtQuick
import QtQuick.Controls
import Lumio
import Lumio.Components

Button {
    id: root

    property string variant: "default"   // default / primary / danger / ghost
    property string iconName: ""         // 可选左侧图标
    property int iconSize: 14
    property real iconRotation: 0        // 图标旋转角度（仅旋转图标，不影响文字）

    implicitHeight: 36
    padding: 14

    contentItem: Row {
        spacing: 6
        anchors.centerIn: parent

        Icon {
            name: root.iconName
            size: root.iconSize
            color: _textColor
            anchors.verticalCenter: parent.verticalCenter
            visible: root.iconName.length > 0
            rotation: root.iconRotation
        }

        Text {
            text: root.text
            color: _textColor
            font.family: Theme.fontBody
            font.pixelSize: Theme.fsSmall
            font.weight: Font.DemiBold
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    background: Rectangle {
        radius: Theme.rSM
        color: _bgColor
        border.width: 1
        border.color: _borderColor

        // primary 渐变（条件启用）
        gradient: root.variant === "primary" ? _primaryGradient : null

        // hover/press 状态
        Behavior on color { ColorAnimation { duration: 150 } }
    }

    Gradient {
        id: _primaryGradient
        orientation: Gradient.Vertical
        GradientStop { position: 0.0; color: Theme.accent }
        GradientStop { position: 1.0; color: Theme.accentPress }
    }

    // ---------- 颜色映射 ----------
    readonly property color _textColor: {
        if (root.variant === "primary") return "#ffffff"
        if (root.variant === "danger")  return Theme.danger
        return root.hovered ? Theme.textPrimary : Theme.textMute
    }

    readonly property color _bgColor: {
        if (root.variant === "primary") return Theme.accent
        if (root.variant === "danger") {
            return root.hovered ? Qt.rgba(1, 69/255, 58/255, 0.12) : "transparent"
        }
        if (root.variant === "ghost")   return "transparent"
        return root.hovered ? Theme.glassBgHi : Theme.glassBg
    }

    readonly property color _borderColor: {
        if (root.variant === "primary") return "transparent"
        if (root.variant === "danger")  return Qt.rgba(1, 69/255, 58/255, 0.3)
        if (root.variant === "ghost")   return "transparent"
        return root.hovered ? Theme.glassBorderHi : Theme.glassBorder
    }

    // ---------- hover 抬升效果（仅 primary） ----------
    transform: Translate {
        y: root.variant === "primary" && root.hovered ? -1 : 0
        Behavior on y { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
    }
}
