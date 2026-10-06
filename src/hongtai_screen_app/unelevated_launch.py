"""
unelevated_launch.py -- launches a child process guaranteed to run at
the *caller's own, standard* integrity level, even when this process
itself is currently elevated (Administrator).

Needed for exactly one thing: backend_app.py's `--ui` WebView2 window.
WebView2 doesn't work when its own host process is elevated --
confirmed via WebView2Feedback #4672 and #2984: no error, no crash,
just a black window and nothing useful in the log, which is exactly
what was reported. But this app's CPU Temp stat needs
LibreHardwareMonitorLib's sensor driver, which only loads when the
process *reading* it is elevated (see themes/dashboard_theme.py's own
comment on that) -- so someone who clicks "Relaunch elevated"
(controller.py's relaunch_elevated()) specifically for CPU Temp still
needs the window to actually show up. Elevating the whole app was
never the right fix for that; only the backend/reader half needs the
extra privilege.

The technique: hand the launch to Task Scheduler with `/RL LIMITED`.
A task created with `/RL LIMITED` always runs at standard rights,
*regardless of the creating process's own elevation* -- that's the
one documented purpose of the flag (see schtasks.exe's own /RL docs),
and unlike the PROC_THREAD_ATTRIBUTE_PARENT_PROCESS/Explorer-reparent
approach (Raymond Chen's "How can I launch an unelevated process from
my elevated process, redux"), it needs no ctypes struct or COM
plumbing at all -- and this codebase already leans on schtasks.exe
elsewhere (startup_registration.py) for exactly this "the normal
Win32 API doesn't have a good answer here, but Task Scheduler does"
reason, so this reuses a pattern that's already proven out on real
machines rather than introducing a second, novel one.

`/RU` is deliberately omitted on the /Create call: with no explicit
run-as user, schtasks registers the task to run as *whoever creates
it* (this account), using an interactive (S4U) logon that needs no
stored password and only fires while that account has an active
desktop session -- exactly the case here, someone sitting at the
machine who just clicked "Relaunch elevated". The task is one-shot,
ad-hoc (a random suffix avoids any collision with a concurrent call),
and deletes itself right after /Run hands the process off; nothing
persists in Task Scheduler between launches.
"""
import datetime
import subprocess
import sys
import uuid


def _noop_log(msg):
    pass


def _is_elevated():
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def launch_unelevated(cmd, log=_noop_log):
    """Spawns `cmd` (an argv list) at standard integrity, whether or
    not this process is currently elevated.

    Returns a real `subprocess.Popen` when this process wasn't
    elevated to begin with (the schtasks dance is only needed to
    *drop* privilege, so it's skipped entirely on the common,
    unelevated path) -- or when the schtasks approach fails outright
    and this falls back to a plain, best-effort elevated launch rather
    than not opening a window at all.

    Returns `None` when the unelevated hand-off via Task Scheduler
    actually happened: Task Scheduler fully detaches the new process
    from this one (same as double-clicking it in Explorer would), so
    there's no Popen handle to give back. The caller can't `.poll()`
    or `.terminate()` a `None` -- see backend_app.py's
    `_DetachedProcessHandle`, which stands in for exactly that case by
    tracking the window instead of the process."""
    if not _is_elevated():
        return subprocess.Popen(cmd)

    task_name = f"HongtaiScreenUIWindow_{uuid.uuid4().hex}"
    cmdline = subprocess.list2cmdline(cmd)
    # /SC ONCE requires a /ST even though /Run below fires it
    # immediately by hand -- a minute out is just a harmless, valid
    # value; nothing waits for that scheduled time to actually arrive.
    start_time = (datetime.datetime.now() + datetime.timedelta(minutes=1)).strftime("%H:%M")
    creationflags = subprocess.CREATE_NO_WINDOW

    def _schtasks(*args):
        log(f"(ui: running: schtasks {' '.join(args)})")
        try:
            result = subprocess.run(
                ["schtasks", *args], capture_output=True, text=True, creationflags=creationflags,
            )
        except OSError as e:
            log(f"(ui: couldn't run schtasks.exe at all: {e})")
            return None
        log(f"(ui: schtasks exited {result.returncode}"
            f"{f' -- stdout: {result.stdout.strip()}' if result.stdout.strip() else ''}"
            f"{f' -- stderr: {result.stderr.strip()}' if result.stderr.strip() else ''})")
        return result

    create = _schtasks(
        "/Create", "/TN", task_name, "/TR", cmdline,
        "/SC", "ONCE", "/ST", start_time, "/RL", "LIMITED", "/F",
    )
    if create is None or create.returncode != 0:
        log("(ui: couldn't schedule an unelevated launch -- opening the window elevated "
            "instead, which WebView2 likely won't show anything for)")
        return subprocess.Popen(cmd)

    run = _schtasks("/Run", "/TN", task_name)
    if run is None or run.returncode != 0:
        log("(ui: unelevated launch didn't run -- opening the window elevated instead, "
            "which WebView2 likely won't show anything for)")
        _schtasks("/Delete", "/TN", task_name, "/F")
        return subprocess.Popen(cmd)

    # Best-effort cleanup: /Run only waits for the task to *start*, not
    # to finish (exactly what's wanted for a GUI window meant to stay
    # open until someone closes it), so the task definition itself is
    # no longer needed by the time this line runs. A failed delete just
    # leaves one harmless stale entry in Task Scheduler; not worth
    # failing the whole launch over.
    _schtasks("/Delete", "/TN", task_name, "/F")
    return None
