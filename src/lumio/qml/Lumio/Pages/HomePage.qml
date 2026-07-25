// ============================================================
// LUMIO // HomePage — 首页
// ------------------------------------------------------------
// 真实对接：
//   - controller.parseUrl(url) → infoExtracted 信号 → previewInfo
//   - controller.addDownloadTask(info_json, format_id, format_type, custom_name, output_dir)
//   - controller.checkUrlDuplicate(url) → 重复提示
// 移除 mock 进度动画，所有数据来自后端
// ============================================================
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Lumio
import Lumio.Components

Item {
    id: root

    // ---------- 状态 ----------
    property string urlText: ""
    property var previewInfo: null      // 解析后的 VideoInfo JSON 对象
    property bool isParsing: false
    property string parseError: ""
    property string selectedFormatId: ""
    property string selectedFormatType: ""
    property string customName: ""

    // ---------- Media Items 横向列表状态 ----------
    // 选中项索引（-1 表示未选中；老版本：点击卡片主体切换顶部预览）
    property int selectedItemIndex: -1
    // 已加入下载队列的 item 索引字典 {orig_idx: true}
    property var addedItemIndices: ({})
    // 排序后的 items（视频在前、图片在后），每项 {orig_idx, item}
    property var sortedItems: []

    // ---------- X-Sou 搜索状态 ----------
    property bool isSearching: false
    property string searchQuery: ""
    property int searchPage: 1
    property int searchLimit: 20
    property int searchTotal: 0
    property var searchResults: []     // [{tweet_id, screen_name, name, content, video_url, video_cover}]
    property var selectedSearchItems: ({})  // {tweet_id: true}

    // ---------- 监听 controller 信号 ----------
    Connections {
        target: typeof controller !== "undefined" ? controller : null
        function onInfoExtracted(info_json) {
            root.isParsing = false
            try {
                root.previewInfo = JSON.parse(info_json)
                root.parseError = ""
                // 默认文件名 = 作者_时间
                var info = root.previewInfo
                if (info.author && info.post_time) {
                    root.customName = info.author + "_" + info.post_time
                } else if (info.author) {
                    root.customName = info.author
                } else {
                    root.customName = info.title || ""
                }
                // 默认选第一个 format
                if (info.formats && info.formats.length > 0) {
                    root.selectedFormatId = info.formats[0].format_id || ""
                    root.selectedFormatType = info.formats[0].type || "video"
                }
                // 构建 media items 横向列表（视频在前、图片在后，保留 orig_idx）
                _buildMediaItems(info)
            } catch (e) {
                root.parseError = "Parse result invalid: " + e
            }
        }
        function onParseFailed(error_message) {
            root.isParsing = false
            root.previewInfo = null
            root.parseError = error_message
        }
        function onSearchCompleted(results_json) {
            root.isSearching = false
            try {
                var r = JSON.parse(results_json)
                root.searchResults = r.data || []
                root.searchTotal = r.total || 0
            } catch (e) {
                root.searchResults = []
                root.searchTotal = 0
            }
        }
        function onSearchFailed(error_message) {
            root.isSearching = false
            root.searchResults = []
            root.searchTotal = 0
            root.parseError = error_message
        }
    }

    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true

        ColumnLayout {
            width: parent.width
            spacing: 20

            // ============================================================
            // HERO
            // ============================================================
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 280
                Layout.topMargin: 16

                // Hero tag
                Rectangle {
                    id: _heroTag
                    anchors.top: parent.top
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: _heroTagText.implicitWidth + 28
                    height: 24
                    radius: Theme.rPill
                    color: Theme.accentSoft
                    border.width: 1
                    border.color: Qt.rgba(10/255, 132/255, 1, 0.35)

                    Row {
                        anchors.centerIn: parent
                        spacing: 6

                        Rectangle {
                            width: 6; height: 6; radius: 3
                            anchors.verticalCenter: parent.verticalCenter
                            color: Theme.accent
                        }

                        Text {
                            id: _heroTagText
                            text: tr("neural_capture")
                            color: Theme.accent
                            font.family: Theme.fontMono
                            font.pixelSize: Theme.fsMicro
                            font.weight: Font.DemiBold
                            font.letterSpacing: 0.5
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }

                // Hero title（渐变文字 — Canvas 模拟）
                Canvas {
                    id: _heroTitle
                    anchors.top: _heroTag.bottom
                    anchors.topMargin: 18
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: 600
                    height: 100
                    renderStrategy: Canvas.Cooperative

                    onPaint: {
                        var ctx = getContext("2d")
                        ctx.reset()
                        ctx.font = "800 44px " + Theme.fontDisplay
                        ctx.textBaseline = "top"
                        var line1 = tr("hero_line1")
                        var line2 = tr("hero_line2")
                        var grad = ctx.createLinearGradient(0, 0, 0, 100)
                        grad.addColorStop(0.0, "#ffffff")
                        grad.addColorStop(1.0, Qt.rgba(1, 1, 1, 0.7))
                        ctx.fillStyle = grad
                        ctx.textAlign = "center"
                        ctx.fillText(line1, 300, 0)
                        ctx.fillText(line2, 300, 50)
                    }
                    Component.onCompleted: requestPaint()
                }

                // Subtitle
                Text {
                    id: _subtitle
                    anchors.top: _heroTitle.bottom
                    anchors.topMargin: 14
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: tr("hero_sub")
                    color: Theme.textMute
                    font.family: Theme.fontBody
                    font.pixelSize: Theme.fsH3
                    font.weight: Font.Normal
                    horizontalAlignment: Text.AlignHCenter
                }

                // Platform pills
                Row {
                    id: _platforms
                    anchors.top: _subtitle.bottom
                    anchors.topMargin: 16
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 8

                    Repeater {
                        model: [
                            { plat: "youtube",    label: "YouTube" },
                            { plat: "instagram",  label: "Instagram" },
                            { plat: "x",          label: "X" },
                            { plat: "bilibili",   label: tr("platform_bilibili") },
                            { plat: "douyin",     label: tr("platform_douyin") },
                            { plat: "kuaishou",   label: tr("platform_kuaishou") },
                            { plat: "weibo",      label: tr("platform_weibo") },
                            { plat: "xiaohongshu",label: tr("platform_xiaohongshu") }
                        ]

                        delegate: Pill {
                            plat: modelData.plat
                            label: modelData.label
                        }
                    }
                }
            }

            // ============================================================
            // URL INPUT CARD
            // ============================================================
            GlassCard {
                Layout.fillWidth: true
                Layout.leftMargin: 48
                Layout.rightMargin: 48
                Layout.preferredHeight: 220
                radius: Theme.rXL

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    // Header
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 50
                        Layout.leftMargin: 22
                        Layout.rightMargin: 22
                        spacing: 6

                        Text {
                            text: tr("url_input")
                            color: Theme.textMute
                            font.family: Theme.fontBody
                            font.pixelSize: Theme.fsSmall
                            font.weight: Font.DemiBold
                            font.letterSpacing: 0.3
                        }

                        Item { Layout.fillWidth: true }

                        Button {
                            text: tr("clear")
                            variant: "ghost"
                            onClicked: { root.urlText = ""; root.previewInfo = null; root.parseError = "" }
                        }

                        Button {
                            text: tr("search_btn")
                            variant: "default"
                            iconName: "i-search"
                            enabled: !root.isParsing && root.urlText.length > 0
                            onClicked: _runSearch(1)
                        }

                        Button {
                            text: tr("paste")
                            variant: "default"
                            iconName: "i-paste"
                            onClicked: {
                                var clip = Qt.application.clipboard
                                if (clip && clip.text) root.urlText = clip.text
                            }
                        }

                        Button {
                            text: tr("parse_btn")
                            variant: "primary"
                            iconName: "i-sparkles"
                            enabled: !root.isParsing && root.urlText.length > 0
                            onClicked: _parseUrl()
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        height: 1
                        color: Theme.glassBorder
                    }

                    // Textarea
                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 90
                        Layout.leftMargin: 22
                        Layout.rightMargin: 22
                        Layout.topMargin: 18

                        Textarea {
                            id: _urlInput
                            anchors.fill: parent
                            placeholderText: tr("url_placeholder")
                            text: root.urlText
                            onTextChanged: root.urlText = text
                        }
                    }

                    // Hint
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 22
                        Layout.rightMargin: 22
                        Layout.topMargin: 8
                        Layout.bottomMargin: 16
                        spacing: 6

                        Text {
                            text: root.isParsing ? "● " + tr("parse_parsing")
                                  : root.parseError ? "● " + root.parseError
                                  : "● " + tr("parse_empty")
                            color: root.isParsing ? Theme.accent
                                  : root.parseError ? Theme.danger
                                  : Theme.textDim
                            font.family: Theme.fontBody
                            font.pixelSize: Theme.fsMicro
                        }

                        Item { Layout.fillWidth: true }
                    }
                }
            }

            // ============================================================
            // MEDIA ITEMS CARD — 横向列表展示帖子内容（预览区上方）
            // ------------------------------------------------------------
            // 还原老版本 _build_media_items_preview 逻辑：
            //   - 视频在前、图片在后，保留 orig_idx 用于下载定位
            //   - 点击卡片主体（非按钮）→ 选中并切换下方预览
            //   - 点击「加入下载队列」按钮 → 单独入队（走 direct_url）
            //   - 已加入的卡片变灰、按钮禁用
            //   - 横向 ScrollBar.AlwaysOn 始终显示，方便查看所有项
            // 仅当 items 数量 > 1 时显示
            // ============================================================
            GlassCard {
                Layout.fillWidth: true
                Layout.leftMargin: 48
                Layout.rightMargin: 48
                Layout.preferredHeight: 260
                radius: Theme.rXL
                visible: root.previewInfo
                         && root.previewInfo.items
                         && root.previewInfo.items.length > 1

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    // Header
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 50
                        Layout.leftMargin: 22
                        Layout.rightMargin: 22
                        spacing: 10

                        Text {
                            text: tr("media_items_title")
                            color: Theme.textMute
                            font.family: Theme.fontBody
                            font.pixelSize: Theme.fsSmall
                            font.weight: Font.DemiBold
                        }

                        Text {
                            text: (root.previewInfo && root.previewInfo.items
                                   ? root.previewInfo.items.length : 0) + " " + tr("items")
                            color: Theme.textDim
                            font.family: Theme.fontMono
                            font.pixelSize: Theme.fsMicro
                        }

                        Item { Layout.fillWidth: true }

                        Text {
                            text: tr("media_items_hint")
                            color: Theme.textDim
                            font.family: Theme.fontBody
                            font.pixelSize: Theme.fsMicro
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        height: 1
                        color: Theme.glassBorder
                    }

                    // 横向列表（带可见滑动条）
                    ListView {
                        id: _mediaListView
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.leftMargin: 16
                        Layout.rightMargin: 16
                        Layout.topMargin: 12
                        Layout.bottomMargin: 4
                        clip: true
                        orientation: ListView.Horizontal
                        spacing: 12
                        boundsBehavior: Flickable.StopAtBounds
                        model: root.sortedItems

                        // 始终显示横向滑动条
                        ScrollBar.horizontal: ScrollBar {
                            policy: ScrollBar.AlwaysOn
                            contentItem: Rectangle {
                                implicitHeight: 6
                                radius: 3
                                color: Qt.rgba(1, 1, 1, 0.2)
                                Rectangle {
                                    anchors.fill: parent
                                    anchors.margins: 1
                                    radius: parent.radius
                                    color: Theme.accent
                                    visible: parent.parent.visualPosition !== undefined
                                }
                            }
                        }
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AlwaysOff }

                        delegate: Rectangle {
                            width: 160
                            height: 188
                            radius: Theme.rMD
                            color: root.selectedItemIndex === modelData.orig_idx
                                   ? Theme.accentSoft
                                   : (hover.hovered ? Theme.glassBg : Qt.rgba(0, 0, 0, 0.2))
                            border.width: root.selectedItemIndex === modelData.orig_idx ? 2 : 1
                            border.color: root.selectedItemIndex === modelData.orig_idx
                                          ? Theme.accent
                                          : (root.addedItemIndices[modelData.orig_idx]
                                             ? Theme.success
                                             : Theme.glassBorder)
                            Behavior on color { ColorAnimation { duration: 120 } }

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 8
                                spacing: 4

                                // 缩略图
                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 104
                                    radius: Theme.rSM
                                    color: Qt.rgba(0, 0, 0, 0.3)
                                    clip: true

                                    Image {
                                        anchors.fill: parent
                                        // 图片项直接用 item.url 加载缩略图
                                        source: !modelData.item.is_video
                                                && modelData.item.url
                                                && modelData.item.url.length > 0
                                                ? (typeof controller !== "undefined" && controller
                                                   ? controller.thumbUrl(modelData.item.url)
                                                   : modelData.item.url)
                                                : ""
                                        fillMode: Image.PreserveAspectCrop
                                        asynchronous: true
                                        cache: true
                                        visible: !modelData.item.is_video
                                                 && modelData.item.url
                                                 && modelData.item.url.length > 0
                                    }

                                    // 视频占位图标
                                    Icon {
                                        anchors.centerIn: parent
                                        name: "i-video"
                                        size: 28
                                        color: Theme.textDim
                                        visible: modelData.item.is_video
                                                 || !modelData.item.url
                                                 || modelData.item.url.length === 0
                                    }

                                    // 已加入角标
                                    Rectangle {
                                        anchors.top: parent.top
                                        anchors.right: parent.right
                                        anchors.margins: 4
                                        width: _addedTick.implicitWidth + 12
                                        height: 18
                                        radius: Theme.rSM
                                        color: Theme.success
                                        visible: root.addedItemIndices[modelData.orig_idx] === true

                                        Text {
                                            id: _addedTick
                                            anchors.centerIn: parent
                                            text: "✓"
                                            color: "#ffffff"
                                            font.family: Theme.fontMono
                                            font.pixelSize: 11
                                            font.weight: Font.Bold
                                        }
                                    }
                                }

                                // 类型标签 "视频 1/3" / "图片 2/3"
                                Text {
                                    Layout.fillWidth: true
                                    horizontalAlignment: Text.AlignHCenter
                                    text: {
                                        var typeText = modelData.item.is_video
                                                       ? tr("media_item_video")
                                                       : tr("media_item_image")
                                        return typeText + " " + (modelData.display_pos + 1) + "/" + root.sortedItems.length
                                    }
                                    color: Theme.textMute
                                    font.family: Theme.fontBody
                                    font.pixelSize: Theme.fsMicro
                                    font.weight: Font.DemiBold
                                }

                                Item { Layout.fillHeight: true }

                                // 加入下载按钮（点击不冒泡到卡片）
                                Button {
                                    Layout.fillWidth: true
                                    text: root.addedItemIndices[modelData.orig_idx] === true
                                          ? tr("item_added")
                                          : tr("add_to_queue")
                                    variant: root.addedItemIndices[modelData.orig_idx] === true
                                             ? "ghost" : "default"
                                    iconName: root.addedItemIndices[modelData.orig_idx] === true
                                              ? "i-check" : "i-download-line"
                                    enabled: root.addedItemIndices[modelData.orig_idx] !== true
                                    onClicked: _enqueueSingleItem(modelData.orig_idx)
                                }
                            }

                            // 卡片主体点击区（覆盖缩略图 + 类型标签区域，不覆盖按钮）
                            MouseArea {
                                anchors.fill: parent
                                anchors.bottomMargin: 40  // 避开底部按钮区域
                                cursorShape: Qt.PointingHandCursor
                                onClicked: _onCardSelected(modelData.orig_idx)
                                z: -1  // 让按钮可点击
                            }

                            HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
                        }
                    }
                }
            }

            // ============================================================
            // PREVIEW CARD — 仅在有 previewInfo 时显示
            // ============================================================
            GlassCard {
                Layout.fillWidth: true
                Layout.leftMargin: 48
                Layout.rightMargin: 48
                Layout.preferredHeight: 380
                radius: Theme.rXL
                visible: root.previewInfo !== null

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    // ============================================================
                    // 媒体预览区 — 居中显示，不含任何文字信息
                    // ============================================================
                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        // 居中容器：保持 16:9 比例的最大可用区域
                        Item {
                            anchors.centerIn: parent
                            width: Math.min(parent.width - 48, 480)
                            height: Math.min(parent.height - 32, width * 9 / 16)

                            Rectangle {
                                anchors.fill: parent
                                radius: Theme.rMD
                                color: Qt.rgba(0, 0, 0, 0.3)
                                border.width: 1
                                border.color: Theme.glassBorder
                                clip: true

                                // 缩略图（如有）— 等比例完整显示，避免裁剪
                                Image {
                                    anchors.fill: parent
                                    source: _previewSource()
                                    fillMode: Image.PreserveAspectFit
                                    asynchronous: true
                                    cache: false
                                    visible: _previewSource().length > 0
                                }

                                // 视频占位图标
                                Icon {
                                    anchors.centerIn: parent
                                    name: "i-video"
                                    size: 36
                                    color: Theme.textDim
                                    visible: _previewIsVideo() && _previewSource().length === 0
                                }

                                // play icon（视频且有缩略图时显示）
                                Rectangle {
                                    anchors.centerIn: parent
                                    width: 44; height: 44; radius: 22
                                    color: Qt.rgba(1, 1, 1, 0.18)
                                    border.width: 1
                                    border.color: Qt.rgba(1, 1, 1, 0.3)
                                    visible: _previewIsVideo() && _previewSource().length > 0

                                    Icon {
                                        anchors.centerIn: parent
                                        name: "i-play"
                                        size: 16
                                        color: "#ffffff"
                                    }
                                }

                                // duration（右下角）
                                Rectangle {
                                    anchors.bottom: parent.bottom
                                    anchors.right: parent.right
                                    anchors.margins: 8
                                    width: _durText.implicitWidth + 14
                                    height: 20
                                    radius: Theme.rSM
                                    color: Qt.rgba(0, 0, 0, 0.6)
                                    visible: root.previewInfo && root.previewInfo.duration > 0

                                    Text {
                                        id: _durText
                                        anchors.centerIn: parent
                                        text: _formatDuration(root.previewInfo ? root.previewInfo.duration : 0)
                                        color: "#ffffff"
                                        font.family: Theme.fontMono
                                        font.pixelSize: 11
                                        font.weight: Font.Medium
                                    }
                                }
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        height: 1
                        color: Theme.glassBorder
                    }

                    // ============================================================
                    // FORMAT ROW — 文件名 + 格式 + 加入队列按钮
                    // ============================================================
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 22
                        Layout.rightMargin: 22
                        Layout.topMargin: 18
                        Layout.bottomMargin: 22
                        spacing: 16

                        // Filename
                        ColumnLayout {
                            Layout.preferredWidth: 280
                            spacing: 6

                            Text {
                                text: tr("filename")
                                color: Theme.textDim
                                font.family: Theme.fontBody
                                font.pixelSize: Theme.fsMicro
                                font.weight: Font.DemiBold
                                font.letterSpacing: 0.3
                                Layout.leftMargin: 4
                            }

                            Input {
                                Layout.fillWidth: true
                                text: root.customName
                                onTextChanged: root.customName = text
                                placeholderText: tr("leave_empty")
                            }
                        }

                        // Format selector（仅多格式时显示）
                        ColumnLayout {
                            Layout.preferredWidth: 200
                            spacing: 6
                            visible: root.previewInfo && root.previewInfo.formats && root.previewInfo.formats.length > 1

                            Text {
                                text: tr("format")
                                color: Theme.textDim
                                font.family: Theme.fontBody
                                font.pixelSize: Theme.fsMicro
                                font.weight: Font.DemiBold
                                font.letterSpacing: 0.3
                                Layout.leftMargin: 4
                            }

                            LumioComboBox {
                                Layout.fillWidth: true
                                model: root.previewInfo ? root.previewInfo.formats : []
                                textRole: "label"
                                valueRole: "format_id"
                                placeholder: tr("format")
                                // 默认选第一个 format
                                currentIndex: root.previewInfo && root.previewInfo.formats && root.previewInfo.formats.length > 0 ? 0 : -1
                                onActivated: {
                                    if (currentValue) {
                                        root.selectedFormatId = currentValue
                                        // 同步 format_type
                                        var fmt = root.previewInfo.formats[currentIndex]
                                        if (fmt) root.selectedFormatType = fmt.type || "video"
                                    }
                                }
                            }
                        }

                        Item { Layout.fillWidth: true }

                        // Enqueue button
                        Button {
                            text: tr("enqueue")
                            variant: "primary"
                            iconName: "i-download-line"
                            onClicked: _enqueue()
                        }
                    }
                }
            }

            // ============================================================
            // X-SOU SEARCH RESULTS — 仅在有搜索结果时显示
            // ============================================================
            GlassCard {
                Layout.fillWidth: true
                Layout.leftMargin: 48
                Layout.rightMargin: 48
                Layout.preferredHeight: Math.min(540, 160 + root.searchResults.length * 90)
                radius: Theme.rXL
                visible: root.searchResults.length > 0 || root.isSearching

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    // Header
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 50
                        Layout.leftMargin: 22
                        Layout.rightMargin: 22
                        spacing: 10

                        Text {
                            text: tr("search_btn") + " · X-Sou"
                            color: Theme.textMute
                            font.family: Theme.fontBody
                            font.pixelSize: Theme.fsSmall
                            font.weight: Font.DemiBold
                        }

                        Item { Layout.fillWidth: true }

                        Text {
                            text: root.isSearching
                                  ? tr("search_loading")
                                  : (root.searchTotal + " " + tr("items"))
                            color: root.isSearching ? Theme.accent : Theme.textDim
                            font.family: Theme.fontMono
                            font.pixelSize: Theme.fsMicro
                        }

                        Button {
                            text: tr("cancel")
                            variant: "ghost"
                            iconName: "i-clear"
                            onClicked: {
                                root.searchResults = []
                                root.searchTotal = 0
                                root.selectedSearchItems = ({})
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        height: 1
                        color: Theme.glassBorder
                    }

                    // 结果列表
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true

                        ListView {
                            model: root.searchResults
                            spacing: 4
                            boundsBehavior: Flickable.StopAtBounds

                            delegate: Rectangle {
                                width: ListView.view.width
                                height: 80
                                color: _isSearchSelected(modelData.tweet_id)
                                       ? Theme.accentSoft
                                       : (hover.hovered ? Theme.glassBg : "transparent")
                                Behavior on color { ColorAnimation { duration: 120 } }

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    spacing: 12

                                    // 选择框（修复清单问题 1：必须用 Layout.preferredWidth/Height
                                    // 让 RowLayout 给出非零尺寸，否则 MouseArea 0x0 无法点击）
                                    Rectangle {
                                        Layout.preferredWidth: 20
                                        Layout.preferredHeight: 20
                                        Layout.alignment: Qt.AlignVCenter
                                        radius: 4
                                        color: _isSearchSelected(modelData.tweet_id)
                                               ? Theme.accent : "transparent"
                                        border.width: 1
                                        border.color: _isSearchSelected(modelData.tweet_id)
                                                      ? Theme.accent : Theme.glassBorderHi
                                        Icon {
                                            anchors.centerIn: parent
                                            name: "i-check"
                                            size: 12
                                            color: "#ffffff"
                                            visible: _isSearchSelected(modelData.tweet_id)
                                        }
                                        MouseArea {
                                            anchors.fill: parent
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: _toggleSearchSelect(modelData)
                                        }
                                    }

                                    // 缩略图
                                    Rectangle {
                                        Layout.preferredWidth: 80
                                        Layout.preferredHeight: 50
                                        Layout.alignment: Qt.AlignVCenter
                                        radius: Theme.rSM
                                        color: Qt.rgba(0, 0, 0, 0.3)
                                        clip: true

                                        Image {
                                            anchors.fill: parent
                                            source: modelData.video_cover || ""
                                            fillMode: Image.PreserveAspectCrop
                                            asynchronous: true
                                            cache: true
                                            visible: (modelData.video_cover || "").length > 0
                                        }
                                        Icon {
                                            anchors.centerIn: parent
                                            name: "i-video"
                                            size: 18
                                            color: Theme.textDim
                                            visible: !(modelData.video_cover || "").length > 0
                                        }
                                    }

                                    // 信息列（标题超长时截断，用 elide + maximumLineCount 显示省略号）
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        Layout.alignment: Qt.AlignVCenter
                                        spacing: 2

                                        Text {
                                            Layout.fillWidth: true
                                            // 老版本：截断到 80 字符，QML 用 elide 显示 ...
                                            text: (modelData.content || "").length > 80
                                                  ? (modelData.content || "").substring(0, 80) + "..."
                                                  : (modelData.content || "")
                                            color: Theme.textPrimary
                                            font.family: Theme.fontBody
                                            font.pixelSize: Theme.fsSmall
                                            elide: Text.ElideRight
                                            maximumLineCount: 1
                                        }
                                        Text {
                                            text: "@" + (modelData.screen_name || "")
                                                  + "  ·  " + (modelData.name || "")
                                            color: Theme.textDim
                                            font.family: Theme.fontBody
                                            font.pixelSize: Theme.fsMicro
                                            elide: Text.ElideRight
                                            maximumLineCount: 1
                                        }
                                    }

                                    // 视频源不可用标识（无 video_url 时显示）
                                    Rectangle {
                                        visible: !(modelData.video_url || "").length > 0
                                        Layout.alignment: Qt.AlignVCenter
                                        Layout.preferredWidth: _noVideo.implicitWidth + 16
                                        Layout.preferredHeight: 22
                                        radius: Theme.rPill
                                        color: Qt.rgba(1, 1, 1, 0.05)
                                        border.width: 1
                                        border.color: Theme.glassBorder
                                        Text {
                                            id: _noVideo
                                            anchors.centerIn: parent
                                            text: tr("video_not_available")
                                            color: Theme.textDim
                                            font.pixelSize: 10
                                        }
                                    }

                                    // 预览按钮（仅当有 video_url 时显示）
                                    // 老版本逻辑：点击调用 _previewXVideo 缓存到本地后用 VideoPreviewDialog 播放
                                    Button {
                                        visible: (modelData.video_url || "").length > 0
                                        text: tr("preview")
                                        variant: "ghost"
                                        iconName: "i-play"
                                        iconSize: 12
                                        Layout.alignment: Qt.AlignVCenter
                                        onClicked: _previewXVideo(modelData.video_url)
                                    }
                                }

                                HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        height: 1
                        color: Theme.glassBorder
                    }

                    // Footer：分页 + 批量入队
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 48
                        Layout.leftMargin: 22
                        Layout.rightMargin: 22
                        spacing: 10

                        Text {
                            text: root.searchPage + " / " + Math.max(1, Math.ceil(root.searchTotal / root.searchLimit))
                            color: Theme.textDim
                            font.family: Theme.fontMono
                            font.pixelSize: Theme.fsMicro
                        }

                        Button {
                            text: tr("prev_page")
                            variant: "ghost"
                            iconName: "i-chevron-right"
                            iconRotation: 180
                            enabled: root.searchPage > 1 && !root.isSearching
                            onClicked: _runSearch(root.searchPage - 1)
                        }

                        Button {
                            text: tr("next_page")
                            variant: "default"
                            iconName: "i-chevron-right"
                            enabled: root.searchPage < Math.ceil(root.searchTotal / root.searchLimit) && !root.isSearching
                            onClicked: _runSearch(root.searchPage + 1)
                        }

                        Item { Layout.fillWidth: true }

                        Text {
                            text: Object.keys(root.selectedSearchItems).length + " " + tr("items")
                            color: Theme.accent
                            font.family: Theme.fontMono
                            font.pixelSize: Theme.fsMicro
                            font.weight: Font.DemiBold
                            visible: Object.keys(root.selectedSearchItems).length > 0
                        }

                        Button {
                            text: tr("enqueue")
                            variant: "primary"
                            iconName: "i-download-line"
                            enabled: Object.keys(root.selectedSearchItems).length > 0
                            onClicked: _enqueueSelectedSearch()
                        }
                    }
                }
            }

            // ============================================================
            // STATUS BAR
            // ============================================================
            GlassCard {
                Layout.fillWidth: true
                Layout.leftMargin: 48
                Layout.rightMargin: 48
                Layout.bottomMargin: 32
                Layout.preferredHeight: 48
                radius: Theme.rLG

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 22
                    anchors.rightMargin: 22
                    spacing: 18

                    Row {
                        spacing: 6
                        Rectangle { width: 6; height: 6; radius: 3; color: Theme.success; anchors.verticalCenter: parent.verticalCenter }
                        Text { text: tr("api_online"); color: Theme.textDim; font.family: Theme.fontBody; font.pixelSize: Theme.fsMicro }
                    }

                    Row {
                        spacing: 6
                        Rectangle { width: 6; height: 6; radius: 3; color: Theme.accent; anchors.verticalCenter: parent.verticalCenter }
                        Text { text: tr("ffmpeg_ready"); color: Theme.textDim; font.family: Theme.fontBody; font.pixelSize: Theme.fsMicro }
                    }

                    Row {
                        spacing: 6
                        Rectangle { width: 6; height: 6; radius: 3; color: Theme.platIg; anchors.verticalCenter: parent.verticalCenter }
                        Text { text: tr("extension_linked"); color: Theme.textDim; font.family: Theme.fontBody; font.pixelSize: Theme.fsMicro }
                    }

                    Item { Layout.fillWidth: true }

                    Text {
                        text: tr("version") + ": " + (typeof controller !== "undefined" && controller ? _getVersion() : "")
                        color: Theme.textDim
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fsMicro
                    }
                }
            }
        }
    }

    // ============================================================
    // 业务逻辑
    // ============================================================
    function _parseUrl() {
        var url = (root.urlText || "").trim()
        if (url.length === 0) return
        if (typeof controller === "undefined" || !controller) return

        root.isParsing = true
        root.previewInfo = null
        root.parseError = ""
        // 重置 media items 状态
        root.selectedItemIndex = -1
        root.addedItemIndices = ({})
        root.sortedItems = []
        controller.parseUrl(url)
    }

    // ============================================================
    // Media Items 横向列表逻辑
    // ============================================================

    // 构建 sortedItems：视频在前、图片在后，保留 orig_idx 与 display_pos
    function _buildMediaItems(info) {
        root.selectedItemIndex = -1
        root.addedItemIndices = ({})
        root.sortedItems = []

        if (!info || !info.items || info.items.length === 0) return

        var arr = []
        for (var i = 0; i < info.items.length; i++) {
            arr.push({ orig_idx: i, item: info.items[i] })
        }
        // 排序：视频在前(0)，图片在后(1)；同类型按 orig_idx 升序
        arr.sort(function(a, b) {
            var ka = a.item.is_video ? 0 : 1
            var kb = b.item.is_video ? 0 : 1
            if (ka !== kb) return ka - kb
            return a.orig_idx - b.orig_idx
        })
        // 补 display_pos
        for (var j = 0; j < arr.length; j++) {
            arr[j].display_pos = j
        }
        root.sortedItems = arr

        // 默认选中第一项，让顶部预览区有内容
        if (arr.length > 0) {
            root.selectedItemIndex = arr[0].orig_idx
        }
    }

    // 点击卡片主体 — 选中并切换下方预览
    function _onCardSelected(orig_idx) {
        if (!root.previewInfo || !root.previewInfo.items) return
        if (orig_idx < 0 || orig_idx >= root.previewInfo.items.length) return
        root.selectedItemIndex = orig_idx
    }

    // 单独入队某一项 — 走 direct_url 直链下载
    function _enqueueSingleItem(orig_idx) {
        if (typeof controller === "undefined" || !controller) return
        if (!root.previewInfo || !root.previewInfo.items) return
        if (orig_idx < 0 || orig_idx >= root.previewInfo.items.length) return
        if (root.addedItemIndices[orig_idx] === true) return

        var item = root.previewInfo.items[orig_idx]
        if (!item.url || item.url.length === 0) {
            showToast(tr("video_not_available"))
            return
        }

        // 自定义名称加序号后缀，避免多图/多视频文件名冲突
        var custom = (root.customName || "").trim()
        var title = root.previewInfo.title || ("item_" + (orig_idx + 1))
        if (custom) {
            title = custom + "_" + (orig_idx + 1)
        } else {
            title = title + "_" + (orig_idx + 1)
        }

        // 调用后端 addDirectDownloadTask(url, title, platform, thumbnail, is_video, author)
        // 修复清单：
        //   1) 传 is_video 让后端能正确推断扩展名（URL 无后缀时不再默认 .mp4）
        //   2) 传 author 让 _effective_name 不再返回 %(title)s 字面值
        //   3) 单项下载 thumbnail 用 item.url（图片项）/ 帖子缩略图（视频项），
        //      不再用 previewInfo.thumbnail（永远是链接第一项）
        var thumb = ""
        if (item.is_video) {
            // 视频项用帖子缩略图（如有）
            thumb = root.previewInfo.thumbnail || ""
        } else {
            // 图片项用自身 url 作为缩略图源
            thumb = item.url
        }

        controller.addDirectDownloadTask(
            item.url,
            title,
            root.previewInfo.platform || "",
            thumb,
            item.is_video === true,
            root.previewInfo.author || ""
        )

        // 标记为已加入（触发 delegate 刷新按钮状态）
        var sel = root.addedItemIndices
        sel[orig_idx] = true
        root.addedItemIndices = sel
    }

    // 顶部预览缩略图 URL — 优先显示选中 item，否则显示帖子总缩略图
    function _previewSource() {
        if (!root.previewInfo) return ""
        // 选中了某项且该项是图片 → 用 item.url 作大图
        if (root.selectedItemIndex >= 0
                && root.previewInfo.items
                && root.selectedItemIndex < root.previewInfo.items.length) {
            var it = root.previewInfo.items[root.selectedItemIndex]
            if (!it.is_video && it.url && it.url.length > 0) {
                return (typeof controller !== "undefined" && controller)
                       ? controller.thumbUrl(it.url) : it.url
            }
            // 视频项 → 用帖子总缩略图（如果有）
            if (it.is_video && root.previewInfo.thumbnail
                    && root.previewInfo.thumbnail.length > 0) {
                return (typeof controller !== "undefined" && controller)
                       ? controller.thumbUrl(root.previewInfo.thumbnail)
                       : root.previewInfo.thumbnail
            }
            return ""
        }
        // 未选中 → 用帖子总缩略图
        if (root.previewInfo.thumbnail && root.previewInfo.thumbnail.length > 0) {
            return (typeof controller !== "undefined" && controller)
                   ? controller.thumbUrl(root.previewInfo.thumbnail)
                   : root.previewInfo.thumbnail
        }
        return ""
    }

    // 顶部预览是否视频 — 选中视频项时显示 play 图标
    function _previewIsVideo() {
        if (!root.previewInfo) return false
        if (root.selectedItemIndex >= 0
                && root.previewInfo.items
                && root.selectedItemIndex < root.previewInfo.items.length) {
            return root.previewInfo.items[root.selectedItemIndex].is_video
        }
        // 未选中 → 默认看 items[0]
        if (root.previewInfo.items && root.previewInfo.items.length > 0) {
            return root.previewInfo.items[0].is_video
        }
        return false
    }

    // ============================================================
    // X-Sou 搜索逻辑
    // ============================================================
    function _runSearch(page) {
        var q = (root.urlText || "").trim()
        if (q.length === 0) return
        if (typeof controller === "undefined" || !controller) return

        // @username → from:username
        if (q.indexOf("@") === 0) {
            q = "from:" + q.substring(1)
        }

        root.isSearching = true
        root.searchQuery = q
        root.searchPage = page || 1
        root.parseError = ""
        // 清空已选
        root.selectedSearchItems = ({})
        controller.searchXSou(q, root.searchPage, root.searchLimit)
    }

    // 安全判断某条搜索结果是否已被选中（避免 modelData/selectedSearchItems
    // 在 delegate 销毁或属性重置期间为 undefined 导致布尔绑定警告）
    function _isSearchSelected(tweet_id) {
        var sel = root.selectedSearchItems
        if (!sel || tweet_id === undefined || tweet_id === null) return false
        return sel[tweet_id] === true
    }

    function _toggleSearchSelect(item) {
        if (!item || !item.tweet_id) return
        var sel = root.selectedSearchItems
        if (!sel) { sel = ({}) }
        if (sel[item.tweet_id]) {
            delete sel[item.tweet_id]
        } else {
            sel[item.tweet_id] = true
        }
        // 触发引用变更通知（QML var 属性需要重新赋值才刷新绑定）
        root.selectedSearchItems = sel
    }

    function _enqueueSelectedSearch() {
        if (typeof controller === "undefined" || !controller) return
        var sel = root.selectedSearchItems
        var keys = Object.keys(sel)
        if (keys.length === 0) return

        var enqueued = 0
        for (var i = 0; i < root.searchResults.length; i++) {
            var r = root.searchResults[i]
            if (!sel[r.tweet_id]) continue
            if (!r.video_url || r.video_url.length === 0) continue
            // X-Sou 直链：video.twimg.com 永久有效，直接入队
            // task.url 用推文 URL 仅作历史/去重，下载走 direct_url
            var tweetUrl = "https://x.com/i/web/status/" + r.tweet_id
            controller.addDirectDownloadTask(
                r.video_url,
                r.content ? r.content.substring(0, 80) : ("X-Sou " + r.tweet_id),
                "x",
                r.video_cover || "",
                true,  // is_video=true（X-Sou 是视频直链）
                ""     // author 未知
            )
            enqueued++
        }

        if (enqueued > 0) {
            showToast(tr("added_to_queue") + " (" + enqueued + ")")
            // 清空已选
            root.selectedSearchItems = ({})
        } else {
            showToast(tr("video_not_available"))
        }
    }

    function _enqueue() {
        if (!root.previewInfo) return
        if (typeof controller === "undefined" || !controller) return

        // 检查重复
        var url = root.previewInfo.url
        if (controller.checkUrlDuplicate(url)) {
            // 重复仍允许下载，但给提示
            showToast(tr("dup_message"))
        }

        controller.addDownloadTask(
            JSON.stringify(root.previewInfo),
            root.selectedFormatId,
            root.selectedFormatType,
            root.customName,
            ""  // output_dir 留空使用默认
        )
    }

    function _formatDuration(sec) {
        if (!sec || sec <= 0) return "00:00"
        var m = Math.floor(sec / 60)
        var s = Math.floor(sec % 60)
        return (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s
    }

    function _getVersion() {
        try {
            // controller 没有暴露 version，使用配置 + 静态字符串
            return "v4.2"
        } catch (e) {
            return ""
        }
    }

    // ============================================================
    // X-Sou 视频预览（先下载到 cache/preview 再播放本地文件）
    // ============================================================
    function _previewXVideo(video_url) {
        if (!video_url || video_url.length === 0) {
            showToast(tr("video_not_available"))
            return
        }
        if (typeof controller === "undefined" || !controller) return
        // 显示进度提示
        _previewProgressDialog.visible = true
        _previewProgressDialog._progress = 0
        _previewProgressDialog._label = tr("x_sou_preview_caching")
        controller.previewXVideo(video_url)
    }

    // 监听 controller 预览信号
    Connections {
        target: typeof controller !== "undefined" ? controller : null
        function onPreviewProgress(downloaded, total) {
            if (total > 0) {
                _previewProgressDialog._progress = Math.floor(downloaded * 100 / total)
                var mb_done = downloaded / 1024 / 1024
                var mb_total = total / 1024 / 1024
                _previewProgressDialog._label = tr("x_sou_preview_caching")
                    + "\n" + mb_done.toFixed(1) + " / " + mb_total.toFixed(1) + " MB"
            } else {
                var mb = downloaded / 1024 / 1024
                _previewProgressDialog._label = tr("x_sou_preview_caching")
                    + "\n" + mb.toFixed(1) + " MB"
            }
        }
        function onPreviewReady(local_path) {
            _previewProgressDialog.visible = false
            _videoPreviewDlg.openWithUrl(local_path)
        }
        function onPreviewFailed(error_message) {
            _previewProgressDialog.visible = false
            if (error_message === "cancelled") {
                showToast(tr("x_sou_preview_cancelled"))
            } else {
                showToast(tr("x_sou_preview_failed").replace("{err}", error_message))
            }
        }
    }

    // 预览进度对话框
    Dialog {
        id: _previewProgressDialog
        visible: false
        modal: true
        anchors.centerIn: parent
        width: 360
        height: 140
        padding: 0
        property int _progress: 0
        property string _label: ""

        background: Rectangle {
            radius: Theme.rLG
            color: Theme.theme === "dark" ? Qt.rgba(20/255, 22/255, 38/255, 0.98)
                                          : Qt.rgba(255/255, 255/255, 255/255, 0.98)
            border.width: 1
            border.color: Theme.glassBorderHi
        }

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 24
            spacing: 12

            Text {
                Layout.fillWidth: true
                text: _previewProgressDialog._label
                color: Theme.textPrimary
                font.family: Theme.fontBody
                font.pixelSize: Theme.fsBody
                wrapMode: Text.WordWrap
            }
            ProgressBar {
                Layout.fillWidth: true
                from: 0; to: 100
                value: _previewProgressDialog._progress
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                Button {
                    text: tr("cancel")
                    variant: "ghost"
                    onClicked: {
                        if (typeof controller !== "undefined" && controller) {
                            controller.cancelPreview()
                        }
                        _previewProgressDialog.visible = false
                    }
                }
            }
        }
    }

    // 视频预览对话框
    VideoPreviewDialog {
        id: _videoPreviewDlg
    }
}
