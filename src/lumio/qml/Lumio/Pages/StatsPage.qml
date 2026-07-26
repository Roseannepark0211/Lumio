// ============================================================
// LUMIO // StatsPage — 统计页
// ------------------------------------------------------------
// 真实对接 controller:
//   - getStatsJson() → {total_downloads, total_size, success_rate, today_count, platforms}
//   - historyChanged 信号 → 刷新
// 4+3 布局：4 主卡 + 3 平台分布卡
// ============================================================
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Lumio
import Lumio.Components

Item {
    id: root

    property var stats: ({
        total_downloads: 0,
        total_size: 0,
        success_rate: 0.0,
        today_count: 0,
        platforms: {}
    })

    Connections {
        target: typeof controller !== "undefined" ? controller : null
        function onHistoryChanged() { _reload() }
    }

    Component.onCompleted: _reload()

    function _reload() {
        if (typeof controller === "undefined" || !controller) return
        try {
            var json = controller.getStatsJson()
            root.stats = JSON.parse(json)
            // 平台分布通过 _platformsArray() 直接绑定到 Repeater.model
        } catch (e) {
            console.log("[StatsPage] reload failed:", e)
        }
    }

    function _formatSize(bytes) {
        if (!bytes || bytes <= 0) return "0 B"
        if (bytes < 1024) return bytes + " B"
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB"
        if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB"
        return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB"
    }

    function _platformsArray() {
        var p = root.stats.platforms || {}
        var arr = []
        for (var k in p) {
            arr.push({ platform: k, count: p[k] })
        }
        arr.sort(function(a, b) { return b.count - a.count })
        return arr
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
                title: tr("stats_page")
                subtitle: tr("stats_subtitle")
                icon: "i-stats"

                // 右侧操作区
                Button {
                    text: tr("refresh"); variant: "ghost"; iconName: "i-retry"
                    onClicked: _reload()
                }
            }

            // 4 stat cards
            GridLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 48
                Layout.rightMargin: 48
                columns: 4
                rowSpacing: 14
                columnSpacing: 14

                Repeater {
                    model: [
                        { label: tr("stats_total"),   value: root.stats.total_downloads.toString() },
                        { label: tr("stats_size"),    value: _formatSize(root.stats.total_size) },
                        { label: tr("stats_success_rate"), value: (root.stats.success_rate || 0).toFixed(1) + "%" },
                        { label: tr("stats_today"),   value: root.stats.today_count.toString() }
                    ]

                    delegate: GlassCard {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 110
                        radius: Theme.rLG
                        padding: 18

                        ColumnLayout {
                            width: parent.width
                            height: parent.height
                            spacing: 4

                            Text {
                                text: modelData.label
                                color: Theme.textMute
                                font.family: Theme.fontMono
                                font.pixelSize: Theme.fsMicro
                                font.letterSpacing: 0.5
                            }

                            Text {
                                text: modelData.value
                                color: Theme.textPrimary
                                font.family: Theme.fontDisplay
                                font.pixelSize: 28
                                font.weight: Font.Bold
                            }
                        }
                    }
                }
            }

            // Platform distribution header
            Text {
                Layout.fillWidth: true
                Layout.leftMargin: 48
                Layout.topMargin: 16
                text: tr("platform_distribution")
                color: Theme.textPrimary
                font.family: Theme.fontDisplay
                font.pixelSize: Theme.fsH2
                font.weight: Font.Bold
            }

            // Platform cards
            GridLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 48
                Layout.rightMargin: 48
                columns: 3
                rowSpacing: 14
                columnSpacing: 14

                Repeater {
                    model: _platformsArray()

                    delegate: GlassCard {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 80
                        radius: Theme.rLG
                        padding: 18

                        RowLayout {
                            width: parent.width
                            height: parent.height
                            spacing: 14

                            // Platform dot
                            Rectangle {
                                width: 10; height: 10; radius: 5
                                color: Theme.platformColor(modelData.platform)
                                Layout.alignment: Qt.AlignVCenter
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2

                                Text {
                                    text: Theme.platformLabel(modelData.platform)
                                    color: Theme.textPrimary
                                    font.family: Theme.fontBody
                                    font.pixelSize: Theme.fsBody
                                    font.weight: Font.DemiBold
                                }

                                Text {
                                    text: modelData.count + " " + tr("downloads_count")
                                    color: Theme.textMute
                                    font.family: Theme.fontMono
                                    font.pixelSize: Theme.fsMicro
                                }
                            }

                            Text {
                                text: modelData.count.toString()
                                color: Theme.platformColor(modelData.platform)
                                font.family: Theme.fontDisplay
                                font.pixelSize: 22
                                font.weight: Font.Bold
                            }
                        }
                    }
                }
            }

            // 空状态
            Text {
                visible: root.stats.total_downloads === 0
                Layout.fillWidth: true
                Layout.topMargin: 40
                text: tr("no_history")
                color: Theme.textMute
                font.family: Theme.fontBody
                font.pixelSize: Theme.fsBody
                horizontalAlignment: Text.AlignHCenter
            }

            Item { Layout.preferredHeight: 48 }
        }
    }
}
