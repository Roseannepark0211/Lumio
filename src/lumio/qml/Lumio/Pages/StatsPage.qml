// ============================================================
// LUMIO // StatsPage — 统计页面
// ------------------------------------------------------------
// 还原 design_preview/stats.html：
//   - 页面头部：渐变标题 + 时间段 segmented + 刷新/导出
//   - KPI 网格：4 张大卡（总下载/总体积/成功率/今日）
//   - 中段 3 图：存储分布 donut / 下载趋势 line / 平台分布 bars
//   - 平台分解：8 张平台卡
//   - 最近活动：活动时间线列表
//   - 空状态：EmptyState
// 外部调用：
//   StatsPage { controller: myController }
// 数据：controller.stats() -> { totalDownloads, totalSize, successRate,
//   todayDownloads, activeNow, storage, trends, platforms, activities }
// ============================================================

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Lumio
import Lumio.Components

Item {
    id: root

    implicitHeight: 900

    property var controller: null
    property var stats: controller && typeof controller.stats === "function"
                       ? controller.stats()
                       : ({
                           totalDownloads: 1284,
                           totalSize: "18.6 GB",
                           successRate: 94.2,
                           todayDownloads: 12,
                           activeNow: 3,
                           storage: [
                               { name: qsTr("Video"),   pct: 58, color: Theme.accent },
                               { name: qsTr("Image"),   pct: 24, color: Theme.warning },
                               { name: qsTr("Audio"),   pct: 12, color: Theme.success },
                               { name: qsTr("Mixed"),   pct: 6,  color: Theme.accent2 }
                           ],
                           platforms: [
                               { name: "YouTube",     key: "youtube",     count: 384, share: 29.9, pct: 100 },
                               { name: "Instagram",   key: "instagram",   count: 256, share: 19.9, pct: 67 },
                               { name: "X",           key: "x",           count: 168, share: 13.1, pct: 44 },
                               { name: qsTr("B站"),   key: "bilibili",    count: 142, share: 11.1, pct: 37 },
                               { name: qsTr("抖音"),  key: "douyin",      count: 124, share: 9.7,  pct: 32 },
                               { name: qsTr("小红书"),key: "xiaohongshu", count: 86,  share: 6.7,  pct: 22 },
                               { name: qsTr("微博"),  key: "weibo",       count: 72,  share: 5.6,  pct: 19 },
                               { name: qsTr("快手"),  key: "kuaishou",    count: 52,  share: 4.0,  pct: 14 }
                           ],
                           activities: [
                               { time: "14:32:18", platform: "youtube",   mediaType: "video", name: "Rick Astley — Never Gonna Give You Up", status: "completed", size: "8.4 MB" },
                               { time: "14:28:05", platform: "instagram", mediaType: "image", name: "Summer sunset over Tokyo",             status: "completed", size: "2.1 MB" },
                               { time: "14:15:42", platform: "x",         mediaType: "video", name: "Late night design thoughts",            status: "failed",    size: qsTr("Cookie expired") },
                               { time: "14:02:18", platform: "bilibili",  mediaType: "video", name: qsTr("赛博朋克城市夜景航拍"),            status: "completed", size: "248 MB" },
                               { time: "13:48:30", platform: "douyin",    mediaType: "video", name: qsTr("设计师的 5 分钟早晨仪式"),         status: "completed", size: "12.4 MB" }
                           ]
                       })

    property string timeRange: "30d"  // today / 7d / 30d / all

    ColumnLayout {
        anchors.fill: parent
        spacing: 16

        // ============================================================
        // 页面头部
        // ============================================================
        RowLayout {
            Layout.fillWidth: true
            spacing: 18

            // 渐变标题 "Statistics"
            Canvas {
                id: titleCanvas
                Layout.preferredWidth: 180
                Layout.preferredHeight: 32
                renderStrategy: Canvas.Cooperative

                onPaint: {
                    var ctx = getContext("2d")
                    ctx.reset()
                    var text = qsTr("Statistics")
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

            // 时间段 segmented
            Rectangle {
                Layout.alignment: Qt.AlignVCenter
                implicitWidth: segRow.implicitWidth + 8
                implicitHeight: 32
                radius: Theme.rMD
                color: Theme.glassBg
                border.width: 1
                border.color: Theme.glassBorder

                Row {
                    id: segRow
                    anchors.centerIn: parent
                    spacing: 2

                    Repeater {
                        model: [
                            { key: "today", label: qsTr("Today") },
                            { key: "7d",    label: qsTr("7 Days") },
                            { key: "30d",   label: qsTr("30 Days") },
                            { key: "all",   label: qsTr("All Time") }
                        ]

                        delegate: Rectangle {
                            width: segLabel.implicitWidth + 20
                            height: 26
                            radius: Theme.rSM
                            color: root.timeRange === modelData.key ? Theme.accent : "transparent"
                            anchors.verticalCenter: parent.verticalCenter

                            Text {
                                id: segLabel
                                anchors.centerIn: parent
                                text: modelData.label
                                color: root.timeRange === modelData.key ? "white" : Theme.textMute
                                font.pixelSize: Theme.fsSmall
                                font.weight: Font.DemiBold
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.timeRange = modelData.key
                            }
                        }
                    }
                }
            }

            Item { Layout.fillWidth: true }

            Button {
                text: qsTr("Refresh")
                variant: "default"
            }
            Button {
                text: qsTr("Export")
                variant: "default"
            }
        }

        // ============================================================
        // KPI 网格（4 张大卡）
        // ============================================================
        GridLayout {
            Layout.fillWidth: true
            columns: 4
            columnSpacing: 12
            rowSpacing: 12

            // KPI 1: Total Downloads
            GlassCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 130
                padding: 18

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 8

                    RowLayout {
                        spacing: 10

                        Rectangle {
                            Layout.preferredWidth: 36
                            Layout.preferredHeight: 36
                            radius: Theme.rMD
                            color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.15)
                            border.width: 1
                            border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.25)

                            Text {
                                anchors.centerIn: parent
                                text: "↓"
                                color: Theme.accent
                                font.pixelSize: 16
                                font.weight: Font.Bold
                            }
                        }

                        Text {
                            text: qsTr("Total Downloads")
                            color: Theme.textMute
                            font.pixelSize: Theme.fsSmall
                            font.weight: Font.DemiBold
                            Layout.fillWidth: true
                        }
                    }

                    Text {
                        text: root.stats.totalDownloads
                        color: Theme.textPrimary
                        font.family: Theme.fontMono
                        font.pixelSize: 28
                        font.weight: Font.Bold
                        Layout.fillWidth: true
                    }

                    Row {
                        spacing: 4
                        Text {
                            text: "↗"
                            color: Theme.success
                            font.pixelSize: Theme.fsMicro
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            text: qsTr("+12.4% vs last month")
                            color: Theme.success
                            font.pixelSize: Theme.fsMicro
                            font.family: Theme.fontMono
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
            }

            // KPI 2: Total Size
            GlassCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 130
                padding: 18

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 8

                    RowLayout {
                        spacing: 10

                        Rectangle {
                            Layout.preferredWidth: 36
                            Layout.preferredHeight: 36
                            radius: Theme.rMD
                            color: Qt.rgba(Theme.accent2.r, Theme.accent2.g, Theme.accent2.b, 0.15)
                            border.width: 1
                            border.color: Qt.rgba(Theme.accent2.r, Theme.accent2.g, Theme.accent2.b, 0.25)

                            Text {
                                anchors.centerIn: parent
                                text: "📁"
                                font.pixelSize: 14
                            }
                        }

                        Text {
                            text: qsTr("Total Size")
                            color: Theme.textMute
                            font.pixelSize: Theme.fsSmall
                            font.weight: Font.DemiBold
                            Layout.fillWidth: true
                        }
                    }

                    Text {
                        text: root.stats.totalSize
                        color: Theme.textPrimary
                        font.family: Theme.fontMono
                        font.pixelSize: 28
                        font.weight: Font.Bold
                        Layout.fillWidth: true
                    }

                    Row {
                        spacing: 4
                        Text {
                            text: "↗"
                            color: Theme.success
                            font.pixelSize: Theme.fsMicro
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            text: qsTr("+2.1 GB")
                            color: Theme.success
                            font.pixelSize: Theme.fsMicro
                            font.family: Theme.fontMono
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
            }

            // KPI 3: Success Rate
            GlassCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 130
                padding: 18

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 8

                    RowLayout {
                        spacing: 10

                        Rectangle {
                            Layout.preferredWidth: 36
                            Layout.preferredHeight: 36
                            radius: Theme.rMD
                            color: Qt.rgba(Theme.success.r, Theme.success.g, Theme.success.b, 0.15)
                            border.width: 1
                            border.color: Qt.rgba(Theme.success.r, Theme.success.g, Theme.success.b, 0.25)

                            Text {
                                anchors.centerIn: parent
                                text: "✓"
                                color: Theme.success
                                font.pixelSize: 16
                                font.weight: Font.Bold
                            }
                        }

                        Text {
                            text: qsTr("Success Rate")
                            color: Theme.textMute
                            font.pixelSize: Theme.fsSmall
                            font.weight: Font.DemiBold
                            Layout.fillWidth: true
                        }
                    }

                    Text {
                        text: root.stats.successRate + "%"
                        color: Theme.textPrimary
                        font.family: Theme.fontMono
                        font.pixelSize: 28
                        font.weight: Font.Bold
                        Layout.fillWidth: true
                    }

                    Row {
                        spacing: 4
                        Text {
                            text: "↗"
                            color: Theme.success
                            font.pixelSize: Theme.fsMicro
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            text: qsTr("+1.8%")
                            color: Theme.success
                            font.pixelSize: Theme.fsMicro
                            font.family: Theme.fontMono
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
            }

            // KPI 4: Today's Downloads
            GlassCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 130
                padding: 18

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 8

                    RowLayout {
                        spacing: 10

                        Rectangle {
                            Layout.preferredWidth: 36
                            Layout.preferredHeight: 36
                            radius: Theme.rMD
                            color: Qt.rgba(Theme.warning.r, Theme.warning.g, Theme.warning.b, 0.15)
                            border.width: 1
                            border.color: Qt.rgba(Theme.warning.r, Theme.warning.g, Theme.warning.b, 0.25)

                            Text {
                                anchors.centerIn: parent
                                text: "⏰"
                                font.pixelSize: 14
                            }
                        }

                        Text {
                            text: qsTr("Today's Downloads")
                            color: Theme.textMute
                            font.pixelSize: Theme.fsSmall
                            font.weight: Font.DemiBold
                            Layout.fillWidth: true
                        }
                    }

                    Text {
                        text: root.stats.todayDownloads
                        color: Theme.textPrimary
                        font.family: Theme.fontMono
                        font.pixelSize: 28
                        font.weight: Font.Bold
                        Layout.fillWidth: true
                    }

                    Row {
                        spacing: 6
                        Rectangle {
                            width: 6; height: 6
                            radius: 3
                            color: Theme.info
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            text: root.stats.activeNow + " " + qsTr("active now")
                            color: Theme.info
                            font.pixelSize: Theme.fsMicro
                            font.family: Theme.fontMono
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
            }
        }

        // ============================================================
        // 中段 3 图（donut / line / bars）
        // ============================================================
        GridLayout {
            Layout.fillWidth: true
            columns: 3
            columnSpacing: 12
            rowSpacing: 12

            // MID 1: Storage Distribution donut
            GlassCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 240
                padding: 18

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 12

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: qsTr("Storage Distribution")
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fsH2
                            font.weight: Font.Bold
                        }
                        Text {
                            text: qsTr("by media type")
                            color: Theme.textDim
                            font.pixelSize: Theme.fsMicro
                            font.family: Theme.fontMono
                            Layout.fillWidth: true
                            horizontalAlignment: Text.AlignRight
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 16

                        // Donut
                        Canvas {
                            id: donutCanvas
                            Layout.preferredWidth: 130
                            Layout.preferredHeight: 130
                            Layout.alignment: Qt.AlignVCenter

                            onPaint: {
                                var ctx = getContext("2d")
                                ctx.reset()
                                var cx = width / 2
                                var cy = height / 2
                                var r = Math.min(width, height) / 2 - 6
                                var start = -Math.PI / 2
                                var items = root.stats.storage

                                for (var i = 0; i < items.length; i++) {
                                    var angle = (items[i].pct / 100) * Math.PI * 2
                                    ctx.beginPath()
                                    ctx.arc(cx, cy, r, start, start + angle)
                                    ctx.lineWidth = 18
                                    ctx.strokeStyle = items[i].color
                                    ctx.stroke()
                                    start += angle
                                }
                            }

                            Component.onCompleted: requestPaint()
                        }

                        // Legend
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Repeater {
                                model: root.stats.storage

                                delegate: RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8

                                    Rectangle {
                                        Layout.preferredWidth: 10
                                        Layout.preferredHeight: 10
                                        radius: 5
                                        color: modelData.color
                                    }

                                    Text {
                                        text: modelData.name
                                        color: Theme.textMute
                                        font.pixelSize: Theme.fsSmall
                                        Layout.fillWidth: true
                                    }

                                    Text {
                                        text: modelData.pct + "%"
                                        color: Theme.textPrimary
                                        font.pixelSize: Theme.fsSmall
                                        font.family: Theme.fontMono
                                        font.weight: Font.DemiBold
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // MID 2: Download Trends line chart
            GlassCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 240
                padding: 18

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 12

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: qsTr("Download Trends")
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fsH2
                            font.weight: Font.Bold
                        }
                        Text {
                            text: qsTr("last 7 days")
                            color: Theme.textDim
                            font.pixelSize: Theme.fsMicro
                            font.family: Theme.fontMono
                            Layout.fillWidth: true
                            horizontalAlignment: Text.AlignRight
                        }
                    }

                    Canvas {
                        id: lineChart
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        onPaint: {
                            var ctx = getContext("2d")
                            ctx.reset()
                            var w = width
                            var h = height
                            // grid lines
                            ctx.strokeStyle = Qt.rgba(1, 1, 1, 0.05)
                            ctx.lineWidth = 1
                            for (var g = 1; g < 4; g++) {
                                ctx.beginPath()
                                ctx.moveTo(8, h * g / 4)
                                ctx.lineTo(w - 8, h * g / 4)
                                ctx.stroke()
                            }

                            // data points
                            var pts = [
                                { x: 0.05, y: 0.65 },
                                { x: 0.20, y: 0.40 },
                                { x: 0.35, y: 0.55 },
                                { x: 0.50, y: 0.25 },
                                { x: 0.65, y: 0.10 },
                                { x: 0.80, y: 0.35 },
                                { x: 0.95, y: 0.50 }
                            ]

                            // fill area
                            var grad = ctx.createLinearGradient(0, 0, 0, h)
                            grad.addColorStop(0, Qt.rgba(10/255, 132/255, 1, 0.55))
                            grad.addColorStop(1, Qt.rgba(10/255, 132/255, 1, 0))
                            ctx.beginPath()
                            ctx.moveTo(pts[0].x * w, pts[0].y * h)
                            for (var i = 1; i < pts.length; i++) {
                                ctx.lineTo(pts[i].x * w, pts[i].y * h)
                            }
                            ctx.lineTo(pts[pts.length - 1].x * w, h - 4)
                            ctx.lineTo(pts[0].x * w, h - 4)
                            ctx.closePath()
                            ctx.fillStyle = grad
                            ctx.fill()

                            // line
                            var lineGrad = ctx.createLinearGradient(0, 0, w, 0)
                            lineGrad.addColorStop(0, "#5e5ce6")
                            lineGrad.addColorStop(1, "#4cc2ff")
                            ctx.beginPath()
                            ctx.moveTo(pts[0].x * w, pts[0].y * h)
                            for (var j = 1; j < pts.length; j++) {
                                ctx.lineTo(pts[j].x * w, pts[j].y * h)
                            }
                            ctx.strokeStyle = lineGrad
                            ctx.lineWidth = 2.2
                            ctx.lineCap = "round"
                            ctx.lineJoin = "round"
                            ctx.stroke()

                            // dots
                            for (var k = 0; k < pts.length; k++) {
                                ctx.beginPath()
                                ctx.arc(pts[k].x * w, pts[k].y * h, 3, 0, Math.PI * 2)
                                ctx.fillStyle = "#0a84ff"
                                ctx.strokeStyle = "#07070d"
                                ctx.lineWidth = 1.5
                                ctx.fill()
                                ctx.stroke()
                            }
                        }

                        Component.onCompleted: requestPaint()
                        onWidthChanged: requestPaint()
                        onHeightChanged: requestPaint()
                    }

                    // X labels
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        Repeater {
                            model: [qsTr("Mon"), qsTr("Tue"), qsTr("Wed"), qsTr("Thu"), qsTr("Fri"), qsTr("Sat"), qsTr("Sun")]
                            delegate: Text {
                                Layout.fillWidth: true
                                text: modelData
                                color: Theme.textDim
                                font.pixelSize: 10
                                font.family: Theme.fontMono
                                horizontalAlignment: Text.AlignHCenter
                            }
                        }
                    }
                }
            }

            // MID 3: Platform Distribution bars
            GlassCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 240
                padding: 18

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 12

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: qsTr("Platform Distribution")
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fsH2
                            font.weight: Font.Bold
                        }
                        Text {
                            text: qsTr("share of total")
                            color: Theme.textDim
                            font.pixelSize: Theme.fsMicro
                            font.family: Theme.fontMono
                            Layout.fillWidth: true
                            horizontalAlignment: Text.AlignRight
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 6

                        Repeater {
                            model: root.stats.platforms

                            delegate: RowLayout {
                                Layout.fillWidth: true
                                spacing: 8

                                Text {
                                    text: modelData.name
                                    color: Theme.platformColor(modelData.key)
                                    font.pixelSize: Theme.fsMicro
                                    font.weight: Font.DemiBold
                                    Layout.preferredWidth: 60
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 8
                                    radius: 4
                                    color: Qt.rgba(0, 0, 0, 0.3)

                                    Rectangle {
                                        width: parent.width * (modelData.pct / 100)
                                        height: parent.height
                                        radius: parent.radius
                                        color: Theme.platformColor(modelData.key)
                                        opacity: 0.85
                                    }
                                }

                                Text {
                                    text: modelData.count
                                    color: Theme.textMute
                                    font.pixelSize: Theme.fsMicro
                                    font.family: Theme.fontMono
                                    Layout.preferredWidth: 32
                                    horizontalAlignment: Text.AlignRight
                                }
                            }
                        }
                    }
                }
            }
        }

        // ============================================================
        // 平台分解（8 张平台卡）
        // ============================================================
        Text {
            text: qsTr("Platform Breakdown")
            color: Theme.textPrimary
            font.pixelSize: Theme.fsH2
            font.weight: Font.Bold
        }

        GridLayout {
            Layout.fillWidth: true
            columns: 4
            columnSpacing: 12
            rowSpacing: 12

            Repeater {
                model: root.stats.platforms

                delegate: GlassCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 130
                    padding: 16

                    readonly property color platColor: Theme.platformColor(modelData.key)

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 6

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Rectangle {
                                Layout.preferredWidth: 28
                                Layout.preferredHeight: 28
                                radius: Theme.rSM
                                color: Qt.rgba(parent.parent.parent.platColor.r,
                                               parent.parent.parent.platColor.g,
                                               parent.parent.parent.platColor.b, 0.15)
                                border.width: 1
                                border.color: Qt.rgba(parent.parent.parent.platColor.r,
                                                       parent.parent.parent.platColor.g,
                                                       parent.parent.parent.platColor.b, 0.3)

                                Text {
                                    anchors.centerIn: parent
                                    text: "•"
                                    color: parent.parent.parent.platColor
                                    font.pixelSize: 18
                                    font.weight: Font.Bold
                                }
                            }

                            Text {
                                text: modelData.name
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fsBody
                                font.weight: Font.DemiBold
                                Layout.fillWidth: true
                            }
                        }

                        Text {
                            text: modelData.count
                            color: Theme.textPrimary
                            font.family: Theme.fontMono
                            font.pixelSize: 24
                            font.weight: Font.Bold
                            Layout.fillWidth: true
                        }

                        Text {
                            text: modelData.share + "% " + qsTr("of total")
                            color: Theme.textMute
                            font.pixelSize: Theme.fsMicro
                            font.family: Theme.fontMono
                            Layout.fillWidth: true
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 4
                            radius: 2
                            color: Qt.rgba(0, 0, 0, 0.3)

                            Rectangle {
                                width: parent.width * (modelData.pct / 100)
                                height: parent.height
                                radius: parent.radius
                                color: parent.parent.parent.parent.platColor
                                opacity: 0.85
                            }
                        }
                    }
                }
            }
        }

        // ============================================================
        // 最近活动时间线
        // ============================================================
        Text {
            text: qsTr("Recent Activity")
            color: Theme.textPrimary
            font.pixelSize: Theme.fsH2
            font.weight: Font.Bold
        }

        GlassCard {
            Layout.fillWidth: true
            padding: 8

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                Repeater {
                    model: root.stats.activities

                    delegate: Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 44
                        color: "transparent"

                        readonly property color platColor: Theme.platformColor(modelData.platform)
                        readonly property bool isFailed: modelData.status === "failed"

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            spacing: 12

                            Text {
                                text: modelData.time
                                color: Theme.textDim
                                font.family: Theme.fontMono
                                font.pixelSize: Theme.fsMicro
                                Layout.preferredWidth: 70
                            }

                            Badge {
                                badgeType: modelData.platform
                                text: modelData.platform
                            }

                            Badge {
                                badgeType: "default"
                                text: modelData.mediaType
                            }

                            Text {
                                text: modelData.name
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fsSmall
                                font.weight: Font.DemiBold
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                            }

                            Badge {
                                badgeType: isFailed ? "danger" : "success"
                                text: isFailed ? qsTr("Failed") : qsTr("Completed")
                            }

                            Text {
                                text: modelData.size
                                color: isFailed ? Theme.danger : Theme.textMute
                                font.family: Theme.fontMono
                                font.pixelSize: Theme.fsMicro
                                Layout.preferredWidth: 80
                                horizontalAlignment: Text.AlignRight
                            }
                        }
                    }
                }
            }
        }
    }
}
