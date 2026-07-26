// ============================================================
// LUMIO // SettingsPage — 设置页（竖向单列）
// ------------------------------------------------------------
// 设计规范参考：Lumio V4.2 设置页 UI 重构修复方案.md
//   - 竖向单列布局：所有卡片纵向排列，占满宽度
//   - 分组：账号 / 下载 / 系统
//   - 视觉中心：PageHeader（大标题 30 + 副标题）
//   - 卡片统一规范：SettingsCard（图标+标题+描述+内容槽）
//   - 控件统一对齐：Label 宽度 120 + 控件 fillWidth
// ============================================================
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import Lumio
import Lumio.Components

Item {
    id: root

    property var config: ({})
    property var cacheStats: ({})
    property string cookieStatus: "missing"
    property var cookieStatuses: ({})  // 各平台单独状态（修复清单问题 4）
    property string updateStatus: ""
    property var tgState: ({})  // Telegram 状态（修复清单问题 3）
    property string tgValidateStatus: ""  // Telegram 验证结果
    property bool tgValidating: false
    property var apifyState: ({})  // Apify 配置状态
    property string apifyValidateStatus: ""  // Apify 验证结果
    property bool apifyValidating: false
    property var apifyUsage: ({})  // Apify 月度用量（usage_usd / plan_credits_usd / plan_name）

    Connections {
        target: typeof controller !== "undefined" ? controller : null
        function onConfigChanged() { _reload() }
        // 额度查询完成（后台异步）→ 刷新 UI
        function onApifyUsageUpdated(usage_json) {
            try {
                root.apifyUsage = JSON.parse(usage_json)
            } catch (e) {
                console.log("[SettingsPage] apifyUsage parse failed:", e)
            }
        }
    }

    Component.onCompleted: _reload()

    function _reload() {
        if (typeof controller === "undefined" || !controller) return
        try {
            var cfg = JSON.parse(controller.getConfigJson())
            root.config = cfg
            root.cookieStatus = controller.getCookieStatus()
            // 修复清单问题 4：加载各平台单独的 cookie 状态
            try {
                root.cookieStatuses = JSON.parse(controller.getCookieStatusesJson())
            } catch (e) {
                root.cookieStatuses = ({})
            }
            // 修复清单问题 3：加载 Telegram 状态（pair_code/bound_device）
            try {
                root.tgState = JSON.parse(controller.getTelegramStateJson())
            } catch (e) {
                root.tgState = ({})
            }
            // 加载 Apify 配置状态
            try {
                root.apifyState = JSON.parse(controller.getApifyStatusJson())
            } catch (e) {
                root.apifyState = ({})
            }
            try {
                root.cacheStats = JSON.parse(controller.getCacheStatsJson())
            } catch (e) {
                root.cacheStats = {}
            }
            // 当 Apify 已配置时，后台刷新月度用量（5 分钟内不重复）
            if (root.apifyState.connected === true
                && typeof controller.refreshApifyUsage === "function") {
                controller.refreshApifyUsage()
            }
        } catch (e) {
            console.log("[SettingsPage] reload failed:", e)
        }
    }

    function _save(key, value) {
        if (!controller) return
        controller.setConfig(key, JSON.stringify(value))
    }

    function _saveNested(parent_key, key, value) {
        if (!controller) return
        var obj = {}
        obj[key] = value
        controller.setNestedConfig(parent_key, JSON.stringify(obj))
    }

    function _formatSize(bytes) {
        if (!bytes || bytes <= 0) return "0 B"
        if (bytes < 1024) return bytes + " B"
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB"
        if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB"
        return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB"
    }

    function _browseDownloadDir() {
        if (!controller) return
        var f = controller.browseFolder()
        if (f && f.length > 0) _save("download_dir", f)
    }

    function _importCookie() {
        if (!controller) return
        // browseCookieFile 现在返回 JSON 路径数组字符串
        var pathsJson = controller.browseCookieFile()
        var paths = []
        try { paths = JSON.parse(pathsJson) } catch (e) { paths = [] }
        if (paths.length > 0) {
            // importCookieFile 接收 JSON 路径数组字符串，支持批量导入
            var result = controller.importCookieFile(pathsJson)
            if (result === "ok") {
                root.cookieStatus = controller.getCookieStatus()
                try {
                    root.cookieStatuses = JSON.parse(controller.getCookieStatusesJson())
                } catch (e) {}
            } else {
                controller.showToast(result)
            }
        }
    }

    function _clearCookie() {
        if (!controller) return
        _cookieClearDialog.visible = true
    }

    function _doClearCookie() {
        if (controller) controller.clearCookie()
        _cookieClearDialog.visible = false
        _refreshTimer.start()
    }

    // 修复清单问题 3：Telegram 验证/配对码/解绑
    function _validateTelegram() {
        if (!controller || root.tgValidating) return
        root.tgValidating = true
        root.tgValidateStatus = tr("telegram_validating")
        // 读取当前输入框的 token（如果是 ***configured*** 占位则用已保存的 token）
        var token = _tgTokenInput.text
        if (token === "••••••••••••••••") {
            // 占位符 → 用 config 中已保存的 token
            token = root.config.telegram_bot_token || ""
            if (token === "***configured***") token = ""
        }
        if (!token) {
            root.tgValidateStatus = tr("telegram_no_token")
            root.tgValidating = false
            return
        }
        var proxy = root.config.http_proxy || ""
        // 后台调用（validate_token 是同步的，会阻塞 — 用 WorkerScript? 暂用直调，验证通常 <3s）
        var resultJson = controller.validateTelegramToken(token, proxy)
        try {
            var r = JSON.parse(resultJson)
            if (r.ok) {
                root.tgValidateStatus = tr("telegram_validate_ok").replace("{username}", r.username || "")
                // 验证成功后保存 token + 自动生成配对码
                _save("telegram_bot_token", token)
                _regenPairCode()
            } else {
                root.tgValidateStatus = tr("telegram_validate_fail") + ": " + (r.error || "")
            }
        } catch (e) {
            root.tgValidateStatus = tr("telegram_validate_fail") + ": " + String(e)
        }
        root.tgValidating = false
    }

    // Apify 验证
    function _validateApify() {
        if (!controller || root.apifyValidating) return
        var token = _apifyTokenInput.text
        // 占位符 → 用 config 中已保存的 token
        if (token === "••••••••••••••••" || token.indexOf("apify_api_") === 0) {
            token = root.config.apify_token || ""
        }
        var actor = _apifyActorInput.text || (root.config.apify_ig_actor || "")
        if (!token) {
            root.apifyValidateStatus = tr("apify_token_empty")
            return
        }
        if (!actor) {
            root.apifyValidateStatus = tr("apify_actor_empty")
            return
        }
        root.apifyValidating = true
        root.apifyValidateStatus = tr("apify_validating")
        var resultJson = controller.validateApifyToken(token, actor)
        try {
            var r = JSON.parse(resultJson)
            if (r.ok) {
                root.apifyValidateStatus = "✅ " + tr("apify_connected")
            } else {
                root.apifyValidateStatus = "❌ " + (r.error || tr("apify_validate_fail"))
            }
        } catch (e) {
            root.apifyValidateStatus = "❌ " + String(e)
        }
        root.apifyValidating = false
        _refreshTimer.start()
    }

    function _regenPairCode() {
        if (!controller) return
        var code = controller.generateTelegramPairCode()
        if (code && code.indexOf("Error") !== 0) {
            try {
                root.tgState = JSON.parse(controller.getTelegramStateJson())
            } catch (e) {}
        } else {
            controller.showToast(code)
        }
    }

    function _copyPairCode() {
        if (!controller) return
        var code = (root.tgState.pair_code || "")
        if (code && code.length > 0) {
            controller.copyToClipboard(code)
            controller.showToast(tr("telegram_copied"))
        }
    }

    function _unlinkTelegram() {
        if (!controller) return
        _tgUnlinkDialog.visible = true
    }

    function _doUnlinkTelegram() {
        if (controller) controller.unlinkTelegramDevice()
        _tgUnlinkDialog.visible = false
        _refreshTimer.start()
    }

    function _cleanByRules() {
        if (controller) controller.cleanCacheByRules()
        _refreshTimer.start()
    }

    function _forceClear() { _forceDialog.visible = true }

    function _doForceClear() {
        if (controller) controller.forceClearCache()
        _forceDialog.visible = false
        _refreshTimer.start()
    }

    function _checkUpdate() {
        if (!controller) return
        root.updateStatus = tr("settings_update_checking")
        try {
            var json = controller.checkUpdate()
            var r = JSON.parse(json)
            if (r.error) {
                root.updateStatus = tr("settings_update_error").replace("{err}", r.error)
            } else if (r.has_update) {
                root.updateStatus = tr("settings_update_found").replace("{ver}", r.latest)
            } else {
                root.updateStatus = tr("settings_update_latest")
            }
        } catch (e) {
            root.updateStatus = tr("settings_update_error").replace("{err}", String(e))
        }
    }

    function _totalCacheSize() {
        var total = 0
        var stats = root.cacheStats || {}
        for (var k in stats) {
            // 跳过元数据键（_total 汇总 / _root 路径字符串 / error）
            if (k.charAt(0) === "_" || k === "error") continue
            var s = stats[k] || {}
            if (s.size_bytes) total += s.size_bytes
        }
        return total
    }

    function _cacheRootPath() {
        var stats = root.cacheStats || {}
        return stats._root || ""
    }

    Timer {
        id: _refreshTimer
        interval: 1500
        repeat: false
        onTriggered: _reload()
    }

    // 强制刷新 Apify 用量（绕过 5 分钟缓存）
    // 用户点「刷新」按钮时清空 root.apifyUsage 显示 loading，
    // 然后用此 Timer 延时调 controller.forceRefreshApifyUsage（强制查询）
    Timer {
        id: _quotaRefreshTimer
        interval: 100
        repeat: false
        onTriggered: {
            if (controller && typeof controller.forceRefreshApifyUsage === "function") {
                controller.forceRefreshApifyUsage()
            }
        }
    }

    // ============================================================
    // 滚动容器
    // ------------------------------------------------------------
    // 历史问题：
    //   - 原写法 `contentWidth: availableWidth` 中 availableWidth 作用域
    //     不明确（QML 解析为 undefined），导致 ScrollView 内部布局失效
    //   - 直接删除 contentWidth 会让 ScrollView 按内容 implicitWidth
    //     自动计算（300 卡片 + 64 边距 = 364），ColumnLayout 被压缩
    //     到 364px，Layout.fillWidth 失效 → 卡片内容拥挤
    //
    // 修复：用 `settingsScroll.width` 显式绑定（作用域无歧义），
    //   contentWidth = 视口宽度 → 禁止水平滚动 + 让 ColumnLayout
    //   拿到真实视口宽度，Layout.fillWidth 才能生效。
    // ============================================================
    ScrollView {
        id: settingsScroll
        anchors.fill: parent
        clip: true
        contentWidth: settingsScroll.width

        ColumnLayout {
            width: settingsScroll.width
            spacing: 20

            // ============================================================
            // 视觉中心：PageHeader
            // ============================================================
            PageHeader {
                Layout.fillWidth: true
                Layout.leftMargin: 32
                Layout.rightMargin: 32
                Layout.topMargin: 24
                title: tr("settings_page")
                subtitle: tr("settings_subtitle")
                icon: "i-settings"
            }

            // ============================================================
            // 分组：账号
            // ============================================================
            Text {
                Layout.fillWidth: true
                Layout.leftMargin: 32
                Layout.rightMargin: 32
                Layout.topMargin: 8
                text: tr("settings_group_account")
                color: Theme.textMute
                font.family: Theme.fontDisplay
                font.pixelSize: 13
                font.weight: Font.DemiBold
                font.letterSpacing: 1.5
            }

            // ---------- Cookie 管理 ----------
            SettingsCard {
                Layout.fillWidth: true
                Layout.leftMargin: 32
                Layout.rightMargin: 32
                title: tr("settings_cookie_section")
                desc: qsTr("IG/X/微博等平台访问凭证")
                icon: "i-cookie"
                iconColor: Theme.warning

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    // 总状态 + 操作按钮
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Text {
                            text: tr("cookie_status")
                            color: Theme.textMute
                            Layout.preferredWidth: 120
                        }
                        Badge {
                            // 修复清单问题 4：补全 expired/warning 状态显示
                            text: root.cookieStatus === "valid" ? tr("cookie_status_valid")
                                : root.cookieStatus === "warning" ? tr("cookie_status_warning")
                                : root.cookieStatus === "expired" ? tr("cookie_status_expired")
                                : tr("cookie_status_missing")
                            status: root.cookieStatus === "valid" ? "completed"
                                  : (root.cookieStatus === "warning" || root.cookieStatus === "expired")
                                    ? "warning" : "failed"
                        }
                        Item { Layout.fillWidth: true }
                        Button {
                            text: tr("cookie_clear_btn")
                            variant: "ghost"
                            iconName: "i-trash"
                            onClicked: _clearCookie()
                        }
                        Button {
                            text: tr("cookie_import_btn")
                            variant: "primary"
                            iconName: "i-download"
                            onClicked: _importCookie()
                        }
                    }

                    // Cookie 文件路径
                    Text {
                        Layout.fillWidth: true
                        text: (root.config.cookie_file || "").length > 0
                              ? (root.config.cookie_file || "")
                              : "—"
                        color: Theme.textDim
                        font.family: Theme.fontMono
                        font.pixelSize: 11
                        elide: Text.ElideMiddle
                    }

                    // 各平台单独状态（2×4 网格）
                    Text {
                        text: tr("cookie_per_platform")
                        color: Theme.textMute
                        font.pixelSize: 11
                        font.letterSpacing: 1.0
                        Layout.topMargin: 6
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 4
                        rowSpacing: 6
                        columnSpacing: 8

                        Repeater {
                            // 修复清单问题 4：让用户清楚知道哪个平台已导入、哪个还没导入
                            model: [
                                { key: "instagram",  label: tr("cookie_status_ig") },
                                { key: "x",          label: tr("cookie_status_x") },
                                { key: "youtube",    label: tr("cookie_status_yt") },
                                { key: "weibo",      label: tr("cookie_status_wb") },
                                { key: "douyin",     label: tr("cookie_status_dy") },
                                { key: "xiaohongshu",label: tr("cookie_status_xhs") },
                                { key: "bilibili",   label: tr("cookie_status_bili") },
                                { key: "kuaishou",   label: tr("cookie_status_ks") }
                            ]
                            delegate: Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 36
                                radius: Theme.rXS
                                color: Qt.rgba(0, 0, 0, 0.15)
                                border.width: 1
                                border.color: Theme.glassBorder

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: 8
                                    spacing: 6

                                    // 状态圆点
                                    Rectangle {
                                        Layout.preferredWidth: 8
                                        Layout.preferredHeight: 8
                                        radius: 4
                                        color: {
                                            var s = (root.cookieStatuses[modelData.key] || "missing")
                                            if (s === "valid") return Theme.success
                                            if (s === "warning") return Theme.warning
                                            if (s === "expired") return Theme.danger
                                            return Qt.rgba(0.5, 0.5, 0.5, 0.4)  // missing
                                        }
                                    }

                                    Text {
                                        text: modelData.label
                                        color: Theme.textPrimary
                                        font.pixelSize: 11
                                        Layout.fillWidth: true
                                    }

                                    Text {
                                        text: {
                                            var s = (root.cookieStatuses[modelData.key] || "missing")
                                            if (s === "valid") return "✓"
                                            if (s === "warning") return "!"
                                            if (s === "expired") return "✗"
                                            return "—"
                                        }
                                        color: {
                                            var s = (root.cookieStatuses[modelData.key] || "missing")
                                            if (s === "valid") return Theme.success
                                            if (s === "warning") return Theme.warning
                                            if (s === "expired") return Theme.danger
                                            return Theme.textDim
                                        }
                                        font.pixelSize: 12
                                        font.weight: Font.Bold
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ---------- Instagram API 代理（Apify） ----------
            // 老版本功能恢复：通过 Apify Actor 代理提取 IG 数据
            // 避免直接调用 IG 移动 API 导致账号风控
            SettingsCard {
                Layout.fillWidth: true
                Layout.leftMargin: 32
                Layout.rightMargin: 32
                title: tr("settings_apify_section")
                desc: tr("apify_section_desc")
                icon: "i-sparkles"
                iconColor: Theme.platIg

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    // 启用开关 + 状态 Badge
                    // 注意：键名必须用 instagram_mode（与后端 get_platform_mode 对齐），
                    // 值为 "api" / "cookie" 二选一（互斥，不是 boolean）。
                    // 之前用 ig_use_apify 导致后端读不到，开关形同虚设。
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Text {
                            text: tr("apify_enable")
                            color: Theme.textMute
                            Layout.preferredWidth: 120
                        }
                        Switch {
                            checked: root.config.instagram_mode === "api"
                            onToggled: _save("instagram_mode", checked ? "api" : "cookie")
                        }
                        Badge {
                            text: root.config.instagram_mode === "api"
                                  ? tr("apify_status_on")
                                  : tr("apify_status_off")
                            status: root.config.instagram_mode === "api" ? "completed" : "default"
                        }
                        Item { Layout.fillWidth: true }
                    }

                    Text {
                        text: tr("apify_enable_hint")
                        color: Theme.textDim
                        font.pixelSize: 11
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                        Layout.leftMargin: 130
                    }

                    // Apify Token
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Text {
                            text: tr("apify_token")
                            color: Theme.textMute
                            Layout.preferredWidth: 120
                        }
                        Input {
                            id: _apifyTokenInput
                            Layout.fillWidth: true
                            placeholderText: "apify_api_..."
                            text: root.apifyState.token_configured === true
                                  ? "••••••••••••••••"
                                  : ""
                            echoMode: TextInput.Password
                            onEditingFinished: _save("apify_token", text)
                        }
                        Button {
                            text: root.apifyValidating ? tr("apify_validating")
                                                       : tr("apify_validate")
                            variant: "default"
                            iconName: "i-check"
                            enabled: !root.apifyValidating
                            onClicked: _validateApify()
                        }
                    }

                    Text {
                        text: tr("apify_token_hint")
                        color: Theme.textDim
                        font.pixelSize: 11
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                        Layout.leftMargin: 130
                    }

                    // Actor ID
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Text {
                            text: tr("apify_actor_id")
                            color: Theme.textMute
                            Layout.preferredWidth: 120
                        }
                        Input {
                            id: _apifyActorInput
                            Layout.fillWidth: true
                            placeholderText: "shu8hvrXbJbY3Eb9W"
                            text: root.apifyState.actor_id || ""
                            onEditingFinished: _save("apify_ig_actor", text)
                        }
                    }

                    Text {
                        text: tr("apify_actor_hint")
                        color: Theme.textDim
                        font.pixelSize: 11
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                        Layout.leftMargin: 130
                    }

                    // 验证状态显示（瞬态：用户点验证按钮后显示几秒）
                    // 已连接持久态显示时隐藏瞬态（避免"✅已连接"和持久徽章同时出现）
                    Text {
                        text: root.apifyValidateStatus
                        color: root.apifyValidateStatus.indexOf("✅") === 0 ? Theme.success
                              : (root.apifyValidateStatus.length > 0 ? Theme.danger : Theme.textDim)
                        font.pixelSize: 12
                        visible: root.apifyValidateStatus.length > 0
                                && !(root.apifyValidateStatus.indexOf("✅") === 0
                                     && root.apifyState.connected === true)
                        Layout.fillWidth: true
                        Layout.leftMargin: 130
                        wrapMode: Text.Wrap
                    }

                    // 持久连接状态（不依赖验证瞬态结果，切页面回来依然显示）
                    // 三态：已验证(绿) / 待验证(橙) / 未配置(隐藏)
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 130
                        spacing: 8
                        // token+actor 已配置就显示（区分已验证/待验证）
                        visible: root.apifyState.token_configured === true
                                && root.apifyState.actor_configured === true

                        Rectangle {
                            width: _connText.implicitWidth + 14
                            height: 18
                            radius: 9
                            // 已验证=绿色，待验证=橙色
                            color: root.apifyState.connected === true
                                   ? Qt.rgba(Theme.success.r, Theme.success.g, Theme.success.b, 0.18)
                                   : Qt.rgba(Theme.warning.r, Theme.warning.g, Theme.warning.b, 0.18)
                            border.width: 1
                            border.color: root.apifyState.connected === true
                                          ? Qt.rgba(Theme.success.r, Theme.success.g, Theme.success.b, 0.4)
                                          : Qt.rgba(Theme.warning.r, Theme.warning.g, Theme.warning.b, 0.4)
                            Text {
                                id: _connText
                                anchors.centerIn: parent
                                text: root.apifyState.connected === true
                                      ? "● " + tr("apify_connected")
                                      : "● " + tr("apify_pending_verify")
                                color: root.apifyState.connected === true
                                       ? Theme.success : Theme.warning
                                font.family: Theme.fontMono
                                font.pixelSize: 10
                                font.weight: Font.DemiBold
                            }
                        }
                        Item { Layout.fillWidth: true }
                    }

                    // 月度用量条（已连接就显示：加载中 / 成功 / 失败 三态）
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: _quotaCol.implicitHeight + 20
                        radius: Theme.rSM
                        color: Qt.rgba(Theme.platIg.r, Theme.platIg.g, Theme.platIg.b, 0.08)
                        border.width: 1
                        border.color: Qt.rgba(Theme.platIg.r, Theme.platIg.g, Theme.platIg.b, 0.2)
                        // 只要已连接（token+actor 配置）就显示，不再要求 plan_credits_usd 必须存在
                        visible: root.apifyState.connected === true

                        ColumnLayout {
                            id: _quotaCol
                            anchors.centerIn: parent
                            anchors.margins: 10
                            spacing: 6
                            Layout.fillWidth: true

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                Text {
                                    text: tr("apify_quota_label")
                                    color: Theme.platIg
                                    font.pixelSize: 11
                                    font.weight: Font.DemiBold
                                }
                                Item { Layout.fillWidth: true }

                                // 刷新按钮（用量查询失败或首次加载时点击重新查询）
                                Button {
                                    text: tr("apify_quota_refresh")
                                    variant: "ghost"
                                    iconName: "i-refresh"
                                    iconSize: 12
                                    implicitWidth: 70
                                    implicitHeight: 22
                                    // 强制刷新：清空时间戳缓存再调
                                    onClicked: {
                                        if (!controller) return
                                        // 清空缓存时间戳，强制下次查询
                                        root.apifyUsage = ({})
                                        // 直接调 controller 的刷新（绕过 5 分钟缓存）
                                        // 通过 setConfig 触发一次空操作来重置内部缓存
                                        try {
                                            // 直接调用 refreshApifyUsage 会被 5 分钟限制，
                                            // 这里通过 JS 侧清空 apifyUsage 触发 UI 显示 loading，
                                            // 然后用 QML Timer 延时调 refreshApifyUsage
                                            _quotaRefreshTimer.restart()
                                        } catch (e) {}
                                    }
                                }

                                Text {
                                    // 已用 / 总额（USD）+ 套餐名 — 仅在有数据时显示
                                    text: "$" + (root.apifyUsage.usage_usd || 0).toFixed(2)
                                          + " / $"
                                          + (root.apifyUsage.plan_credits_usd || 0).toFixed(2)
                                          + (root.apifyUsage.plan_name
                                             ? "  (" + root.apifyUsage.plan_name + ")"
                                             : "")
                                    color: Theme.textPrimary
                                    font.family: Theme.fontMono
                                    font.pixelSize: 11
                                    font.weight: Font.DemiBold
                                    visible: root.apifyUsage.plan_credits_usd !== undefined
                                            && root.apifyUsage.error === undefined
                                }
                            }

                            // 进度条（已用 / 总额）— 仅在有数据时显示
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 4
                                radius: 2
                                color: Qt.rgba(0, 0, 0, 0.15)
                                visible: root.apifyUsage.plan_credits_usd !== undefined
                                        && root.apifyUsage.error === undefined
                                Rectangle {
                                    anchors.left: parent.left
                                    anchors.verticalCenter: parent.verticalCenter
                                    height: parent.height
                                    radius: 2
                                    width: {
                                        var total = root.apifyUsage.plan_credits_usd || 0
                                        var used = root.apifyUsage.usage_usd || 0
                                        if (total <= 0) return 0
                                        var pct = Math.min(1, Math.max(0, used / total))
                                        return parent.width * pct
                                    }
                                    color: {
                                        var total = root.apifyUsage.plan_credits_usd || 0
                                        var used = root.apifyUsage.usage_usd || 0
                                        if (total > 0 && used / total > 0.8) return Theme.danger
                                        return Theme.platIg
                                    }
                                    Behavior on width { NumberAnimation { duration: 300 } }
                                }
                            }

                            // 加载中提示
                            Text {
                                text: tr("apify_quota_loading")
                                color: Theme.textDim
                                font.pixelSize: 11
                                visible: root.apifyUsage.plan_credits_usd === undefined
                                        && root.apifyUsage.error === undefined
                                Layout.fillWidth: true
                            }

                            // 错误提示
                            Text {
                                text: {
                                    var err = root.apifyUsage.error || ""
                                    if (err.length === 0) return ""
                                    return tr("apify_quota_error").replace("{err}", err)
                                }
                                color: Theme.danger
                                font.pixelSize: 11
                                wrapMode: Text.Wrap
                                visible: root.apifyUsage.error !== undefined
                                Layout.fillWidth: true
                            }

                            Text {
                                text: tr("apify_quota_hint")
                                      + (root.apifyUsage.usage_updated
                                         ? "  ·  " + tr("apify_quota_updated")
                                           + " " + root.apifyUsage.usage_updated
                                         : "")
                                color: Theme.textDim
                                font.pixelSize: 10
                                wrapMode: Text.Wrap
                                Layout.fillWidth: true
                            }
                        }
                    }

                    // 国内代理说明
                    Text {
                        text: tr("apify_proxy_hint")
                        color: Theme.textDim
                        font.pixelSize: 10
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                        Layout.leftMargin: 130
                    }
                }
            }

            // ---------- Telegram ----------
            SettingsCard {
                Layout.fillWidth: true
                Layout.leftMargin: 32
                Layout.rightMargin: 32
                title: tr("settings_telegram_section")
                desc: qsTr("Bot Token + 本地 API Server")
                icon: "i-telegram"
                iconColor: Theme.platTelegram

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    // 启用开关 + 显性状态提示（修复清单问题 3）
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Text {
                            text: tr("telegram_enable")
                            color: Theme.textMute
                            Layout.preferredWidth: 120
                        }
                        Switch {
                            checked: root.config.telegram_enabled === true
                            onToggled: _save("telegram_enabled", checked)
                        }
                        // 显性状态 Badge
                        Badge {
                            text: root.config.telegram_enabled === true
                                  ? tr("telegram_status_on")
                                  : tr("telegram_status_off")
                            status: root.config.telegram_enabled === true ? "completed" : "default"
                        }
                        Item { Layout.fillWidth: true }
                    }

                    Text {
                        text: tr("telegram_enable_hint")
                        color: Theme.textDim
                        font.pixelSize: 11
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                        Layout.leftMargin: 130
                    }

                    // Bot Token + 验证按钮（修复清单问题 3）
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Text {
                            text: tr("bot_token")
                            color: Theme.textMute
                            Layout.preferredWidth: 120
                        }
                        Input {
                            id: _tgTokenInput
                            Layout.fillWidth: true
                            placeholderText: "123456:ABC-DEF..."
                            text: root.config.telegram_bot_token === "***configured***"
                                  ? "••••••••••••••••"
                                  : (root.config.telegram_bot_token || "")
                            echoMode: TextInput.Password
                            onEditingFinished: _save("telegram_bot_token", text)
                        }
                        Button {
                            text: root.tgValidating ? tr("telegram_validating")
                                                  : tr("telegram_validate_btn")
                            variant: "default"
                            iconName: "i-check"
                            enabled: !root.tgValidating
                            onClicked: _validateTelegram()
                        }
                    }

                    // 验证状态显示
                    Text {
                        text: root.tgValidateStatus
                        color: root.tgValidateStatus.indexOf("🟢") === 0 ? Theme.success
                              : (root.tgValidateStatus.length > 0 ? Theme.danger : Theme.textDim)
                        font.pixelSize: 12
                        visible: root.tgValidateStatus.length > 0
                        Layout.fillWidth: true
                        Layout.leftMargin: 130
                        wrapMode: Text.Wrap
                    }

                    // API 地址
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Text {
                            text: tr("api_address")
                            color: Theme.textMute
                            Layout.preferredWidth: 120
                        }
                        Input {
                            Layout.fillWidth: true
                            placeholderText: "https://api.telegram.org"
                            text: root.config.telegram_api_base || ""
                            onEditingFinished: _save("telegram_api_base", text)
                        }
                    }

                    Text {
                        text: tr("telegram_api_base_hint")
                        color: Theme.textDim
                        font.pixelSize: 11
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                        Layout.leftMargin: 130
                    }

                    // 配对码区域（修复清单问题 3：原版本完全缺失）
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        visible: !root.tgState.bound_device

                        Text {
                            text: tr("telegram_pair_code_label")
                            color: Theme.textMute
                            Layout.preferredWidth: 120
                        }
                        Text {
                            text: root.tgState.pair_code || "—"
                            color: Theme.accent
                            font.family: Theme.fontMono
                            font.pixelSize: 18
                            font.weight: Font.Bold
                            Layout.fillWidth: true
                        }
                        Button {
                            text: tr("telegram_copy_btn")
                            variant: "ghost"
                            iconName: "i-copy"
                            visible: (root.tgState.pair_code || "").length > 0
                            onClicked: _copyPairCode()
                        }
                        Button {
                            text: tr("telegram_regen_btn")
                            variant: "ghost"
                            iconName: "i-refresh"
                            onClicked: _regenPairCode()
                        }
                    }

                    Text {
                        text: tr("telegram_pair_hint")
                        color: Theme.textDim
                        font.pixelSize: 11
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                        Layout.leftMargin: 130
                        visible: !root.tgState.bound_device && (root.tgState.pair_code || "").length > 0
                    }

                    // 已绑定设备区域
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        visible: root.tgState.bound_device !== null && root.tgState.bound_device !== undefined

                        Text {
                            text: tr("telegram_bound_label")
                            color: Theme.textMute
                            Layout.preferredWidth: 120
                        }
                        Text {
                            text: root.tgState.bound_device
                                  ? ("@" + (root.tgState.bound_device.username
                                            || root.tgState.bound_device.first_name
                                            || root.tgState.bound_device.telegram_user_id))
                                  : "—"
                            color: Theme.success
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                            Layout.fillWidth: true
                        }
                        Button {
                            text: tr("telegram_unlink_btn")
                            variant: "danger"
                            iconName: "i-trash"
                            onClicked: _unlinkTelegram()
                        }
                    }
                }
            }

            // ============================================================
            // 分组：下载
            // ============================================================
            Text {
                Layout.fillWidth: true
                Layout.leftMargin: 32
                Layout.rightMargin: 32
                Layout.topMargin: 8
                text: tr("settings_group_download")
                color: Theme.textMute
                font.family: Theme.fontDisplay
                font.pixelSize: 13
                font.weight: Font.DemiBold
                font.letterSpacing: 1.5
            }

            // ---------- 下载设置 ----------
            SettingsCard {
                Layout.fillWidth: true
                Layout.leftMargin: 32
                Layout.rightMargin: 32
                title: tr("settings_download_section")
                desc: qsTr("下载目录、存储模式、并发与冲突策略")
                icon: "i-download"
                iconColor: Theme.accent

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Text {
                            text: tr("download_dir")
                            color: Theme.textMute
                            Layout.preferredWidth: 120
                        }
                        Text {
                            text: root.config.download_dir || "—"
                            color: Theme.textDim
                            font.family: Theme.fontMono
                            font.pixelSize: 11
                            elide: Text.ElideMiddle
                            Layout.fillWidth: true
                        }
                        Button {
                            text: tr("browse")
                            variant: "ghost"
                            iconName: "i-folder"
                            onClicked: _browseDownloadDir()
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Text {
                            text: tr("storage_mode")
                            color: Theme.textMute
                            Layout.preferredWidth: 120
                        }
                        LumioComboBox {
                            Layout.fillWidth: true
                            model: [
                                { value: "simple",     label: tr("storage_simple") },
                                { value: "organized",  label: tr("storage_organized") }
                            ]
                            textRole: "label"; valueRole: "value"
                            currentIndex: {
                                var v = root.config.storage_mode || "simple"
                                for (var i = 0; i < model.length; i++) {
                                    if (model[i].value === v) return i
                                }
                                return 0
                            }
                            onActivated: _save("storage_mode", currentValue)
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Text {
                            text: tr("file_conflict")
                            color: Theme.textMute
                            Layout.preferredWidth: 120
                        }
                        LumioComboBox {
                            Layout.fillWidth: true
                            model: [
                                { value: "rename",    label: tr("conflict_rename") },
                                { value: "skip",      label: tr("conflict_skip") },
                                { value: "overwrite", label: tr("conflict_overwrite") },
                                { value: "ask",       label: tr("conflict_ask") }
                            ]
                            textRole: "label"; valueRole: "value"
                            currentIndex: {
                                var v = root.config.file_conflict_policy || "rename"
                                for (var i = 0; i < model.length; i++) {
                                    if (model[i].value === v) return i
                                }
                                return 0
                            }
                            onActivated: _save("file_conflict_policy", currentValue)
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Text {
                            text: tr("max_concurrent")
                            color: Theme.textMute
                            Layout.preferredWidth: 120
                        }
                        LumioSpinBox {
                            Layout.preferredWidth: 140
                            from: 1; to: 10
                            value: root.config.max_concurrent || 3
                            onValueModified: _save("max_concurrent", value)
                        }
                        Item { Layout.fillWidth: true }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Text {
                            text: tr("max_retries")
                            color: Theme.textMute
                            Layout.preferredWidth: 120
                        }
                        LumioSpinBox {
                            Layout.preferredWidth: 140
                            from: 0; to: 10
                            value: root.config.max_retries || 3
                            onValueModified: _save("max_retries", value)
                        }
                        Item { Layout.fillWidth: true }
                    }
                }
            }

            // ---------- 缓存管理 ----------
            SettingsCard {
                Layout.fillWidth: true
                Layout.leftMargin: 32
                Layout.rightMargin: 32
                title: tr("settings_cache_section")
                // 标题旁显示总缓存路径（跟随用户 home 自动变化，不硬编码）
                desc: tr("cache_total_size") + ": " + _formatSize(_totalCacheSize())
                      + (_cacheRootPath().length > 0 ? "  ·  " + _cacheRootPath() : "")
                icon: "i-database"
                iconColor: Theme.success

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    RowLayout {
                        Layout.fillWidth: true
                        Item { Layout.fillWidth: true }
                        Button {
                            text: tr("clean_now")
                            variant: "default"
                            iconName: "i-refresh"
                            onClicked: _cleanByRules()
                        }
                        Button {
                            text: tr("force_clear_all")
                            variant: "danger"
                            iconName: "i-trash"
                            onClicked: _forceClear()
                        }
                    }

                    // 4 个缓存目录统计（2×2 网格）
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2
                        rowSpacing: 8
                        columnSpacing: 8

                        Repeater {
                            model: [
                                { label: tr("cache_inbox"),    key: "inbox_media" },
                                { label: tr("cache_thumbs"),   key: "thumbs" },
                                { label: tr("cache_provider"), key: "provider_cache" },
                                { label: tr("cache_preview"),  key: "preview" }
                            ]
                            delegate: Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 64
                                radius: Theme.rSM
                                color: Qt.rgba(0, 0, 0, 0.18)
                                border.width: 1
                                border.color: Theme.glassBorder

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    spacing: 10

                                    ColumnLayout {
                                        spacing: 1
                                        Text {
                                            text: modelData.label
                                            color: Theme.textMute
                                            font.pixelSize: 11
                                        }
                                        // 显示该缓存目录的完整路径（跟随用户 home）
                                        Text {
                                            text: (root.cacheStats[modelData.key] || {}).path || ""
                                            color: Theme.textDim
                                            font.family: Theme.fontMono
                                            font.pixelSize: 9
                                            elide: Text.ElideMiddle
                                            Layout.maximumWidth: 220
                                        }
                                    }
                                    Item { Layout.fillWidth: true }
                                    ColumnLayout {
                                        spacing: 1
                                        Text {
                                            text: _formatSize(
                                                (root.cacheStats[modelData.key] || {}).size_bytes || 0)
                                            color: Theme.textPrimary
                                            font.family: Theme.fontMono
                                            font.pixelSize: 13
                                            font.weight: Font.DemiBold
                                            Layout.alignment: Qt.AlignRight
                                        }
                                        Text {
                                            text: ((root.cacheStats[modelData.key] || {}).file_count || 0)
                                                  + " " + tr("cache_files")
                                            color: Theme.textDim
                                            font.family: Theme.fontMono
                                            font.pixelSize: 10
                                            Layout.alignment: Qt.AlignRight
                                        }
                                    }
                                }
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Text {
                            text: tr("auto_clean")
                            color: Theme.textMute
                            Layout.preferredWidth: 120
                        }
                        LumioComboBox {
                            Layout.fillWidth: true
                            model: [
                                { value: "off",     label: tr("auto_clean_off") },
                                { value: "startup", label: tr("auto_clean_startup") },
                                { value: "daily",   label: tr("auto_clean_daily") },
                                { value: "weekly",  label: tr("auto_clean_weekly") }
                            ]
                            textRole: "label"; valueRole: "value"
                            currentIndex: {
                                var v = (root.config.cache_management || {}).auto_clean || "off"
                                for (var i = 0; i < model.length; i++) {
                                    if (model[i].value === v) return i
                                }
                                return 0
                            }
                            onActivated: _saveNested("cache_management", "auto_clean", currentValue)
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Text {
                            text: tr("retain_days")
                            color: Theme.textMute
                            Layout.preferredWidth: 120
                        }
                        LumioSpinBox {
                            Layout.preferredWidth: 140
                            from: 1; to: 365
                            value: (root.config.cache_management || {}).retain_days || 7
                            onValueModified: _saveNested("cache_management", "retain_days", value)
                        }
                        Item { Layout.fillWidth: true }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Text {
                            text: tr("max_size_mb")
                            color: Theme.textMute
                            Layout.preferredWidth: 120
                        }
                        LumioSpinBox {
                            Layout.preferredWidth: 160
                            from: 50; to: 10000; stepSize: 50
                            value: (root.config.cache_management || {}).max_size_mb || 500
                            onValueModified: _saveNested("cache_management", "max_size_mb", value)
                        }
                        Item { Layout.fillWidth: true }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Text {
                            text: tr("last_cleaned")
                            color: Theme.textMute
                            Layout.preferredWidth: 120
                        }
                        Text {
                            text: {
                                var t = (root.config.cache_management || {}).last_cleaned || ""
                                if (!t || t.length === 0) return tr("never")
                                return t.replace("T", " ").substring(0, 19)
                            }
                            color: Theme.textDim
                            font.family: Theme.fontMono
                            font.pixelSize: 11
                        }
                    }
                }
            }

            // ============================================================
            // 分组：系统
            // ============================================================
            Text {
                Layout.fillWidth: true
                Layout.leftMargin: 32
                Layout.rightMargin: 32
                Layout.topMargin: 8
                text: tr("settings_group_system")
                color: Theme.textMute
                font.family: Theme.fontDisplay
                font.pixelSize: 13
                font.weight: Font.DemiBold
                font.letterSpacing: 1.5
            }

            // ---------- 通用 ----------
            SettingsCard {
                Layout.fillWidth: true
                Layout.leftMargin: 32
                Layout.rightMargin: 32
                title: tr("settings_general_section")
                desc: qsTr("语言、主题、自动下载")
                icon: "i-settings"
                iconColor: Theme.accent2

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Text {
                            text: tr("language")
                            color: Theme.textMute
                            Layout.preferredWidth: 120
                        }
                        LumioComboBox {
                            Layout.preferredWidth: 200
                            model: [
                                { value: "zh", label: tr("language_zh") },
                                { value: "en", label: tr("language_en") }
                            ]
                            textRole: "label"; valueRole: "value"
                            currentIndex: {
                                var v = root.config.lang || "zh"
                                for (var i = 0; i < model.length; i++) {
                                    if (model[i].value === v) return i
                                }
                                return 0
                            }
                            onActivated: {
                                if (controller) controller.setLang(currentValue)
                            }
                        }
                        Item { Layout.fillWidth: true }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Text {
                            text: tr("theme_dark")
                            color: Theme.textMute
                            Layout.preferredWidth: 120
                        }
                        LumioComboBox {
                            Layout.preferredWidth: 200
                            model: [
                                { value: "dark",  label: tr("theme_dark") },
                                { value: "light", label: tr("theme_light") }
                            ]
                            textRole: "label"; valueRole: "value"
                            currentIndex: {
                                var v = root.config.theme || "dark"
                                for (var i = 0; i < model.length; i++) {
                                    if (model[i].value === v) return i
                                }
                                return 0
                            }
                            onActivated: {
                                if (controller) controller.setTheme(currentValue)
                            }
                        }
                        Item { Layout.fillWidth: true }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Text {
                                text: tr("auto_download_inbox")
                                color: Theme.textMute
                                font.pixelSize: 13
                            }
                            Text {
                                text: tr("auto_download_inbox_desc")
                                color: Theme.textDim
                                font.pixelSize: 11
                            }
                        }
                        Switch {
                            checked: root.config.auto_download_inbox === true
                            onToggled: _save("auto_download_inbox", checked)
                        }
                    }

                    // X-Sou 启用开关（含 18+ 内容警告）
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Text {
                                text: tr("enable_xsou")
                                color: Theme.textMute
                                font.pixelSize: 13
                            }
                            Text {
                                text: tr("enable_xsou_desc")
                                color: Theme.textDim
                                font.pixelSize: 11
                                wrapMode: Text.Wrap
                                Layout.fillWidth: true
                            }
                            // 18+ 警告标签
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 22
                                radius: Theme.rPill
                                color: Qt.rgba(255/255, 140/255, 50/255, 0.12)
                                border.width: 1
                                border.color: Qt.rgba(255/255, 140/255, 50/255, 0.35)
                                visible: root.config.enable_xsou !== true
                                Text {
                                    anchors.centerIn: parent
                                    text: tr("enable_xsou_warning")
                                    color: Qt.rgba(255/255, 140/255, 50/255, 1)
                                    font.family: Theme.fontBody
                                    font.pixelSize: 10
                                    font.weight: Font.DemiBold
                                }
                            }
                        }
                        Switch {
                            checked: root.config.enable_xsou === true
                            onToggled: _save("enable_xsou", checked)
                        }
                    }
                }
            }

            // ---------- 关于 ----------
            SettingsCard {
                Layout.fillWidth: true
                Layout.leftMargin: 32
                Layout.rightMargin: 32
                title: tr("settings_about_section")
                desc: "Lumio © 2026"
                icon: "i-info"
                iconColor: Theme.info

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Text {
                            text: tr("version")
                            color: Theme.textMute
                            Layout.preferredWidth: 120
                        }
                        Text {
                            text: root.config.version || "v4.2"
                            color: Theme.textPrimary
                            font.family: Theme.fontMono
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                        }
                        Item { Layout.fillWidth: true }
                        Button {
                            text: tr("settings_check_update")
                            variant: "primary"
                            iconName: "i-refresh"
                            onClicked: _checkUpdate()
                        }
                    }

                    Text {
                        text: root.updateStatus
                        color: Theme.accent
                        font.pixelSize: 12
                        visible: root.updateStatus.length > 0
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                    }

                    Text {
                        text: "Lumio © 2026 · Build " + (root.config.build_date || "2026.07.25")
                        color: Theme.textDim
                        font.family: Theme.fontMono
                        font.pixelSize: 10
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                    }
                }
            }

            Item { Layout.preferredHeight: 32 }
        }
    }

    // 强制清空确认
    Dialog {
        id: _forceDialog
        visible: false
        modal: true
        anchors.centerIn: parent
        title: tr("force_clear_all")
        width: 380

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
                text: tr("cache_force_confirm")
                color: Theme.textPrimary
                font.family: Theme.fontBody
                font.pixelSize: 14
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Item { Layout.fillWidth: true }
                Button {
                    text: tr("cancel"); variant: "ghost"
                    onClicked: _forceDialog.visible = false
                }
                Button {
                    text: tr("force_clear_all"); variant: "danger"
                    onClicked: _doForceClear()
                }
            }
        }
    }

    // Cookie 清除确认（修复清单问题 4）
    Dialog {
        id: _cookieClearDialog
        visible: false
        modal: true
        anchors.centerIn: parent
        title: tr("cookie_clear_btn")
        width: 380

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
                text: tr("cookie_clear_confirm")
                color: Theme.textPrimary
                font.family: Theme.fontBody
                font.pixelSize: 14
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Item { Layout.fillWidth: true }
                Button {
                    text: tr("cancel"); variant: "ghost"
                    onClicked: _cookieClearDialog.visible = false
                }
                Button {
                    text: tr("cookie_clear_btn"); variant: "danger"
                    onClicked: _doClearCookie()
                }
            }
        }
    }

    // Telegram 解绑确认（修复清单问题 3）
    Dialog {
        id: _tgUnlinkDialog
        visible: false
        modal: true
        anchors.centerIn: parent
        title: tr("telegram_unlink_btn")
        width: 380

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
                text: qsTr("确定解除 Telegram 设备绑定？解除后需重新生成配对码并重新绑定。")
                color: Theme.textPrimary
                font.family: Theme.fontBody
                font.pixelSize: 14
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Item { Layout.fillWidth: true }
                Button {
                    text: tr("cancel"); variant: "ghost"
                    onClicked: _tgUnlinkDialog.visible = false
                }
                Button {
                    text: tr("telegram_unlink_btn"); variant: "danger"
                    onClicked: _doUnlinkTelegram()
                }
            }
        }
    }
}
