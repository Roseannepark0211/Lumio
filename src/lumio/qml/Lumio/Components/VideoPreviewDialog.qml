// ============================================================
// LUMIO // VideoPreviewDialog — 视频预览对话框
// ------------------------------------------------------------
// 用法：
//   VideoPreviewDialog {
//       id: _previewDlg
//       visible: false
//   }
//   _previewDlg.openWithUrl("file:///xxx.mp4")
//
// 支持本地 file:// 路径和 http(s):// 流式 URL。
// 控制栏：播放/暂停 + 进度条 + 时间 + 关闭。
// ============================================================
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import QtMultimedia
import Lumio
import Lumio.Components

Dialog {
    id: root
    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    anchors.centerIn: parent
    width: 900
    height: 640
    padding: 0
    background: Rectangle {
        radius: Theme.rLG
        color: Qt.rgba(0, 0, 0, 0.95)
        border.width: 1
        border.color: Theme.glassBorderHi
        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: Qt.rgba(0, 0, 0, 0.5)
            shadowBlur: 0.8
            shadowVerticalOffset: 12
        }
    }

    property url videoSource: ""

    function openWithUrl(urlStr) {
        if (!urlStr) return
        if (urlStr.indexOf("http://") === 0 || urlStr.indexOf("https://") === 0) {
            root.videoSource = urlStr
        } else {
            // 本地路径 → file:// URL
            root.videoSource = Qt.resolvedUrl("file:///" + urlStr.replace(/\\/g, "/"))
        }
        _player.source = root.videoSource
        _player.play()
        root.open()
    }

    onClosed: {
        _player.stop()
        _player.source = ""
        root.videoSource = ""
    }

    contentItem: ColumnLayout {
        spacing: 0
        anchors.fill: parent

        // 视频区
        VideoOutput {
            id: _videoOutput
            Layout.fillWidth: true
            Layout.fillHeight: true
            fillMode: VideoOutput.PreserveAspectFit
        }

        // 错误提示
        Text {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: _player.errorString && _player.errorString.length > 0
            text: tr("preview_format_error") + "\n" + (_player.errorString || "")
            color: Theme.textDim
            font.family: Theme.fontBody
            font.pixelSize: Theme.fsBody
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }

        // 控制栏
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 52
            color: Qt.rgba(0, 0, 0, 0.6)

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                spacing: 12

                // 播放/暂停按钮
                Rectangle {
                    Layout.preferredWidth: 36
                    Layout.preferredHeight: 36
                    Layout.alignment: Qt.AlignVCenter
                    radius: 18
                    color: _playMouse.containsMouse ? Theme.accentSoft : "transparent"
                    Icon {
                        anchors.centerIn: parent
                        name: _player.playbackState === MediaPlayer.PlayingState ? "i-pause" : "i-play"
                        size: 18
                        color: "#ffffff"
                    }
                    MouseArea {
                        id: _playMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (_player.playbackState === MediaPlayer.PlayingState) {
                                _player.pause()
                            } else {
                                _player.play()
                            }
                        }
                    }
                }

                // 当前时间
                Text {
                    Layout.alignment: Qt.AlignVCenter
                    text: _formatTime(_player.position)
                    color: "#ffffff"
                    font.family: Theme.fontMono
                    font.pixelSize: Theme.fsSmall
                }

                // 进度条
                Slider {
                    id: _seekBar
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignVCenter
                    from: 0
                    to: Math.max(1, _player.duration)
                    value: _player.position
                    enabled: _player.duration > 0 && _player.seekable
                    onMoved: _player.setPosition(value)

                    background: Rectangle {
                        x: _seekBar.leftPadding
                        y: _seekBar.topPadding + _seekBar.availableHeight / 2 - 2
                        width: _seekBar.availableWidth
                        height: 4
                        radius: 2
                        color: Qt.rgba(1, 1, 1, 0.2)
                        Rectangle {
                            width: _seekBar.visualPosition * parent.width
                            height: parent.height
                            radius: 2
                            color: Theme.accent
                        }
                    }
                    handle: Rectangle {
                        x: _seekBar.leftPadding + _seekBar.visualPosition * _seekBar.availableWidth - width / 2
                        y: _seekBar.topPadding + _seekBar.availableHeight / 2 - height / 2
                        width: 12; height: 12; radius: 6
                        color: "#ffffff"
                    }
                }

                // 总时长
                Text {
                    Layout.alignment: Qt.AlignVCenter
                    text: _formatTime(_player.duration)
                    color: "#cccccc"
                    font.family: Theme.fontMono
                    font.pixelSize: Theme.fsSmall
                }

                // 音量图标（点击静音/恢复）
                Rectangle {
                    Layout.preferredWidth: 28
                    Layout.preferredHeight: 28
                    Layout.alignment: Qt.AlignVCenter
                    radius: 14
                    color: _volIconMouse.containsMouse ? Qt.rgba(1, 1, 1, 0.1) : "transparent"
                    Icon {
                        anchors.centerIn: parent
                        name: _audioOut.volume <= 0 ? "i-volume-mute" : "i-volume"
                        size: 16
                        color: "#ffffff"
                    }
                    MouseArea {
                        id: _volIconMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            // 点击图标：静音 / 恢复上次音量
                            if (_audioOut.volume > 0) {
                                _volSlider._lastVol = _audioOut.volume
                                _audioOut.volume = 0
                                _volSlider.value = 0
                            } else {
                                var v = _volSlider._lastVol > 0 ? _volSlider._lastVol : 0.8
                                _audioOut.volume = v
                                _volSlider.value = v
                            }
                        }
                    }
                }

                // 音量条
                Slider {
                    id: _volSlider
                    Layout.preferredWidth: 90
                    Layout.alignment: Qt.AlignVCenter
                    from: 0
                    to: 1
                    value: _audioOut.volume
                    // 同步：滑块改变 → 音量
                    onMoved: _audioOut.volume = value
                    property real _lastVol: 0.8  // 记住静音前的音量

                    background: Rectangle {
                        x: _volSlider.leftPadding
                        y: _volSlider.topPadding + _volSlider.availableHeight / 2 - 2
                        width: _volSlider.availableWidth
                        height: 4
                        radius: 2
                        color: Qt.rgba(1, 1, 1, 0.2)
                        Rectangle {
                            width: _volSlider.visualPosition * parent.width
                            height: parent.height
                            radius: 2
                            color: "#ffffff"
                        }
                    }
                    handle: Rectangle {
                        x: _volSlider.leftPadding + _volSlider.visualPosition * _volSlider.availableWidth - width / 2
                        y: _volSlider.topPadding + _volSlider.availableHeight / 2 - height / 2
                        width: 10; height: 10; radius: 5
                        color: "#ffffff"
                    }
                }

                Item { Layout.preferredWidth: 8 }

                // 关闭按钮（X 图标，表示关闭预览）
                Rectangle {
                    Layout.preferredWidth: 36
                    Layout.preferredHeight: 36
                    Layout.alignment: Qt.AlignVCenter
                    radius: 18
                    color: _closeMouse.containsMouse ? Qt.rgba(1, 0, 0, 0.2) : "transparent"
                    Icon {
                        anchors.centerIn: parent
                        name: "i-close"
                        size: 18
                        color: "#ffffff"
                    }
                    MouseArea {
                        id: _closeMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.close()
                    }
                }
            }
        }
    }

    MediaPlayer {
        id: _player
        videoOutput: _videoOutput
        audioOutput: _audioOut
    }

    AudioOutput {
        id: _audioOut
        volume: 0.8
    }

    function _formatTime(ms) {
        if (!ms || ms <= 0) return "00:00"
        var s = Math.floor(ms / 1000)
        var m = Math.floor(s / 60)
        s = s % 60
        var h = Math.floor(m / 60)
        m = m % 60
        if (h > 0) {
            return (h < 10 ? "0" + h : h) + ":" + (m < 10 ? "0" + m : m) + ":" + (s < 10 ? "0" + s : s)
        }
        return (m < 10 ? "0" + m : m) + ":" + (s < 10 ? "0" + s : s)
    }
}
