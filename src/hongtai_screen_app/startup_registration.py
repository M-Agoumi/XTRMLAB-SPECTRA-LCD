"""
startup_registration.py -- the "Launch at Windows startup" feature: a
Task Scheduler entry (trigger: at this user's logon) that launches
scripts/run_v2_app.py --autostart hidden, no console. Split out of
app.py (Phase 1 of ROADMAP.md's v2.0 rewrite) -- nothing here touches
Tkinter, it's pure Windows/filesystem plumbing.

Registers scripts/run_v2_app.py --autostart (the backend + webview UI),
not app.py -- see enable_startup()'s docstring.

Was a hidden-window VBScript dropped in the Startup folder until a user
report ("takes over a minute to show up, the AIO screen's own vendor
app is up in 5 seconds") traced back to this specific mechanism: items
in shell:startup (and the Run registry key) are what Windows' own
"boot storm" mitigation deliberately staggers/delays after login to
keep the system responsive right after logon, sometimes by minutes on
a system with several startup entries -- well-documented Windows
behavior, and the standard workaround for it is exactly what this now
does: a Task Scheduler task with a logon trigger fires directly off
that trigger, without going through the Startup-apps throttling path
shell:startup/Run-key entries get funneled through. STARTUP_TASK_NAME
is both the Task Scheduler task's name and (for one release) doubles
as a marker for the still-possible leftover .vbs from before this
change -- see _migrate_legacy_startup_file()'s docstring for how an
existing install picks up the new mechanism automatically.
"""
import os
import subprocess
import sys
import tempfile
import uuid
from collections import namedtuple

from .paths import _app_base_dir

STARTUP_TASK_NAME = "HongtaiScreenApp"

# Mimics subprocess.CompletedProcess's shape (just the 3 fields callers
# here actually read) for _run_schtasks_elevated()'s return value, so
# every caller can treat a plain and an elevated attempt identically.
_Result = namedtuple("_Result", ["returncode", "stdout", "stderr"])


def _noop_log(msg):
    pass


def _legacy_startup_script_path():
    """Where the old (pre-Task-Scheduler) Startup-folder .vbs launcher
    used to live -- kept around only so enable_startup()/disable_startup()
    can clean up a leftover copy from an install made before this file
    switched mechanisms (see _migrate_legacy_startup_file()). Returns
    None off Windows, same as before."""
    if sys.platform != "win32":
        return None
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu",
                         "Programs", "Startup", f"{STARTUP_TASK_NAME}.vbs")


def _migrate_legacy_startup_file(log=_noop_log):
    """Removes a leftover .vbs from the old Startup-folder mechanism, if
    one exists -- called from both enable_startup() and disable_startup()
    so either action, on a machine that still has the old install, fully
    replaces/removes it rather than leaving both the old (slow) launcher
    and the new Task Scheduler entry active at once (which would launch
    the app twice at login). An install made before this change needs no
    manual cleanup: the very next time the person touches the "Launch at
    Windows startup" checkbox -- off, or back on -- this runs and the old
    .vbs is gone."""
    path = _legacy_startup_script_path()
    if path and os.path.isfile(path):
        try:
            os.remove(path)
            log(f"(startup: removed leftover old-style launcher at {path})")
        except OSError as e:
            log(f"(startup: couldn't remove leftover old-style launcher at {path}: {e})")


