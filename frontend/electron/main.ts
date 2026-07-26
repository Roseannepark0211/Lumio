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

import { app, BrowserWindow, shell, protocol, net } from "electron";
import { spawn, ChildProcess, execSync } from "node:child_process";
import path from "node:path";
import fs from "node:fs";
import http from "node:http";
import crypto from "node:crypto";
import { pathToFileURL } from "node:url";

// ============================================================
// 全局状态
// ============================================================

let fastapiProc: ChildProcess | null = null;
let mainWindow: BrowserWindow | null = null;

// FastAPI 连接信息（每次启动随机生成，传给子进程 + 渲染进程）
const fastapiPort = pickUnusedPort();
const fastapiToken = crypto.randomBytes(24).toString("hex");
const FASTAPI_BASE = `http://127.0.0.1:${fastapiPort}`;

// 把 token 通过环境变量传给渲染进程（preload 阶段读出）
process.env.LUMIO_FASTAPI_BASE = FASTAPI_BASE;
process.env.LUMIO_FASTAPI_TOKEN = fastapiToken;

// 在 app.whenReady() 之前重写 userData 目录，避免沙箱限制 %APPDATA%/lumio-frontend
// 必须在 app ready 之前调用，否则 Electron 会用默认路径初始化各种缓存
{
  const projectRoot = path.resolve(__dirname, "..", "..");
  const userDataDir = path.join(projectRoot, "frontend", ".electron-cache", "user-data");
  try {
    fs.mkdirSync(userDataDir, { recursive: true });
    app.setPath("userData", userDataDir);
  } catch {
    // 如果设置失败（比如目录不可写），让 Electron 用默认路径
  }
}

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
  ".png": "image/png",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".bmp": "image/bmp",
  ".svg": "image/svg+xml",
};

/** 在 10000-60000 之间挑一个看起来没被占用的端口。 */
function pickUnusedPort(): number {
  // 简单策略：随机一个高位端口。即使偶尔冲突，FastAPI 启动失败也能感知。
  // 真正避免冲突需要 net.createServer().listen(0)，但那是异步的，启动时机太早。
  // 这里用 38910-38999 范围（保留端口段），冲突时 FastAPI 会立即报错。
  return 38910 + Math.floor(Math.random() * 90);
}

/** 同步检查端口是否被占用（用 netstat）。 */
function isPortInUse(port: number): boolean {
  try {
    const out = execSync(`netstat -ano -p tcp | findstr ":${port} "`, {
      windowsHide: true,
      encoding: "utf8",
    });
    return out.trim().length > 0;
  } catch {
    return false;
  }
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

    const projectRoot = path.resolve(__dirname, "..", "..");
    const pythonCmd = process.platform === "win32" ? "python" : "python3";
    const args = ["-m", "lumio.api_fastapi"];

    console.log(`[electron] starting FastAPI on port ${fastapiPort} (token: ${fastapiToken.slice(0, 8)}...)`);
    console.log(`[electron] cwd: ${projectRoot}`);
    console.log(`[electron] cmd: ${pythonCmd} ${args.join(" ")}`);
    console.log(`[electron] PYTHONPATH: ${path.join(projectRoot, "src")}`);

    fastapiProc = spawn(pythonCmd, args, {
      cwd: projectRoot,
      env: {
        ...process.env,
        PYTHONPATH: path.join(projectRoot, "src"),
        LUMIO_FASTAPI_PORT: String(fastapiPort),
        LUMIO_FASTAPI_TOKEN: fastapiToken,
      },
      stdio: ["ignore", "pipe", "pipe"],
    });

    fastapiProc.on("error", (err) => {
      // spawn 本身失败（如 python 命令不存在）
      console.error(`[electron] spawn python failed: ${err.message}`);
      console.error(`[electron] PATH: ${process.env.PATH}`);
      reject(new Error(`spawn python failed: ${err.message}`));
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
        setTimeout(checkHealth, 500);
      }
    };
    setTimeout(checkHealth, 800);
  });
}

/** 优雅关闭 FastAPI：先发 /api/shutdown，等 3 秒，再强制 kill。 */
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

  // 2. 等 3 秒优雅退出
  await new Promise((r) => setTimeout(r, 3000));

  // 3. 强制 kill 残留进程（兜底）
  if (fastapiProc) {
    console.log("[electron] force-killing FastAPI");
    try {
      if (process.platform === "win32") {
        spawn("taskkill", ["/pid", String(fastapiProc.pid), "/f", "/t"]);
      } else {
        fastapiProc.kill("SIGKILL");
      }
    } catch {
      // ignore
    }
    fastapiProc = null;
  }

  // 4. 终极兜底：扫端口上的所有 pid 都干掉（防 spawn 出来的 uvicorn worker 残留）
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
          spawn("taskkill", ["/pid", pid, "/f", "/t"]);
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
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  if (process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL);
    mainWindow.webContents.openDevTools({ mode: "detach" });
  } else {
    mainWindow.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// ============================================================
// App lifecycle
// ============================================================

let isQuitting = false;

app.whenReady().then(async () => {
  // 注册 lumio-file:// protocol 的实际 handler
  // lumio-file:///C:/Users/.../foo.mp4 → file:///C:/Users/.../foo.mp4
  // 用 net.fetch 处理 Range 请求（视频拖动进度条需要）
  //
  // 关键：net.fetch(file://) 返回的 Response Content-Type 默认是 application/octet-stream，
  // <video> 标签会因 MIME 不匹配拒绝播放。这里根据文件扩展名手动推断 MIME，
  // 重新构造 Response 强制设置 Content-Type。
  protocol.handle("lumio-file", async (request) => {
    try {
      // request.url 形如 lumio-file:///C%3A/Users/.../foo.mp4
      // URL 解析后 pathname 是 /C:/Users/.../foo.mp4（前导斜杠+盘符）
      const u = new URL(request.url);
      let p = decodeURIComponent(u.pathname);
      // Windows 路径前导斜杠去掉：/C:/foo → C:/foo
      if (process.platform === "win32" && /^\/[A-Za-z]:\//.test(p)) {
        p = p.slice(1);
      }
      // 安全校验：必须存在且是文件
      if (!fs.existsSync(p) || !fs.statSync(p).isFile()) {
        return new Response("Not found", { status: 404 });
      }
      // 推断 MIME（net.fetch 对 file:// 返回的 mime 不可靠，video 标签会拒绝播放）
      const ext = path.extname(p).toLowerCase();
      const mime = MIME_TYPES[ext] || "application/octet-stream";
      // 用 file:// URL 让 net.fetch 处理 Range 等细节
      const fileResp = await net.fetch(pathToFileURL(p).toString());
      // 重新构造 Response，强制设置 Content-Type
      const headers = new Headers(fileResp.headers);
      headers.set("Content-Type", mime);
      headers.set("Accept-Ranges", "bytes");
      return new Response(fileResp.body, {
        status: fileResp.status,
        statusText: fileResp.statusText,
        headers,
      });
    } catch (e) {
      console.error("[electron] lumio-file handler error:", e);
      return new Response(`Internal error: ${e}`, { status: 500 });
    }
  });

  try {
    await startFastApi();
  } catch (e) {
    console.error("[electron] Failed to start FastAPI:", e);
  }
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", async () => {
  if (isQuitting) return;
  isQuitting = true;
  await stopFastApi();
  if (process.platform !== "darwin") app.quit();
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
    try {
      if (process.platform === "win32") {
        spawn("taskkill", ["/pid", String(fastapiProc.pid), "/f", "/t"]);
      } else {
        fastapiProc.kill("SIGKILL");
      }
    } catch {
      // ignore
    }
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
