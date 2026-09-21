"""
Phase 0 follow-up -- NOT part of the shipped app. See ../../ROADMAP.md
and README.md in this folder.

The first spike (spike.py) showed something more specific than "does
memory come back": "this process" RSS jumped once on first window
creation (30.9 -> 80.9MB), then held flat around ~101-102MB regardless
of whether the window existed or had just been destroyed. That pattern
-- a one-time jump, then no further movement -- looks like loading the
WebView2 runtime into the process at all (DLLs, COM init) is a
per-process cost paid once, not a per-window cost that destroy()
reclaims. This script checks that theory two ways:

  cycles  -- automates 12 open/destroy cycles back to back (no manual
             clicking) and prints RSS after each one. If it's a one-time
             load cost, RSS should jump early then flatten out. If it's
             a real per-cycle leak, it keeps climbing.

  control -- opens ONE window and never destroys it, sampling RSS every
             5s for a minute. If the steady-state number here lands
             close to the ~101-102MB the first spike settled at even
             WITHOUT ever destroying anything, that confirms the cost
             is about the runtime being loaded, not about specific
             window instances piling up.

Setup (same venv as spike.py is fine):

    python spike_followup.py cycles [N]     # default N=12
    python spike_followup.py control [SECONDS]   # default 60

As with spike.py: written against pywebview's documented APIs, not
verified on a real machine by me. The looping create/destroy pattern
did work in your run of spike.py for 2 cycles already, so this is the
same mechanism extended to more cycles -- if it breaks partway through,
paste the console output and traceback and it'll get fixed.

Report back: the printed RSS history line from whichever mode(s) you
run, plus the "still climbing" / "flat" verdict cycles mode prints.
"""
import os
import sys
import threading
import time

import psutil
import webview

HTML = """
<!doctype html>
<html><body style="background:#111;color:#0ff;font-family:sans-serif;
             text-align:center;padding-top:50px;margin:0">
  <h2 id="title">spike</h2>
</body></html>
"""


def _webview2_processes():
    """Total RSS across every msedgewebview2.exe process system-wide --
    see spike.py's version of this for why it's checked system-wide
    rather than just processes we spawned."""
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


def _report(label, history):
    proc = psutil.Process(os.getpid())
    our_mb = proc.memory_info().rss / (1024 * 1024)
    wv_count, wv_rss = _webview2_processes()
    wv_mb = wv_rss / (1024 * 1024)
    print(f"{label:28s}  this={our_mb:7.1f}MB   "
          f"msedgewebview2.exe x{wv_count:<2}={wv_mb:7.1f}MB")
    history.append(our_mb)


def _summarize(history):
    print("\nRSS history for 'this process' (MB):",
          [f"{v:.1f}" for v in history])
    if len(history) >= 6:
        prev = sum(history[-6:-3]) / 3
        last = sum(history[-3:]) / 3
        delta = last - prev
        print(f"Last-3 avg: {last:.1f}MB vs prior-3 avg: {prev:.1f}MB "
              f"(delta {delta:+.1f}MB)")
        if delta > 5:
            print("-> Still climbing: looks like real growth, not just "
                  "a one-time load cost. Worth investigating further "
                  "before relying on this architecture.")
        else:
            print("-> Flat: consistent with a one-time runtime-load "
                  "cost rather than a per-cycle leak.")
    else:
        print("(not enough samples for a growth verdict -- run more cycles)")


def run_cycles(n, open_seconds=1.0, settle_seconds=2.0):
    history = []
    _report("baseline", history)

    for i in range(n):
        window = webview.create_window(
            f"cycle {i + 1}/{n}", html=HTML, width=380, height=220)
        # Auto-destroy after `open_seconds` instead of waiting for a
        # click -- this is what lets the whole run happen unattended.
        timer = threading.Timer(open_seconds, window.destroy)
        timer.start()
        webview.start()  # blocks until this window is destroyed
        time.sleep(settle_seconds)
        _report(f"after cycle {i + 1}/{n}", history)

    _summarize(history)


def run_control(duration, sample_every=5):
    history = []
    _report("baseline", history)

    window = webview.create_window("control", html=HTML, width=380, height=220)

    def sampler():
        elapsed = 0
        while elapsed < duration:
            time.sleep(sample_every)
            elapsed += sample_every
            _report(f"open +{elapsed}s (never destroyed)", history)
        window.destroy()

    threading.Thread(target=sampler, daemon=True).start()
    webview.start()  # returns once the sampler destroys the window at the end
    _report("after final destroy", history)
    _summarize(history)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "cycles"
    if mode == "cycles":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 12
        print(f"Running {n} open/destroy cycles...\n")
        run_cycles(n)
    elif mode == "control":
        seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        print(f"Opening one window and leaving it for {seconds}s "
              f"(sampled every 5s)...\n")
        run_control(seconds)
    else:
        print("Usage: python spike_followup.py [cycles [N] | control [SECONDS]]")
        sys.exit(1)
