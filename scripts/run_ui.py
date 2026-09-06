"""
run_ui.py -- the "UI process" half of ROADMAP.md's Phase 2c: a thin
pywebview window pointed at the backend's own HTTP server (the control
API + the built frontend it serves -- see control_server.py). This is
a standalone script with no import from the hongtai_screen_app package
on purpose: it doesn't need any of the app's logic, only a URL to
point a window at, and keeping it dependency-free keeps pywebview
(and, transitively, WebView2 on Windows) confined to this one process.

Deliberately a SEPARATE process from the backend, spawned fresh every
time (see backend_app.py's _on_show()) rather than a window opened
in-process and hidden/shown -- ROADMAP.md's Phase 0 spike measured
that destroying a pywebview/WebView2 window does NOT release its
~90MB overhead within the same process (it's a one-time, per-process
cost). The only way to actually reclaim that memory when the window
closes is to end the whole process, which is exactly what happens
here: webview.start() blocks until the window is closed, then this
script just runs off the end and exits, taking WebView2's overhead
with it -- no explicit cleanup needed, there's nothing else running in
this process.

    python scripts/run_ui.py --url http://127.0.0.1:8899/

Needs `pip install pywebview` and a real desktop with WebView2
(Windows) -- there is no headless mode, so this can't be run or
tested from a sandbox with no display at all.
"""
import argparse
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True, help="the backend's own URL, e.g. http://127.0.0.1:8899/")
    ap.add_argument("--width", type=int, default=1040)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--title", default="Hongtai Screen")
    args = ap.parse_args(argv)

    try:
        import webview
    except ImportError:
        print("pywebview isn't installed -- run: pip install pywebview", file=sys.stderr)
        raise SystemExit(1)

    webview.create_window(args.title, args.url, width=args.width, height=args.height)
    webview.start()


if __name__ == "__main__":
    main()
