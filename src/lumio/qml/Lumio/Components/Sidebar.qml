// ============================================================
// LUMIO // Sidebar — 左侧导航栏
// ------------------------------------------------------------
// 还原 .sidebar 样式：
//   - 220px 宽 + 半透明 + backdrop blur
//   - Brand logo + version
//   - 8 个 nav-item（Home/Inbox/Downloads/History/Library/Stats/Notifications/Settings）
//   - active 项左侧蓝色指示条
//   - 底部主题切换 + 版本号
// ============================================================
import QtQuick
import QtQuick.Layouts
import QtQuick.Effects
import Lumio
import Lumio.Components

Item {
    id: root

    // ---------- 公开属性 ----------
    property string activePage: "home"
    property string version: "v4.2"
    property string theme: "dark"

    // ---------- 信号 ----------
    signal pageRequested(string page)
    signal themeToggleRequested()

    // ---------- 徽章计数（绑定 controller 信号实时刷新） ----------
    // inbox: status='new' 数量；notifications: 未读数量
    // 注意：属性名避免下划线前缀，QML 对 _xxxChanged 信号命名不一致
    property int inboxUnread: 0
    property int notifUnread: 0

    // 启动 + 信号驱动刷新（避免轮询）
    Component.onCompleted: _refreshBadges()
    function _refreshBadges() {
        if (typeof controller === "undefined" || !controller) return
        try {
            if (controller.unreadInbox)        root.inboxUnread = controller.unreadInbox()
            if (controller.unreadNotifications) root.notifUnread = controller.unreadNotifications()
        } catch (e) {
            console.log("[Sidebar] refresh badges failed:", e)
        }
    }

    Connections {
        target: typeof controller !== "undefined" ? controller : null
        // Inbox 任何变化（新增/状态更新/删除）→ 重新拉未读数
        function onInboxChanged() { _refreshBadges() }
        // 通知变化（新增/标记已读/清除）→ 直接用后端给的 unread_count
        function onNotificationsChanged(unread_count) {
            root.notifUnread = unread_count || 0
            // 通知变化时也刷新一下 inbox（极少数场景：通知触发自动下载入队）
        }
    }

    // ---------- 背景层（半透明 + backdrop blur） ----------
    Rectangle {
        id: _bg
        anchors.fill: parent
        // 跟随主题：使用 Theme token 确保与全局主题一致
        // 深色模式：深蓝近黑半透明
        // 浅色模式：纯白半透明，叠加在浅灰白渐变背景上形成层次
        color: Theme.theme === "dark"
               ? Qt.rgba(10/255, 10/255, 20/255, 0.55)
               : Qt.rgba(255/255, 255/255, 255/255, 0.85)
        border.width: 0
        // backdrop blur 通过 layer.effect 实现
        // 注意：真正的 backdrop 需要 source 下方内容，这里用静态半透明模拟
    }

    // 右侧分隔线
    Rectangle {
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        width: 1
        color: Theme.glassBorder
    }

    // ---------- 内容 ----------
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 0

        // Brand
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 56
            Layout.topMargin: 8

            // 用单个 Text + style: Text.Outline 模拟渐变（避免 Text+Canvas 双层重叠）
            Text {
                id: _brand
                anchors.left: parent.left
                anchors.top: parent.top
                text: "Lumio"
                color: Theme.textPrimary
                font.family: Theme.fontDisplay
                font.pixelSize: 20
                font.weight: Font.Black
                font.letterSpacing: 1
            }

            Text {
                anchors.left: parent.left
                anchors.top: _brand.bottom
                anchors.topMargin: 2
                text: root.version
                color: Theme.textDim
                font.family: Theme.fontMono
                font.pixelSize: 10
                font.letterSpacing: 1.5
            }
        }

        Item { Layout.preferredHeight: 28 }

        // Nav items
        ColumnLayout {
            id: _navCol
            Layout.fillWidth: true
            // 增大间距避免浅色模式相邻 hover 项视觉重叠
            spacing: 4

            // 直接绑定到 controller.lang（Property 有 langChanged notify）
            // 语言切换时 controller.lang 变化 → model binding 重新评估 → tr() 重算
            // 兜底：若 controller 不可用，用本地 _langRev 占位避免 ReferenceError
            property string _langKey: typeof controller !== "undefined" && controller
                                      ? controller.lang : "fallback"

            Repeater {
                // model 依赖 _langKey，使语言切换后重新构建
                model: {
                    var _ = _navCol._langKey  // 触发依赖
                    return [
                        { key: "home",          label: tr("home"),          icon: "i-home" },
                        { key: "inbox",         label: tr("inbox"),         icon: "i-inbox" },
                        { key: "downloads",     label: tr("downloads"),     icon: "i-download" },
                        { key: "history",       label: tr("history"),       icon: "i-history" },
                        { key: "library",       label: tr("library"),       icon: "i-library" },
                        { key: "stats",         label: tr("stats"),         icon: "i-stats" },
                        { key: "notifications", label: tr("notifications"), icon: "i-bell" },
                        { key: "settings",      label: tr("settings"),      icon: "i-settings" }
                    ]
                }

                delegate: Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 38

                    Rectangle {
                        id: _navBg
                        anchors.fill: parent
                        radius: Theme.rMD
                        color: "transparent"

                        // ============================================================
                        // 双层背景策略（修复浅色模式切换页面时两个 bar 同时闪烁）
                        // ------------------------------------------------------------
                        // 历史问题：单层 Rectangle + Behavior on color 让 active
                        //   切换也走 150ms ColorAnimation。切换页面时旧 active 项
                        //   (glassBgHi→transparent) 和新 active 项
                        //   (transparent→glassBgHi) 同时动画，浅色模式下
                        //   glassBgHi=rgba(255,255,255,0.9) 与白底对比度低，
                        //   过渡中间状态经过透明露出底色，视觉上"两个 bar 同时闪"。
                        //
                        // 修复：拆成两层
                        //   - 底层 _activeBg：active 状态背景，visible 直接绑定 active，
                        //     无 ColorAnimation → active 切换瞬时完成
                        //   - 上层 _hoverBg：hover 状态背景，仅非 active 时显示，
                        //     有 150ms ColorAnimation → hover 平滑过渡
                        // ============================================================

                        // 底层：active 背景（瞬时切换，无动画）
                        Rectangle {
                            id: _activeBg
                            anchors.fill: parent
                            radius: Theme.rMD
                            color: Theme.glassBgHi
                            visible: root.activePage === modelData.key
                            // 顶部高光
                            Rectangle {
                                visible: root.activePage === modelData.key
                                anchors.top: parent.top
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.margins: 1
                                height: 1
                                color: Qt.rgba(1, 1, 1, 0.1)
                            }
                        }

                        // 上层：hover 背景（仅非 active 时显示，有动画）
                        Rectangle {
                            id: _hoverBg
                            anchors.fill: parent
                            radius: Theme.rMD
                            // hover 颜色按主题区分
                            // 浅色：rgba(0,0,0,0.04) 轻微暗化（与白底有清晰对比）
                            // 深色：glassBg 柔和亮化
                            color: Theme.theme === "light"
                                   ? Qt.rgba(0, 0, 0, 0.04)
                                   : Theme.glassBg
                            // active 时不显示 hover 层（让 active 背景独立呈现）
                            visible: root.activePage !== modelData.key
                                     && _mouse.containsMouse
                            Behavior on color { ColorAnimation { duration: 150 } }
                            Behavior on visible { NumberAnimation { duration: 0 } }
                        }
                    }

                    // active 左侧指示条
                    Rectangle {
                        visible: root.activePage === modelData.key
                        anchors.left: parent.left
                        anchors.leftMargin: -12
                        anchors.verticalCenter: parent.verticalCenter
                        width: 3
                        height: 16
                        radius: 2
                        gradient: Gradient {
                            orientation: Gradient.Vertical
                            GradientStop { position: 0.0; color: Theme.accent }
                            GradientStop { position: 1.0; color: Theme.accent2 }
                        }
                    }

                    Row {
                        anchors.left: parent.left
                        anchors.leftMargin: 14
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 12

                        Icon {
                            name: modelData.icon
                            size: 16
                            color: root.activePage === modelData.key
                                   ? Theme.textPrimary
                                   : (_mouse.containsMouse ? Theme.textPrimary : Theme.textMute)
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        Text {
                            text: modelData.label
                            color: root.activePage === modelData.key
                                   ? Theme.textPrimary
                                   : (_mouse.containsMouse ? Theme.textPrimary : Theme.textMute)
                            font.family: Theme.fontBody
                            font.pixelSize: Theme.fsBody
                            font.weight: Font.Medium
                            anchors.verticalCenter: parent.verticalCenter
                            Behavior on color { ColorAnimation { duration: 60 } }
                        }
                    }

                    // ============================================================
                    // 红点徽章（仅 inbox / notifications 显示）
                    // ------------------------------------------------------------
                    // 视觉规则：
                    //   - 1-9   → 圆形 (16px) 单数字
                    //   - 10-99 → 胶囊 (变宽) 双数字
                    //   - ≥100  → 胶囊 "99+"
                    //   - 0     → 隐藏
                    // 颜色：danger 红 + 白色 Mono 字
                    // 位置：右侧 12px 内边距，垂直居中
                    // ============================================================
                    Item {
                        id: _badge
                        anchors.right: parent.right
                        anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter

                        // 当前项的未读数（直接表达式，便于绑定依赖追踪）
                        property int _value: {
                            if (modelData.key === "inbox")         return root.inboxUnread
                            if (modelData.key === "notifications")  return root.notifUnread
                            return 0
                        }
                        property string _text: _value >= 100 ? "99+" : String(_value)
                        visible: _value > 0
                        implicitWidth: _badgeRect.implicitWidth
                        implicitHeight: _badgeRect.implicitHeight

                        Rectangle {
                            id: _badgeRect
                            anchors.centerIn: parent
                            implicitWidth: Math.max(16, _badgeText.implicitWidth + 14)
                            implicitHeight: 16
                            radius: 8   // height/2 → 完整胶囊
                            color: Theme.danger
                            border.width: 1
                            border.color: Theme.theme === "light"
                                          ? Qt.rgba(180/255, 30/255, 30/255, 0.6)
                                          : Qt.rgba(255/255, 255/255, 255/255, 0.15)

                            Text {
                                id: _badgeText
                                anchors.centerIn: parent
                                text: _badge._text
                                color: "#FFFFFF"
                                font.family: Theme.fontMono
                                font.pixelSize: 10
                                font.weight: Font.DemiBold
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }
                        }
                    }

                    MouseArea {
                        id: _mouse
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        hoverEnabled: true
                        onClicked: root.pageRequested(modelData.key)
                    }
                }
            }
        }

        // 弹性填充
        Item { Layout.fillHeight: true }

        // Sidebar footer
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 8

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                color: Theme.glassBorder
            }

            // Theme toggle
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 36
                radius: Theme.rSM
                color: _themeMouse.containsMouse ? Theme.glassBg : "transparent"
                border.width: 1
                border.color: Theme.glassBorder
                Behavior on color { ColorAnimation { duration: 200 } }

                Row {
                    anchors.centerIn: parent
                    spacing: 6

                    Icon {
                        name: root.theme === "dark" ? "i-moon" : "i-sun"
                        size: 14
                        color: Theme.textMute
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    Text {
                        // 依赖 _langKey 让语言切换时重新评估 tr() 调用
                        text: {
                            var _ = _navCol._langKey
                            return root.theme === "dark" ? tr("theme_dark") : tr("theme_light")
                        }
                        color: Theme.textMute
                        font.family: Theme.fontBody
                        font.pixelSize: Theme.fsMicro
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }

                MouseArea {
                    id: _themeMouse
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    hoverEnabled: true
                    onClicked: root.themeToggleRequested()
                }
            }

            Text {
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                text: "Build 2026.07.25"
                color: Theme.textDim
                font.family: Theme.fontMono
                font.pixelSize: 9
                font.letterSpacing: 0.5
            }
        }
    }
}
