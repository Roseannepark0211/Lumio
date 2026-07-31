/**
 * Electron 主进程入口（v2）。
 *
 * 完整生命周期（用户指定）：
 *
 * 启动流程：
 *   1. 随机生成端口号（避免固定端口冲突）
 *   2. 生成临时 token（防止本机其他进程误调）
 *   3. child_process 拉起 FastAPI，传入 PORT + TOKEN
 *   4. 轮询 /api/health?token=xxx 直到就绪
 *   5. 就绪后加载前端页面
 *
 * 退出流程：
 *   1. BrowserWindow close → 给 FastAPI 发 /api/shutdown 信号
 *   2. 等待 3 秒优雅退出
 *   3. 强制 kill 残留进程（兜底）
 */

import { app, BrowserWindow, shell, protocol, dialog, ipcMain } from "electron";
import { spawn, ChildProcess, execSync } from "node:child_process";
import path from "node:path";
import fs from "node:fs";
import http from "node:http";
import crypto from "node:crypto";
// A1: TrayManager 运行时延迟到 whenReady 内动态 import，类型用 import type 编译时擦除
import type { TrayManager } from "./tray";
// UpdaterManager 类型用 import type 编译时擦除，运行时动态 import
import type { UpdaterManager } from "./updater";

// ============================================================
// 全局状态
// ============================================================

let fastapiProc: ChildProcess | null = null;
let mainWindow: BrowserWindow | null = null;
let splashWindow: BrowserWindow | null = null;
let trayManager: TrayManager | null = null;
let updaterManager: UpdaterManager | null = null;

// FastAPI 连接信息（每次启动随机生成，传给子进程 + 渲染进程）
const fastapiPort = pickUnusedPort();
const fastapiToken = crypto.randomBytes(24).toString("hex");
const FASTAPI_BASE = `http://127.0.0.1:${fastapiPort}`;

// 把 token 通过环境变量传给渲染进程（preload 阶段读出）
// ⚠️ 注意：sandbox 模式下 preload 的 process.env 是 polyfill，读不到主进程
// 动态设置的变量。改用 IPC sendSync 同步获取（见下方 ipcMain.on 注册）。
// 保留 env 设置作为兼容（dev 模式 + 非 sandbox 场景）
process.env.LUMIO_FASTAPI_BASE = FASTAPI_BASE;
process.env.LUMIO_FASTAPI_TOKEN = fastapiToken;

// IPC 同步返回 FastAPI 连接信息给 preload 脚本。
// preload 用 ipcRenderer.sendSync('get-fastapi-config') 同步获取，
// 确保 sandbox 模式下也能拿到正确的端口和 token。
// sendSync 是同步阻塞调用，在 preload 中安全使用（不会阻塞 UI）。
ipcMain.on("get-fastapi-config", (event: Electron.IpcMainEvent) => {
  event.returnValue = { base: FASTAPI_BASE, token: fastapiToken };
});

// D5: FastAPI spawn 前移到模块顶层——与 Electron 主进程初始化并行启动。
//
// 旧实现：在 app.whenReady() 内才 spawn FastAPI，串行等待 Electron 初始化完成才开始拉起 Python。
// 新实现：模块加载时就 spawn FastAPI 子进程（child_process.spawn 不依赖 app ready），
//         返回的 Promise 存到 fastApiReadyPromise，whenReady 内 await 这个 Promise。
//
// 收益：FastAPI 冷启动（Python import sqlalchemy/yt-dlp 等）与 Electron 主进程初始化
//       （Chromium 启动 + V8 初始化 + splash 窗口创建）完全并行，节省 1-3 秒。
//
// 注意：spawn 时不能读取 process.resourcesPath（虽然 Node 全局可读，但为稳妥起见
//       在 startFastApi 内部判断 app.isPackaged 决定 exePath，这部分不依赖 whenReady）。
let fastApiReadyPromise: Promise<void> | null = null;
function startFastApiEarly(): void {
  if (fastApiReadyPromise) return;
  fastApiReadyPromise = startFastApi();
}

// 在 app.whenReady() 之前重写 userData 目录（M3 修复：dev/packaged 分流）。
// 必须在 app ready 之前调用，否则 Electron 会用默认路径初始化各种缓存。
//
// - dev 模式：写到项目目录下 frontend/.electron-cache/user-data
//   好处：① 调试时可直接清空缓存 ② 避免 %APPDATA%/lumio-frontend 沙箱权限问题
//   ③ 多个 dev 实例切换时缓存隔离
//
// - packaged 模式：用 Electron 默认 userData 路径（不重写）
//   Windows: %APPDATA%/Lumio
//   macOS:   ~/Library/Application Support/Lumio
//   Linux:   ~/.config/Lumio
//   好处：① 符合各平台惯例（用户可找到日志/缓存） ② 系统级清理工具能识别
//   ③ 升级安装时配置保留 ④ 不会写到 app.asar 内（只读）
//
// 旧实现无脑写 <projectRoot>/frontend/.electron-cache/user-data，
// 打包后 projectRoot 解析成 app.asar 内部路径 → 写入失败 → Electron 用默认路径
// 但 setPath 已被调用 → 内部状态混乱（AGENTS.md "M3" 问题）
{
  if (!app.isPackaged) {
    const projectRoot = path.resolve(__dirname, "..", "..");
    const userDataDir = path.join(projectRoot, "frontend", ".electron-cache", "user-data");
    try {
      fs.mkdirSync(userDataDir, { recursive: true });
      app.setPath("userData", userDataDir);
    } catch {
      // 如果设置失败（比如目录不可写），让 Electron 用默认路径
    }
  }
  // packaged 模式不重写，让 Electron 用平台默认路径
}

