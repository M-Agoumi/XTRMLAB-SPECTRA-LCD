# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller build spec for the desktop app -- produces a single
# "Hongtai Screen.exe" with no console window, the app icon baked in,
# and assets/icon.ico + the built React frontend bundled as resources
# (paths.py's _resource_path() / control_server.py's frontend lookup
# find them inside sys._MEIPASS at runtime).
#
# This ONE .exe is both halves of the app: launched plain or with
# --autostart it's the backend + tray icon; launched with --ui (which
# only backend_app.py itself ever does, spawning a second copy of this
# same .exe as a child process) it's the webview window instead -- see
# app.py's own docstring for why a single-file frozen build needs that
# dispatch rather than two separate scripts.
#
# Build (Windows only; see BUILD.md, which also covers building
# frontend/dist/ first):
#
#   pip install pyinstaller
#   pyinstaller packaging/hongtai_screen.spec
#
# Output lands in dist\Hongtai Screen.exe -- a single portable file.
# app_config.json is created next to whatever folder you put the exe
# in (see paths.py's _app_base_dir()), so it's fine to move the exe
# around after building; nothing else needs to travel with it -- the
# app package (src/), the built frontend, and the icon are all baked
# in.
#
# Every path below is anchored on REPO_ROOT (derived from SPECPATH,
# PyInstaller's own "directory this spec file lives in" variable), NOT
# on whatever directory `pyinstaller` happens to be invoked from. A
# real CI run confirmed PyInstaller resolves the Analysis() entry
# script relative to the spec file's own directory regardless of cwd
# ("script '...\packaging\app.py' not found" -- it was looking for
# app.py *inside* packaging/, i.e. treating "app.py" as relative to
# this file rather than to the repo root command shown above) -- this
# used to be dismissed as a sandbox-only quirk when it first showed up
# during local testing, but it happens on real Windows too. Building
# every path here from REPO_ROOT makes this spec correct no matter
# where it's invoked from, instead of relying on an invocation-
# directory convention PyInstaller doesn't actually honor.

import glob
import os
import sys

from PyInstaller.utils.hooks import collect_all

block_cipher = None
REPO_ROOT = os.path.dirname(SPECPATH)  # SPECPATH: packaging/ -- one level up is the repo root

# pycairo (dashboard_theme.py's `import cairo`, the gauges/thumbnails --
# see its own try/except ImportError right at the top of that file) --
# a real report from a built exe: the app ran, but every Dashboard
# render and every preset thumbnail failed with dashboard_theme.py's own
# "needs pycairo... it isn't installed" message, even though `pip
# install -r requirements.txt` (pycairo is in there, unconditionally)
# had clearly succeeded during that same build -- so pycairo was
# present at BUILD time but its compiled extension (cairo/_cairo.
# cp3xx-win_amd64.pyd) didn't make it into the frozen exe. `import
# cairo` is a plain top-level statement in a module PyInstaller's
# static analyzer can already see (controller.py imports dashboard_
# theme.py directly, no lazy/dynamic import in between, unlike pystray/
# webview/pythonnet above), so this isn't the same "analyzer can't
# trace a runtime backend pick" problem those hidden_imports exist for
# -- collect_all() is the standard, more thorough fix PyInstaller's own
# docs recommend when a compiled extension's binary gets silently
# dropped despite a plain static import, and it's cheap/harmless to
# apply even if the exact root cause on that CI run was something more
# specific (a stale build cache, say).
cairo_datas, cairo_binaries, cairo_hiddenimports = collect_all("cairo")

hidden_imports = [
    # PyInstaller's static import scanner can miss these -- they're
    # loaded conditionally/lazily by the libraries that use them.
    "pynvml",              # nvidia-ml-py's importable name (dashboard GPU stats)
    "winsdk",
    "winsdk.windows.media.control",
    "winsdk.windows.storage.streams",
    "pystray._win32",      # pystray picks its backend at import time
    # pywebview (ui_window.py) picks its rendering backend at import
    # time too, same reasoning as pystray above -- edgechromium is the
    # one that actually matters on Windows (WebView2), winforms is its
    # fallback on an older pywebview/no WebView2 install.
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    # pythonnet (CPU Temp, dashboard_theme.py's _lhm_cpu_temp()) loads
    # its .NET runtime dynamically via clr_loader -- PyInstaller's
    # static scanner can't follow that either. Untested from this
    # Linux sandbox (pythonnet is Windows-only at runtime); if CPU
    # Temp works with `python app.py` but not the built exe, check the
    # exe's console output (see BUILD.md's "If something doesn't work
    # in the exe") for a clr/clr_loader import error first.
    "clr",
    "clr_loader",
] + cairo_hiddenimports

