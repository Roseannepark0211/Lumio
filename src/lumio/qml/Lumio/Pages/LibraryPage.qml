// ============================================================
// LUMIO // LibraryPage — 素材库页面
// ------------------------------------------------------------
// 还原 design_preview/library.html：
//   - 页面头部：渐变标题 + lib-badge + 批量操作 + 视图切换
//   - Collections 侧栏：All/Favorites/自定义集合列表
//   - 筛选工具条：搜索 + 平台 + 类型 + 收藏 + 日期范围 + 批次 + 重置
//   - 批量工具条：选中数 + 全选 + 批量操作
//   - 媒体卡片网格：缩略图 + 平台/类型 badge + 收藏 + 元信息 + 操作
//   - 分页：上一页/页码/下一页 + 显示范围
//   - 空状态：EmptyState
// 外部调用：
//   LibraryPage { controller: myController }
// 数据：controller.libraryItems() -> [{ title, author, platform, mediaType,
//   size, date, favorited, thumbC1, thumbC2 }]
//   controller.collections() -> [{ name, count, icon, active, favorite }]
// ============================================================

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Lumio
import Lumio.Components

Item {
    id: root

    implicitHeight: 720

    property var controller: null
    property var libraryItems: controller && typeof controller.libraryItems === "function"
                                ? controller.libraryItems()
                                : []
    property var collections: controller && typeof controller.collections === "function"
                              ? controller.collections()
                              : [
                                  { name: qsTr("All Items"), count: 248, icon: "📦", active: true },
                                  { name: qsTr("Favorites"), count: 32, icon: "❤", favorite: true },
                                  { name: qsTr("Travel"), count: 18, icon: "📁" },
                                  { name: qsTr("Design Inspiration"), count: 45, icon: "📁" },
                                  { name: qsTr("Music Videos"), count: 24, icon: "📁" },
                                  { name: qsTr("Recipe"), count: 12, icon: "📁" },
                                  { name: qsTr("Uncategorized"), count: 117, icon: "📁" }
                              ]

    // 筛选状态
    property string searchQuery: ""
    property string platformFilter: "all"
    property string mediaTypeFilter: "all"
    property string favoriteFilter: "all"
    property string batchFilter: "all"
    property int selectedCount: 0
    property string viewMode: "grid"  // "grid" / "list"

    readonly property int totalItems: libraryItems.length
    readonly property int totalSelected: selectedCount

    ColumnLayout {
        anchors.fill: parent
        spacing: 16

        // ============================================================
        // 页面头部
        // ============================================================
        RowLayout {
            Layout.fillWidth: true
            spacing: 14

            // 渐变标题 "Library"
            Canvas {
                id: titleCanvas
                Layout.preferredWidth: 140
                Layout.preferredHeight: 32
                renderStrategy: Canvas.Cooperative

                onPaint: {
                    var ctx = getContext("2d")
                    ctx.reset()
                    var text = qsTr("Library")
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

            // lib-badge: items + size
            Rectangle {
                Layout.alignment: Qt.AlignVCenter
                implicitWidth: libBadge.implicitWidth + 20
                implicitHeight: 22
                radius: Theme.rPill
                color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.12)
                border.width: 1
                border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.3)

                Row {
                    id: libBadge
                    anchors.centerIn: parent
                    spacing: 6

                    Rectangle {
                        width: 6; height: 6
                        radius: 3
                        anchors.verticalCenter: parent.verticalCenter
                        color: Theme.accent
                    }

                    Text {
                        text: root.totalItems + " " + qsTr("items") + " · 4.2 GB"
                        color: Theme.accent
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fsMicro
                        font.letterSpacing: 0.5
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }

            Item { Layout.fillWidth: true }

            // 批量操作按钮
            Button {
                text: qsTr("Add to Collection")
                variant: "default"
            }
            Button {
                text: qsTr("Batch Favorite")
                variant: "default"
            }
            Button {
                text: qsTr("Batch Delete")
                variant: "danger"
            }

            // 视图切换
            Rectangle {
                Layout.alignment: Qt.AlignVCenter
                implicitWidth: 72
                implicitHeight: 32
                radius: Theme.rSM
                color: Theme.glassBg
                border.width: 1
                border.color: Theme.glassBorder

                RowLayout {
                    anchors.fill: parent
                    spacing: 0

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        radius: Theme.rSM
                        color: root.viewMode === "grid" ? Theme.glassBgHi : "transparent"

                        Text {
                            anchors.centerIn: parent
                            text: "▦"
                            color: root.viewMode === "grid" ? Theme.textPrimary : Theme.textMute
                            font.pixelSize: 14
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.viewMode = "grid"
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        radius: Theme.rSM
                        color: root.viewMode === "list" ? Theme.glassBgHi : "transparent"

                        Text {
                            anchors.centerIn: parent
                            text: "☰"
                            color: root.viewMode === "list" ? Theme.textPrimary : Theme.textMute
                            font.pixelSize: 14
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.viewMode = "list"
                        }
                    }
                }
            }
        }

        // ============================================================
        // Library 主体布局：Collections 侧栏 + Content
        // ============================================================
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 16

            // ---------- Collections 侧栏 ----------
            GlassCard {
                Layout.preferredWidth: 220
                Layout.fillHeight: true
                Layout.alignment: Qt.AlignTop
                padding: 12

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 8

                    // Collections 头部
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        Text {
                            text: qsTr("Collections")
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fsBody
                            font.weight: Font.Bold
                            Layout.fillWidth: true
                        }

                        Rectangle {
                            Layout.preferredWidth: 22
                            Layout.preferredHeight: 22
                            radius: Theme.rXS
                            color: Theme.glassBg
                            border.width: 1
                            border.color: Theme.glassBorder

                            Text {
                                anchors.centerIn: parent
                                text: "+"
                                color: Theme.textMute
                                font.pixelSize: 14
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                            }
                        }
                    }

                    // Collection 列表
                    ListView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: root.collections
                        spacing: 2
                        interactive: false

                        delegate: Rectangle {
                            width: ListView.view.width
                            height: 36
                            radius: Theme.rMD
                            color: modelData.active ? Theme.glassBgHi : "transparent"
                            border.width: modelData.active ? 1 : 0
                            border.color: modelData.active ? Theme.glassBorder : "transparent"

                            readonly property bool isFav: !!modelData.favorite

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 8
                                anchors.rightMargin: 8
                                spacing: 8

                                Text {
                                    text: modelData.icon || "📁"
                                    color: isFav ? Theme.danger : Theme.textMute
                                    font.pixelSize: 12
                                }

                                Text {
                                    text: modelData.name
                                    color: modelData.active ? Theme.textPrimary : Theme.textMute
                                    font.pixelSize: Theme.fsSmall
                                    font.weight: modelData.active ? Font.DemiBold : Font.Normal
                                    Layout.fillWidth: true
                                    elide: Text.ElideRight
                                }

                                Text {
                                    text: modelData.count
                                    color: Theme.textDim
                                    font.family: Theme.fontMono
                                    font.pixelSize: Theme.fsMicro
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                            }
                        }
                    }

                    // 提示
                    Text {
                        Layout.fillWidth: true
                        text: qsTr("Right-click collection to rename or delete")
                        color: Theme.textDim
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                        horizontalAlignment: Text.AlignHCenter
                        topPadding: 8
                    }
                }
            }

            // ---------- Library 内容区 ----------
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 12

                // ===== 筛选工具条 =====
                GlassCard {
                    Layout.fillWidth: true
                    padding: 14

                    RowLayout {
                        anchors.fill: parent
                        spacing: 10

                        Input {
                            Layout.fillWidth: true
                            Layout.preferredWidth: 1
                            placeholderText: qsTr("Search title, author, URL...")
                            text: root.searchQuery
                            onTextEdited: root.searchQuery = text
                        }

                        ComboBox {
                            id: platCombo
                            Layout.preferredWidth: 130
                            model: [qsTr("All Platforms"), "YouTube", "Instagram", "X",
                                    qsTr("哔哩哔哩"), qsTr("抖音"), qsTr("快手"),
                                    qsTr("微博"), qsTr("小红书")]

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

                        ComboBox {
                            id: mediaCombo
                            Layout.preferredWidth: 110
                            model: [qsTr("All Media"), qsTr("Video"), qsTr("Audio"),
                                    qsTr("Image"), qsTr("Mixed")]
                            onActivated: root.mediaTypeFilter = (index === 0) ? "all" : ["all","video","audio","image","mixed"][index]

                            background: Rectangle {
                                color: Theme.inputBg
                                border.width: 1
                                border.color: mediaCombo.activeFocus ? Theme.accent : Theme.glassBorder
                                radius: Theme.rMD
                            }
                            contentItem: Text {
                                text: mediaCombo.displayText
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fsSmall
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 10
                            }
                        }

                        ComboBox {
                            id: favCombo
                            Layout.preferredWidth: 110
                            model: [qsTr("All"), qsTr("Favorites Only"), qsTr("Not Favorited")]

                            background: Rectangle {
                                color: Theme.inputBg
                                border.width: 1
                                border.color: favCombo.activeFocus ? Theme.accent : Theme.glassBorder
                                radius: Theme.rMD
                            }
                            contentItem: Text {
                                text: favCombo.displayText
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fsSmall
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 10
                            }
                        }

                        ComboBox {
                            id: batchCombo
                            Layout.preferredWidth: 140
                            model: [qsTr("All Batches"), "Batch 2024.07.24", "Batch 2024.07.20", "Batch 2024.07.15"]

                            background: Rectangle {
                                color: Theme.inputBg
                                border.width: 1
                                border.color: batchCombo.activeFocus ? Theme.accent : Theme.glassBorder
                                radius: Theme.rMD
                            }
                            contentItem: Text {
                                text: batchCombo.displayText
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fsSmall
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 10
                            }
                        }

                        Button {
                            text: qsTr("Reset")
                            variant: "default"
                        }
                    }
                }

                // ===== 批量工具条（选中时显示） =====
                GlassCard {
                    Layout.fillWidth: true
                    visible: root.selectedCount > 0
                    padding: 10

                    RowLayout {
                        anchors.fill: parent
                        spacing: 12

                        Text {
                            text: "<b>" + root.selectedCount + "</b> " + qsTr("selected")
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fsSmall
                            textFormat: Text.RichText
                        }

                        Button {
                            text: qsTr("Select All")
                            variant: "default"
                        }

                        Item { Layout.fillWidth: true }

                        Button {
                            text: qsTr("Favorite")
                            variant: "default"
                        }
                        Button {
                            text: qsTr("Add to Collection")
                            variant: "default"
                        }
                        Button {
                            text: qsTr("Delete")
                            variant: "danger"
                        }
                    }
                }

                // ===== 媒体卡片网格 =====
                GridLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    columns: root.width > 1100 ? 4 : (root.width > 800 ? 3 : 2)
                    columnSpacing: 12
                    rowSpacing: 12
                    visible: root.libraryItems.length > 0

                    Repeater {
                        model: root.libraryItems

                        delegate: GlassCard {
                            id: mediaCard
                            required property var modelData
                            required property int index

                            Layout.fillWidth: true
                            Layout.preferredHeight: 220
                            padding: 0

                            readonly property string platform: modelData.platform || ""
                            readonly property string mediaType: modelData.mediaType || "video"
                            readonly property bool favorited: !!modelData.favorited
                            readonly property color platColor: Theme.platformColor(platform)
                            readonly property color thumbC1: modelData.thumbC1 || platColor
                            readonly property color thumbC2: modelData.thumbC2 || Theme.accent2
                            property bool selected: false

                            ColumnLayout {
                                anchors.fill: parent
                                spacing: 0

                                // 缩略图区
                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 120
                                    radius: Theme.rXL
                                    color: "transparent"
                                    clip: true

                                    Rectangle {
                                        anchors.fill: parent
                                        anchors.bottomMargin: -Theme.rXL
                                        radius: Theme.rXL
                                        gradient: Gradient {
                                            orientation: Gradient.Horizontal
                                            GradientStop { position: 0.0; color: mediaCard.thumbC1 }
                                            GradientStop { position: 1.0; color: mediaCard.thumbC2 }
                                        }

                                        // 媒体类型图标
                                        Text {
                                            anchors.centerIn: parent
                                            text: mediaCard.mediaType === "audio" ? "🎵"
                                                  : (mediaCard.mediaType === "image" ? "🖼" : "🎬")
                                            color: Qt.rgba(1, 1, 1, 0.9)
                                            font.pixelSize: 28
                                        }

                                        // 顶部 badges
                                        RowLayout {
                                            anchors.top: parent.top
                                            anchors.left: parent.left
                                            anchors.right: parent.right
                                            anchors.margins: 8
                                            spacing: 4

                                            Badge {
                                                badgeType: mediaCard.platform
                                                text: mediaCard.platform
                                            }

                                            Badge {
                                                badgeType: "default"
                                                text: mediaCard.mediaType
                                            }

                                            Item { Layout.fillWidth: true }

                                            // 收藏按钮
                                            Rectangle {
                                                Layout.preferredWidth: 24
                                                Layout.preferredHeight: 24
                                                radius: 12
                                                color: Qt.rgba(0, 0, 0, 0.4)
                                                border.width: 1
                                                border.color: Qt.rgba(1, 1, 1, 0.2)

                                                Text {
                                                    anchors.centerIn: parent
                                                    text: mediaCard.favorited ? "❤" : "♡"
                                                    color: mediaCard.favorited ? Theme.danger : "white"
                                                    font.pixelSize: 12
                                                }

                                                MouseArea {
                                                    anchors.fill: parent
                                                    cursorShape: Qt.PointingHandCursor
                                                }
                                            }
                                        }
                                    }
                                }

                                // 信息 + 操作
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Layout.leftMargin: 12
                                    Layout.rightMargin: 12
                                    Layout.topMargin: 8
                                    Layout.bottomMargin: 8
                                    spacing: 4

                                    Text {
                                        Layout.fillWidth: true
                                        text: modelData.title || ""
                                        color: Theme.textPrimary
                                        font.pixelSize: Theme.fsBody
                                        font.weight: Font.DemiBold
                                        elide: Text.ElideRight
                                        maximumLineCount: 1
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        text: (modelData.author || "") + " · "
                                              + (modelData.size || "") + " · "
                                              + (modelData.date || "")
                                        color: Theme.textMute
                                        font.family: Theme.fontMono
                                        font.pixelSize: Theme.fsMicro
                                        elide: Text.ElideRight
                                    }

                                    Item { Layout.fillHeight: true }

                                    // 操作按钮
                                    Row {
                                        spacing: 4
                                        Layout.fillWidth: true

                                        Button {
                                            text: "👁"
                                            variant: "default"
                                            implicitWidth: 32
                                            implicitHeight: 28
                                        }
                                        Button {
                                            text: "📂"
                                            variant: "default"
                                            implicitWidth: 32
                                            implicitHeight: 28
                                        }
                                        Button {
                                            text: "+"
                                            variant: "default"
                                            implicitWidth: 32
                                            implicitHeight: 28
                                        }
                                        Button {
                                            text: "🗑"
                                            variant: "danger"
                                            implicitWidth: 32
                                            implicitHeight: 28
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // ===== 分页 =====
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    visible: root.libraryItems.length > 0

                    Button {
                        text: "‹"
                        variant: "default"
                        implicitWidth: 32
                        implicitHeight: 32
                    }

                    Repeater {
                        model: ["1", "2", "3", "···", "28"]

                        delegate: Rectangle {
                            Layout.preferredWidth: 32
                            Layout.preferredHeight: 32
                            radius: Theme.rSM
                            color: index === 0 ? Theme.accent : Theme.glassBg
                            border.width: 1
                            border.color: index === 0 ? "transparent" : Theme.glassBorder

                            Text {
                                anchors.centerIn: parent
                                text: modelData
                                color: index === 0 ? "white" : Theme.textMute
                                font.family: Theme.fontMono
                                font.pixelSize: Theme.fsSmall
                                font.weight: Font.DemiBold
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                            }
                        }
                    }

                    Button {
                        text: "›"
                        variant: "default"
                        implicitWidth: 32
                        implicitHeight: 32
                    }

                    Item { Layout.fillWidth: true }

                    Text {
                        text: qsTr("Showing") + " <b>1-" + root.libraryItems.length + "</b> " + qsTr("of") + " <b>" + root.totalItems + "</b>"
                        color: Theme.textMute
                        font.pixelSize: Theme.fsMicro
                        font.family: Theme.fontMono
                        textFormat: Text.RichText
                    }
                }

                // ===== 空状态 =====
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: root.libraryItems.length === 0

                    Item { Layout.fillHeight: true }

                    EmptyState {
                        Layout.alignment: Qt.AlignHCenter
                        icon: "📚"
                        title: qsTr("Library is empty")
                        hint: qsTr("Downloaded media will appear here")
                    }

                    Item { Layout.fillHeight: true }
                }
            }
        }
    }
}
