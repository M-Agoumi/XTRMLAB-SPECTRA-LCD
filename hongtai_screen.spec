# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller build spec for the desktop app -- produces a single
# "Hongtai Screen.exe" with no console window, the app icon baked in,
# and icon.ico bundled as a resource (app.py's _resource_path() finds
# it inside sys._MEIPASS at runtime, see app.py).
#
# Build (Windows only -- run this yourself, see BUILD.md):
#
#   pip install pyinstaller
#   pyinstaller hongtai_screen.spec
#
# Output lands in dist\Hongtai Screen.exe -- a single portable file.
# app_config.json is created next to whatever folder you put the exe
# in (see app.py's _app_base_dir()), so it's fine to move the exe
# around after building; just keep icon.ico out of the way, it's
# already embedded and not needed alongside the exe.

import sys

block_cipher = None

hidden_imports = [
    # PyInstaller's static import scanner can miss these -- they're
    # loaded conditionally/lazily by the libraries that use them.
    "pynvml",              # nvidia-ml-py's importable name (dashboard GPU stats)
    "winsdk",
    "winsdk.windows.media.control",
    "winsdk.windows.storage.streams",
    "pystray._win32",      # pystray picks its backend at import time
    "PIL._tkinter_finder",
]

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("icon.ico", "."),
    ],
    hiddenimports=hidden_imports,
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Hongtai Screen",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX-compressing a Tkinter/opencv/playwright build
                         # is a common source of false-positive AV flags;
                         # leave it off for a release build
    console=False,       # no console window -- same effect as pythonw.exe
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="icon.ico",
)
