// ============================================================
// LUMIO // GlassCard — 玻璃材质卡片
// ------------------------------------------------------------
// 还原 .card 样式：
//   - 半透明 + backdrop blur(28px) + saturate(180%)
//   - 1px 顶部高光（折射感）
//   - 圆角 + 边框
// 注意：QSG OpenGL 后端在某些驱动上 backdrop blur 不支持，
//       使用 layer.effect MultiEffect 模拟（贴上层模糊）
// ============================================================
import QtQuick
import QtQuick.Effects
import Lumio

Item {
    id: root

    // ---------- 公开属性 ----------
    property int radius: Theme.rXL
    property color borderColor: Theme.glassBorder
    property color bgColor: Theme.glassBg
    property int padding: 0           // 内容内边距
    property bool topHighlight: true  // 顶部 1px 高光线
    default property alias content: _contentSlot.children

    implicitWidth: 200
    implicitHeight: 100

    // ============================================================
    // 背景层 — 玻璃材质
    // ============================================================
    Rectangle {
        id: _bg
        anchors.fill: parent
        radius: root.radius
        color: root.bgColor
        border.width: 1
        border.color: root.borderColor

        // backdrop blur 需要层合成；这里用静态半透明 + border 模拟玻璃
        // 真正的 backdrop-filter 效果由父级使用 layer.effect 实现（见 root layer）
        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: Qt.rgba(0, 0, 0, 0.18)   // 弱化阴影（原 0.6）
            shadowBlur: 0.5                        // 弱化模糊
            shadowVerticalOffset: 4                // Y 偏移（原 16）
            shadowHorizontalOffset: 0
            shadowScale: 1.0
            brightness: 0.0
            saturation: 0.0
        }
    }

    // ============================================================
    // 顶部高光 — 1px 折射光带
    // ============================================================
    Rectangle {
        id: _topHighlight
        visible: root.topHighlight
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.topMargin: 0
        anchors.leftMargin: root.radius * 0.6
        anchors.rightMargin: root.radius * 0.6
        height: 1
        radius: 0.5
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0) }
            GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, 0.4) }
            GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0) }
        }
    }

    // ============================================================
    // 内容槽
    // ============================================================
    Item {
        id: _contentSlot
        anchors.fill: parent
        anchors.margins: root.padding
        z: 1
    }
}
