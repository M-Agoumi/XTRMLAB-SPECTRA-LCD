"""
paths.py -- where this app's files live, on disk.

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
    startup-launcher command in startup_registration.py).

    NOT this module's own __file__: since the v2.0 restructure this
    file lives inside src/hongtai_screen_app/, several directories
    below the repo root that app_config.json/startup_debug.log/icon.ico
    actually need to sit next to (wherever the real entry point --
    root app.py, or the frozen .exe -- lives). Resolved instead via
    whatever module Python itself is running as __main__, same
    approach startup_registration.py and desktop_shortcut.py already
    use to find the real script to point a launcher/shortcut at.

    Under a frozen PyInstaller build, __main__'s __file__ points inside
    a temporary extraction folder instead (a fresh one every run), so
    this checks sys.frozen and uses the real .exe's own folder in that
    case."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    main_file = getattr(sys.modules.get("__main__"), "__file__", None)
    if main_file:
        return os.path.dirname(os.path.abspath(main_file))
    return os.getcwd()  # best-effort fallback -- e.g. an interactive shell


def _resource_path(*parts):
    """Path to a bundled read-only resource (icon.ico) -- inside
    sys._MEIPASS/assets when frozen (PyInstaller's extraction dir for
    --add-data files; see packaging/hongtai_screen.spec's `datas`),
    inside the repo root's assets/ folder otherwise."""
    base = getattr(sys, "_MEIPASS", None) or _app_base_dir()
    return os.path.join(base, "assets", *parts)


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
