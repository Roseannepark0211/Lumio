/**
 * Electron 预加载脚本。
 *
 * 通过 contextBridge 暴露安全的 API 给渲染进程。
 * 渲染进程通过 lumio.fastapiBase / lumio.fastapiToken 访问动态生成的后端地址。
 * lumio.lumioFileUrl(path) 把本地文件路径转成 lumio-file:// URL（用于 <video>/<img>）。
 */

import { contextBridge, ipcRenderer } from "electron";

const fastapiBase = process.env.LUMIO_FASTAPI_BASE || "http://127.0.0.1:38910";
const fastapiToken = process.env.LUMIO_FASTAPI_TOKEN || "";

/**
 * 把本地文件绝对路径转成 lumio-file:// URL。
 * 例：C:\Users\foo\bar.mp4 → lumio-file:///C:/Users/foo/bar.mp4
 * 渲染进程用 <video src={lumioFileUrl(path)}> 播放本地视频。
 *
 * 关键：不对路径做 encodeURIComponent！
 * - encodeURIComponent("C:") = "C%3A"，导致 URL 形如 lumio-file:///C%3A/Users/...
 * - Chromium 的 URL safety check 会拒绝带 %3A 的路径，
 *   <video> 报错 "Media load rejected by URL safety check"
 * - lumio-file:// 是自定义 protocol，路径部分直接拼接即可，
 *   main.ts 的 handler 用 decodeURIComponent 兜底解码
 */
function lumioFileUrl(p: string): string {
  if (!p) return "";
  // 反斜杠 → 正斜杠（Windows 路径兼容）
  const normalized = p.replace(/\\/g, "/");
  // lumio-file:/// + 路径（带前导斜杠表示 absolute）
  // 不做 URL 编码，保留 C: 形式
  return `lumio-file:///${normalized}`;
}

/** 文件过滤器（与 Electron FileFilter 对齐） */
export interface ElectronFileFilter {
  name: string;
  extensions: string[];
}

contextBridge.exposeInMainWorld("lumio", {
  version: "0.1.0",
  platform: process.platform,
  isElectron: true,
  fastapiBase,
  fastapiToken,
  lumioFileUrl,
  /** 打开文件夹选择对话框，返回选中路径（取消返回空串） */
  pickFolder: (): Promise<string> => ipcRenderer.invoke("dialog:open-folder"),
  /** 打开文件选择对话框（支持多选），返回路径数组 */
  pickFiles: (filters?: ElectronFileFilter[]): Promise<string[]> =>
    ipcRenderer.invoke("dialog:open-files", filters),
  /** 托盘菜单 IPC 桥接 — tray-menu.html / close-dialog.html 调用 */
  tray: {
    showWindow: () => ipcRenderer.send("tray:action", "showWindow"),
    openDir: () => ipcRenderer.send("tray:action", "openDir"),
    navigate: (page: string) => ipcRenderer.send("tray:action", "navigate", page),
    toggleTheme: () => ipcRenderer.send("tray:action", "toggleTheme"),
    pauseAll: () => ipcRenderer.send("tray:action", "pauseAll"),
    quit: () => ipcRenderer.send("tray:action", "quit"),
    close: () => ipcRenderer.send("tray:action", "close"),
    // 关闭确认弹窗
    cancelClose: () => ipcRenderer.send("tray:close-dialog", "cancel"),
    minimizeToTray: () => ipcRenderer.send("tray:close-dialog", "minimize"),
    quitApp: () => ipcRenderer.send("tray:close-dialog", "quit"),
    // 前端 render() 后报告菜单实际高度，主进程据此调整 BrowserWindow 高度
    reportHeight: (height: number) => ipcRenderer.send("tray:report-height", height),
  },
  /** 监听托盘菜单导航事件（主进程 → 渲染进程） */
  onNavigate: (callback: (page: string) => void) => {
    ipcRenderer.on("navigate", (_e, page: string) => callback(page));
  },
  /** 自动更新 IPC 桥接 — SettingsPage 检查更新流程调用 */
  updater: {
    /** 手动检查更新（用户点击"检查更新"按钮触发） */
    check: () => ipcRenderer.invoke("updater:check"),
    /** 开始下载更新（用户在更新对话框点"立即下载"触发） */
    download: () => ipcRenderer.invoke("updater:download"),
    /** 退出并安装更新（用户在下载完成提示点"立即重启"触发） */
    quitAndInstall: () => ipcRenderer.invoke("updater:quit-and-install"),
    /** 监听主进程推送的更新事件 */
    onEvent: (callback: (channel: string, data: any) => void) => {
      const channels = [
        "update:checking",
        "update:available",
        "update:not-available",
        "update:download-progress",
        "update:downloaded",
        "update:error",
      ];
      channels.forEach((ch) => {
        ipcRenderer.on(ch, (_e, data: any) => callback(ch, data));
      });
    },
  },
});
