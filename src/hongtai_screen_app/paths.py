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

    Anchored on THIS file's own location (three parents up from
    src/hongtai_screen_app/paths.py is always the repo root), not on
    whatever script Python happened to be run as. It used to be
    resolved via sys.modules["__main__"].__file__ instead -- fine back
    when root app.py was the only legitimate entry point, but Phase 2
    added a second one (scripts/run_backend.py, which runs the backend
    with no Tkinter at all) that lives a directory below the repo root.
    Resolving via __main__ made that script write its own separate
    scripts/app_config.json instead of sharing the real one next to
    app.py -- exactly the "same app_config.json" run_backend.py's own
    docstring promises. Anchoring on this file's location instead means
    every entry point (app.py, scripts/run_backend.py, and whatever
    Phase 2c's webview backend turns out to be) agrees on the same
    directory, without needing to know about each other.

    startup_registration.py and desktop_shortcut.py still use
    sys.modules["__main__"].__file__ directly, deliberately -- they're
    solving a different problem (what command line actually points at
    the real running script, for a Windows Startup/.lnk launcher),
    where the __main__ script's own identity is exactly what's wanted.

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
# and app.py's App._poll_show_trigger(). Touched by a second launch that
# finds the app already running, polled by the first (real) instance's
# existing 100ms log-queue timer; when its mtime moves forward, that
# instance shows/raises its own window. This is the RELIABLE way to
# bring the running instance to front -- FindWindowW + SetForegroundWindow
# is attempted first as a same-instant bonus (feels snappier when it
# works) but Windows' foreground-window-stealing restrictions can
# silently no-op it from another process with no way to detect that it
# failed; this file-touch path always works within one poll tick
# (<=100ms) because it's the app itself, on its own Tk main thread,
# deciding to raise its own window -- nothing for Windows to block.
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
