"""One-time setup helper: writes "Launch Hongtai Screen.vbs" next to this
script, then (unless --no-desktop-icon is passed) also drops a desktop
shortcut to it, using icon.ico, so it's a real double-click icon rather
than just a file in this folder.

Why the .vbs exists: double-clicking app.py directly runs it through
python.exe, which opens a console window to host it. The app's own
"close to tray" logic only handles the *app's* window (the X button) --
it can't do anything about that console, and closing the console kills
the whole process tree (including the tray icon), console and app
together. There's no way to intercept that from inside app.py itself:
the fix has to be to not have a console in the first place.

This mirrors exactly what "Launch at Windows startup" (see
enable_startup() in app.py) already does for the Startup-folder
launcher: run app.py via pythonw.exe (the windowless twin of
python.exe) through VBScript's WshShell.Run(..., 0, False), which is
what actually gives a 0-windows launch -- a .bat file here would still
flash a console briefly, which plain Python can't suppress on its own
without extra dependencies. The difference is this one lives next to
app.py for you to double-click (or pin/shortcut to your desktop)
whenever you want, instead of firing automatically at login.

Why the desktop shortcut is a second, separate file rather than just
pointing you at the .vbs: a .vbs file's icon is fixed (the generic
Windows Script Host scroll icon) -- Windows has no way to reskin it.
A .lnk shortcut *can* carry a custom icon regardless of what it points
to, so that's what creating one buys you: an actual Hongtai Screen icon
on your desktop instead of a generic scroll. The shortcut is built by
handing WScript.Shell.CreateShortcut to a throwaway helper .vbs run
once via cscript -- the same "no extra dependencies" approach as
everything else here; it's deleted right after.

Run once:
    python make_launcher.py

Re-run any time you move this folder or switch Python installs, to
refresh the paths baked into the .vbs/.lnk. Any extra arguments are
passed through to app.py every time the launcher runs, e.g.:
    python make_launcher.py --theme video
"""
import os
import subprocess
import sys
import tempfile


def _write_run_vbs(app_dir, app_path, extra):
    py_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(py_dir, "pythonw.exe")
    interpreter = pythonw if os.path.isfile(pythonw) else sys.executable

    # VBScript doesn't treat backslash as an escape character, so Windows
    # paths need no special handling here -- only the quotes around each
    # path need doubling (VBScript's way of embedding a literal " in a
    # string), same as enable_startup() in app.py.
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


def _desktop_dir():
    """Where Desktop actually is. Not just `~\\Desktop` -- OneDrive's
    "Known Folder Move" (on by default on a lot of pre-configured
    Windows machines) relocates it to somewhere like
    `~\\OneDrive\\Desktop` instead, and `~\\Desktop` then simply doesn't
    exist. The registry's User Shell Folders key is what Windows itself
    actually uses to resolve "Desktop", so ask it rather than guessing
    the plain path."""
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


def _create_desktop_shortcut(vbs_path, app_dir):
    icon_path = os.path.join(app_dir, "icon.ico")
    if not os.path.isfile(icon_path):
        print("(no icon.ico next to this script -- skipping the desktop "
              "shortcut, the .vbs launcher above still works fine)")
        return None

    desktop = _desktop_dir()
    if not os.path.isdir(desktop):
        print(f"(no Desktop folder found at {desktop} -- skipping the "
              "desktop shortcut)")
        return None

    shortcut_path = os.path.join(desktop, "Hongtai Screen.lnk")
    # No space around the comma -- WScript.Shell's IconLocation parser is
    # picky about this; "path, 0" (with a space) can silently fail to
    # apply while still saving the shortcut, leaving the target's own
    # default icon showing instead.
    helper_script = (
        'Set WshShell = CreateObject("WScript.Shell")\n'
        f'Set link = WshShell.CreateShortcut("{shortcut_path}")\n'
        f'link.TargetPath = "{vbs_path}"\n'
        f'link.WorkingDirectory = "{app_dir}"\n'
        f'link.IconLocation = "{icon_path},0"\n'
        'link.Description = "Start the Hongtai/XTRM lab screen app"\n'
        'link.Save\n'
        'WScript.Echo "OK TargetPath=" & link.TargetPath\n'
        'WScript.Echo "OK IconLocation=" & link.IconLocation\n'
    )
    fd, helper_path = tempfile.mkstemp(suffix=".vbs")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(helper_script)
        result = subprocess.run(["cscript", "//nologo", helper_path],
                                 capture_output=True, text=True)
        if result.stdout.strip():
            print(result.stdout.strip())
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


def main():
    app_dir = os.path.dirname(os.path.abspath(__file__))
    app_path = os.path.join(app_dir, "app.py")

    args = sys.argv[1:]
    skip_desktop_icon = "--no-desktop-icon" in args
    extra_args = [a for a in args if a != "--no-desktop-icon"]
    extra = " " + " ".join(extra_args) if extra_args else ""

    vbs_path = _write_run_vbs(app_dir, app_path, extra)
    print(f"Wrote {vbs_path}")

    if skip_desktop_icon:
        print("Double-click it (or right-click -> Send to -> Desktop, to "
              "make a shortcut yourself) to start the app with no "
              "console window at all -- there's nothing to close that "
              "can kill it anymore.")
        return

    try:
        shortcut_path = _create_desktop_shortcut(vbs_path, app_dir)
    except Exception as e:  # noqa: BLE001 -- the .vbs above still works either way
        shortcut_path = None
        print(f"(couldn't create the desktop shortcut: {e})")

    if shortcut_path:
        print(f"Wrote {shortcut_path}")
        print('Double-click "Hongtai Screen" on your desktop to start the '
              "app with no console window at all -- there's nothing to "
              "close that can kill it anymore.")


if __name__ == "__main__":
    if sys.platform != "win32":
        print("This launcher is Windows-only (it needs pythonw.exe and "
              "the Windows Script Host). On other platforms, just run "
              "'python app.py' from a terminal and leave the terminal "
              "open, or use your OS's own way of running a background "
              "GUI app.")
        sys.exit(1)
    main()
