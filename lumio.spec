# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Lumio FastAPI backend — Electron 前端通过 spawn 启动此可执行文件
# 注：前端用 electron-builder 单独打包，此 spec 只打包 Python 后端
#
# 三平台产物（参见发布迁移架构正式版前的准备工作.md "S4"）：
#   - Windows: dist/LumioAPI/LumioAPI.exe（COLLECT 输出，文件夹+exe）
#   - Linux:   dist/LumioAPI/LumioAPI（COLLECT 输出，文件夹+可执行文件）
#   - macOS:   dist/LumioAPI.app（BUNDLE 输出，.app 包，可签名公证）
#              ↑ BUNDLE 让 PyInstaller 生成标准 macOS application bundle，
#                electron-builder 把整个 .app 复制到 Lumio.app/Contents/Resources/
#                这样 afterSign 阶段可对 .app 整体签名，无需逐个 .so/.dylib 签名

import sys
from pathlib import Path

block_cipher = None

src_path = Path(SPECPATH) / "src"
assets_path = src_path / "lumio" / "assets"

a = Analysis(
    [str(Path(SPECPATH) / "run_api.py")],
    pathex=[str(src_path)],
    binaries=[],
    datas=[
        (str(assets_path / "logo.png"), "lumio/assets"),
    ],
    hiddenimports=[
        "flask",
        "werkzeug",
        "werkzeug.serving",
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 已剥离 PySide6 依赖，确保不打进包
        "PySide6",
        "shiboken6",
        # C2 性能优化：排除 Lumio 不使用的常见模块，减小包体积 + 加速冷启动
        # 静态分析器可能因 import 链误打包这些模块，显式 exclude 强制剥离
        # Qt 其他绑定（Lumio 已剥离 PySide6，不用 PyQt）
        "PyQt5",
        "PyQt6",
        "PySide2",
        # GUI 框架（Lumio 用 Electron 前端，不用 tkinter）
        "tkinter",
        # 科学计算（Lumio 不用，但 pip 安装其他包时可能被静态分析误带）
        # numpy 36MB + numpy.libs 5MB = 41MB 体积优化
        "numpy",
        "pandas",
        "matplotlib",
        # IDE 自动补全（运行时不需要，3.3MB）
        "jedi",
        # 高性能 HTTP 客户端（Lumio 用 requests/httpx，不用 impit，7.2MB）
        "impit",
        # 测试/文档/REPL 工具（运行时不需要）
        "pytest",
        "unittest",
        "pydoc",
        "doctest",
        "test",
        "tests",
        "sphinx",
        "docutils",
        "IPython",
        "jupyter",
        "notebook",
        "setuptools",
        "pip",
        "pkg_resources",
        # distutils 在 Python 3.12+ 已移除（PEP 632），不需要 exclude
        # 若 exclude 会与 setuptools._distutils_hack 启动时加载冲突：
        #   ValueError: Target module "distutils" already imported as "ExcludedModule"
        # 标准 GUI/网络模块（Lumio 不用）
        "curses",
        "pdb",
        "xmlrpc",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LumioAPI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # 后端服务，保留 console 便于查看日志
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(assets_path / "logo.png"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="LumioAPI",
)

# ============================================================
# macOS only — BUNDLE 生成 .app 包
# ============================================================
# 仅在 macOS 上生成 .app bundle：
#   - Windows/Linux: 用 COLLECT 输出的文件夹（dist/LumioAPI/）
#   - macOS:         用 BUNDLE 输出的 .app（dist/LumioAPI.app/）
#
# 这样做的好处：
#   1. electron-builder afterSign 阶段可对 .app 整体签名（无需逐个 .so 签名）
#   2. 符合 macOS 应用结构约定（Contents/MacOS/LumioAPI + Contents/Resources/）
#   3. 用户可通过双击 .app 直接运行 Python 后端（开发期调试用）
#
# 注意：electron-builder.cjs 的 extraResources 仍指向 "python-backend"，
# 构建 macOS 时需要把 dist/LumioAPI.app/ 复制到 frontend/python-backend/LumioAPI.app/
# （build-backend.js 脚本会处理这个细节，根据 sys.platform 选择复制 .app 还是文件夹）
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="LumioAPI.app",
        icon=str(assets_path / "logo.png"),
        bundle_identifier="io.lumio.api",
        info_plist={
            "CFBundleName": "LumioAPI",
            "CFBundleDisplayName": "Lumio API",
            "CFBundleShortVersionString": "4.4.1",
            "CFBundleVersion": "4.4.1",
            "LSMinimumSystemVersion": "10.13",
            "LSBackgroundOnly": True,  # 后台服务，不显示 Dock 图标
            "NSHighResolutionCapable": True,
        },
    )
