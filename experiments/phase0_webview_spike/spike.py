"""
Phase 0 spike -- NOT part of the shipped app. See ../../ROADMAP.md.

Answers one question with real numbers: when a pywebview/WebView2
window is destroyed (not just hidden) on minimize-to-tray, does the
memory actually come back, and how long does re-opening take?

This can only be run and measured on the real target machine (Windows,
real WebView2) -- there's no way to test this from a Linux sandbox, so
this script is written against pywebview's documented APIs but hasn't
been run by me. If it errors out or behaves oddly, paste the exact
console output/traceback back and I'll fix it -- same as every other
Windows-only bug in this project so far.

Setup (a throwaway venv is fine, doesn't need to touch the real app's
environment):

    pip install pywebview pystray psutil pillow
    python spike.py

What to do once it's running:
  1. A small window opens. Note the "window shown after Xs" line.
  2. Click "Minimize to tray" in the window.
  3. Watch the printed RAM numbers over the next ~10s.
  4. Right-click the tray icon (a cyan dot) -> Show. Time how long it
     takes for the window to visibly reappear -- the console also
     prints a fresh "window shown after Xs" line for this.
  5. Repeat step 2-4 a couple more times if you like, then Quit from
     the tray icon.

Report back: the four sets of RAM numbers it prints (baseline, window
open, right after destroy, 10s after destroy) and the reopen timings.
That directly answers Phase 0's go/no-go question.
"""
import os
import threading
import time

import psutil
import pystray
import webview
from PIL import Image, ImageDraw

_show_event = threading.Event()
_quit_event = threading.Event()
_window = None


def _webview2_processes():
    """Total RSS across every msedgewebview2.exe process system-wide.

    WebView2 can share a single "browser process" across multiple host
    apps (or keep it briefly alive for fast relaunch), so checking only
    "processes spawned by us" could hide the real answer -- this counts
    every WebView2 process running on the machine, which is the honest
    (if slightly pessimistic, if something else on the machine also
    uses WebView2) number.
    """
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


def _report(label):
    proc = psutil.Process(os.getpid())
    our_mb = proc.memory_info().rss / (1024 * 1024)
    wv_count, wv_rss = _webview2_processes()
    wv_mb = wv_rss / (1024 * 1024)
    print(f"\n=== {label} ===")
    print(f"  this process:              {our_mb:7.1f} MB")
    print(f"  msedgewebview2.exe x{wv_count:<2}:    {wv_mb:7.1f} MB")
    print(f"  TOTAL:                     {our_mb + wv_mb:7.1f} MB")


HTML = """
<!doctype html>
<html>
<body style="background:#111;color:#0ff;font-family:sans-serif;
             text-align:center;padding-top:40px;margin:0">
  <h2>Phase 0 spike</h2>
  <p>If you can see this, WebView2 rendered the page.</p>
  <p id="clock" style="font-size:32px"></p>
  <button onclick="window.pywebview.api.minimize_to_tray()"
          style="font-size:18px;padding:10px 20px;cursor:pointer">
    Minimize to tray
  </button>
  <script>
    setInterval(() => {
      document.getElementById('clock').textContent =
        new Date().toLocaleTimeString();
    }, 1000);
  </script>
</body>
</html>
"""


class Api:
    def minimize_to_tray(self):
        # This call comes in on the webview's own thread -- hand the
        # actual destroy() off to a fresh thread so this call can
        # return cleanly first, rather than destroying the window out
        # from under the call that's currently running on it.
        threading.Thread(target=_destroy_current_window, daemon=True).start()
        return "ok"


def _destroy_current_window():
    global _window
    time.sleep(0.05)
    if _window is not None:
        _window.destroy()


def _make_tray_icon():
    img = Image.new("RGB", (64, 64), "black")
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, 56, 56), fill=(0, 200, 200))

    def on_show(icon, item):
        _show_event.set()

    def on_quit(icon, item):
        _quit_event.set()
        _show_event.set()  # wake the main loop so it notices quit and exits
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Show", on_show, default=True),
        pystray.MenuItem("Quit", on_quit),
    )
    return pystray.Icon("phase0spike", img, "Phase 0 Spike", menu)


def main():
    global _window

    icon = _make_tray_icon()
    threading.Thread(target=icon.run, daemon=True).start()

    _report("baseline (before any window)")

    while not _quit_event.is_set():
        _show_event.clear()
        t0 = time.time()

        _window = webview.create_window(
            "Phase 0 Spike", html=HTML, js_api=Api(), width=500, height=350)

        def _after_shown():
            print(f"\nWindow shown after {time.time() - t0:.2f}s")
            _report("window open")

        # webview.start() blocks until every window has been closed or
        # destroyed, then returns -- this loop relies on that to
        # recreate a fresh window each time "Show" is clicked. This is
        # the one part of pywebview's behavior I can't verify without
        # running it; if the second create_window()/start() cycle
        # misbehaves, that's exactly the kind of thing to paste back.
        webview.start(func=_after_shown)

        _window = None
        _report("window destroyed (just now)")
        print("Waiting 10s before re-checking "
              "(giving WebView2 processes time to actually exit) ...")
        time.sleep(10)
        _report("10s after destroy")

        if _quit_event.is_set():
            break

        print("\nWaiting for 'Show' from the tray icon "
              "(or 'Quit' to exit the spike)...")
        _show_event.wait()

    icon.stop()
    print("\nSpike finished.")


if __name__ == "__main__":
    main()
