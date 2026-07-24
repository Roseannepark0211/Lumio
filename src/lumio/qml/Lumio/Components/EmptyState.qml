import QtQuick
import Lumio

Column {
    id: root
    spacing: 12

    property string icon: ""
    property string title: ""
    property string hint: ""

    Text {
        text: root.icon
        font.pixelSize: 48
        anchors.horizontalCenter: parent.horizontalCenter
    }

    Text {
        text: root.title
        color: Theme.textPrimary
        font.pixelSize: Theme.fsH2
        font.weight: Font.DemiBold
        anchors.horizontalCenter: parent.horizontalCenter
    }

    Text {
        text: root.hint
        color: Theme.textMute
        font.pixelSize: Theme.fsBody
        wrapMode: Text.WordWrap
        anchors.horizontalCenter: parent.horizontalCenter
    }
}
