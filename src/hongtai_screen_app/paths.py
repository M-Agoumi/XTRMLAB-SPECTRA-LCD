"""
paths.py -- where this app's files live, on disk. Every entry point
(app.py, scripts/run_backend.py, the tray/webview process) needs the
exact same answers to "where's the config", "where's the icon",
"where's the startup-debug log".
"""
import os
import sys
import time


def _app_base_dir():
    """Directory the running app actually lives in -- used for anything
    that must persist next to it across runs (app_config.json, the
    startup-launcher command in startup_registration.py).

    Anchored on THIS file's own location (three parents up from
    src/hongtai_screen_app/paths.py is always the repo root), not on
    whatever script Python happened to be run as. It used to be
    resolved via sys.modules["__main__"].__file__ instead -- that made
    a second entry point (scripts/run_backend.py, which lives a
    directory below the repo root) write its own separate
    scripts/app_config.json instead of sharing the real one next to
    app.py, exactly the "same app_config.json" run_backend.py's own
    docstring promises. Anchoring on this file's location instead means
    every entry point (app.py, scripts/run_backend.py, the tray/webview
    process) agrees on the same directory, without needing to know
    about each other.

    startup_registration.py's _launch_command() and desktop_shortcut.py's
    create_desktop_shortcut() also resolve their source-run target via
    this same function now, for the same reason -- see their own
    docstrings for the report that traced a broken Startup entry back to
    trusting __main__ instead.

    Under a frozen PyInstaller build, this file's own location points
    inside a temporary extraction folder instead (a fresh one every
    run), so this checks sys.frozen and uses the real .exe's own folder
    in that case."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _resource_path(*parts):
    """Path to a bundled read-only resource (icon.ico) -- inside
    sys._MEIPASS/assets when frozen (PyInstaller's extraction dir for
    --add-data files; see packaging/hongtai_screen.spec's `datas`),
    inside the repo root's assets/ folder otherwise."""
    base = getattr(sys, "_MEIPASS", None) or _app_base_dir()
    return os.path.join(base, "assets", *parts)


def frontend_dist_path():
    """Path to the built React frontend's frontend/dist/ folder --
    same sys._MEIPASS-vs-repo-root resolution as _resource_path()
    above, just rooted one level higher (frontend/dist, not
    assets/...) since hongtai_screen.spec bundles it under its own
    top-level datas entry rather than inside assets/. Used by
    control_server.py to find the static frontend build; without this,
    a frozen build would look next to the .exe (where _app_base_dir()
    alone points) instead of inside the extraction dir where
    hongtai_screen.spec actually puts it, and silently fall back to
    the plain-HTML placeholder page."""
    base = getattr(sys, "_MEIPASS", None) or _app_base_dir()
    return os.path.join(base, "frontend", "dist")


# Public alias -- dashboard_theme.py's bundled background images
# (assets/backgrounds/<name>.jpg, see BUNDLED_BACKGROUND_IMAGES) need
# this same "where do read-only bundled resources live" resolution but
# for a filename picked at render time, not a fixed constant like
# ICON_PATH below, so they import the function itself rather than a
# precomputed path.
resource_path = _resource_path

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

# A plain empty file next to app_config.json whose *mtime* is the whole
# point -- see single_instance.py's _bring_existing_window_to_front()
# and backend_app.py's start_show_watcher(). Touched by a second launch
# that finds the app already running, polled by the first (real)
# instance's own watcher thread; when its mtime moves forward, that
# instance shows/raises its own window. This is the RELIABLE way to
# bring the running instance to front -- FindWindowW + SetForegroundWindow
# is attempted first as a same-instant bonus (feels snappier when it
# works) but Windows' foreground-window-stealing restrictions can
# silently no-op it from another process with no way to detect that it
# failed; this file-touch path always works within one poll tick
# (<=200ms) because it's the app itself deciding to raise its own
# window -- nothing for Windows to block.
SHOW_TRIGGER_PATH = os.path.join(_app_base_dir(), "show_request.trigger")


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
