/**
 * 构建 Python 后端可执行文件（PyInstaller）并复制到 frontend/python-backend/。
 *
 * 流程：
 *   1. 调用 PyInstaller 用 lumio.spec 打包 src/lumio/ → dist/LumioAPI/
 *      （macOS 还会额外生成 dist/LumioAPI.app/ —— BUNDLE 输出）
 *   2. 清空 frontend/python-backend/（避免旧文件残留）
 *   3. 复制产物到 frontend/python-backend/：
 *        Windows/Linux: dist/LumioAPI/* → frontend/python-backend/*
 *        macOS:         dist/LumioAPI.app → frontend/python-backend/LumioAPI.app
 *                       （保留 .app bundle 结构，便于 electron-builder afterSign 整体签名）
 *
 * 用法：
 *   npm run build:backend           # 默认构建
 *   npm run build:backend -- --clean  # 仅清理不构建（调试用）
 *
 * 依赖：
 *   - PyInstaller（pip install pyinstaller）
 *   - 项目依赖已 pip install -e .
 *
 * 输出：
 *   frontend/python-backend/LumioAPI.exe（Windows）
 *   frontend/python-backend/LumioAPI.app/Contents/MacOS/LumioAPI（macOS）
 *   frontend/python-backend/LumioAPI（Linux）
 */
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..", "..");
const frontendRoot = path.resolve(__dirname, "..");
const distDir = path.join(projectRoot, "dist");
const backendDistDir = path.join(distDir, "LumioAPI");
// macOS BUNDLE 输出 .app 包；其他平台无此产物
const backendAppBundle = path.join(distDir, "LumioAPI.app");
const targetDir = path.join(frontendRoot, "python-backend");

const isMacos = process.platform === "darwin";
const exeName = process.platform === "win32" ? "LumioAPI.exe" : "LumioAPI";

function log(msg) {
  console.log(`[build:backend] ${msg}`);
}

function fail(msg) {
  console.error(`[build:backend] ERROR: ${msg}`);
  process.exit(1);
}

// 1. 检查 PyInstaller 可用
log("checking PyInstaller...");
try {
  execSync("pyinstaller --version", { stdio: "pipe", windowsHide: true });
} catch {
  fail("PyInstaller not found. Run: pip install pyinstaller");
}

// 2. 调用 PyInstaller
log(`running PyInstaller (cwd: ${projectRoot})...`);
execSync("pyinstaller lumio.spec --noconfirm", {
  cwd: projectRoot,
  stdio: "inherit",
  windowsHide: true,
});

// 3. 验证产物
// macOS 优先用 .app bundle（BUNDLE 输出），其他平台用 COLLECT 输出的文件夹
const useAppBundle = isMacos && fs.existsSync(backendAppBundle);
const primaryDist = useAppBundle ? backendAppBundle : backendDistDir;
const exePath = useAppBundle
  ? path.join(backendAppBundle, "Contents", "MacOS", "LumioAPI")
  : path.join(backendDistDir, exeName);
if (!fs.existsSync(exePath)) {
  fail(`PyInstaller output not found: ${exePath}`);
}
log(`PyInstaller output: ${exePath}`);
if (useAppBundle) {
  log("macOS: using .app bundle (BUNDLE output) for proper code signing");
}

// 4. 清空目标目录
if (fs.existsSync(targetDir)) {
  log(`cleaning ${targetDir}`);
  fs.rmSync(targetDir, { recursive: true, force: true });
}
fs.mkdirSync(targetDir, { recursive: true });

// 5. 复制产物 → frontend/python-backend/
// macOS + .app: 把整个 .app bundle 复制到 python-backend/LumioAPI.app/
//   main.ts 在 macOS 上 spawn python-backend/LumioAPI.app/Contents/MacOS/LumioAPI
// 其他平台: 把 dist/LumioAPI/* 平铺到 python-backend/
log(`copying ${primaryDist} → ${targetDir}`);
fs.cpSync(primaryDist, targetDir, { recursive: true });

// 5.5 生成 version.txt（packaged 模式 splash 窗口显示真实版本号）
// main.ts 的 readAppVersion() 会读 resources/build/version.txt
const initPath = path.resolve(__dirname, "..", "..", "src", "lumio", "__init__.py");
if (fs.existsSync(initPath)) {
  const content = fs.readFileSync(initPath, { encoding: "utf-8" });
  const m = content.match(/__version__\s*=\s*["']([^"']+)["']/);
  if (m) {
    const versionDir = path.resolve(__dirname, "..", "build");
    if (!fs.existsSync(versionDir)) fs.mkdirSync(versionDir, { recursive: true });
    fs.writeFileSync(path.join(versionDir, "version.txt"), m[1], { encoding: "utf-8" });
    log(`wrote build/version.txt: ${m[1]}`);
  }
}

// 6. 验证最终产物
const finalExe = useAppBundle
  ? path.join(targetDir, "LumioAPI.app", "Contents", "MacOS", "LumioAPI")
  : path.join(targetDir, exeName);
if (!fs.existsSync(finalExe)) {
  fail(`Final binary not found: ${finalExe}`);
}
const sizeMB = (fs.statSync(finalExe).size / 1024 / 1024).toFixed(1);
log(`done: ${finalExe} (${sizeMB} MB)`);
