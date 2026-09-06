"""
startup_registration.py -- the "Launch at Windows startup" feature: a
hidden-window VBScript launcher dropped in the Startup folder. Split out
of app.py (Phase 1 of ROADMAP.md's v2.0 rewrite) -- nothing here touches
Tkinter, it's pure Windows/filesystem plumbing.
"""
import os
import sys

STARTUP_TASK_NAME = "HongtaiScreenApp"


def _startup_script_path():
    """Where the Windows Startup-folder launcher lives, or None if this
    isn't Windows (the feature is Windows-only -- other platforms have
    their own login-item mechanisms this app doesn't try to drive)."""
    if sys.platform != "win32":
        return None
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu",
                         "Programs", "Startup", f"{STARTUP_TASK_NAME}.vbs")


def is_startup_enabled():
    path = _startup_script_path()
    return path is not None and os.path.isfile(path)


def enable_startup():
    """Writes a tiny VBScript into the Windows Startup folder that
    launches this app hidden (no console, no window flash) at login.
    VBScript's WshShell.Run(..., 0, False) is what actually gives the
    "0 windows visible" launch -- a .bat file here would still flash a
    console window briefly, which a plain Python script can't avoid on
    its own without extra dependencies.

    Deliberately just `--autostart` with no `--theme` -- which theme
    actually starts is decided at runtime from whatever was last
    actually running (see App.__init__'s auto-resume logic), not fixed
    to whatever was selected the moment this checkbox was ticked."""
    path = _startup_script_path()
    if path is None:
        raise RuntimeError("Launch-at-startup is only supported on Windows.")

    # VBScript doesn't treat backslash as an escape character, so Windows
    # paths need no special handling -- only the quotes around each path
    # need doubling (VBScript's way of embedding a literal " in a string).
    if getattr(sys, "frozen", False):
        # Frozen build: sys.executable IS the app -- one self-contained
        # .exe, no separate interpreter to pick.
        cmd = '""{app}"" --autostart'.format(app=sys.executable)
    else:
        app_path = os.path.abspath(sys.modules["__main__"].__file__)
        py_dir = os.path.dirname(sys.executable)
        pythonw = os.path.join(py_dir, "pythonw.exe")
        interpreter = pythonw if os.path.isfile(pythonw) else sys.executable
        cmd = '""{interpreter}"" ""{app}"" --autostart'.format(
            interpreter=interpreter, app=app_path)
    vbs = (
        'Set WshShell = CreateObject("WScript.Shell")\n'
        f'WshShell.Run "{cmd}", 0, False\n'
    )

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(vbs)


def disable_startup():
    path = _startup_script_path()
    if path and os.path.isfile(path):
        os.remove(path)
