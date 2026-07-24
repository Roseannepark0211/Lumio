import QtQuick
import Lumio

Item {
    id: root
    width: 44
    height: 24

    property bool checked: false
    signal toggled(bool checked)

    readonly property color _offTrack: Qt.rgba(0.5, 0.5, 0.5, 0.45)

    Rectangle {
        id: track
        anchors.fill: parent
        radius: height / 2
        color: root.checked ? Theme.accent : root._offTrack
        border.width: 0
        Behavior on color { ColorAnimation { duration: 200 } }
    }

    Rectangle {
        id: knob
        width: 20
        height: 20
        radius: 10
        anchors.verticalCenter: parent.verticalCenter
        x: root.checked ? parent.width - width - 2 : 2
        color: "white"
        Behavior on x {
            NumberAnimation { duration: 200; easing.type: Easing.OutCubic }
        }
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            root.checked = !root.checked
            root.toggled(root.checked)
        }
    }
}