// V8 js-flags 调优：桌面单用户场景，限制老生代堆上限避免内存膨胀，
// 提高 GC 频率换启动速度（社区推荐配置：单用户 Electron 应用 2GB 上限 + 100MB 间隔）
// 必须在 app ready 之前调用，否则 V8 已用默认参数初始化堆
app.commandLine.appendSwitch(
  "js-flags",
  "--max-old-space-size=2048 --gc-interval=100"
);

// A2: Chromium 启动开关裁剪——关闭 Lumio 不需要的子系统，加速主进程冷启动
// 必须在 app ready 之前调用，否则 Chromium 已用默认配置初始化
// - disable-extensions: 不加载 Chromium 扩展系统（Electron 不用扩展）
// - disable-plugins: 不加载 PepperFlash/PDF 插件子系统
// - disable-background-networking: 关闭 Chromium 后台网络轮询（safebrowsing/time-sync 等）
// - disable-default-apps: 不加载默认应用工厂
// - disable-hang-monitor: 关闭 Chromium 卡死检测线程
// - disable-prompt-on-repost: 关闭重新提交表单提示
// 注意：禁用 GPU 会大幅降低视频/缩略图渲染性能，所以保留 GPU 加速
app.commandLine.appendSwitch("disable-extensions");
app.commandLine.appendSwitch("disable-plugins");
app.commandLine.appendSwitch("disable-background-networking");
app.commandLine.appendSwitch("disable-default-apps");
app.commandLine.appendSwitch("disable-hang-monitor");
app.commandLine.appendSwitch("disable-prompt-on-repost");
// 禁用 PDF 子进程（PDF.js 不需要，Electron 直接 shell.openExternal 系统打开）
app.commandLine.appendSwitch("disable-features", "OutOfProcessPdf");

// 注册 lumio-file:// 自定义 protocol，映射本地文件路径
// 必须在 app.whenReady() 之前调用 registerSchemesAsPrivileged，
// 否则 Chromium 同源策略会拦截跨 protocol 的 fetch/video/image 请求
// 用途：
//   - X-Sou 视频预览：~/.lumio/cache/preview/<hash>.mp4 → <video src="lumio-file://...">
//   - Library 缩略图（未来）：~/.lumio/cache/thumbs/<id>.jpg → <img src="lumio-file://...">
//   - 素材预览（未来）：本地视频/图片文件
// 调用约定：lumio-file:///<absolute_path>（path 自动 URL-decode）
protocol.registerSchemesAsPrivileged([
  {
    scheme: "lumio-file",
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      stream: true,            // 关键：让 <video> 能 Range 请求流式播放
      bypassCSP: true,
      codeCache: true,
    },
  },
]);

// ============================================================
// 单例锁：禁止多开
// ============================================================
// 用户通过快捷方式或拖拽文件到图标上可能触发多次启动，每次都会 spawn 一个
// FastAPI 子进程并占用端口，导致多个后台进程同时运行。
// app.requestSingleInstanceLock() 在应用启动最早阶段获取系统级锁，
// 第二个实例启动时获取锁失败 → 直接 quit，并通知主实例激活窗口。
//
// got-second-instance 事件回调中：
//   1. 如果窗口最小化/关闭，恢复并显示
//   2. 如果有 splash 窗口，也一并恢复
//   3. focus 主窗口确保用户看到应用已运行
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  // 第二个实例：立即退出，不执行后续任何初始化（不 spawn FastAPI、不创建窗口）
  app.quit();
} else {
  app.on("second-instance", () => {
    // 主实例收到第二个实例启动通知：激活并聚焦主窗口
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      if (!mainWindow.isVisible()) mainWindow.show();
      mainWindow.focus();
    }
    // splash 窗口可能仍然存在（FastAPI 未就绪时）
    if (splashWindow) {
      if (splashWindow.isMinimized()) splashWindow.restore();
      if (!splashWindow.isVisible()) splashWindow.show();
      splashWindow.focus();
    }
  });
}

// D5: 立即 spawn FastAPI 子进程——与 Electron 主进程后续初始化（Chromium 启动 +
// V8 初始化 + whenReady 触发 + splash 窗口创建）完全并行，节省 1-3 秒。
// startFastApi 是函数声明（function declaration），会被提升到模块顶部，可在此调用。
// fastApiReadyPromise 由 startFastApiEarly 内部赋值，whenReady 内 await 这个 Promise。
startFastApiEarly();

// ============================================================
// 工具函数
// ============================================================

/** 文件扩展名 → MIME 映射（lumio-file:// handler 用）。
 *  net.fetch(file://) 返回的 Content-Type 不可靠（通常是 application/octet-stream），
 *  <video>/<audio> 标签会因 MIME 不匹配拒绝播放，这里手动推断。 */
const MIME_TYPES: Record<string, string> = {
  // 视频
  ".mp4": "video/mp4",
  ".m4v": "video/x-m4v",
  ".webm": "video/webm",
  ".mkv": "video/x-matroska",
  ".mov": "video/quicktime",
  ".avi": "video/x-msvideo",
  ".flv": "video/x-flv",
  ".ogv": "video/ogg",
  // 音频
  ".mp3": "audio/mpeg",
  ".m4a": "audio/mp4",
  ".aac": "audio/aac",
  ".wav": "audio/wav",
  ".ogg": "audio/ogg",
  ".flac": "audio/flac",
  ".opus": "audio/opus",
  // 图片
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".jfif": "image/jpeg",
  ".pjpeg": "image/jpeg",
  ".pjp": "image/jpeg",
  ".png": "image/png",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".bmp": "image/bmp",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".tiff": "image/tiff",
  ".tif": "image/tiff",
  ".avif": "image/avif",
  ".heic": "image/heic",
  ".heif": "image/heif",
};

