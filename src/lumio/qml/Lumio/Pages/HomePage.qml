// ============================================================
// LUMIO // HomePage — 主页
// ------------------------------------------------------------
// 还原 design_preview/liquid_glass_home.html 的核心布局：
//   1. Hero（"Lumio" 渐变大标题 44px/800 + "Universal Media Downloader" 副标题）
//   2. URL 输入卡片（多行 textarea + 文件名输入 + 下载按钮 + 平台 pills）
//   3. 快捷操作区（4 个 GlassCard：收件箱 / 媒体库 / 统计 / 设置）
// 交互：
//   - URL 输入绑定到 root.urlText
//   - 下载按钮调用 controller.addDownloadTask(url, "", platform, customName)
//   - 平台 pill 选中设置 root.selectedPlatform（单选，再次点击回退 auto）
// 尺寸：
//   - implicitHeight: 600（确保 ScrollView 能撑开）
// ============================================================

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Lumio
import Lumio.Components

pragma ComponentBehavior: Bound

ColumnLayout {
    id: root
    spacing: 20
    implicitHeight: 600

    // ---- 对外属性 ----
    property string urlText: ""
    property string selectedPlatform: "auto"
    property string customName: ""

    // ---- 平台 pill 配置 ----
    readonly property var _platforms: [
        { key: "youtube",     label: "YouTube" },
        { key: "instagram",   label: "Instagram" },
        { key: "x",           label: "X" },
        { key: "bilibili",    label: "B站" },
        { key: "douyin",      label: "抖音" },
        { key: "kuaishou",    label: "快手" },
        { key: "weibo",       label: "微博" },
        { key: "xiaohongshu", label: "小红书" },
        { key: "telegram",    label: "Telegram" }
    ]

    // ---- 快捷操作卡片 ----
    readonly property var _shortcuts: [
        { icon: "📥", title: "收件箱", desc: "浏览器与 Telegram 采集", pageId: "inbox" },
        { icon: "📚", title: "媒体库", desc: "所有下载的素材",       pageId: "library" },
        { icon: "📊", title: "统计",   desc: "下载量与平台分布",     pageId: "stats" },
        { icon: "⚙️", title: "设置",   desc: "通用 / 下载 / Cookie",  pageId: "settings" }
    ]

    // ---- 内部方法 ----
    function _enqueue() {
        var url = root.urlText.trim()
        if (url.length === 0) return
        if (typeof controller !== "undefined" && controller) {
            controller.addDownloadTask(url, "", root.selectedPlatform, root.customName)
        }
        root.urlText = ""
        root.customName = ""
        urlInput.text = ""
        nameInput.text = ""
    }

    function _selectPlatform(key) {
        // 单选：再次点击同一个回退到 auto
        root.selectedPlatform = (root.selectedPlatform === key) ? "auto" : key
    }

    function _gotoPage(pageId) {
        if (typeof controller !== "undefined" && controller
                && typeof controller.navigateTo === "function") {
            controller.navigateTo(pageId)
        }
    }

    // ============================================================
    // 1. Hero 区域
    // ============================================================
    ColumnLayout {
        Layout.fillWidth: true
        spacing: 10

        // "Lumio" 渐变大标题（44px / 800）— white → #a8c7ff 水平渐变
        // 与 Sidebar 品牌区一致，用 Canvas 绘制渐变文字
        Canvas {
            id: heroTitle
            Layout.fillWidth: true
            Layout.preferredHeight: 52
            renderStrategy: Canvas.Cooperative

            onPaint: {
                var ctx = getContext("2d")
                ctx.reset()
                var text = "Lumio"
                ctx.font = "800 44px " + Theme.fontDisplay
                ctx.textBaseline = "top"
                var metrics = ctx.measureText(text)
                var w = Math.max(1, metrics.width)
                var grad = ctx.createLinearGradient(0, 0, w, 0)
                grad.addColorStop(0.0, "#ffffff")
                grad.addColorStop(1.0, "#a8c7ff")
                ctx.fillStyle = grad
                ctx.fillText(text, 0, 0)
            }
            onWidthChanged: requestPaint()
            Component.onCompleted: requestPaint()
        }

        // 副标题（14px / textMute）
        Text {
            text: "Universal Media Downloader"
            color: Theme.textMute
            font.family: Theme.fontBody
            font.pixelSize: Theme.fsH3   // 14
        }
    }

    // ============================================================
    // 2. URL 输入卡片（GlassCard）
    //    Hero → 卡片间距 28px = root.spacing(20) + topMargin(8)
    // ============================================================
    GlassCard {
        Layout.fillWidth: true
        Layout.topMargin: 8
        padding: 20
        Layout.preferredHeight: Math.max(220, urlContent.implicitHeight + 40)

        ColumnLayout {
            id: urlContent
            anchors.fill: parent
            spacing: 14

            // ---- URL textarea（多行，Input 风格背景）----
            TextArea {
                id: urlInput
                Layout.fillWidth: true
                Layout.preferredHeight: 76
                onTextChanged: root.urlText = text
                placeholderText: "粘贴视频/图片/帖子链接..."
                placeholderTextColor: Theme.textDim
                color: Theme.textPrimary
                font.family: Theme.fontMono
                font.pixelSize: 13
                wrapMode: TextArea.Wrap
                selectByMouse: true
                verticalAlignment: TextInput.AlignTop
                leftPadding: 14
                rightPadding: 14
                topPadding: 12
                bottomPadding: 12

                background: Rectangle {
                    color: urlInput.activeFocus ? Theme.inputBgFocus : Theme.inputBg
                    border.width: 1
                    border.color: urlInput.activeFocus ? Theme.accent : Theme.glassBorder
                    radius: Theme.rMD
                    Behavior on color { ColorAnimation { duration: 150 } }
                    Behavior on border.color { ColorAnimation { duration: 150 } }
                }
            }

            // ---- 文件名输入 + 下载按钮 ----
            RowLayout {
                Layout.fillWidth: true
                spacing: 10

                Input {
                    id: nameInput
                    Layout.fillWidth: true
                    onTextChanged: root.customName = text
                    placeholderText: "自定义文件名（可选）"
                    font.pixelSize: Theme.fsSmall
                }

                Button {
                    text: "⬇ 下载"
                    variant: "primary"
                    implicitHeight: 40
                    onClicked: root._enqueue()
                }
            }

            // ---- 平台选择 pills（Flow 自动换行）----
            Flow {
                Layout.fillWidth: true
                spacing: 8

                Repeater {
                    model: root._platforms
                    delegate: Pill {
                        required property var modelData
                        // 关闭自动 toggle，由 selectedPlatform 单选驱动 checked
                        checkable: false
                        platform: modelData.key
                        text: modelData.label
                        checked: root.selectedPlatform === modelData.key
                        onClicked: root._selectPlatform(modelData.key)
                    }
                }
            }
        }
    }

    // ============================================================
    // 3. 快捷操作区（4 个小卡片横排）
    // ============================================================
    RowLayout {
        Layout.fillWidth: true
        spacing: 12

        Repeater {
            model: root._shortcuts
            delegate: GlassCard {
                id: shortcutCard
                required property var modelData
                Layout.fillWidth: true
                Layout.preferredHeight: 110
                padding: 16

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 6

                    Text {
                        text: shortcutCard.modelData.icon
                        font.pixelSize: 24
                    }

                    Text {
                        text: shortcutCard.modelData.title
                        color: Theme.textPrimary
                        font.family: Theme.fontDisplay
                        font.pixelSize: Theme.fsBody
                        font.weight: Font.DemiBold
                    }

                    Text {
                        Layout.fillWidth: true
                        text: shortcutCard.modelData.desc
                        color: Theme.textMute
                        font.family: Theme.fontBody
                        font.pixelSize: Theme.fsMicro
                        wrapMode: Text.WordWrap
                    }

                    Item { Layout.fillHeight: true }
                }

                // 点击跳转到对应页面
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root._gotoPage(shortcutCard.modelData.pageId)
                }
            }
        }
    }

    // 弹性占位（让内容顶对齐）
    Item { Layout.fillHeight: true }
}
