/**
 * electron-builder 配置。
 *
 * 打包架构（参见 AGENTS.md "架构迁移规则"）：
 *
 *   Lumio.exe（Electron 前端）
 *     └── resources/
 *          └── python-backend/      ← PyInstaller 产物（LumioAPI.exe + 依赖）
 *               └── LumioAPI.exe    ← FastAPI 后端可执行文件
 *
 * 构建流程：
 *   1. PyInstaller 把 src/lumio/ 打包成 dist/LumioAPI/LumioAPI.exe（含 Python runtime）
 *   2. 复制到 frontend/python-backend/（electron-builder 输入目录）
 *   3. electron-builder 把 dist/ + dist-electron/ + python-backend/ 打包成安装包
 *
 * main.ts 在 app.isPackaged 时 spawn resources/python-backend/LumioAPI.exe
 */
module.exports = {
  appId: "io.lumio.desktop",
  productName: "Lumio",
  directories: {
    output: "release",
    buildResources: "build",
  },
  files: [
    "dist/**/*",
    "dist-electron/**/*",
  ],
  // PyInstaller 产物作为 extraResources 打入安装包
  // 打包后路径：process.resourcesPath/python-backend/LumioAPI.exe
  extraResources: [
    {
      from: "python-backend",
      to: "python-backend",
      filter: ["**/*"],
    },
  ],
  // 应用图标（build/icon.png 或 build/icon.ico）
  win: {
    target: ["nsis"],
    icon: "build/icon.png",
  },
  mac: {
    target: ["dmg"],
    icon: "build/icon.png",
  },
  linux: {
    target: ["AppImage"],
    icon: "build/icon.png",
  },
  nsis: {
    oneClick: false,
    allowToChangeInstallationDirectory: true,
    perMachine: false,
    include: "build/installer.nsh",
  },
};
