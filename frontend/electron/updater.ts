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
 */

import { app, BrowserWindow, ipcMain, shell, dialog } from "electron";
import { autoUpdater } from "electron-updater";
import type { ChildProcess } from "node:child_process";

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
  error: string | null;
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
      this.sendToRenderer("update:error", { message: err.message });
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
      return {
        hasUpdate: info.version !== app.getVersion(),
        info: {
          version: info.version,
          releaseNotes: this.normalizeReleaseNotes(info.releaseNotes),
          releaseName: info.releaseName || null,
          releaseDate: info.releaseDate || null,
        },
        error: null,
      };
    } catch (e: any) {
      return { hasUpdate: false, info: null, error: e.message };
    }
  }

  /** 开始下载更新（IPC 调用，用户点"立即下载"后触发） */
  async downloadUpdate(): Promise<{ ok: boolean; error: string | null }> {
    if (!app.isPackaged) {
      return { ok: false, error: "dev mode" };
    }
    if (process.platform === "darwin") {
      // macOS 手动模式：直接打开 Release 页面
      await shell.openExternal("https://github.com/Roseannepark0211/Lumio/releases/latest");
      return { ok: true, error: null };
    }
    try {
      await autoUpdater.downloadUpdate();
      return { ok: true, error: null };
    } catch (e: any) {
      return { ok: false, error: e.message };
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
      return { hasUpdate: false, info: null, error: e.message };
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