def _run_schtasks(*args, log=_noop_log):
    """Runs schtasks.exe with `args`, returning its CompletedProcess (or
    re-raising whatever subprocess.run() itself raised, e.g. schtasks.exe
    not being found on PATH at all -- rare, but not impossible if
    something's wrong with the machine's System32 PATH entry, and worth
    surfacing rather than crashing with no explanation).

    Every call is logged -- the exact argv, the exit code, and both
    stdout/stderr (schtasks puts its actual error text on one or the
    other depending on the flavor of failure) -- via `log` (a plain str
    -> None callable; defaults to doing nothing, e.g. when nothing wants
    to watch). This is deliberately unconditional, not just-on-failure:
    the previous version only reported a failure's *message*, which on
    at least one real report ("still doesn't work, no error shown")
    wasn't enough to tell whether schtasks even ran, ran but was denied,
    or ran and silently didn't do what was asked -- three different
    problems that all look identical from a single exception string.
    Seeing the literal command and its literal output is what actually
    lets a person (or Claude, reading the same log back) tell those
    apart.

    Never raises on a non-zero *exit code* -- callers check `returncode`
    themselves, since "task doesn't exist" (query/delete on a fresh
    install) is an expected outcome here, not an error worth a
    traceback. `creationflags=CREATE_NO_WINDOW` keeps this invisible
    even if a caller ever runs it from a windowed (not console)
    process, matching how the launch itself is meant to be silent."""
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    log(f"(startup: running: schtasks {' '.join(args)})")
    try:
        result = subprocess.run(
            ["schtasks", *args],
            capture_output=True, text=True, creationflags=creationflags,
        )
    except OSError as e:
        # schtasks.exe itself couldn't even be started -- e.g. not on
        # PATH. Distinct from a non-zero exit code (which is schtasks
        # running fine and saying no), and would otherwise propagate as
        # a bare, unlogged traceback.
        log(f"(startup: couldn't run schtasks.exe at all: {e})")
        raise
    log(f"(startup: schtasks exited {result.returncode}"
        f"{f' -- stdout: {result.stdout.strip()}' if result.stdout.strip() else ''}"
        f"{f' -- stderr: {result.stderr.strip()}' if result.stderr.strip() else ''})")
    return result


def _looks_like_permission_error(result):
    """True if a failed schtasks attempt looks like it was refused for
    a permissions reason (worth retrying elevated) rather than some
    other problem (a bad argument, say) that elevating again wouldn't
    fix. schtasks' own wording for this is a plain "Access is denied"
    on either stream depending on exactly what it was doing when it
    hit the wall -- seen for real as `stderr: ERROR: Access is
    denied.` on a standard (non-admin) account where, on this
    particular machine/policy, even a /rl limited (run at the user's
    own level, not elevated) task still isn't creatable without an
    elevated *creator*."""
    text = f"{result.stdout} {result.stderr}".lower()
    return "access is denied" in text or "access denied" in text


def _ps_quote(s):
    """Wraps `s` as a PowerShell single-quoted string literal (doubling
    any embedded `'`, PowerShell's own escape for one inside a single-
    quoted string). Single-quoted rather than double-quoted deliberately:
    every value this is used for (the schtasks args, including /tr's
    value, which itself already contains literal embedded `"` chars
    around each path) needs those inner double-quotes to survive
    untouched, and a single-quoted PowerShell string treats `"` as
    perfectly ordinary text -- no escaping of it needed at all, unlike
    a double-quoted one."""
    return "'" + str(s).replace("'", "''") + "'"


