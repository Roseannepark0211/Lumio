import QtQuick
import QtQuick.Controls
import Lumio

Button {
    id: control

    property string variant: "default"

    readonly property color _dangerCol: Theme.danger
    readonly property color _dangerBorder: Qt.rgba(_dangerCol.r, _dangerCol.g, _dangerCol.b, 0.3)

    implicitHeight: 36
    padding: 0
    hoverEnabled: true

    Behavior on y {
        NumberAnimation { duration: 180; easing.type: Easing.OutCubic }
    }
    y: hovered ? -1 : 0

    readonly property color _textColor: {
        if (variant === "primary") return Theme.textOnAccent
        if (variant === "danger") return Theme.danger
        return control.hovered ? Theme.textPrimary : Theme.textMute
    }
    readonly property color _bgColor: {
        if (variant === "primary") return Theme.accent
        if (variant === "danger") return Theme.glassBg
        return control.hovered ? Theme.glassBgHi : Theme.glassBg
    }
    readonly property color _borderColor: {
        if (variant === "primary") return "transparent"
        if (variant === "danger") return _dangerBorder
        return control.hovered ? Theme.glassBorderHi : Theme.glassBorder
    }

    contentItem: Text {
        text: control.text
        color: control._textColor
        font.pixelSize: Theme.fsSmall
        font.weight: Font.DemiBold
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }

    background: Rectangle {
        radius: Theme.rSM
        color: control._bgColor
        border.width: 1
        border.color: control._borderColor

        Behavior on color { ColorAnimation { duration: 150 } }
        Behavior on border.color { ColorAnimation { duration: 150 } }

        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            visible: control.variant === "primary"
            gradient: Gradient {
                orientation: Gradient.Vertical
                GradientStop { position: 0.0; color: Theme.accent }
                GradientStop { position: 1.0; color: Theme.accentPress }
            }
        }
    }
}
