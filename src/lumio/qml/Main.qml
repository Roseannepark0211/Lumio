// ============================================================
// LUMIO // Main.qml — 主入口
// ------------------------------------------------------------
// 布局：
//   - 左侧 Sidebar（220px）
//   - 右侧主区域（背景大气色光球 + 噪点 + StackLayout 切页）
// 页面路由通过 StackLayout 切换，由 activePage 控制
// ============================================================
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import Lumio
import Lumio.Components

ApplicationWindow {
    id: window
    visible: true
    width: 1180
    height: 760
    minimumWidth: 1080
    minimumHeight: 680
    title: "Lumio"
    color: Theme.bgBase

    // ---------- 全局状态 ----------
    property string activePage: "home"
    // controller 由 qml_bridge.QmlController 通过 setContextProperty 注入为全局 `controller`
    // 全局 tr() 函数：所有页面统一用 tr("key") 调用 i18n，参数通过 controller.tr 传递
    function tr(key) {
        return (typeof controller !== "undefined" && controller) ? controller.tr(key) : key
    }
    function trFmt(key, kwargs) {
        // 简单格式化：tr(key) 返回 "xxx {n} yyy"，用 kwargs 字典替换
        var s = tr(key)
        if (!kwargs) return s
        for (var k in kwargs) {
            s = s.replace(new RegExp("\\{" + k + "\\}", "g"), kwargs[k])
        }
        return s
    }

    // Toast 全局容器
    function showToast(msg) {
        if (typeof controller !== "undefined" && controller) {
            controller.showToast(msg)
        }
    }

    // 监听 controller 信号 → 主题/语言切换
    Connections {
        target: typeof controller !== "undefined" ? controller : null
        // 启动时同步 controller 的 theme 到 QML Theme（修复清单问题 1：首次切换需点两次）
        // 原因：Theme.qml 第 14 行硬编码 theme="dark"，若 config.json 是 "light"，
        // 启动后 Theme.theme 仍是 dark，第一次点击 setTheme("light") 时
        // controller._theme 已是 light（无变化），不触发 themeChanged 信号
        Component.onCompleted: {
            if (controller && controller.theme) {
                Theme.theme = controller.theme
            }
        }
        function onThemeChanged(theme) { Theme.theme = theme }
        function onLangChanged(lang) { _reloadCurrentPage() }
        function onToastRequested(message) { _toast.show(message) }
    }

    // 语言切换后刷新当前页（重新加载 Loader，触发 tr() 重算）
    function _reloadCurrentPage() {
        var idx = _pageStack.currentIndex
        var loader = _pageStack.itemAt(idx)
        if (!loader) return
        var src = loader.source
        loader.source = ""
        loader.source = src
    }

    // Toast 提示框
    Rectangle {
        id: _toast
        anchors.bottom: parent.bottom
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottomMargin: 40
        width: _toastText.implicitWidth + 40
        height: 38
        radius: 12
        color: Qt.rgba(0, 0, 0, 0.85)
        border.width: 1
        border.color: Qt.rgba(1, 1, 1, 0.15)
        opacity: 0
        z: 9999

        function show(msg) {
            _toastText.text = msg
            _toast.opacity = 1
            _toastHide.restart()
        }

        Text {
            id: _toastText
            anchors.centerIn: parent
            color: "#ffffff"
            font.family: Theme.fontBody
            font.pixelSize: Theme.fsBody
            font.weight: Font.Medium
        }

        SequentialAnimation on opacity {
            id: _toastHide
            running: false
            NumberAnimation { from: 1; to: 1; duration: 2200 }
            NumberAnimation { from: 1; to: 0; duration: 300 }
        }
    }

    // ============================================================
    // 大气背景层 — 4 个色光球 + 渐变底
    // 用 Canvas 绘制 radial gradient（兼容所有 Qt 6.x）
    // ============================================================
    Item {
        id: _atmosphere
        anchors.fill: parent
        z: 0

        // 渐变底色
        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                orientation: Gradient.Vertical
                GradientStop { position: 0.0; color: Theme.bgGrad1 }
                GradientStop { position: 1.0; color: Theme.bgGrad2 }
            }
        }

        // 4 个色光球（Canvas 绘制 radial gradient）
        Canvas {
            anchors.fill: parent
            renderStrategy: Canvas.Cooperative
            onPaint: {
                var ctx = getContext("2d")
                ctx.reset()
                var w = width, h = height

                // 紫色 #5e5ce6 - 左上
                var g1 = ctx.createRadialGradient(w * 0.15, h * 0.0, 0, w * 0.15, h * 0.0, w * 0.5)
                g1.addColorStop(0, "rgba(94, 92, 230, 0.28)")
                g1.addColorStop(1, "rgba(94, 92, 230, 0)")
                ctx.fillStyle = g1
                ctx.fillRect(0, 0, w, h)

                // 粉红 #ff3b5c - 右上
                var g2 = ctx.createRadialGradient(w * 0.85, h * 0.2, 0, w * 0.85, h * 0.2, w * 0.45)
                g2.addColorStop(0, "rgba(255, 59, 92, 0.18)")
                g2.addColorStop(1, "rgba(255, 59, 92, 0)")
                ctx.fillStyle = g2
                ctx.fillRect(0, 0, w, h)

                // 蓝色 #0a84ff - 右下
                var g3 = ctx.createRadialGradient(w * 0.8, h * 1.0, 0, w * 0.8, h * 1.0, w * 0.5)
                g3.addColorStop(0, "rgba(10, 132, 255, 0.22)")
                g3.addColorStop(1, "rgba(10, 132, 255, 0)")
                ctx.fillStyle = g3
                ctx.fillRect(0, 0, w, h)

                // 橙色 #ff9f0a - 左下
                var g4 = ctx.createRadialGradient(w * 0.3, h * 0.9, 0, w * 0.3, h * 0.9, w * 0.45)
                g4.addColorStop(0, "rgba(255, 159, 10, 0.12)")
                g4.addColorStop(1, "rgba(255, 159, 10, 0)")
                ctx.fillStyle = g4
                ctx.fillRect(0, 0, w, h)
            }
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            Component.onCompleted: requestPaint()
        }
    }

    // ============================================================
    // 主布局：Sidebar + Content
    // ============================================================
    RowLayout {
        anchors.fill: parent
        spacing: 0
        z: 1

        // ---------- Sidebar ----------
        Sidebar {
            Layout.preferredWidth: 220
            Layout.fillHeight: true
            activePage: window.activePage
            theme: Theme.theme
            onPageRequested: function(page) {
                window.activePage = page
            }
            onThemeToggleRequested: {
                // 通过 controller 持久化到 config，并触发 themeChanged 信号
                // Main.qml 的 onThemeChanged 处理器会同步更新 Theme.theme
                if (typeof controller !== "undefined" && controller) {
                    controller.toggleTheme()
                } else {
                    Theme.theme = Theme.theme === "dark" ? "light" : "dark"
                }
            }
        }

        // ---------- Content 区域 ----------
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // 页面 Stack
            StackLayout {
                id: _pageStack
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: _pageIndex(window.activePage)

                function _pageIndex(page) {
                    var pages = ["home", "inbox", "downloads", "history",
                                 "library", "stats", "notifications", "settings"]
                    var idx = pages.indexOf(page)
                    return idx < 0 ? 0 : idx
                }

                // 8 个页面（用 Loader 延迟加载，节省启动时间）
                Loader {
                    active: _pageStack.currentIndex === 0
                    source: "Lumio/Pages/HomePage.qml"
                }
                Loader {
                    active: _pageStack.currentIndex === 1
                    source: "Lumio/Pages/InboxPage.qml"
                }
                Loader {
                    active: _pageStack.currentIndex === 2
                    source: "Lumio/Pages/DownloadsPage.qml"
                }
                Loader {
                    active: _pageStack.currentIndex === 3
                    source: "Lumio/Pages/HistoryPage.qml"
                }
                Loader {
                    active: _pageStack.currentIndex === 4
                    source: "Lumio/Pages/LibraryPage.qml"
                }
                Loader {
                    active: _pageStack.currentIndex === 5
                    source: "Lumio/Pages/StatsPage.qml"
                }
                Loader {
                    active: _pageStack.currentIndex === 6
                    source: "Lumio/Pages/NotificationsPage.qml"
                }
                Loader {
                    active: _pageStack.currentIndex === 7
                    source: "Lumio/Pages/SettingsPage.qml"
                }
            }
        }
    }
}
