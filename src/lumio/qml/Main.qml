import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import Lumio
import Lumio.Components
import Lumio.Pages

// 根窗口，还原 design_preview/styles.css 的 .app 布局：
//   grid-template-columns: 220px 1fr
ApplicationWindow {
    id: window
    visible: true
    width: 1020
    height: 700
    minimumWidth: 960
    minimumHeight: 640
    color: Theme.bgBase  // 防止闪烁
    title: "Lumio"

    // ---- 大气背景层 ----
    AtmosphericBackground {
        anchors.fill: parent
        z: 0
    }

    // ---- 主内容：sidebar + content area ----
    RowLayout {
        anchors.fill: parent
        spacing: 0

        // Sidebar
        Sidebar {
            id: sidebar
            Layout.fillHeight: true
            Layout.preferredWidth: Theme.sidebarWidth
            onNavigateTo: function(pageId) {
                pageStack.switchTo(pageId)
            }
        }

        // 1px 分隔线
        Rectangle {
            Layout.fillHeight: true
            Layout.preferredWidth: 1
            color: Theme.glassBorder
        }

        // 内容区
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            // 内容容器（统一 padding + max-width）
            Item {
                id: contentContainer
                width: Math.min(parent.width, Theme.mainMaxWidth + Theme.mainPaddingLeft * 2)
                height: Math.max(parent.height, pageStack.contentHeight)
                anchors.horizontalCenter: parent.horizontalCenter

                // 页面切换栈
                StackLayout {
                    id: pageStack
                    anchors.fill: parent
                    anchors.margins: 0

                    // 当前页面的高度用于撑开 ScrollView
                    property real contentHeight: currentIndex > -1 && itemAt(currentIndex) ? itemAt(currentIndex).implicitHeight : 0

                    currentIndex: 0

                    function switchTo(pageId) {
                        var pages = {
                            "home": 0, "inbox": 1, "downloads": 2,
                            "history": 3, "library": 4, "stats": 5,
                            "notifications": 6, "settings": 7
                        }
                        if (pageId in pages) {
                            currentIndex = pages[pageId]
                            if (controller) controller.navigateTo(pageId)
                        }
                    }

                    // ---- 实际页面 ----
                    HomePage {}
                    InboxPage {}
                    DownloadsPage {}
                    HistoryPage {}
                    LibraryPage {}
                    StatsPage {}
                    NotificationsPage {}
                    SettingsPage {}
                }
            }
        }
    }

    // QML 加载完成后，根据配置设置主题
    Component.onCompleted: {
        if (typeof controller !== "undefined") {
            Theme.theme = controller.theme
        }
    }
}
