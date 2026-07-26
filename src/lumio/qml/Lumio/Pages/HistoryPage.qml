// ============================================================
// LUMIO // HistoryPage — 历史记录页
// ------------------------------------------------------------
// 真实对接 controller:
//   - getHistoryJson() → 记录列表
//   - deleteHistory(record_id) / clearHistory()
//   - openFile(path) / openFolder(path)
//   - historyChanged 信号 → 刷新
// 客户端搜索/平台筛选（数据量小）
// ============================================================
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import Lumio
import Lumio.Components

Item {
    id: root

    property var records: []
    property string searchText: ""
    property string filterPlatform: "all"

    Connections {
        target: typeof controller !== "undefined" ? controller : null
        function onHistoryChanged() { _reload() }
        // 文件缺失（被外部删除）→ 弹「是否删除本条记录」对话框
        function onFileMissing(path, source) {
            if (source !== "history") return
            _fileMissingDialog._missingPath = path
            _fileMissingDialog._missingRecordId = _findRecordIdByPath(path)
            _fileMissingDialog.open()
        }
    }

    Component.onCompleted: _reload()

    // 按 file_path 反查 record_id
    function _findRecordIdByPath(path) {
        for (var i = 0; i < root.records.length; i++) {
            if (root.records[i].file_path === path) return root.records[i].record_id
        }
        return ""
    }

    function _reload() {
        if (typeof controller === "undefined" || !controller) return
        try {
            var json = controller.getHistoryJson()
            root.records = JSON.parse(json)
            _applyFilter()
        } catch (e) {
            console.log("[HistoryPage] reload failed:", e)
        }
    }

    function _applyFilter() {
        var arr = root.records
        var q = root.searchText.toLowerCase()
        var fp = root.filterPlatform
        var out = []
        for (var i = 0; i < arr.length; i++) {
            var r = arr[i]
            if (fp !== "all" && r.platform !== fp) continue
            if (q.length > 0) {
                var hay = ((r.title || "") + " " + (r.author || "") + " " + (r.url || "") + " " + (r.file_path || "")).toLowerCase()
                if (hay.indexOf(q) < 0) continue
            }
            out.push(r)
        }
        _list.model = out
    }

    function _formatSize(bytes) {
        if (!bytes || bytes <= 0) return "—"
        if (bytes < 1024) return bytes + " B"
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB"
        if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB"
        return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB"
    }

    function _formatTime(t) {
        if (!t || t.length === 0) return "—"
        return t.replace("T", " ").substring(0, 19)
    }

    function _confirmClear() {
        _confirmDialog.visible = true
    }

    ScrollView {
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            width: parent.width
            spacing: 16

            // ============================================================
            // 视觉中心：PageHeader
            // ============================================================
            PageHeader {
                Layout.fillWidth: true
                Layout.leftMargin: 32
                Layout.rightMargin: 32
                Layout.topMargin: 24
                title: tr("history_page")
                subtitle: tr("history_subtitle")
                icon: "i-history"

                // 右侧操作区
                Rectangle {
                    width: _countText.implicitWidth + 20
                    height: 22
                    radius: Theme.rPill
                    color: Qt.rgba(10/255, 132/255, 1, 0.12)
                    border.width: 1
                    border.color: Qt.rgba(10/255, 132/255, 1, 0.3)

                    Text {
                        id: _countText
                        anchors.centerIn: parent
                        text: root.records.length + " " + tr("items")
                        color: Theme.accent
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fsMicro
                        font.weight: Font.DemiBold
                    }
                }

                Button {
                    text: tr("history_clear")
                    variant: "danger"
                    iconName: "i-trash"
                    enabled: root.records.length > 0
                    onClicked: _confirmClear()
                }
            }

            // Filter bar
            GlassCard {
                Layout.fillWidth: true
                Layout.leftMargin: 48
                Layout.rightMargin: 48
                Layout.preferredHeight: 48
                radius: Theme.rMD

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    anchors.rightMargin: 14
                    spacing: 10

                    Input {
                        Layout.fillWidth: true
                        placeholderText: tr("search_placeholder")
                        text: root.searchText
                        onTextChanged: { root.searchText = text; _applyFilter() }
                    }

                    LumioComboBox {
                        Layout.preferredWidth: 180
                        currentIndex: 0
                        model: [
                            { value: "all",         label: tr("all_platforms") },
                            { value: "youtube",     label: "YouTube" },
                            { value: "instagram",   label: "Instagram" },
                            { value: "x",           label: "X" },
                            { value: "bilibili",    label: tr("platform_bilibili") },
                            { value: "douyin",      label: tr("platform_douyin") },
                            { value: "kuaishou",    label: tr("platform_kuaishou") },
                            { value: "weibo",       label: tr("platform_weibo") },
                            { value: "xiaohongshu", label: tr("platform_xiaohongshu") }
                        ]
                        textRole: "label"
                        valueRole: "value"
                        onActivated: { root.filterPlatform = currentValue; _applyFilter() }
                    }
                }
            }

            // 空状态
            Text {
                visible: root.records.length === 0
                Layout.fillWidth: true
                Layout.topMargin: 80
                text: tr("no_history")
                color: Theme.textMute
                font.family: Theme.fontBody
                font.pixelSize: Theme.fsBody
                horizontalAlignment: Text.AlignHCenter
            }

            // 记录列表
            Repeater {
                id: _list
                model: []

                delegate: GlassCard {
                    Layout.fillWidth: true
                    Layout.leftMargin: 48
                    Layout.rightMargin: 48
                    Layout.preferredHeight: 90
                    radius: Theme.rLG

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 14
                        spacing: 14

                        // Thumbnail / platform icon
                        Rectangle {
                            Layout.preferredWidth: 62
                            Layout.preferredHeight: 62
                            radius: Theme.rMD
                            color: Qt.rgba(0, 0, 0, 0.3)
                            border.width: 1
                            border.color: Theme.glassBorder
                            clip: true

                            Image {
                                anchors.fill: parent
                                source: modelData.thumbnail_url && modelData.thumbnail_url.length > 0
                                        ? (typeof controller !== "undefined" && controller
                                           ? controller.thumbUrl(modelData.thumbnail_url)
                                           : modelData.thumbnail_url)
                                        : ""
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                                visible: modelData.thumbnail_url && modelData.thumbnail_url.length > 0
                            }

                            Icon {
                                anchors.centerIn: parent
                                name: "i-history"
                                size: 22
                                color: Theme.platformColor(modelData.platform)
                                visible: !(modelData.thumbnail_url && modelData.thumbnail_url.length > 0)
                            }
                        }

                        // Info
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4

                            Text {
                                text: modelData.title || modelData.url
                                color: Theme.textPrimary
                                font.family: Theme.fontDisplay
                                font.pixelSize: Theme.fsBody
                                font.weight: Font.DemiBold
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }

                            Text {
                                text: (modelData.author || "") + " · "
                                      + Theme.platformLabel(modelData.platform) + " · "
                                      + _formatSize(modelData.file_size) + " · "
                                      + _formatTime(modelData.download_time)
                                color: Theme.textMute
                                font.family: Theme.fontMono
                                font.pixelSize: Theme.fsSmall
                            }
                        }

                        // Status badge
                        Badge {
                            text: modelData.success ? tr("status_completed") : tr("status_failed")
                            status: modelData.success ? "completed" : "failed"
                        }

                        // Actions
                        Row {
                            spacing: 4

                            Button {
                                iconName: "i-play"; variant: "ghost"; iconSize: 16
                                enabled: modelData.file_path && modelData.file_path.length > 0
                                onClicked: {
                                    if (controller) controller.openFileFromSource(modelData.file_path, "history")
                                }
                            }
                            Button {
                                iconName: "i-folder"; variant: "ghost"; iconSize: 16
                                enabled: modelData.file_path && modelData.file_path.length > 0
                                onClicked: {
                                    if (controller) controller.openFolderFromSource(modelData.file_path, "history")
                                }
                            }
                            Button {
                                iconName: "i-trash"; variant: "ghost"; iconSize: 16
                                onClicked: {
                                    if (controller) controller.deleteHistory(modelData.record_id)
                                }
                            }
                        }
                    }
                }
            }

            Item { Layout.preferredHeight: 48 }
        }
    }

    // 清空确认对话框
    Dialog {
        id: _confirmDialog
        visible: false
        modal: true
        anchors.centerIn: parent
        title: tr("history_clear")
        width: 360

        // 自定义深色背景，匹配整体 UI 风格（避免原生白底）
        background: Rectangle {
            radius: Theme.rLG
            color: Theme.theme === "dark" ? Qt.rgba(20/255, 22/255, 38/255, 0.98)
                                          : Qt.rgba(255/255, 255/255, 255/255, 0.98)
            border.width: 1
            border.color: Theme.glassBorderHi
            layer.enabled: true
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: Qt.rgba(0, 0, 0, 0.4)
                shadowBlur: 0.8
                shadowVerticalOffset: 8
            }
        }

        contentItem: ColumnLayout {
            spacing: 14
            Text {
                text: tr("history_confirm_clear")
                color: Theme.textPrimary
                font.family: Theme.fontBody
                font.pixelSize: Theme.fsBody
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Item { Layout.fillWidth: true }
                Button {
                    text: tr("cancel")
                    variant: "ghost"
                    onClicked: _confirmDialog.visible = false
                }
                Button {
                    text: tr("clear")
                    variant: "danger"
                    onClicked: {
                        if (controller) controller.clearHistory()
                        _confirmDialog.visible = false
                    }
                }
            }
        }
    }

    // 文件缺失确认对话框（文件被外部删除后弹此）
    Dialog {
        id: _fileMissingDialog
        visible: false
        modal: true
        anchors.centerIn: parent
        width: 420

        property string _missingPath: ""
        property string _missingRecordId: ""

        background: Rectangle {
            radius: Theme.rLG
            color: Theme.theme === "dark" ? Qt.rgba(20/255, 22/255, 38/255, 0.98)
                                          : Qt.rgba(255/255, 255/255, 255/255, 0.98)
            border.width: 1
            border.color: Theme.glassBorderHi
            layer.enabled: true
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: Qt.rgba(0, 0, 0, 0.4)
                shadowBlur: 0.8
                shadowVerticalOffset: 8
            }
        }

        contentItem: ColumnLayout {
            spacing: 12
            Text {
                text: tr("file_missing_title")
                color: Theme.danger
                font.family: Theme.fontDisplay
                font.pixelSize: 15
                font.weight: Font.DemiBold
                Layout.fillWidth: true
            }
            Text {
                text: tr("file_missing_msg")
                color: Theme.textPrimary
                font.pixelSize: 12
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            Text {
                text: _fileMissingDialog._missingPath
                color: Theme.textDim
                font.family: Theme.fontMono
                font.pixelSize: 10
                wrapMode: Text.WrapAnywhere
                Layout.fillWidth: true
                Layout.leftMargin: 8
                Layout.rightMargin: 8
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Item { Layout.fillWidth: true }
                Button {
                    text: tr("cancel"); variant: "ghost"
                    onClicked: _fileMissingDialog.visible = false
                }
                Button {
                    text: tr("file_missing_delete"); variant: "danger"
                    enabled: _fileMissingDialog._missingRecordId.length > 0
                    onClicked: {
                        if (controller && _fileMissingDialog._missingRecordId.length > 0) {
                            controller.deleteHistory(_fileMissingDialog._missingRecordId)
                        }
                        _fileMissingDialog.visible = false
                    }
                }
            }
        }
    }
}
