// ============================================================
// LUMIO // DownloadsPage — 下载队列页
// ------------------------------------------------------------
// 还原 design_preview/downloads.html 的核心布局：
//   1. 页面头部（"下载队列" 渐变标题 26px/700 + 任务数 badge + 全部暂停 / 清空已完成 按钮）
//   2. 任务列表（Repeater + GlassCard：缩略图 / 标题作者 / 平台+状态 badge / 进度条 / 操作按钮）
//   3. 空状态（GlassCard + EmptyState "暂无下载任务"）
//   4. 底部状态栏（下载中数量 + 已完成数量 + 总速度）
// 数据绑定：
//   property var queueItems: controller ? controller.queueItems() : []
//   Connections 监听 controller.queueChanged 自动刷新
// 进度条：
//   暂用 QtQuick.Controls ProgressBar，后续替换为自定义 LaserProgress
// 尺寸：
//   - implicitHeight: 500
// ============================================================

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Lumio
import Lumio.Components

pragma ComponentBehavior: Bound

ColumnLayout {
    id: root
    spacing: 16
    implicitHeight: 500

    // ---- 数据 ----
    property var queueItems: (typeof controller !== "undefined" && controller)
                             ? controller.queueItems()
                             : []

    // ---- 计数 ----
    readonly property int _downloadingCount: {
        var n = 0
        for (var i = 0; i < queueItems.length; i++) {
            if (queueItems[i].status === "下载中") n++
        }
        return n
    }
    readonly property int _completedCount: {
        var n = 0
        for (var i = 0; i < queueItems.length; i++) {
            if (queueItems[i].status === "已完成") n++
        }
        return n
    }

    // ---- 状态 → Badge 类型映射 ----
    function _statusBadgeType(status) {
        if (status === "下载中") return "info"
        if (status === "已完成") return "success"
        if (status === "失败") return "danger"
        if (status === "重试中" || status === "暂停中" || status === "已中断") return "warning"
        return "default"
    }

    // ---- 平台 key → 显示名 ----
    function _platformLabel(plat) {
        var map = {
            "youtube": "YouTube", "instagram": "Instagram", "x": "X",
            "bilibili": "B站", "douyin": "抖音", "kuaishou": "快手",
            "weibo": "微博", "xiaohongshu": "小红书", "xhs": "小红书",
            "telegram": "Telegram", "auto": "自动"
        }
        return map[plat] || plat || "未知"
    }

    // ---- 主操作按钮图标（按状态）----
    function _primaryActionIcon(status) {
        if (status === "下载中") return "⏸"
        if (status === "暂停中" || status === "已中断" || status === "等待中") return "▶"
        if (status === "重试中" || status === "失败") return "↻"
        return ""
    }

    // ---- 执行主操作 ----
    function _doPrimary(task) {
        if (typeof controller === "undefined" || !controller) return
        var s = task.status
        var id = task.task_id
        if (s === "下载中") controller.pauseDownload(id)
        else if (s === "暂停中" || s === "已中断" || s === "等待中") controller.startDownload(id)
        else if (s === "重试中" || s === "失败") controller.retryDownload(id)
    }

    // ---- 监听队列变化自动刷新 ----
    Connections {
        target: (typeof controller !== "undefined" && controller) ? controller : null
        function onQueueChanged() {
            if (typeof controller !== "undefined" && controller) {
                root.queueItems = controller.queueItems()
            }
        }
    }

    // ============================================================
    // 1. 页面头部
    // ============================================================
    RowLayout {
        Layout.fillWidth: true
        spacing: 12

        // "下载队列" 渐变标题（26px / 700）— white → 75% white 垂直渐变
        Canvas {
            id: pageTitle
            Layout.preferredHeight: 34
            Layout.preferredWidth: pageTitleMetrics.width + 2
            renderStrategy: Canvas.Cooperative

            TextMetrics {
                id: pageTitleMetrics
                text: "下载队列"
                font.family: Theme.fontDisplay
                font.pixelSize: Theme.fsH1   // 26
                font.weight: Font.Bold
            }

            onPaint: {
                var ctx = getContext("2d")
                ctx.reset()
                ctx.font = "700 26px " + Theme.fontDisplay
                ctx.textBaseline = "top"
                var w = Math.max(1, pageTitleMetrics.width)
                var grad = ctx.createLinearGradient(0, 0, 0, 28)
                grad.addColorStop(0.0, "#ffffff")
                grad.addColorStop(1.0, Qt.rgba(1, 1, 1, 0.75))
                ctx.fillStyle = grad
                ctx.fillText("下载队列", 0, 0)
            }
            Component.onCompleted: requestPaint()
        }

        // 任务数 badge
        Badge {
            badgeType: "info"
            text: root.queueItems.length + " 任务"
            Layout.alignment: Qt.AlignVCenter
        }

        Item { Layout.fillWidth: true }

        // 操作按钮
        Button {
            text: "全部暂停"
            onClicked: {
                if (typeof controller === "undefined" || !controller) return
                for (var i = 0; i < root.queueItems.length; i++) {
                    var t = root.queueItems[i]
                    if (t.status === "下载中") controller.pauseDownload(t.task_id)
                }
            }
        }

        Button {
            text: "清空已完成"
            variant: "danger"
            onClicked: {
                if (typeof controller === "undefined" || !controller) return
                for (var i = 0; i < root.queueItems.length; i++) {
                    var t = root.queueItems[i]
                    if (t.status === "已完成" || t.status === "已取消") {
                        controller.removeDownload(t.task_id)
                    }
                }
            }
        }
    }

    // ============================================================
    // 2. 任务列表
    // ============================================================
    ColumnLayout {
        Layout.fillWidth: true
        spacing: 10

        // ---- 空状态 ----
        GlassCard {
            Layout.fillWidth: true
            Layout.topMargin: 20
            visible: root.queueItems.length === 0
            padding: 40
            Layout.preferredHeight: 220

            EmptyState {
                anchors.centerIn: parent
                icon: "⬇"
                title: "暂无下载任务"
                hint: "在主页粘贴 URL 并加入队列，任务将在此处显示实时进度"
            }
        }

        // ---- 任务卡片 ----
        Repeater {
            model: root.queueItems
            delegate: GlassCard {
                id: taskCard
                required property var modelData

                Layout.fillWidth: true
                padding: 14
                Layout.preferredHeight: Math.max(116, taskRow.implicitHeight + 28)

                // 从 modelData 解出常用字段
                readonly property var _task: modelData
                readonly property string _status: _task.status || ""
                readonly property real _progress: _task.progress || 0
                readonly property string _platform: _task.platform || "auto"

                // 进度条颜色（按状态）
                readonly property color _progressColor: {
                    if (_status === "已完成") return Theme.success
                    if (_status === "失败") return Theme.danger
                    if (_status === "重试中" || _status === "暂停中" || _status === "已中断") return Theme.warning
                    if (_status === "下载中") return Theme.accent
                    return Qt.rgba(1, 1, 1, 0.12)   // 等待中 / 已取消
                }

                RowLayout {
                    id: taskRow
                    anchors.fill: parent
                    spacing: 14

                    // ---- 左侧：缩略图占位（48×48 圆角，平台色 → accent2 渐变）----
                    Rectangle {
                        Layout.preferredWidth: 48
                        Layout.preferredHeight: 48
                        Layout.alignment: Qt.AlignVCenter
                        radius: Theme.rMD
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0.0; color: Theme.platformColor(taskCard._platform) }
                            GradientStop { position: 1.0; color: Theme.accent2 }
                        }

                        Text {
                            anchors.centerIn: parent
                            text: "▶"
                            color: Qt.rgba(1, 1, 1, 0.9)
                            font.pixelSize: 18
                        }
                    }

                    // ---- 中间：信息列（badges / 标题 / 进度 / 作者）----
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        // badges 行：平台 + 状态
                        Row {
                            spacing: 8
                            Badge {
                                badgeType: taskCard._platform
                                text: root._platformLabel(taskCard._platform)
                            }
                            Badge {
                                badgeType: root._statusBadgeType(taskCard._status)
                                text: taskCard._status
                            }
                        }

                        // 标题（超长省略）
                        Text {
                            Layout.fillWidth: true
                            text: taskCard._task.title || taskCard._task.url || ""
                            color: Theme.textPrimary
                            font.family: Theme.fontBody
                            font.pixelSize: Theme.fsBody
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }

                        // 进度行：进度条 + 百分比
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10

                            // 暂用简单 ProgressBar，后续替换为 LaserProgress
                            ProgressBar {
                                id: progBar
                                Layout.fillWidth: true
                                Layout.preferredHeight: 6
                                from: 0
                                to: 100
                                value: taskCard._progress

                                background: Rectangle {
                                    implicitWidth: 100
                                    implicitHeight: 6
                                    color: Qt.rgba(0, 0, 0, 0.35)
                                    radius: 3
                                    border.width: 1
                                    border.color: Theme.glassBorder
                                }

                                contentItem: Item {
                                    implicitWidth: 100
                                    implicitHeight: 6
                                    Rectangle {
                                        width: parent.width * progBar.position
                                        height: parent.height
                                        radius: 3
                                        color: taskCard._progressColor
                                    }
                                }
                            }

                            Text {
                                text: taskCard._status === "等待中"
                                      ? "—"
                                      : Math.round(taskCard._progress) + "%"
                                color: taskCard._progressColor
                                font.family: Theme.fontMono
                                font.pixelSize: Theme.fsMicro
                                Layout.preferredWidth: 40
                                horizontalAlignment: Text.AlignRight
                            }
                        }

                        // 作者 / 元信息行
                        Text {
                            Layout.fillWidth: true
                            text: {
                                var parts = []
                                if (taskCard._task.author) parts.push(taskCard._task.author)
                                if (taskCard._status !== "等待中") {
                                    parts.push(Math.round(taskCard._progress) + "%")
                                }
                                return parts.join(" · ")
                            }
                            color: Theme.textDim
                            font.family: Theme.fontMono
                            font.pixelSize: Theme.fsMicro
                            elide: Text.ElideRight
                        }
                    }

                    // ---- 右侧：操作按钮 ----
                    Row {
                        Layout.alignment: Qt.AlignVCenter
                        spacing: 4

                        // 主操作按钮（暂停 / 继续 / 重试）— 已完成 / 已取消 隐藏
                        Rectangle {
                            visible: taskCard._status !== "已完成"
                                     && taskCard._status !== "已取消"
                            width: 30
                            height: 30
                            radius: Theme.rSM
                            color: primaryMouse.containsMouse ? Theme.glassBgHi : "transparent"
                            border.width: 1
                            border.color: primaryMouse.containsMouse ? Theme.glassBorder : "transparent"
                            Behavior on color { ColorAnimation { duration: 150 } }
                            Behavior on border.color { ColorAnimation { duration: 150 } }

                            Text {
                                anchors.centerIn: parent
                                text: root._primaryActionIcon(taskCard._status)
                                color: primaryMouse.containsMouse ? Theme.accent : Theme.textMute
                                font.pixelSize: 14
                                Behavior on color { ColorAnimation { duration: 150 } }
                            }

                            MouseArea {
                                id: primaryMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root._doPrimary(taskCard._task)
                            }
                        }

                        // 取消 / 移除按钮
                        Rectangle {
                            width: 30
                            height: 30
                            radius: Theme.rSM
                            color: cancelMouse.containsMouse
                                   ? Qt.rgba(Theme.danger.r, Theme.danger.g, Theme.danger.b, 0.08)
                                   : "transparent"
                            border.width: 1
                            border.color: cancelMouse.containsMouse
                                          ? Qt.rgba(Theme.danger.r, Theme.danger.g, Theme.danger.b, 0.3)
                                          : "transparent"
                            Behavior on color { ColorAnimation { duration: 150 } }
                            Behavior on border.color { ColorAnimation { duration: 150 } }

                            Text {
                                anchors.centerIn: parent
                                text: "✕"
                                color: cancelMouse.containsMouse ? Theme.danger : Theme.textMute
                                font.pixelSize: 14
                                Behavior on color { ColorAnimation { duration: 150 } }
                            }

                            MouseArea {
                                id: cancelMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (typeof controller === "undefined" || !controller) return
                                    if (taskCard._status === "已完成"
                                            || taskCard._status === "已取消") {
                                        controller.removeDownload(taskCard._task.task_id)
                                    } else {
                                        controller.cancelDownload(taskCard._task.task_id)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // 弹性占位（把状态栏推到底部；任务少时撑开，任务多时坍缩）
    Item { Layout.fillHeight: true }

    // ============================================================
    // 3. 底部状态栏
    // ============================================================
    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 40
        radius: Theme.rLG
        color: Theme.glassBg
        border.width: 1
        border.color: Theme.glassBorder

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 22
            anchors.rightMargin: 22
            spacing: 18

            // 下载中数量
            Led {
                color: "blue"
                Layout.preferredWidth: 6
                Layout.preferredHeight: 6
            }
            Text {
                text: "下载中 " + root._downloadingCount
                color: Theme.textDim
                font.family: Theme.fontMono
                font.pixelSize: Theme.fsMicro
            }

            // 已完成数量
            Led {
                color: "green"
                Layout.preferredWidth: 6
                Layout.preferredHeight: 6
            }
            Text {
                text: "已完成 " + root._completedCount
                color: Theme.textDim
                font.family: Theme.fontMono
                font.pixelSize: Theme.fsMicro
            }

            Item { Layout.fillWidth: true }

            // 总速度（queueItems 无速度字段，暂显示占位）
            Text {
                text: "总速度 — MB/s"
                color: Theme.textDim
                font.family: Theme.fontMono
                font.pixelSize: Theme.fsMicro
            }
        }
    }
}
