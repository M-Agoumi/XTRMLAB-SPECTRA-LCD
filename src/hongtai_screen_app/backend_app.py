"""
backend_app.py -- the desktop app itself: the control API
(control_server.py, the same server scripts/run_backend.py runs
standalone), a system tray icon, and spawning/killing the separate UI
process (ui_window.py -- see its own docstring for why it has to be a
separate process) when "Show" is clicked.

Desktop shortcuts and the "Launch at Windows startup" entry
(desktop_shortcut.py, startup_registration.py) point at the repo-root
`app.py` (source run) or the packaged .exe (frozen build) -- either
way that's this module's main(), reached via app.py's dispatch or
scripts/run_v2_app.py's CLI shim. The React frontend is the only UI;
there is no other GUI in this app any more.

    python app.py                                    # opens the window immediately
    python app.py --autostart                         # resumes last theme, tray only, no window
    python app.py --autostart --theme video
    python scripts/run_v2_app.py                      # same thing, explicit script form

Needs Windows for the tray icon and the single-instance mutex, and the
UI process needs a real desktop with WebView2 -- none of this is
testable end-to-end from a sandbox with no display, no WebView2 and no
tray daemon. What headless testing can and does cover: BackendApp's
own logic (resume-on-launch, server start/stop, show/quit bookkeeping)
against a stubbed-out tray and a stubbed subprocess spawn.
"""
import argparse
import os
import subprocess
import sys
import threading

from . import config_store
from . import single_instance
from . import tray_icon
from .control_server import DEFAULT_PORT, ControlServer, _make_handler
from .controller import AppController
from .paths import ICON_PATH, SHOW_TRIGGER_PATH, _app_base_dir, _write_startup_log

# Passed explicitly as run_ui.py's --title (rather than relying on its
# own --title default staying "Hongtai Screen" forever) so this same
# string can double as the FindWindowW target in _focus_ui_window()
# below -- see that function's docstring for why a click on the tray
# icon while the window is already open needs this at all.
UI_WINDOW_TITLE = "Hongtai Screen"


