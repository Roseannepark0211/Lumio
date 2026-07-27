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
  /** 首次打开菜单时等 HTML 加载 + render 完成后再 show，
   *  避免 400px 高的窗口立即显示而内容只有 300px → 底部 100px 空白 */
  private menuPendingShow: boolean = false;
  /** 首次打开时右键位置的 bounds，等 reportHeight 触发 show 时用 */
  private pendingBounds?: Electron.Rectangle;
  /** 菜单锚点（首次打开时记录，后续 reportHeight 触发重新定位时复用，
   *  避免鼠标移动后 cursor 实时位置变化导致菜单跳动）。
   *  - anchor.x: 首次点击的水平位置（菜单水平居中对齐此点）
   *  - anchor.y: 任务栏顶部 Y（菜单底部对齐此点，贴任务栏弹出）
   *  - anchor.taskbarSide: 任务栏位置（bottom/top/left/right） */
  private menuAnchor: { x: number; y: number; taskbarSide: "bottom" | "top" | "left" | "right" } | null = null;

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
   *  水平定位以鼠标 x 为中心，菜单跟随鼠标位置而非托盘图标中心。
   *
   *  关键时序设计：
   *  - 首次打开：先创建窗口（不显示）→ 等 HTML 加载完 + render 完成 →
   *    前端调 reportHeight IPC 报告实际内容高度 → 主进程 setSize 调整窗口高度 →
   *    positionMenu 用实际窗口高度贴合任务栏 → show 显示
   *  - 这样用户看到的菜单窗口高度 = 内容高度，底部直接贴合任务栏，无空白间距
   *  - 二次打开（窗口已加载过）：直接 positionMenu + show
   */
  private showMenu(bounds?: Electron.Rectangle): void {
    // 每次打开（含二次打开）都重新计算锚点：
    // - 水平锚点 = 鼠标当前 x（菜单水平居中对齐此点）
    // - 垂直锚点 = 任务栏顶部 Y（菜单底部对齐此点，贴任务栏弹出）
    //
    // 关键：垂直锚点用 workArea 底部（任务栏顶部）而非 cursor.y。
    // 用户从隐藏图标展开面板点击时 cursor.y 在面板里（比任务栏顶部高 ~40-80px），
    // 如果菜单底部贴 cursor.y 会让菜单底部悬空在任务栏上方，菜单和任务栏之间出现空白。
    // 用 workArea 底部作锚点保证菜单始终贴任务栏顶部弹出，符合 Windows 系统原生菜单行为。
    this.menuAnchor = this.computeMenuAnchor();

    if (!this.menuWin) {
      this.menuWin = new BrowserWindow({
        width: MENU_WIDTH,
        height: MENU_MAX_HEIGHT,
        show: false,           // 关键：不在创建时显示，等 reportHeight 后再显示
        frame: false,
        resizable: false,
        maximizable: false,
        minimizable: false,
        fullscreenable: false,
        skipTaskbar: true,
        transparent: true,
        // 显式声明透明背景色：默认 #00000000（ARGB）。
        // 不写 backgroundColor 时，某些 Windows 版本会用系统主题色填充 transparent 窗口，
        // 看起来像菜单周围有一圈暗色"阴影背景"。
        backgroundColor: "#00000000",
        alwaysOnTop: true,
        focusable: true,
        webPreferences: {
          preload: path.join(__dirname, "preload.js"),
          contextIsolation: true,
          nodeIntegration: false,
          // 关键：托盘菜单 hide() 后默认会被节流到 10fps，
          // setTimeout 被 throttled 到 1000ms+，WS onmessage 虽触发但
          // refreshQueue 里的防抖 setTimeout 会被延迟执行，
          // 导致下载状态变化监测不到。关闭后台节流保持实时性。
          backgroundThrottling: false,
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

      // 标记：首次打开需要等 HTML 加载完 + render 完成后才显示
      // reportHeight IPC 触发后会调 setVisibilityReady(true) → positionMenu + show
      this.menuPendingShow = true;
      this.pendingBounds = bounds;
      this.loadTrayHtml(this.menuWin, "tray-menu.html");

      // 兜底：如果 HTML 加载失败或 reportHeight 没触发，
      // 2 秒后强制显示（避免右键点了完全没反应）
      setTimeout(() => {
        if (this.menuWin && !this.menuWin.isDestroyed() &&
            this.menuPendingShow && !this.menuWin.isVisible()) {
          this.menuPendingShow = false;
          this.positionMenu(bounds);
          this.menuWin.show();
          this.menuWin.focus();
        }
      }, 2000);
      return;
    }

    // 窗口已存在：定位 + 显示
    this.positionMenu(bounds);
    this.menuWin.show();
    this.menuWin.focus();
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
   *  重要：使用首次 showMenu 时记录的锚点，不实时取 cursor。
   *  原因：reportHeight 触发 setSize 后会再次调 positionMenu 重新对齐，
   *  如果用实时 cursor，鼠标可能已移动到别处，菜单会"跳"到新位置。
   *
   *  winBounds.height 是当前窗口实际高度（首次打开时刚 setSize 过，
   *  二次打开时是上次 setSize 后的高度）。
   *  - 底部任务栏：y = anchorY - winBounds.height（菜单底部对齐任务栏顶部）
   *  - 顶部任务栏：y = anchorY（菜单顶部对齐任务栏底部）
   *  - 左/右侧任务栏：水平贴 workArea 边，垂直对齐 cursor.y（anchorY = cursor.y）
   */
  private positionMenu(_bounds?: Electron.Rectangle): void {
    if (!this.menuWin || !this.tray) return;
    if (!this.menuAnchor) return;

    const winBounds = this.menuWin.getBounds();
    const display = screen.getDisplayNearestPoint({ x: this.menuAnchor.x, y: this.menuAnchor.y });
    const { workArea } = display;

    const { x: anchorX, y: anchorY, taskbarSide } = this.menuAnchor;

    let x: number;
    let y: number;

    if (taskbarSide === "bottom") {
      // 底部任务栏：菜单底部对齐任务栏顶部，水平居中对齐点击位置
      x = anchorX - winBounds.width / 2;
      y = anchorY - winBounds.height;
    } else if (taskbarSide === "top") {
      // 顶部任务栏：菜单顶部对齐任务栏底部，水平居中对齐点击位置
      x = anchorX - winBounds.width / 2;
      y = anchorY;
    } else if (taskbarSide === "left") {
      // 左侧任务栏：水平左边界贴合 workArea 左，垂直居中对齐点击 y
      x = workArea.x;
      y = anchorY - winBounds.height / 2;
    } else {
      // 右侧任务栏：水平右边界贴合 workArea 右，垂直居中对齐点击 y
      x = workArea.x + workArea.width - winBounds.width;
      y = anchorY - winBounds.height / 2;
    }

    // 水平方向不超出 workArea 边界（与屏幕边缘留 8px 余量）
    x = Math.max(workArea.x + 8, Math.min(x, workArea.x + workArea.width - winBounds.width - 8));

    // 垂直方向：菜单必须完整可见，不能超出 workArea 顶部/底部
    if (y < workArea.y) {
      y = workArea.y;
    }
    if (y + winBounds.height > workArea.y + workArea.height) {
      y = workArea.y + workArea.height - winBounds.height;
    }

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

    // 前端 render() 后报告菜单实际内容高度
    // 关键时序：首次打开时窗口还未显示（showMenu 设了 menuPendingShow=true），
    // 收到 reportHeight 后才 setSize 调整高度 + positionMenu + show
    // 这样用户看到的菜单窗口高度 = 内容实际高度，底部直接贴合任务栏，无空白间距
    ipcMain.on("tray:report-height", (_evt, menuHeight: number) => {
      if (!this.menuWin || this.menuWin.isDestroyed()) return;
      if (!Number.isFinite(menuHeight) || menuHeight <= 0) return;
      const winHeight = Math.max(120, Math.min(MENU_MAX_HEIGHT, Math.round(menuHeight)));
      this.menuWin.setSize(MENU_WIDTH, winHeight);
      // 用实际窗口高度重新定位（垂直贴合任务栏）
      this.positionMenu(this.pendingBounds);
      // 首次打开：现在窗口高度对了，可以显示
      if (this.menuPendingShow) {
        this.menuPendingShow = false;
        this.menuWin.show();
        this.menuWin.focus();
      }
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
