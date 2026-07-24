import QtQuick
import QtQuick.Effects
import Lumio

Item {
    id: root

    default property alias contentItem: content.data
    property int padding: 24
    property int radius: Theme.rXL

    implicitWidth: 240
    implicitHeight: 160

    layer.enabled: true
    layer.effect: MultiEffect {
        shadowEnabled: true
        shadowColor: Qt.rgba(0, 0, 0, 0.6)
        shadowBlur: 0.9
        shadowOpacity: 0.6
        shadowVerticalOffset: 12
        shadowHorizontalOffset: 0
        blurEnabled: false
    }

    Rectangle {
        id: background
        anchors.fill: parent
        radius: root.radius
        color: Theme.glassBg
        border.width: 1
        border.color: Theme.glassBorder
        clip: true

        layer.enabled: true
        layer.effect: MultiEffect {
            blurEnabled: true
            blur: 0.7
            blurMax: 28
            shadowEnabled: false
        }

        Rectangle {
            id: topHighlight
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: 1
            color: "transparent"
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0) }
                GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, 0.4) }
                GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0) }
            }
        }
    }

    Item {
        id: content
        anchors.fill: parent
        anchors.margins: root.padding
        z: 1
    }
}
