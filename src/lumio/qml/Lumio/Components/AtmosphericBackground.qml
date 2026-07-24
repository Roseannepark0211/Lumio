import QtQuick
import Lumio

// 还原 design_preview/styles.css 的 body 背景：
//   - 底层垂直线性渐变（bgGrad1 → bgGrad2）
//   - 4 个径向光球（紫 / 粉红 / 蓝 / 橙）
//   - 200x200 随机噪点层（opacity 0.025，对应 body::before）
Item {
    id: root

    // 从 Theme 单例获取颜色（值见 styles.css :root）
    property color grad1: Theme.bgGrad1
    property color grad2: Theme.bgGrad2

    // ---- 底层渐变 + 4 层径向光球 ----
    Canvas {
        id: bgCanvas
        anchors.fill: parent

        onPaint: {
            var ctx = getContext("2d")
            var w = width
            var h = height
            ctx.reset()

            // 底层线性渐变（180deg: 上 → 下）
            var lg = ctx.createLinearGradient(0, 0, 0, h)
            lg.addColorStop(0, grad1)
            lg.addColorStop(1, grad2)
            ctx.fillStyle = lg
            ctx.fillRect(0, 0, w, h)

            // 4 层径向光球（还原 CSS radial-gradient ellipse）
            // 球1: 中心 (0.15, 0.0)，大小 80%x60%，紫
            drawOrb(ctx, w * 0.15, h * 0.0, w * 0.8, h * 0.6, "rgba(94,92,230,0.28)", 0.6)
            // 球2: 中心 (0.85, 0.2)，大小 70%x50%，粉红
            drawOrb(ctx, w * 0.85, h * 0.2, w * 0.7, h * 0.5, "rgba(255,55,92,0.18)", 0.55)
            // 球3: 中心 (0.8, 1.0)，大小 60%x80%，蓝
            drawOrb(ctx, w * 0.8, h * 1.0, w * 0.6, h * 0.8, "rgba(10,132,255,0.22)", 0.6)
            // 球4: 中心 (0.3, 0.9)，大小 50%x50%，橙
            drawOrb(ctx, w * 0.3, h * 0.9, w * 0.5, h * 0.5, "rgba(255,159,10,0.12)", 0.6)
        }

        // 绘制单个椭圆径向光球：通过 translate + scale 把单位圆拉伸成椭圆
        function drawOrb(ctx, cx, cy, rx, ry, color, fade) {
            ctx.save()
            ctx.translate(cx, cy)
            ctx.scale(rx, ry)
            var grad = ctx.createRadialGradient(0, 0, 0, 0, 0, 1)
            // 把 rgba(...,a) 的 alpha 替换成 0 得到透明色
            var transparent = color.replace(/[\d.]+\)$/, '0)')
            grad.addColorStop(0, color)
            grad.addColorStop(fade, transparent)
            grad.addColorStop(1, transparent)
            ctx.fillStyle = grad
            ctx.fillRect(-1, -1, 2, 2)
            ctx.restore()
        }

        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
    }

    // ---- 噪点层（还原 body::before，opacity 0.025）----
    Canvas {
        id: noiseCanvas
        anchors.fill: parent
        opacity: 0.025

        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var w = Math.ceil(width)
            var h = Math.ceil(height)
            var tileSize = 200

            // 生成 200x200 随机灰度噪点 tile
            var tileImageData = ctx.createImageData(tileSize, tileSize)
            var td = tileImageData.data
            for (var i = 0; i < td.length; i += 4) {
                var v = Math.floor(Math.random() * 255)
                td[i] = v
                td[i + 1] = v
                td[i + 2] = v
                td[i + 3] = 255
            }

            // 平铺到整个画布
            for (var x = 0; x < w; x += tileSize) {
                for (var y = 0; y < h; y += tileSize) {
                    ctx.putImageData(tileImageData, x, y)
                }
            }
        }

        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
    }
}
