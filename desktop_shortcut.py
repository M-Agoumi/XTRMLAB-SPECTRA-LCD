"""
desktop_shortcut.py -- the "Create Desktop Shortcut" feature. Split out
of app.py (Phase 1 of ROADMAP.md's v2.0 rewrite) -- pure Windows/
filesystem plumbing, no Tkinter involved.
"""
import os
import subprocess
import sys
import tempfile

from app_paths import _app_base_dir, ICON_PATH


def _desktop_dir():
    """Where Desktop actually is. Not just `~\\Desktop` -- OneDrive's
    "Known Folder Move" (on by default on a lot of pre-configured
    Windows machines) relocates it to somewhere like
    `~\\OneDrive\\Desktop` instead, and `~\\Desktop` then simply doesn't
    exist. The registry's User Shell Folders key is what Windows itself
    actually uses to resolve "Desktop", so ask it rather than guessing
    the plain path. (Same helper as make_launcher.py -- kept as its own
    copy here so this works even if make_launcher.py is ever removed
    from a packaged build.)"""
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


def create_desktop_shortcut():
    """Drops a "Hongtai Screen.lnk" shortcut on the Desktop, and returns
    its path.

    Frozen build (the standalone .exe from BUILD.md): the shortcut
    points straight at the exe -- it's already windowless and already
    carries its own icon (baked in at build time via hongtai_screen.spec),
    nothing else to wire up.

    Running from source (`python app.py`): points at the same hidden
    "Launch Hongtai Screen.vbs" launcher make_launcher.py writes
    (written fresh here if missing), using icon.ico for the icon since a
    .vbs file can't carry a custom one itself -- see make_launcher.py's
    own docstring for why a second .lnk file is needed for that.

    Raises on failure (missing Desktop folder, non-Windows, cscript
    error) -- callers show that message rather than silently no-op'ing.
    """
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
        app_path = os.path.abspath(sys.modules["__main__"].__file__)
        # Reuse make_launcher's own .vbs writer so both paths always
        # point at the exact same launcher, instead of two subtly
        # different copies of the same VBScript living in two files.
        import make_launcher
        target = make_launcher._write_run_vbs(app_dir, app_path, "")
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
