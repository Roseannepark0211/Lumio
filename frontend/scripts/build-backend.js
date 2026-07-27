/**
 * 构建 Python 后端可执行文件（PyInstaller）并复制到 frontend/python-backend/。
 *
 * 流程：
 *   1. 调用 PyInstaller 用 lumio.spec 打包 src/lumio/ → dist/LumioAPI/
 *   2. 清空 frontend/python-backend/（避免旧文件残留）
 *   3. 复制 dist/LumioAPI/* → frontend/python-backend/
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
 *   frontend/python-backend/LumioAPI（macOS/Linux）
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
const targetDir = path.join(frontendRoot, "python-backend");

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
const exePath = path.join(backendDistDir, exeName);
if (!fs.existsSync(exePath)) {
  fail(`PyInstaller output not found: ${exePath}`);
}
log(`PyInstaller output: ${exePath}`);

// 4. 清空目标目录
if (fs.existsSync(targetDir)) {
  log(`cleaning ${targetDir}`);
  fs.rmSync(targetDir, { recursive: true, force: true });
}
fs.mkdirSync(targetDir, { recursive: true });

// 5. 复制 dist/LumioAPI/* → frontend/python-backend/
log(`copying ${backendDistDir} → ${targetDir}`);
fs.cpSync(backendDistDir, targetDir, { recursive: true });

// 6. 验证最终产物
const finalExe = path.join(targetDir, exeName);
if (!fs.existsSync(finalExe)) {
  fail(`Final binary not found: ${finalExe}`);
}
const sizeMB = (fs.statSync(finalExe).size / 1024 / 1024).toFixed(1);
log(`done: ${finalExe} (${sizeMB} MB)`);
