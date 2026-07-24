import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import Lumio

Button {
    id: control
    checkable: true
    property string platform: ""

    readonly property color _platformCol: Theme.platformColor(platform)

    implicitHeight: 32
    padding: 0
    hoverEnabled: true

    Behavior on y {
        NumberAnimation { duration: 180; easing.type: Easing.OutCubic }
    }
    y: hovered ? -2 : 0

    contentItem: Row {
        spacing: 6
        leftPadding: 14
        rightPadding: 14
        topPadding: 7
        bottomPadding: 7

        Item {
            width: 6
            height: 6
            anchors.verticalCenter: parent.verticalCenter

            Rectangle {
                anchors.centerIn: parent
                width: 6
                height: 6
                radius: 3
                color: control._platformCol
                opacity: 0.5
                layer.enabled: true
                layer.effect: MultiEffect {
                    blurEnabled: true
                    blur: 0.7
                    blurMax: 6
                    shadowEnabled: false
                }
            }

            Rectangle {
                anchors.centerIn: parent
                width: 6
                height: 6
                radius: 3
                color: control._platformCol
            }
        }

        Text {
            text: control.text
            color: control.checked ? control._platformCol : (control.hovered ? Theme.textPrimary : Theme.textMute)
            font.pixelSize: Theme.fsSmall
            font.weight: Font.DemiBold
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    background: Rectangle {
        radius: Theme.rPill
        color: control.checked
               ? Qt.rgba(_platformCol.r, _platformCol.g, _platformCol.b, 0.12)
               : (control.hovered ? Theme.glassBgHi : Theme.glassBg)
        border.width: 1
        border.color: (control.hovered || control.checked) ? control._platformCol : Theme.glassBorder

        Behavior on color { ColorAnimation { duration: 150 } }
        Behavior on border.color { ColorAnimation { duration: 150 } }

        layer.enabled: control.hovered
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: control._platformCol
            shadowBlur: 0.8
            shadowOpacity: 0.5
            shadowVerticalOffset: 4
            blurEnabled: false
        }
    }
}
