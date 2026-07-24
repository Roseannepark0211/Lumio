import QtQuick
import QtQuick.Controls
import Lumio

TextField {
    id: control

    color: Theme.textPrimary
    placeholderTextColor: Theme.textDim
    font.pixelSize: Theme.fsBody
    verticalAlignment: TextInput.AlignVCenter
    leftPadding: 14
    rightPadding: 14
    topPadding: 10
    bottomPadding: 10
    selectByMouse: true

    background: Item {
        implicitWidth: 220
        implicitHeight: 40

        Rectangle {
            id: focusRing
            anchors.fill: parent
            anchors.margins: -3
            color: "transparent"
            border.width: 3
            border.color: Theme.accentSoft
            radius: Theme.rMD + 3
            visible: control.activeFocus
            opacity: control.activeFocus ? 1.0 : 0.0
            Behavior on opacity { NumberAnimation { duration: 150 } }
        }

        Rectangle {
            id: bg
            anchors.fill: parent
            color: control.activeFocus ? Theme.inputBgFocus : Theme.inputBg
            border.width: 1
            border.color: control.activeFocus ? Theme.accent : Theme.glassBorder
            radius: Theme.rMD
            Behavior on color { ColorAnimation { duration: 150 } }
            Behavior on border.color { ColorAnimation { duration: 150 } }
        }
    }
}