/** 在 10000-60000 之间挑一个看起来没被占用的端口。 */
function pickUnusedPort(): number {
  // 简单策略：随机一个高位端口。即使偶尔冲突，FastAPI 启动失败也能感知。
  // 真正避免冲突需要 net.createServer().listen(0)，但那是异步的，启动时机太早。
  // 这里用 38910-38999 范围（保留端口段），冲突时 FastAPI 会立即报错。
  return 38910 + Math.floor(Math.random() * 90);
}

/**
 * 同步检查端口是否被占用（M2 修复：跨平台）。
 *
 * 旧实现 `netstat -ano | findstr` 仅 Windows。
 * 新实现按平台分流：
 *   - Windows: netstat -ano（保留原方案，原生可用）
 *   - Unix:    lsof -i :PORT -P -t（macOS/Linux 通用）
 *
 * 不用 node:net + listen 是因为 Server.listen() 异步，而 isPortInUse
 * 在 startFastApi Promise 构造器里被同步调用（早期预警用，FastAPI
 * 真正冲突时仍会立即报错，这里只是 UX 优化）。
 */
function isPortInUse(port: number): boolean {
  try {
    if (process.platform === "win32") {
      const out = execSync(`netstat -ano -p tcp | findstr ":${port} "`, {
        windowsHide: true,
        encoding: "utf8",
      });
      return out.trim().length > 0;
    } else {
      // Unix: lsof -i :PORT（macOS/Linux 都有 lsof）
      // -P 强制不解析端口名（更快），-t 只输出 pid（更简洁）
      const out = execSync(`lsof -i :${port} -P -t`, {
        encoding: "utf8",
        windowsHide: true,
      });
      return out.trim().length > 0;
    }
  } catch {
    // netstat/lsof 退出码 1 = 无匹配（端口空闲），正常情况
    return false;
  }
}

/**
 * 跨平台杀进程树（M1 修复）。
 *
 * - Windows: taskkill /pid X /f /t（/t 递归杀子进程）
 * - Unix:    递归 pgrep -P X 找子进程后 kill -9
 *            （Unix kill 默认不杀进程树，uvicorn worker 会被 orphan 留在系统里）
 *
 * 不引入 tree-kill npm 包（已是 concurrently 间接依赖，但避免变直接依赖）。
 */
function killProcessTree(pid: number): void {
  try {
    if (process.platform === "win32") {
      spawn("taskkill", ["/pid", String(pid), "/f", "/t"]);
    } else {
      // 递归收集所有子进程 pid（BFS）
      const collect = (rootPid: number): number[] => {
        const all = [rootPid];
        const queue = [rootPid];
        while (queue.length > 0) {
          const parent = queue.shift()!;
          try {
            const out = execSync(`pgrep -P ${parent}`, {
              encoding: "utf8",
              windowsHide: true,
            });
            for (const line of out.trim().split(/\r?\n/)) {
              const child = parseInt(line.trim(), 10);
              if (Number.isFinite(child) && !all.includes(child)) {
                all.push(child);
                queue.push(child);
              }
            }
          } catch {
            // pgrep 退出码 1 = 无子进程，正常情况
          }
        }
        return all;
      };
      // 先杀子进程，最后杀父进程（避免父进程在子进程死前收到 SIGCHLD 重生 worker）
      const all = collect(pid).reverse();
      for (const p of all) {
        try {
          process.kill(p, "SIGKILL");
        } catch {
          // ESRCH = 进程已退出，忽略
        }
      }
    }
  } catch {
    // ignore
  }
}

/** 获取应用图标路径（dev / packaged 分流）。
 *
 *  dev 模式：frontend/build/icon.png（源码目录）
 *  packaged 模式：resources/build/icon.png（extraResources 复制出来的）
 *
 *  不能用 path.join(__dirname, "..", "build", "icon.png")：
 *  打包后 __dirname 在 app.asar/dist-electron/，上一级是 app.asar/，
 *  app.asar/build/icon.png 不存在（build/ 不在 files 列表里，不在 asar 内）。
 *  必须用 process.resourcesPath（指向 app.asar 同级的 resources/ 目录），
 *  electron-builder.cjs 的 extraResources 把 build/icon.png 复制到这里。
 *
 *  nativeImage.createFromPath 无法读取 asar 内的文件，必须用 extraResources
 *  把图标复制到 asar 外部才能被 Tray / BrowserWindow 加载。
 */
function getIconPath(): string {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, "build", "icon.png");
  }
  return path.join(__dirname, "..", "build", "icon.png");
}

/** 同步读取 config.close_behavior（用于 close 事件分支判断）。
 *  - "ask"      → 每次询问（默认）
 *  - "minimize" → 总是最小化到托盘
 *  - "quit"     → 总是退出
 *
 *  直接用 fs 读 ~/.lumio/config.json 而非走 FastAPI：
 *  close 事件是同步的，不能 await；config.py 内存缓存与磁盘文件同步由 save_config 保证。
 *
 *  Node.js 不识别 Python 的 'utf-8-sig' 编码，手动剥离 BOM 头 (\uFEFF)。
 */
function readCloseBehavior(): string {
  try {
    const home = process.env.USERPROFILE || process.env.HOME;
    if (!home) return "ask";
    const cfgPath = path.join(home, ".lumio", "config.json");
    if (!fs.existsSync(cfgPath)) return "ask";
    let raw = fs.readFileSync(cfgPath, { encoding: "utf-8" });
    if (raw.charCodeAt(0) === 0xfeff) raw = raw.slice(1); // strip BOM
    const cfg = JSON.parse(raw);
    const v = cfg.close_behavior;
    return v === "minimize" || v === "quit" ? v : "ask";
  } catch {
    return "ask";
  }
}