def _run_schtasks_elevated(*args, log=_noop_log):
    """Same job as _run_schtasks(), but runs schtasks.exe elevated --
    via PowerShell's `Start-Process -Verb RunAs`, which is what
    actually shows the person a UAC consent prompt and, once they
    approve it, launches the elevated process with an administrator
    token. Used as enable_startup()/disable_startup()'s fallback after
    a plain attempt comes back "Access is denied" -- confirmed by a
    real report: /rl limited (the task runs at the person's own,
    non-elevated level once it fires at logon) still wasn't enough to
    *create* it without an elevated creator on that machine.

    The first version of this tried `-Verb RunAs` directly on
    schtasks.exe with `-RedirectStandardOutput`/`-RedirectStandardError`
    to capture its output -- which a real run immediately rejected with
    "Parameter set cannot be resolved using the specified named
    parameters." Start-Process's output-redirection parameters and its
    `-Verb` (elevation) parameter are two different, mutually exclusive
    parameter sets: an elevated child runs with a different token in
    what's effectively a different session, and stdout/stderr can't be
    piped back across that boundary the normal way -- so asking for
    both together isn't just unsupported here, PowerShell refuses to
    even attempt it, and no UAC prompt appears at all.

    The fix: elevate a small temporary .ps1 script instead of schtasks
    directly. The script itself runs *inside* the elevated process, so
    it can write schtasks' combined output and exit code to two plain
    files with ordinary `Out-File` -- no cross-boundary redirection
    needed, because nothing is being redirected across the boundary;
    the elevated process is simply choosing to write its own files.
    The outer, non-elevated `Start-Process -Verb RunAs -Wait` call
    then only needs to elevate and wait, no redirection parameters at
    all, so the two parameter sets never collide. Both the script and
    its two output files are temporary, written fresh (a random suffix
    avoids any collision with a concurrent call) and deleted again
    before this returns either way.

    The outer PowerShell script never raises past its own try/catch: a
    `Win32Exception` there (message containing "cancel" -- what .NET
    reports when the person clicks No/Cancel on the UAC prompt) is
    turned into this function raising a clear, specific RuntimeError
    instead of an opaque PowerShell stack trace.

    Returns a `_Result(returncode, stdout, stderr)` -- same shape
    `_run_schtasks()` returns (stderr always empty here -- the inner
    script merges schtasks' stdout/stderr into one stream since
    there's no elevation-boundary reason not to, and the caller only
    ever logs/searches the combined text anyway), so enable_startup()/
    disable_startup() can treat a plain and an elevated attempt
    identically once this returns; raises RuntimeError instead of
    returning if the person declined the prompt (or elevation
    otherwise never happened), since there's no meaningful "exit code"
    for that."""
    tmp = tempfile.gettempdir()
    tag = uuid.uuid4().hex
    script_path = os.path.join(tmp, f"hongtai_schtasks_{tag}.ps1")
    out_path = os.path.join(tmp, f"hongtai_schtasks_{tag}.out")
    exit_path = os.path.join(tmp, f"hongtai_schtasks_{tag}.exit")
    temp_paths = (script_path, out_path, exit_path)

    arg_list = ", ".join(_ps_quote(a) for a in args)
    # Runs INSIDE the elevated process once Start-Process below launches
    # it -- 2>&1 merges schtasks' stderr into the same stream captured
    # in $output, and $LASTEXITCODE is schtasks' own exit code (the
    # last native command PowerShell ran), not this script's.
    inner_script = (
        f"$a = @({arg_list})\n"
        f"$output = & schtasks.exe @a 2>&1\n"
        f"$output | Out-File -FilePath {_ps_quote(out_path)} -Encoding utf8\n"
        f'"$LASTEXITCODE" | Out-File -FilePath {_ps_quote(exit_path)} -Encoding utf8\n'
    )
    try:
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(inner_script)
    except OSError as e:
        raise RuntimeError(f"Couldn't write the temporary elevated-run script: {e}")

    outer_script = (
        "$ErrorActionPreference = 'Stop'; "
        "try { "
        "Start-Process -FilePath 'powershell.exe' "
        "-ArgumentList @('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', "
        f"'-File', {_ps_quote(script_path)}) "
        "-Verb RunAs -Wait -WindowStyle Hidden; "
        "Write-Output 'ELEVATION_OK' "
        "} catch { "
        "Write-Output ('ELEVATION_FAILED:' + $_.Exception.Message) "
        "}"
    )
    log(f"(startup: requesting elevated permissions to run: schtasks {' '.join(args)})")
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    ps = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", outer_script],
        capture_output=True, text=True, creationflags=creationflags,
    )
    marker = (ps.stdout or "").strip().splitlines()[-1] if (ps.stdout or "").strip() else ""

    def _cleanup():
        for p in temp_paths:
            try:
                os.remove(p)
            except OSError:
                pass

    if not marker.startswith("ELEVATION_OK"):
        reason = (
            marker[len("ELEVATION_FAILED:"):].strip() if marker.startswith("ELEVATION_FAILED:")
            else (ps.stderr.strip() or marker or "no output from the elevation attempt")
        )
        log(f"(startup: elevation request failed or was declined: {reason})")
        _cleanup()
        raise RuntimeError(
            "The permission prompt was declined (or elevation otherwise "
            f"didn't happen): {reason}"
        )
    # "utf-8-sig", not "utf-8": Windows PowerShell 5.1's `Out-File
    # -Encoding utf8` (used above, for both files) always writes a
    # UTF-8 byte-order-mark, unlike PowerShell 7's same-named encoding.
    # A real run showed schtasks succeeding (printed its own "SUCCESS:
    # ..." line) but this code logging exit code -1 anyway -- reading
    # the BOM back as "utf-8" leaves a leading U+FEFF character glued
    # onto the file's text content ("﻿0"), which str.strip() does
    # NOT remove (it's not whitespace), so int("﻿0") raised
    # ValueError and fell through to the -1 fallback below every single
    # time, regardless of what schtasks actually returned. "utf-8-sig"
    # strips a leading BOM automatically if present and behaves exactly
    # like "utf-8" if it's not, so this is a strict improvement either
    # way -- also applied to out_path so a stray BOM can't land at the
    # front of the logged/returned output text either.
    try:
        with open(exit_path, "r", encoding="utf-8-sig", errors="replace") as f:
            returncode = int(f.read().strip())
    except (OSError, ValueError) as e:
        log(f"(startup: couldn't read/parse the elevated exit-code file: {e})")
        returncode = -1
    try:
        with open(out_path, "r", encoding="utf-8-sig", errors="replace") as f:
            output = f.read()
    except OSError:
        output = ""
    _cleanup()
    log(f"(startup: elevated schtasks exited {returncode}"
        f"{f' -- output: {output.strip()}' if output.strip() else ''})")
    return _Result(returncode, output, "")


