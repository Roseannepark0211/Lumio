/**
 * 系统托盘管理 — Liquid Glass 风格自定义弹窗。
 *
 * 设计稿：design_preview/tray_menu.html
 *
 * 架构：
 *   - Tray 图标 + 动态 tooltip（显示下载状态）
 *   - 左键点击托盘 → 切换主窗口显示/隐藏（Windows 行为）
 *   - 右键点击托盘 → 弹出 Liquid Glass 自定义菜单（frameless BrowserWindow）
 *   - 主窗口关闭 → 弹出关闭确认弹窗（最小化到托盘 / 退出 / 取消）
 *
 * 菜单弹窗加载 public/tray-menu.html（独立 HTML，不依赖 React 构建）
 * 关闭弹窗加载 public/close-dialog.html
 *
 * IPC 桥接（preload.ts 暴露 window.lumio.tray.*）：
 *   - showWindow()      — 显示并聚焦主窗口
 *   - openDir()         — 打开下载目录
 *   - navigate(page)    — 导航到指定页面 + 显示主窗口
 *   - toggleTheme()     — 切换深/浅主题
 *   - pauseAll()        — 暂停所有下载
 *   - quit()             — 退出应用
 *   - close()           — 关闭托盘菜单弹窗
 *   - cancelClose()     — 取消关闭确认
 *   - minimizeToTray() — 最小化到托盘
 *   - quitApp()         — 确认退出
 */

import {
  Tray,
  BrowserWindow,
  shell,
  screen,
  ipcMain,
  nativeImage,
} from "electron";
import path from "node:path";
import http from "node:http";

export interface TrayManagerDeps {
  getMainWindow: () => BrowserWindow | null;
  fastapiBase: string;
  fastapiToken: string;
  /** 用户点击"退出"时调用（负责 stopFastApi + app.quit） */
  onQuit: () => void;
  /** 用户选择"最小化到托盘"时调用 */
  onMinimizeToTray: () => void;
}

const MENU_WIDTH = 280;
const MENU_MAX_HEIGHT = 480;
const CLOSE_DIALOG_WIDTH = 360;
const CLOSE_DIALOG_HEIGHT = 200;

export class TrayManager {
  private tray: Tray | null = null;
  private menuWin: BrowserWindow | null = null;
  private closeWin: BrowserWindow | null = null;
  private deps: TrayManagerDeps;
  private tooltipTimer: NodeJS.Timeout | null = null;

  constructor(deps: TrayManagerDeps) {
    this.deps = deps;
  }

  /** 初始化托盘（必须在 app.whenReady() 之后调用） */
  init(): void {
    const iconPath = path.join(__dirname, "..", "build", "icon.png");
    let icon: Electron.NativeImage;
    try {
      icon = nativeImage.createFromPath(iconPath);
      if (process.platform === "win32") {
        icon = icon.resize({ width: 16, height: 16 });
      }
    } catch {
      icon = nativeImage.createEmpty();
    }

    this.tray = new Tray(icon);
    this.tray.setToolTip("Lumio");

    // Windows: 左键点击切换主窗口，右键弹出自定义菜单
    // macOS: 左键点击弹出菜单（系统约定）
    this.tray.on("click", () => {
      if (process.platform === "darwin") {
        this.toggleMenu();
      } else {
        this.toggleMainWindow();
      }
    });

    this.tray.on("right-click", () => {
      this.toggleMenu();
    });

    // 双击托盘图标 → 显示主窗口（Windows 约定）
    this.tray.on("double-click", () => {
      this.showMainWindow();
    });

    this.setupIpc();
    this.startTooltipRefresh();
  }

  /** 切换主窗口显示/隐藏 */
  private toggleMainWindow(): void {
    const win = this.deps.getMainWindow();
    if (!win) return;
    if (win.isVisible() && win.isFocused()) {
      win.hide();
    } else {
      this.showMainWindow();
    }
  }

  /** 显示并聚焦主窗口 */
  showMainWindow(): void {
    const win = this.deps.getMainWindow();
    if (!win) return;
    if (!win.isVisible()) win.show();
    if (win.isMinimized()) win.restore();
    win.focus();
  }

  /** 切换托盘菜单弹窗 */
  private toggleMenu(): void {
    if (this.menuWin && this.menuWin.isVisible()) {
      this.hideMenu();
    } else {
      this.showMenu();
    }
  }