/**
 * 同步读取 Python lumio.__version__（用于 splash 窗口显示真实版本号）。
 *
 * dev 模式：读 src/lumio/__init__.py 解析 __version__ = "x.y.z"
 * packaged 模式：读 resources/build/version.txt（build-backend.js 生成）
 * 都失败：返回 app.getVersion()（package.json 的 version，可能是 0.1.0）
 */
function readAppVersion(): string {
  // dev 模式：读 src/lumio/__init__.py
  if (!app.isPackaged) {
    try {
      const projectRoot = path.resolve(__dirname, "..", "..");
      const initPath = path.join(projectRoot, "src", "lumio", "__init__.py");
      if (fs.existsSync(initPath)) {
        const content = fs.readFileSync(initPath, { encoding: "utf-8" });
        const m = content.match(/__version__\s*=\s*["']([^"']+)["']/);
        if (m) return m[1];
      }
    } catch {
      // ignore
    }
  }
  // packaged 模式：读 resources/build/version.txt（build-backend.js 生成）
  if (app.isPackaged) {
    try {
      const versionPath = path.join(process.resourcesPath, "build", "version.txt");
      if (fs.existsSync(versionPath)) {
        return fs.readFileSync(versionPath, { encoding: "utf-8" }).trim();
      }
    } catch {
      // ignore
    }
  }
  // 兜底：用 package.json 的 version
  return app.getVersion();
}

// ============================================================
// FastAPI 子进程管理
// ============================================================

function startFastApi(): Promise<void> {
  return new Promise((resolve, reject) => {
    // 端口被占用了直接拒绝
    if (isPortInUse(fastapiPort)) {
      reject(new Error(`Port ${fastapiPort} already in use, abort`));
      return;
    }

    // 打包模式：spawn 内嵌的 LumioAPI 可执行文件（PyInstaller 产物）
    // 开发模式：spawn python -m lumio.api_fastapi（依赖系统 Python + 项目源码）
    //
    // PyInstaller 产物路径：
    //   Windows: <app>/resources/python-backend/LumioAPI.exe
    //   macOS:   <app>/Contents/Resources/python-backend/LumioAPI
    //   Linux:   <app>/resources/python-backend/LumioAPI
    // electron-builder extraResources 配置见 electron-builder.cjs
    let exePath: string;
    let cwdPath: string;
    let env: NodeJS.ProcessEnv;

    if (app.isPackaged) {
      const resourcesPath = process.resourcesPath;
      // macOS: build-backend.js 复制 .app bundle 到 python-backend/LumioAPI.app/
      //   spawn 路径：python-backend/LumioAPI.app/Contents/MacOS/LumioAPI
      // Windows/Linux: build-backend.js 平铺 LumioAPI[.exe] 到 python-backend/
      //   spawn 路径：python-backend/LumioAPI[.exe]
      if (process.platform === "darwin") {
        exePath = path.join(
          resourcesPath,
          "python-backend",
          "LumioAPI.app",
          "Contents",
          "MacOS",
          "LumioAPI"
        );
      } else {
        const exeName = process.platform === "win32" ? "LumioAPI.exe" : "LumioAPI";
        exePath = path.join(resourcesPath, "python-backend", exeName);
      }
      cwdPath = path.dirname(exePath);
      env = {
        ...process.env,
        LUMIO_FASTAPI_PORT: String(fastapiPort),
        LUMIO_FASTAPI_TOKEN: fastapiToken,
      };
      console.log(`[electron] starting packaged FastAPI: ${exePath}`);
    } else {
      const projectRoot = path.resolve(__dirname, "..", "..");
      const pythonCmd = process.platform === "win32" ? "python" : "python3";
      exePath = pythonCmd;
      cwdPath = projectRoot;
      env = {
        ...process.env,
        PYTHONPATH: path.join(projectRoot, "src"),
        LUMIO_FASTAPI_PORT: String(fastapiPort),
        LUMIO_FASTAPI_TOKEN: fastapiToken,
      };
      // 用 args 字段传递 -m lumio.api_fastapi
      (env as any)._devArgs = ["-m", "lumio.api_fastapi"];
      console.log(`[electron] starting dev FastAPI: ${pythonCmd} -m lumio.api_fastapi`);
      console.log(`[electron] cwd: ${projectRoot}`);
      console.log(`[electron] PYTHONPATH: ${path.join(projectRoot, "src")}`);
    }

    const devArgs = (env as any)._devArgs as string[] | undefined;
    delete (env as any)._devArgs;

    fastapiProc = spawn(exePath, devArgs || [], {
      cwd: cwdPath,
      env,
      stdio: ["ignore", "pipe", "pipe"],
    });

    fastapiProc.on("error", (err) => {
      // spawn 本身失败（如 python 命令不存在 / LumioAPI.exe 缺失）
      console.error(`[electron] spawn FastAPI failed: ${err.message}`);
      console.error(`[electron] exe: ${exePath}`);
      if (!app.isPackaged) {
        console.error(`[electron] PATH: ${process.env.PATH}`);
      }
      reject(new Error(`spawn FastAPI failed: ${err.message}`));
    });

    const stdoutBuf: string[] = [];
    fastapiProc.stdout?.on("data", (d) => {
      const s = d.toString();
      stdoutBuf.push(s);
      process.stdout.write(`[fastapi] ${s}`);
    });
    fastapiProc.stderr?.on("data", (d) => {
      process.stderr.write(`[fastapi] ${d}`);
    });
    fastapiProc.on("exit", (code, signal) => {
      console.log(`[electron] FastAPI exited with code ${code} signal ${signal}`);
      if (code !== 0 && code !== null) {
        reject(new Error(`FastAPI exited with code ${code}`));
      }
      fastapiProc = null;
    });

    // 轮询 /api/health（最多 30 秒）
    // 首次延迟 300ms（FastAPI 至少需要 1s 启动，300ms 后开始探活合理）
    // 轮询间隔 200ms（更快感知 ready，减少用户等待）
    const deadline = Date.now() + 30_000;
    const checkHealth = () => {
      const req = http.get(`${FASTAPI_BASE}/api/health`, (res) => {
        if (res.statusCode === 200) {
          res.resume();
          console.log("[electron] FastAPI ready");
          resolve();
        } else {
          res.resume();
          retry();
        }
      });
      req.on("error", () => retry());
      req.setTimeout(1000, () => {
        req.destroy();
        retry();
      });
    };
    const retry = () => {
      if (Date.now() > deadline) {
        reject(new Error("FastAPI startup timeout (30s)"));
      } else {
        setTimeout(checkHealth, 200);
      }
    };
    setTimeout(checkHealth, 300);
  });
}

