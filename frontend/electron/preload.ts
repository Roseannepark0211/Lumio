/**
 * Electron 预加载脚本。
 *
 * 通过 contextBridge 暴露安全的 API 给渲染进程。
 * 渲染进程通过 lumio.fastapiBase / lumio.fastapiToken 访问动态生成的后端地址。
 * lumio.lumioFileUrl(path) 把本地文件路径转成 lumio-file:// URL（用于 <video>/<img>）。
 */

import { contextBridge, ipcRenderer } from "electron";

// 获取 FastAPI 连接信息（base URL + token）。
//
// 优先用 IPC sendSync 同步获取（sandbox 模式下唯一可靠方式）：
//   sandbox 模式下 preload 的 process.env 是 polyfill，读不到主进程
//   通过 process.env.X = Y 动态设置的变量。IPC sendSync 是同步阻塞调用，
//   在 preload 执行期间就能拿到主进程的响应。
//
// fallback 到 process.env（dev 模式 + 非 sandbox 场景）：
//   dev 模式下 sandbox 可能未启用，process.env 可用。
//   浏览器开发模式（非 Electron）回退到固定 38910。
let fastapiBase = "http://127.0.0.1:38910";
let fastapiToken = "";
try {
  const config = ipcRenderer.sendSync("get-fastapi-config") as
    | { base: string; token: string }
    | null;
  if (config && config.base) {
    fastapiBase = config.base;
    fastapiToken = config.token || "";
  } else {
    // IPC 返回 null/undefined（主进程 handler 未注册时）— fallback 到 env
    fastapiBase = process.env.LUMIO_FASTAPI_BASE || fastapiBase;
    fastapiToken = process.env.LUMIO_FASTAPI_TOKEN || fastapiToken;
  }
} catch {
  // sendSync 失败（主进程未注册 handler）— fallback 到 env
  fastapiBase = process.env.LUMIO_FASTAPI_BASE || fastapiBase;
  fastapiToken = process.env.LUMIO_FASTAPI_TOKEN || fastapiToken;
}

/**
 * 把本地文件绝对路径转成 lumio-file:// URL。
 * 例：C:\Users\foo\bar.mp4 → lumio-file://localhost/C%3A/Users/foo/bar.mp4
 * 渲染进程用 <video src={lumioFileUrl(path)}> 播放本地视频。
 *
 * ⚠️ URL 格式设计（关键 Bug 修复）：
 *   lumio-file 协议注册为 standard: true（见 main.ts registerSchemesAsPrivileged），
 *   Chromium 会按 RFC 3986 规范化 URL。
 *
 *   错误格式 lumio-file:///C:/Users/... 会被 Chromium 把 "C:" 当成 host:port，
 *   规范化为 lumio-file://c/Users/...（host=c，pathname 丢失盘符）。
 *   当 Lumio 安装在非 C 盘时，fs.existsSync("/Users/...") 解析为当前驱动器根目录
 *   → 文件找不到 → 404。
 *
 *   即便去掉冒号 lumio-file:///C/Users/...，Chromium 仍会把单字母 "C" 当成 host。
 *
 *   解决方案：使用固定 host "localhost"，把完整路径（含盘符冒号）放在 pathname 中。
 *   lumio-file://localhost/C%3A/Users/foo/bar.mp4
 *   - host=localhost（固定，不会变化）
 *   - pathname=/C%3A/Users/foo/bar.mp4（盘符冒号 URL 编码为 %3A，不会与 URL 语法冲突）
 *   - handler 中 decodeURIComponent(pathname) 还原为 /C:/Users/... → 去前导斜杠 → C:/Users/...
 *
 *   protocol.handle 会拦截所有 lumio-file:// 的请求，不管 host 是什么，
 *   所以使用 "localhost" 作为 host 不会触发实际网络请求。
 */
function lumioFileUrl(p: string): string {
  if (!p) return "";
  // 反斜杠 → 正斜杠（Windows 路径兼容）
  const normalized = p.replace(/\\/g, "/");
  // 按分隔符拆分，每段单独编码后拼接
  const segments = normalized.split("/");
  const encoded = segments
    .map((seg) => {
      // 空段（前导斜杠产生）保留
      if (seg === "") return seg;
      // 所有段（含盘符）统一 encodeURIComponent
      // "C:" → "C%3A"，不会被 Chromium 当成 authority
      return encodeURIComponent(seg);
    })
    .join("/");
  // 使用 localhost 作为固定 host，pathname 以 / 开头
  return `lumio-file://localhost/${encoded}`;
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
    /** 监听主进程发来的"重新加载数据"事件（每次菜单显示时触发） */
    onReload: (callback: () => void) => {
      ipcRenderer.on("tray:reload", () => callback());
    },
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
