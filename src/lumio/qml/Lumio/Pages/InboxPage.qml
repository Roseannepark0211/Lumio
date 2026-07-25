// ============================================================
// LUMIO // InboxPage — 收件箱页
// ------------------------------------------------------------
// 真实对接 controller:
//   - getInboxJson() → 收件箱列表
//   - inboxDownload(item_id) / inboxBatchDownload(ids_json)
//   - inboxArchive(item_id) / inboxDelete(item_id) / inboxBatchDelete(ids_json)
//   - inboxClearCompleted() / openExternalUrl(url)
//   - inboxChanged 信号 → 刷新
// 客户端状态/来源筛选
// ============================================================
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import Lumio
import Lumio.Components

Item {
    id: root

    property var items: []
    property var selectedIds: []
    property string filterStatus: "all"   // all / new / queued / downloaded / archived / failed
    property string filterSource: "all"   // all / browser / telegram / manual
    property bool selectMode: false

    Connections {
        target: typeof controller !== "undefined" ? controller : null
        function onInboxChanged() { _reload() }
    }

    Component.onCompleted: _reload()

    function _reload() {
        if (typeof controller === "undefined" || !controller) return
        try {
            var json = controller.getInboxJson()
            root.items = JSON.parse(json)
            _applyFilter()
        } catch (e) {
            console.log("[InboxPage] reload failed:", e)
        }
    }

    function _applyFilter() {
        var arr = root.items
        var fs = root.filterStatus
        var fsrc = root.filterSource
        var out = []
        for (var i = 0; i < arr.length; i++) {
            var it = arr[i]
            if (fs !== "all" && it.status !== fs) continue
            if (fsrc !== "all" && it.source !== fsrc) continue
            out.push(it)
        }
        _list.model = out
        _updateCounters()
    }

    function _updateCounters() {
        var newCount = 0
        for (var i = 0; i < root.items.length; i++) {
            if (root.items[i].status === "new") newCount++
        }
        _badgeText.text = newCount + " " + tr("inbox_status_new") + " · "
                          + root.items.length + " " + tr("items")
    }

    function _formatTime(t) {
        if (!t || t.length === 0) return "—"
        return t.replace("T", " ").substring(0, 19)
    }

    function _sourceLabel(s) {
        if (s === "browser")  return tr("inbox_source_browser")
        if (s === "telegram") return tr("inbox_source_telegram")
        if (s === "manual")   return tr("inbox_source_manual")
        return s || "—"
    }

    function _statusLabel(s) {
        if (s === "new")        return tr("inbox_status_new")
        if (s === "queued")     return tr("inbox_status_queued")
        if (s === "downloaded") return tr("inbox_status_downloaded")
        if (s === "archived")   return tr("inbox_status_archived")
        if (s === "failed")     return tr("inbox_status_failed")
        return s
    }

    function _toggleSelect(id) {
        var idx = root.selectedIds.indexOf(id)
        var arr = root.selectedIds.slice()
        if (idx >= 0) arr.splice(idx, 1)
        else arr.push(id)
        root.selectedIds = arr
    }

    function _selectAll() {
        var arr = []
        var model = _list.model
        for (var i = 0; i < model.length; i++) arr.push(model[i].id)
        root.selectedIds = arr
    }

    function _deselectAll() {
        root.selectedIds = []
    }

    function _batchDownload() {
        if (root.selectedIds.length === 0) return
        if (controller) controller.inboxBatchDownload(JSON.stringify(root.selectedIds))
        root.selectedIds = []
        root.selectMode = false
    }

    function _batchDelete() {
        if (root.selectedIds.length === 0) return
        _deleteDialog.ids = root.selectedIds.slice()
        _deleteDialog.visible = true
    }

    function _confirmClearCompleted() {
        _clearDialog.visible = true
    }

    ScrollView {
        anchors.fill: parent
        clip: true

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
                title: tr("inbox_page")
                subtitle: tr("inbox_subtitle")
                icon: "i-inbox"

                // 右侧操作区
                Rectangle {
                    width: _badgeText.implicitWidth + 20
                    height: 22
                    radius: Theme.rPill
                    color: Qt.rgba(10/255, 132/255, 1, 0.12)
                    border.width: 1
                    border.color: Qt.rgba(10/255, 132/255, 1, 0.3)

                    Text {
                        id: _badgeText
                        anchors.centerIn: parent
                        text: "0 " + tr("inbox_status_new") + " · 0 " + tr("items")
                        color: Theme.accent
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fsMicro
                        font.weight: Font.DemiBold
                    }
                }

                Button {
                    text: tr("inbox_refresh")
                    variant: "default"
                    iconName: "i-refresh"
                    onClicked: _reload()
                }

                Button {
                    text: root.selectMode ? tr("library_batch_cancel") : tr("library_batch_select")
                    variant: "default"
                    iconName: root.selectMode ? "i-close" : "i-check"
                    onClicked: {
                        root.selectMode = !root.selectMode
                        if (!root.selectMode) root.selectedIds = []
                    }
                }

                Button {
                    text: tr("inbox_clear_completed")
                    variant: "ghost"
                    iconName: "i-trash"
                    enabled: root.items.length > 0
                    onClicked: _confirmClearCompleted()
                }
            }

            // 批量操作栏（仅 selectMode 显示）
            GlassCard {
                Layout.fillWidth: true
                Layout.leftMargin: 48
                Layout.rightMargin: 48
                Layout.preferredHeight: 48
                radius: Theme.rMD
                visible: root.selectMode

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    anchors.rightMargin: 14
                    spacing: 10

                    Text {
                        text: root.selectedIds.length > 0
                              ? tr("library_batch_selected").replace("{n}", root.selectedIds.length)
                              : tr("library_batch_select")
                        color: Theme.textMute
                        font.family: Theme.fontBody
                        font.pixelSize: Theme.fsSmall
                    }

                    Item { Layout.fillWidth: true }

                    Button {
                        text: tr("library_batch_select_all")
                        variant: "ghost"
                        onClicked: _selectAll()
                    }
                    Button {
                        text: tr("library_batch_deselect_all")
                        variant: "ghost"
                        onClicked: _deselectAll()
                    }
                    Button {
                        text: tr("inbox_download_selected")
                        variant: "primary"
                        iconName: "i-download"
                        enabled: root.selectedIds.length > 0
                        onClicked: _batchDownload()
                    }
                    Button {
                        text: tr("inbox_delete_selected")
                        variant: "danger"
                        iconName: "i-trash"
                        enabled: root.selectedIds.length > 0
                        onClicked: _batchDelete()
                    }
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

                    Text {
                        text: tr("inbox_filter_all")
                        color: Theme.textMute
                        font.family: Theme.fontBody
                        font.pixelSize: Theme.fsSmall
                    }

                    LumioComboBox {
                        Layout.preferredWidth: 160
                        currentIndex: 0
                        model: [
                            { value: "all",        label: tr("inbox_filter_all") },
                            { value: "new",        label: tr("inbox_status_new") },
                            { value: "queued",     label: tr("inbox_status_queued") },
                            { value: "downloaded", label: tr("inbox_status_downloaded") },
                            { value: "archived",   label: tr("inbox_status_archived") },
                            { value: "failed",     label: tr("inbox_status_failed") }
                        ]
                        textRole: "label"
                        valueRole: "value"
                        onActivated: { root.filterStatus = currentValue; _applyFilter() }
                    }

                    Item { Layout.fillWidth: true }

                    Text {
                        text: tr("inbox_source_browser")
                        color: Theme.textMute
                        font.family: Theme.fontBody
                        font.pixelSize: Theme.fsSmall
                    }

                    LumioComboBox {
                        Layout.preferredWidth: 140
                        currentIndex: 0
                        model: [
                            { value: "all",      label: tr("inbox_filter_all") },
                            { value: "browser",  label: tr("inbox_source_browser") },
                            { value: "telegram", label: tr("inbox_source_telegram") },
                            { value: "manual",   label: tr("inbox_source_manual") }
                        ]
                        textRole: "label"
                        valueRole: "value"
                        onActivated: { root.filterSource = currentValue; _applyFilter() }
                    }
                }
            }

            // 空状态
            Text {
                visible: root.items.length === 0
                Layout.fillWidth: true
                Layout.topMargin: 80
                text: tr("no_inbox_items")
                color: Theme.textMute
                font.family: Theme.fontBody
                font.pixelSize: Theme.fsBody
                horizontalAlignment: Text.AlignHCenter
            }

            // 收件箱列表
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

                        // 选择框（仅 selectMode 显示）
                        Rectangle {
                            visible: root.selectMode
                            Layout.preferredWidth: 22
                            Layout.preferredHeight: 22
                            radius: 6
                            color: root.selectedIds.indexOf(modelData.id) >= 0
                                   ? Theme.accent : "transparent"
                            border.width: 1
                            border.color: root.selectedIds.indexOf(modelData.id) >= 0
                                          ? Theme.accent : Theme.glassBorderHi
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: _toggleSelect(modelData.id)
                            }
                            Icon {
                                anchors.centerIn: parent
                                name: "i-check"
                                size: 14
                                color: "#ffffff"
                                visible: root.selectedIds.indexOf(modelData.id) >= 0
                            }
                        }

                        // 缩略图
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
                                name: modelData.type === "image" ? "i-image" : "i-play"
                                size: 22
                                color: Theme.platformColor(modelData.platform)
                                visible: !(modelData.thumbnail_url && modelData.thumbnail_url.length > 0)
                            }
                        }

                        // 信息
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
                                text: (modelData.author || "—") + " · "
                                      + (modelData.platform || "").toUpperCase() + " · "
                                      + _sourceLabel(modelData.source) + " · "
                                      + _formatTime(modelData.captured_at)
                                color: Theme.textMute
                                font.family: Theme.fontMono
                                font.pixelSize: Theme.fsSmall
                            }
                        }

                        // 状态徽章
                        Badge {
                            text: _statusLabel(modelData.status)
                            status: modelData.status === "downloaded" ? "completed"
                                  : modelData.status === "failed" ? "failed"
                                  : modelData.status === "queued" ? "waiting"
                                  : modelData.status === "archived" ? "paused"
                                  : "downloading"
                        }

                        // 操作
                        Row {
                            spacing: 4

                            Button {
                                iconName: "i-download"; variant: "ghost"; iconSize: 16
                                enabled: modelData.status === "new" || modelData.status === "failed"
                                onClicked: { if (controller) controller.inboxDownload(modelData.id) }
                            }
                            Button {
                                iconName: "i-external"; variant: "ghost"; iconSize: 16
                                enabled: modelData.url && modelData.url.length > 0
                                onClicked: { if (controller) controller.openExternalUrl(modelData.url) }
                            }
                            Button {
                                iconName: "i-archive"; variant: "ghost"; iconSize: 16
                                enabled: modelData.status !== "archived"
                                onClicked: { if (controller) controller.inboxArchive(modelData.id) }
                            }
                            Button {
                                iconName: "i-trash"; variant: "ghost"; iconSize: 16
                                onClicked: {
                                    _deleteDialog.ids = [modelData.id]
                                    _deleteDialog.visible = true
                                }
                            }
                        }
                    }
                }
            }

            Item { Layout.preferredHeight: 48 }
        }
    }

    // 删除确认
    Dialog {
        id: _deleteDialog
        visible: false
        modal: true
        anchors.centerIn: parent
        title: tr("inbox_delete")
        width: 360
        property var ids: []

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
                text: tr("inbox_confirm_delete").replace("{n}", _deleteDialog.ids.length)
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
                    text: tr("cancel"); variant: "ghost"
                    onClicked: _deleteDialog.visible = false
                }
                Button {
                    text: tr("delete"); variant: "danger"
                    onClicked: {
                        if (controller) {
                            if (_deleteDialog.ids.length === 1) {
                                controller.inboxDelete(_deleteDialog.ids[0])
                            } else {
                                controller.inboxBatchDelete(JSON.stringify(_deleteDialog.ids))
                            }
                        }
                        _deleteDialog.visible = false
                        root.selectedIds = []
                    }
                }
            }
        }
    }

    // 清空已完成确认
    Dialog {
        id: _clearDialog
        visible: false
        modal: true
        anchors.centerIn: parent
        title: tr("inbox_clear_completed")
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
                text: tr("inbox_confirm_clear")
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
                    text: tr("cancel"); variant: "ghost"
                    onClicked: _clearDialog.visible = false
                }
                Button {
                    text: tr("clear"); variant: "danger"
                    onClicked: {
                        if (controller) controller.inboxClearCompleted()
                        _clearDialog.visible = false
                    }
                }
            }
        }
    }
}
