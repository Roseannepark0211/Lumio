/**
 * 自动更新管理器（基于 electron-updater）。
 *
 * 设计要点：
 *   1. 三平台分流：
 *      - Windows/Linux: 走 electron-updater 全自动（检查→下载→安装）
 *      - macOS: 无 Apple Developer 证书时降级为"手动下载 DMG"模式，
 *        只调 GitHub API 检查版本 + 打开 Release 页面，不走 electron-updater
 *
 *   2. 用户体验：
 *      - autoDownload: false —— 发现新版本后不自动下载，弹窗让用户决定
 *      - autoInstallOnAppQuit: true —— 用户选"下次启动时安装"时，退出应用自动安装
 *      - 进度条：通过 IPC 推送 download-progress 事件给渲染进程
 *
 *   3. 双进程安全：
 *      - before-quit-for-update 事件中先 SIGTERM LumioAPI 子进程（5s 超时）
 *      - 避免 NSIS 安装时 LumioAPI.exe 文件被占用导致替换失败
 *
 *   4. 安全：
 *      - verifyUpdateCodeSignature: true（默认）—— 校验下载包签名
 *      - electron-updater ≥6.3.0 修复 CVE-2024-39698 签名绕过漏洞
 *
 *   5. 错误提示用户友好化：
 *      - electron-updater / Node 抛出的英文技术错误（如 net::ERR_CONNECTION_TIMED_OUT）
 *        经 friendlyUpdateError() 映射为中文提示，原文保留为 detail 供排查
 */

import { app, BrowserWindow, ipcMain, shell, dialog } from "electron";
import { autoUpdater } from "electron-updater";
import type { ChildProcess } from "node:child_process";

/** GitHub Release 页面（macOS 手动下载 / 报错兜底用） */
const RELEASES_URL = "https://github.com/Roseannepark0211/Lumio/releases/latest";

/** Lumio 官网（设置页「关于」里的官网按钮用，固定域名，不随版本变） */
const WEBSITE_URL = "https://xksye7.dpdns.org/";

// ============================================================
// 错误文案映射：英文技术错误 → 用户能看懂的中文提示
// 原文保留为 detail，随事件一起发给渲染进程（小字展示，方便报障排查）
// ============================================================
const UPDATE_ERROR_PATTERNS: Array<[RegExp, string]> = [
  [/ERR_INTERNET_DISCONNECTED/i, "网络未连接，请检查网络连接后重试"],
  [/ERR_CONNECTION_TIMED_OUT|ETIMEDOUT|ERR_TIMED_OUT|GitHub API timeout/i, "连接 GitHub 超时，可能是网络较慢，请稍后重试"],
  [/ERR_NAME_NOT_RESOLVED|ERR_NAME_RESOLUTION_FAILED|ENOTFOUND|getaddrinfo/i, "无法连接到 GitHub，请检查网络或 DNS 设置"],
  [/ERR_CONNECTION_REFUSED|ECONNREFUSED/i, "连接被拒绝，请检查防火墙或代理设置"],
  [/ERR_PROXY_CONNECTION_FAILED/i, "代理服务器连接失败，请检查系统代理设置"],
  [/ERR_NETWORK_CHANGED/i, "网络环境发生变化，请重试"],
  [/ERR_ABORTED/i, "更新请求被中断，请重试"],
  [/HttpError:\s*404|GitHub API 404/i, "更新服务器暂时不可用，请稍后重试"],
  [/HttpError:\s*403|GitHub API 403/i, "GitHub 访问受限（可能请求过于频繁），请稍后重试"],
  [/HttpError:\s*5\d\d/i, "GitHub 服务器繁忙，请稍后重试"],
  [/Latest version info is empty/i, "未能获取到版本信息，请检查网络后重试"],
  [/not signed by the application owner/i, "新版本签名校验失败，已中止更新以保护你的设备"],
  [/ENOENT/i, "更新文件读取失败，请重试"],
];

/** 把原始错误翻译成用户友好的中文提示（附带原文 detail） */
export function friendlyUpdateError(raw: unknown): { message: string; detail: string } {
  const detail = raw instanceof Error ? raw.message : String(raw ?? "");
  for (const [pattern, message] of UPDATE_ERROR_PATTERNS) {
    if (pattern.test(detail)) return { message, detail };
  }
  return { message: "检查更新失败，请检查网络连接后重试", detail };
}

// ============================================================
// 类型定义（与渲染进程共享）
// ============================================================

export interface UpdateInfo {
  version: string;
  releaseNotes: string | null;
  releaseName: string | null;
  releaseDate: string | null;
}

export interface DownloadProgress {
  percent: number;
  transferredBytes: number;
  totalBytes: number;
  bytesPerSecond: number;
}

export interface CheckUpdateResult {
  hasUpdate: boolean;
  info: UpdateInfo | null;
  /** 用户友好的中文错误提示（无错误时为 null） */
  error: string | null;
  /** 原始英文技术错误（排查用，可选） */
  errorDetail?: string | null;
}

// ============================================================
// UpdaterManager 类
// ============================================================

