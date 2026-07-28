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
  app,
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

const MENU_WIDTH = 240;        // 280 → 240 同比例缩小约 15%
// 移除任务卡片后菜单内容减少，max-height 同比例缩到 400
const MENU_MAX_HEIGHT = 400;
const CLOSE_DIALOG_WIDTH = 360;
const CLOSE_DIALOG_HEIGHT = 200;

export class TrayManager {
  private tray: Tray | null = null;
  private menuWin: BrowserWindow | null = null;
  private closeWin: BrowserWindow | null = null;
  private deps: TrayManagerDeps;
  private tooltipTimer: NodeJS.Timeout | null = null;
  /** showMenu 调用后 200ms 内忽略 blur 事件，避免 show/focus 触发的瞬时 blur 立即关闭菜单 */
  private suppressBlurUntil: number = 0;
  /** 菜单锚点（每次 showMenu 时记录，positionMenu 复用避免菜单跟随鼠标跳动）。
   *  - anchor.x: 点击的水平位置（菜单水平居中对齐此点）
   *  - anchor.y: 任务栏顶部 Y（菜单底部对齐此点，贴任务栏弹出）
   *  - anchor.taskbarSide: 任务栏位置（bottom/top/left/right） */
  private menuAnchor: { x: number; y: number; taskbarSide: "bottom" | "top" | "left" | "right" } | null = null;

  constructor(deps: TrayManagerDeps) {
    this.deps = deps;
  }

