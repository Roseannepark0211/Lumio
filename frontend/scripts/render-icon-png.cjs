/**
 * render-icon-png.cjs — 用 Electron BrowserWindow 将 logo-mark.svg 渲染为 1024x1024 icon.png
 *
 * 关键点：
 *   - 使用 win.setContentSize(SIZE, SIZE) 强制内容区为正方形
 *   - HTML 中用 div 容器撑满 100vw/100vh，SVG 自适应
 *   - capturePage 截取整个窗口（一定是正方形）
 *   - nativeImage resize 兜底（防止 HiDPI 导致尺寸不准）
 *
 * 用法：
 *   npx electron scripts/render-icon-png.cjs
 *
 * 输出：
 *   frontend/build/icon.png
 */

const { app, BrowserWindow, nativeImage } = require('electron');
const fs = require('fs');
const path = require('path');

const SVG_PATH = path.join(__dirname, '..', 'public', 'logo-mark.svg');
const OUT_PATH = path.join(__dirname, '..', 'build', 'icon.png');
const SIZE = 1024;

const buildDir = path.dirname(OUT_PATH);
if (!fs.existsSync(buildDir)) {
  fs.mkdirSync(buildDir, { recursive: true });
}

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    width: SIZE,
    height: SIZE,
    show: false,
    transparent: true,
    frame: false,
    resizable: false,
    webPreferences: {
      // 不使用 offscreen，普通后台窗口更稳定
      devTools: false,
    },
  });

  // 强制内容区为 SIZE x SIZE（不受标题栏/边框影响）
  win.setContentSize(SIZE, SIZE);

  // 用 HTML 包装 SVG，让 SVG 自适应填充整个窗口
  const svgBase64 = Buffer.from(fs.readFileSync(SVG_PATH)).toString('base64');
  const html = `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body {
    width: 100vw;
    height: 100vh;
    overflow: hidden;
    background: transparent;
  }
  .container {
    width: 100vw;
    height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  img {
    width: 100vw;
    height: 100vh;
    display: block;
    object-fit: contain;
  }
</style>
</head>
<body>
<div class="container">
  <img src="data:image/svg+xml;base64,${svgBase64}" />
</div>
</body>
</html>`;

  const htmlBase64 = Buffer.from(html).toString('base64');
  await win.loadURL(`data:text/html;base64,${htmlBase64}`);

  // 等待 SVG 滤镜和渐变完全渲染
  await new Promise(resolve => setTimeout(resolve, 2000));

  // 截图 — 一定是正方形
  const image = await win.webContents.capturePage();
  const rawBuffer = image.toPNG();
  const rawSize = image.getSize();

  // 用 nativeImage resize 到精确 SIZE x SIZE（兜底，防止 HiDPI 导致尺寸不准）
  const ni = nativeImage.createFromBuffer(rawBuffer);
  const final = ni.resize({ width: SIZE, height: SIZE, quality: 'best' });
  const finalBuffer = final.toPNG();

  fs.writeFileSync(OUT_PATH, finalBuffer);

  console.log(`✓ icon.png 已生成: ${OUT_PATH}`);
  console.log(`  截图原始尺寸: ${rawSize.width}x${rawSize.height}`);
  console.log(`  最终尺寸: ${SIZE}x${SIZE}`);
  console.log(`  文件大小: ${(finalBuffer.length / 1024).toFixed(1)} KB`);

  win.destroy();
  app.quit();
}).catch(err => {
  console.error('✗ 生成失败:', err);
  app.exit(1);
});
