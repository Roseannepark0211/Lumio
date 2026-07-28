/**
 * electron-builder 配置 — 三平台完整支持。
 *
 * 打包架构（参见 AGENTS.md "架构迁移规则"）：
 *
 *   Lumio.exe / Lumio.app / Lumio.AppImage（Electron 前端）
 *     └── resources/
 *          └── python-backend/      ← PyInstaller 产物（LumioAPI + 依赖）
 *               └── LumioAPI[.exe]  ← FastAPI 后端可执行文件
 *
 * 构建流程：
 *   1. PyInstaller 把 src/lumio/ 打包成 dist/LumioAPI/LumioAPI[.exe]（含 Python runtime）
 *   2. 复制到 frontend/python-backend/（electron-builder 输入目录）
 *   3. electron-builder 把 dist/ + dist-electron/ + python-backend/ 打包成安装包
 *
 * main.ts 在 app.isPackaged 时 spawn resources/python-backend/LumioAPI[.exe]
 *
 * 三平台产物（参见发布迁移架构正式版前的准备工作.md "S3"）：
 *   - Windows: NSIS 安装包（.exe），icon.png 自动转 .ico
 *   - macOS:   DMG + universal2（x64 + arm64），icon.png 自动转 .icns
 *              notarize 默认关闭（需 Apple Developer ID，通过环境变量启用）
 *   - Linux:   AppImage + deb + rpm，icon.png 直接用
 *
 * 图标要求：build/icon.png 必须 ≥1024×1024（electron-builder 据此自动生成
 *           .ico / .icns 各尺寸变体），低于此尺寸 Windows/macOS 会报错
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
  // publish: electron-updater 通过此配置拉取 latest.yml + 下载安装包
  // GitHub Releases 作为唯一更新源（个人项目零服务器成本）
  // electron-builder --publish always 会自动上传产物到对应 Release tag
  publish: [
    {
      provider: "github",
      owner: "Roseannepark0211",
      repo: "Lumio",
    },
  ],
  // asar 打包：把 dist/ + dist-electron/ 整体打入 app.asar 归档
  // - 安装包体积 -30%~50%（小文件合并 + 压缩）
  // - 启动时减少 fs 系统调用（一次读取归档 vs 多次小文件 IO）
  // - extraResources 不打入 asar（PyInstaller 产物需要原生文件路径）
  asar: true,
  // 压缩级别：maximum（社区推荐，安装包体积最小，代价是构建时间 +30s）
  compression: "maximum",
  // extraResources：不打入 asar，需要原生文件路径的资源
  //   - python-backend/  : PyInstaller 产物（LumioAPI + 依赖）
  //   - build/splash.html : 开屏 loading 页（main.ts 通过 process.resourcesPath 读取）
  //   - build/version.txt : 真实版本号（main.ts 的 readAppVersion 读取）
  extraResources: [
    {
      from: "python-backend",
      to: "python-backend",
      filter: ["**/*"],
    },
    {
      from: "build/splash.html",
      to: "build/splash.html",
    },
    {
      from: "build/version.txt",
      to: "build/version.txt",
    },
  ],

  // ============================================================
  // Windows — NSIS 安装包
  // ============================================================
  win: {
    target: ["nsis"],
    // icon.png 会被 electron-builder 自动转 .ico（要求 ≥256×256）
    // 多尺寸变体（16/32/48/64/128/256）由 electron-builder 内部生成
    icon: "build/icon.png",
  },
  nsis: {
    // oneClick: false → 显示完整安装向导（欢迎页→选择路径→开始菜单→安装进度→完成）
    // 不是一键安装，用户可以选择安装路径
    oneClick: false,
    allowToChangeInstallationDirectory: true,
    perMachine: false,
    // 卸载安全性：只删除安装目录（%LOCALAPPDATA%\Programs\lumio\），
    // 不删除用户数据（~/.lumio/ 在用户主目录，不受卸载影响）
    // - false（默认）：卸载后保留 AppData
    // - true：卸载时同时删除 %APPDATA%\lumio\ 和 %APPDATA%\Roaming\lumio\
    deleteAppDataOnUninstall: false,
    // 移除了不存在的 build/installer.nsh 引用
    // 如需自定义 NSIS 模板，请新建 build/installer.nsh 后取消注释
    // include: "build/installer.nsh",
    // 安装包图标（缺省用 win.icon）
    installerIcon: "build/icon.png",
    uninstallerIcon: "build/icon.png",
    // 安装完成后是否创建桌面快捷方式
    createDesktopShortcut: true,
    createStartMenuShortcut: true,
  },

  // ============================================================
  // macOS — DMG（单架构，由 CI 矩阵分别构建 x64 / arm64）
  // ============================================================
  // 关键设计：
  //   - 不在 electron-builder.config.js 里指定 mac.arch / target.arch，
  //     让 electron-builder 默认用当前主机架构打包
  //   - CI 矩阵用 macos-13 (Intel x64) + macos-14 (Apple Silicon arm64)
  //     分别跑一次构建，每次产出单一架构的 DMG
  //   - 原因：PyInstaller 不支持交叉编译，Python 后端必须是原生架构
  //     若在 arm64 主机上让 electron-builder 交叉编译 x64，Python 后端
  //     仍是 arm64 → x64 包跑起来后 spawn arm64 LumioAPI 会失败
  //
  //   - notarize: 默认关闭；启用需 Apple Developer ID 证书 +
  //     环境变量 APPLE_ID / APPLE_APP_SPECIFIC_PASSWORD / APPLE_TEAM_ID
  //   - hardenedRuntime: true 是 notarize 的前提（即使不 notarize 也建议开）
  //   - category: App Store 应用分类（utilities=工具类）
  mac: {
    target: ["dmg"],
    icon: "build/icon.png",
    category: "public.app-category.utilities",
    hardenedRuntime: true,
    gatekeeperAssess: false,
    darkModeSupport: true,
    // notarize 默认关闭；通过环境变量启用（CI/CD 中传入凭据）
    //   APPLE_ID=xxx@apple.com
    //   APPLE_APP_SPECIFIC_PASSWORD=xxxx-xxxx-xxxx-xxxx
    //   APPLE_TEAM_ID=XXXXXXXXXX
    notarize: !!(process.env.APPLE_ID && process.env.APPLE_APP_SPECIFIC_PASSWORD && process.env.APPLE_TEAM_ID),
    // entitlements 文件路径（macOS 沙盒权限声明）
    // 即使不开 notarize，hardenedRuntime 也需要 entitlements 才能正常运行
    entitlements: "build/entitlements.mac.plist",
    entitlementsInherit: "build/entitlements.mac.plist",
  },
  dmg: {
    // DMG 卷标题：Lumio-X.Y.Z-arm64.dmg / Lumio-X.Y.Z-x64.dmg
    // ${arch} 由 electron-builder 自动填充为当前主机架构
    title: "${productName}-${version}-${arch}",
    contents: [
      { x: 130, y: 220 },
      { x: 410, y: 220, type: "link", path: "/Applications" },
    ],
  },

  // ============================================================
  // Linux — AppImage + deb + rpm
  // ============================================================
  linux: {
    // 显式 target 列表（字符串数组形式），避免 electron-builder 自动添加 snap
    // CI 中额外用 --linux AppImage deb rpm 命令行参数强制覆盖（命令行优先级最高）
    target: ["AppImage", "deb", "rpm"],
    icon: "build/icon.png",
    // AppImage 分类（遵循 freedesktop.org Desktop Menu Specification）
    category: "Utility",
    // 维护者信息（deb/rpm control 文件用）
    maintainer: "Lumio <lumio@localhost>",
    // 桌面快捷方式元数据（.desktop 文件）
    desktop: {
      Name: "Lumio",
      Comment: "Download media from YouTube/Instagram/X/B站/抖音/快手/微博/小红书",
      Categories: "Network;AudioVideo;",
    },
    // deb 包元数据（控制依赖项）
    deb: {
      depends: ["libnotify4", "libxtst6", "libnss3"],
    },
  },
  AppImage: {
    // AppImage 文件名含架构：Lumio-X.Y.Z.AppImage
    artifactName: "${productName}-${version}-${arch}.${ext}",
  },
};
