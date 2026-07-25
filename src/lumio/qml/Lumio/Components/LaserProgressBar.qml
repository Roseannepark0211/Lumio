// ============================================================
// LUMIO // LaserProgressBar — 激光粒子进度条
// ------------------------------------------------------------
// 还原 design_preview/liquid_glass_home.html 的签名时刻：
//   - 渐变填充（紫→蓝→青）
//   - 激光头白色亮点 + 光晕
//   - 80 粒子上限的 Canvas 粒子拖尾
//   - 60fps rAF 驱动，CPU <1%
// ============================================================
import QtQuick
import Lumio

Item {
    id: root

    // ---------- 公开属性 ----------
    property real progress: 0.0       // 0..1（自动 clamp）
    property string labelText: ""     // 左侧标签（如 "Spooling · 12.4 MB / 18.2 MB"）
    property bool particlesEnabled: true
    property bool compact: false      // compact 模式隐藏 label 区域，只显示 bar+粒子

    // progress clamp 到 0..1，防止后端传 100 等越界值导致宽度爆炸
    readonly property real _p: Math.max(0, Math.min(1, progress))

    implicitHeight: compact ? 20 : 50  // compact 只含 bar，否则含上下 label
    implicitWidth: 400

    // ============================================================
    // 上方 label + 百分比
    // ============================================================
    Item {
        id: _meta
        visible: !root.compact
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: 24

        Text {
            anchors.left: parent.left
            anchors.baseline: parent.baseline
            text: root.labelText
            color: Theme.textDim
            font.family: Theme.fontBody
            font.pixelSize: Theme.fsMicro
            font.weight: Font.Medium
            font.letterSpacing: 0.3
        }

        // 百分比（渐变文字 — Canvas 模拟 background-clip:text）
        Canvas {
            id: _pctCanvas
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            width: 70
            height: 24
            renderStrategy: Canvas.Cooperative

            onPaint: {
                var ctx = getContext("2d")
                ctx.reset()
                var pct = Math.round(root._p * 100)
                var text = pct + "%"
                ctx.font = "700 22px " + Theme.fontDisplay
                ctx.textBaseline = "middle"
                var metrics = ctx.measureText(text)
                var w = Math.max(1, metrics.width)
                var grad = ctx.createLinearGradient(0, 0, w, 0)
                grad.addColorStop(0.0, "#ffffff")
                grad.addColorStop(1.0, "#a8c7ff")
                ctx.fillStyle = grad
                ctx.fillText(text, 70 - w, 12)
            }

            // 监听 root.progress 变化触发重绘
            // （_p 是 progress 的派生 readonly property，带下划线前缀的属性
            //   QML 不会生成合法的 onPChanged 信号名，所以监听源属性 progress）
            Connections {
                target: root
                function onProgressChanged() { _pctCanvas.requestPaint() }
            }
        }
    }

    // ============================================================
    // 进度条 track + fill + 激光头
    // ============================================================
    Item {
        id: _bar
        anchors.top: root.compact ? parent.top : _meta.bottom
        anchors.bottom: root.compact ? parent.bottom : undefined
        anchors.left: parent.left
        anchors.right: parent.right
        height: root.compact ? undefined : 20  // compact 模式下用 anchors.fill 高度

        // track 背景
        Rectangle {
            id: _track
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.right: parent.right
            height: 8
            radius: Theme.rPill
            color: Qt.rgba(0, 0, 0, 0.3)
            border.width: 1
            border.color: Theme.glassBorder

            // 内嵌阴影
            Rectangle {
                anchors.fill: parent
                anchors.margins: 1
                radius: parent.radius
                gradient: Gradient {
                    orientation: Gradient.Vertical
                    GradientStop { position: 0.0; color: Qt.rgba(0, 0, 0, 0.4) }
                    GradientStop { position: 1.0; color: Qt.rgba(0, 0, 0, 0.1) }
                }
            }
        }

        // fill 渐变
        Rectangle {
            id: _fill
            anchors.left: _track.left
            anchors.verticalCenter: _track.verticalCenter
            height: _track.height
            width: Math.max(0, _track.width * root._p)
            radius: _track.radius
            clip: true

            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: Theme.accent2 }
                GradientStop { position: 0.5; color: Theme.accent }
                GradientStop { position: 1.0; color: "#4cc2ff" }
            }

            // fill 光晕（可后续加 MultiEffect blur）
            layer.enabled: true
            layer.effect: null
        }

        // 激光头亮点
        Rectangle {
            id: _laserHead
            visible: root._p > 0.001 && root._p < 0.999
            x: _fill.x + _fill.width - 2
            anchors.verticalCenter: _track.verticalCenter
            width: 4
            height: _track.height + 4
            radius: Theme.rPill
            color: "#ffffff"

            // 外发光
            Rectangle {
                anchors.centerIn: parent
                width: 32
                height: 32
                radius: 16
                color: Qt.rgba(1, 1, 1, 0.4)
                layer.enabled: true
                layer.effect: null
            }
        }

        // ============================================================
        // 粒子 Canvas — 80 粒子上限的激光拖尾
        // ============================================================
        Canvas {
            id: _particleCanvas
            visible: root.particlesEnabled
            anchors.fill: parent
            anchors.topMargin: -10
            anchors.bottomMargin: -10
            z: 2

            // 粒子状态（注：Canvas 没有 class，用内部对象数组）
            property var _particles: []

            renderStrategy: Canvas.Cooperative
            renderTarget: Canvas.FramebufferObject

            onWidthChanged: _schedulePaint()
            onHeightChanged: _schedulePaint()

            // 用 Timer 驱动 60fps 重绘（QML Canvas 不支持 requestAnimationFrame）
            Timer {
                id: _tick
                interval: 16  // ~60fps
                repeat: true
                running: root.visible && root.particlesEnabled
                onTriggered: _particleCanvas._tick()
            }

            function _schedulePaint() {
                requestPaint()
            }

            function _spawnParticle(headX, headY) {
                if (_particles.length > 80) return
                var angle = (Math.random() - 0.5) * Math.PI * 0.7 + Math.PI  // backward fan
                var speed = 0.5 + Math.random() * 1.8
                _particles.push({
                    x: headX,
                    y: headY + (Math.random() - 0.5) * 4,
                    vx: Math.cos(angle) * speed,
                    vy: Math.sin(angle) * speed * 0.6,
                    life: 1,
                    decay: 0.012 + Math.random() * 0.018,
                    size: 1 + Math.random() * 2,
                    hue: 200 + Math.random() * 40
                })
            }

            function _tick() {
                var ctx = getContext("2d")
                ctx.reset()
                var headX = _fill.x + _fill.width
                var headY = _track.y - _particleCanvas.y + _track.height / 2

                // 生成新粒子
                if (root._p > 0.01 && root._p < 0.99) {
                    var spawnCount = Math.random() < 0.7 ? 2 : 1
                    for (var i = 0; i < spawnCount; i++) {
                        _spawnParticle(headX, headY)
                    }
                }

                // hsla→rgba 工具：QML Canvas addColorStop 不支持 hsla() 字符串，
                // 必须转成 rgba(r,g,b,a) 格式（hue 200-240 蓝-青色域）
                function _hsla(h, s, l, a) {
                    s /= 100; l /= 100
                    var k = (h % 360) / 360
                    var q = l < 0.5 ? l * (1 + s) : l + s - l * s
                    var p = 2 * l - q
                    function _hue(t) {
                        if (t < 0) t += 1
                        if (t > 1) t -= 1
                        if (t < 1/6) return p + (q - p) * 6 * t
                        if (t < 1/2) return q
                        if (t < 2/3) return p + (q - p) * (2/3 - t) * 6
                        return p
                    }
                    var r = Math.round(_hue(k + 1/3) * 255)
                    var g = Math.round(_hue(k) * 255)
                    var b = Math.round(_hue(k - 1/3) * 255)
                    return "rgba(" + r + "," + g + "," + b + "," + a + ")"
                }

                // 更新 + 绘制粒子
                for (var j = _particles.length - 1; j >= 0; j--) {
                    var p = _particles[j]
                    p.x += p.vx
                    p.y += p.vy
                    p.vy += 0.02
                    p.life -= p.decay
                    if (p.life <= 0) {
                        _particles.splice(j, 1)
                        continue
                    }
                    var alpha = p.life * 0.9
                    var r = p.size * p.life

                    // 外发光
                    var grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, r * 4)
                    grad.addColorStop(0,   _hsla(p.hue, 100, 70, alpha))
                    grad.addColorStop(0.4, _hsla(p.hue, 100, 60, alpha * 0.4))
                    grad.addColorStop(1,   _hsla(p.hue, 100, 50, 0))
                    ctx.fillStyle = grad
                    ctx.beginPath()
                    ctx.arc(p.x, p.y, r * 4, 0, Math.PI * 2)
                    ctx.fill()

                    // 亮核
                    ctx.fillStyle = _hsla(p.hue, 100, 90, alpha)
                    ctx.beginPath()
                    ctx.arc(p.x, p.y, r, 0, Math.PI * 2)
                    ctx.fill()
                }

                // 激光头光晕
                if (root._p > 0.001 && root._p < 0.999) {
                    var headGrad = ctx.createRadialGradient(headX, headY, 0, headX, headY, 16)
                    headGrad.addColorStop(0, "rgba(255, 255, 255, 0.9)")
                    headGrad.addColorStop(0.3, "rgba(120, 180, 255, 0.5)")
                    headGrad.addColorStop(1, "rgba(10, 132, 255, 0)")
                    ctx.fillStyle = headGrad
                    ctx.beginPath()
                    ctx.arc(headX, headY, 16, 0, Math.PI * 2)
                    ctx.fill()
                }
                requestPaint()
            }

            onPaint: {
                // 实际绘制由 _tick 推进
            }
        }
    }

    // 平滑动画
    Behavior on progress {
        NumberAnimation {
            duration: 300
            easing.type: Easing.OutCubic
        }
    }
}
