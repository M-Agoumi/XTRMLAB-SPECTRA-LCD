"""
single_instance.py -- refuses to let a second copy of this app start, and
brings the already-running one to the front instead. Split out of app.py
(Phase 1 of ROADMAP.md's v2.0 rewrite) -- the mutex check itself has
nothing to do with Tkinter; only the "bring to front" fallback's error
box borrows tkinter.messagebox, and only if FindWindowW can't even
locate the other instance's window.
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
    """Best-effort: finds the already-running instance's window by its
    exact title (FindWindowW matches top-level windows regardless of
    their visibility, so this works even if it's currently withdrawn to
    the tray) and activates it, so refusing to open a second copy still
    does something useful instead of the second launch just silently
    doing nothing."""
    import ctypes
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, _WINDOW_TITLE)
    if not hwnd:
        try:
            from tkinter import messagebox
            messagebox.showinfo(
                "Hongtai Screen",
                "Hongtai Screen is already running -- check your system "
                "tray.")
        except Exception:  # noqa: BLE001 -- best-effort notice only
            pass
        return
    SW_RESTORE = 9
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
