"""
Phase 0b spike -- NOT part of the shipped app. See ROADMAP.md and
README.md in this folder.

Tests the two-process design settled on after Phase 0: an always-on
"backend" process (this script stands in for it) spawns a completely
separate "UI process" (ui_child.py) only while a window is open, and
fully TERMINATES that process -- not window.destroy() inside a shared
process -- when it's done. Phase 0 already showed window.destroy()
doesn't reclaim a shared process's own retained memory; killing a
whole separate process should be a much stronger guarantee (the OS
reclaims 100% of a terminated process's own memory), but there's one
genuinely open question that "should be" doesn't answer: when
ui_child.py's own process is killed, do the msedgewebview2.exe helper
processes IT spawned die along with it, or do they survive as orphans?

This checks both ways, alternating cycles: some cycles kill ONLY the
immediate child PID, others kill the child's WHOLE process tree
(every process it spawned, recursively, found and killed explicitly).
Whichever approach actually leaves nothing behind is what the real app
should use -- relying on an unverified OS cascade would be exactly the
kind of assumption Phase 0 already taught us not to trust.

Setup:
    pip install pywebview psutil pillow
    python spike_process_split.py [cycles]

Written against psutil/subprocess/pywebview's documented behavior, not
verified on a real machine by me -- paste back the console output (or
use the .bat wrapper, which logs to a file) if anything errors out.

Report back: the full printed table, especially the "child-tree" and
"orphans found" columns on the "right after kill" / "5s after kill"
rows -- that's the actual answer to whether this design is safe.
"""
import os
import subprocess
import sys
import time

import psutil

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CHILD_SCRIPT = os.path.join(THIS_DIR, "ui_child.py")


def _webview2_system_wide():
    """Total RSS across every msedgewebview2.exe process on the machine
    -- includes other apps' WebView2 usage too (see spike.py), kept
    here as context alongside the more precise tracked-PID numbers
    below."""
    total = 0
    count = 0
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            name = p.info["name"] or ""
            if "msedgewebview2" in name.lower():
                total += p.info["memory_info"].rss
                count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return count, total


def _alive_pids_info(pids):
    """For a list of PIDs captured BEFORE killing anything, report how
    many are STILL running and their combined RSS.

    This is the only correct way to detect orphaned survivors: once
    the parent PID is dead, re-querying its .children() returns
    nothing even if those children are still very much alive under a
    new parent -- so orphans have to be checked by PID, not by walking
    a process tree that may no longer have a living root.
    """
    alive_count = 0
    alive_rss = 0
    for pid in pids:
        if psutil.pid_exists(pid):
            try:
                alive_rss += psutil.Process(pid).memory_info().rss
                alive_count += 1
            except psutil.NoSuchProcess:
                pass
    return alive_count, alive_rss


def _report(label, backend_pid, tracked_pids=None):
    backend_rss = psutil.Process(backend_pid).memory_info().rss / (1024 * 1024)
    wv_count, wv_rss = _webview2_system_wide()
    line = (f"{label:34s} backend={backend_rss:7.1f}MB  "
            f"msedgewebview2.exe(system) x{wv_count:<2}={wv_rss / (1024 * 1024):7.1f}MB")
    if tracked_pids is not None:
        alive_count, alive_rss = _alive_pids_info(tracked_pids)
        line += (f"  tracked-child-tree alive={alive_count}/{len(tracked_pids)} "
                 f"rss={alive_rss / (1024 * 1024):7.1f}MB")
    print(line)


def kill_pid_only(pid):
    try:
        psutil.Process(pid).kill()
    except psutil.NoSuchProcess:
        pass


def kill_process_tree(pid):
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    for c in proc.children(recursive=True):
        try:
            c.kill()
        except psutil.NoSuchProcess:
            pass
    try:
        proc.kill()
    except psutil.NoSuchProcess:
        pass


def run(cycles=4):
    backend_pid = os.getpid()
    print(f"Backend (this process) PID={backend_pid}\n")
    _report("baseline (backend only, no UI yet)", backend_pid)

    for i in range(cycles):
        method = "PID-only" if i % 2 == 0 else "WHOLE TREE"
        print(f"\n--- cycle {i + 1}/{cycles}  (kill method: {method}) ---")

        child = subprocess.Popen([sys.executable, CHILD_SCRIPT])
        time.sleep(2.5)  # let the window actually show and WebView2 spin up

        try:
            child_proc = psutil.Process(child.pid)
            descendants = [c.pid for c in child_proc.children(recursive=True)]
        except psutil.NoSuchProcess:
            descendants = []
        tracked_pids = [child.pid] + descendants

        _report("UI open", backend_pid, tracked_pids)

        if method == "PID-only":
            kill_pid_only(child.pid)
        else:
            kill_process_tree(child.pid)

        time.sleep(1)
        _report("right after kill", backend_pid, tracked_pids)
        time.sleep(5)
        _report("5s after kill", backend_pid, tracked_pids)

    print("\nDone. Compare 'tracked-child-tree alive=X/Y' on the "
          "'right after kill' / '5s after kill' rows between PID-only "
          "and WHOLE TREE cycles. alive=0/Y on both kinds of cycles "
          "means killing just the child PID is enough (WebView2's own "
          "job-object cleanup handles the rest). If PID-only cycles "
          "leave survivors but WHOLE TREE cycles don't, the real app "
          "needs to explicitly kill the whole process tree, not just "
          "the immediate child PID.")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    run(n)
