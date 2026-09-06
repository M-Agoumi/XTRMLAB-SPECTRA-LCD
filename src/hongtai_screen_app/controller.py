"""
controller.py -- AppController: the same start/stop/apply/config logic
the Tkinter App class drives (see app.py), with no Tkinter dependency
at all. Built for control_server.py's HTTP API (ROADMAP.md Phase 2),
and the shape the eventual webview UI's backend is meant to run on.

The Tkinter app is NOT wired to this yet -- it keeps its own inline
copy of this logic for now (see theme_kwargs.py's docstring for why).
This class is additive: a second, independent way to drive the same
underlying modules (config_store, ThemeWorker, theme_kwargs, the
driver), fully headless and fully testable without a display.
"""
import queue
import sys
import threading
import time
from collections import deque

from . import config_store
from . import desktop_shortcut
from . import startup_registration
from . import theme_kwargs
from .driver import hongtai_screen
from .theme_worker import ThemeWorker


class AppController:
    """One process's worth of "what's running, what's configured, what
    just got logged" -- everything a UI (HTTP API today, a webview
    frontend eventually) needs to drive the app without any of them
    touching a ThemeWorker or the driver directly.

    Thread-safety: every public method takes `_lock` internally, so
    this is safe to call concurrently from multiple HTTP handler
    threads (ThreadingHTTPServer spins one thread per connection).
    """

    LOG_HISTORY = 400          # lines an SSE client catches up on when it connects
    WATCH_INTERVAL = 0.5        # seconds between "did the worker finish?" checks

    def __init__(self):
        self.cfg = config_store.load_config()
        self._lock = threading.RLock()
        self.worker = None
        self.stop_event = None
        self.running_theme = None      # display name, e.g. "Dashboard"
        self.active_screen = None      # set via on_connected once connect() succeeds
        self._pending_restart = False  # set by apply(); consumed once the
                                        # worker it told to stop actually winds down
        self._log_history = deque(maxlen=self.LOG_HISTORY)
        self._log_subscribers = []     # list of queue.Queue, one per SSE client
        self._closed = False

        self._watch_thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._watch_thread.start()

    # ------------------------------------------------------------------ #
    # logging / pub-sub -- ThemeWorker calls this exactly like the
    # Tkinter app's self._log does; SSE clients get every line pushed to
    # them live, plus the last LOG_HISTORY lines on first connect.
    # ------------------------------------------------------------------ #
    def _log(self, msg):
        msg = str(msg)
        with self._lock:
            self._log_history.append(msg)
            subs = list(self._log_subscribers)
        for q in subs:
            q.put(msg)

    def subscribe_log(self):
        q = queue.Queue()
        with self._lock:
            for line in self._log_history:
                q.put(line)
            self._log_subscribers.append(q)
        return q

    def unsubscribe_log(self, q):
        with self._lock:
            if q in self._log_subscribers:
                self._log_subscribers.remove(q)

    # ------------------------------------------------------------------ #
    # state / config
    # ------------------------------------------------------------------ #
    def state(self):
        with self._lock:
            screen = self.active_screen
            return {
                "running_theme": self.running_theme,
                "worker_alive": self.worker.is_alive() if self.worker is not None else False,
                "port": self.cfg.get("port", config_store.AUTO_DETECT),
                "brightness": self.cfg.get("brightness", 90),
                "active_tab": self.cfg.get("active_tab", 0),
                "connected": screen is not None,
                "screen_info": self._screen_info(screen) if screen is not None else None,
            }

    @staticmethod
    def _screen_info(screen):
        info = getattr(screen, "info", None)
        if info is None:
            return None
        return {
            "width": info.width, "height": info.height,
            "version": info.version, "model": info.model, "uid": info.uid,
        }

    def get_config(self):
        with self._lock:
            return dict(self.cfg)

    def update_config(self, patch: dict):
        """Shallow-merges `patch` into the config and saves it -- same
        "last write wins, per top-level key" shape app_config.json
        already has (e.g. a `dashboard` patch replaces the whole
        `dashboard` sub-dict, matching how the Tkinter app's own
        _save_current_config() writes it)."""
        if not isinstance(patch, dict):
            raise ValueError("config patch must be a JSON object")
        with self._lock:
            self.cfg.update(patch)
            config_store.save_config(self.cfg)
            return dict(self.cfg)

    def set_brightness(self, value):
        """Brightness is special-cased instead of going through
        update_config(): app.py's own slider applies it *live*, with no
        restart, by calling screen.set_brightness() directly on the
        running HongtaiScreen the moment the slider moves (it's just a
        per-frame software dim -- see the driver's set_brightness()
        docstring -- so there's nothing to reconnect). A generic config
        patch only takes effect on the next Start/Apply, which would
        make the web UI's brightness slider feel broken by comparison
        (dial it down, nothing visibly happens until you restart the
        theme). This does both: persists the new value to
        app_config.json like any other setting, AND, if a screen is
        currently connected, pushes it to the panel immediately."""
        try:
            value = max(0, min(100, int(value)))
        except (TypeError, ValueError):
            raise ValueError(f"brightness must be a number 0-100, got {value!r}")
        with self._lock:
            self.cfg["brightness"] = value
            config_store.save_config(self.cfg)
            screen = self.active_screen
        if screen is not None:
            try:
                screen.set_brightness(value)
            except Exception as e:  # noqa: BLE001 -- surfaced in the log either way
                self._log(f"(brightness change failed: {e})")
        return {"brightness": value}

    # ------------------------------------------------------------------ #
    # Windows integration -- "Launch at Windows startup" / desktop
    # shortcut. Thin wrappers around startup_registration.py/
    # desktop_shortcut.py (Phase 1's extraction already made these
    # Tkinter-independent); routed through here rather than called
    # directly from control_server.py so every controller action is
    # logged/handled the same way, and so a future caller other than
    # the HTTP API (a future in-process UI, say) gets the same surface.
    # ------------------------------------------------------------------ #
    def system_info(self):
        return {
            "platform": sys.platform,
            "startup_supported": sys.platform == "win32",
            "startup_enabled": startup_registration.is_startup_enabled(),
        }

    def set_startup(self, enabled):
        if enabled:
            startup_registration.enable_startup()
        else:
            startup_registration.disable_startup()
        return self.system_info()

    def create_desktop_shortcut(self):
        """Raises on failure (non-Windows, no Desktop folder, cscript
        error) -- same as desktop_shortcut.create_desktop_shortcut()
        itself; control_server.py's do_POST already turns a RuntimeError
        into a 400 with the message intact."""
        return {"path": desktop_shortcut.create_desktop_shortcut()}

    def _selected_port(self):
        """app_config.json's "port" is a human-readable *label* (e.g.
        "COM3  (VID 33C3:7804 -- ...)  USB Serial Device (COM3)"), not
        an openable device path -- see ScreenPort.label in the driver.
        app.py's own _selected_port() never opens that string directly
        either: it rescans find_hongtai_ports() and looks up the
        matching candidate's real .device (e.g. "COM3") by comparing
        labels, because the only thing worth persisting across restarts
        is *which physical port the user picked*, not a device name
        that can shift across reboots/replugs. This does the same
        lookup, so a saved selection behaves identically whether it's
        driven from the Tkinter GUI or this headless controller.

        Returns None (auto-detect) if the saved label doesn't match any
        port currently plugged in -- same fallback app.py's
        _refresh_ports() does when the saved selection isn't in the
        current port list any more."""
        label = self.cfg.get("port", config_store.AUTO_DETECT)
        if not label or label == config_store.AUTO_DETECT:
            return None
        for candidate in hongtai_screen.find_hongtai_ports():
            if candidate.label == label:
                return candidate.device
        self._log(
            f"(saved port selection {label!r} doesn't match any port "
            f"plugged in right now -- falling back to auto-detect)"
        )
        return None

    # ------------------------------------------------------------------ #
    # start / stop / apply -- mirrors app.py's _on_start()/_on_stop()/
    # _on_apply()/_on_theme_finished(), minus every Tk widget touch.
    # ------------------------------------------------------------------ #
    def start(self, theme_name=None):
        with self._lock:
            if self.worker is not None and self.worker.is_alive():
                raise RuntimeError("already running -- stop it first")

            if theme_name is None:
                idx = self.cfg.get("active_tab", 0)
                if not (0 <= idx < len(config_store.THEME_TAB_ORDER)):
                    idx = 0
                theme_name = config_store.THEME_TAB_ORDER[idx]
            elif theme_name not in config_store.THEME_TAB_ORDER:
                raise ValueError(
                    f"Unknown theme {theme_name!r} -- expected one of "
                    f"{config_store.THEME_TAB_ORDER}")

            port = self._selected_port()
            brightness = self.cfg.get("brightness", 90)
            label, target, kwargs = theme_kwargs.build(theme_name, self.cfg, port, brightness)

            stop_event = threading.Event()
            kwargs["stop_event"] = stop_event
            kwargs["log"] = self._log
            kwargs["on_connected"] = self._on_screen_connected

            self.stop_event = stop_event
            self.running_theme = label
            self.active_screen = None
            self.cfg["active_tab"] = config_store.THEME_TAB_ORDER.index(theme_name)
            self.cfg["auto_resume_tab"] = self.cfg["active_tab"]
            config_store.save_config(self.cfg)

            self.worker = ThemeWorker(target, kwargs, self._log)
            self.worker.start()
            return {"running_theme": label}

    def _on_screen_connected(self, screen):
        with self._lock:
            self.active_screen = screen
        screen.enable_frame_capture()

    def stop(self):
        with self._lock:
            if self.stop_event is not None:
                self.stop_event.set()
            self.cfg["auto_resume_tab"] = None
            config_store.save_config(self.cfg)

    def apply(self):
        """One call instead of stop-then-notice-it-stopped-then-start --
        same one-click restart the Tkinter app's Apply button does.
        Stops whatever's running; _watch_loop() below starts it back up
        again, with whatever the config currently says, once the worker
        it told to stop has actually wound down."""
        with self._lock:
            if self.worker is None or not self.worker.is_alive():
                raise RuntimeError("nothing running to restart -- use start() instead")
            self._pending_restart = True
        self.stop()

    # ------------------------------------------------------------------ #
    # background watcher -- the non-Tk equivalent of app.py's
    # _poll_log_queue() noticing self.worker died and calling
    # _on_theme_finished(). Runs for this controller's whole lifetime.
    # ------------------------------------------------------------------ #
    def _watch_loop(self):
        while True:
            time.sleep(self.WATCH_INTERVAL)
            with self._lock:
                if self._closed:
                    return
                worker = self.worker
                if worker is None or worker.is_alive():
                    continue
                # The worker thread finished on its own (Stop was called,
                # a video ended without --loop, a connection error ran
                # out of recovery attempts, ...) -- reset state exactly
                # like app.py's _on_theme_finished().
                self.worker = None
                self.stop_event = None
                self.running_theme = None
                self.active_screen = None
                if self.cfg.get("auto_resume_tab") is not None and not self._pending_restart:
                    # Ended on its own rather than via an explicit Stop
                    # (which already cleared auto_resume_tab itself) --
                    # nothing is actually running any more to resume.
                    self.cfg["auto_resume_tab"] = None
                    config_store.save_config(self.cfg)
                restart = self._pending_restart
                self._pending_restart = False
            if restart:
                time.sleep(0.3)  # let the OS fully release the serial port first
                try:
                    self.start()
                except Exception as e:  # noqa: BLE001 -- surfaced in the log either way
                    self._log(f"(restart after Apply failed: {e})")

    def close(self):
        """Stops the watcher thread and unblocks any open SSE
        subscribers -- call this when shutting the whole process down
        (see control_server.py's shutdown handling)."""
        with self._lock:
            self._closed = True
            if self.stop_event is not None:
                self.stop_event.set()
            subs = list(self._log_subscribers)
        for q in subs:
            q.put(None)  # sentinel: tells an SSE handler to close its stream
