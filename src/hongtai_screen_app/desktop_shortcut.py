"""
desktop_shortcut.py -- the "Create Desktop Shortcut" feature. Pure
Windows/filesystem plumbing, no UI toolkit involved.

Frozen build: the shortcut points straight at the packaged .exe (see
create_desktop_shortcut() below). Source run: it points at
scripts/run_v2_app.py (backend_app.py's CLI shim -- equivalent to
`python app.py`, see that module's own docstring) via a hidden
VBScript launcher (write_run_vbs() below).
"""
import os
import subprocess
import sys
import tempfile

from .paths import _app_base_dir, ICON_PATH


def _desktop_dir():
    """Where Desktop actually is. Not just `~\\Desktop` -- OneDrive's
    "Known Folder Move" (on by default on a lot of pre-configured
    Windows machines) relocates it to somewhere like
    `~\\OneDrive\\Desktop` instead, and `~\\Desktop` then simply doesn't
    exist. The registry's User Shell Folders key is what Windows itself
    actually uses to resolve "Desktop", so ask it rather than guessing
    the plain path. (scripts/make_launcher.py reuses this exact
    function -- see there.)"""
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer"
                r"\User Shell Folders") as key:
            path, _ = winreg.QueryValueEx(key, "Desktop")
        return os.path.expandvars(path)
    except OSError:
        return os.path.join(os.path.expanduser("~"), "Desktop")


def write_run_vbs(app_dir, app_path, extra=""):
    """Writes "Launch Hongtai Screen.vbs" into `app_dir` -- a hidden-
    window launcher that runs `app_path` (plus any `extra` CLI args)
    through pythonw.exe via VBScript's WshShell.Run(..., 0, False),
    which is what actually gives a 0-windows launch (a .bat file here
    would still flash a console briefly, which plain Python can't
    suppress on its own without extra dependencies). Returns the
    written .vbs's path.

    Used by create_desktop_shortcut() below (the shortcut points at
    this launcher, not at app_path directly, so double-clicking it
    never opens a console window) and by scripts/make_launcher.py (a
    standalone setup helper for anyone who'd rather not go through the
    GUI's button) -- single source of truth for both, rather than two
    subtly different copies of the same VBScript living in two files."""
    py_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(py_dir, "pythonw.exe")
    interpreter = pythonw if os.path.isfile(pythonw) else sys.executable

    # VBScript doesn't treat backslash as an escape character, so
    # Windows paths need no special handling here -- only the quotes
    # around each path need doubling (VBScript's way of embedding a
    # literal " in a string).
    cmd = '""{interpreter}"" ""{app}""{extra}'.format(
        interpreter=interpreter, app=app_path, extra=extra)
    vbs = (
        'Set WshShell = CreateObject("WScript.Shell")\n'
        f'WshShell.Run "{cmd}", 0, False\n'
    )
    out_path = os.path.join(app_dir, "Launch Hongtai Screen.vbs")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(vbs)
    return out_path


def create_desktop_shortcut():
    """Drops a "Hongtai Screen.lnk" shortcut on the Desktop, and returns
    its path.

    Frozen build (the standalone .exe from BUILD.md): the shortcut
    points straight at the exe -- it's already windowless and already
    carries its own icon (baked in at build time via
    hongtai_screen.spec), and launching it plain (no args) opens the
    backend + window the same way `python app.py` does from source.

    Running from source (`pip install -r requirements.txt`, no build
    step): points at the same hidden "Launch Hongtai Screen.vbs"
    launcher write_run_vbs() above writes (written fresh here if
    missing), targeting scripts/run_v2_app.py -- using icon.ico for the
    icon since a .vbs file can't carry a custom one itself -- see
    scripts/make_launcher.py's own docstring for why a second .lnk file
    is needed for that.

    Raises on failure (missing Desktop folder, non-Windows, cscript
    error) -- callers show that message rather than silently no-op'ing.

    Resolves the source-run target via `_app_base_dir()` (the real
    on-disk repo root), not via `sys.modules["__main__"].__file__` the
    way this used to -- this function is reachable from the exact same
    control_server.py endpoint regardless of which script is currently
    running the control server backing whichever UI clicked the
    button, so trusting `__main__` could bake in the wrong one (see
    startup_registration.py's enable_startup() docstring for the full
    story of how that went wrong before this fix)."""
    if sys.platform != "win32":
        raise RuntimeError("Desktop shortcuts are only supported on Windows.")

    desktop = _desktop_dir()
    if not os.path.isdir(desktop):
        raise RuntimeError(f"No Desktop folder found at {desktop!r}")

    shortcut_path = os.path.join(desktop, "Hongtai Screen.lnk")

    if getattr(sys, "frozen", False):
        target = sys.executable
        working_dir = os.path.dirname(target)
        icon_spec = f"{target},0"
    else:
        app_dir = _app_base_dir()
        app_path = os.path.join(app_dir, "scripts", "run_v2_app.py")
        target = write_run_vbs(app_dir, app_path, "")
        working_dir = app_dir
        icon_spec = (f"{ICON_PATH},0" if os.path.isfile(ICON_PATH)
                     else f"{target},0")

    # Same "no extra dependencies" trick as everywhere else here: hand
    # WScript.Shell.CreateShortcut to a throwaway helper .vbs run once
    # via cscript, rather than pulling in pywin32 just for this.
    helper_script = (
        'Set WshShell = CreateObject("WScript.Shell")\n'
        f'Set link = WshShell.CreateShortcut("{shortcut_path}")\n'
        f'link.TargetPath = "{target}"\n'
        f'link.WorkingDirectory = "{working_dir}"\n'
        f'link.IconLocation = "{icon_spec}"\n'
        'link.Description = "Start the Hongtai/XTRM lab screen app"\n'
        'link.Save\n'
    )
    fd, helper_path = tempfile.mkstemp(suffix=".vbs")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(helper_script)
        result = subprocess.run(["cscript", "//nologo", helper_path],
                                 capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"cscript exited {result.returncode}: "
                f"{result.stderr.strip() or '(no error output)'}")
    finally:
        os.remove(helper_path)

    if not os.path.isfile(shortcut_path):
        raise RuntimeError(
            f"cscript reported success but {shortcut_path} doesn't exist")
    return shortcut_path
