// ============================================================
// LUMIO // HistoryPage — 历史记录页面
// ------------------------------------------------------------
// 还原 design_preview/history.html：
//   - 页面头部：渐变标题 + 记录数 badge + 操作按钮
//   - 筛选行：搜索 + 平台/状态/排序下拉
//   - 统计卡：总数 / 完成 / 失败 / 体积
//   - 历史列表：GlassCard 记录卡片（缩略图 + 标题 + badge + 元信息 + 操作）
//   - 空状态：EmptyState
// 外部调用：
//   HistoryPage { controller: myController }
// 数据：controller.historyItems() -> [{ title, author, platform, mediaType,
//   status, size, time, thumbColor1, thumbColor2 }]
// ============================================================

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Lumio
import Lumio.Components

Item {
    id: root

    implicitHeight: 500

    property var controller: null
    property var historyItems: controller && typeof controller.historyItems === "function"
                                ? controller.historyItems()
                                : []

    // 筛选状态
    property string searchQuery: ""
    property string platformFilter: "all"
    property string statusFilter: "all"
    property string sortKey: "newest"

    // 统计
    readonly property int totalCount: historyItems.length
    readonly property int completedCount: {
        var n = 0
        for (var i = 0; i < historyItems.length; i++) {
            if (historyItems[i].status === "completed") n++
        }
        return n
    }
    readonly property int failedCount: {
        var n = 0
        for (var i = 0; i < historyItems.length; i++) {
            if (historyItems[i].status === "failed") n++
        }
        return n
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 16

        // ============================================================
        // 页面头部：标题 + 记录数 badge + 操作按钮
        // ============================================================
        RowLayout {
            Layout.fillWidth: true
            spacing: 14

            // 渐变标题 "历史记录"
            Canvas {
                id: titleCanvas
                Layout.preferredWidth: 180
                Layout.preferredHeight: 32
                renderStrategy: Canvas.Cooperative

                onPaint: {
                    var ctx = getContext("2d")
                    ctx.reset()
                    var text = qsTr("历史记录")
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

            // 记录数 badge
            Badge {
                badgeType: "default"
                text: totalCount + " " + qsTr("records")
            }

            Item { Layout.fillWidth: true }

            // 操作按钮
            Button {
                text: qsTr("导出")
                variant: "default"
            }
            Button {
                text: qsTr("清空全部")
                variant: "danger"
            }
        }

        // ============================================================
        // 筛选行：搜索 + 平台 + 状态 + 排序
        // ============================================================
        GlassCard {
            Layout.fillWidth: true
            padding: 14

            RowLayout {
                anchors.fill: parent
                spacing: 10

                Input {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    placeholderText: qsTr("搜索标题、作者、URL、文件路径...")
                    text: root.searchQuery
                    onTextEdited: root.searchQuery = text
                }

                ComboBox {
                    id: platformCombo
                    Layout.preferredWidth: 140
                    model: [
                        qsTr("全部平台"),
                        qsTr("YouTube"), qsTr("Instagram"), qsTr("X"),
                        qsTr("B站"), qsTr("抖音"), qsTr("快手"),
                        qsTr("微博"), qsTr("小红书")
                    ]
                    onActivated: root.platformFilter = (index === 0) ? "all" : model[index]

                    background: Rectangle {
                        color: Theme.inputBg
                        border.width: 1
                        border.color: platformCombo.activeFocus ? Theme.accent : Theme.glassBorder
                        radius: Theme.rMD
                    }
                    contentItem: Text {
                        text: platformCombo.displayText
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fsBody
                        verticalAlignment: Text.AlignVCenter
                        leftPadding: 10
                    }
                }

                ComboBox {
                    id: statusCombo
                    Layout.preferredWidth: 120
                    model: [qsTr("全部状态"), qsTr("已完成"), qsTr("失败"), qsTr("已取消")]
                    onActivated: root.statusFilter = (index === 0) ? "all" : ["all","completed","failed","cancelled"][index]

                    background: Rectangle {
                        color: Theme.inputBg
                        border.width: 1
                        border.color: statusCombo.activeFocus ? Theme.accent : Theme.glassBorder
                        radius: Theme.rMD
                    }
                    contentItem: Text {
                        text: statusCombo.displayText
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fsBody
                        verticalAlignment: Text.AlignVCenter
                        leftPadding: 10
                    }
                }

                ComboBox {
                    id: sortCombo
                    Layout.preferredWidth: 140
                    model: [qsTr("最新优先"), qsTr("最旧优先"), qsTr("体积最大"), qsTr("体积最小")]
                    onActivated: root.sortKey = ["newest","oldest","largest","smallest"][index]

                    background: Rectangle {
                        color: Theme.inputBg
                        border.width: 1
                        border.color: sortCombo.activeFocus ? Theme.accent : Theme.glassBorder
                        radius: Theme.rMD
                    }
                    contentItem: Text {
                        text: sortCombo.displayText
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fsBody
                        verticalAlignment: Text.AlignVCenter
                        leftPadding: 10
                    }
                }
            }
        }

        // ============================================================
        // 统计卡（4 张）
        // ============================================================
        GridLayout {
            Layout.fillWidth: true
            columns: 4
            columnSpacing: 12
            rowSpacing: 12

            // 总记录数
            GlassCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 70
                padding: 14

                RowLayout {
                    anchors.fill: parent
                    spacing: 12

                    Rectangle {
                        Layout.preferredWidth: 38
                        Layout.preferredHeight: 38
                        radius: Theme.rMD
                        color: Qt.rgba(168/255, 199/255, 1, 0.08)
                        border.width: 1
                        border.color: Qt.rgba(168/255, 199/255, 1, 0.25)

                        Text {
                            anchors.centerIn: parent
                            text: "📋"
                            font.pixelSize: 16
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0

                        Text {
                            text: root.totalCount
                            color: Theme.textPrimary
                            font.family: Theme.fontMono
                            font.pixelSize: 20
                            font.weight: Font.Bold
                        }
                        Text {
                            text: qsTr("总记录数")
                            color: Theme.textDim
                            font.family: Theme.fontMono
                            font.pixelSize: Theme.fsMicro
                            font.letterSpacing: 1
                        }
                    }
                }
            }

            // 已完成
            GlassCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 70
                padding: 14

                RowLayout {
                    anchors.fill: parent
                    spacing: 12

                    Rectangle {
                        Layout.preferredWidth: 38
                        Layout.preferredHeight: 38
                        radius: Theme.rMD
                        color: Qt.rgba(48/255, 209/255, 88/255, 0.1)
                        border.width: 1
                        border.color: Qt.rgba(48/255, 209/255, 88/255, 0.3)

                        Text {
                            anchors.centerIn: parent
                            text: "✓"
                            color: Theme.success
                            font.pixelSize: 18
                            font.weight: Font.Bold
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0

                        Text {
                            text: root.completedCount
                            color: Theme.textPrimary
                            font.family: Theme.fontMono
                            font.pixelSize: 20
                            font.weight: Font.Bold
                        }
                        Text {
                            text: qsTr("已完成")
                            color: Theme.textDim
                            font.family: Theme.fontMono
                            font.pixelSize: Theme.fsMicro
                            font.letterSpacing: 1
                        }
                    }
                }
            }

            // 失败
            GlassCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 70
                padding: 14

                RowLayout {
                    anchors.fill: parent
                    spacing: 12

                    Rectangle {
                        Layout.preferredWidth: 38
                        Layout.preferredHeight: 38
                        radius: Theme.rMD
                        color: Qt.rgba(255/255, 69/255, 58/255, 0.1)
                        border.width: 1
                        border.color: Qt.rgba(255/255, 69/255, 58/255, 0.3)

                        Text {
                            anchors.centerIn: parent
                            text: "✕"
                            color: Theme.danger
                            font.pixelSize: 16
                            font.weight: Font.Bold
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0

                        Text {
                            text: root.failedCount
                            color: Theme.textPrimary
                            font.family: Theme.fontMono
                            font.pixelSize: 20
                            font.weight: Font.Bold
                        }
                        Text {
                            text: qsTr("失败")
                            color: Theme.textDim
                            font.family: Theme.fontMono
                            font.pixelSize: Theme.fsMicro
                            font.letterSpacing: 1
                        }
                    }
                }
            }

            // 总体积
            GlassCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 70
                padding: 14

                RowLayout {
                    anchors.fill: parent
                    spacing: 12

                    Rectangle {
                        Layout.preferredWidth: 38
                        Layout.preferredHeight: 38
                        radius: Theme.rMD
                        color: Qt.rgba(10/255, 132/255, 1, 0.1)
                        border.width: 1
                        border.color: Qt.rgba(10/255, 132/255, 1, 0.3)

                        Text {
                            anchors.centerIn: parent
                            text: "📁"
                            font.pixelSize: 16
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0

                        Text {
                            text: "18.6 GB"
                            color: Theme.textPrimary
                            font.family: Theme.fontMono
                            font.pixelSize: 20
                            font.weight: Font.Bold
                        }
                        Text {
                            text: qsTr("总体积")
                            color: Theme.textDim
                            font.family: Theme.fontMono
                            font.pixelSize: Theme.fsMicro
                            font.letterSpacing: 1
                        }
                    }
                }
            }
        }

        // ============================================================
        // 历史记录列表 / 空状态
        // ============================================================
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.historyItems.length > 0

            ColumnLayout {
                anchors.fill: parent
                spacing: 8

                Repeater {
                    model: root.historyItems

                    delegate: GlassCard {
                        id: recordCard
                        required property var modelData
                        required property int index

                        Layout.fillWidth: true
                        Layout.preferredHeight: 76
                        padding: 12

                        readonly property string platform: modelData.platform || ""
                        readonly property string mediaType: modelData.mediaType || "video"
                        readonly property string status: modelData.status || "completed"
                        readonly property color platColor: Theme.platformColor(platform)

                        RowLayout {
                            anchors.fill: parent
                            spacing: 12

                            // 平台渐变缩略图
                            Rectangle {
                                Layout.preferredWidth: 44
                                Layout.preferredHeight: 44
                                radius: Theme.rSM
                                gradient: Gradient {
                                    orientation: Gradient.Horizontal
                                    GradientStop { position: 0.0; color: recordCard.platColor }
                                    GradientStop { position: 1.0; color: Theme.accent2 }
                                }

                                Text {
                                    anchors.centerIn: parent
                                    text: recordCard.mediaType === "audio" ? "🎵"
                                          : (recordCard.mediaType === "image" ? "🖼" : "🎬")
                                    font.pixelSize: 18
                                }
                            }

                            // 信息块
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 4

                                RowLayout {
                                    spacing: 6

                                    Badge {
                                        badgeType: recordCard.platform
                                        text: recordCard.platform
                                    }
                                    Badge {
                                        badgeType: recordCard.status === "completed" ? "success"
                                                   : (recordCard.status === "failed" ? "danger" : "default")
                                        text: recordCard.status === "completed" ? qsTr("已完成")
                                              : (recordCard.status === "failed" ? qsTr("失败") : qsTr("已取消"))
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        text: modelData.title || ""
                                        color: Theme.textPrimary
                                        font.pixelSize: Theme.fsBody
                                        font.weight: Font.DemiBold
                                        elide: Text.ElideRight
                                    }
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: (modelData.author || "") + "  ·  "
                                          + (modelData.size || "0 MB") + "  ·  "
                                          + (modelData.time || "")
                                    color: Theme.textMute
                                    font.family: Theme.fontMono
                                    font.pixelSize: Theme.fsMicro
                                    elide: Text.ElideRight
                                }
                            }

                            // 操作按钮
                            Row {
                                spacing: 4

                                Button {
                                    text: "📂"
                                    variant: "default"
                                    implicitWidth: 32
                                    implicitHeight: 32
                                }
                                Button {
                                    text: "🗑"
                                    variant: "danger"
                                    implicitWidth: 32
                                    implicitHeight: 32
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
            visible: root.historyItems.length === 0

            Item { Layout.fillHeight: true }

            EmptyState {
                Layout.alignment: Qt.AlignHCenter
                icon: "📋"
                title: qsTr("暂无历史记录")
                hint: qsTr("下载的文件会显示在这里")
            }

            Item { Layout.fillHeight: true }
        }
    }
}