export class UpdaterManager {
  private getMainWindow: () => BrowserWindow | null;
  private getFastApiProcess: () => ChildProcess | null;
  private killFastApi: () => Promise<void>;
  private isQuittingForUpdate = false;

  constructor(opts: {
    getMainWindow: () => BrowserWindow | null;
    getFastApiProcess: () => ChildProcess | null;
    killFastApi: () => Promise<void>;
  }) {
    this.getMainWindow = opts.getMainWindow;
    this.getFastApiProcess = opts.getFastApiProcess;
    this.killFastApi = opts.killFastApi;
  }

  /** 初始化：配置 autoUpdater + 注册 IPC handlers + 监听事件 */
  init(): void {
    // 只在打包模式下启用自动更新
    // dev 模式下 electron-updater 找不到 latest.yml，会报错
    if (!app.isPackaged) {
      console.log("[updater] dev mode, auto-update disabled");
      this.registerIpcHandlers();
      return;
    }

    // macOS 无 Apple Developer 证书时降级为"手动下载 DMG"模式
    // electron-updater 在 macOS 上需要签名+公证才能工作
    const isMacosManualMode = process.platform === "darwin";

    if (isMacosManualMode) {
      console.log("[updater] macOS manual download mode (no Apple Developer cert)");
      this.registerIpcHandlers();
      return;
    }

    // Windows/Linux: 走 electron-updater 全自动
    autoUpdater.autoDownload = false; // 用户决定是否下载
    autoUpdater.autoInstallOnAppQuit = true; // 退出时自动安装已下载的更新
    autoUpdater.allowDowngrade = false;
    autoUpdater.allowPrerelease = false;

    // 监听事件并转发给渲染进程
    autoUpdater.on("checking-for-update", () => {
      this.sendToRenderer("update:checking", null);
    });

    autoUpdater.on("update-available", (info) => {
      const updateInfo: UpdateInfo = {
        version: info.version,
        releaseNotes: this.normalizeReleaseNotes(info.releaseNotes),
        releaseName: info.releaseName || null,
        releaseDate: info.releaseDate || null,
      };
      this.sendToRenderer("update:available", updateInfo);
    });

    autoUpdater.on("update-not-available", (info) => {
      this.sendToRenderer("update:not-available", { version: info.version });
    });

    autoUpdater.on("download-progress", (progress) => {
      const p: DownloadProgress = {
        percent: progress.percent,
        transferredBytes: progress.transferred,
        totalBytes: progress.total,
        bytesPerSecond: progress.bytesPerSecond,
      };
      this.sendToRenderer("update:download-progress", p);
    });

    autoUpdater.on("update-downloaded", (info) => {
      const updateInfo: UpdateInfo = {
        version: info.version,
        releaseNotes: this.normalizeReleaseNotes(info.releaseNotes),
        releaseName: info.releaseName || null,
        releaseDate: info.releaseDate || null,
      };
      this.sendToRenderer("update:downloaded", updateInfo);
    });

    autoUpdater.on("error", (err) => {
      console.error("[updater] error:", err);
      const friendly = friendlyUpdateError(err);
      this.sendToRenderer("update:error", { message: friendly.message, detail: friendly.detail });
    });

    this.registerIpcHandlers();
    console.log("[updater] initialized (electron-updater mode)");
  }

  /** 启动后延迟 10 秒自动检查更新（避免阻塞首屏） */
  scheduleAutoCheck(delayMs = 10_000): void {
    if (!app.isPackaged) return;
    setTimeout(() => {
      this.checkForUpdates().catch((err) => {
        console.error("[updater] auto check failed:", err);
      });
    }, delayMs);
  }

  /** 手动触发检查更新（IPC 调用） */
  async checkForUpdates(): Promise<CheckUpdateResult> {
    if (!app.isPackaged) {
      return { hasUpdate: false, info: null, error: "dev mode" };
    }

    // macOS: 手动模式，调 GitHub API
    if (process.platform === "darwin") {
      return this.checkUpdateMacosManual();
    }

    // Windows/Linux: electron-updater
    try {
      const result = await autoUpdater.checkForUpdates();
      if (!result || !result.updateInfo) {
        return { hasUpdate: false, info: null, error: null };
      }
      const info = result.updateInfo;
      // 用语义版本对比代替字符串 !==，避免 "4.4.2" vs "4.4.10" 误判
      // electron-updater 内部已做 isUpdateAvailable 判断，但这里二次校验
      // 防止 allowDowngrade=false 时旧版本被误判为新版本
      const hasUpdate = this.compareVersions(app.getVersion(), info.version) < 0;
      return {
        hasUpdate,
        info: {
          version: info.version,
          releaseNotes: this.normalizeReleaseNotes(info.releaseNotes),
          releaseName: info.releaseName || null,
          releaseDate: info.releaseDate || null,
        },
        error: null,
      };
    } catch (e: any) {
      const friendly = friendlyUpdateError(e);
      return { hasUpdate: false, info: null, error: friendly.message, errorDetail: friendly.detail };
    }
  }