# LibreHardwareMonitorLib.dll (CPU Temp, dashboard_theme.py's
# _lhm_cpu_temp()) -- NOT committed to this repo, see BUILD.md's
# "Hardware sensors" section for why (get it straight from its own
# maintainers) and where to place it before building. Genuinely
# optional, unlike the other datas entries below: PyInstaller hard-
# fails the *entire build* (SystemExit) on a datas glob that matches
# zero files -- it does NOT just skip a missing one the way this app's
# own optional dependencies degrade gracefully at runtime -- so this
# has to be built up conditionally in Python here rather than listed
# as a plain tuple like everything else.
optional_datas = []
if glob.glob(os.path.join(REPO_ROOT, "assets", "hardware", "*.dll")):
    optional_datas.append((os.path.join(REPO_ROOT, "assets", "hardware", "*.dll"), "assets/hardware"))
else:
    print('NOTE: assets/hardware/*.dll not found -- building without CPU Temp '
          'support. See BUILD.md\'s "Hardware sensors" section.')

a = Analysis(
    [os.path.join(REPO_ROOT, "app.py")],
    # app.py (the repo-root launcher) does its own sys.path.insert(0,
    # ".../src") before importing hongtai_screen_app -- PyInstaller's
    # static analyzer can't follow that at scan time, so it's told
    # here explicitly instead.
    pathex=[os.path.join(REPO_ROOT, "src")],
    binaries=[] + cairo_binaries,
    datas=[
        (os.path.join(REPO_ROOT, "assets", "icon.ico"), "assets"),
        # The bundled dashboard background pictures (dashboard_theme.
        # py's BUNDLED_BACKGROUND_IMAGES) -- same "assets" dest dir as
        # the icon above, so paths.py's _resource_path() finds them at
        # sys._MEIPASS/assets/backgrounds/*.jpg the same way it finds
        # icon.ico.
        (os.path.join(REPO_ROOT, "assets", "backgrounds", "*.jpg"), "assets/backgrounds"),
        # The bundled display fonts (dashboard_theme.py's
        # FONT_FAMILIES), resolved through the same resource_path()
        # mechanism. Without these a frozen build silently falls back
        # to whatever generic sans Windows has, which is exactly the
        # "every theme looks the same" problem they were added to fix
        # -- so they're a real build dependency, not decoration.
        (os.path.join(REPO_ROOT, "assets", "fonts", "*.ttf"), "assets/fonts"),
        (os.path.join(REPO_ROOT, "assets", "fonts", "*-OFL.txt"), "assets/fonts"),
        (os.path.join(REPO_ROOT, "assets", "fonts", "LICENSES.md"), "assets/fonts"),
        # The built React frontend (see BUILD.md/README.md -- `cd
        # frontend && npm install && npm run build` before running
        # pyinstaller) -- control_server.py serves this out of
        # paths.py's frontend_dist_path(), which resolves to
        # frontend/dist/ next to the repo root when running from
        # source, or sys._MEIPASS/frontend/dist when frozen (same
        # split as the assets above). Without this a frozen build
        # would fall back to the plain-HTML placeholder page instead
        # of the real UI.
        (os.path.join(REPO_ROOT, "frontend", "dist"), "frontend/dist"),
    ] + optional_datas + cairo_datas,
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
    upx=False,          # UPX-compressing an opencv/webview/playwright build
                         # is a common source of false-positive AV flags;
                         # leave it off for a release build
    console=False,       # no console window -- same effect as pythonw.exe
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(REPO_ROOT, "assets", "icon.ico"),
)
