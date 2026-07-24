// ============================================================
// LUMIO // Sidebar — Liquid Glass 侧边栏
// ------------------------------------------------------------
// 还原 design_preview/styles.css 的 .sidebar 样式：
//   - 背景 Theme.sidebarBg + 右侧 1px glassBorder
//   - padding (24, 16, 16)
//   - 品牌 "Lumio" 渐变文字 (white → #a8c7ff)
//   - 8 个导航项 (Home/Inbox/Downloads/History/Library/Stats/Notifications/Settings)
//   - active 态：glassBgHi 背景 + 左侧 3px 渐变竖条 + 辉光
//   - hover 态：glassBg 背景 + 文字色变化
//   - Collections 区域（标题 + 添加按钮 + 集合列表）
//   - 底部：主题切换按钮 + 版本号
// ------------------------------------------------------------
// 外部调用：
//   Sidebar { controller: myController; activePageId: "home" }
//   controller.navigateTo(pageId) / controller.toggleTheme() / controller.collections()
// 信号：
//   navigateTo(string pageId)
//   collectionSelected(int collectionId)
//   createCollectionRequested()
// ============================================================

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import Lumio

pragma ComponentBehavior: Bound

Rectangle {
    id: root

    // ---- 尺寸 ----
    implicitWidth: Theme.sidebarWidth   // 220
    implicitHeight: 600
    color: Theme.sidebarBg
    border.width: 0

    // ---- 对外属性 ----
    property var navItems: [
        { icon: "🏠", label: "首页", pageId: "home" },
        { icon: "📥", label: "收件箱", pageId: "inbox" },
        { icon: "⬇️", label: "下载", pageId: "downloads" },
        { icon: "📋", label: "历史", pageId: "history" },
        { icon: "📚", label: "媒体库", pageId: "library" },
        { icon: "📊", label: "统计", pageId: "stats" },
        { icon: "🔔", label: "通知", pageId: "notifications" },
        { icon: "⚙️", label: "设置", pageId: "settings" }
    ]
    property string activePageId: "home"
    property var collections: []                 // [{ id: int, name: string, count: int }]
    property int activeCollectionId: -1
    property var controller: null                // 可选：注入 navigateTo/toggleTheme/collections
    property string brandSub: "v4.2"
    property string versionText: "Build 2026.07.24"

    // ---- 对外信号 ----
    signal navigateTo(string pageId)
    signal collectionSelected(int collectionId)
    signal createCollectionRequested()

    // ---- 内部方法 ----
    function _navigate(pageId) {
        root.activePageId = pageId
        root.navigateTo(pageId)
        if (root.controller && typeof root.controller.navigateTo === "function") {
            root.controller.navigateTo(pageId)
        }
    }

    function _toggleTheme() {
        if (root.controller && typeof root.controller.toggleTheme === "function") {
            root.controller.toggleTheme()
        } else {
            // 直接切 Theme 单例，全局响应式刷新
            Theme.theme = Theme.theme === "dark" ? "light" : "dark"
        }
    }

    function _loadCollections() {
        if (root.controller && typeof root.controller.collections === "function") {
            try {
                root.collections = root.controller.collections() || []
            } catch (e) {
                root.collections = []
            }
        }
    }

    Component.onCompleted: _loadCollections()

    // ---- 右侧 1px 玻璃分隔线（.sidebar border-right） ----
    Rectangle {
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        width: 1
        color: Theme.glassBorder
    }

    // ---- 主布局：padding (24, 16, 16) ----
    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: 24
        anchors.leftMargin: 16
        anchors.rightMargin: 16
        anchors.bottomMargin: 16
        spacing: 0

        // ============================================================
        // 品牌区
        // ============================================================
        // "Lumio" 渐变文字 — 用 Canvas 绘制 white → #a8c7ff 水平渐变
        // （CSS linear-gradient(135deg, #ffffff, #a8c7ff)，水平近似）
        Canvas {
            id: brandCanvas
            Layout.fillWidth: true
            Layout.bottomMargin: 2
            Layout.preferredHeight: 26
            renderStrategy: Canvas.Cooperative

            onPaint: {
                var ctx = getContext("2d")
                ctx.reset()
                var text = "Lumio"
                ctx.font = "800 20px " + Theme.fontDisplay
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

        // brand-sub（v4.2，mono，dim，letter-spacing 1.5）
        Text {
            Layout.fillWidth: true
            Layout.bottomMargin: 28
            text: root.brandSub
            color: Theme.textDim
            font.family: Theme.fontMono
            font.pixelSize: 10
            font.letterSpacing: 1.5
        }

        // ============================================================
        // 导航列表（.nav，gap 2px）
        // ============================================================
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2

            Repeater {
                model: root.navItems
                delegate: Rectangle {
                    id: navItem
                    required property var modelData

                    readonly property bool isActive: root.activePageId === modelData.pageId

                    Layout.fillWidth: true
                    height: 34
                    radius: Theme.rMD              // 14
                    color: navItem.isActive
                           ? Theme.glassBgHi
                           : (navMouse.containsMouse ? Theme.glassBg : "transparent")

                    Behavior on color { ColorAnimation { duration: 200 } }

                    // 按压缩放反馈
                    scale: navMouse.pressed ? 0.98 : 1.0
                    Behavior on scale {
                        NumberAnimation { duration: 120; easing.type: Easing.OutCubic }
                    }

                    // ---- active 态左侧指示器（3px × 16px 渐变竖条 + 辉光） ----
                    Rectangle {
                        id: activeIndicator
                        width: 3
                        height: 16
                        radius: 2
                        x: 4
                        anchors.verticalCenter: parent.verticalCenter
                        visible: navItem.isActive
                        gradient: Gradient {
                            orientation: Gradient.Vertical
                            GradientStop { position: 0.0; color: Theme.accent }
                            GradientStop { position: 1.0; color: Theme.accent2 }
                        }
                        // 辉光：accentSoft 8px 模糊
                        layer.enabled: true
                        layer.effect: MultiEffect {
                            shadowEnabled: true
                            shadowColor: Theme.accentSoft
                            shadowBlur: 0.8
                            shadowOpacity: 1.0
                            shadowVerticalOffset: 0
                            shadowHorizontalOffset: 0
                            blurEnabled: false
                        }
                    }

                    // ---- 内容：icon + label，gap 12px，padding 14px ----
                    Row {
                        anchors.fill: parent
                        anchors.leftMargin: 14
                        anchors.rightMargin: 14
                        spacing: 12

                        Text {
                            width: 18
                            height: parent.height
                            text: navItem.modelData.icon
                            font.pixelSize: 14
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            color: navItem.isActive
                                   ? Theme.textPrimary
                                   : (navMouse.containsMouse ? Theme.textPrimary : Theme.textMute)
                            Behavior on color { ColorAnimation { duration: 200 } }
                        }

                        Text {
                            height: parent.height
                            text: navItem.modelData.label
                            color: navItem.isActive
                                   ? Theme.textPrimary
                                   : (navMouse.containsMouse ? Theme.textPrimary : Theme.textMute)
                            font.family: Theme.fontBody
                            font.pixelSize: Theme.fsBody        // 14
                            font.weight: Font.Medium
                            verticalAlignment: Text.AlignVCenter
                            Behavior on color { ColorAnimation { duration: 200 } }
                        }
                    }

                    MouseArea {
                        id: navMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root._navigate(navItem.modelData.pageId)
                    }
                }
            }
        }

        // ============================================================
        // Collections 区域（library 导航项下方）
        // ============================================================
        ColumnLayout {
            id: collectionsSection
            Layout.fillWidth: true
            Layout.topMargin: 16
            spacing: 2

            // 标题行：COLLECTIONS + 添加按钮
            RowLayout {
                Layout.fillWidth: true
                Layout.bottomMargin: 6
                spacing: 0

                Text {
                    text: "COLLECTIONS"
                    color: Theme.textDim
                    font.family: Theme.fontMono
                    font.pixelSize: 10
                    font.letterSpacing: 1.5
                    font.weight: Font.Medium
                    verticalAlignment: Text.AlignVCenter
                }

                Item { Layout.fillWidth: true }

                // + 添加按钮（22×22，hover 显示 accent）
                Rectangle {
                    Layout.preferredWidth: 22
                    Layout.preferredHeight: 22
                    radius: 6
                    color: addCollMouse.containsMouse ? Theme.glassBgHi : "transparent"
                    Behavior on color { ColorAnimation { duration: 150 } }

                    Text {
                        anchors.centerIn: parent
                        text: "+"
                        color: addCollMouse.containsMouse ? Theme.accent : Theme.textMute
                        font.pixelSize: 14
                        font.weight: Font.Bold
                        Behavior on color { ColorAnimation { duration: 150 } }
                    }

                    MouseArea {
                        id: addCollMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.createCollectionRequested()
                    }
                }
            }

            // 集合列表
            Repeater {
                model: root.collections
                delegate: Rectangle {
                    id: collItem
                    required property var modelData

                    readonly property bool isActiveColl: root.activeCollectionId === modelData.id

                    Layout.fillWidth: true
                    height: 30
                    radius: Theme.rSM              // 10
                    color: collItem.isActiveColl
                           ? Theme.glassBgHi
                           : (collMouse.containsMouse ? Theme.glassBg : "transparent")

                    Behavior on color { ColorAnimation { duration: 200 } }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        anchors.rightMargin: 10
                        spacing: 8

                        Text {
                            Layout.preferredWidth: 16
                            text: "📁"
                            font.pixelSize: 12
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }

                        Text {
                            Layout.fillWidth: true
                            text: collItem.modelData.name
                            color: collItem.isActiveColl
                                   ? Theme.textPrimary
                                   : (collMouse.containsMouse ? Theme.textPrimary : Theme.textMute)
                            font.family: Theme.fontBody
                            font.pixelSize: 13
                            font.weight: Font.Medium
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                            Behavior on color { ColorAnimation { duration: 200 } }
                        }

                        Text {
                            text: String(collItem.modelData.count)
                            color: Theme.textDim
                            font.family: Theme.fontMono
                            font.pixelSize: 11
                            verticalAlignment: Text.AlignVCenter
                        }
                    }

                    MouseArea {
                        id: collMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            root.activeCollectionId = collItem.modelData.id
                            root.collectionSelected(collItem.modelData.id)
                            if (root.controller
                                    && typeof root.controller.onCollectionSelected === "function") {
                                root.controller.onCollectionSelected(collItem.modelData.id)
                            }
                        }
                    }
                }
            }
        }

        // ---- 弹性占位：把 footer 推到底部（.sidebar-footer margin-top: auto） ----
        Item { Layout.fillHeight: true }

        // ============================================================
        // 底部 footer（border-top + 主题切换 + 版本号）
        // ============================================================
        ColumnLayout {
            Layout.fillWidth: true
            Layout.topMargin: 16
            spacing: 0

            // 顶部分隔线
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                color: Theme.glassBorder
            }

            // padding-top 16
            Item { Layout.preferredHeight: 16 }

            // 主题切换按钮
            Rectangle {
                id: themeToggle
                Layout.fillWidth: true
                Layout.preferredHeight: 30
                radius: Theme.rSM              // 10
                color: themeMouse.containsMouse ? Theme.glassBg : "transparent"
                border.width: 1
                border.color: Theme.glassBorder

                Behavior on color { ColorAnimation { duration: 200 } }
                Behavior on border.color { ColorAnimation { duration: 200 } }

                Row {
                    anchors.centerIn: parent
                    spacing: 6

                    Text {
                        text: Theme.theme === "dark" ? "🌙" : "☀️"
                        font.pixelSize: 12
                        verticalAlignment: Text.AlignVCenter
                    }

                    Text {
                        text: Theme.theme === "dark" ? "Dark" : "Light"
                        color: themeMouse.containsMouse ? Theme.textPrimary : Theme.textMute
                        font.family: Theme.fontBody
                        font.pixelSize: Theme.fsMicro     // 11
                        font.weight: Font.Medium
                        verticalAlignment: Text.AlignVCenter
                        Behavior on color { ColorAnimation { duration: 200 } }
                    }
                }

                MouseArea {
                    id: themeMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root._toggleTheme()
                }
            }

            // 版本号（mono，9px，dim，居中）
            Text {
                Layout.fillWidth: true
                Layout.topMargin: 8
                text: root.versionText
                color: Theme.textDim
                font.family: Theme.fontMono
                font.pixelSize: 9
                font.letterSpacing: 0.5
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }
}
