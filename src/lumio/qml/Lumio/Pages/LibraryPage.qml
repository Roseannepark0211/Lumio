// ============================================================
// LUMIO // LibraryPage — 素材库页
// ------------------------------------------------------------
// 真实对接 controller:
//   - getLibraryJson() / getCollectionsJson()
//   - toggleFavorite(item_id) / deleteLibraryItem(item_id)
//   - createCollection(name) / deleteCollection(id)
//   - libraryChanged 信号 → 刷新
// 布局：Collections 左侧栏 + 媒体网格 3 列
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
    property var collections: []
    property string searchText: ""
    property string filterPlatform: "all"
    property string filterType: "all"
    property bool filterFavorites: false
    property int activeCollectionId: -1   // -1 = All Items, -2 = Favorites

    Connections {
        target: typeof controller !== "undefined" ? controller : null
        function onLibraryChanged() { _reload() }
        // 文件缺失（被外部删除）→ 弹「是否删除本条记录」对话框
        function onFileMissing(path, source) {
            if (source !== "library") return
            _fileMissingDialog._missingPath = path
            _fileMissingDialog._missingItemId = _findItemIdByPath(path)
            _fileMissingDialog.open()
        }
    }

    Component.onCompleted: _reload()

    // 按 file_path 反查 item_id（用于文件缺失时定位待删除的素材）
    function _findItemIdByPath(path) {
        for (var i = 0; i < root.items.length; i++) {
            if (root.items[i].file_path === path) return root.items[i].id
        }
        return ""
    }

    function _reload() {
        if (typeof controller === "undefined" || !controller) return
        try {
            root.items = JSON.parse(controller.getLibraryJson())
            root.collections = JSON.parse(controller.getCollectionsJson())
            _applyFilter()
        } catch (e) {
            console.log("[LibraryPage] reload failed:", e)
        }
    }

    function _applyFilter() {
        var arr = root.items
        var q = root.searchText.toLowerCase()
        var fp = root.filterPlatform
        var ft = root.filterType
        var ff = root.filterFavorites
        var fc = root.activeCollectionId  // -1=全部, -2=收藏, >0=指定 Collection
        var out = []
        for (var i = 0; i < arr.length; i++) {
            var it = arr[i]
            if (ff && !it.is_favorite) continue
            if (fp !== "all" && it.platform !== fp) continue
            if (ft !== "all" && it.media_type !== ft) continue
            // Collection 筛选：仅当指定了具体 Collection 时生效
            if (fc > 0) {
                var cids = it.collection_ids || []
                if (cids.indexOf(fc) < 0) continue
            }
            if (q.length > 0) {
                var hay = ((it.title || "") + " " + (it.author || "") + " " + (it.url || "")).toLowerCase()
                if (hay.indexOf(q) < 0) continue
            }
            out.push(it)
        }
        _grid.model = out
    }

    function _formatSize(bytes) {
        if (!bytes || bytes <= 0) return "—"
        if (bytes < 1024) return bytes + " B"
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB"
        if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB"
        return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB"
    }

    // 同步更新 root.items 缓存中指定 item 的 is_favorite 字段。
    // toggleFavorite 不发 libraryChanged 信号（避免全量 reload 闪烁），
    // 但 root.items 是 _applyFilter 的数据源，如果不手动同步，
    // 切换到「收藏夹」视图时过滤用的还是旧 is_favorite，新收藏的项不会出现。
    function _updateItemFavoriteInCache(item_id, new_fav) {
        for (var i = 0; i < root.items.length; i++) {
            if (root.items[i].id === item_id) {
                // 创建新对象触发 QML 属性变更通知
                var newArr = root.items.slice()
                newArr[i] = Object.assign({}, root.items[i], { is_favorite: new_fav })
                root.items = newArr
                // 如果当前在收藏夹视图且取消了收藏，立即重新过滤移除该项
                if (root.filterFavorites && !new_fav) {
                    _applyFilter()
                }
                return
            }
        }
    }

    function _totalSize() {
        var s = 0
        for (var i = 0; i < root.items.length; i++) s += (root.items[i].file_size || 0)
        return s
    }

    function _createCollection() {
        var name = _newCollectionDialog.text
        if (name && name.length > 0 && controller) {
            controller.createCollection(name)
        }
        _newCollectionDialog.visible = false
    }

    // 显示「加入 Collection」菜单 — 以触发按钮为锚点定位
    // 菜单内：已加入的 Collection 显示 ✓ 标记，再次点击则移除（切换模式）
    function _showCollectionMenu(item_id, btn) {
        _collectionMenu._itemId = item_id
        // 拉取该项已加入的 Collection id 列表，用于显示 ✓ 标记
        if (controller) {
            try {
                _collectionMenu._joinedIds = JSON.parse(
                    controller.getItemCollectionsJson(item_id))
            } catch (e) {
                _collectionMenu._joinedIds = []
            }
        } else {
            _collectionMenu._joinedIds = []
        }
        if (btn) {
            // 以按钮右下角为弹出锚点，避免错位到左侧栏旁
            _collectionMenu.x = btn.mapToItem(root, 0, btn.height).x + (btn.width - _collectionMenu.width) / 2
            _collectionMenu.y = btn.mapToItem(root, 0, btn.height).y + 4
            _collectionMenu.open()
        } else {
            _collectionMenu.open()
        }
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 32
        spacing: 20

        // ============================================================
        // Collections Sidebar
        // ============================================================
        GlassCard {
            Layout.preferredWidth: 220
            Layout.fillHeight: true
            radius: Theme.rXL

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 4

                RowLayout {
                    Layout.fillWidth: true
                    Layout.bottomMargin: 12
                    Text {
                        text: tr("collections")
                        color: Theme.textMute
                        font.family: Theme.fontBody
                        font.pixelSize: Theme.fsMicro
                        font.weight: Font.DemiBold
                        font.letterSpacing: 1.2
                        Layout.fillWidth: true
                    }
                    Button {
                        iconName: "i-plus"; variant: "ghost"; iconSize: 14
                        onClicked: _newCollectionDialog.visible = true
                    }
                }

                // All Items
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 36
                    radius: Theme.rSM
                    color: root.activeCollectionId === -1 ? Theme.glassBgHi : "transparent"

                    Row {
                        anchors.left: parent.left
                        anchors.leftMargin: 10
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 10
                        Icon { name: "i-library"; size: 14; color: root.activeCollectionId === -1 ? Theme.textPrimary : Theme.textMute; anchors.verticalCenter: parent.verticalCenter }
                        Text { text: tr("all_items"); color: root.activeCollectionId === -1 ? Theme.textPrimary : Theme.textMute; font.family: Theme.fontBody; font.pixelSize: Theme.fsSmall; anchors.verticalCenter: parent.verticalCenter }
                    }
                    Text {
                        anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
                        text: root.items.length
                        color: Theme.textDim; font.family: Theme.fontMono; font.pixelSize: Theme.fsMicro
                    }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: { root.activeCollectionId = -1; root.filterFavorites = false; _applyFilter() } }
                }

                // Favorites
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 36
                    radius: Theme.rSM
                    color: root.activeCollectionId === -2 ? Theme.glassBgHi : "transparent"

                    Row {
                        anchors.left: parent.left
                        anchors.leftMargin: 10
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 10
                        Icon { name: "i-heart"; size: 14; color: root.activeCollectionId === -2 ? Theme.textPrimary : Theme.textMute; anchors.verticalCenter: parent.verticalCenter }
                        Text { text: tr("favorites"); color: root.activeCollectionId === -2 ? Theme.textPrimary : Theme.textMute; font.family: Theme.fontBody; font.pixelSize: Theme.fsSmall; anchors.verticalCenter: parent.verticalCenter }
                    }
                    Text {
                        anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
                        text: root.items.filter(function(it) { return it.is_favorite }).length
                        color: Theme.textDim; font.family: Theme.fontMono; font.pixelSize: Theme.fsMicro
                    }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: { root.activeCollectionId = -2; root.filterFavorites = true; _applyFilter() } }
                }

                Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.glassBorder; Layout.topMargin: 8; Layout.bottomMargin: 8 }

                // User Collections
                // 注意：修复清单问题 2 — 老版本支持右键菜单（重命名/删除），现版本缺失。
                // 加 acceptedButtons: Qt.LeftButton | Qt.RightButton + onPressAndHold 触发菜单。
                Repeater {
                    model: root.collections

                    delegate: Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 36
                        radius: Theme.rSM
                        color: root.activeCollectionId === modelData.id ? Theme.glassBgHi : "transparent"

                        Row {
                            anchors.left: parent.left
                            anchors.leftMargin: 10
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 10
                            Icon { name: "i-folder"; size: 14; color: root.activeCollectionId === modelData.id ? Theme.textPrimary : Theme.textMute; anchors.verticalCenter: parent.verticalCenter }
                            Text {
                                text: modelData.name
                                color: root.activeCollectionId === modelData.id ? Theme.textPrimary : Theme.textMute
                                font.family: Theme.fontBody; font.pixelSize: Theme.fsSmall
                                anchors.verticalCenter: parent.verticalCenter
                                elide: Text.ElideRight
                                width: 100
                            }
                        }
                        Text {
                            anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
                            text: modelData.count
                            color: Theme.textDim; font.family: Theme.fontMono; font.pixelSize: Theme.fsMicro
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            acceptedButtons: Qt.LeftButton | Qt.RightButton
                            // 左键：切换分类
                            onClicked: function(mouse) {
                                if (mouse.button === Qt.LeftButton) {
                                    root.activeCollectionId = modelData.id
                                    root.filterFavorites = false
                                    _applyFilter()
                                } else if (mouse.button === Qt.RightButton) {
                                    _showCollectionCtxMenu(modelData.id, modelData.name, this)
                                }
                            }
                            // 长按（移动端兼容）：弹出菜单
                            onPressAndHold: _showCollectionCtxMenu(modelData.id, modelData.name, this)
                        }
                    }
                }

                Item { Layout.fillHeight: true }
            }
        }

        // ============================================================
        // Media Grid
        // ============================================================
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 16

            // ============================================================
            // 视觉中心：PageHeader
            // ============================================================
            PageHeader {
                Layout.fillWidth: true
                title: tr("library_page")
                subtitle: tr("library_subtitle")
                icon: "i-library"

                // 右侧操作区
                Rectangle {
                    width: _libBadge.implicitWidth + 20
                    height: 22
                    radius: Theme.rPill
                    color: Qt.rgba(94/255, 92/255, 230/255, 0.12)
                    border.width: 1
                    border.color: Qt.rgba(94/255, 92/255, 230/255, 0.3)

                    Row {
                        id: _libBadge
                        anchors.centerIn: parent
                        spacing: 6

                        Rectangle { width: 5; height: 5; radius: 2.5; color: Theme.accent2; anchors.verticalCenter: parent.verticalCenter }

                        Text {
                            text: root.items.length + " " + tr("items") + " · " + _formatSize(_totalSize())
                            color: "#a8c7ff"
                            font.family: Theme.fontMono
                            font.pixelSize: Theme.fsMicro
                            font.letterSpacing: 0.5
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
            }

            // Filter bar
            GlassCard {
                Layout.fillWidth: true
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
                        Layout.preferredWidth: 140
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
                        textRole: "label"; valueRole: "value"
                        onActivated: { root.filterPlatform = currentValue; _applyFilter() }
                    }

                    LumioComboBox {
                        Layout.preferredWidth: 120
                        currentIndex: 0
                        model: [
                            { value: "all",   label: tr("all_types") },
                            { value: "video", label: tr("fmt_video") },
                            { value: "audio", label: tr("fmt_audio") },
                            { value: "image", label: tr("library_filter_image") }
                        ]
                        textRole: "label"; valueRole: "value"
                        onActivated: { root.filterType = currentValue; _applyFilter() }
                    }

                    Button {
                        text: tr("library_reset_filters"); variant: "ghost"
                        onClicked: {
                            root.searchText = ""
                            root.filterPlatform = "all"
                            root.filterType = "all"
                            root.filterFavorites = false
                            root.activeCollectionId = -1
                            _applyFilter()
                        }
                    }
                }
            }

            // 空状态
            Text {
                visible: root.items.length === 0
                Layout.fillWidth: true
                Layout.topMargin: 80
                text: tr("no_library_items")
                color: Theme.textMute
                font.family: Theme.fontBody
                font.pixelSize: Theme.fsBody
                horizontalAlignment: Text.AlignHCenter
            }

            // Media grid — 固定 3 列布局
            // 用户要求：
            //   1) 封面区固定高度宽度，PreserveAspectCrop 等比裁剪填充
            //   2) 卡片固定总高度宽度，底部操作栏锚定底部
            //   3) 网格容器强制统一单元格行高
            //   4) 文本开启省略规则，禁止内容撑高卡片
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                leftPadding: 4
                rightPadding: 4
                topPadding: 4
                bottomPadding: 4

                GridLayout {
                    width: parent.width - 8  // 抵消 ScrollView padding
                    // 固定 3 列，每列 fillWidth 均分
                    columns: 3
                    rowSpacing: 24
                    columnSpacing: 24

                    Repeater {
                        id: _grid
                        model: []

                        delegate: GlassCard {
                            // 强制统一单元格行高：fillWidth + 固定 height
                            Layout.fillWidth: true
                            Layout.preferredHeight: 260
                            Layout.maximumHeight: 260
                            Layout.minimumHeight: 260
                            radius: Theme.rLG
                            // GlassCard clip 防止任何子元素溢出
                            clip: true

                            // 本地收藏状态：点击后立即翻转，不等 libraryChanged 信号
                            // （toggleFavorite 不再发信号，避免全量 reload 导致所有卡片闪烁）
                            property bool isFav: modelData.is_favorite === true

                            // 卡片内容用 anchors 布局（非 ColumnLayout），确保固定尺寸
                            // 封面区锚定顶部+左右，操作栏锚定底部
                            Item {
                                anchors.fill: parent

                                // ---- 封面区（固定高度 150，左右各留 10 margin） ----
                                Rectangle {
                                    id: _thumb
                                    anchors.top: parent.top
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.topMargin: 10
                                    anchors.leftMargin: 10
                                    anchors.rightMargin: 10
                                    height: 150
                                    radius: Theme.rMD
                                    color: Qt.rgba(0, 0, 0, 0.3)
                                    clip: true  // 封面裁剪，防止 PreserveAspectCrop 溢出

                                    Image {
                                        anchors.fill: parent
                                        source: {
                                            var local = modelData.local_thumbnail_path || ""
                                            if (local.length > 0) return local
                                            var remote = modelData.thumbnail_url || ""
                                            if (remote.length === 0) return ""
                                            if (typeof controller !== "undefined" && controller) {
                                                return controller.thumbUrl(remote)
                                            }
                                            return remote
                                        }
                                        // 等比裁剪填充：图片填满 Rectangle，超出部分裁掉
                                        fillMode: Image.PreserveAspectCrop
                                        asynchronous: true
                                        cache: false
                                        visible: (modelData.local_thumbnail_path && modelData.local_thumbnail_path.length > 0)
                                                 || (modelData.thumbnail_url && modelData.thumbnail_url.length > 0)
                                    }

                                    Icon {
                                        anchors.centerIn: parent
                                        name: modelData.media_type === "audio" ? "i-audio"
                                              : (modelData.media_type === "image" ? "i-image" : "i-video")
                                        size: 32
                                        color: "#ffffff"
                                        opacity: 0.6
                                        visible: !((modelData.local_thumbnail_path && modelData.local_thumbnail_path.length > 0)
                                                  || (modelData.thumbnail_url && modelData.thumbnail_url.length > 0))
                                    }

                                    // 收藏按钮（右上）
                                    Rectangle {
                                        anchors.top: parent.top; anchors.right: parent.right; anchors.margins: 6
                                        width: 24; height: 24; radius: 12
                                        color: Qt.rgba(0, 0, 0, 0.5)
                                        Icon {
                                            anchors.centerIn: parent
                                            name: "i-heart"
                                            size: 12
                                            // 绑定到本地 isFav（点击立即翻转，不等信号）
                                            color: isFav ? Theme.danger : "#888888"
                                        }
                                        MouseArea {
                                            anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                            onClicked: {
                                                if (controller) {
                                                    // 立即翻转本地状态（UI 即时响应）
                                                    isFav = !isFav
                                                    // 调后端持久化（不再触发 libraryChanged 全量刷新）
                                                    controller.toggleFavorite(modelData.id)
                                                    // 同步更新 root.items 缓存中该项的 is_favorite，
                                                    // 否则切换到「收藏夹」视图时 _applyFilter 用的还是旧数据，
                                                    // 会导致新收藏的项不显示在收藏夹里。
                                                    _updateItemFavoriteInCache(modelData.id, isFav)
                                                }
                                            }
                                        }
                                    }
                                }

                                // ---- 信息区（封面下方，操作栏上方） ----
                                // 不用 ColumnLayout，用 anchors 逐行锚定，固定每行高度
                                // 标题行：封面下方 +10
                                Text {
                                    id: _titleText
                                    anchors.top: _thumb.bottom
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.topMargin: 10
                                    anchors.leftMargin: 12
                                    anchors.rightMargin: 12
                                    text: modelData.title || tr("untitled")
                                    color: Theme.textPrimary
                                    font.family: Theme.fontDisplay
                                    font.pixelSize: Theme.fsSmall
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                    maximumLineCount: 1
                                }

                                // 作者+大小行：标题下方 +4
                                Text {
                                    id: _authorText
                                    anchors.top: _titleText.bottom
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.topMargin: 4
                                    anchors.leftMargin: 12
                                    anchors.rightMargin: 12
                                    text: (modelData.author || "—") + "  ·  "
                                          + _formatSize(modelData.file_size)
                                    color: Theme.textMute
                                    font.family: Theme.fontMono
                                    font.pixelSize: Theme.fsMicro
                                    elide: Text.ElideRight
                                    maximumLineCount: 1
                                }

                                // 平台 + 媒体类型徽章行：作者下方 +6（两个并列，避免平台徽章挡封面）
                                Row {
                                    id: _badgeRow
                                    anchors.top: _authorText.bottom
                                    anchors.left: parent.left
                                    anchors.topMargin: 6
                                    anchors.leftMargin: 12
                                    spacing: 4

                                    // 平台徽章
                                    Rectangle {
                                        visible: (modelData.platform || "").length > 0
                                        width: visible ? (_platText.implicitWidth + 10) : 0
                                        height: 16
                                        radius: Theme.rXS
                                        color: Qt.rgba(0, 0, 0, 0.4)
                                        Text {
                                            id: _platText
                                            anchors.centerIn: parent
                                            text: Theme.platformLabel(modelData.platform)
                                            color: Theme.platformColor(modelData.platform)
                                            font.family: Theme.fontMono
                                            font.pixelSize: 9
                                            font.weight: Font.DemiBold
                                        }
                                    }

                                    // 媒体类型徽章
                                    Rectangle {
                                        id: _typeBadge
                                        visible: (modelData.media_type || "").length > 0
                                        width: visible ? (_typeText.implicitWidth + 10) : 0
                                        height: 16
                                        radius: Theme.rXS
                                        color: {
                                            var t = modelData.media_type || ""
                                            if (t === "video") return Qt.rgba(10/255, 132/255, 1, 0.18)
                                            if (t === "image") return Qt.rgba(94/255, 230/255, 180/255, 0.18)
                                            if (t === "audio") return Qt.rgba(230/255, 180/255, 60/255, 0.18)
                                            return Qt.rgba(180/255, 100/255, 230/255, 0.18)
                                        }
                                        Text {
                                            id: _typeText
                                            anchors.centerIn: parent
                                            text: {
                                                var t = modelData.media_type || ""
                                                var m = {"video": tr("fmt_video"),
                                                         "image": tr("library_filter_image"),
                                                         "audio": tr("fmt_audio"),
                                                         "mixed": tr("media_mixed")}
                                                return m[t] || t.toUpperCase()
                                            }
                                            color: {
                                                var t = modelData.media_type || ""
                                                if (t === "video") return Theme.accent
                                                if (t === "image") return Theme.success
                                                if (t === "audio") return Theme.warning
                                                return Theme.accent2
                                            }
                                            font.family: Theme.fontMono
                                            font.pixelSize: 9
                                            font.weight: Font.DemiBold
                                        }
                                    }
                                }

                                // ---- 操作栏（锚定卡片底部） ----
                                Row {
                                    id: _actionBar
                                    anchors.bottom: parent.bottom
                                    anchors.left: parent.left
                                    anchors.bottomMargin: 8
                                    anchors.leftMargin: 8
                                    spacing: 2

                                    // 显式设定 Button 尺寸，避免无 text 时 implicitWidth=0 导致点击区域过小
                                    Button {
                                        iconName: "i-play"; variant: "ghost"; iconSize: 16
                                        text: ""
                                        implicitWidth: 36
                                        implicitHeight: 28
                                        // 传 source="library"：文件缺失时弹「是否删除本条记录」对话框
                                        onClicked: {
                                            if (controller) controller.openFileFromSource(modelData.file_path, "library")
                                        }
                                    }
                                    Button {
                                        iconName: "i-folder"; variant: "ghost"; iconSize: 16
                                        text: ""
                                        implicitWidth: 36
                                        implicitHeight: 28
                                        onClicked: {
                                            if (controller) controller.openFolderFromSource(modelData.file_path, "library")
                                        }
                                    }
                                    Button {
                                        id: _addColBtn
                                        // 当处于具体分类视图下且该项已属于当前分类时，
                                        // 图标变为 ×，点击则从当前分类移除；
                                        // 否则保持 + 图标，点击弹出「加入分类」菜单。
                                        iconName: (root.activeCollectionId > 0
                                                    && (modelData.collection_ids || [])
                                                       .indexOf(root.activeCollectionId) >= 0)
                                                  ? "i-close"
                                                  : "i-folder-add"
                                        variant: "ghost"; iconSize: 16
                                        text: ""
                                        implicitWidth: 36
                                        implicitHeight: 28
                                        onClicked: {
                                            if (root.activeCollectionId > 0
                                                && (modelData.collection_ids || [])
                                                   .indexOf(root.activeCollectionId) >= 0) {
                                                // 当前在分类视图下且属于该分类 → 从当前分类移除
                                                if (controller) {
                                                    controller.removeItemFromCollection(
                                                        modelData.id, root.activeCollectionId)
                                                }
                                            } else {
                                                _showCollectionMenu(modelData.id, _addColBtn)
                                            }
                                        }
                                    }
                                    Item { width: 4; height: 1 }
                                    Button {
                                        iconName: "i-trash"; variant: "ghost"; iconSize: 16
                                        text: ""
                                        implicitWidth: 36
                                        implicitHeight: 28
                                        onClicked: { if (controller) controller.deleteLibraryItem(modelData.id) }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // 新建 Collection 对话框
    Dialog {
        id: _newCollectionDialog
        visible: false
        modal: true
        anchors.centerIn: parent
        title: tr("collection_create")
        width: 360

        property string text: ""

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
            Input {
                Layout.fillWidth: true
                placeholderText: tr("collection_name_label")
                text: _newCollectionDialog.text
                onTextChanged: _newCollectionDialog.text = text
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Item { Layout.fillWidth: true }
                Button {
                    text: tr("cancel"); variant: "ghost"
                    onClicked: _newCollectionDialog.visible = false
                }
                Button {
                    text: tr("apply"); variant: "primary"
                    onClicked: _createCollection()
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
        property string _missingItemId: ""

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
                    enabled: _fileMissingDialog._missingItemId.length > 0
                    onClicked: {
                        if (controller && _fileMissingDialog._missingItemId.length > 0) {
                            controller.deleteLibraryItem(_fileMissingDialog._missingItemId)
                        }
                        _fileMissingDialog.visible = false
                    }
                }
            }
        }
    }

    // 「加入 Collection」菜单 — 自定义深色毛玻璃样式
    // 切换模式：已加入的显示 ✓，点击移除；未加入的点击添加
    Menu {
        id: _collectionMenu
        property string _itemId: ""
        property var _joinedIds: []  // 该项已加入的 Collection id 列表
        // 固定宽度，确保 _showCollectionMenu 中 x 计算正确（避免 width=0 导致偏移）
        width: 220

        // 自定义背景：圆角 + 半透明深色 + 边框，匹配整体 UI 风格
        background: Rectangle {
            radius: Theme.rMD
            color: Theme.theme === "dark" ? Qt.rgba(20/255, 22/255, 38/255, 0.95)
                                          : Qt.rgba(255/255, 255/255, 255/255, 0.95)
            border.width: 1
            border.color: Theme.glassBorderHi
            layer.enabled: true
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: Qt.rgba(0, 0, 0, 0.3)
                shadowBlur: 0.6
                shadowVerticalOffset: 4
            }
        }

        // 顶部固定项：新建 Collection
        // 注意：MenuItem 没有 highlighted 属性（仅 ItemDelegate/ComboBox delegate 才有）
        // MenuItem.background 是 Rectangle，不在 MenuItem 的 visual tree 中，
        // QML 无法隐式查找 MenuItem.hovered —— 必须用 parent.hovered 显式引用
        // （Rectangle.parent == MenuItem 本身）
        MenuItem {
            text: tr("collection_create")
            height: 34
            background: Rectangle {
                radius: Theme.rXS
                // 浅色模式下避免 glassBgHi 闪烁，用轻微暗化色
                color: parent.hovered
                       ? (Theme.theme === "dark" ? Theme.accentSoft : Qt.rgba(0, 0, 0, 0.04))
                       : "transparent"
                Behavior on color { ColorAnimation { duration: 150 } }
            }
            contentItem: Text {
                leftPadding: 14
                rightPadding: 14
                text: tr("collection_create")
                color: parent.hovered ? Theme.accent : Theme.textPrimary
                font.family: Theme.fontBody
                font.pixelSize: Theme.fsSmall
                verticalAlignment: Text.AlignVCenter
            }
            onTriggered: _newCollectionDialog.visible = true
        }

        MenuSeparator {
            contentItem: Rectangle {
                implicitHeight: 1
                color: Theme.glassBorder
            }
        }

        // 动态生成已有 Collection 列表（切换模式：✓ = 已加入，点击移除；无 ✓ = 未加入，点击添加）
        Instantiator {
            model: root.collections
            delegate: MenuItem {
                id: _colItem
                height: 34
                // 判断该 Collection 是否已包含当前素材
                property bool _isJoined: _collectionMenu._joinedIds.indexOf(modelData.id) >= 0
                background: Rectangle {
                    radius: Theme.rXS
                    // 浅色模式下 glassBgHi 是 rgba(255,255,255,0.9) 几乎无对比度，
                    // hover 时会导致闪烁。改用轻微暗化色，对比度明显且稳定。
                    color: parent.hovered
                           ? (Theme.theme === "dark" ? Theme.glassBgHi : Qt.rgba(0, 0, 0, 0.04))
                           : "transparent"
                    Behavior on color { ColorAnimation { duration: 150 } }
                }
                contentItem: Item {
                    anchors.fill: parent
                    // 用 Row + 显式 anchors.verticalCenter 布局
                    Row {
                        anchors.left: parent.left
                        anchors.leftMargin: 14
                        anchors.right: parent.right
                        anchors.rightMargin: 14
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 8

                        // ✓ 标记（已加入时显示）
                        Text {
                            text: "✓"
                            color: Theme.success
                            font.family: Theme.fontMono
                            font.pixelSize: Theme.fsSmall
                            font.weight: Font.Bold
                            visible: _colItem._isJoined
                            width: visible ? 14 : 0
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            text: modelData.name + "  (" + modelData.count + ")"
                            color: _colItem.hovered ? Theme.accent : Theme.textPrimary
                            font.family: Theme.fontBody
                            font.pixelSize: Theme.fsSmall
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
                onTriggered: {
                    if (controller && _collectionMenu._itemId.length > 0) {
                        // 切换：已加入 → 移除；未加入 → 添加
                        if (_isJoined) {
                            controller.removeItemFromCollection(_collectionMenu._itemId, modelData.id)
                        } else {
                            controller.addItemToCollection(_collectionMenu._itemId, modelData.id)
                        }
                    }
                }
            }
            onObjectAdded: (index, object) => _collectionMenu.insertItem(index + 2, object)
            onObjectRemoved: (index, object) => _collectionMenu.removeItem(object)
        }
    }

    // ============================================================
    // Collection 右键菜单（重命名/删除）— 修复清单问题 2
    // ============================================================
    Menu {
        id: _collectionCtxMenu
        property int _cid: -1
        property string _cname: ""

        width: 180

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

        MenuItem {
            text: tr("collection_rename")
            height: 34
            background: Rectangle {
                radius: Theme.rXS
                color: parent.hovered ? Theme.glassBgHi : "transparent"
                Behavior on color { ColorAnimation { duration: 100 } }
            }
            contentItem: Text {
                leftPadding: 14
                rightPadding: 14
                text: tr("collection_rename")
                color: parent.hovered ? Theme.accent : Theme.textPrimary
                font.family: Theme.fontBody
                font.pixelSize: Theme.fsSmall
                verticalAlignment: Text.AlignVCenter
            }
            onTriggered: {
                _renameCollectionDialog._cid = _collectionCtxMenu._cid
                _renameCollectionDialog.text = _collectionCtxMenu._cname
                _renameCollectionDialog.visible = true
            }
        }

        MenuItem {
            text: tr("collection_delete")
            height: 34
            background: Rectangle {
                radius: Theme.rXS
                color: parent.hovered ? Qt.rgba(255/255, 59/255, 92/255, 0.15) : "transparent"
                Behavior on color { ColorAnimation { duration: 100 } }
            }
            contentItem: Text {
                leftPadding: 14
                rightPadding: 14
                text: tr("collection_delete")
                color: parent.hovered ? Theme.danger : Theme.textPrimary
                font.family: Theme.fontBody
                font.pixelSize: Theme.fsSmall
                verticalAlignment: Text.AlignVCenter
            }
            onTriggered: {
                if (controller && _collectionCtxMenu._cid > 0) {
                    controller.deleteCollection(_collectionCtxMenu._cid)
                }
            }
        }
    }

    // 重命名 Collection 对话框
    Dialog {
        id: _renameCollectionDialog
        visible: false
        modal: true
        anchors.centerIn: parent
        width: 360
        height: 180
        padding: 0
        property int _cid: -1
        property string text: ""

        background: Rectangle {
            radius: Theme.rLG
            color: Theme.theme === "dark" ? Qt.rgba(20/255, 22/255, 38/255, 0.98)
                                          : Qt.rgba(255/255, 255/255, 255/255, 0.98)
            border.width: 1
            border.color: Theme.glassBorderHi
        }

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 12

            Text {
                text: tr("collection_rename")
                color: Theme.textPrimary
                font.family: Theme.fontDisplay
                font.pixelSize: Theme.fsH3
                font.weight: Font.DemiBold
            }

            Input {
                Layout.fillWidth: true
                text: _renameCollectionDialog.text
                onTextChanged: _renameCollectionDialog.text = text
                focus: true
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Item { Layout.fillWidth: true }
                Button {
                    text: tr("cancel")
                    variant: "ghost"
                    onClicked: _renameCollectionDialog.visible = false
                }
                Button {
                    text: tr("apply")
                    variant: "primary"
                    enabled: _renameCollectionDialog.text.length > 0
                    onClicked: {
                        if (controller && _renameCollectionDialog._cid > 0
                                && _renameCollectionDialog.text.length > 0) {
                            controller.renameCollection(
                                _renameCollectionDialog._cid,
                                _renameCollectionDialog.text
                            )
                        }
                        _renameCollectionDialog.visible = false
                    }
                }
            }
        }
    }

    function _showCollectionCtxMenu(cid, cname, mouseArea) {
        _collectionCtxMenu._cid = cid
        _collectionCtxMenu._cname = cname
        // 以鼠标位置为基准弹出
        var pos = mouseArea ? mouseArea.mapToItem(root, mouseArea.mouseX, mouseArea.mouseY) : null
        if (pos) {
            _collectionCtxMenu.x = pos.x
            _collectionCtxMenu.y = pos.y
            _collectionCtxMenu.open()
        } else {
            _collectionCtxMenu.open()
        }
    }
}
