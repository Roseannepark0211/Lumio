import { defineManifest } from "@crxjs/vite-plugin";
import pkg from "./package.json";

/**
 * Lumio Browser Extension - MV3 Manifest
 *
 * 阶段 1：仅基础 popup + background（连接状态 + 主按钮发送 URL）
 * 阶段 2：加 content_scripts（平台元数据提取）
 * 阶段 3：加 commands + omnibox
 */
export const manifest = defineManifest({
  manifest_version: 3,
  name: "Lumio",
  version: pkg.version,
  description:
    "将网页中的视频/图片一键发送到 Lumio 桌面客户端下载（支持 YouTube/Instagram/X/B站/快手/小红书）",
  permissions: [
    "activeTab",
    "tabs",
    "contextMenus",
    "storage",
    "scripting",
    "commands",
    "omnibox",
  ],
  host_permissions: [
    "*://*.youtube.com/*",
    "*://*.youtu.be/*",
    "*://*.instagram.com/*",
    "*://*.x.com/*",
    "*://*.twitter.com/*",
    "*://*.bilibili.com/*",
    "*://*.b23.tv/*",
    "*://*.kuaishou.com/*",
    "*://*.xiaohongshu.com/*",
    "*://*.xhslink.com/*",
    "*://*.xhslink.cn/*",
    // Bug 3: 允许任意端口的 localhost 通信（用户可在 Lumio 设置中自定义 Flask 端口）
    "http://127.0.0.1/*",
    "http://localhost/*",
  ],
  background: {
    service_worker: "src/background/index.ts",
    type: "module",
  },
  content_scripts: [
    {
      matches: [
        "*://*.youtube.com/*",
        "*://*.instagram.com/*",
        "*://*.x.com/*",
        "*://*.twitter.com/*",
        "*://*.bilibili.com/*",
        "*://*.kuaishou.com/*",
        "*://*.xiaohongshu.com/*",
      ],
      js: ["src/content/index.ts"],
      run_at: "document_idle",
    },
  ],
  action: {
    default_popup: "src/popup/index.html",
    default_title: "Lumio",
    default_icon: {
      16: "src/assets/icons/logo-16.png",
      32: "src/assets/icons/logo-32.png",
      48: "src/assets/icons/logo-48.png",
      128: "src/assets/icons/logo-128.png",
    },
  },
  icons: {
    16: "src/assets/icons/logo-16.png",
    32: "src/assets/icons/logo-32.png",
    48: "src/assets/icons/logo-48.png",
    128: "src/assets/icons/logo-128.png",
  },
  // 阶段 3：快捷键
  commands: {
    _execute_action: {
      suggested_key: { default: "Ctrl+Shift+L", mac: "Command+Shift+L" },
      description: "打开 Lumio popup",
    },
    "capture-page-silent": {
      suggested_key: { default: "Ctrl+Shift+D", mac: "Command+Shift+D" },
      description: "静默发送当前页面到 Lumio",
    },
  },
  // 阶段 3：地址栏 omnibox
  omnibox: { keyword: "lumio" },
});
