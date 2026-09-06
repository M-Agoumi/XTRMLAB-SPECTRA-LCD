"""
backend_app.py -- the always-running v2.0 backend process (ROADMAP.md
Phase 2c): the control API (control_server.py, the same server
scripts/run_backend.py runs standalone), a system tray icon, and
spawning/killing the separate UI process (scripts/run_ui.py -- see its
own docstring for why it has to be a separate process) when "Show" is
clicked.

This is the shape the v2.0 architecture describes -- app.py (the
Tkinter GUI) is untouched and still the currently-shipped way to run
this app. This is a parallel, not-yet-wired-up entry point for
exercising the real two-process design end to end; nothing switches
over to it until ROADMAP.md's Phase 7 (packaging/cutover).

    python scripts/run_v2_app.py                    # opens the window immediately
    python scripts/run_v2_app.py --autostart         # resumes last theme, tray only, no window
    python scripts/run_v2_app.py --autostart --theme video

Needs Windows for the tray icon and the single-instance mutex, and the
UI process needs a real desktop with WebView2 -- none of this is
testable end-to-end from a sandbox with no display, no WebView2 and no
tray daemon. What headless testing can and does cover: BackendApp's
own logic (resume-on-launch, server start/stop, show/quit bookkeeping)
against a stubbed-out tray and a stubbed subprocess spawn -- see the
module's test notes in ROADMAP.md Phase 2c.
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
from .paths import _app_base_dir, _write_startup_log


class BackendApp:
    """Owns one AppController, one ControlServer, one TrayIcon, and at
    most one live UI subprocess. `_on_show`/`_on_stop_screen`/`_on_quit`
    are handed straight to TrayIcon as its three callbacks -- see
    tray_icon.py's docstring: they run on pystray's own background
    thread, but nothing here touches any UI toolkit, so there's no
    "hop back to the right thread" step needed the way app.py's
    Tkinter callbacks require."""

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

        # Same "what should come back up automatically" logic as
        # app.py's App.__init__ (see its docstring/comments around
        # resume_theme): an explicit --theme always wins; otherwise
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
        handler = _make_handler(self.controller)
        self.server = ControlServer(("127.0.0.1", self.port), handler)
        self._server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._server_thread.start()

    # ------------------------------------------------------------------ #
    # tray icon
    # ------------------------------------------------------------------ #
    def start_tray(self):
        """Returns False (not fatal) if a tray icon can't be started at
        all here -- same as app.py's _start_tray(): a nice-to-have, not
        required to run."""
        if not tray_icon.available():
            return False
        self._tray = tray_icon.TrayIcon(self._on_show, self._on_stop_screen, self._on_quit)
        try:
            self._tray.start()
        except Exception:  # noqa: BLE001
            self._tray = None
            return False
        return True

    # ------------------------------------------------------------------ #
    # UI process spawn/kill -- the actual Phase 2c mechanic
    # ------------------------------------------------------------------ #
    def _run_ui_script_path(self):
        # _app_base_dir() (paths.py) is anchored on this package's own
        # location, so it's the repo root regardless of which script
        # started this process -- see paths.py's docstring for why that
        # matters. Under a frozen build this would need its own answer
        # (ROADMAP.md Phase 7's concern, not this phase's).
        return os.path.join(_app_base_dir(), "scripts", "run_ui.py")

    def _on_show(self):
        """Spawns the UI process if none is currently alive. Phase 2c
        deliberately does NOT try to refocus an already-open window --
        with only one entry point (this tray icon) able to trigger a
        Show, "do nothing, it's already open" is enough; a later phase
        can add real refocusing if that turns out to matter in
        practice."""
        with self._ui_lock:
            if self._ui_process is not None and self._ui_process.poll() is None:
                return
            script = self._run_ui_script_path()
            url = f"http://127.0.0.1:{self.port}/"
            try:
                self._ui_process = subprocess.Popen([sys.executable, script, "--url", url])
            except Exception as e:  # noqa: BLE001 -- surfaced in the log either way
                self.controller._log(f"(couldn't open the UI window: {e})")

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
    have_tray = app.start_tray()

    # A plain launch opens the window right away, same as app.py
    # showing its window on a normal (non-autostart) run. --autostart
    # starts hidden UNLESS there's no tray to bring it back with later
    # -- same fallback app.py's own autostart path uses -- in which
    # case showing it anyway beats running invisibly forever.
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
