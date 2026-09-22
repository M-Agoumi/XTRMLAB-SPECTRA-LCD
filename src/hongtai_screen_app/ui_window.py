"""
ui_window.py -- the "UI process" half of the app: a thin pywebview
window pointed at the backend's own HTTP server (the control API + the
built frontend it serves -- see control_server.py).

Deliberately a SEPARATE process from the backend, spawned fresh every
time (see backend_app.py's _on_show()) rather than a window opened
in-process and hidden/shown -- an early spike measured that destroying
a pywebview/WebView2 window does NOT release its ~90MB overhead within
the same process (it's a one-time, per-process cost). The only way to
actually reclaim that memory when the window closes is to end the
whole process, which is exactly what happens here: webview.start()
blocks until the window is closed, then this process just runs off the
end and exits, taking WebView2's overhead with it -- no explicit
cleanup needed, there's nothing else running in this process.

Reached two ways:
    python scripts/run_ui.py --url http://127.0.0.1:8899/       (source run)
    "Hongtai Screen.exe" --ui --url http://127.0.0.1:8899/      (frozen build,
        spawned by backend_app.py's _on_show() -- see app.py's dispatch)

Needs `pip install pywebview` and a real desktop with WebView2
(Windows) -- there is no headless mode, so this can't be run or
tested from a sandbox with no display at all.
"""
import argparse
import os
import sys

# WebView2's underlying Chromium tries to hardware-accelerate its
# compositor -- in a GPU-less environment (Windows Sandbox, most VMs,
# an RDP/remote-desktop session with no real GPU) that produces a
# solid BLACK window instead of a visible error, which looks exactly
# like a silent failure with nothing in this file's own error handling
# to catch (confirmed by a real test: WebView2 loaded fine, the window
# opened, and stayed black the whole time). WebView2's loader reads
# WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS from the environment and
# appends it verbatim to the underlying Chromium's own command line --
# this is a documented WebView2 mechanism, not a pywebview API, so it
# has to be set before webview.create_window()/webview.start() trigger
# WebView2's environment creation, which is why it's set here at
# import time rather than deeper in main(). --disable-gpu forces
# software rendering, which is plenty for this app's plain HTML/CSS
# dashboard UI and fixes the black-window case unconditionally, at the
# cost of not hardware-accelerating on a real GPU either -- an
# acceptable trade for a small control-panel window, not a game.
# setdefault(), not a plain assignment, so a user/packager who already
# set their own WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS isn't overridden.
os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "--disable-gpu")


def _looks_like_missing_webview2(exc):
    """True if `exc` (whatever webview.create_window()/start() raised)
    looks like the specific "WebView2 Runtime isn't installed" failure
    rather than some other problem. pywebview doesn't expose a
    dedicated exception type for this -- it's whatever the underlying
    edgechromium backend's own init raised, which in practice is a
    plain Exception/OSError whose message mentions the runtime by name
    (seen in the wild as variations on "WebView2 runtime is not
    installed" / "Couldn't find Edge WebView2 Runtime installation").
    Matched loosely on substrings rather than a specific message, since
    the exact wording isn't a stable contract."""
    text = str(exc).lower()
    return "webview2" in text or ("edge" in text and "runtime" in text)


def _show_webview2_missing_message():
    """Best-effort native message box pointing at the download page --
    WebView2 ships with Windows 11 and is normally present on Windows
    10 via Edge, but isn't guaranteed (a stripped-down or LTSC install,
    say), and a bare pywebview stack trace with no console attached
    (this runs via pythonw.exe/frozen, so the person never sees it) is
    indistinguishable from the app silently doing nothing. Windows-only
    (ctypes.windll), same as every other native-UI fallback in this
    app; a no-op everywhere else, and never raises past its own
    try/except -- this is already the failure path, so it must not
    itself fail loudly."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        MB_ICONERROR, MB_OK = 0x10, 0x0
        ctypes.windll.user32.MessageBoxW(
            0,
            "Hongtai Screen needs the Microsoft Edge WebView2 Runtime "
            "to show its window, and couldn't find it on this machine.\n\n"
            "It ships with Windows 11 and is usually already present on "
            "Windows 10 via Edge -- if it's missing, install it from:\n"
            "https://developer.microsoft.com/microsoft-edge/webview2/",
            "Hongtai Screen", MB_ICONERROR | MB_OK)
    except Exception:  # noqa: BLE001 -- best-effort, never fatal
        pass


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

    try:
        window = webview.create_window(args.title, args.url, width=args.width, height=args.height)
    except Exception as e:  # noqa: BLE001 -- see _looks_like_missing_webview2()
        if _looks_like_missing_webview2(e):
            _show_webview2_missing_message()
            raise SystemExit(1)
        raise

    if args.icon:
        # pywebview's own `icon=` on start() only does anything on GTK/Qt
        # (Linux) -- per its docs, on every other platform "icon is set
        # during freezing" i.e. baked into a PyInstaller .exe (see
        # packaging/hongtai_screen.spec's own `icon=`). Running as a
        # plain `python.exe scripts/run_ui.py` from source in the
        # meantime, there's no .exe of ours to bake an icon into, so
        # Windows shows python.exe's own icon in the title bar/taskbar
        # instead. Worked around here the same way single_instance.py
        # already finds another window (by its exact title, via
        # FindWindowW) -- once the window is showing, push the .ico
        # onto it directly with WM_SETICON, which is what both the
        # title bar and the taskbar button actually read. Best-effort
        # and Windows-only; never blocks the window from opening if
        # anything here goes wrong.
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

    # HONGTAI_SCREEN_DEBUG=1 in the environment (inherited from whatever
    # spawned this process -- see backend_app.py's _on_show(), which
    # doesn't strip the environment when it Popen()s this) opens
    # WebView2's DevTools (right-click "Inspect", or F12) instead of the
    # normal no-devtools end-user window. Not exposed as its own CLI
    # flag: this is a debugging aid, not a feature, and an env var
    # means it can be flipped on for one run without a new build --
    # e.g. `$env:HONGTAI_SCREEN_DEBUG=1; & ".\Hongtai Screen.exe"` on a
    # machine where the page is rendering blank/black and the actual
    # browser console error is what's needed to diagnose it.
    debug = bool(os.environ.get("HONGTAI_SCREEN_DEBUG"))

    try:
        webview.start(icon=args.icon, debug=debug) if args.icon else webview.start(debug=debug)
    except TypeError:
        # Older pywebview missing the `icon` and/or `debug` kwarg on
        # start() entirely -- fall back a step at a time rather than
        # straight to the bare call, so `debug` still applies wherever
        # pywebview's own version actually supports it.
        try:
            webview.start(debug=debug)
        except TypeError:
            webview.start()
    except Exception as e:  # noqa: BLE001 -- see _looks_like_missing_webview2()
        if _looks_like_missing_webview2(e):
            _show_webview2_missing_message()
            raise SystemExit(1)
        raise


if __name__ == "__main__":
    main()
