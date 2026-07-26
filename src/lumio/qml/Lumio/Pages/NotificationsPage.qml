// ============================================================
// LUMIO // NotificationsPage — 通知页（v2 重构）
// ------------------------------------------------------------
// 对接 controller:
//   - getNotificationsJson() → 通知列表（含 priority/source_key/expires_at）
//   - unreadNotifications() → 未读数量
//   - markAllNotificationsRead() / markNotificationRead(id)
//   - clearReadNotifications() / dismissNotification(id)
//   - notificationsChanged 信号 → 刷新
//
// 重构要点：
//   1. 优先级视觉（critical 红色左边条 / high 橙色 / normal 默认 / low 半透明）
//   2. 新增 system 分类（紫色 accent2，含 Apify 配额 / 缓存清理等）
//   3. 永久通知用锁图标替代关闭按钮（dismissable=False 强化）
//   4. 整卡点击标记已读（修复原 QML 版缺单条已读的 bug）
//   5. "清除已读"改调 clearReadNotifications()（修复原逐条 dismiss 的 bug）
//   6. 分类筛选支持 all/deps/env/update/system/permanent
// ============================================================
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Lumio
import Lumio.Components

Item {
    id: root

    property var notifications: []
    property string filterCategory: "all"   // all/deps/env/update/system/permanent

    Connections {
        target: typeof controller !== "undefined" ? controller : null
        // 修复：用 Qt.callLater 延迟到下一个事件循环 tick
        // 否则点击卡片 → markNotificationRead → notificationsChanged → _reload
        // → _list.model = new → 当前 delegate 被销毁 → 还在处理 click 事件 → CRASH
        function onNotificationsChanged(unread_count) { Qt.callLater(_reload) }
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
            if (fc === "all") {
                out.push(n)
            } else if (fc === "permanent") {
                // permanent 筛选 = 所有 dismissable=false 的通知
                if (!n.dismissable) out.push(n)
            } else {
                if (n.category === fc && n.dismissable) out.push(n)
            }
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
        if (c === "deps")    return tr("notif_cat_deps")
        if (c === "env")     return tr("notif_cat_env")
        if (c === "update")  return tr("notif_cat_update")
        if (c === "system")  return tr("notif_cat_system")
        return c
    }

    function _typeIcon(t) {
        if (t === "warning") return "i-warning"
        if (t === "update")  return "i-refresh"
        if (t === "tip")     return "i-info"
        return "i-info"
    }

    // 按 category 决定图标色（与新分类 system 紫色一致）
    function _categoryColor(c) {
        if (c === "deps")    return Theme.warning
        if (c === "env")     return Theme.info
        if (c === "update")  return Theme.success
        if (c === "system")  return Theme.accent2
        return Theme.textMute
    }

    function _priorityColor(p) {
        if (p === "critical") return Theme.danger
        if (p === "high")     return Theme.warning
        return Theme.textMute
    }

    function _handleAction(action) {
        if (!action || action.length === 0) return
        if (action.indexOf("open_page:") === 0) {
            var page = action.substring("open_page:".length)
            if (typeof window !== "undefined") window.activePage = page
        } else if (action.indexOf("open_url:") === 0) {
            var url = action.substring("open_url:".length)
            if (controller) controller.openExternalUrl(url)
        }
    }

    ScrollView {
        id: _notifScroll
        anchors.fill: parent
        clip: true
        // 绑定 contentWidth 到视口宽度，避免 ColumnLayout 被压缩
        contentWidth: _notifScroll.width

        ColumnLayout {
            width: _notifScroll.width
            spacing: 16

            // ============================================================
            // PageHeader
            // ============================================================
            PageHeader {
                Layout.fillWidth: true
                Layout.leftMargin: 32
                Layout.rightMargin: 32
                Layout.topMargin: 24
                title: tr("notifications_page")
                subtitle: tr("notifications_subtitle")
                icon: "i-bell"

                // 未读数 badge
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
                        // 修复：原版逐条 dismissNotification 存在循环操作过期数据
                        // 和 dismiss 不检查 dismissable 的双重 bug
                        // 改为后端一次性 clear_read()（永久通知保留）
                        if (controller) controller.clearReadNotifications()
                    }
                }
            }

            // ============================================================
            // 分类筛选（segmented control 风格）
            // ============================================================
            GlassCard {
                Layout.fillWidth: true
                Layout.leftMargin: 48
                Layout.rightMargin: 48
                Layout.preferredHeight: 48
                radius: Theme.rMD

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 8
                    anchors.rightMargin: 8
                    spacing: 4

                    Repeater {
                        model: [
                            { value: "all",         label: tr("notif_filter_all"),     color: Theme.accent   },
                            { value: "deps",        label: tr("notif_cat_deps"),       color: Theme.warning  },
                            { value: "env",         label: tr("notif_cat_env"),        color: Theme.info     },
                            { value: "update",      label: tr("notif_cat_update"),     color: Theme.success  },
                            { value: "system",      label: tr("notif_cat_system"),     color: Theme.accent2  },
                            { value: "permanent",   label: tr("notif_cat_permanent"),  color: Theme.danger   }
                        ]

                        delegate: ItemDelegate {
                            Layout.preferredWidth: _segText.implicitWidth + 24
                            Layout.fillHeight: true

                            Rectangle {
                                anchors.fill: parent
                                anchors.margins: 4
                                radius: Theme.rSM
                                color: root.filterCategory === modelData.value
                                       ? Qt.rgba(modelData.color.r, modelData.color.g, modelData.color.b, 0.18)
                                       : "transparent"
                                border.width: root.filterCategory === modelData.value ? 1 : 0
                                border.color: Qt.rgba(modelData.color.r, modelData.color.g, modelData.color.b, 0.4)

                                RowLayout {
                                    anchors.centerIn: parent
                                    spacing: 6

                                    // 分类色小圆点
                                    Rectangle {
                                        visible: modelData.value !== "all"
                                        Layout.preferredWidth: 6
                                        Layout.preferredHeight: 6
                                        radius: 3
                                        color: modelData.color
                                    }

                                    Text {
                                        id: _segText
                                        text: modelData.label
                                        color: root.filterCategory === modelData.value
                                               ? Theme.textPrimary
                                               : Theme.textMute
                                        font.family: Theme.fontBody
                                        font.pixelSize: Theme.fsSmall
                                        font.weight: root.filterCategory === modelData.value
                                                     ? Font.DemiBold : Font.Normal
                                    }
                                }
                            }

                            onClicked: {
                                root.filterCategory = modelData.value
                                _applyFilter()
                            }
                        }
                    }

                    Item { Layout.fillWidth: true }
                }
            }

            // ============================================================
            // 空状态
            // ============================================================
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

            // ============================================================
            // 通知列表
            // ============================================================
            Repeater {
                id: _list
                model: []

                delegate: GlassCard {
                    Layout.fillWidth: true
                    Layout.leftMargin: 48
                    Layout.rightMargin: 48
                    Layout.preferredHeight: _cardContent.implicitHeight + 32
                    radius: Theme.rLG

                    // 整卡可点：标记已读
                    // 修复崩溃：原版 onPressed 同步调 markNotificationRead → 信号
                    // 同步触发 _reload → model 替换销毁当前 delegate → 还在 click
                    // 事件中 → CRASH。改用 onClicked + Qt.callLater 双重延迟。
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        propagateComposedEvents: true
                        onClicked: function(mouse) {
                            // 不拦截按钮区域的点击（让事件透传给 Button）
                            if (!_isPointOnInteractive(mouse.x, mouse.y)) {
                                if (!modelData.read && controller) {
                                    // 延迟到下一个事件循环 tick，确保当前 click
                                    // 事件完全结束后再触发后端调用 + 列表刷新
                                    Qt.callLater(function() {
                                        if (controller) {
                                            controller.markNotificationRead(modelData.id)
                                        }
                                    })
                                }
                            }
                            mouse.accepted = false
                        }
                    }

                    // 优先级视觉：critical/high 左侧色条
                    Rectangle {
                        visible: modelData.priority === "critical" || modelData.priority === "high"
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        anchors.margins: 10
                        width: modelData.priority === "critical" ? 3 : 2
                        radius: width / 2
                        color: _priorityColor(modelData.priority)
                        opacity: modelData.priority === "critical" ? 1.0 : 0.7
                    }

                    // 永久通知左侧 indicator
                    Rectangle {
                        visible: !modelData.dismissable
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        anchors.margins: 10
                        width: 4
                        radius: 2
                        color: Theme.danger
                        opacity: 0.6
                    }

                    function _isPointOnInteractive(x, y) {
                        // 检测点是否落在按钮上（粗略检测右下区域）
                        return x > parent.width - 100
                    }

                    RowLayout {
                        id: _cardContent
                        anchors.fill: parent
                        anchors.margins: 16
                        anchors.leftMargin: 24
                        spacing: 14

                        // 类型图标（颜色按 category 区分）
                        Rectangle {
                            Layout.preferredWidth: modelData.priority === "low" ? 32 : 40
                            Layout.preferredHeight: modelData.priority === "low" ? 32 : 40
                            Layout.alignment: Qt.AlignTop
                            radius: width / 2
                            color: Qt.rgba(_categoryColor(modelData.category).r,
                                           _categoryColor(modelData.category).g,
                                           _categoryColor(modelData.category).b, 0.15)
                            border.width: 1
                            border.color: Qt.rgba(_categoryColor(modelData.category).r,
                                                  _categoryColor(modelData.category).g,
                                                  _categoryColor(modelData.category).b, 0.3)

                            Icon {
                                anchors.centerIn: parent
                                name: _typeIcon(modelData.type)
                                size: modelData.priority === "low" ? 14 : 18
                                color: _categoryColor(modelData.category)
                            }
                        }

                        // 内容
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 6

                            // 标题行：标题 + 优先级 badge + 分类 badge + 时间
                            RowLayout {
                                spacing: 8

                                Text {
                                    text: modelData.title
                                    color: modelData.read ? Theme.textMute : Theme.textPrimary
                                    font.family: Theme.fontDisplay
                                    font.pixelSize: Theme.fsBody
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }

                                // 优先级 badge（仅 critical/high 显示）
                                Rectangle {
                                    visible: modelData.priority === "critical" || modelData.priority === "high"
                                    Layout.preferredWidth: _priorityBadgeText.implicitWidth + 12
                                    Layout.preferredHeight: 16
                                    radius: Theme.rXS
                                    color: Qt.rgba(_priorityColor(modelData.priority).r,
                                                   _priorityColor(modelData.priority).g,
                                                   _priorityColor(modelData.priority).b, 0.12)
                                    border.width: 1
                                    border.color: Qt.rgba(_priorityColor(modelData.priority).r,
                                                          _priorityColor(modelData.priority).g,
                                                          _priorityColor(modelData.priority).b, 0.3)

                                    Text {
                                        id: _priorityBadgeText
                                        anchors.centerIn: parent
                                        text: modelData.priority === "critical" ? "CRITICAL" : "HIGH"
                                        color: _priorityColor(modelData.priority)
                                        font.family: Theme.fontMono
                                        font.pixelSize: 9
                                        font.weight: Font.Bold
                                    }
                                }

                                // 分类 badge
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

                            // 消息正文
                            Text {
                                text: modelData.message
                                color: Theme.textMute
                                font.family: Theme.fontBody
                                font.pixelSize: Theme.fsSmall
                                wrapMode: Text.Wrap
                                Layout.fillWidth: true
                                visible: modelData.message && modelData.message.length > 0
                                opacity: modelData.priority === "low" ? 0.72 : 1.0
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

                        // 右侧：未读红点 + 关闭/锁图标
                        ColumnLayout {
                            Layout.alignment: Qt.AlignTop
                            spacing: 8

                            // 未读小红点
                            Rectangle {
                                visible: !modelData.read
                                Layout.preferredWidth: 8
                                Layout.preferredHeight: 8
                                radius: 4
                                color: Theme.accent
                                opacity: 0.9
                            }

                            Item { Layout.fillHeight: true }

                            // 关闭按钮（可关闭的通知）或锁图标（永久通知）
                            Button {
                                visible: modelData.dismissable
                                iconName: "i-close"
                                variant: "ghost"
                                iconSize: 14
                                onClicked: {
                                    if (controller) controller.dismissNotification(modelData.id)
                                }
                            }

                            // 永久通知的锁图标（不可关闭，hover 提示）
                            Item {
                                visible: !modelData.dismissable
                                Layout.preferredWidth: 26
                                Layout.preferredHeight: 26

                                Rectangle {
                                    anchors.centerIn: parent
                                    width: 26
                                    height: 26
                                    radius: 13
                                    color: "transparent"
                                    border.width: 1
                                    border.color: Theme.glassBorder

                                    Icon {
                                        anchors.centerIn: parent
                                        name: "i-lock"
                                        size: 12
                                        color: Theme.textDim
                                    }
                                }

                                ToolTip.visible: _lockMA.containsMouse
                                ToolTip.text: tr("notif_permanent_locked")

                                MouseArea {
                                    id: _lockMA
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.WhatsThisCursor
                                }
                            }
                        }
                    }
                }
            }

            Item { Layout.preferredHeight: 48 }
        }
    }
}
