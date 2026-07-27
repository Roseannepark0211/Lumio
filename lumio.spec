# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Lumio FastAPI backend — Electron 前端通过 spawn 启动此可执行文件
# 注：前端用 electron-builder 单独打包，此 spec 只打包 Python 后端

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
