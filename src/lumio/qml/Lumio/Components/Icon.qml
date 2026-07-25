// ============================================================
// LUMIO // Icon — SVG 图标组件
// ------------------------------------------------------------
// 用法：
//   Icon { name: "i-home"; size: 20; color: Theme.textPrimary }
// 底层通过 IconProvider（image://icons/）渲染 SVG symbol
// ============================================================
import QtQuick
import Lumio

Item {
    id: root

    // ---------- 公开属性 ----------
    property string name: ""           // SVG symbol id，如 "i-home"
    property int size: 16              // 输出尺寸（px）
    property color color: Theme.textPrimary  // currentColor

    implicitWidth: size
    implicitHeight: size

    // ---------- 渲染 ----------
    Image {
        anchors.fill: parent
        source: name.length > 0
                ? "image://icons/%1?color=%2&size=%3"
                    .arg(name)
                    .arg(_urlEncode(color))
                    .arg(size)
                : ""
        sourceSize.width: size * 2   // 2x for retina sharpness
        sourceSize.height: size * 2
        fillMode: Image.PreserveAspectFit
        smooth: true
        asynchronous: true
    }

    // ---------- URL 颜色编码 ----------
    // Qt.rgba → "#rrggbb" → URL-encode "#"
    function _urlEncode(c) {
        var r = Math.round(c.r * 255)
        var g = Math.round(c.g * 255)
        var b = Math.round(c.b * 255)
        var hex = "#" + _pad(r) + _pad(g) + _pad(b)
        return encodeURIComponent(hex)
    }

    function _pad(n) {
        var s = n.toString(16)
        return s.length === 1 ? "0" + s : s
    }
}