def is_startup_enabled(log=_noop_log):
    if sys.platform != "win32":
        return False
    result = _run_schtasks("/query", "/tn", STARTUP_TASK_NAME, log=log)
    if result.returncode == 0:
        return True
    # Also true for a not-yet-migrated old install -- see
    # _migrate_legacy_startup_file()'s docstring. Without this, the
    # checkbox would show "off" on an existing install that's actually
    # still launching (slowly) via the old .vbs, until the person
    # happened to toggle it.
    legacy_path = _legacy_startup_script_path()
    return legacy_path is not None and os.path.isfile(legacy_path)


def _launch_command():
    """The interpreter+script command line to register, as a single
    string with each path already quoted -- exactly the same command
    the old .vbs wrapped in WshShell.Run(), just no longer wrapped in
    VBScript. Reused as-is by enable_startup() for schtasks' /tr.

    Deliberately does NOT resolve the app path via
    `sys.modules["__main__"].__file__` (the way this function used to,
    and the way desktop_shortcut.py's create_desktop_shortcut() still
    briefly did): this is reachable from more than one __main__ -- the
    exact same control_server.py REST endpoint the web frontend's
    "Launch at Windows startup" checkbox hits regardless of whether the
    control server behind it happens to be scripts/run_v2_app.py (the
    real thing), scripts/run_backend.py (a headless dev/test server),
    or app.py (the old Tkinter GUI, kept for manual use). Ticking this
    checkbox while the wrong one was __main__ silently baked THAT
    script into the startup entry instead -- which, since only
    run_v2_app.py opens the real app window, could leave "Launch at
    Windows startup" pointing at something that can never show anything
    a later double-click of the desktop icon could find. Resolving via
    `_app_base_dir()` instead (anchored on this package's own on-disk
    location, not on whichever script happened to be running) always
    means the one real scripts/run_v2_app.py, regardless of which entry
    point's UI this was called from.

    Uses pythonw.exe (no console window) when it's sitting next to
    whatever interpreter is actually running this, same fallback as
    before if it isn't there."""
    if getattr(sys, "frozen", False):
        # Frozen build: sys.executable IS the app -- one self-contained
        # .exe, no separate interpreter to pick. NOTE: the current
        # PyInstaller spec (packaging/hongtai_screen.spec) still
        # packages app.py, not run_v2_app.py + the webview UI -- see
        # desktop_shortcut.py's create_desktop_shortcut() docstring.
        # This branch is future Phase 7 packaging work.
        return f'"{sys.executable}" --autostart'
    app_path = os.path.join(_app_base_dir(), "scripts", "run_v2_app.py")
    py_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(py_dir, "pythonw.exe")
    interpreter = pythonw if os.path.isfile(pythonw) else sys.executable
    return f'"{interpreter}" "{app_path}" --autostart'