/** 优雅关闭 FastAPI：发 /api/shutdown，等进程退出（最多 3 秒），超时强制 kill。 */
async function stopFastApi(): Promise<void> {
  if (!fastapiProc) return;

  const pid = fastapiProc.pid;
  console.log(`[electron] stopping FastAPI (pid=${pid})`);

  // 1. 发 shutdown 信号给 FastAPI
  try {
    await new Promise<void>((resolve) => {
      const req = http.request(
        `${FASTAPI_BASE}/api/shutdown`,
        { method: "POST", headers: { "X-Lumio-Token": fastapiToken } },
        (res) => {
          res.resume();
          resolve();
        }
      );
      req.on("error", () => resolve());
      req.setTimeout(1000, () => {
        req.destroy();
        resolve();
      });
      req.end();
    });
    console.log("[electron] /api/shutdown sent");
  } catch {
    // ignore
  }

  // 2. 等进程退出（最多 3 秒），退出立即继续，避免固定 3 秒延迟
  await new Promise<void>((resolve) => {
    const proc = fastapiProc;
    if (!proc) {
      resolve();
      return;
    }
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      resolve();
    };
    // 进程退出 → 立即 resolve
    proc.once("exit", () => {
      console.log("[electron] FastAPI exited gracefully");
      finish();
    });
    // 3 秒兜底超时
    setTimeout(finish, 3000);
  });

  // 3. 强制 kill 残留进程树（兜底）—— M1 修复：跨平台杀进程树
  if (fastapiProc) {
    console.log("[electron] force-killing FastAPI");
    killProcessTree(fastapiProc.pid!);
    fastapiProc = null;
  }

  // 4. 终极兜底：扫端口上的所有 pid 都干掉（防 spawn 出来的 uvicorn worker 残留）
  // 跨平台方案：用 lsof（Unix）+ netstat（Windows）—— 两者输出格式不同
  if (process.platform === "win32") {
    try {
      const out = execSync(`netstat -ano -p tcp | findstr ":${fastapiPort} "`, {
        windowsHide: true,
        encoding: "utf8",
      });
      const pids = new Set<string>();
      for (const line of out.trim().split(/\r?\n/)) {
        const parts = line.trim().split(/\s+/);
        const pid = parts[parts.length - 1];
        if (pid && /^\d+$/.test(pid) && pid !== "0") pids.add(pid);
      }
      for (const pid of pids) {
        try {
          killProcessTree(parseInt(pid, 10));
          console.log(`[electron] cleanup kill pid=${pid}`);
        } catch {
          // ignore
        }
      }
    } catch {
      // no leftover
    }
  } else {
    // Unix: lsof -i :PORT -t 列出占端口的 pid
    try {
      const out = execSync(`lsof -i :${fastapiPort} -t`, {
        encoding: "utf8",
        windowsHide: true,
      });
      const pids = new Set<string>();
      for (const line of out.trim().split(/\r?\n/)) {
        const pid = line.trim();
        if (pid && /^\d+$/.test(pid) && pid !== "0") pids.add(pid);
      }
      for (const pid of pids) {
        try {
          killProcessTree(parseInt(pid, 10));
          console.log(`[electron] cleanup kill pid=${pid}`);
        } catch {
          // ignore
        }
      }
    } catch {
      // no leftover
    }
  }
}

