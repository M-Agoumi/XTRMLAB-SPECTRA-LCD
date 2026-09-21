"""
single_instance.py -- refuses to let a second copy of this app start,
and brings the already-running one to the front instead. Pure
Windows/ctypes plumbing, no UI toolkit dependency.
"""
import sys

_SINGLE_INSTANCE_MUTEX_NAME = "Local\\HongtaiScreenApp_SingleInstance"
_WINDOW_TITLE = "Hongtai Screen Control"
_single_instance_mutex_handle = None  # kept alive for the process's whole
# lifetime on purpose -- see _ensure_single_instance()'s docstring.


def _ensure_single_instance():
    """Windows-only: refuses to let a second copy of this app start, and
    instead brings the already-running one to the front (even if it's
    currently hidden in the tray). Without this, launching a second copy
    used to silently race the first one for the same COM port -- only
    whichever got there first actually talked to the panel, and every
    other copy just sat there uselessly failing to connect (or, worse,
    fighting the first one for it).

    The "is one already running" check is a named kernel mutex (built
    into ctypes/kernel32 -- no extra dependency), not a lock *file*:
    a mutex is owned by its process and Windows itself cleans it up the
    instant that process exits or is killed, so a prior crash can never
    leave this stuck thinking an instance is running when none actually
    is (the classic failure mode of a stale PID/lock file).

    Returns True if it's fine to keep starting up (either this is the
    first copy, or this isn't Windows and the check doesn't apply),
    False if another instance is already running and this process
    should exit immediately without opening a window.
    """
    if sys.platform != "win32":
        return True  # this app's Windows-specific features (see
                      # startup_registration.py) are Windows-only
                      # already; nothing here needs to apply anywhere else.

    import ctypes

    global _single_instance_mutex_handle
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, _SINGLE_INSTANCE_MUTEX_NAME)
    # GetLastError() (the real Win32 call, not ctypes' own get_last_error()
    # cache, which needs use_last_error=True at DLL-load time to be
    # reliable) -- ERROR_ALREADY_EXISTS means CreateMutexW handed back a
    # handle to an existing mutex rather than creating a new one, i.e.
    # another copy of this app already holds it.
    ERROR_ALREADY_EXISTS = 183
    already_running = kernel32.GetLastError() == ERROR_ALREADY_EXISTS
    # Never closed and never allowed to go out of scope: holding this
    # handle open for this process's entire lifetime is exactly what
    # makes the *next* launch see ERROR_ALREADY_EXISTS. Windows closes it
    # automatically on process exit either way (clean or crashed).
    _single_instance_mutex_handle = handle

    if not already_running:
        return True

    _bring_existing_window_to_front()
    return False


def _bring_existing_window_to_front():
    """Brings the already-running instance's window to front -- so
    double-clicking the desktop icon (or the .lnk, or launching a
    second copy any other way) while it's already running (most of the
    time: minimized to the tray, with no window and no taskbar entry at
    all) just shows it, the way a normal single-window app behaves,
    instead of a second launch either silently doing nothing or -- what
    this used to do -- popping up a "this is already running" message
    box. A person who double-clicked the icon already knows they just
    did that; what they wanted was to SEE the app, not be told why they
    can't have a second one.

    Two mechanisms, in order:

    1. FindWindowW + SetForegroundWindow, same-instant. Matches
       top-level windows regardless of their visibility, so this can
       work even while withdrawn to the tray. Best-effort only: Windows
       restricts which processes are allowed to steal foreground focus,
       and a process calling this from outside the foreground app can
       be silently ignored (the window raises but doesn't actually come
       to the front, or nothing visible happens at all) with no
       reliable way to detect that from here.
    2. Touching SHOW_TRIGGER_PATH's mtime -- picked up by the *running*
       instance's own watcher thread (see backend_app.py's
       start_show_watcher()), which then spawns/focuses its own window.
       Windows never gets a say in that, so unlike FindWindowW this
       always works, just up to ~200ms slower. Done unconditionally (not
       only when FindWindowW fails) since it's the one guaranteed path
       and costs nothing extra when the other one also worked."""
    import ctypes
    from .paths import SHOW_TRIGGER_PATH

    try:
        with open(SHOW_TRIGGER_PATH, "w", encoding="utf-8") as f:
            f.write("")
    except OSError:
        pass  # best-effort -- FindWindowW below is still tried either way

    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, _WINDOW_TITLE)
    if hwnd:
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
