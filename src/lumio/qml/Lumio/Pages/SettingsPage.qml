// ============================================================
// LUMIO // SettingsPage — 设置页面
// ------------------------------------------------------------
// 还原 design_preview/settings.html：
//   - 页面头部：渐变标题 + 版本 badge + 检查更新
//   - 设置布局：左侧 nav + 右侧内容
//   - General 组：语言 / 主题 / 系统托盘 / 自启动 / 启动时检查更新
//   - Downloads 组：输出目录 / 并发数 / 冲突策略 / 文件名模板 / YT画质 / 自动合并 / 续传
//   - Cookie & API 组：IG / X / Apify / TG Bot / 本地 Bot API（可折叠）
//   - Cache 组：4 张缓存卡 + 自动清理 + 保留天数 + 单目录上限 + 清空全部
//   - About 组：Logo + 版本 + 描述 + 技术栈 + 操作按钮
// 外部调用：
//   SettingsPage { controller: myController }
// 数据：controller.settings() -> { ... }
// ============================================================

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Lumio
import Lumio.Components

Item {
    id: root

    implicitHeight: 1100

    property var controller: null
    property string activeSection: "general"
    property bool cookieApiExpanded: true

    // 通用设置（默认值，实际由 controller 注入）
    property string language: "English"
    property string theme: "dark"
    property bool systemTray: true
    property bool autoStart: false
    property bool checkUpdatesOnStart: true
    property string outputDir: "C:\\Users\\17551\\Downloads\\Lumio"
    property int maxConcurrent: 3
    property string conflictPolicy: "rename"
    property string filenamePattern: "{author}_{timestamp}"
    property string ytQuality: "Best Available"
    property bool autoMerge: true
    property bool resumeOnRestart: true
    property string autoCleanMode: "startup"
    property int retentionDays: 7
    property int maxSizePerDir: 500

    // 缓存数据
    property var cacheInfos: [
        { name: qsTr("Inbox Media"),    size: "248.5", unit: "MB", files: 1284, path: "~/.lumio/inbox_media/",     icon: "📥" },
        { name: qsTr("Thumbnails"),     size: "18.4",  unit: "MB", files: 248,  path: "~/.lumio/thumbs/",          icon: "🖼" },
        { name: qsTr("Provider Cache"), size: "2.1",   unit: "MB", files: 1,    path: "~/.lumio/provider_cache/",  icon: "🔗" },
        { name: qsTr("Preview Cache"),  size: "8.6",   unit: "MB", files: 42,   path: "~/.lumio/preview/",         icon: "👁" }
    ]

    // 凭证数据
    property var credentials: [
        { name: qsTr("Instagram Cookie"),       status: qsTr("Configured · Valid until 2024-08-15"),     state: "success", actions: ["import","validate","clear"] },
        { name: qsTr("X (Twitter) Cookie"),     status: qsTr("Configured · auth_token + ct0"),           state: "success", actions: ["import","validate","clear"] },
        { name: qsTr("Apify API Token"),        status: qsTr("Token set · Using Apify proxy for IG"),    state: "warning", actions: ["edit","test","clear"] },
        { name: qsTr("Telegram Bot Token"),     status: qsTr("Not configured"),                          state: "dim",     actions: ["configure"] },
        { name: qsTr("Local Bot API Server"),   status: qsTr("Not configured · 20MB file size limit"),   state: "dim",     actions: ["configure"] }
    ]

    ColumnLayout {
        anchors.fill: parent
        spacing: 16

        // ============================================================
        // 页面头部
        // ============================================================
        RowLayout {
            Layout.fillWidth: true
            spacing: 14

            // 渐变标题 "Settings"
            Canvas {
                id: titleCanvas
                Layout.preferredWidth: 160
                Layout.preferredHeight: 32
                renderStrategy: Canvas.Cooperative

                onPaint: {
                    var ctx = getContext("2d")
                    ctx.reset()
                    var text = qsTr("Settings")
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

            Item { Layout.fillWidth: true }

            // 版本 badge
            Rectangle {
                Layout.alignment: Qt.AlignVCenter
                implicitWidth: versionText.implicitWidth + 20
                implicitHeight: 24
                radius: Theme.rPill
                color: Theme.glassBg
                border.width: 1
                border.color: Theme.glassBorder

                Text {
                    id: versionText
                    anchors.centerIn: parent
                    text: "v4.2.0"
                    color: Theme.textMute
                    font.family: Theme.fontMono
                    font.pixelSize: Theme.fsMicro
                    font.weight: Font.DemiBold
                }
            }

            Button {
                text: qsTr("Check Update")
                variant: "primary"
            }
        }

        // ============================================================
        // 设置布局：左侧 nav + 右侧内容
        // ============================================================
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 20

            // ---------- 左侧 NAV ----------
            GlassCard {
                Layout.preferredWidth: 200
                Layout.fillHeight: true
                Layout.alignment: Qt.AlignTop
                padding: 8

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 2

                    Repeater {
                        model: [
                            { key: "general",  label: qsTr("General"),      icon: "⚙" },
                            { key: "downloads",label: qsTr("Downloads"),    icon: "↓" },
                            { key: "cookie",   label: qsTr("Cookie & API"), icon: "🔗" },
                            { key: "cache",    label: qsTr("Cache"),         icon: "📁" },
                            { key: "about",    label: qsTr("About"),         icon: "ⓘ" }
                        ]

                        delegate: Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 38
                            radius: Theme.rMD
                            color: root.activeSection === modelData.key ? Theme.glassBgHi : "transparent"
                            border.width: root.activeSection === modelData.key ? 1 : 0
                            border.color: root.activeSection === modelData.key ? Theme.glassBorder : "transparent"

                            // Active indicator bar
                            Rectangle {
                                visible: root.activeSection === modelData.key
                                x: 2
                                anchors.verticalCenter: parent.verticalCenter
                                width: 3
                                height: 18
                                radius: 2
                                gradient: Gradient {
                                    orientation: Gradient.Vertical
                                    GradientStop { position: 0.0; color: Theme.accent }
                                    GradientStop { position: 1.0; color: Theme.accent2 }
                                }
                            }

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 14
                                anchors.rightMargin: 12
                                spacing: 10

                                Text {
                                    text: modelData.icon
                                    color: root.activeSection === modelData.key ? Theme.accent : Theme.textMute
                                    font.pixelSize: 14
                                }

                                Text {
                                    text: modelData.label
                                    color: root.activeSection === modelData.key ? Theme.textPrimary : Theme.textMute
                                    font.pixelSize: Theme.fsBody
                                    font.weight: root.activeSection === modelData.key ? Font.DemiBold : Font.Normal
                                    Layout.fillWidth: true
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.activeSection = modelData.key
                            }
                        }
                    }

                    Item { Layout.fillHeight: true }
                }
            }

            // ---------- 右侧内容 ----------
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 16

                // ===== GROUP 1: GENERAL =====
                GlassCard {
                    Layout.fillWidth: true
                    padding: 24
                    visible: root.activeSection === "general"

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 0

                        // Head
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.bottomMargin: 16
                            spacing: 2

                            RowLayout {
                                spacing: 10
                                Text {
                                    text: "⚙"
                                    color: Theme.accent
                                    font.pixelSize: 18
                                }
                                Text {
                                    text: qsTr("General")
                                    color: Theme.textPrimary
                                    font.pixelSize: Theme.fsH2
                                    font.weight: Font.Bold
                                }
                            }
                            Text {
                                text: qsTr("Application preferences")
                                color: Theme.textMute
                                font.pixelSize: Theme.fsSmall
                            }
                        }

                        // Language
                        SettingsRow {
                            Layout.fillWidth: true
                            label: qsTr("Language")
                            hint: qsTr("Interface display language")
                            ComboBox {
                                id: langCombo
                                model: ["English", "中文", "日本語"]
                                implicitWidth: 200

                                background: Rectangle {
                                    color: Theme.inputBg
                                    border.width: 1
                                    border.color: langCombo.activeFocus ? Theme.accent : Theme.glassBorder
                                    radius: Theme.rMD
                                }
                                contentItem: Text {
                                    text: langCombo.displayText
                                    color: Theme.textPrimary
                                    font.pixelSize: Theme.fsSmall
                                    verticalAlignment: Text.AlignVCenter
                                    leftPadding: 10
                                }
                            }
                        }

                        // Theme
                        SettingsRow {
                            Layout.fillWidth: true
                            label: qsTr("Theme")
                            hint: qsTr("Choose application appearance")

                            RowLayout {
                                spacing: 8
                                Layout.maximumWidth: 280

                                Repeater {
                                    model: [
                                        { key: "dark",  label: qsTr("Dark"),  icon: "🌙" },
                                        { key: "light", label: qsTr("Light"), icon: "☀" }
                                    ]

                                    delegate: Rectangle {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 40
                                        radius: Theme.rMD
                                        color: root.theme === modelData.key ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.08) : Theme.glassBg
                                        border.width: root.theme === modelData.key ? 2 : 1
                                        border.color: root.theme === modelData.key ? Theme.accent : Theme.glassBorder

                                        RowLayout {
                                            anchors.centerIn: parent
                                            spacing: 8
                                            Text {
                                                text: modelData.icon
                                                color: root.theme === modelData.key ? Theme.accent : Theme.textMute
                                                font.pixelSize: 14
                                            }
                                            Text {
                                                text: modelData.label
                                                color: root.theme === modelData.key ? Theme.textPrimary : Theme.textMute
                                                font.pixelSize: Theme.fsSmall
                                                font.weight: Font.DemiBold
                                            }
                                        }

                                        MouseArea {
                                            anchors.fill: parent
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: root.theme = modelData.key
                                        }
                                    }
                                }
                            }
                        }

                        // System Tray
                        SettingsRow {
                            Layout.fillWidth: true
                            label: qsTr("System Tray")
                            hint: qsTr("Minimize to system tray on window close")
                            Toggle { checked: root.systemTray; onToggled: root.systemTray = checked }
                        }

                        // Auto Start
                        SettingsRow {
                            Layout.fillWidth: true
                            label: qsTr("Auto Start")
                            hint: qsTr("Launch Lumio on system startup")
                            Toggle { checked: root.autoStart; onToggled: root.autoStart = checked }
                        }

                        // Check Updates on Start
                        SettingsRow {
                            Layout.fillWidth: true
                            label: qsTr("Check Updates on Start")
                            hint: qsTr("Automatically check for new versions when app launches")
                            Toggle { checked: root.checkUpdatesOnStart; onToggled: root.checkUpdatesOnStart = checked }
                        }
                    }
                }

                // ===== GROUP 2: DOWNLOADS =====
                GlassCard {
                    Layout.fillWidth: true
                    padding: 24
                    visible: root.activeSection === "downloads"

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 0

                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.bottomMargin: 16
                            spacing: 2

                            RowLayout {
                                spacing: 10
                                Text {
                                    text: "↓"
                                    color: Theme.accent
                                    font.pixelSize: 18
                                }
                                Text {
                                    text: qsTr("Downloads")
                                    color: Theme.textPrimary
                                    font.pixelSize: Theme.fsH2
                                    font.weight: Font.Bold
                                }
                            }
                            Text {
                                text: qsTr("Download behavior and file handling")
                                color: Theme.textMute
                                font.pixelSize: Theme.fsSmall
                            }
                        }

                        // Output Directory
                        SettingsRow {
                            Layout.fillWidth: true
                            label: qsTr("Output Directory")
                            hint: qsTr("Where downloaded files are saved")

                            RowLayout {
                                spacing: 6
                                Layout.maximumWidth: 480

                                Input {
                                    Layout.fillWidth: true
                                    text: root.outputDir
                                    readOnly: true
                                    font.family: Theme.fontMono
                                    font.pixelSize: Theme.fsMicro
                                }
                                Button { text: "📂"; variant: "default"; implicitWidth: 32; implicitHeight: 32 }
                                Button { text: "📋"; variant: "default"; implicitWidth: 32; implicitHeight: 32 }
                            }
                        }

                        // Max Concurrent
                        SettingsRow {
                            Layout.fillWidth: true
                            label: qsTr("Max Concurrent Downloads")
                            hint: qsTr("Parallel download limit (1–8)")

                            RowLayout {
                                spacing: 10
                                Layout.maximumWidth: 280

                                Slider {
                                    Layout.fillWidth: true
                                    from: 1; to: 8; stepSize: 1
                                    value: root.maxConcurrent
                                    onValueChanged: root.maxConcurrent = value
                                }
                                SpinBox {
                                    from: 1; to: 8
                                    value: root.maxConcurrent
                                    onValueModified: root.maxConcurrent = value
                                }
                            }
                        }

                        // Conflict Policy
                        SettingsRow {
                            Layout.fillWidth: true
                            label: qsTr("File Conflict Policy")
                            hint: qsTr("Behavior when a file with the same name exists")

                            RowLayout {
                                spacing: 8
                                Layout.maximumWidth: 360

                                Repeater {
                                    model: [
                                        { key: "rename",    label: qsTr("Rename") },
                                        { key: "skip",      label: qsTr("Skip") },
                                        { key: "overwrite", label: qsTr("Overwrite") }
                                    ]

                                    delegate: Rectangle {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 40
                                        radius: Theme.rMD
                                        color: root.conflictPolicy === modelData.key ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.08) : Theme.glassBg
                                        border.width: root.conflictPolicy === modelData.key ? 2 : 1
                                        border.color: root.conflictPolicy === modelData.key ? Theme.accent : Theme.glassBorder

                                        Text {
                                            anchors.centerIn: parent
                                            text: modelData.label
                                            color: root.conflictPolicy === modelData.key ? Theme.accent : Theme.textMute
                                            font.pixelSize: Theme.fsSmall
                                            font.weight: Font.DemiBold
                                        }

                                        MouseArea {
                                            anchors.fill: parent
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: root.conflictPolicy = modelData.key
                                        }
                                    }
                                }
                            }
                        }

                        // Filename Pattern
                        SettingsRow {
                            Layout.fillWidth: true
                            label: qsTr("Default Filename Pattern")
                            hint: qsTr("Template used when no custom name is given")

                            RowLayout {
                                spacing: 6
                                Layout.maximumWidth: 480

                                Input {
                                    Layout.fillWidth: true
                                    text: root.filenamePattern
                                    font.family: Theme.fontMono
                                    font.pixelSize: Theme.fsMicro
                                    onTextEdited: root.filenamePattern = text
                                }
                                Button { text: "📋"; variant: "default"; implicitWidth: 32; implicitHeight: 32 }
                            }
                        }

                        // YouTube Quality
                        SettingsRow {
                            Layout.fillWidth: true
                            label: qsTr("YouTube Quality")
                            hint: qsTr("Preferred video resolution")

                            ComboBox {
                                id: ytCombo
                                model: ["2160p", "1440p", "1080p", "720p", "480p", qsTr("Best Available")]
                                implicitWidth: 200
                                currentIndex: 5

                                background: Rectangle {
                                    color: Theme.inputBg
                                    border.width: 1
                                    border.color: ytCombo.activeFocus ? Theme.accent : Theme.glassBorder
                                    radius: Theme.rMD
                                }
                                contentItem: Text {
                                    text: ytCombo.displayText
                                    color: Theme.textPrimary
                                    font.pixelSize: Theme.fsSmall
                                    verticalAlignment: Text.AlignVCenter
                                    leftPadding: 10
                                }
                            }
                        }

                        // Auto-merge
                        SettingsRow {
                            Layout.fillWidth: true
                            label: qsTr("Auto-merge Video+Audio")
                            hint: qsTr("YouTube: automatically merge video and audio streams")
                            Toggle { checked: root.autoMerge; onToggled: root.autoMerge = checked }
                        }

                        // Resume on Restart
                        SettingsRow {
                            Layout.fillWidth: true
                            label: qsTr("Resume on Restart")
                            hint: qsTr("Resume interrupted downloads when app restarts")
                            Toggle { checked: root.resumeOnRestart; onToggled: root.resumeOnRestart = checked }
                        }
                    }
                }

                // ===== GROUP 3: COOKIE & API =====
                GlassCard {
                    Layout.fillWidth: true
                    padding: 24
                    visible: root.activeSection === "cookie"

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 0

                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.bottomMargin: 16
                            spacing: 2

                            RowLayout {
                                spacing: 10
                                Text {
                                    text: "🔗"
                                    color: Theme.accent
                                    font.pixelSize: 18
                                }
                                Text {
                                    text: qsTr("Cookie & API Credentials")
                                    color: Theme.textPrimary
                                    font.pixelSize: Theme.fsH2
                                    font.weight: Font.Bold
                                }
                            }
                            Text {
                                text: qsTr("Platform authentication")
                                color: Theme.textMute
                                font.pixelSize: Theme.fsSmall
                            }
                        }

                        // Collapsible header
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 56
                            radius: Theme.rMD
                            color: Theme.glassBg
                            border.width: 1
                            border.color: Theme.glassBorder

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 14
                                anchors.rightMargin: 14
                                spacing: 12

                                Rectangle {
                                    Layout.preferredWidth: 32
                                    Layout.preferredHeight: 32
                                    radius: Theme.rSM
                                    color: Theme.glassBgHi
                                    border.width: 1
                                    border.color: Theme.glassBorder

                                    Text {
                                        anchors.centerIn: parent
                                        text: "🔗"
                                        font.pixelSize: 14
                                    }
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 0
                                    Text {
                                        text: qsTr("Cookie & API Credentials")
                                        color: Theme.textPrimary
                                        font.pixelSize: Theme.fsBody
                                        font.weight: Font.DemiBold
                                    }
                                    Text {
                                        text: qsTr("Manage platform authentication tokens")
                                        color: Theme.textMute
                                        font.pixelSize: 10
                                    }
                                }

                                // Configured badge
                                Rectangle {
                                    Layout.preferredWidth: 90
                                    Layout.preferredHeight: 22
                                    radius: Theme.rPill
                                    color: Qt.rgba(Theme.success.r, Theme.success.g, Theme.success.b, 0.12)
                                    border.width: 1
                                    border.color: Qt.rgba(Theme.success.r, Theme.success.g, Theme.success.b, 0.3)

                                    Text {
                                        anchors.centerIn: parent
                                        text: "3 " + qsTr("configured")
                                        color: Theme.success
                                        font.pixelSize: 10
                                        font.family: Theme.fontMono
                                        font.weight: Font.DemiBold
                                    }
                                }

                                Text {
                                    text: root.cookieApiExpanded ? "▾" : "▸"
                                    color: Theme.textMute
                                    font.pixelSize: 14
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.cookieApiExpanded = !root.cookieApiExpanded
                            }
                        }

                        // Collapsible body
                        ColumnLayout {
                            Layout.fillWidth: true
                            visible: root.cookieApiExpanded
                            spacing: 0

                            Repeater {
                                model: root.credentials

                                delegate: Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 64
                                    color: "transparent"

                                    Rectangle {
                                        anchors.top: parent.top
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        height: 1
                                        color: Theme.glassBorder
                                    }

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 14
                                        anchors.rightMargin: 14
                                        spacing: 12

                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 2

                                            Text {
                                                text: modelData.name
                                                color: Theme.textPrimary
                                                font.pixelSize: Theme.fsBody
                                                font.weight: Font.DemiBold
                                            }

                                            Row {
                                                spacing: 4

                                                Text {
                                                    text: modelData.state === "success" ? "✓"
                                                          : (modelData.state === "warning" ? "⚠" : "⏱")
                                                    color: modelData.state === "success" ? Theme.success
                                                           : (modelData.state === "warning" ? Theme.warning : Theme.textDim)
                                                    font.pixelSize: 10
                                                    anchors.verticalCenter: parent.verticalCenter
                                                }

                                                Text {
                                                    text: modelData.status
                                                    color: modelData.state === "success" ? Theme.success
                                                           : (modelData.state === "warning" ? Theme.warning : Theme.textDim)
                                                    font.pixelSize: 10
                                                    font.family: Theme.fontMono
                                                    anchors.verticalCenter: parent.verticalCenter
                                                }
                                            }
                                        }

                                        Row {
                                            spacing: 4

                                            Repeater {
                                                model: modelData.actions

                                                delegate: Button {
                                                    text: {
                                                        if (modelData === "import")    return qsTr("Import")
                                                        if (modelData === "validate")  return qsTr("Validate")
                                                        if (modelData === "clear")     return qsTr("Clear")
                                                        if (modelData === "edit")      return qsTr("Edit")
                                                        if (modelData === "test")      return qsTr("Test")
                                                        if (modelData === "configure") return qsTr("Configure")
                                                        return ""
                                                    }
                                                    variant: modelData === "clear" ? "danger"
                                                            : (modelData === "configure" ? "primary" : "default")
                                                    implicitHeight: 28
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // ===== GROUP 4: CACHE =====
                GlassCard {
                    Layout.fillWidth: true
                    padding: 24
                    visible: root.activeSection === "cache"

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 16

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2

                            RowLayout {
                                spacing: 10
                                Text {
                                    text: "📁"
                                    color: Theme.accent
                                    font.pixelSize: 18
                                }
                                Text {
                                    text: qsTr("Cache Management")
                                    color: Theme.textPrimary
                                    font.pixelSize: Theme.fsH2
                                    font.weight: Font.Bold
                                }
                            }
                            Text {
                                text: qsTr("Storage cleanup and cache policies")
                                color: Theme.textMute
                                font.pixelSize: Theme.fsSmall
                            }
                        }

                        // Cache grid 2x2
                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2
                            columnSpacing: 12
                            rowSpacing: 12

                            Repeater {
                                model: root.cacheInfos

                                delegate: GlassCard {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 110
                                    padding: 14

                                    ColumnLayout {
                                        anchors.fill: parent
                                        spacing: 6

                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 8

                                            Text {
                                                text: modelData.icon + " " + modelData.name
                                                color: Theme.textPrimary
                                                font.pixelSize: Theme.fsSmall
                                                font.weight: Font.DemiBold
                                                Layout.fillWidth: true
                                            }

                                            Button {
                                                text: qsTr("Clean Now")
                                                variant: "default"
                                                implicitHeight: 26
                                            }
                                        }

                                        Text {
                                            text: modelData.size + " <span style='color:gray'>" + modelData.unit + "</span>"
                                            color: Theme.textPrimary
                                            font.family: Theme.fontMono
                                            font.pixelSize: 24
                                            font.weight: Font.Bold
                                            textFormat: Text.RichText
                                            Layout.fillWidth: true
                                        }

                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 8
                                            Text {
                                                text: modelData.files + " " + qsTr("files")
                                                color: Theme.textMute
                                                font.pixelSize: 10
                                                font.family: Theme.fontMono
                                            }
                                            Text {
                                                text: modelData.path
                                                color: Theme.textDim
                                                font.pixelSize: 10
                                                font.family: Theme.fontMono
                                                Layout.fillWidth: true
                                                elide: Text.ElideRight
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // Auto Clean Mode
                        SettingsRow {
                            Layout.fillWidth: true
                            label: qsTr("Auto Clean Mode")
                            hint: qsTr("When to automatically clean caches")

                            ComboBox {
                                id: cleanCombo
                                model: [qsTr("Off"), qsTr("On Startup"), qsTr("Daily"), qsTr("Weekly")]
                                implicitWidth: 200
                                currentIndex: 1

                                background: Rectangle {
                                    color: Theme.inputBg
                                    border.width: 1
                                    border.color: cleanCombo.activeFocus ? Theme.accent : Theme.glassBorder
                                    radius: Theme.rMD
                                }
                                contentItem: Text {
                                    text: cleanCombo.displayText
                                    color: Theme.textPrimary
                                    font.pixelSize: Theme.fsSmall
                                    verticalAlignment: Text.AlignVCenter
                                    leftPadding: 10
                                }
                            }
                        }

                        // Retention Days
                        SettingsRow {
                            Layout.fillWidth: true
                            label: qsTr("Retention Days")
                            hint: qsTr("Delete files older than N days")

                            RowLayout {
                                spacing: 8
                                Layout.maximumWidth: 280

                                Slider {
                                    Layout.fillWidth: true
                                    from: 1; to: 90; stepSize: 1
                                    value: root.retentionDays
                                    onValueChanged: root.retentionDays = value
                                }
                                SpinBox {
                                    from: 1; to: 90
                                    value: root.retentionDays
                                    onValueModified: root.retentionDays = value
                                }
                                Text {
                                    text: qsTr("days")
                                    color: Theme.textMute
                                    font.pixelSize: Theme.fsMicro
                                }
                            }
                        }

                        // Max Size per Directory
                        SettingsRow {
                            Layout.fillWidth: true
                            label: qsTr("Max Size per Directory")
                            hint: qsTr("Upper limit before oldest files are removed")

                            RowLayout {
                                spacing: 8
                                Layout.maximumWidth: 200

                                SpinBox {
                                    from: 50; to: 5000
                                    value: root.maxSizePerDir
                                    onValueModified: root.maxSizePerDir = value
                                }
                                Text {
                                    text: "MB"
                                    color: Theme.textMute
                                    font.pixelSize: Theme.fsMicro
                                }
                            }
                        }

                        // Clean All Caches button
                        RowLayout {
                            Layout.fillWidth: true

                            Item { Layout.fillWidth: true }
                            Button {
                                text: "🗑 " + qsTr("Clean All Caches")
                                variant: "danger"
                            }
                        }
                    }
                }

                // ===== GROUP 5: ABOUT =====
                GlassCard {
                    Layout.fillWidth: true
                    padding: 24
                    visible: root.activeSection === "about"

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 16

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2

                            RowLayout {
                                spacing: 10
                                Text {
                                    text: "ⓘ"
                                    color: Theme.accent
                                    font.pixelSize: 18
                                }
                                Text {
                                    text: qsTr("About")
                                    color: Theme.textPrimary
                                    font.pixelSize: Theme.fsH2
                                    font.weight: Font.Bold
                                }
                            }
                            Text {
                                text: qsTr("Application information")
                                color: Theme.textMute
                                font.pixelSize: Theme.fsSmall
                            }
                        }

                        // Logo + version
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignHCenter
                            spacing: 8

                            Rectangle {
                                Layout.alignment: Qt.AlignHCenter
                                Layout.preferredWidth: 64
                                Layout.preferredHeight: 64
                                radius: Theme.rLG
                                gradient: Gradient {
                                    orientation: Gradient.Vertical
                                    GradientStop { position: 0.0; color: Theme.accent }
                                    GradientStop { position: 1.0; color: Theme.accent2 }
                                }

                                Text {
                                    anchors.centerIn: parent
                                    text: "L"
                                    color: "white"
                                    font.pixelSize: 36
                                    font.weight: Font.Bold
                                    font.family: Theme.fontDisplay
                                }
                            }

                            Text {
                                Layout.alignment: Qt.AlignHCenter
                                text: "v4.2.0"
                                color: Theme.textPrimary
                                font.family: Theme.fontMono
                                font.pixelSize: Theme.fsH2
                                font.weight: Font.Bold
                            }

                            Text {
                                Layout.alignment: Qt.AlignHCenter
                                text: qsTr("Personal media downloader for YouTube, Instagram, X, and Chinese platforms")
                                color: Theme.textMute
                                font.pixelSize: Theme.fsSmall
                                horizontalAlignment: Text.AlignHCenter
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }

                        // Tech badges
                        Row {
                            Layout.alignment: Qt.AlignHCenter
                            spacing: 6

                            Repeater {
                                model: ["PySide6", "yt-dlp", "Flask", "SQLAlchemy", "Pillow"]
                                delegate: Badge {
                                    badgeType: "default"
                                    text: modelData
                                }
                            }
                        }

                        // Action buttons
                        Row {
                            Layout.alignment: Qt.AlignHCenter
                            spacing: 6

                            Button { text: qsTr("GitHub Repo");    variant: "default" }
                            Button { text: qsTr("Report Issue");    variant: "default" }
                            Button { text: qsTr("Changelog");       variant: "default" }
                            Button { text: qsTr("License");         variant: "default" }
                            Button { text: qsTr("Check for Updates"); variant: "primary" }
                        }
                    }
                }
            }
        }
    }

    // ============================================================
    // 通用组件：设置行
    // ============================================================
    component SettingsRow : ColumnLayout {
        property string label: ""
        property string hint: ""

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.glassBorder
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 12
            Layout.bottomMargin: 12
            spacing: 16

            ColumnLayout {
                Layout.preferredWidth: 220
                Layout.maximumWidth: 220
                spacing: 2

                Text {
                    text: parent.parent.parent.label
                    color: Theme.textPrimary
                    font.pixelSize: Theme.fsBody
                    font.weight: Font.DemiBold
                }

                Text {
                    text: parent.parent.parent.hint
                    color: Theme.textMute
                    font.pixelSize: 10
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }

            Item { Layout.fillWidth: true }

            // Control slot — set by user via children
            RowLayout {
                Layout.alignment: Qt.AlignRight
                spacing: 6
            }
        }
    }
}
