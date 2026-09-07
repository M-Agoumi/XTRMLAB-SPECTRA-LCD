"""
power_state.py -- detects "is Windows locked right now", so a running
theme can optionally pause pushing new frames to the panel while the
lock screen is up, the same choice the official XTRM Lab app offers as
"Keep playing when screen is off" (found in its Settings panel --
Electron's `powerMonitor.on('lock-screen' | 'suspend', ...)` stops
rendering there unless that toggle is on).

True system suspend can't meaningfully be "kept active" through from
here: Windows freezes this whole process during real sleep, so there's
nothing to pause or resume -- a theme's run() loop just picks up again,
mid-frame-timing, whenever the process (and the OS) wakes back up. This
module only concerns itself with the one case a policy choice actually
applies: a screen *lock* (Win+L, an idle timeout, "Lock" from the Start
menu), which Windows runs every process straight through, unaffected --
the theme would otherwise happily keep polling stats and pushing frames
to a panel nobody's near.

No extra dependency: `ctypes.windll.user32.OpenInputDesktop()` is the
standard userspace trick for "is the interactive desktop locked (or a
UAC/secure-desktop prompt showing)" -- it only fails in exactly those
cases for a normal, unprivileged process. Always reports "not locked"
on any non-Windows OS, since this whole feature (like the rest of this
app) is Windows-only.
"""
import ctypes
import platform
import threading
import time

IS_WINDOWS = platform.system() == "Windows"

_GENERIC_READ = 0x80000000
POLL_INTERVAL = 2.0  # seconds -- lock state doesn't need checking any faster than this


def _query_locked():
    if not IS_WINDOWS:
        return False
    try:
        user32 = ctypes.windll.user32
        desktop = user32.OpenInputDesktop(0, False, _GENERIC_READ)
        if not desktop:
            return True
        user32.CloseDesktop(desktop)
        return False
    except Exception:  # noqa: BLE001 -- any ctypes/WinAPI hiccup -> assume unlocked
        return False


_lock = threading.Lock()
_locked_now = False
_keep_active = True  # the setting itself -- True (default) means "ignore lock state, same as before this feature existed"
_thread_started = False


def set_keep_active_when_locked(value):
    """True (the default, and the only behavior this app had before
    this setting existed) -- keep pushing frames to the panel no matter
    what. False -- pause (skip pushing new frames, so the panel just
    freezes on whatever it last showed) while Windows is locked, and
    resume automatically the moment it's unlocked. Safe to call whether
    or not polling has started yet."""
    global _keep_active
    _keep_active = bool(value)


def _poll_worker():
    global _locked_now
    while True:
        with _lock:
            _locked_now = _query_locked()
        time.sleep(POLL_INTERVAL)


def start_polling():
    """Idempotent, same pattern as weather.py's/dashboard_theme.py's
    own background pollers -- a no-op off Windows, since IS_WINDOWS is
    False there and should_pause() already always returns False."""
    global _thread_started
    if _thread_started or not IS_WINDOWS:
        return
    _thread_started = True
    threading.Thread(target=_poll_worker, daemon=True).start()


def should_pause():
    """True only when the setting is off AND Windows is actually locked
    right now -- a theme's render loop calls this right before pushing
    a frame and just skips that one push when it's True. Always False
    while the setting is on (the default) or off Windows, so this is a
    safe no-op call to sprinkle into every theme's loop regardless of
    platform or configuration."""
    if _keep_active or not IS_WINDOWS:
        return False
    with _lock:
        return _locked_now