  /** 显示托盘菜单弹窗 */
  private showMenu(): void {
    if (!this.menuWin) {
      this.menuWin = new BrowserWindow({
        width: MENU_WIDTH,
        height: MENU_MAX_HEIGHT,
        show: false,
        frame: false,
        resizable: false,
        maximizable: false,
        minimizable: false,
        fullscreenable: false,
        skipTaskbar: true,
        transparent: true,
        alwaysOnTop: true,
        focusable: true,
        webPreferences: {
          preload: path.join(__dirname, "preload.js"),
          contextIsolation: true,
          nodeIntegration: false,
        },
      });

      // 点击外部关闭
      this.menuWin.on("blur", () => {
        // 延迟关闭：避免点击菜单项时先 blur 导致点击失效
        setTimeout(() => {
          if (this.menuWin && !this.menuWin.isDestroyed()) {
            this.menuWin.hide();
          }
        }, 120);
      });

      // Esc 关闭
      this.menuWin.webContents.on("before-input-event", (_e, input) => {
        if (input.key === "Escape") this.hideMenu();
      });

      this.loadTrayHtml(this.menuWin, "tray-menu.html");
    }

    // 定位到托盘图标上方
    this.positionMenu();
    this.menuWin.show();
    this.menuWin.focus();
  }

  /** 隐藏托盘菜单弹窗 */
  private hideMenu(): void {
    if (this.menuWin && !this.menuWin.isDestroyed() && this.menuWin.isVisible()) {
      this.menuWin.hide();
    }
  }

  /** 定位菜单弹窗到托盘图标上方 */
  private positionMenu(): void {
    if (!this.menuWin || !this.tray) return;

    const trayBounds = this.tray.getBounds();
    const winBounds = this.menuWin.getBounds();
    const display = screen.getDisplayNearestPoint({
      x: trayBounds.x,
      y: trayBounds.y,
    });
    const { workArea } = display;

    // X: 居中对齐托盘图标，但不超出屏幕
    let x = trayBounds.x + trayBounds.width / 2 - winBounds.width / 2;
    x = Math.max(workArea.x + 8, Math.min(x, workArea.x + workArea.width - winBounds.width - 8));

    // Y: 托盘图标上方（Windows 任务栏在底部）
    let y = trayBounds.y - winBounds.height - 4;
    // 如果上方空间不够（任务栏在顶部），放下方
    if (y < workArea.y + 8) {
      y = trayBounds.y + trayBounds.height + 4;
    }
    // 不超出屏幕底部
    y = Math.min(y, workArea.y + workArea.height - winBounds.height - 8);

    this.menuWin.setPosition(Math.round(x), Math.round(y));
  }

  /** 显示关闭确认弹窗 */
  showCloseDialog(): void {
    if (this.closeWin && !this.closeWin.isDestroyed()) {
      this.closeWin.show();
      this.closeWin.focus();
      return;
    }

    this.closeWin = new BrowserWindow({
      width: CLOSE_DIALOG_WIDTH + 48,
      height: CLOSE_DIALOG_HEIGHT + 48,
      show: false,
      frame: false,
      resizable: false,
      maximizable: false,
      minimizable: false,
      fullscreenable: false,
      skipTaskbar: true,
      transparent: true,
      alwaysOnTop: true,
      center: true,
      webPreferences: {
        preload: path.join(__dirname, "preload.js"),
        contextIsolation: true,
        nodeIntegration: false,
      },
    });

    this.closeWin.on("blur", () => {
      // 点击外部 = 取消
      this.hideCloseDialog();
    });

    this.closeWin.webContents.on("before-input-event", (_e, input) => {
      if (input.key === "Escape") this.hideCloseDialog();
    });

    this.loadTrayHtml(this.closeWin, "close-dialog.html");
    this.closeWin.show();
    this.closeWin.focus();
  }

  /** 隐藏关闭确认弹窗 */
  private hideCloseDialog(): void {
    if (this.closeWin && !this.closeWin.isDestroyed()) {
      this.closeWin.hide();
    }
  }

  /** 加载 popup HTML（dev 用 Vite server，打包用本地文件） */
  private loadTrayHtml(win: BrowserWindow, filename: string): void {
    if (process.env.VITE_DEV_SERVER_URL) {
      // dev: Vite dev server 提供 public/ 静态文件
      win.loadURL(`${process.env.VITE_DEV_SERVER_URL}/${filename}`);
    } else {
      // 打包: dist/ 下
      win.loadFile(path.join(__dirname, "..", "dist", filename));
    }
  }

  /** 设置 IPC 处理器 */
  private setupIpc(): void {
    // 托盘菜单动作（从 tray-menu.html 的 window.lumio.tray.* 调用）
    ipcMain.on("tray:action", (_evt, action: string, arg?: string) => {
      this.handleTrayAction(action, arg);
    });

    // 关闭对话框动作
    ipcMain.on("tray:close-dialog", (_evt, action: string) => {
      this.handleCloseDialogAction(action);
    });
  }

