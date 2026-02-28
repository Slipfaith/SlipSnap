# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for building SlipSnap as a single-file Windows executable.
Compatible with PyInstaller 6+ and Python 3.13+
"""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

# ----------------------------------------------------------------------
# 💡 Project base directory
# ----------------------------------------------------------------------
if "__file__" in globals():
    project_dir = Path(__file__).parent.resolve()
else:
    project_dir = Path(os.getcwd()).resolve()

# Ensure the project path is importable
if str(project_dir) not in sys.path:
    sys.path.insert(0, str(project_dir))

block_cipher = None

# ----------------------------------------------------------------------
# 🔍 Hidden imports
# ----------------------------------------------------------------------
hiddenimports = [
    "mss.windows",
    "pyqtkeybind.win",
    "pyqtkeybind.win.keybindutil",
    "pyqtkeybind.win.keycodes",
]
hiddenimports += collect_submodules("editor")
hiddenimports += collect_submodules("pyqtkeybind")
# OCR stack (pytesseract pulls optional submodules dynamically)
hiddenimports += collect_submodules("pytesseract")
hiddenimports += collect_submodules("PIL")

# ----------------------------------------------------------------------
# 🧩 Path & icon
# ----------------------------------------------------------------------
pathex = [str(project_dir)]
icon_path = project_dir / "SlipSnap.ico"
ffmpeg_candidates = [
    project_dir / "ffmpeg.exe",
    project_dir / "ffmpeg" / "ffmpeg.exe",
    project_dir / "bin" / "ffmpeg.exe",
]
bundled_binaries = []
for candidate in ffmpeg_candidates:
    if candidate.is_file():
        bundled_binaries.append((str(candidate), "."))
        break
if not bundled_binaries:
    print("WARNING: ffmpeg.exe not found, build will require FFmpeg in PATH at runtime.")

# ----------------------------------------------------------------------
# ⚙️ Analysis configuration
# ----------------------------------------------------------------------
a = Analysis(
    [str(project_dir / "main.py")],
    pathex=pathex,
    binaries=bundled_binaries,
    datas=[],  # можно добавить ресурсы: [("assets", "assets")]
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ----------------------------------------------------------------------
# 📦 Create executable
# ----------------------------------------------------------------------
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
    console=False,  # ❌ без консоли
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path) if icon_path.exists() else None,
    onefile=True,  # ✅ один .exe-файл
)
