// ============================================================
// LUMIO // NotificationsPage — 通知页面
// ------------------------------------------------------------
// 还原 design_preview/notifications.html：
//   - 页面头部：渐变标题 + 未读 badge + 操作按钮（全部已读 / 清空已读 / 刷新）
//   - 分类标签（分段控件）：All / Dependencies / Environment / Version / Permanent
//   - 通知列表：GlassCard 卡片（类型图标 + 标题 + 类型 badge + 时间 + 描述 + 操作）
//     · Permanent 类型：左侧红色指示条 + 红色辉光背景
//     · Read 状态：opacity 0.78
//   - 通知偏好卡：5 行 Toggle 开关
//   - 空状态：EmptyState
// 外部调用：
//   NotificationsPage { controller: myController }
// 数据：controller.notifications() -> [{ type, title, desc, time, unread,
//   permanent, actions: [{ label, kind }] }]
// ============================================================

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import Lumio
import Lumio.Components

Item {
    id: root

    implicitHeight: 720

    property var controller: null
    property var notifications: controller && typeof controller.notifications === "function"
                                 ? controller.notifications()
                                 : defaultNotifications()

    // 当前分类筛选
    property string categoryFilter: "all"

    // 通知偏好（持久化由 controller 管理，这里仅 UI 状态）
    property bool prefDesktop: true
    property bool prefAutoCheck: true
    property bool prefCookieExpiry: true
    property bool prefDownloadComplete: false
    property bool prefDownloadFailed: true

    // ---------- 统计 ----------
    readonly property int totalCount: notifications.length
    readonly property int unreadCount: {
        var n = 0
        for (var i = 0; i < notifications.length; i++) {
            if (notifications[i].unread) n++
        }
        return n
    }
    readonly property int readCount: totalCount - unreadCount
    readonly property int depCount: _countByType("dependencies")
    readonly property int envCount: _countByType("environment")
    readonly property int verCount: _countByType("version")
    readonly property int permCount: _countByType("permanent")

    function _countByType(t) {
        var n = 0
        for (var i = 0; i < notifications.length; i++) {
            if (notifications[i].type === t) n++
        }
        return n
    }

    // ---------- 默认占位数据（与 HTML 设计稿一致） ----------
    function defaultNotifications() {
        return [
            { type: "version", title: qsTr("New version available"),
              desc: qsTr("Lumio v4.3.0 is available. Current: v4.2.0. New features include improved X-Sou search and Apify proxy fallback."),
              time: "14:32", unread: true, permanent: false,
              actions: [
                  { label: qsTr("Download"), kind: "primary" },
                  { label: qsTr("View Changelog"), kind: "default" },
                  { label: qsTr("Later"), kind: "default" }
              ] },
            { type: "environment", title: qsTr("Instagram Cookie expired"),
              desc: qsTr("Your Instagram cookie has expired. Re-import to continue downloading. Mobile API calls will fail until refreshed."),
              time: "14:28", unread: true, permanent: false,
              actions: [
                  { label: qsTr("Open Settings"), kind: "primary" },
                  { label: qsTr("Dismiss"), kind: "default" }
              ] },
            { type: "dependencies", title: qsTr("FFmpeg not found"),
              desc: qsTr("FFmpeg binary is missing. Video merging will fail for YouTube and X downloads. Imageio-ffmpeg bundle may be corrupted."),
              time: "14:15", unread: true, permanent: false,
              actions: [
                  { label: qsTr("Install"), kind: "primary" },
                  { label: qsTr("Dismiss"), kind: "default" }
              ] },
            { type: "environment", title: qsTr("Telegram Bot not configured"),
              desc: qsTr("Configure Telegram Bot token to enable mobile capture. Inbox will not receive Telegram messages until configured."),
              time: "13:48", unread: true, permanent: false,
              actions: [
                  { label: qsTr("Open Settings"), kind: "primary" },
                  { label: qsTr("Dismiss"), kind: "default" }
              ] },
            { type: "permanent", title: qsTr("Instagram API Risk Notice"),
              desc: qsTr("Frequent Instagram API calls may lead to account restrictions. Use browser extension for safer downloads. This notice cannot be dismissed."),
              time: "—", unread: true, permanent: true, actions: [] },
            { type: "dependencies", title: qsTr("yt-dlp updated"),
              desc: qsTr("yt-dlp has been updated to version 2024.07.22. YouTube extraction compatibility improved."),
              time: "12:30", unread: false, permanent: false, actions: [] },
            { type: "version", title: qsTr("X GraphQL query ID updated"),
              desc: qsTr("X GraphQL query ID has been refreshed. Tweet media extraction restored after Twitter API rotation."),
              time: "11:15", unread: false, permanent: false, actions: [] },
            { type: "environment", title: qsTr("X (Twitter) Cookie configured"),
              desc: qsTr("Your X cookie is valid. Auth token + ct0 detected. Image downloads and batch enumeration enabled."),
              time: "10:42", unread: false, permanent: false, actions: [] },
            { type: "dependencies", title: qsTr("Browser extension connected"),
              desc: qsTr("Chrome/Edge extension is connected and ready. Capture endpoint responding on 127.0.0.1:38900."),
              time: "10:30", unread: false, permanent: false, actions: [] },
            { type: "environment", title: qsTr("Local API server started"),
              desc: qsTr("Flask API server running on 127.0.0.1:38900. Health check passing. Browser extension capture endpoint active."),
              time: "10:28", unread: false, permanent: false, actions: [] },
            { type: "permanent", title: qsTr("YouTube download policy"),
              desc: qsTr("YouTube downloads may be subject to copyright restrictions. Please respect content creators and applicable terms of service."),
              time: "—", unread: false, permanent: true, actions: [] },
            { type: "permanent", title: qsTr("Apify API usage"),
              desc: qsTr("Apify Actor proxy is active for Instagram. Monitor your API usage to avoid quota limits. Free tier includes $5 monthly credit."),
              time: "—", unread: false, permanent: true, actions: [] }
        ]
    }

    // ---------- 分类配置 ----------
    readonly property var categories: [
        { key: "all",           label: qsTr("All"),              count: totalCount, dotColor: "transparent" },
        { key: "dependencies",  label: qsTr("Dependencies"),     count: depCount,   dotColor: Theme.warning },
        { key: "environment",   label: qsTr("Environment"),      count: envCount,   dotColor: Theme.info },
        { key: "version",       label: qsTr("Version Updates"),  count: verCount,   dotColor: Theme.success },
        { key: "permanent",     label: qsTr("Permanent"),        count: permCount,  dotColor: Theme.danger }
    ]

    // ---------- 类型 → 图标 / 颜色映射 ----------
    function typeColor(t) {
        if (t === "dependencies") return Theme.warning
        if (t === "environment")  return Theme.info
        if (t === "version")      return Theme.success
        if (t === "permanent")    return Theme.danger
        return Theme.textMute
    }
    function typeIcon(t) {
        if (t === "dependencies") return "⚠"
        if (t === "environment")  return "ℹ"
        if (t === "version")      return "✓"
        if (t === "permanent")    return "!"
        return "•"
    }
    function typeLabel(t) {
        if (t === "dependencies") return qsTr("Dependency")
        if (t === "environment")  return qsTr("Environment")
        if (t === "version")      return qsTr("Version")
        if (t === "permanent")    return qsTr("Permanent")
        return t
    }

    // ---------- 过滤后的通知列表 ----------
    readonly property var filteredNotifications: {
        var out = []
        for (var i = 0; i < notifications.length; i++) {
            var n = notifications[i]
            if (root.categoryFilter === "all" || n.type === root.categoryFilter) {
                out.push(n)
            }
        }
        return out
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 16

        // ============================================================
        // 页面头部：渐变标题 + 未读 badge + 操作按钮
        // ============================================================
        RowLayout {
            Layout.fillWidth: true
            spacing: 14

            // 渐变标题 "Notifications"
            Canvas {
                id: titleCanvas
                Layout.preferredWidth: 200
                Layout.preferredHeight: 32
                renderStrategy: Canvas.Cooperative

                onPaint: {
                    var ctx = getContext("2d")
                    ctx.reset()
                    var text = qsTr("Notifications")
                    ctx.font = "700 " + Theme.fsH1 + "px " + Theme.fontDisplay
                    ctx.textBaseline = "top"
                    var metrics = ctx.measureText(text)
                    var w = Math.max(1, metrics.width)
                    var grad = ctx.createLinearGradient(0, 0, w, 0)
                    grad.addColorStop(0.0, "#ffffff")
                    grad.addColorStop(1.0, "#a8c7ff")
                    ctx.fillStyle = grad
                    ctx.fillText(text, 0, 2)
                }
                onWidthChanged: requestPaint()
                onHeightChanged: requestPaint()
                Component.onCompleted: requestPaint()
            }

            // 未读 badge
            Rectangle {
                Layout.alignment: Qt.AlignVCenter
                implicitWidth: unreadRow.implicitWidth + 20
                implicitHeight: 22
                radius: Theme.rPill
                color: Qt.rgba(10/255, 132/255, 1, 0.12)
                border.width: 1
                border.color: Qt.rgba(10/255, 132/255, 1, 0.3)

                RowLayout {
                    id: unreadRow
                    anchors.centerIn: parent
                    spacing: 6

                    Rectangle {
                        width: 6; height: 6; radius: 3
                        color: Theme.accent
                        layer.enabled: true
                        layer.effect: MultiEffect {
                            blurEnabled: true
                            blur: 0.6
                            blurMax: 8
                        }
                    }

                    Text {
                        text: root.unreadCount + " " + qsTr("unread")
                        color: Theme.accent
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fsMicro
                        font.letterSpacing: 0.5
                    }
                }

                // 呼吸动画
                SequentialAnimation on opacity {
                    loops: Animation.Infinite
                    NumberAnimation { from: 1.0; to: 0.65; duration: 1000 }
                    NumberAnimation { from: 0.65; to: 1.0; duration: 1000 }
                }
            }

            Item { Layout.fillWidth: true }

            // 操作按钮
            Button {
                text: qsTr("Mark All Read")
                variant: "default"
            }
            Button {
                text: qsTr("Clear Read")
                variant: "default"
            }
            Button {
                text: qsTr("Refresh")
                variant: "default"
            }
        }

        // ============================================================
        // 分类标签（分段控件）
        // ============================================================
        GlassCard {
            Layout.fillWidth: true
            padding: 4

            RowLayout {
                anchors.fill: parent
                spacing: 4

                Repeater {
                    model: root.categories

                    delegate: Rectangle {
                        id: segTab
                        required property var modelData
                        required property int index

                        Layout.preferredHeight: 36
                        implicitWidth: segRow.implicitWidth + 28
                        radius: Theme.rMD
                        color: modelData.key === root.categoryFilter ? "transparent" : "transparent"
                        border.width: 0

                        // 激活背景（渐变 + 辉光）
                        Rectangle {
                            anchors.fill: parent
                            radius: parent.radius
                            visible: modelData.key === root.categoryFilter
                            gradient: Gradient {
                                orientation: Gradient.Vertical
                                GradientStop { position: 0.0; color: Theme.accent }
                                GradientStop { position: 1.0; color: Theme.accentPress }
                            }
                            layer.enabled: true
                            layer.effect: MultiEffect {
                                blurEnabled: true
                                blur: 0.5
                                blurMax: 12
                                shadowEnabled: false
                            }
                        }

                        RowLayout {
                            id: segRow
                            anchors.centerIn: parent
                            spacing: 8

                            // 分类指示点（permanent / dependencies / 等）
                            Rectangle {
                                visible: modelData.dotColor !== "transparent"
                                width: 6; height: 6; radius: 3
                                color: modelData.dotColor
                                layer.enabled: true
                                layer.effect: MultiEffect {
                                    blurEnabled: true
                                    blur: 0.6
                                    blurMax: 8
                                }
                            }

                            Text {
                                text: modelData.label
                                color: modelData.key === root.categoryFilter ? "#ffffff" : Theme.textMute
                                font.pixelSize: Theme.fsSmall
                                font.weight: Font.DemiBold
                            }

                            // 计数 pill
                            Rectangle {
                                implicitWidth: countText.implicitWidth + 12
                                implicitHeight: countText.implicitHeight + 4
                                radius: Theme.rPill
                                color: modelData.key === root.categoryFilter
                                       ? Qt.rgba(1, 1, 1, 0.2)
                                       : Qt.rgba(1, 1, 1, 0.08)

                                Text {
                                    id: countText
                                    anchors.centerIn: parent
                                    text: modelData.count
                                    color: modelData.key === root.categoryFilter
                                           ? Qt.rgba(1, 1, 1, 0.95)
                                           : Theme.textDim
                                    font.family: Theme.fontMono
                                    font.pixelSize: 10
                                    font.letterSpacing: 0.3
                                }
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.categoryFilter = modelData.key
                        }
                    }
                }

                Item { Layout.fillWidth: true }
            }
        }

        // ============================================================
        // 通知列表 / 空状态
        // ============================================================
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.filteredNotifications.length > 0

            ColumnLayout {
                anchors.fill: parent
                spacing: 10

                Repeater {
                    model: root.filteredNotifications

                    delegate: GlassCard {
                        id: notifCard
                        required property var modelData
                        required property int index

                        Layout.fillWidth: true
                        Layout.preferredHeight: modelData.actions && modelData.actions.length > 0 ? 132 : 92
                        padding: 14

                        readonly property string notifType: modelData.type || "info"
                        readonly property color typeCol: root.typeColor(notifType)
                        readonly property bool isPermanent: !!modelData.permanent
                        readonly property bool isUnread: !!modelData.unread
                        opacity: isUnread ? 1.0 : 0.78

                        // Permanent 卡片背景：红色辉光叠加
                        Rectangle {
                            anchors.fill: parent
                            radius: parent.radius
                            visible: notifCard.isPermanent
                            color: "transparent"
                            gradient: Gradient {
                                orientation: Gradient.Horizontal
                                GradientStop { position: 0.0; color: Qt.rgba(255/255, 69/255, 58/255, 0.06) }
                                GradientStop { position: 0.6; color: Qt.rgba(255/255, 69/255, 58/255, 0) }
                            }
                        }

                        // Permanent 左侧红色指示条
                        Rectangle {
                            visible: notifCard.isPermanent
                            anchors.left: parent.left
                            anchors.top: parent.top
                            anchors.bottom: parent.bottom
                            anchors.margins: 14
                            width: 4
                            radius: 2
                            gradient: Gradient {
                                orientation: Gradient.Vertical
                                GradientStop { position: 0.0; color: Theme.danger }
                                GradientStop { position: 1.0; color: Qt.rgba(255/255, 69/255, 58/255, 0.5) }
                            }
                            layer.enabled: true
                            layer.effect: MultiEffect {
                                blurEnabled: true
                                blur: 0.6
                                blurMax: 10
                            }
                        }

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 4
                            spacing: 14

                            // ----- 左侧类型图标 -----
                            Item {
                                Layout.preferredWidth: 44
                                Layout.preferredHeight: 44
                                Layout.alignment: Qt.AlignTop

                                Rectangle {
                                    anchors.centerIn: parent
                                    width: 40; height: 40; radius: 20
                                    color: Qt.rgba(notifCard.typeCol.r, notifCard.typeCol.g, notifCard.typeCol.b, 0.15)
                                    border.width: 1
                                    border.color: Qt.rgba(notifCard.typeCol.r, notifCard.typeCol.g, notifCard.typeCol.b, 0.2)

                                    Text {
                                        anchors.centerIn: parent
                                        text: root.typeIcon(notifCard.notifType)
                                        color: notifCard.typeCol
                                        font.pixelSize: notifCard.notifType === "permanent" ? 16 : 18
                                        font.weight: Font.Bold
                                    }
                                }
                            }

                            // ----- 主体内容 -----
                            ColumnLayout {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                spacing: 6

                                // 头部行：标题 + 类型 badge + 时间
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 10

                                    Text {
                                        text: modelData.title || ""
                                        color: notifCard.isUnread ? Theme.textPrimary : Theme.textMute
                                        font.pixelSize: Theme.fsBody
                                        font.weight: Font.DemiBold
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                    }

                                    // 类型 badge
                                    Rectangle {
                                        implicitWidth: typeBadgeText.implicitWidth + 16
                                        implicitHeight: typeBadgeText.implicitHeight + 4
                                        radius: Theme.rPill
                                        color: Qt.rgba(notifCard.typeCol.r, notifCard.typeCol.g, notifCard.typeCol.b, 0.1)
                                        border.width: 1
                                        border.color: Qt.rgba(notifCard.typeCol.r, notifCard.typeCol.g, notifCard.typeCol.b, 0.25)

                                        Text {
                                            id: typeBadgeText
                                            anchors.centerIn: parent
                                            text: root.typeLabel(notifCard.notifType)
                                            color: notifCard.typeCol
                                            font.family: Theme.fontMono
                                            font.pixelSize: 10
                                            font.weight: Font.DemiBold
                                            font.letterSpacing: 0.3
                                            font.capitalization: Font.AllUppercase
                                        }
                                    }

                                    Text {
                                        text: modelData.time || ""
                                        color: Theme.textDim
                                        font.family: Theme.fontMono
                                        font.pixelSize: 10
                                        font.letterSpacing: 0.5
                                    }
                                }

                                // 描述（最多 2 行）
                                Text {
                                    Layout.fillWidth: true
                                    text: modelData.desc || ""
                                    color: Theme.textMute
                                    font.pixelSize: 13
                                    wrapMode: Text.WordWrap
                                    maximumLineCount: 2
                                    elide: Text.ElideRight
                                }

                                // 操作按钮
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 6
                                    visible: modelData.actions && modelData.actions.length > 0

                                    Repeater {
                                        model: modelData.actions || []

                                        delegate: Rectangle {
                                            id: actionBtn
                                            required property var modelData
                                            required property int index

                                            implicitWidth: actLabel.implicitWidth + 20
                                            implicitHeight: 26
                                            radius: Theme.rXS
                                            readonly property bool isPrimary: modelData.kind === "primary"
                                            color: isPrimary
                                                   ? Qt.rgba(10/255, 132/255, 1, 0.15)
                                                   : Theme.glassBg
                                            border.width: 1
                                            border.color: isPrimary
                                                          ? Qt.rgba(10/255, 132/255, 1, 0.3)
                                                          : Theme.glassBorder

                                            Text {
                                                id: actLabel
                                                anchors.centerIn: parent
                                                text: modelData.label
                                                color: actionBtn.isPrimary ? Theme.accent : Theme.textMute
                                                font.pixelSize: Theme.fsMicro
                                                font.weight: Font.DemiBold
                                            }

                                            MouseArea {
                                                anchors.fill: parent
                                                cursorShape: Qt.PointingHandCursor
                                                hoverEnabled: true
                                                onClicked: {
                                                    if (root.controller && typeof root.controller.handleNotifAction === "function") {
                                                        root.controller.handleNotifAction(notifCard.index, actionBtn.index)
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }

                                Item { Layout.fillHeight: true }
                            }

                            // ----- 右侧 aside：未读标记 + 关闭按钮 -----
                            ColumnLayout {
                                Layout.preferredWidth: 32
                                Layout.alignment: Qt.AlignTop
                                spacing: 10

                                // 未读标记（呼吸圆点）
                                Item {
                                    Layout.preferredWidth: 16
                                    Layout.preferredHeight: 16
                                    visible: notifCard.isUnread

                                    Rectangle {
                                        anchors.centerIn: parent
                                        width: 8; height: 8; radius: 4
                                        color: Theme.accent
                                        layer.enabled: true
                                        layer.effect: MultiEffect {
                                            blurEnabled: true
                                            blur: 0.6
                                            blurMax: 10
                                        }
                                        SequentialAnimation on opacity {
                                            loops: Animation.Infinite
                                            NumberAnimation { from: 1.0; to: 0.5; duration: 1000 }
                                            NumberAnimation { from: 0.5; to: 1.0; duration: 1000 }
                                        }
                                    }
                                }

                                // 关闭按钮（permanent 不显示）
                                Rectangle {
                                    Layout.preferredWidth: 26
                                    Layout.preferredHeight: 26
                                    Layout.alignment: Qt.AlignHCenter
                                    visible: !notifCard.isPermanent
                                    radius: 13
                                    color: "transparent"
                                    border.width: 1
                                    border.color: "transparent"

                                    Text {
                                        anchors.centerIn: parent
                                        text: "×"
                                        color: Theme.textDim
                                        font.pixelSize: 16
                                        font.weight: Font.Bold
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        hoverEnabled: true
                                        onClicked: {
                                            if (root.controller && typeof root.controller.dismissNotification === "function") {
                                                root.controller.dismissNotification(notifCard.index)
                                            }
                                        }
                                    }
                                }

                                Item { Layout.fillHeight: true }
                            }
                        }
                    }
                }
            }
        }

        // 空状态
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.filteredNotifications.length === 0

            Item { Layout.fillHeight: true }

            EmptyState {
                Layout.alignment: Qt.AlignHCenter
                icon: "🔔"
                title: qsTr("暂无通知")
                hint: qsTr("依赖、环境、版本更新通知会显示在这里")
            }

            Item { Layout.fillHeight: true }
        }

        // ============================================================
        // 通知偏好卡
        // ============================================================
        GlassCard {
            Layout.fillWidth: true
            padding: 24

            ColumnLayout {
                anchors.fill: parent
                spacing: 4

                // 标题
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Text {
                        text: "⚙"
                        color: Theme.accent
                        font.pixelSize: 18
                    }
                    Text {
                        text: qsTr("Notification Preferences")
                        color: Theme.textPrimary
                        font.family: Theme.fontDisplay
                        font.pixelSize: Theme.fsH2
                        font.weight: Font.Bold
                    }
                }

                Text {
                    Layout.fillWidth: true
                    text: qsTr("Configure how Lumio notifies you about important events")
                    color: Theme.textDim
                    font.pixelSize: 12
                    font.letterSpacing: 0.2
                }

                Item { Layout.preferredHeight: 8 }

                // 偏好行（可复用）
                Repeater {
                    model: [
                        { label: qsTr("Enable Desktop Notifications"), hint: qsTr("Show system notifications for important events"), checked: root.prefDesktop, prop: "prefDesktop" },
                        { label: qsTr("Auto-check Updates"), hint: qsTr("Check for new versions on app startup"), checked: root.prefAutoCheck, prop: "prefAutoCheck" },
                        { label: qsTr("Notify on Cookie Expiry"), hint: qsTr("Alert when platform cookies expire"), checked: root.prefCookieExpiry, prop: "prefCookieExpiry" },
                        { label: qsTr("Notify on Download Complete"), hint: qsTr("Show notification when downloads finish"), checked: root.prefDownloadComplete, prop: "prefDownloadComplete" },
                        { label: qsTr("Notify on Download Failed"), hint: qsTr("Show notification when downloads fail"), checked: root.prefDownloadFailed, prop: "prefDownloadFailed" }
                    ]

                    delegate: ColumnLayout {
                        id: prefRow
                        required property var modelData
                        required property int index

                        Layout.fillWidth: true
                        spacing: 0

                        // 分隔线
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 1
                            color: Theme.glassBorder
                            visible: prefRow.index > 0
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 56
                            spacing: 16

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2

                                Text {
                                    text: prefRow.modelData.label
                                    color: Theme.textPrimary
                                    font.pixelSize: Theme.fsBody
                                    font.weight: Font.DemiBold
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: prefRow.modelData.hint
                                    color: Theme.textMute
                                    font.pixelSize: 12
                                    wrapMode: Text.WordWrap
                                }
                            }

                            Item { Layout.fillWidth: true }

                            Toggle {
                                checked: prefRow.modelData.checked
                                onToggled: function(checked) {
                                    if (prefRow.modelData.prop === "prefDesktop") root.prefDesktop = checked
                                    else if (prefRow.modelData.prop === "prefAutoCheck") root.prefAutoCheck = checked
                                    else if (prefRow.modelData.prop === "prefCookieExpiry") root.prefCookieExpiry = checked
                                    else if (prefRow.modelData.prop === "prefDownloadComplete") root.prefDownloadComplete = checked
                                    else if (prefRow.modelData.prop === "prefDownloadFailed") root.prefDownloadFailed = checked

                                    if (root.controller && typeof root.controller.setNotifPref === "function") {
                                        root.controller.setNotifPref(prefRow.modelData.prop, checked)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // ============================================================
        // 状态栏
        // ============================================================
        GlassCard {
            Layout.fillWidth: true
            padding: 10

            RowLayout {
                anchors.fill: parent
                spacing: 16

                // 左侧：API 状态 + 未读/已读统计
                RowLayout {
                    spacing: 14

                    RowLayout {
                        spacing: 6
                        Rectangle { width: 7; height: 7; radius: 3.5; color: Theme.success }
                        Text {
                            text: qsTr("API Online")
                            color: Theme.textMute
                            font.pixelSize: Theme.fsMicro
                            font.family: Theme.fontMono
                        }
                    }
                    Text {
                        text: root.unreadCount + " " + qsTr("unread")
                        color: Theme.textMute
                        font.pixelSize: Theme.fsMicro
                        font.family: Theme.fontMono
                    }
                    Text {
                        text: root.readCount + " " + qsTr("read")
                        color: Theme.textMute
                        font.pixelSize: Theme.fsMicro
                        font.family: Theme.fontMono
                    }
                }

                Item { Layout.fillWidth: true }

                // 右侧：存储路径 + 更新时间
                Text {
                    text: "~/.lumio/notifications.json"
                    color: Theme.textDim
                    font.pixelSize: Theme.fsMicro
                    font.family: Theme.fontMono
                }
                Text {
                    text: qsTr("Last updated") + " 14:32"
                    color: Theme.textDim
                    font.pixelSize: Theme.fsMicro
                    font.family: Theme.fontMono
                }
            }
        }
    }
}