  private handleTrayAction(action: string, arg?: string): void {
    switch (action) {
      case "showWindow":
        this.showMainWindow();
        break;
      case "openDir":
        this.openDownloadDir();
        break;
      case "navigate":
        if (arg) this.navigate(arg);
        break;
      case "toggleTheme":
        this.toggleTheme();
        break;
      case "pauseAll":
        this.pauseAllDownloads();
        break;
      case "quit":
        this.deps.onQuit();
        break;
      case "close":
        this.hideMenu();
        break;
    }
  }

  private handleCloseDialogAction(action: string): void {
    this.hideCloseDialog();
    switch (action) {
      case "minimize":
        this.deps.onMinimizeToTray();
        break;
      case "quit":
        this.deps.onQuit();
        break;
      // cancel: 仅关闭弹窗
    }
  }

  /** 打开下载目录 */
  private openDownloadDir(): void {
    // 从 FastAPI 读 config 获取 download_dir
    this.apiGet("/api/config")
      .then((cfg) => {
        const c = cfg as Record<string, unknown>;
        const dir = c.download_dir || c.downloadDir;
        if (dir && typeof dir === "string") {
          shell.openPath(dir);
        } else {
          // 回退：调 /api/open-folder 打开默认下载目录
          this.apiPost("/api/open-folder", { path: "", source: "tray" });
        }
      })
      .catch(() => {});
  }

  /** 导航到页面 + 显示主窗口 */
  private navigate(page: string): void {
    this.showMainWindow();
    const win = this.deps.getMainWindow();
    if (win) {
      win.webContents.send("navigate", page);
    }
  }

  /** 切换主题 */
  private toggleTheme(): void {
    this.apiPost("/api/theme/toggle", undefined).catch(() => {});
  }

  /** 暂停所有下载 */
  private pauseAllDownloads(): void {
    this.apiPost("/api/queue/pause-all", undefined).catch(() => {});
  }

  /** FastAPI GET 请求 */
  private apiGet(path: string): Promise<unknown> {
    return new Promise((resolve, reject) => {
      const req = http.get(
        `${this.deps.fastapiBase}${path}`,
        {
          headers: this.deps.fastapiToken
            ? { "X-Lumio-Token": this.deps.fastapiToken }
            : {},
        },
        (res) => {
          let data = "";
          res.on("data", (chunk) => (data += chunk));
          res.on("end", () => {
            try {
              resolve(JSON.parse(data));
            } catch (e) {
              reject(e);
            }
          });
        }
      );
      req.on("error", reject);
      req.setTimeout(3000, () => {
        req.destroy();
        reject(new Error("timeout"));
      });
    });
  }

  /** FastAPI POST 请求 */
  private apiPost(path: string, body: unknown): Promise<unknown> {
    return new Promise((resolve, reject) => {
      const url = new URL(this.deps.fastapiBase + path);
      const bodyStr = body ? JSON.stringify(body) : "";
      const req = http.request(
        {
          hostname: url.hostname,
          port: url.port,
          path: url.pathname,
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(this.deps.fastapiToken
              ? { "X-Lumio-Token": this.deps.fastapiToken }
              : {}),
            ...(bodyStr ? { "Content-Length": Buffer.byteLength(bodyStr) } : {}),
          },
        },
        (res) => {
          let data = "";
          res.on("data", (chunk) => (data += chunk));
          res.on("end", () => {
            try {
              resolve(JSON.parse(data));
            } catch {
              resolve({});
            }
          });
        }
      );
      req.on("error", reject);
      req.setTimeout(3000, () => {
        req.destroy();
        reject(new Error("timeout"));
      });
      if (bodyStr) req.write(bodyStr);
      req.end();
    });
  }

  /** 定时刷新 tooltip（显示下载状态） */
  private startTooltipRefresh(): void {
    const refresh = () => {
      this.apiGet("/api/queue")
        .then((tasks: unknown) => {
          if (!Array.isArray(tasks)) return;
          const active = tasks.filter((t: any) => {
            const s = (t.status || "").toLowerCase();
            return s === "下载中" || s === "downloading";
          });
          if (active.length > 0) {
            this.tray?.setToolTip(`Lumio — 下载中 ${active.length}`);
          } else {
            this.tray?.setToolTip("Lumio");
          }
        })
        .catch(() => {});
    };

    refresh();
    this.tooltipTimer = setInterval(refresh, 5000);
  }

  /** 销毁 */
  destroy(): void {
    if (this.tooltipTimer) {
      clearInterval(this.tooltipTimer);
      this.tooltipTimer = null;
    }
    if (this.menuWin && !this.menuWin.isDestroyed()) {
      this.menuWin.destroy();
      this.menuWin = null;
    }
    if (this.closeWin && !this.closeWin.isDestroyed()) {
      this.closeWin.destroy();
      this.closeWin = null;
    }
    if (this.tray) {
      this.tray.destroy();
      this.tray = null;
    }
  }
}
