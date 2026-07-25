// ============================================================
// LUMIO // NotificationsPage — 通知页
// ------------------------------------------------------------
// 真实对接 controller:
//   - getNotificationsJson() → 通知列表
//   - unreadNotifications() → 未读数量
//   - markAllNotificationsRead() / dismissNotification(id)
//   - notificationsChanged 信号 → 刷新
// 客户端按 category 筛选（all/deps/env/update）
// ============================================================
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Lumio
import Lumio.Components

Item {
    id: root

    property var notifications: []
    property string filterCategory: "all"   // all / deps / env / update

    Connections {
        target: typeof controller !== "undefined" ? controller : null
        function onNotificationsChanged(unread_count) { _reload() }
    }

    Component.onCompleted: _reload()

    function _reload() {
        if (typeof controller === "undefined" || !controller) return
        try {
            var json = controller.getNotificationsJson()
            root.notifications = JSON.parse(json)
            _applyFilter()
        } catch (e) {
            console.log("[NotificationsPage] reload failed:", e)
        }
    }

    function _applyFilter() {
        var arr = root.notifications
        var fc = root.filterCategory
        var out = []
        for (var i = 0; i < arr.length; i++) {
            var n = arr[i]
            if (fc !== "all" && n.category !== fc) continue
            out.push(n)
        }
        _list.model = out
        _updateBadge()
    }

    function _updateBadge() {
        var unread = 0
        for (var i = 0; i < root.notifications.length; i++) {
            if (!root.notifications[i].read) unread++
        }
        _badgeText.text = unread + " " + tr("unread") + " · "
                          + root.notifications.length + " " + tr("items")
    }

    function _formatTime(t) {
        if (!t || t.length === 0) return "—"
        return t.replace("T", " ").substring(0, 19)
    }

    function _categoryLabel(c) {
        if (c === "deps")  return tr("notif_cat_deps")
        if (c === "env")   return tr("notif_cat_env")
        if (c === "update") return tr("notif_cat_update")
        return c
    }

    function _typeIcon(t) {
        if (t === "warning") return "i-warning"
        if (t === "update")  return "i-refresh"
        if (t === "tip")     return "i-info"
        return "i-info"
    }

    function _typeColor(t) {
        if (t === "warning") return Theme.warning
        if (t === "update")  return Theme.accent
        if (t === "tip")     return Theme.info
        return Theme.textMute
    }

    function _handleAction(action) {
        if (!action || action.length === 0) return
        if (action.indexOf("open_page:") === 0) {
            var page = action.substring("open_page:".length)
            // 直接修改 Main.qml 中 window 的 activePage 属性
            if (typeof window !== "undefined") window.activePage = page
        } else if (action.indexOf("open_url:") === 0) {
            var url = action.substring("open_url:".length)
            if (controller) controller.openExternalUrl(url)
        }
    }

    ScrollView {
        anchors.fill: parent
        clip: true

        ColumnLayout {
            width: parent.width
            spacing: 16

            // ============================================================
            // 视觉中心：PageHeader
            // ============================================================
            PageHeader {
                Layout.fillWidth: true
                Layout.leftMargin: 32
                Layout.rightMargin: 32
                Layout.topMargin: 24
                title: tr("notifications_page")
                subtitle: tr("notifications_subtitle")
                icon: "i-bell"

                // 右侧操作区
                Rectangle {
                    width: _badgeText.implicitWidth + 20
                    height: 22
                    radius: Theme.rPill
                    color: Qt.rgba(10/255, 132/255, 1, 0.12)
                    border.width: 1
                    border.color: Qt.rgba(10/255, 132/255, 1, 0.3)

                    Text {
                        id: _badgeText
                        anchors.centerIn: parent
                        text: "0 " + tr("unread") + " · 0 " + tr("items")
                        color: Theme.accent
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fsMicro
                        font.weight: Font.DemiBold
                    }
                }

                Button {
                    text: tr("mark_all_read")
                    variant: "default"
                    iconName: "i-check"
                    enabled: root.notifications.length > 0
                    onClicked: {
                        if (controller) controller.markAllNotificationsRead()
                    }
                }

                Button {
                    text: tr("notif_clear_read")
                    variant: "ghost"
                    iconName: "i-trash"
                    enabled: root.notifications.length > 0
                    onClicked: {
                        // 清除已读（仅前端过滤，后端 dismissable 的永久通知保留）
                        var arr = root.notifications
                        var out = []
                        for (var i = 0; i < arr.length; i++) {
                            var n = arr[i]
                            if (!n.read && n.dismissable) continue
                            if (n.read && n.dismissable) {
                                if (controller) controller.dismissNotification(n.id)
                            }
                        }
                    }
                }
            }

            // Filter bar
            GlassCard {
                Layout.fillWidth: true
                Layout.leftMargin: 48
                Layout.rightMargin: 48
                Layout.preferredHeight: 48
                radius: Theme.rMD

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    anchors.rightMargin: 14
                    spacing: 10

                    Text {
                        text: tr("notif_filter_all")
                        color: Theme.textMute
                        font.family: Theme.fontBody
                        font.pixelSize: Theme.fsSmall
                    }

                    LumioComboBox {
                        Layout.preferredWidth: 160
                        currentIndex: 0
                        model: [
                            { value: "all",    label: tr("notif_filter_all") },
                            { value: "deps",   label: tr("notif_cat_deps") },
                            { value: "env",    label: tr("notif_cat_env") },
                            { value: "update", label: tr("notif_cat_update") }
                        ]
                        textRole: "label"
                        valueRole: "value"
                        onActivated: { root.filterCategory = currentValue; _applyFilter() }
                    }
                }
            }

            // 空状态
            Text {
                visible: root.notifications.length === 0
                Layout.fillWidth: true
                Layout.topMargin: 80
                text: tr("no_notifications")
                color: Theme.textMute
                font.family: Theme.fontBody
                font.pixelSize: Theme.fsBody
                horizontalAlignment: Text.AlignHCenter
            }

            // 通知列表
            Repeater {
                id: _list
                model: []

                delegate: GlassCard {
                    Layout.fillWidth: true
                    Layout.leftMargin: 48
                    Layout.rightMargin: 48
                    Layout.preferredHeight: _content.implicitHeight + 80
                    radius: Theme.rLG

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 14
                        spacing: 14

                        // 类型图标
                        Rectangle {
                            Layout.preferredWidth: 40
                            Layout.preferredHeight: 40
                            radius: 20
                            color: Qt.rgba(_typeColor(modelData.type).r,
                                           _typeColor(modelData.type).g,
                                           _typeColor(modelData.type).b, 0.15)
                            border.width: 1
                            border.color: Qt.rgba(_typeColor(modelData.type).r,
                                                  _typeColor(modelData.type).g,
                                                  _typeColor(modelData.type).b, 0.3)

                            Icon {
                                anchors.centerIn: parent
                                name: _typeIcon(modelData.type)
                                size: 18
                                color: _typeColor(modelData.type)
                            }
                        }

                        // 内容
                        ColumnLayout {
                            id: _content
                            Layout.fillWidth: true
                            spacing: 4

                            RowLayout {
                                spacing: 8

                                Text {
                                    text: modelData.title
                                    color: Theme.textPrimary
                                    font.family: Theme.fontDisplay
                                    font.pixelSize: Theme.fsBody
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }

                                // 未读小红点
                                Rectangle {
                                    visible: !modelData.read
                                    Layout.preferredWidth: 8
                                    Layout.preferredHeight: 8
                                    radius: 4
                                    color: Theme.danger
                                }
                            }

                            Text {
                                text: modelData.message
                                color: Theme.textMute
                                font.family: Theme.fontBody
                                font.pixelSize: Theme.fsSmall
                                wrapMode: Text.Wrap
                                Layout.fillWidth: true
                                visible: modelData.message && modelData.message.length > 0
                            }

                            RowLayout {
                                spacing: 8

                                Badge {
                                    text: _categoryLabel(modelData.category)
                                }

                                Text {
                                    text: _formatTime(modelData.created_at)
                                    color: Theme.textDim
                                    font.family: Theme.fontMono
                                    font.pixelSize: Theme.fsMicro
                                }
                            }

                            // Action 按钮
                            Button {
                                visible: modelData.action_text && modelData.action_text.length > 0
                                text: modelData.action_text
                                variant: "ghost"
                                iconName: "i-external"
                                onClicked: _handleAction(modelData.action)
                            }
                        }

                        // 关闭按钮（可关闭的通知）
                        Button {
                            visible: modelData.dismissable
                            iconName: "i-close"
                            variant: "ghost"
                            iconSize: 14
                            onClicked: {
                                if (controller) controller.dismissNotification(modelData.id)
                            }
                        }
                    }
                }
            }

            Item { Layout.preferredHeight: 48 }
        }
    }
}
