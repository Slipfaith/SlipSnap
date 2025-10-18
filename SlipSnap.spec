# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for building SlipSnap into a single-file Windows executable."""
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_submodules

project_dir = Path(__file__).parent.resolve()
if str(project_dir) not in sys.path:
    sys.path.insert(0, str(project_dir))
block_cipher = None

# Collect platform-specific helper modules that PyInstaller might miss during analysis.
hiddenimports = [
    "mss.windows",
    "pyqtkeybind.win",
    "pyqtkeybind.win.keybindutil",
    "pyqtkeybind.win.keycodes",
]
# Ensure package-local dynamic imports are bundled when building on non-Windows hosts.
hiddenimports += collect_submodules("editor")
hiddenimports += collect_submodules("pyqtkeybind")

pathex = [str(project_dir)]
icon_path = project_dir / "SlipSnap.ico"


a = Analysis(
    [str(project_dir / "main.py")],
    pathex=pathex,
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="SlipSnap",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path) if icon_path.exists() else None,
)
