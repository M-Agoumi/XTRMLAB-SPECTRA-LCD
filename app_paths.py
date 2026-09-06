"""
app_paths.py -- where this app's files live, on disk.

Split out of app.py (Phase 1 of ROADMAP.md's v2.0 rewrite) because every
future UI -- the current Tkinter one, and eventually the webview/React
one -- needs the exact same answers to "where's the config", "where's
the icon", "where's the startup-debug log", and none of that has
anything to do with Tkinter.
"""
import os
import sys
import time


def _app_base_dir():
    """Directory the running app actually lives in -- used for anything
    that must persist next to it across runs (app_config.json, the
    startup-launcher command in startup_registration.py). Under a frozen
    PyInstaller build, __file__ points inside a temporary extraction
    folder instead (a fresh one every run), so this checks sys.frozen
    and uses the real .exe's own folder in that case."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _resource_path(*parts):
    """Path to a bundled read-only resource (icon.ico) -- inside
    sys._MEIPASS when frozen (PyInstaller's extraction dir for
    --add-data files), next to this script otherwise."""
    base = getattr(sys, "_MEIPASS", None) or _app_base_dir()
    return os.path.join(base, *parts)


CONFIG_PATH = os.path.join(_app_base_dir(), "app_config.json")
ICON_PATH = _resource_path("icon.ico")

# A plain text file next to app_config.json, written to ONLY for
# --autostart launches (see _write_startup_log()) -- pythonw.exe has no
# console and an autostart launch usually starts hidden/minimized too,
# so this is the only way to see what actually happened during a boot
# launch: whether Windows even ran the Startup script, whether the
# single-instance check passed, which theme it decided to resume, and
# any exception along the way. Already covered by .gitignore's blanket
# "*.log" rule.
STARTUP_LOG_PATH = os.path.join(_app_base_dir(), "startup_debug.log")


def _write_startup_log(msg):
    """Best-effort append to STARTUP_LOG_PATH. Opened and closed on every
    call rather than held open, so a line written just before a hard
    crash or a killed process still actually lands on disk instead of
    sitting lost in a buffer."""
    try:
        with open(STARTUP_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:  # noqa: BLE001 -- never let logging itself crash the app
        pass
