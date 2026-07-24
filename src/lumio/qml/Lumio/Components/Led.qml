import QtQuick
import QtQuick.Effects
import Lumio

Item {
    id: root
    width: 6
    height: 6

    property string color: "dim"

    readonly property var _colorMap: ({
        "green": Theme.success,
        "blue": Theme.info,
        "yellow": Theme.warning,
        "red": Theme.danger,
        "pink": Theme.accent2,
        "dim": Theme.textDim
    })
    readonly property color _resolved: _colorMap[color] || Theme.textDim

    Rectangle {
        anchors.fill: parent
        radius: 3
        color: root._resolved
        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: root._resolved
            shadowBlur: 1.0
            shadowOpacity: 0.8
            shadowVerticalOffset: 0
            shadowHorizontalOffset: 0
            blurEnabled: false
        }
    }
}