  /** 初始化托盘（必须在 app.whenReady() 之后调用） */
  init(): void {
    // 打包模式：resources/build/icon.png（extraResources 复制出来的）
    // dev 模式：frontend/build/icon.png（源码目录）
    // 不能用 path.join(__dirname, "..", "build", "icon.png")：
    //   打包后 __dirname 在 app.asar/dist-electron/，上一级是 app.asar/，
    //   app.asar/build/icon.png 不存在（build/ 不在 asar 内）。
    const iconPath = app.isPackaged
      ? path.join(process.resourcesPath, "build", "icon.png")
      : path.join(__dirname, "..", "build", "icon.png");
    let icon: Electron.NativeImage;
    try {
      icon = nativeImage.createFromPath(iconPath);
      if (process.platform === "win32") {
        icon = icon.resize({ width: 16, height: 16 });
      }
      // 空图像兜底：如果文件不存在或加载失败，createFromPath 返回空图像，
      // 此时用 nativeImage.createEmpty() 至少不会崩溃（托盘透明但不影响功能）
      if (icon.isEmpty()) {
        console.warn(`[tray] icon not found or empty: ${iconPath}`);
      }
    } catch (e) {
      console.error(`[tray] failed to load icon: ${iconPath}`, e);
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

    this.tray.on("right-click", (_e, bounds) => {
      // 右键不再 toggle 开关，而是一直打开：
      // 已打开时重新定位到最新鼠标位置，未打开时打开。
      // 这样用户连点右键不会闪关闪开，符合 Win10 系统托盘行为。
      this.showMenu(bounds);
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

  /** 显示托盘菜单弹窗。
   *  bounds 参数：右键点击的位置（Electron right-click 事件第二参数）。
   *  不传则用托盘图标位置（macOS 左键点击场景）。
   *
   *  关键时序设计（修复闪烁问题）：
   *  - 首次打开：创建窗口 → 等 ready-to-show 信号（首次绘制完成）→ show
   *    避免 transparent 窗口先显示空白再填充内容的"内容闪现"
   *    ready-to-show 比 HTML 完全加载快（50-100ms），用户感觉"立即响应"
   *  - 窗口已可见：只重新定位，不重复 show（避免 Windows 窗口管理器激活动画闪烁）
   *  - 窗口已存在但隐藏：show() 一次即可，不调 focus()（show 已激活窗口，focus 是冗余二次激活）
   *  - reportHeight 触发后用 setBounds 一步到位调整尺寸+位置，避免 setSize+setPosition 两次重绘
   */
  private showMenu(bounds?: Electron.Rectangle): void {
    this.menuAnchor = this.computeMenuAnchor();

    // 窗口已可见：只重新定位到最新鼠标位置，不重复 show（避免闪烁）
    if (this.menuWin && this.menuWin.isVisible()) {
      this.positionMenu(bounds);
      return;
    }

    if (!this.menuWin) {
      // 首次打开：创建窗口，等 ready-to-show 信号才 show
      this.menuWin = new BrowserWindow({
        width: MENU_WIDTH,
        height: 280,
        show: false,              // 关键：等 ready-to-show 信号
        frame: false,
        resizable: false,
        maximizable: false,
        minimizable: false,
        fullscreenable: false,
        skipTaskbar: true,
        transparent: true,
        backgroundColor: "#00000000",
        alwaysOnTop: true,
        focusable: true,
        webPreferences: {
          preload: path.join(__dirname, "preload.js"),
          contextIsolation: true,
          nodeIntegration: false,
          backgroundThrottling: false,
        },
      });

      // ready-to-show = 首次绘制完成，比 HTML 完全加载快
      // 此时 show 不会出现"先空白再内容"的闪烁
      this.menuWin.once("ready-to-show", () => {
        if (!this.menuWin || this.menuWin.isDestroyed()) return;
        this.positionMenu(bounds);
        this.suppressBlurUntil = Date.now() + 200;
        this.menuWin.show();
        // 不调 focus() — show() 已激活窗口，focus 是冗余的二次激活事件，
        // 会触发 Windows 窗口管理器的额外动画导致闪烁
      });

      // blur 关闭：延迟 200ms + suppressBlurUntil 防抖
      this.menuWin.on("blur", () => {
        setTimeout(() => {
          if (this.menuWin && !this.menuWin.isDestroyed() &&
              Date.now() > this.suppressBlurUntil) {
            this.menuWin.hide();
          }
        }, 200);
      });

      // Esc 关闭
      this.menuWin.webContents.on("before-input-event", (_e, input) => {
        if (input.key === "Escape") this.hideMenu();
      });

      this.loadTrayHtml(this.menuWin, "tray-menu.html");

      // 兜底：如果 ready-to-show 1 秒没触发（异常情况），强制显示
      setTimeout(() => {
        if (this.menuWin && !this.menuWin.isDestroyed() && !this.menuWin.isVisible()) {
          this.positionMenu(bounds);
          this.suppressBlurUntil = Date.now() + 200;
          this.menuWin.show();
        }
      }, 1000);
      return;
    }

    // 窗口已存在但隐藏：定位 + show（不调 focus，避免闪烁）
    this.positionMenu(bounds);
    this.suppressBlurUntil = Date.now() + 200;
    this.menuWin.show();
  }

  /** 隐藏托盘菜单弹窗 */
  private hideMenu(): void {
    if (this.menuWin && !this.menuWin.isDestroyed() && this.menuWin.isVisible()) {
      this.menuWin.hide();
    }
  }

  /** 计算菜单锚点（首次打开时调用，记录水平点击位置 + 任务栏顶部 Y）。
   *
   *  关键设计：
   *  - 水平锚点 = 鼠标当前 x（菜单水平居中对齐此点，符合"在点击位置上方弹出"直觉）
   *  - 垂直锚点 = workArea 底部 Y（任务栏顶部），菜单底部对齐此点
   *
   *  为什么垂直锚点不用 cursor.y：
   *  - 用户从隐藏图标展开面板点击 Lumio 时，cursor.y 在展开面板里
   *    （比任务栏顶部高约 40-80px，展开面板浮在任务栏上方）
   *  - 如果菜单底部对齐 cursor.y，菜单底部会悬空在任务栏上方
   *  - 菜单底部和任务栏之间出现 40-80px 空白，看起来像"菜单被抬高"
   *  - Windows 系统原生菜单行为是贴任务栏顶部弹出，无论点击位置在哪
   *
   *  为什么不用 tray.getBounds()：
   *  - Windows 高 DPI（125%/150%缩放）+ 多屏 + 隐藏图标展开面板场景下
   *    tray.getBounds() 返回错误坐标是 Electron 已知 bug
   *
   *  适配任务栏位置（底部/顶部/左侧/右侧）：
   *  - 底部任务栏：菜单底部对齐 workArea 底部（任务栏顶部），向上展开
   *  - 顶部任务栏：菜单顶部对齐 workArea 顶部（任务栏底部），向下展开
   *  - 左/右侧任务栏：水平贴合 workArea 侧边，垂直对齐鼠标 y
   *
   *  所有坐标均使用 DIP（设备无关像素），DPI 无关。
   */
  private computeMenuAnchor(): { x: number; y: number; taskbarSide: "bottom" | "top" | "left" | "right" } | null {
    const cursor = screen.getCursorScreenPoint();
    const display = screen.getDisplayNearestPoint(cursor);
    const { workArea, bounds: screenBounds } = display;

    // 任务栏位置判定（workArea 比 screenBounds 小的那一侧）
    const taskbarBottom = workArea.y + workArea.height < screenBounds.height - 1;
    const taskbarTop = workArea.y > 1;
    const taskbarLeft = workArea.x > 1;
    const taskbarRight = workArea.x + workArea.width < screenBounds.width - 1;

    let taskbarSide: "bottom" | "top" | "left" | "right";
    let anchorY: number;

    if (taskbarBottom) {
      // 底部任务栏：菜单底部对齐 workArea 底部（任务栏顶部）
      taskbarSide = "bottom";
      anchorY = workArea.y + workArea.height;
    } else if (taskbarTop) {
      // 顶部任务栏：菜单顶部对齐 workArea 顶部（任务栏底部）
      taskbarSide = "top";
      anchorY = workArea.y;
    } else if (taskbarLeft) {
      // 左侧任务栏：垂直用 cursor.y（侧边任务栏场景菜单水平贴边，垂直跟随鼠标）
      taskbarSide = "left";
      anchorY = cursor.y;
    } else if (taskbarRight) {
      // 右侧任务栏：垂直用 cursor.y
      taskbarSide = "right";
      anchorY = cursor.y;
    } else {
      // 兜底：按底部任务栏处理
      taskbarSide = "bottom";
      anchorY = workArea.y + workArea.height;
    }

    return { x: cursor.x, y: anchorY, taskbarSide };
  }

  /** 定位菜单弹窗（基于已记录的锚点 this.menuAnchor）。
   *
   *  优化：用 setBounds 一步到位设置位置 + 尺寸，避免 setSize + setPosition
   *  两次重绘导致的视觉跳动。
   *
   *  opts.height 可指定新高度（reportHeight 触发时用），不指定则用当前高度。
   */
  private positionMenu(_bounds?: Electron.Rectangle, opts?: { height?: number }): void {
    if (!this.menuWin || !this.tray) return;
    if (!this.menuAnchor) return;

    const curBounds = this.menuWin.getBounds();
    const width = MENU_WIDTH;
    const height = opts?.height ?? curBounds.height;
    const display = screen.getDisplayNearestPoint({ x: this.menuAnchor.x, y: this.menuAnchor.y });
    const { workArea } = display;

    const { x: anchorX, y: anchorY, taskbarSide } = this.menuAnchor;

    let x: number;
    let y: number;

    if (taskbarSide === "bottom") {
      x = anchorX - width / 2;
      y = anchorY - height;
    } else if (taskbarSide === "top") {
      x = anchorX - width / 2;
      y = anchorY;
    } else if (taskbarSide === "left") {
      x = workArea.x;
      y = anchorY - height / 2;
    } else {
      x = workArea.x + workArea.width - width;
      y = anchorY - height / 2;
    }

    x = Math.max(workArea.x + 8, Math.min(x, workArea.x + workArea.width - width - 8));

    if (y < workArea.y) y = workArea.y;
    if (y + height > workArea.y + workArea.height) {
      y = workArea.y + workArea.height - height;
    }

    // setBounds 一步到位：避免 setSize + setPosition 两次重绘
    this.menuWin.setBounds({
      x: Math.round(x),
      y: Math.round(y),
      width,
      height,
    });
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

    // 前端 render() 后报告菜单实际内容高度
    // 用 setBounds 一步到位调整位置 + 尺寸，避免 setSize + setPosition 两次重绘
    ipcMain.on("tray:report-height", (_evt, menuHeight: number) => {
      if (!this.menuWin || this.menuWin.isDestroyed()) return;
      if (!Number.isFinite(menuHeight) || menuHeight <= 0) return;
      const winHeight = Math.max(120, Math.min(MENU_MAX_HEIGHT, Math.round(menuHeight)));
      this.positionMenu(undefined, { height: winHeight });
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

  /** 定时刷新 tooltip（显示总状态：忙碌中/空闲，按 lang 切换文案） */
  private startTooltipRefresh(): void {
    const refresh = async () => {
      try {
        const [tasks, cfg] = await Promise.all([
          this.apiGet("/api/queue") as Promise<unknown[]>,
          this.apiGet("/api/config") as Promise<Record<string, unknown>>,
        ]);
        if (!Array.isArray(tasks)) return;
        const busy = tasks.some((t: any) => {
          const s = (t.status || "").toLowerCase();
          return s === "下载中" || s === "downloading";
        });
        const lang = cfg.lang === "en" ? "en" : "zh";
        const tip = busy
          ? lang === "en" ? "Lumio — Busy" : "Lumio — 忙碌中"
          : "Lumio";
        this.tray?.setToolTip(tip);
      } catch {
        // ignore
      }
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
