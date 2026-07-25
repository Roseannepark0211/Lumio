// ============================================================
// LUMIO // DownloadsPage — 下载队列页
// ------------------------------------------------------------
// 真实对接 controller:
//   - getQueueJson() → 任务列表
//   - startTask/pauseTask/resumeTask/cancelTask/retryTask/deleteTask
//   - startAll/pauseAll/resumeAll
//   - queueChanged/taskStatusChanged/downloadProgressChanged 信号驱动刷新
// ============================================================
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Lumio
import Lumio.Components

Item {
    id: root

    property var tasks: []          // 任务数组
    property string filterStatus: "all"  // all / downloading / paused / completed / failed

    // ---------- 监听 controller 信号 ----------
    Connections {
        target: typeof controller !== "undefined" ? controller : null
        function onQueueChanged() { _reload() }
        function onTaskStatusChanged(task_id, status) { _reload() }
        function onDownloadProgressChanged(task_id, progress) {
            // 仅更新该任务的进度，避免整列重绘
            // 用 ListModel.set 才能触发 delegate 重新评估绑定
            for (var i = 0; i < _listModel.count; i++) {
                var item = _listModel.get(i)
                if (item.task_id === task_id) {
                    // clamp progress 到 0..1（防止后端异常值导致宽度越界）
                    var p = Math.max(0, Math.min(1, progress || 0))
                    _listModel.setProperty(i, "progress", p)
                    return
                }
            }
        }
    }

    // ListModel 才能触发 setProperty → delegate 绑定刷新
    // JS array 赋值 t.progress = x 不会触发任何 binding 重算
    ListModel {
        id: _listModel
    }

    Component.onCompleted: _reload()

    function _reload() {
        if (typeof controller === "undefined" || !controller) return
        try {
            var json = controller.getQueueJson()
            var arr = JSON.parse(json)
            root.tasks = arr
            var filtered = _applyFilter(arr)
            _listModel.clear()
            for (var i = 0; i < filtered.length; i++) {
                // 确保 progress 是合法 float（0..1）
                var t = filtered[i]
                t.progress = Math.max(0, Math.min(1, t.progress || 0))
                _listModel.append(t)
            }
        } catch (e) {
            console.log("[DownloadsPage] reload failed:", e)
        }
    }

    function _applyFilter(arr) {
        if (root.filterStatus === "all") return arr
        return arr.filter(function(t) {
            // 兼容中英文状态值（后端 TaskStatus 中文，未来可能改英文）
            var s = t.status
            if (root.filterStatus === "downloading") return s === "downloading" || s === "retrying" || s === "下载中" || s === "重试中"
            if (root.filterStatus === "paused") return s === "paused" || s === "interrupted" || s === "暂停中" || s === "已中断"
            if (root.filterStatus === "completed") return s === "completed" || s === "已完成"
            if (root.filterStatus === "failed") return s === "failed" || s === "cancelled" || s === "失败" || s === "已取消"
            return true
        })
    }

    // 状态归一化：把后端中文状态值统一映射为英文 key，便于 QML 比较
    function _normStatus(s) {
        var m = {
            "等待中": "waiting", "下载中": "downloading", "暂停中": "paused",
            "重试中": "retrying", "已中断": "interrupted", "已完成": "completed",
            "失败": "failed", "已取消": "cancelled"
        }
        return m[s] || s
    }

    function _statusText(s) {
        // 直接用后端原始中文值（i18n 已在后端完成）
        var m = {
            "waiting": "等待中", "downloading": "下载中", "paused": "暂停中",
            "retrying": "重试中", "interrupted": "已中断", "completed": "已完成",
            "failed": "失败", "cancelled": "已取消",
            // 后端已是中文时直接返回
            "等待中": "等待中", "下载中": "下载中", "暂停中": "暂停中",
            "重试中": "重试中", "已中断": "已中断", "已完成": "已完成",
            "失败": "失败", "已取消": "已取消"
        }
        return m[s] || s
    }

    function _statusColor(s) {
        var n = _normStatus(s)
        if (n === "completed") return Theme.success
        if (n === "downloading") return Theme.accent
        if (n === "failed" || n === "cancelled") return Theme.danger
        if (n === "paused" || n === "interrupted") return Theme.warning
        return Theme.textMute
    }

    function _formatSize(bytes) {
        if (!bytes || bytes <= 0) return "—"
        if (bytes < 1024) return bytes + " B"
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB"
        if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB"
        return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB"
    }

    function _formatPct(p) {
        return Math.round((p || 0) * 100) + "%"
    }

    function _activeCount() {
        var c = 0
        for (var i = 0; i < root.tasks.length; i++) {
            var n = _normStatus(root.tasks[i].status)
            if (n === "downloading" || n === "retrying") c++
        }
        return c
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
                title: tr("downloads_page")
                subtitle: tr("downloads_subtitle")
                icon: "i-download"

                // 右侧操作区
                Rectangle {
                    width: _queueText.implicitWidth + 20
                    height: 22
                    radius: Theme.rPill
                    color: Qt.rgba(10/255, 132/255, 1, 0.12)
                    border.width: 1
                    border.color: Qt.rgba(10/255, 132/255, 1, 0.3)

                    Text {
                        id: _queueText
                        anchors.centerIn: parent
                        text: _activeCount() + " " + tr("active")
                        color: Theme.accent
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fsMicro
                        font.weight: Font.DemiBold
                        font.letterSpacing: 0.5
                    }
                }

                Button {
                    text: tr("start_all"); variant: "primary"; iconName: "i-play"
                    onClicked: { if (controller) controller.startAll() }
                }
                Button {
                    text: tr("pause_all"); variant: "default"; iconName: "i-pause"
                    onClicked: { if (controller) controller.pauseAll() }
                }
                Button {
                    text: tr("resume_all"); variant: "default"; iconName: "i-retry"
                    onClicked: { if (controller) controller.resumeAll() }
                }
            }

            // 空状态
            Text {
                visible: root.tasks.length === 0
                Layout.fillWidth: true
                Layout.topMargin: 80
                text: tr("no_tasks")
                color: Theme.textMute
                font.family: Theme.fontBody
                font.pixelSize: Theme.fsBody
                horizontalAlignment: Text.AlignHCenter
            }

            // 任务列表
            Repeater {
                id: _list
                model: _listModel

                delegate: GlassCard {
                    Layout.fillWidth: true
                    Layout.leftMargin: 48
                    Layout.rightMargin: 48
                    Layout.preferredHeight: 110
                    radius: Theme.rLG

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 14
                        spacing: 14

                        // Thumbnail
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
                                source: model.thumbnail_url && model.thumbnail_url.length > 0
                                        ? (typeof controller !== "undefined" && controller
                                           ? controller.thumbUrl(model.thumbnail_url)
                                           : model.thumbnail_url)
                                        : ""
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                                visible: model.thumbnail_url && model.thumbnail_url.length > 0
                            }

                            Icon {
                                anchors.centerIn: parent
                                name: model.format_type === "audio" ? "i-audio" : "i-video"
                                size: 22
                                color: "#ffffff"
                                opacity: 0.6
                                visible: !(model.thumbnail_url && model.thumbnail_url.length > 0)
                            }
                        }

                        // Info
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4

                            Text {
                                text: model.title || model.url
                                color: Theme.textPrimary
                                font.family: Theme.fontDisplay
                                font.pixelSize: Theme.fsBody
                                font.weight: Font.DemiBold
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }

                            Text {
                                text: (model.author || "") + " · "
                                      + (model.platform || "").toUpperCase() + " · "
                                      + (model.speed || "—") + " · "
                                      + _formatSize(model.size || 0)
                                color: Theme.textMute
                                font.family: Theme.fontMono
                                font.pixelSize: Theme.fsSmall
                            }

                            // 激光粒子进度条（compact 模式，无 label）
                            // progress 自动 clamp 到 0..1
                            LaserProgressBar {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 20
                                progress: model.progress || 0
                                compact: true
                                particlesEnabled: _normStatus(model.status) === "downloading"
                                                  || _normStatus(model.status) === "retrying"
                            }
                        }

                        // Progress percent
                        Text {
                            text: _formatPct(model.progress)
                            color: Theme.textMute
                            font.family: Theme.fontMono
                            font.pixelSize: Theme.fsSmall
                            font.weight: Font.DemiBold
                        }

                        // Status
                        Badge {
                            text: _statusText(model.status)
                            status: model.status
                        }

                        // Action buttons
                        Row {
                            spacing: 4

                            // 开始/暂停/继续
                            Button {
                                // 用归一化状态判断图标和操作
                                property string _n: _normStatus(model.status)
                                iconName: _n === "downloading" ? "i-pause"
                                          : (_n === "paused" || _n === "interrupted" ? "i-play"
                                          : "i-play")
                                variant: "ghost"; iconSize: 16
                                enabled: _n === "waiting" || _n === "paused"
                                         || _n === "interrupted" || _n === "downloading"
                                onClicked: {
                                    if (!controller) return
                                    if (_n === "downloading") controller.pauseTask(model.task_id)
                                    else if (_n === "paused" || _n === "interrupted") controller.resumeTask(model.task_id)
                                    else controller.startTask(model.task_id)
                                }
                            }

                            // 重试（仅失败时）
                            Button {
                                property string _n: _normStatus(model.status)
                                iconName: "i-retry"; variant: "ghost"; iconSize: 16
                                visible: _n === "failed" || _n === "cancelled"
                                onClicked: { if (controller) controller.retryTask(model.task_id) }
                            }

                            // 取消
                            Button {
                                property string _n: _normStatus(model.status)
                                iconName: "i-cancel"; variant: "ghost"; iconSize: 16
                                enabled: _n === "downloading" || _n === "paused"
                                         || _n === "waiting" || _n === "retrying"
                                onClicked: { if (controller) controller.cancelTask(model.task_id) }
                            }

                            // 删除
                            Button {
                                iconName: "i-trash"; variant: "ghost"; iconSize: 16
                                onClicked: { if (controller) controller.deleteTask(model.task_id) }
                            }
                        }
                    }
                }
            }

            // 错误信息（如有）
            Repeater {
                model: root.tasks.filter(function(t) { return t.error && t.error.length > 0 })

                delegate: Text {
                    Layout.fillWidth: true
                    Layout.leftMargin: 48
                    Layout.rightMargin: 48
                    text: "⚠ " + modelData.title + ": " + modelData.error
                    color: Theme.danger
                    font.family: Theme.fontBody
                    font.pixelSize: Theme.fsSmall
                    wrapMode: Text.Wrap
                }
            }

            Item { Layout.preferredHeight: 48 }
        }
    }
}
