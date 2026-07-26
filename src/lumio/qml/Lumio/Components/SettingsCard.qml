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

    // ============================================================
    // 高度自适应 — 用 Binding 保证内容变化时自动更新
    // ------------------------------------------------------------
    // 历史问题：原写法 `implicitHeight: _col.implicitHeight + 40`
    // 是一次性快照计算，初始化时 _contentSlot 还没有外部注入的
    // children，导致高度算少了；后续新增内容（Cookie 网格、
    // Telegram 配对码等）时卡片不会自动变高 → 内容溢出。
    //
    // 根治：用 Binding 显式绑定，任何 child 增减/尺寸变化都会
    // 自动重新计算 implicitHeight。
    //
    // padding：顶部 24 + 底部 32 = 56（底部多留 8px，避免最后
    // 一行内容贴卡片底边，视觉上更舒适）。
    // ============================================================
    Binding on implicitHeight {
        value: _col.implicitHeight + 56
        restoreMode: Binding.RestoreBindingOrValue
    }

    implicitWidth: 300

    ColumnLayout {
        id: _col
        // 注意：不用 anchors.fill: parent（会与 implicitHeight 形成循环依赖）
        // 改用 top/left/right 锚定，bottom 不设 — 让高度按内容计算
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.topMargin: 24
        anchors.leftMargin: 24
        anchors.rightMargin: 24
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
                    font.pixelSize: 18
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

        // 内容槽 — 高度由内容驱动
        // 关键：不设 Layout.fillHeight，让 ColumnLayout 按内容计算 implicitHeight
        ColumnLayout {
            id: _contentSlot
            Layout.fillWidth: true
            spacing: 12
        }
    }
}