def enable_startup(log=_noop_log):
    """Registers a Task Scheduler task, triggered at this user's logon,
    that runs `_launch_command()` -- see this module's own docstring
    for why Task Scheduler instead of the Startup folder. `/rl limited`
    runs it with the same (standard, non-elevated) privileges the
    person's own logon session has, same as a Startup-folder launch
    always did; `/f` overwrites a previous registration instead of
    failing if the checkbox is toggled on twice, or if an old task
    exists from before some earlier field (like the command line, on
    an app reinstalled somewhere else) changed.

    `log` (a plain str -> None callable) gets every step of this --
    see _run_schtasks()'s docstring for why that's unconditional, not
    just-on-failure. controller.py's set_startup() passes its own
    _log(), which is what actually shows up in the app's own Log panel
    -- the one place a person can see this without a console attached
    at all (pythonw.exe has none).

    A plain (non-elevated) attempt is tried first -- on most machines
    a standard user can create their own /rl limited logon task with
    no prompt at all, and there's no reason to interrupt that person
    with a UAC dialog they don't need. Only if that comes back looking
    like a permissions refusal (see _looks_like_permission_error()) is
    it retried via _run_schtasks_elevated(), which pops the actual UAC
    prompt -- confirmed necessary by a real "ERROR: Access is denied."
    report on a machine where even a non-elevated-at-runtime task still
    needed an elevated creator."""
    if sys.platform != "win32":
        raise RuntimeError("Launch-at-startup is only supported on Windows.")
    log(f"(startup: enabling -- command that will run at logon: {_launch_command()})")
    _migrate_legacy_startup_file(log=log)
    create_args = (
        "/create", "/tn", STARTUP_TASK_NAME,
        "/tr", _launch_command(),
        "/sc", "onlogon", "/rl", "limited", "/f",
    )
    result = _run_schtasks(*create_args, log=log)
    if result.returncode != 0 and _looks_like_permission_error(result):
        log("(startup: plain attempt was refused for what looks like a "
            "permissions reason -- retrying elevated)")
        result = _run_schtasks_elevated(*create_args, log=log)
    if result.returncode != 0:
        raise RuntimeError(
            f"Couldn't register the startup task (schtasks exited "
            f"{result.returncode}): {result.stderr.strip() or result.stdout.strip()}"
        )
    log("(startup: task registered)")


def disable_startup(log=_noop_log):
    """Same plain-attempt-first, elevate-only-on-a-permissions-refusal
    approach as enable_startup() -- see its docstring. Unlike enabling,
    a failed *disable* still isn't treated as fatal even after the
    elevated retry: the task might never have existed in the first
    place (schtasks reports that as its own kind of failure, not
    success, but it's a fine outcome for "make sure this is off"), and
    this is also called opportunistically from enable_startup() itself
    (by way of _migrate_legacy_startup_file()) where a stale task
    lingering isn't worth surfacing as an error either."""
    log("(startup: disabling)")
    _migrate_legacy_startup_file(log=log)
    if sys.platform != "win32":
        return
    delete_args = ("/delete", "/tn", STARTUP_TASK_NAME, "/f")
    result = _run_schtasks(*delete_args, log=log)
    if result.returncode != 0 and _looks_like_permission_error(result):
        log("(startup: plain attempt was refused for what looks like a "
            "permissions reason -- retrying elevated)")
        try:
            _run_schtasks_elevated(*delete_args, log=log)
        except RuntimeError as e:
            # Still not fatal -- see this function's own docstring.
            log(f"(startup: elevated delete attempt also didn't succeed: {e})")
