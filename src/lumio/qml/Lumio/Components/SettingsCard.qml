// ============================================================
// LUMIO // SettingsCard — 设置页统一卡片
// ------------------------------------------------------------
// 规范：
//   - 圆角统一（rXL）
//   - Header 高度统一（图标 + 标题 + 描述）
//   - 内容槽默认 padding
//   - 高度自适应（按内容）
// 用法：
//   SettingsCard {
//       title: tr("settings_cookie_section")
//       desc: "..."
//       icon: "i-cookie"
//       // 内容放 children
//   }
// ============================================================
import QtQuick
import QtQuick.Layouts
import Lumio
import Lumio.Components

GlassCard {
    id: root

    property string title: ""
    property string desc: ""
    property string icon: ""
    property int iconSize: 18
    property color iconColor: Theme.accent

    radius: Theme.rXL
    padding: 20

    // 内容槽
    default property alias content: _contentSlot.children

    // 高度 = 内容总高 + 上下 padding（margins 20×2 = 40）
    implicitHeight: _col.implicitHeight + 40

    ColumnLayout {
        id: _col
        anchors.fill: parent
        anchors.margins: 20
        spacing: 14

        // ===== Header（图标 + 标题 + 描述）=====
        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            // 图标圆角方块
            Rectangle {
                Layout.preferredWidth: 36
                Layout.preferredHeight: 36
                radius: 10
                color: Qt.rgba(root.iconColor.r, root.iconColor.g, root.iconColor.b, 0.15)
                border.width: 1
                border.color: Qt.rgba(root.iconColor.r, root.iconColor.g, root.iconColor.b, 0.3)
                visible: root.icon.length > 0

                Icon {
                    anchors.centerIn: parent
                    name: root.icon
                    size: root.iconSize
                    color: root.iconColor
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                Text {
                    text: root.title
                    color: Theme.textPrimary
                    font.family: Theme.fontDisplay
                    font.pixelSize: 18              // 文档要求卡片标题 22，但 22 在卡内太大；18 更协调
                    font.weight: Font.DemiBold
                }

                Text {
                    text: root.desc
                    color: Theme.textMute
                    font.family: Theme.fontBody
                    font.pixelSize: 12
                    visible: root.desc.length > 0
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }
            }
        }

        // 分隔线
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: Theme.glassBorder
        }

        // 内容槽
        ColumnLayout {
            id: _contentSlot
            Layout.fillWidth: true
            spacing: 12
        }
    }
}