class BackendApp:
    """Owns one AppController, one ControlServer, one TrayIcon, and at
    most one live UI subprocess. `_on_show`/`_on_stop_screen`/`_on_quit`
    are handed straight to TrayIcon as its three callbacks -- see
    tray_icon.py's docstring: they run on pystray's own background
    thread, but nothing here touches any UI toolkit at all (the window
    lives entirely in the separate UI process), so there's no "hop back
    to the right thread" step needed."""

    def __init__(self, autostart=False, autostart_theme=None, port=DEFAULT_PORT):
        self.autostart = autostart
        self.port = port
        self.controller = AppController()
        self.server = None
        self._server_thread = None
        self._tray = None
        self._ui_process = None
        self._ui_lock = threading.Lock()
        self.quit_event = threading.Event()
        self._show_watcher_thread = None
        # Baseline reading, not None -- see start_show_watcher(). Reading
        # whatever's already on disk (rather than starting from "never
        # seen it") means a trigger left over from before this instance
        # even started never causes a spurious self-show the moment
        # this instance's own watcher starts -- only a touch that
        # happens *after* this line runs counts as "someone just asked
        # to be shown".
        try:
            self._show_trigger_mtime = os.path.getmtime(SHOW_TRIGGER_PATH)
        except OSError:
            self._show_trigger_mtime = None

        # What should come back up automatically: an explicit --theme
        # always wins; otherwise
        # resume whatever was last actually streaming; --autostart with
        # neither falls back to Dashboard; a plain launch with nothing
        # to resume and no --autostart just starts idle.
        cfg = self.controller.cfg
        auto_resume_tab = cfg.get("auto_resume_tab")
        if autostart_theme in config_store.THEME_TAB_ORDER:
            resume_theme = autostart_theme
        elif auto_resume_tab is not None and 0 <= auto_resume_tab < len(config_store.THEME_TAB_ORDER):
            resume_theme = config_store.THEME_TAB_ORDER[auto_resume_tab]
        elif autostart:
            resume_theme = "dashboard"
        else:
            resume_theme = None

        if autostart:
            _write_startup_log(f"backend_app starting (resume_theme={resume_theme!r})")

        if resume_theme is not None:
            try:
                self.controller.start(theme_name=resume_theme)
            except Exception as e:  # noqa: BLE001 -- never let a bad resume block startup
                if autostart:
                    _write_startup_log(f"backend_app: resume failed: {e}")

    # ------------------------------------------------------------------ #
    # control API
    # ------------------------------------------------------------------ #
    def start_server(self):
        # quit_callback=self._on_quit: lets POST /api/relaunch_elevated
        # (control_server.py) shut this whole process down the exact
        # same way the tray icon's own Quit does -- UI window subprocess
        # killed, engine closed, server stopped -- instead of a bare
        # os._exit() that skipped all of that and left the UI window an
        # orphan (see controller.py's relaunch_elevated() docstring).
        handler = _make_handler(self.controller, quit_callback=self._on_quit)
        self.server = ControlServer(("127.0.0.1", self.port), handler)
        self._server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._server_thread.start()

    # ------------------------------------------------------------------ #
    # tray icon
    # ------------------------------------------------------------------ #
    def start_tray(self):
        """Returns False (not fatal) if a tray icon can't be started at
        all here -- a nice-to-have, not required to run. Logs *why*
        (missing pystray, wrong platform, or whatever pystray's own
        init raised) through the controller -- silently returning False
        here made a failed tray indistinguishable from "worked, icon
        just isn't visible" the first time this was tried on the real
        machine."""
        if not tray_icon.available():
            reason = ("not on Windows" if sys.platform != "win32"
                       else "pystray isn't installed (pip install pystray)")
            self.controller._log(f"(no system tray icon: {reason})")
            return False
        self._tray = tray_icon.TrayIcon(self._on_show, self._on_stop_screen, self._on_quit)
        try:
            self._tray.start()
        except Exception as e:  # noqa: BLE001
            self.controller._log(f"(couldn't start the system tray icon: {e})")
            self._tray = None
            return False
        return True

    # ------------------------------------------------------------------ #
    # "show yourself" watcher -- for a second launch while already running
    # ------------------------------------------------------------------ #
    def start_show_watcher(self):
        """See single_instance.py's _bring_existing_window_to_front()
        for the other half of this. Double-clicking the desktop icon
        (or the .lnk) while this is already running -- the single most
        common way that happens, since the desktop icon and "Launch at
        Windows startup" both point here -- touches SHOW_TRIGGER_PATH's
        mtime; single_instance.py's own FindWindowW attempt is a no-op
        for this process (the window it looks for lives in the separate
        UI process, not this one), so this watcher is what actually
        makes a second launch do something useful: it notices the
        touched file within one poll tick and calls _on_show(), the
        exact same thing the tray icon's own "Show" menu item does.

        A plain daemon thread with a sleep loop -- this process has no
        UI event loop to ride. `self.quit_event.wait(...)` doubles as
        the sleep and as an immediate wakeup on shutdown, so this
        thread doesn't linger or delay process exit."""
        def _watch():
            while not self.quit_event.is_set():
                try:
                    mtime = os.path.getmtime(SHOW_TRIGGER_PATH)
                except OSError:
                    mtime = None
                if mtime is not None and mtime != self._show_trigger_mtime:
                    self._show_trigger_mtime = mtime
                    self._on_show()
                self.quit_event.wait(0.2)
        self._show_watcher_thread = threading.Thread(target=_watch, daemon=True)
        self._show_watcher_thread.start()

    # ------------------------------------------------------------------ #
    # UI process spawn/kill
    # ------------------------------------------------------------------ #
    def _ui_process_command(self):
        """The argv to spawn the UI process with. Two cases, because a
        frozen build is one single .exe with no separate run_ui.py
        script sitting alongside it to point an interpreter at:

        - Frozen (`sys.frozen`): re-invoke this same .exe
          (`sys.executable`) with `--ui` -- app.py's dispatch (see its
          own docstring) is what tells that freshly spawned copy of
          itself to run the window half instead of the backend half.
        - Source run: `sys.executable` is a real Python interpreter, so
          it's pointed at scripts/run_ui.py directly, same as any other
          script under scripts/. `_app_base_dir()` (paths.py) is
          anchored on this package's own location, so it resolves to
          the repo root regardless of which script started this
          process."""
        url = f"http://127.0.0.1:{self.port}/"
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--ui", "--url", url, "--title", UI_WINDOW_TITLE]
        else:
            script = os.path.join(_app_base_dir(), "scripts", "run_ui.py")
            cmd = [sys.executable, script, "--url", url, "--title", UI_WINDOW_TITLE]
        if os.path.isfile(ICON_PATH):
            cmd += ["--icon", ICON_PATH]
        return cmd

    def _on_show(self):
        """Spawns the UI process if none is currently alive; if one
        already is, brings its window to the front instead of doing
        nothing.

        An earlier version deliberately skipped refocusing here ("it's
        already open" was judged enough) -- a real report from actually
        using the tray icon day to day disagreed: clicking "Show
        window" while the window was already open but sitting behind
        another one visibly did nothing, which reads as the tray icon
        being broken rather than as "it was already open, nothing to
        do" (the two look identical to someone who can't see the
        window either way). Fixed via _focus_ui_window() -- same
        FindWindowW + SetForegroundWindow mechanism single_instance.py
        already uses for the second-launch case, pointed at the webview
        window's title instead."""
        with self._ui_lock:
            if self._ui_process is not None and self._ui_process.poll() is None:
                self._focus_ui_window()
                return
            try:
                self._ui_process = subprocess.Popen(self._ui_process_command())
            except Exception as e:  # noqa: BLE001 -- surfaced in the log either way
                self.controller._log(f"(couldn't open the UI window: {e})")

    def _focus_ui_window(self):
        """Best-effort: brings the already-open UI window to the front
        and restores it if minimized. Windows-only (ctypes.windll);
        a no-op everywhere else, same as every other Windows-specific
        feature in this file.

        FindWindowW matches on the exact window title (UI_WINDOW_TITLE,
        passed to run_ui.py's --title above) regardless of whether the
        window is minimized, behind another window, or simply not the
        foreground app -- exactly the case that was reported ("under
        another window", so still open and not minimized, just not on
        top). SetForegroundWindow is still best-effort: Windows
        restricts which processes may steal foreground focus from
        whatever the user is currently looking at, and a call from a
        background process like this one can be silently ignored (the
        window raises in the taskbar but doesn't actually come to
        the front) with no reliable way to detect that from here --
        same caveat single_instance.py's own use of this documents.
        Logged either way so a report of "still doesn't come up" is
        diagnosable from the app's own Log panel instead of a guess."""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, UI_WINDOW_TITLE)
            if not hwnd:
                self.controller._log(
                    "(show: UI window process is alive but its window "
                    "couldn't be found by title -- not focusing)")
                return
            SW_RESTORE = 9
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
            self.controller._log("(show: brought the already-open window to the front)")
        except Exception as e:  # noqa: BLE001 -- best-effort, never fatal
            self.controller._log(f"(show: couldn't focus the already-open window: {e})")

    def _on_stop_screen(self):
        self.controller.stop()

    def _on_quit(self):
        self.shutdown()
        self.quit_event.set()

    # ------------------------------------------------------------------ #
    # shutdown
    # ------------------------------------------------------------------ #
    def shutdown(self):
        with self._ui_lock:
            if self._ui_process is not None and self._ui_process.poll() is None:
                self._ui_process.terminate()
        self.controller.close()
        if self.server is not None:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:  # noqa: BLE001 -- best-effort on the way out
                pass


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--autostart", action="store_true",
                     help="start hidden/tray-only and resume whatever theme was last "
                          "running (or Dashboard if nothing was) -- for a Windows "
                          "Startup-folder launch, not manual use")
    ap.add_argument("--theme", choices=config_store.THEME_TAB_ORDER, default=None,
                     help="force a specific tab for --autostart, instead of resuming")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = ap.parse_args(argv)

    if not single_instance._ensure_single_instance():
        return

    app = BackendApp(autostart=args.autostart, autostart_theme=args.theme, port=args.port)
    app.start_server()
    # Through the controller's own _log() (visible in the web UI's Log
    # panel, and mirrored to STARTUP_LOG_PATH for --autostart), not
    # print(): this is launched via pythonw.exe (or the frozen .exe)
    # with no console attached once it's what the desktop icon points
    # at, where a bare print() either goes nowhere or can raise
    # outright with no console streams to write to. A manual `python
    # app.py` from a terminal loses console echo of these two lines as
    # a result, but gets everything else the same way (stdout when run
    # manually anyway, the Log panel once the window's open).
    startup_msg = f"Control API listening on http://127.0.0.1:{args.port}/ (localhost only)"
    app.controller._log(startup_msg)
    have_tray = app.start_tray()
    app.controller._log(
        "System tray icon: started" if have_tray else
        "System tray icon: NOT started -- see the Log panel above for why")
    if args.autostart:
        _write_startup_log(startup_msg)
        _write_startup_log("System tray icon: started" if have_tray else
                            "System tray icon: NOT started")
    app.start_show_watcher()

    # A plain launch opens the window right away. --autostart starts
    # hidden UNLESS there's no tray to bring it back with later, in
    # which case showing it anyway beats running invisibly forever.
    if not args.autostart or not have_tray:
        app._on_show()

    try:
        app.quit_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        app.shutdown()


if __name__ == "__main__":
    main()