// ============================================================
// BrowserWindow
// ============================================================

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1120,
    height: 720,
    minWidth: 880,
    minHeight: 560,
    backgroundColor: "#0a0a0f",
    title: "Lumio",
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
    autoHideMenuBar: true,
    icon: getIconPath(),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      // sandbox: false — 允许 preload 脚本访问 Node.js API（虽然我们用 IPC 传递配置，
      // 但 sandbox 模式下 process.env 是 polyfill，禁用 sandbox 更稳妥）
      sandbox: false,
      // webSecurity: false — 打包模式必须禁用，否则 file:// origin 的 fetch 请求
      // 到 http://127.0.0.1:PORT 会被 Chromium 的同源策略阻止（"Failed to fetch"）。
      // dev 模式 Vite dev server 自带 CORS 头，不需要禁用。
      // 安全风险：桌面应用本地调用，无敏感风险（FastAPI 只监听 127.0.0.1）
      webSecurity: !app.isPackaged,
    },
    // 关键：主窗口创建时不立即显示
    // 等 React 渲染完毕（ready-to-show）+ FastAPI ready 后再 show
    // 避免显示空窗口或 React 加载期间的黑屏
    show: false,
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  // 加载 React 主页
  // - dev 模式：立即加载 Vite dev server（Vite 已在运行，React HMR 可用）
  // - packaged 模式：不在此处 loadFile！等 FastAPI ready 后再 loadFile（见下方 whenReady）
  //   原因：如果在 FastAPI ready 之前 loadFile，React useEffect 会立即发起 fetch，
  //   此时 FastAPI 还没启动，fetch 会失败。虽然有 fetchWithRetry（30 次重试 15 秒），
  //   但如果 FastAPI 启动慢或时序不巧，重试可能全部失败 → setError → 页面显示
  //   "TypeError: Failed to fetch"，且 React 不会自动重新 fetch。
  //   等 FastAPI ready 后再 loadFile，React 渲染时 FastAPI 已 ready，fetch 第一次就成功。
  if (process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL);
    mainWindow.webContents.openDevTools({ mode: "detach" });
  }
  // packaged 模式的 loadFile 延迟到 FastAPI ready 之后（见 app.whenReady 中的 4.5 步）

  // 关键：React 渲染完毕后触发 ready-to-show
  // 配合 FastAPI ready 条件，两者都满足后才 show 主窗口 + 销毁 splash
  // 避免切换瞬间黑屏（主窗口 show 时内容已渲染完毕）
  mainWindow.once("ready-to-show", () => {
    console.log("[electron] mainWindow ready-to-show");
    mainWindowReady = true;
    tryShowMainWindow();
  });

  // 关闭窗口 → 按 config.close_behavior 分支：
  //   - "ask"      → 弹三选确认窗（取消/退出/最小化到托盘）
  //   - "minimize" → 直接最小化到托盘（不弹窗）
  //   - "quit"     → 直接退出程序（不弹窗）
  // isQuitting=true 时（用户从托盘菜单选"退出"）直接放行
  // 用户在 close-dialog 勾选「记住选择」时写入 close_behavior，从此不再弹窗
  // SettingsPage 通用设置也能改这个值
  mainWindow.on("close", (e) => {
    if (isQuitting) return;
    e.preventDefault();
    const behavior = readCloseBehavior();
    if (behavior === "minimize") {
      mainWindow?.hide();
      return;
    }
    if (behavior === "quit") {
      isQuitting = true;
      stopFastApi().finally(() => app.quit());
      return;
    }
    // "ask" 或读取失败 → 弹窗
    if (trayManager) {
      trayManager.showCloseDialog();
    } else {
      mainWindow?.hide();
    }
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

/**
 * 创建 splash 启动窗口（极简 HTML，不依赖 React，秒开）。
 *
 * 双窗口架构：
 *   1. splash 窗口立即显示（loadFile splash.html，无 React 依赖，<100ms 渲染）
 *   2. 主窗口后台加载 React（show: false，用户看不到加载过程）
 *   3. 主窗口 ready-to-show + FastAPI ready → 主窗口 show + splash 销毁
 *
 * splash 窗口特点：
 *   - 与主窗口同尺寸（1120x720）+ 同 backgroundColor，切换瞬间无大小/色差跳变
 *   - frame: false 无标题栏（splash 不需要交互）
 *   - 不依赖 React bundle，纯 HTML+CSS，秒开
 *   - 版本号通过 query string 传入（readAppVersion 同步读取）
 */
function createSplashWindow(): void {
  const version = readAppVersion();
  splashWindow = new BrowserWindow({
    width: 1120,
    height: 720,
    frame: false,
    resizable: false,
    maximizable: false,
    minimizable: false,
    backgroundColor: "#0a0a0f",
    icon: getIconPath(),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
    // A3: 立即显示——splash 内容是纯内联 HTML+CSS（splash.html 无 external 资源），
    // 配合 backgroundColor 与最终主窗口底色一致（#0a0a0f），切换瞬间无色差跳变。
    // 不等 ready-to-show，让 splash 在 Chromium 完成首次绘制前就用背景色占据屏幕。
    show: true,
  });

  const splashPath = app.isPackaged
    ? path.join(process.resourcesPath, "build", "splash.html")
    : path.join(__dirname, "..", "build", "splash.html");

  splashWindow.loadFile(splashPath, { query: { v: version } });

  splashWindow.on("closed", () => {
    splashWindow = null;
  });
}

// ============================================================
// 双条件同步：主窗口 ready-to-show + FastAPI ready
// ============================================================

// 两个独立条件，都满足后才 show 主窗口 + 销毁 splash
let mainWindowReady = false;  // React 渲染完毕
let fastapiReady = false;     // FastAPI 启动完毕

/** 主窗口 ready-to-show 或 FastAPI ready 时调用，检查是否两个条件都满足。 */
function tryShowMainWindow(): void {
  if (mainWindowReady && fastapiReady && mainWindow && !mainWindow.isDestroyed()) {
    console.log("[electron] both ready, showing main window + destroying splash");
    mainWindow.show();
    mainWindow.focus();
    // 销毁 splash（主窗口已显示，无黑屏瞬间）
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.close();
      splashWindow = null;
    }
  }
}

// ============================================================
// App lifecycle
// ============================================================

let isQuitting = false;

app.whenReady().then(async () => {
  // ============================================================
  // IPC handlers — 文件/文件夹选择对话框
  // ============================================================
  // SettingsPage 走 Electron 原生对话框，不走 FastAPI/Qt 的 QFileDialog
  // 原因：QFileDialog 必须在 Qt 主线程调用，而 FastAPI 端点在 asyncio 事件循环，
  //       模态对话框会阻塞整个 FastAPI 30 秒（用户选文件夹期间），
  //       期间所有其他 API 请求都会卡住。Electron dialog 异步且不阻塞 FastAPI。
  ipcMain.handle("dialog:open-folder", async () => {
    if (!mainWindow) return "";
    const r = await dialog.showOpenDialog(mainWindow, {
      title: "选择文件夹",
      properties: ["openDirectory"],
    });
    return r.canceled || r.filePaths.length === 0 ? "" : r.filePaths[0];
  });

  ipcMain.handle(
    "dialog:open-files",
    async (_evt, filters: Electron.FileFilter[] | undefined) => {
      if (!mainWindow) return [] as string[];
      const r = await dialog.showOpenDialog(mainWindow, {
        title: "选择文件",
        properties: ["openFile", "multiSelections"],
        filters: filters || [{ name: "All Files", extensions: ["*"] }],
      });
      return r.canceled ? [] : r.filePaths;
    }
  );

  // 注册 lumio-file:// protocol 的实际 handler
  // lumio-file:///C:/Users/.../foo.mp4 → 本地文件 → Response(stream)
  //
  // 可靠性设计：
  // - 之前用 net.fetch(file://) 返回 Response，但 Windows 上 net.fetch 对 file:// 的
  //   Range 请求处理不可靠，<video> 标签会拒绝播放（无声卡死或黑屏）
  // - 改用 fs.createReadStream 直接读取文件，手动处理 Range 请求头
  // - 根据文件扩展名推断 MIME，强制设置 Content-Type（video 标签要求 video/mp4 等）
  // 诊断日志：记录所有 lumio-file:// 请求到文件，用于排查 packaged 模式下播放器加载失败
  const debugLogPath = path.join(app.getPath("home"), ".lumio", "lumio-file-debug.log");
  const debugLog = (msg: string) => {
    try {
      const ts = new Date().toISOString();
      fs.appendFileSync(debugLogPath, `[${ts}] ${msg}\n`);
    } catch {}
  };
  debugLog(`protocol.handle registered. isPackaged=${app.isPackaged}`);
  protocol.handle("lumio-file", (request) => {
    debugLog(`REQUEST url=${request.url} range=${request.headers.get("range") || "none"}`);
    try {
      // request.url 形如 lumio-file://localhost/C%3A/Users/.../foo.mp4
      // host=localhost（固定），pathname=/C%3A/Users/.../foo.mp4
      // decodeURIComponent 后 /C:/Users/.../foo.mp4 → 去前导斜杠 → C:/Users/...
      const u = new URL(request.url);
      let p = decodeURIComponent(u.pathname);
      // Windows 路径前导斜杠去掉：/C:/foo → C:/foo
      if (process.platform === "win32" && /^\/[A-Za-z]:\//.test(p)) {
        p = p.slice(1);
      }
      debugLog(`PATH decoded=${p} exists=${fs.existsSync(p)}`);
      // 安全校验：必须存在且是文件
      if (!fs.existsSync(p) || !fs.statSync(p).isFile()) {
        debugLog(`404 NOT FOUND path=${p}`);
        return new Response("Not found", { status: 404 });
      }
      // 推断 MIME（<video> 标签要求 video/mp4 等，application/octet-stream 会拒绝播放）
      const ext = path.extname(p).toLowerCase();
      const mime = MIME_TYPES[ext] || "application/octet-stream";
      const fileSize = fs.statSync(p).size;

      // 处理 Range 请求（视频拖动进度条 / 分块加载必需）
      const rangeHeader = request.headers.get("range");
      let start = 0;
      let end = fileSize - 1;
      let isPartial = false;

      if (rangeHeader && rangeHeader.startsWith("bytes=")) {
        const m = /bytes=(\d*)-(\d*)/.exec(rangeHeader);
        if (m) {
          isPartial = true;
          start = m[1] ? parseInt(m[1], 10) : 0;
          end = m[2] ? parseInt(m[2], 10) : fileSize - 1;
          // 边界保护
          if (start > end || start >= fileSize) {
            return new Response("Range Not Satisfiable", {
              status: 416,
              headers: {
                "Content-Range": `bytes */${fileSize}`,
              },
            });
          }
          end = Math.min(end, fileSize - 1);
        }
      }

      const contentLength = end - start + 1;
      const stream = fs.createReadStream(p, { start, end });

      // Node Readable → Web ReadableStream
      const webStream = new ReadableStream({
        start(controller) {
          stream.on("data", (chunk) => controller.enqueue(chunk));
          stream.on("end", () => controller.close());
          stream.on("error", (e) => controller.error(e));
        },
        cancel() {
          stream.destroy();
        },
      });

      // 图片缩略图不变 → 长缓存（二次进入 LibraryPage 零 I/O）
      // 视频/其他 → no-cache（用户可能在外部修改，且 <video> Range 请求需要新鲜状态）
      const imageExts = [".jpg", ".jpeg", ".jfif", ".pjpeg", ".pjp", ".png", ".gif", ".webp", ".bmp", ".svg", ".avif", ".heic", ".heif"];
      const isImage = imageExts.includes(ext);
      const headers: Record<string, string> = {
        "Content-Type": mime,
        "Accept-Ranges": "bytes",
        "Content-Length": String(contentLength),
        "Cache-Control": isImage
          ? "public, max-age=604800, immutable"
          : "no-cache",
      };
      if (isPartial) {
        headers["Content-Range"] = `bytes ${start}-${end}/${fileSize}`;
      }

      debugLog(`OK path=${p} mime=${mime} size=${fileSize} range=${start}-${end} status=${isPartial ? 206 : 200}`);
      return new Response(webStream, {
        status: isPartial ? 206 : 200,
        headers,
      });
    } catch (e) {
      debugLog(`500 ERROR: ${e}`);
      console.error("[electron] lumio-file handler error:", e);
      return new Response(`Internal error: ${e}`, { status: 500 });
    }
  });

  // 1. 立即创建 splash 窗口（极简 HTML，秒开，用户立即看到 loading）
  createSplashWindow();
  // 2. 创建主窗口（show: false，后台加载 React，用户看不到加载过程）
  createWindow();

  // 3. 立即初始化系统托盘（不等 FastAPI）
  //    关键修复：原来 tray init 在 await fastApiReadyPromise 之后，FastAPI 启动失败
  //    时（30s 超时）托盘才出现，用户期间无法操作。现在 tray 在窗口创建后立即初始化，
  //    即使 FastAPI 失败用户也能通过托盘菜单退出。
  //    TrayManager.getMainWindow() 是 lazy 函数，调用时才取 mainWindow 引用，
  //    所以在 mainWindow 创建之后初始化 tray 即可。
  const { TrayManager } = await import("./tray");
  trayManager = new TrayManager({
    getMainWindow: () => mainWindow,
    fastapiBase: FASTAPI_BASE,
    fastapiToken: fastapiToken,
    onQuit: async () => {
      isQuitting = true;
      await stopFastApi();
      app.quit();
    },
    onMinimizeToTray: () => {
      mainWindow?.hide();
    },
  });
  trayManager.init();

  // 4. await FastAPI ready（D5: spawn 已在模块顶层启动，这里只等 health 轮询结果）
  //    FastAPI 冷启动与 Electron 主进程初始化并行，这里通常 0 等待或仅需等剩余 health
  try {
    if (fastApiReadyPromise) {
      await fastApiReadyPromise;
    }
    fastapiReady = true;
  } catch (e) {
    // FastAPI 启动失败：仍然显示主窗口（不能让 splash 永远停留）
    // React 前端会检测 /api/health 不可用，显示错误状态 + 重试按钮
    // 用户至少能看到主界面 + 通过托盘菜单退出
    console.error("[electron] Failed to start FastAPI:", e);
    fastapiReady = true;
  }

  // 4.5 FastAPI ready 后加载 React 主页（packaged 模式）
  //     关键修复：之前 createWindow 中立即 loadFile，React useEffect 在 FastAPI ready
  //     之前就发起 fetch，导致 Inbox/History/Library/Stats 页面 "TypeError: Failed to fetch"。
  //     现在等 FastAPI ready 后再 loadFile，React 渲染时后端已就绪，fetch 第一次就成功。
  //     dev 模式已在 createWindow 中 loadURL，此处跳过。
  if (!process.env.VITE_DEV_SERVER_URL && mainWindow && !mainWindow.isDestroyed()) {
    console.log("[electron] FastAPI ready, loading React page");
    mainWindow.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }

  // 5. 检查是否可以显示主窗口（mainWindowReady + fastapiReady 都满足时 show）
  tryShowMainWindow();

  // 自动更新管理器初始化（延迟动态 import，避免主进程启动时加载 electron-updater）
  // 三平台分流：
  //   Windows/Linux: electron-updater 全自动（检查→下载→安装）
  //   macOS: 手动下载 DMG 模式（无 Apple Developer 证书）
  const { UpdaterManager } = await import("./updater");
  updaterManager = new UpdaterManager({
    getMainWindow: () => mainWindow,
    getFastApiProcess: () => fastapiProc,
    killFastApi: async () => {
      // 复用 main.ts 已有的 stopFastApi 逻辑（含 5s 超时 + force kill 兜底）
      await stopFastApi();
    },
  });
  updaterManager.init();
  // 启动后延迟 10 秒自动检查更新（避免阻塞首屏）
  updaterManager.scheduleAutoCheck(10_000);

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

// 窗口全部关闭时不退出（最小化到托盘）；仅在 isQuitting 时真正退出
app.on("window-all-closed", async () => {
  if (!isQuitting) return; // 保持在托盘运行
  await stopFastApi();
  if (process.platform !== "darwin") app.quit();
});

// ============================================================
// 阶段3传输加密：Electron 证书校验（任务11）
// - dev mode（!app.isPackaged）：允许 self-signed 证书，方便本地 HTTPS 测试
// - production mode（app.isPackaged）：默认拒绝无效证书，
//   仅允许 LUMIO_CERT_FINGERPRINT 环境变量指定的 SHA-256 指纹（逗号分隔）
// ============================================================
app.on("certificate-error", (event, webContents, url, error, certificate, callback) => {
  // dev mode：放行所有证书错误（本地 self-signed 方便开发）
  if (!app.isPackaged) {
    debugLog(`certificate-error (dev allow): ${url} - ${error}`);
    event.preventDefault();
    callback(true);
    return;
  }
  // production mode：校验证书指纹白名单
  const allowedFingerprints = (process.env.LUMIO_CERT_FINGERPRINT || "")
    .split(",")
    .map((f) => f.trim().toLowerCase())
    .filter(Boolean);
  const certFp = (certificate.fingerprints?.sha256 || "").toLowerCase();
  if (allowedFingerprints.length > 0 && certFp && allowedFingerprints.includes(certFp)) {
    debugLog(`certificate-error (whitelisted): ${url} fp=${certFp}`);
    event.preventDefault();
    callback(true);
    return;
  }
  // 默认拒绝（不调用 callback(true)），Electron 会显示证书错误页
  debugLog(`certificate-error (rejected): ${url} - ${error} fp=${certFp}`);
  callback(false);
});

app.on("before-quit", async (e) => {
  if (isQuitting) return;
  e.preventDefault();
  isQuitting = true;
  await stopFastApi();
  app.quit();
});

process.on("exit", () => {
  if (fastapiProc) {
    // M1 修复：跨平台杀进程树（exit 事件同步执行，不能用异步 stopFastApi）
    killProcessTree(fastapiProc.pid!);
  }
});

// 信号处理（Ctrl+C 等）
process.on("SIGINT", async () => {
  await stopFastApi();
  process.exit(0);
});
process.on("SIGTERM", async () => {
  await stopFastApi();
  process.exit(0);
});
