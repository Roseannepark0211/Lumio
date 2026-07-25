// ============================================================
// LUMIO // PageHeader — 页面头部（视觉中心）
// ------------------------------------------------------------
// 提供统一页面标题区：大标题 + 描述 + 右侧操作槽
// 用法：
//   PageHeader {
//       title: tr("settings_page")
//       subtitle: tr("settings_subtitle")
//   }
// 注意：根为 ColumnLayout，直接放入父 ColumnLayout 即可，
//       不要用 anchors.fill，否则会破坏 implicitHeight 链。
// ============================================================
import QtQuick
import QtQuick.Layouts
import Lumio
import Lumio.Components

ColumnLayout {
    id: root

    property string title: ""
    property string subtitle: ""
    property string icon: ""        // 可选：标题左侧图标
    property int iconSize: 22
    property color iconColor: Theme.accent

    // 右侧操作区（默认空）
    default property alias actions: _actionsSlot.children

    spacing: 6

    // ===== 标题行：图标 + 标题/副标题 + 右侧操作 =====
    RowLayout {
        Layout.fillWidth: true
        spacing: 12

        // 图标（可选）
        Icon {
            name: root.icon
            size: root.iconSize
            color: root.iconColor
            visible: root.icon.length > 0
            Layout.alignment: Qt.AlignVCenter
        }

        // 标题 + 副标题
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2

            Text {
                text: root.title
                color: Theme.textPrimary
                font.family: Theme.fontDisplay
                font.pixelSize: 30           // 文档要求页面标题 30
                font.weight: Font.Bold
                Layout.fillWidth: true
            }

            Text {
                text: root.subtitle
                color: Theme.textMute
                font.family: Theme.fontBody
                font.pixelSize: 13           // Caption
                visible: root.subtitle.length > 0
                Layout.fillWidth: true
                wrapMode: Text.Wrap
            }
        }

        // 右侧操作槽
        RowLayout {
            id: _actionsSlot
            spacing: 10
            Layout.alignment: Qt.AlignVCenter
        }
    }

    // 分隔线（柔和）
    Rectangle {
        Layout.fillWidth: true
        Layout.topMargin: 8
        height: 1
        color: Theme.glassBorder
    }
}
