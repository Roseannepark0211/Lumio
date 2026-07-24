// ============================================================
// LUMIO // InboxPage — 收件箱页面
// ------------------------------------------------------------
// 还原 design_preview/inbox.html：
//   - 页面头部：渐变标题 + 新增/总数 badge + 数据源 pills + 操作按钮
//   - 筛选工具栏：搜索 + 类型 + 状态 + 平台 + 日期范围 + 重置
//   - 数据源状态卡（2 列）：Browser Extension + Telegram Bot
//   - 收件箱记录列表：GlassCard（左侧 source 指示条 + 平台渐变缩略图 + 信息 + 操作）
//     · 状态：new（呼吸点）/ downloaded（绿色）/ skipped（淡化）
//   - 格式选择对话框预览：缩略图 + 格式选项 + 操作
//   - 空状态：EmptyState
//   - 状态栏：API / Telegram / Browser 状态 + 统计
// 外部调用：
//   InboxPage { controller: myController }
// 数据：controller.inboxItems() -> [{ source, platform, type, status,
//   title, author, time, size, albumCount }]
// ============================================================

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import Lumio
import Lumio.Components

Item {
    id: root

    implicitHeight: 900

    property var controller: null
    property var inboxItems: controller && typeof controller.inboxItems === "function"
                             ? controller.inboxItems()
                             : defaultInboxItems()

    // ---------- 筛选状态 ----------
    property string searchQuery: ""
    property string sourceFilter: "all"     // all / browser / telegram
    property string typeFilter: "all"        // all / url / direct / image / video / file / note / album
    property string statusFilter: "all"      // all / new / downloaded / skipped
    property string platformFilter: "all"
    property string dateFrom: "2026-07-20"
    property string dateTo: "2026-07-24"

    // ---------- 默认占位数据（与 HTML 设计稿一致） ----------
    function defaultInboxItems() {
        return [
            { source: "browser", platform: "youtube", type: "url", status: "new",
              title: qsTr("Rick Astley — Never Gonna Give You Up"),
              author: "@RickAstleyYT", time: "14:32",
              detail: qsTr("captured from browser") },
            { source: "telegram", platform: "instagram", type: "image", status: "new",
              title: qsTr("Summer sunset over Tokyo"),
              author: "@tokyo_views", time: "14:28", size: "2.1 MB",
              detail: qsTr("via Telegram") },
            { source: "browser", platform: "x", type: "video", status: "new",
              title: qsTr("Late night design thoughts"),
              author: "@uxgod", time: "14:15",
              detail: qsTr("captured from browser") },
            { source: "telegram", platform: "telegram", type: "album", status: "new",
              title: qsTr("上海外滩夜景合集 (8 photos)"),
              author: "@shanghai_photo", time: "14:02", size: "18.4 MB", albumCount: 8,
              detail: qsTr("via Telegram") },
            { source: "browser", platform: "bilibili", type: "video", status: "downloaded",
              title: qsTr("【4K】赛博朋克城市夜景航拍"),
              author: "@drone_master", time: "13:48", size: "248 MB",
              detail: qsTr("已下载到 Library") },
            { source: "browser", platform: "xiaohongshu", type: "image", status: "skipped",
              title: qsTr("10 个桌面工具推荐"),
              author: "@toolbox_lab", time: "13:30",
              detail: qsTr("已存在于 Library") },
            { source: "telegram", platform: "telegram", type: "note", status: "new",
              title: qsTr("设计师的 5 分钟早晨仪式"),
              author: "@morning_design", time: "13:15",
              detail: qsTr("via Telegram") },
            { source: "browser", platform: "douyin", type: "video", status: "downloaded",
              title: qsTr("深夜电台·成长的悄悄话"),
              author: "@night_radio", time: "12:42", size: "6.2 MB",
              detail: qsTr("已下载到 Library") }
        ]
    }

    // ---------- 统计 ----------
    readonly property int totalCount: inboxItems.length
    readonly property int newCount: _countByStatus("new")
    readonly property int downloadedCount: _countByStatus("downloaded")
    readonly property int skippedCount: _countByStatus("skipped")
    function _countByStatus(s) {
        var n = 0
        for (var i = 0; i < inboxItems.length; i++) {
            if (inboxItems[i].status === s) n++
        }
        return n
    }

    // ---------- 数据源状态（占位） ----------
    readonly property var sourceStatus: [
        { key: "browser", name: qsTr("Browser Extension"), status: qsTr("Connected"), statusKind: "ok",
          detail: "POST /capture · Manifest V3", meta: "127.0.0.1:38900", time: qsTr("Last capture") + " 14:32" },
        { key: "telegram", name: qsTr("Telegram Bot"), status: qsTr("Polling"), statusKind: "info",
          detail: "getUpdates · long-poll mode", meta: "@lumio_capture_bot", time: qsTr("Last poll") + " 14:30" }
    ]

    // ---------- 数据源 pills ----------
    readonly property var sourcePills: [
        { key: "all",      label: qsTr("All"),       dotColor: "transparent" },
        { key: "browser",  label: qsTr("Browser"),   dotColor: Theme.accent },
        { key: "telegram", label: qsTr("Telegram"),  dotColor: Theme.platformColor("telegram") }
    ]

    // ---------- 类型 → 图标 ----------
    function typeIcon(t) {
        if (t === "url")    return "🔗"
        if (t === "direct") return "🔗"
        if (t === "image")  return "🖼"
        if (t === "video")  return "🎬"
        if (t === "file")   return "📄"
        if (t === "note")   return "📝"
        if (t === "album")  return "🎞"
        return "•"
    }
    function typeLabel(t) {
        if (t === "url")    return qsTr("URL")
        if (t === "direct") return qsTr("Direct Link")
        if (t === "image")  return qsTr("Image")
        if (t === "video")  return qsTr("Video")
        if (t === "file")   return qsTr("File")
        if (t === "note")   return qsTr("Note")
        if (t === "album")  return qsTr("Album")
        return t
    }
    function statusLabel(s) {
        if (s === "new")        return qsTr("New")
        if (s === "downloaded") return qsTr("Downloaded")
        if (s === "skipped")    return qsTr("Skipped")
        return s
    }

    // ---------- 过滤后的记录 ----------
    readonly property var filteredItems: {
        var out = []
        for (var i = 0; i < inboxItems.length; i++) {
            var it = inboxItems[i]
            if (sourceFilter !== "all" && it.source !== sourceFilter) continue
            if (typeFilter !== "all" && it.type !== typeFilter) continue
            if (statusFilter !== "all" && it.status !== statusFilter) continue
            if (platformFilter !== "all" && it.platform !== platformFilter) continue
            if (searchQuery && searchQuery.length > 0) {
                var q = searchQuery.toLowerCase()
                var hay = ((it.title || "") + " " + (it.author || "")).toLowerCase()
                if (hay.indexOf(q) < 0) continue
            }
            out.push(it)
        }
        return out
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 16

        // ============================================================
        // 页面头部：渐变标题 + badge + source pills + 操作按钮
        // ============================================================
        RowLayout {
            Layout.fillWidth: true
            spacing: 14

            // 渐变标题 "Inbox"
            Canvas {
                id: titleCanvas
                Layout.preferredWidth: 90
                Layout.preferredHeight: 32
                renderStrategy: Canvas.Cooperative

                onPaint: {
                    var ctx = getContext("2d")
                    ctx.reset()
                    var text = qsTr("Inbox")
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

            // 新增 / 总数 badge
            Rectangle {
                Layout.alignment: Qt.AlignVCenter
                implicitWidth: badgeRow.implicitWidth + 20
                implicitHeight: 22
                radius: Theme.rPill
                color: Qt.rgba(10/255, 132/255, 1, 0.12)
                border.width: 1
                border.color: Qt.rgba(10/255, 132/255, 1, 0.3)

                RowLayout {
                    id: badgeRow
                    anchors.centerIn: parent
                    spacing: 6

                    Text {
                        text: root.newCount + " " + qsTr("new")
                        color: Theme.accent
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fsMicro
                        font.weight: Font.DemiBold
                        font.letterSpacing: 0.5
                    }
                    Text {
                        text: "·"
                        color: Theme.textDim
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fsMicro
                    }
                    Text {
                        text: root.totalCount + " " + qsTr("total")
                        color: Theme.textMute
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fsMicro
                        font.letterSpacing: 0.5
                    }
                }
            }

            // 数据源 pills
            Rectangle {
                Layout.alignment: Qt.AlignVCenter
                implicitWidth: pillsRow.implicitWidth + 8
                implicitHeight: 30
                radius: Theme.rPill
                color: Qt.rgba(0, 0, 0, 0.3)
                border.width: 1
                border.color: Theme.glassBorder

                RowLayout {
                    id: pillsRow
                    anchors.centerIn: parent
                    spacing: 4

                    Repeater {
                        model: root.sourcePills

                        delegate: Rectangle {
                            id: pill
                            required property var modelData
                            required property int index

                            implicitWidth: pillRow.implicitWidth + 24
                            implicitHeight: 24
                            radius: Theme.rPill
                            color: modelData.key === root.sourceFilter
                                   ? "transparent" : "transparent"
                            border.width: 0

                            Rectangle {
                                anchors.fill: parent
                                radius: parent.radius
                                visible: modelData.key === root.sourceFilter
                                gradient: Gradient {
                                    orientation: Gradient.Vertical
                                    GradientStop { position: 0.0; color: Theme.accent }
                                    GradientStop { position: 1.0; color: Theme.accentPress }
                                }
                            }

                            RowLayout {
                                id: pillRow
                                anchors.centerIn: parent
                                spacing: 6

                                Rectangle {
                                    visible: modelData.dotColor !== "transparent"
                                    width: 5; height: 5; radius: 2.5
                                    color: modelData.key === root.sourceFilter
                                           ? "#ffffff" : modelData.dotColor
                                    layer.enabled: modelData.dotColor !== "transparent"
                                    layer.effect: MultiEffect {
                                        blurEnabled: true
                                        blur: 0.6
                                        blurMax: 8
                                    }
                                }

                                Text {
                                    text: modelData.label
                                    color: modelData.key === root.sourceFilter ? "#ffffff" : Theme.textMute
                                    font.pixelSize: Theme.fsMicro
                                    font.weight: Font.DemiBold
                                    font.letterSpacing: 0.3
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.sourceFilter = modelData.key
                            }
                        }
                    }
                }
            }

            Item { Layout.fillWidth: true }

            // 操作按钮
            Button {
                text: qsTr("Refresh")
                variant: "default"
            }
            Button {
                text: qsTr("Download All")
                variant: "primary"
            }
            Button {
                text: qsTr("Clear All")
                variant: "danger"
            }
        }

        // ============================================================
        // 筛选工具栏
        // ============================================================
        GlassCard {
            Layout.fillWidth: true
            padding: 14

            RowLayout {
                anchors.fill: parent
                spacing: 10

                // 搜索框
                Input {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    placeholderText: qsTr("搜索标题、URL、作者...")
                    text: root.searchQuery
                    onTextEdited: root.searchQuery = text
                }

                // 类型筛选
                ComboBox {
                    id: typeCombo
                    Layout.preferredWidth: 130
                    model: [qsTr("All Types"), qsTr("URL"), qsTr("Direct Link"),
                            qsTr("Image"), qsTr("Video"), qsTr("File"),
                            qsTr("Note"), qsTr("Album")]
                    onActivated: root.typeFilter = (index === 0) ? "all"
                                 : ["all","url","direct","image","video","file","note","album"][index]

                    background: Rectangle {
                        color: Theme.inputBg
                        border.width: 1
                        border.color: typeCombo.activeFocus ? Theme.accent : Theme.glassBorder
                        radius: Theme.rMD
                    }
                    contentItem: Text {
                        text: typeCombo.displayText
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fsSmall
                        verticalAlignment: Text.AlignVCenter
                        leftPadding: 10
                    }
                }

                // 状态筛选
                ComboBox {
                    id: statusCombo
                    Layout.preferredWidth: 130
                    model: [qsTr("All Status"), qsTr("New"), qsTr("Downloaded"), qsTr("Skipped")]
                    onActivated: root.statusFilter = (index === 0) ? "all"
                                 : ["all","new","downloaded","skipped"][index]

                    background: Rectangle {
                        color: Theme.inputBg
                        border.width: 1
                        border.color: statusCombo.activeFocus ? Theme.accent : Theme.glassBorder
                        radius: Theme.rMD
                    }
                    contentItem: Text {
                        text: statusCombo.displayText
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fsSmall
                        verticalAlignment: Text.AlignVCenter
                        leftPadding: 10
                    }
                }

                // 平台筛选
                ComboBox {
                    id: platCombo
                    Layout.preferredWidth: 130
                    model: [qsTr("All Platforms"), "YouTube", "Instagram", "X",
                            qsTr("B站"), qsTr("抖音"), qsTr("快手"),
                            qsTr("微博"), qsTr("小红书"), "Telegram"]
                    onActivated: root.platformFilter = (index === 0) ? "all"
                                 : ["all","youtube","instagram","x","bilibili","douyin",
                                    "kuaishou","weibo","xiaohongshu","telegram"][index]

                    background: Rectangle {
                        color: Theme.inputBg
                        border.width: 1
                        border.color: platCombo.activeFocus ? Theme.accent : Theme.glassBorder
                        radius: Theme.rMD
                    }
                    contentItem: Text {
                        text: platCombo.displayText
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fsSmall
                        verticalAlignment: Text.AlignVCenter
                        leftPadding: 10
                    }
                }

                // 日期范围
                RowLayout {
                    spacing: 6

                    TextField {
                        id: dateFromInput
                        Layout.preferredWidth: 110
                        text: root.dateFrom
                        color: Theme.textPrimary
                        font.family: Theme.fontMono
                        font.pixelSize: 11
                        horizontalAlignment: Text.AlignHCenter
                        onTextEdited: root.dateFrom = text

                        background: Rectangle {
                            color: Theme.inputBg
                            border.width: 1
                            border.color: dateFromInput.activeFocus ? Theme.accent : Theme.glassBorder
                            radius: Theme.rMD
                        }
                    }

                    Text {
                        text: "—"
                        color: Theme.textDim
                        font.pixelSize: Theme.fsMicro
                    }

                    TextField {
                        id: dateToInput
                        Layout.preferredWidth: 110
                        text: root.dateTo
                        color: Theme.textPrimary
                        font.family: Theme.fontMono
                        font.pixelSize: 11
                        horizontalAlignment: Text.AlignHCenter
                        onTextEdited: root.dateTo = text

                        background: Rectangle {
                            color: Theme.inputBg
                            border.width: 1
                            border.color: dateToInput.activeFocus ? Theme.accent : Theme.glassBorder
                            radius: Theme.rMD
                        }
                    }
                }

                // 重置按钮
                Button {
                    text: "✕"
                    variant: "default"
                    implicitWidth: 32
                    implicitHeight: 32
                    onClicked: {
                        root.searchQuery = ""
                        root.sourceFilter = "all"
                        root.typeFilter = "all"
                        root.statusFilter = "all"
                        root.platformFilter = "all"
                        typeCombo.currentIndex = 0
                        statusCombo.currentIndex = 0
                        platCombo.currentIndex = 0
                    }
                }
            }
        }

        // ============================================================
        // 数据源状态卡（2 列）
        // ============================================================
        GridLayout {
            Layout.fillWidth: true
            columns: 2
            columnSpacing: 12
            rowSpacing: 12

            Repeater {
                model: root.sourceStatus

                delegate: GlassCard {
                    id: srcCard
                    required property var modelData
                    required property int index

                    Layout.fillWidth: true
                    Layout.preferredHeight: 76
                    padding: 14

                    readonly property color srcColor: modelData.key === "browser"
                                                      ? Theme.accent
                                                      : Theme.platformColor("telegram")

                    RowLayout {
                        anchors.fill: parent
                        spacing: 12

                        // 左侧：图标 + 名称 + 详情
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12

                            // 图标方块
                            Rectangle {
                                Layout.preferredWidth: 40
                                Layout.preferredHeight: 40
                                radius: Theme.rMD
                                color: Theme.glassBgHi
                                border.width: 1
                                border.color: Theme.glassBorder

                                Text {
                                    anchors.centerIn: parent
                                    text: srcCard.modelData.key === "browser" ? "🌐" : "✈"
                                    font.pixelSize: 18
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2

                                RowLayout {
                                    spacing: 8

                                    Text {
                                        text: srcCard.modelData.name
                                        color: Theme.textPrimary
                                        font.pixelSize: Theme.fsBody
                                        font.weight: Font.DemiBold
                                    }

                                    // mini status badge
                                    Rectangle {
                                        implicitWidth: miniStatusText.implicitWidth + 14
                                        implicitHeight: miniStatusText.implicitHeight + 4
                                        radius: Theme.rPill
                                        readonly property bool isOk: srcCard.modelData.statusKind === "ok"
                                        color: isOk
                                               ? Qt.rgba(48/255, 209/255, 88/255, 0.12)
                                               : Qt.rgba(10/255, 132/255, 1, 0.12)
                                        border.width: 1
                                        border.color: isOk
                                                      ? Qt.rgba(48/255, 209/255, 88/255, 0.3)
                                                      : Qt.rgba(10/255, 132/255, 1, 0.3)

                                        RowLayout {
                                            anchors.centerIn: parent
                                            spacing: 4

                                            Rectangle {
                                                width: 5; height: 5; radius: 2.5
                                                color: parent.parent.isOk ? Theme.success : Theme.accent
                                                layer.enabled: true
                                                layer.effect: MultiEffect {
                                                    blurEnabled: true
                                                    blur: 0.5
                                                    blurMax: 6
                                                }
                                            }

                                            Text {
                                                id: miniStatusText
                                                text: srcCard.modelData.status
                                                color: parent.parent.isOk ? Theme.success : Theme.accent
                                                font.pixelSize: 10
                                                font.weight: Font.DemiBold
                                            }
                                        }
                                    }
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: srcCard.modelData.detail
                                    color: Theme.textDim
                                    font.family: Theme.fontMono
                                    font.pixelSize: Theme.fsMicro
                                    font.letterSpacing: 0.3
                                    elide: Text.ElideRight
                                }
                            }
                        }

                        // 右侧：地址 + 时间
                        ColumnLayout {
                            Layout.alignment: Qt.AlignRight
                            spacing: 2

                            Text {
                                text: srcCard.modelData.meta
                                color: Theme.textMute
                                font.family: Theme.fontMono
                                font.pixelSize: 11
                                font.letterSpacing: 0.3
                            }
                            Text {
                                text: srcCard.modelData.time
                                color: Theme.textDim
                                font.family: Theme.fontMono
                                font.pixelSize: 10
                            }
                        }
                    }
                }
            }
        }

        // ============================================================
        // 收件箱记录列表 / 空状态
        // ============================================================
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.filteredItems.length > 0

            ColumnLayout {
                anchors.fill: parent
                spacing: 10

                Repeater {
                    model: root.filteredItems

                    delegate: GlassCard {
                        id: recordCard
                        required property var modelData
                        required property int index

                        Layout.fillWidth: true
                        Layout.preferredHeight: 92
                        padding: 14

                        readonly property string source: modelData.source || "browser"
                        readonly property string platform: modelData.platform || ""
                        readonly property string rType: modelData.type || "url"
                        readonly property string rStatus: modelData.status || "new"
                        readonly property color platColor: Theme.platformColor(platform)
                        readonly property color srcColor: source === "browser"
                                                          ? Theme.accent
                                                          : Theme.platformColor("telegram")
                        opacity: rStatus === "skipped" ? 0.78 : 1.0

                        // downloaded 状态的轻微绿色背景
                        Rectangle {
                            anchors.fill: parent
                            radius: parent.radius
                            visible: recordCard.rStatus === "downloaded"
                            color: Qt.rgba(48/255, 209/255, 88/255, 0.03)
                        }

                        RowLayout {
                            anchors.fill: parent
                            spacing: 14

                            // ----- 左侧 source 指示条 -----
                            Rectangle {
                                Layout.preferredWidth: 4
                                Layout.fillHeight: true
                                Layout.minimumHeight: 56
                                radius: 2
                                gradient: Gradient {
                                    orientation: Gradient.Vertical
                                    GradientStop { position: 0.0; color: recordCard.srcColor }
                                    GradientStop { position: 1.0; color: recordCard.source === "browser"
                                                                        ? Theme.accent2
                                                                        : Qt.rgba(94/255, 197/255, 1, 1) }
                                }
                                layer.enabled: true
                                layer.effect: MultiEffect {
                                    blurEnabled: true
                                    blur: 0.5
                                    blurMax: 8
                                }
                            }

                            // ----- 平台渐变缩略图 -----
                            Item {
                                Layout.preferredWidth: 56
                                Layout.preferredHeight: 56

                                Rectangle {
                                    anchors.fill: parent
                                    radius: Theme.rMD
                                    gradient: Gradient {
                                        orientation: Gradient.Horizontal
                                        GradientStop { position: 0.0; color: recordCard.platColor }
                                        GradientStop { position: 1.0; color: recordCard.platform === "telegram"
                                                                            ? Qt.rgba(94/255, 197/255, 1, 1)
                                                                            : Theme.accent2 }
                                    }
                                    layer.enabled: true
                                    layer.effect: MultiEffect {
                                        blurEnabled: false
                                        shadowEnabled: true
                                        shadowColor: Qt.rgba(0, 0, 0, 0.5)
                                        shadowBlur: 0.6
                                        shadowOpacity: 0.5
                                        shadowVerticalOffset: 4
                                    }

                                    // 高光
                                    Rectangle {
                                        anchors.fill: parent
                                        radius: parent.radius
                                        gradient: Gradient {
                                            orientation: Gradient.Vertical
                                            GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.25) }
                                            GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, 0) }
                                            GradientStop { position: 1.0; color: Qt.rgba(0, 0, 0, 0.3) }
                                        }
                                    }

                                    Text {
                                        anchors.centerIn: parent
                                        text: root.typeIcon(recordCard.rType)
                                        font.pixelSize: 22
                                        z: 2
                                    }

                                    // Album 数量角标
                                    Rectangle {
                                        visible: recordCard.rType === "album" && !!recordCard.modelData.albumCount
                                        anchors.bottom: parent.bottom
                                        anchors.right: parent.right
                                        anchors.margins: 3
                                        radius: Theme.rPill
                                        color: Qt.rgba(0, 0, 0, 0.65)
                                        border.width: 1
                                        border.color: Qt.rgba(1, 1, 1, 0.15)
                                        implicitWidth: albumCountText.implicitWidth + 10
                                        implicitHeight: albumCountText.implicitHeight + 2

                                        Text {
                                            id: albumCountText
                                            anchors.centerIn: parent
                                            text: recordCard.modelData.albumCount || 0
                                            color: "#ffffff"
                                            font.family: Theme.fontMono
                                            font.pixelSize: 9
                                            font.weight: Font.DemiBold
                                        }
                                    }
                                }
                            }

                            // ----- 信息块 -----
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6

                                // badge 行：平台 + 类型 + 状态
                                RowLayout {
                                    spacing: 6

                                    Badge {
                                        badgeType: recordCard.platform
                                        text: recordCard.platform === "xiaohongshu" ? qsTr("小红书")
                                              : (recordCard.platform === "bilibili" ? qsTr("B站") : recordCard.platform)
                                    }

                                    Badge {
                                        badgeType: recordCard.rType === "url" ? "info" : "default"
                                        text: root.typeLabel(recordCard.rType)
                                    }

                                    // 状态 badge
                                    Rectangle {
                                        implicitWidth: statusBadgeText.implicitWidth + 16
                                        implicitHeight: statusBadgeText.implicitHeight + 6
                                        radius: Theme.rPill
                                        readonly property color sCol: recordCard.rStatus === "new"
                                                                      ? Theme.accent
                                                                      : (recordCard.rStatus === "downloaded" ? Theme.success : Theme.textDim)
                                        color: Qt.rgba(sCol.r, sCol.g, sCol.b, 0.1)
                                        border.width: 1
                                        border.color: Qt.rgba(sCol.r, sCol.g, sCol.b, 0.3)

                                        RowLayout {
                                            anchors.centerIn: parent
                                            spacing: 4

                                            Rectangle {
                                                visible: recordCard.rStatus === "new"
                                                width: 6; height: 6; radius: 3
                                                color: parent.parent.sCol
                                                layer.enabled: true
                                                layer.effect: MultiEffect {
                                                    blurEnabled: true
                                                    blur: 0.5
                                                    blurMax: 6
                                                }
                                                SequentialAnimation on opacity {
                                                    loops: Animation.Infinite
                                                    NumberAnimation { from: 1.0; to: 0.4; duration: 1000 }
                                                    NumberAnimation { from: 0.4; to: 1.0; duration: 1000 }
                                                }
                                            }

                                            Text {
                                                id: statusBadgeText
                                                text: root.statusLabel(recordCard.rStatus)
                                                color: parent.parent.sCol
                                                font.pixelSize: Theme.fsMicro
                                                font.weight: Font.DemiBold
                                            }
                                        }
                                    }
                                }

                                // 标题
                                Text {
                                    Layout.fillWidth: true
                                    text: modelData.title || ""
                                    color: recordCard.rStatus === "new" ? Theme.textPrimary : Theme.textMute
                                    font.pixelSize: Theme.fsBody
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                }

                                // 元信息行
                                Text {
                                    Layout.fillWidth: true
                                    text: (modelData.author || "") + "  ·  "
                                          + (modelData.source || "") + "  ·  "
                                          + (modelData.time || "")
                                          + (modelData.size ? "  ·  " + modelData.size : "")
                                          + "  ·  " + (modelData.detail || "")
                                    color: Theme.textDim
                                    font.family: Theme.fontMono
                                    font.pixelSize: Theme.fsMicro
                                    font.letterSpacing: 0.3
                                    elide: Text.ElideRight
                                }
                            }

                            // ----- 操作按钮 -----
                            RowLayout {
                                spacing: 4
                                Layout.alignment: Qt.AlignVCenter

                                // Format 按钮（仅 video/url/note/album 类型且未下载时显示）
                                Button {
                                    text: qsTr("Format")
                                    variant: "default"
                                    implicitWidth: 80
                                    implicitHeight: 30
                                    visible: recordCard.rStatus === "new"
                                             && (recordCard.rType === "video"
                                                 || recordCard.rType === "url"
                                                 || recordCard.rType === "note"
                                                 || recordCard.rType === "album")
                                    onClicked: {
                                        if (root.controller && typeof root.controller.openFormatDialog === "function") {
                                            root.controller.openFormatDialog(recordCard.index)
                                        }
                                    }
                                }

                                // 下载按钮（new 状态）/ Open file 按钮（downloaded 状态）
                                Button {
                                    text: recordCard.rStatus === "downloaded" ? "📂" : "⬇"
                                    variant: recordCard.rStatus === "downloaded" ? "default" : "primary"
                                    implicitWidth: 32
                                    implicitHeight: 32
                                    visible: recordCard.rStatus !== "skipped"
                                    onClicked: {
                                        if (root.controller) {
                                            if (recordCard.rStatus === "downloaded" && typeof root.controller.openInboxFile === "function") {
                                                root.controller.openInboxFile(recordCard.index)
                                            } else if (typeof root.controller.downloadInboxItem === "function") {
                                                root.controller.downloadInboxItem(recordCard.index)
                                            }
                                        }
                                    }
                                }

                                // Download anyway 按钮（skipped 状态）
                                Button {
                                    text: "⬇"
                                    variant: "primary"
                                    implicitWidth: 32
                                    implicitHeight: 32
                                    visible: recordCard.rStatus === "skipped"
                                    onClicked: {
                                        if (root.controller && typeof root.controller.downloadInboxItem === "function") {
                                            root.controller.downloadInboxItem(recordCard.index)
                                        }
                                    }
                                }

                                // 删除按钮
                                Button {
                                    text: "🗑"
                                    variant: "danger"
                                    implicitWidth: 32
                                    implicitHeight: 32
                                    onClicked: {
                                        if (root.controller && typeof root.controller.deleteInboxItem === "function") {
                                            root.controller.deleteInboxItem(recordCard.index)
                                        }
                                    }
                                }
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
            visible: root.filteredItems.length === 0

            Item { Layout.fillHeight: true }

            EmptyState {
                Layout.alignment: Qt.AlignHCenter
                icon: "📥"
                title: qsTr("收件箱为空")
                hint: qsTr("通过浏览器扩展或 Telegram Bot 采集的内容会显示在这里")
            }

            Item { Layout.fillHeight: true }
        }

        // ============================================================
        // 格式选择对话框预览（与 HTML 设计稿一致）
        // ============================================================
        GlassCard {
            Layout.fillWidth: true
            padding: 28
            visible: root.filteredItems.length > 0

            ColumnLayout {
                anchors.fill: parent
                spacing: 16

                // 区段标签
                Text {
                    text: qsTr("FORMAT SELECTION PREVIEW · 点击记录右侧 Format 按钮时弹出").toUpperCase()
                    color: Theme.textDim
                    font.family: Theme.fontMono
                    font.pixelSize: 10
                    font.weight: Font.DemiBold
                    font.letterSpacing: 1.5
                    Layout.alignment: Qt.AlignHCenter
                }

                Text {
                    Layout.fillWidth: true
                    Layout.maximumWidth: 360
                    text: qsTr("选择目标格式后点击 Download 即可。图片类型会跳过此弹框直接下载。")
                    color: Theme.textDim
                    font.pixelSize: Theme.fsMicro
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    Layout.alignment: Qt.AlignHCenter
                }

                // 对话框卡片
                Rectangle {
                    Layout.fillWidth: true
                    Layout.maximumWidth: 400
                    Layout.alignment: Qt.AlignHCenter
                    implicitHeight: dialogContent.implicitHeight + 40
                    radius: Theme.rLG
                    color: Qt.rgba(20/255, 20/255, 30/255, 0.85)
                    border.width: 1
                    border.color: Theme.glassBorderHi

                    // 顶部高光线
                    Rectangle {
                        anchors.top: parent.top
                        anchors.left: parent.left
                        anchors.right: parent.right
                        height: 1
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0.0; color: "transparent" }
                            GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, 0.5) }
                            GradientStop { position: 1.0; color: "transparent" }
                        }
                    }

                    ColumnLayout {
                        id: dialogContent
                        anchors.fill: parent
                        anchors.margins: 20
                        spacing: 16

                        // 对话框头部：缩略图 + 标题 + badges
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12

                            Rectangle {
                                Layout.preferredWidth: 48
                                Layout.preferredHeight: 48
                                radius: Theme.rSM
                                gradient: Gradient {
                                    orientation: Gradient.Horizontal
                                    GradientStop { position: 0.0; color: Theme.platformColor("youtube") }
                                    GradientStop { position: 1.0; color: Theme.accent2 }
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6

                                Text {
                                    Layout.fillWidth: true
                                    text: qsTr("Rick Astley — Never Gonna Give You Up")
                                    color: Theme.textPrimary
                                    font.pixelSize: Theme.fsBody
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                    maximumLineCount: 1
                                }

                                RowLayout {
                                    spacing: 6
                                    Badge { badgeType: "youtube"; text: "YouTube" }
                                    Badge { badgeType: "default"; text: qsTr("Video") }
                                }
                            }
                        }

                        // 分隔线
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 1
                            color: Theme.glassBorder
                        }

                        // 格式选项
                        ColumnLayout {
                            id: fmtOptions
                            Layout.fillWidth: true
                            spacing: 6

                            property int activeIndex: 0

                            Repeater {
                                model: [
                                    { name: qsTr("Video · 1080p"), meta: "MP4 · H.264 · 30fps · stereo", size: "18.2 MB", recommended: true },
                                    { name: qsTr("Video · 720p"),  meta: "MP4 · H.264 · 30fps · stereo", size: "8.4 MB",  recommended: false },
                                    { name: qsTr("Video · 480p"),  meta: "MP4 · H.264 · 30fps · stereo", size: "4.2 MB",  recommended: false },
                                    { name: qsTr("Audio · 128kbps"), meta: "MP3 · 44.1kHz · stereo",     size: "2.1 MB",  recommended: false }
                                ]

                                delegate: Rectangle {
                                    id: fmtOpt
                                    required property var modelData
                                    required property int index

                                    Layout.fillWidth: true
                                    implicitHeight: 50
                                    radius: Theme.rMD
                                    readonly property bool isActive: index === fmtOptions.activeIndex
                                    color: isActive ? Qt.rgba(10/255, 132/255, 1, 0.1) : Qt.rgba(0, 0, 0, 0.2)
                                    border.width: 1
                                    border.color: isActive ? Qt.rgba(10/255, 132/255, 1, 0.4) : Theme.glassBorder

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.margins: 12
                                        spacing: 12

                                        // radio
                                        Rectangle {
                                            Layout.preferredWidth: 16
                                            Layout.preferredHeight: 16
                                            radius: 8
                                            color: "transparent"
                                            border.width: 1.5
                                            border.color: fmtOpt.isActive ? Theme.accent : Theme.textDim

                                            Rectangle {
                                                anchors.centerIn: parent
                                                visible: fmtOpt.isActive
                                                width: 8; height: 8; radius: 4
                                                color: Theme.accent
                                                layer.enabled: true
                                                layer.effect: MultiEffect {
                                                    blurEnabled: true
                                                    blur: 0.5
                                                    blurMax: 6
                                                }
                                            }
                                        }

                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 2

                                            RowLayout {
                                                spacing: 6

                                                Text {
                                                    text: fmtOpt.modelData.name
                                                    color: Theme.textPrimary
                                                    font.pixelSize: Theme.fsSmall
                                                    font.weight: Font.DemiBold
                                                }

                                                // Recommended 角标
                                                Rectangle {
                                                    visible: fmtOpt.modelData.recommended
                                                    implicitWidth: recText.implicitWidth + 12
                                                    implicitHeight: recText.implicitHeight + 4
                                                    radius: Theme.rPill
                                                    color: Qt.rgba(48/255, 209/255, 88/255, 0.15)
                                                    border.width: 1
                                                    border.color: Qt.rgba(48/255, 209/255, 88/255, 0.3)

                                                    Text {
                                                        id: recText
                                                        anchors.centerIn: parent
                                                        text: qsTr("RECOMMENDED")
                                                        color: Theme.success
                                                        font.pixelSize: 9
                                                        font.weight: Font.Bold
                                                        font.letterSpacing: 0.5
                                                    }
                                                }
                                            }

                                            Text {
                                                text: fmtOpt.modelData.meta
                                                color: Theme.textDim
                                                font.family: Theme.fontMono
                                                font.pixelSize: 10
                                                font.letterSpacing: 0.3
                                            }
                                        }

                                        Text {
                                            text: fmtOpt.modelData.size
                                            color: Theme.textMute
                                            font.family: Theme.fontMono
                                            font.pixelSize: 11
                                            font.weight: Font.DemiBold
                                        }
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: fmtOptions.activeIndex = fmtOpt.index
                                    }
                                }
                            }
                        }

                        // 分隔线
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 1
                            color: Theme.glassBorder
                        }

                        // 底部操作
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Item { Layout.fillWidth: true }

                            Button {
                                text: qsTr("Cancel")
                                variant: "default"
                            }
                            Button {
                                text: qsTr("Download")
                                variant: "primary"
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

                // 左侧：3 个状态指示
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
                    RowLayout {
                        spacing: 6
                        Rectangle {
                            width: 7; height: 7; radius: 3.5
                            color: Theme.platformColor("telegram")
                            layer.enabled: true
                            layer.effect: MultiEffect {
                                blurEnabled: true
                                blur: 0.5
                                blurMax: 6
                            }
                        }
                        Text {
                            text: qsTr("Telegram Polling")
                            color: Theme.textMute
                            font.pixelSize: Theme.fsMicro
                            font.family: Theme.fontMono
                        }
                    }
                    RowLayout {
                        spacing: 6
                        Rectangle { width: 7; height: 7; radius: 3.5; color: Theme.success }
                        Text {
                            text: qsTr("Browser Linked")
                            color: Theme.textMute
                            font.pixelSize: Theme.fsMicro
                            font.family: Theme.fontMono
                        }
                    }
                }

                Item { Layout.fillWidth: true }

                // 右侧：统计
                Text {
                    text: root.newCount + " " + qsTr("new")
                    color: Theme.textMute
                    font.pixelSize: Theme.fsMicro
                    font.family: Theme.fontMono
                }
                Text {
                    text: root.totalCount + " " + qsTr("total")
                    color: Theme.textMute
                    font.pixelSize: Theme.fsMicro
                    font.family: Theme.fontMono
                }
                Text {
                    text: "18.6 MB"
                    color: Theme.textMute
                    font.pixelSize: Theme.fsMicro
                    font.family: Theme.fontMono
                }
            }
        }
    }
}
