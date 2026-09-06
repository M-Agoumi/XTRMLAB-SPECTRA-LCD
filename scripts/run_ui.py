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
    ap.add_argument("--icon", default=None,
                     help="path to a .ico for the window/taskbar icon")
    args = ap.parse_args(argv)

    try:
        import webview
    except ImportError:
        print("pywebview isn't installed -- run: pip install pywebview", file=sys.stderr)
        raise SystemExit(1)

    window = webview.create_window(args.title, args.url, width=args.width, height=args.height)

    if args.icon:
        # pywebview's own `icon=` on start() only does anything on GTK/Qt
        # (Linux) -- per its docs, on every other platform "icon is set
        # during freezing" i.e. baked into a PyInstaller .exe (see
        # packaging/hongtai_screen.spec's own `icon=`), which is what
        # ROADMAP.md Phase 7 eventually does. Running as a plain
        # `python.exe script.py` in the meantime, there's no .exe of
        # ours to bake an icon into, so Windows shows python.exe's own
        # icon in the title bar/taskbar instead. Worked around here the
        # same way single_instance.py already finds another window (by
        # its exact title, via FindWindowW) -- once the window is
        # showing, push the .ico onto it directly with WM_SETICON, which
        # is what both the title bar and the taskbar button actually
        # read. Best-effort and Windows-only; never blocks the window
        # from opening if anything here goes wrong.
        def _apply_windows_icon():
            if sys.platform != "win32":
                return
            try:
                import ctypes
                user32 = ctypes.windll.user32
                IMAGE_ICON, LR_LOADFROMFILE = 1, 0x00000010
                WM_SETICON, ICON_SMALL, ICON_BIG = 0x0080, 0, 1
                hwnd = user32.FindWindowW(None, args.title)
                if not hwnd:
                    return
                for icon_slot, size in ((ICON_SMALL, 16), (ICON_BIG, 32)):
                    hicon = user32.LoadImageW(0, args.icon, IMAGE_ICON, size, size, LR_LOADFROMFILE)
                    if hicon:
                        user32.SendMessageW(hwnd, WM_SETICON, icon_slot, hicon)
            except Exception:  # noqa: BLE001 -- cosmetic only, never fatal
                pass

        try:
            window.events.shown += _apply_windows_icon
        except Exception:  # noqa: BLE001 -- older pywebview without .events.shown
            pass

    try:
        webview.start(icon=args.icon) if args.icon else webview.start()
    except TypeError:
        # Older pywebview without the `icon` kwarg on start() at all.
        webview.start()


if __name__ == "__main__":
    main()