  /** 开始下载更新（IPC 调用，用户点"立即下载"后触发） */
  async downloadUpdate(): Promise<{ ok: boolean; error: string | null }> {
    if (!app.isPackaged) {
      return { ok: false, error: "dev mode" };
    }
    if (process.platform === "darwin") {
      // macOS 手动模式：直接打开 Release 页面
      await shell.openExternal(RELEASES_URL);
      return { ok: true, error: null };
    }
    try {
      await autoUpdater.downloadUpdate();
      return { ok: true, error: null };
    } catch (e: any) {
      const friendly = friendlyUpdateError(e);
      return { ok: false, error: friendly.message };
    }
  }

  /** 退出并安装更新（IPC 调用，用户点"立即重启"后触发） */
  async quitAndInstall(): Promise<void> {
    if (!app.isPackaged) return;
    if (process.platform === "darwin") {
      // macOS 手动模式：没有下载流程，直接退出让用户手动安装 DMG
      app.quit();
      return;
    }

    // 设置标志位，before-quit 事件中知道这是更新退出
    this.isQuittingForUpdate = true;

    // 先优雅关闭 FastAPI 子进程（5s 超时）
    try {
      await this.killFastApi();
    } catch (e) {
      console.error("[updater] kill FastAPI failed:", e);
    }

    // 调用 electron-updater 的 quitAndInstall
    // isSilent=false 会让安装器显示 UI（推荐，让用户看到安装进度）
    // isForceRunAfter=true 安装完成后自动启动新版本
    autoUpdater.quitAndInstall(false, true);
  }

  /** 是否正在为更新而退出（main.ts 的 before-quit 事件可读取此标志） */
  getIsQuittingForUpdate(): boolean {
    return this.isQuittingForUpdate;
  }

  // ============================================================
  // 内部方法
  // ============================================================

  /** macOS 手动模式：调 GitHub API 检查版本 */
  private async checkUpdateMacosManual(): Promise<CheckUpdateResult> {
    try {
      const https = await import("node:https");
      const apiUrl = "https://api.github.com/repos/Roseannepark0211/Lumio/releases/latest";
      const data: any = await new Promise((resolve, reject) => {
        const req = https.get(apiUrl, {
          headers: { "User-Agent": "Lumio" },
          timeout: 8000,
        }, (res) => {
          if (res.statusCode !== 200) {
            reject(new Error(`GitHub API ${res.statusCode}`));
            return;
          }
          let body = "";
          res.on("data", (chunk) => (body += chunk));
          res.on("end", () => {
            try {
              resolve(JSON.parse(body));
            } catch (e) {
              reject(e);
            }
          });
        });
        req.on("error", reject);
        req.on("timeout", () => {
          req.destroy();
          reject(new Error("GitHub API timeout"));
        });
      });

      const latest = (data.tag_name || "").replace(/^v/, "");
      const current = app.getVersion();
      const hasUpdate = this.compareVersions(current, latest) < 0;

      return {
        hasUpdate,
        info: {
          version: latest,
          releaseNotes: data.body || null,
          releaseName: data.name || null,
          releaseDate: data.published_at || null,
        },
        error: null,
      };
    } catch (e: any) {
      const friendly = friendlyUpdateError(e);
      return { hasUpdate: false, info: null, error: friendly.message, errorDetail: friendly.detail };
    }
  }

  /** 注册 IPC handlers（渲染进程通过 window.lumio.updater.* 调用） */
  private registerIpcHandlers(): void {
    ipcMain.handle("updater:check", async () => {
      return this.checkForUpdates();
    });

    ipcMain.handle("updater:download", async () => {
      return this.downloadUpdate();
    });

    ipcMain.handle("updater:quit-and-install", async () => {
      await this.quitAndInstall();
      return { ok: true };
    });

    ipcMain.handle("updater:open-releases", async () => {
      await shell.openExternal(RELEASES_URL);
    });

    ipcMain.handle("updater:open-website", async () => {
      await shell.openExternal(WEBSITE_URL);
    });
  }

  /** 转发事件到渲染进程 */
  private sendToRenderer(channel: string, data: any): void {
    const win = this.getMainWindow();
    if (win && !win.isDestroyed()) {
      win.webContents.send(channel, data);
    }
  }

  /** 把 releaseNotes 标准化为字符串（electron-updater 可能传数组） */
  private normalizeReleaseNotes(notes: any): string | null {
    if (!notes) return null;
    if (typeof notes === "string") return notes;
    if (Array.isArray(notes)) {
      return notes.map((n: any) => (typeof n === "string" ? n : n.note || "")).join("\n");
    }
    return String(notes);
  }

  /** 语义版本对比：a < b 返回 -1，相等返回 0，a > b 返回 1 */
  private compareVersions(a: string, b: string): number {
    const pa = a.split(".").map((x) => parseInt(x, 10) || 0);
    const pb = b.split(".").map((x) => parseInt(x, 10) || 0);
    for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
      const na = pa[i] || 0;
      const nb = pb[i] || 0;
      if (na < nb) return -1;
      if (na > nb) return 1;
    }
    return 0;
  }
}
