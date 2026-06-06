# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Lumio — run on each target platform

import sys
from pathlib import Path

block_cipher = None

src_path = Path(SPECPATH) / "src"
assets_path = src_path / "lumio" / "assets"

a = Analysis(
    [str(Path(SPECPATH) / "run.py")],
    pathex=[str(src_path)],
    binaries=[],
    datas=[
        (str(assets_path / "logo.png"), "lumio/assets"),
    ],
    hiddenimports=[
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "lumio.gui.preview_dialog",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name="Lumio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
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
    name="Lumio",
)
