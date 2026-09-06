"""
controller.py -- AppController: the same start/stop/apply/config logic
the Tkinter App class drives (see app.py), with no Tkinter dependency
at all. Built for control_server.py's HTTP API (ROADMAP.md Phase 2),
and the shape the eventual webview UI's backend is meant to run on.

The Tkinter app is NOT wired to this yet -- it keeps its own inline
copy of this logic for now (see theme_kwargs.py's docstring for why),
including its own ThemeWorker-based start/stop. This class is
additive: a second, independent way to drive the same underlying
modules (config_store, theme_kwargs, the driver), fully headless and
fully testable without a display -- and, unlike the Tkinter app, built
on ScreenEngine (screen_engine.py) instead of ThemeWorker, so switching
themes here reuses one persistent connection instead of reconnecting.
"""
import queue
import sys
import threading
from collections import deque

import base64

from . import config_store
from . import desktop_shortcut
from . import image_store
from . import startup_registration
from . import theme_kwargs
from . import weather
from .driver import hongtai_screen
from .screen_engine import ScreenEngine
from .themes import dashboard_theme


class AppController:
    """One process's worth of "what's running, what's configured, what
    just got logged" -- everything a UI (HTTP API today, a webview
    frontend eventually) needs to drive the app without any of them
    touching a ScreenEngine or the driver directly.

    Thread-safety: every public method takes `_lock` internally, so
    this is safe to call concurrently from multiple HTTP handler
    threads (ThreadingHTTPServer spins one thread per connection).
    """

    LOG_HISTORY = 400          # lines an SSE client catches up on when it connects

    def __init__(self):
        self.cfg = config_store.load_config()
        self._lock = threading.RLock()
        self.running_theme = None      # display name, e.g. "Dashboard"
        self.active_screen = None      # set via on_connected once connect() succeeds
        self._log_history = deque(maxlen=self.LOG_HISTORY)
        self._log_subscribers = []     # list of queue.Queue, one per SSE client
        self._closed = False

        # One persistent connection for this controller's whole
        # lifetime (ROADMAP.md's live-theme-switching rewrite) --
        # switching themes reuses it instead of reconnecting; see
        # screen_engine.py's module docstring for the full reasoning.
        self.engine = ScreenEngine(
            log=self._log,
            on_connected=self._on_screen_connected,
            on_disconnected=self._on_screen_disconnected,
            on_finished=self._on_theme_finished,
        )

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
                "worker_alive": self.running_theme is not None,
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

    def upload_dashboard_image(self, filename, data_b64):
        """Saves a browser-picked image (base64-encoded, since a
        browser file input can only hand back the file's *content*, not
        a real filesystem path the way Tkinter's Browse dialog can) into
        this app's own managed image folder (image_store.py) and
        returns its stored path -- the caller then saves THAT path
        through save_dashboard_background()/save_dashboard_now_playing()/
        save_dashboard_elements(), same as if it had been typed in
        directly. Raises ValueError on a missing/invalid `data_b64`, or
        whatever image_store.store_image_bytes() raises for a file
        that's too large or doesn't actually decode as an image."""
        if not data_b64:
            raise ValueError("no image data given")
        try:
            data = base64.b64decode(data_b64, validate=True)
        except Exception as e:  # noqa: BLE001 -- malformed base64
            raise ValueError(f"invalid image data: {e}")
        path = image_store.store_image_bytes(data, filename)
        return {"path": path}

    # ------------------------------------------------------------------ #
    # Dashboard design canvas (ROADMAP.md Phase 5) -- reading/writing
    # dashboard.elements (and named presets of it) gets its own small
    # surface instead of going through the generic update_config(),
    # because update_config()'s per-top-level-key merge would replace
    # the ENTIRE "dashboard" sub-dict on every save -- fine for Phase 3's
    # video/webpage forms (their own top-level keys), but saving just a
    # layout tweak through it would silently wipe out web_port/
    # enable_web/background/slots. These methods merge into the existing
    # "dashboard" dict instead, so the canvas can save a layout without
    # knowing or caring what else is in there.
    # ------------------------------------------------------------------ #
    def dashboard_meta(self):
        """Everything the design canvas needs to initialize itself: the
        layout it would actually render right now (resolved the same
        way dashboard_kwargs() resolves it, so the canvas can never
        drift from what Start/Apply actually renders), the built-in
        default layout to reset to, any saved named presets, and enough
        STAT_DEFS metadata to populate a per-gauge stat picker without
        the frontend needing to import anything from dashboard_theme.py
        itself."""
        with self._lock:
            cfg = dict(self.cfg)
        d = cfg.get("dashboard", {}) or {}
        return {
            "elements": theme_kwargs.resolve_dashboard_elements(cfg),
            "defaults": dashboard_theme.DEFAULT_ELEMENTS,
            "presets": d.get("presets", {}),
            "stats": {
                key: {"label": meta["label"], "title": meta["title"]}
                for key, meta in dashboard_theme.STAT_DEFS.items()
            },
            "background": dict(dashboard_theme.DEFAULT_BACKGROUND, **(d.get("background") or {})),
            "backgroundPresets": dict(dashboard_theme.BACKGROUND_PRESETS),
            "backgroundSchemes": {
                key: {"label": scheme["label"]}
                for key, scheme in dashboard_theme.BACKGROUND_COLOR_SCHEMES.items()
            },
            "nowPlaying": {
                "default_art_path": d.get("default_art_path") or None,
                "not_playing_message": d.get("not_playing_message") or None,
                "default_message": dashboard_theme.DEFAULT_NOT_PLAYING_MESSAGE,
            },
            "middleContent": {
                "value": d.get("middle_content") or "spotify",
                "options": dict(dashboard_theme.MIDDLE_CONTENT_OPTIONS),
                "weather_location": d.get("weather_location") or "",
                "weather_units": d.get("weather_units") or "celsius",
                "weather_unit_options": dict(weather.UNIT_OPTIONS),
            },
        }

    def save_dashboard_elements(self, elements):
        """Persists a new gauge layout -- takes effect on the next
        Start/Apply, same as any other "needs a restart" dashboard
        setting (see build_static_background()'s docstring). Doesn't
        validate element shape beyond "is it a list" -- a malformed
        element just fails loudly inside dashboard_theme.py's own
        render path the next time it's started, same as a bad video
        path or URL does for those themes."""
        if not isinstance(elements, list):
            raise ValueError("elements must be a list")
        with self._lock:
            dashboard_cfg = dict(self.cfg.get("dashboard") or {})
            dashboard_cfg["elements"] = elements
            self.cfg["dashboard"] = dashboard_cfg
            config_store.save_config(self.cfg)
            return dict(self.cfg["dashboard"])

    def save_dashboard_background(self, background):
        """Persists the panel background (preset mode, color scheme,
        and/or custom image path) -- same merge-into-"dashboard" shape
        as save_dashboard_elements(), and the same "needs a restart"
        deal: it's baked into the static background image at Start/
        Apply time (see build_static_background()'s docstring), not
        re-rendered live. Doesn't validate image_path exists or mode/
        scheme are known keys -- dashboard_theme.py already falls back
        to the default background silently if the image can't be
        opened or a key is unrecognized, same tolerance app.py's own
        Tkinter picker has always relied on."""
        if not isinstance(background, dict):
            raise ValueError("background must be an object")
        with self._lock:
            dashboard_cfg = dict(self.cfg.get("dashboard") or {})
            existing = dict(dashboard_cfg.get("background") or {})
            existing.update(background)
            dashboard_cfg["background"] = existing
            self.cfg["dashboard"] = dashboard_cfg
            config_store.save_config(self.cfg)
            return dict(self.cfg["dashboard"]["background"])

    def save_dashboard_now_playing(self, patch):
        """Persists the "nothing playing" placeholder settings -- the
        default album-art image and/or the message shown in place of a
        track title -- same merge-into-"dashboard" shape as
        save_dashboard_background(), but unlike the background these
        two are live settings dashboard_theme.py re-reads every frame
        (see set_default_art_path()/set_not_playing_message()), the
        same way app.py's Tkinter Dashboard tab has always applied them
        as you type, no Stop/Start needed -- so this applies them to
        the running dashboard_theme module immediately too, not just on
        the next Start/Apply. Only `default_art_path`/
        `not_playing_message` keys are meaningful here; anything else
        in `patch` is stored but ignored by the renderer, same
        tolerance every other merge-safe dashboard endpoint has."""
        if not isinstance(patch, dict):
            raise ValueError("patch must be an object")
        with self._lock:
            dashboard_cfg = dict(self.cfg.get("dashboard") or {})
            dashboard_cfg.update(patch)
            self.cfg["dashboard"] = dashboard_cfg
            config_store.save_config(self.cfg)
            result = dict(self.cfg["dashboard"])
        if "default_art_path" in patch:
            dashboard_theme.set_default_art_path(patch.get("default_art_path") or None)
        if "not_playing_message" in patch:
            dashboard_theme.set_not_playing_message(patch.get("not_playing_message"))
        return result

    def save_dashboard_middle_content(self, patch):
        """Persists which content fills the dashboard's middle column
        -- Spotify now-playing (the original, default behavior), the
        weather (weather.py -- free, no API key, just a place name), or
        nothing at all for anyone who wants neither glued to their PC's
        case. Same merge-into-"dashboard" shape and same "applies live
        immediately" deal as save_dashboard_now_playing() -- dashboard_
        theme.py re-reads the current selection every frame and
        weather.py re-reads the current location/units on its own
        background poll loop, so switching this while the Dashboard is
        already running takes effect without a Stop/Start. Only
        `middle_content`/`weather_location`/`weather_units` keys are
        meaningful here; anything else in `patch` is stored but
        ignored, same tolerance every other merge-safe dashboard
        endpoint has."""
        if not isinstance(patch, dict):
            raise ValueError("patch must be an object")
        if "middle_content" in patch and (patch.get("middle_content") or "spotify") not in dashboard_theme.MIDDLE_CONTENT_OPTIONS:
            raise ValueError(f"unknown middle_content: {patch.get('middle_content')!r}")
        with self._lock:
            dashboard_cfg = dict(self.cfg.get("dashboard") or {})
            dashboard_cfg.update(patch)
            self.cfg["dashboard"] = dashboard_cfg
            config_store.save_config(self.cfg)
            result = dict(self.cfg["dashboard"])
        if "middle_content" in patch:
            dashboard_theme.set_middle_content(patch.get("middle_content") or "spotify")
        if "weather_location" in patch:
            weather.set_location(patch.get("weather_location"))
        if "weather_units" in patch:
            weather.set_units(patch.get("weather_units"))
        weather.start_polling()
        return result

    def save_dashboard_preset(self, name, elements):
        name = (name or "").strip()
        if not name:
            raise ValueError("preset name can't be empty")
        if not isinstance(elements, list):
            raise ValueError("elements must be a list")
        with self._lock:
            dashboard_cfg = dict(self.cfg.get("dashboard") or {})
            presets = dict(dashboard_cfg.get("presets") or {})
            presets[name] = elements
            dashboard_cfg["presets"] = presets
            self.cfg["dashboard"] = dashboard_cfg
            config_store.save_config(self.cfg)
            return presets

    def delete_dashboard_preset(self, name):
        with self._lock:
            dashboard_cfg = dict(self.cfg.get("dashboard") or {})
            presets = dict(dashboard_cfg.get("presets") or {})
            presets.pop(name, None)
            dashboard_cfg["presets"] = presets
            self.cfg["dashboard"] = dashboard_cfg
            config_store.save_config(self.cfg)
            return presets

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
    #
    # There is no "already running" guard on start() any more: calling
    # it while another theme is active is exactly what live-switching
    # means, and ScreenEngine.switch() handles interrupting whatever
    # was running and reusing the existing connection for the new one
    # instead of reopening the serial port. See screen_engine.py.
    # ------------------------------------------------------------------ #
    def start(self, theme_name=None):
        with self._lock:
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

            self.running_theme = label
            self.cfg["active_tab"] = config_store.THEME_TAB_ORDER.index(theme_name)
            self.cfg["auto_resume_tab"] = self.cfg["active_tab"]
            config_store.save_config(self.cfg)

        self.engine.switch(label, target, kwargs, port=port)
        return {"running_theme": label}

    def _on_screen_connected(self, screen):
        with self._lock:
            self.active_screen = screen
        screen.enable_frame_capture()

    def _on_screen_disconnected(self):
        """ScreenEngine fully closed the connection -- an explicit
        stop(), a switch/stop racing an in-flight error, or giving up
        after RECOVERY_ATTEMPTS. Whatever the cause, nothing is running
        any more, so there's nothing left to auto-resume on next
        launch either (an explicit stop() already cleared
        auto_resume_tab itself, so this is a no-op in that case)."""
        with self._lock:
            self.active_screen = None
            self.running_theme = None
            if self.cfg.get("auto_resume_tab") is not None:
                self.cfg["auto_resume_tab"] = None
                config_store.save_config(self.cfg)

    def _on_theme_finished(self, label):
        """A theme's run() returned on its own -- e.g. a non-looping
        video reaching its last frame -- rather than being interrupted
        by stop()/switch(). Purely informational (the engine already
        tore the connection down and fired _on_screen_disconnected by
        the time this runs); kept as its own hook so a UI could
        distinguish "finished" from "stopped" in the log if it wanted
        to."""
        self._log(f"{label} finished on its own.")

    def stop(self):
        with self._lock:
            self.cfg["auto_resume_tab"] = None
            config_store.save_config(self.cfg)
        self.engine.stop()

    def apply(self):
        """Re-reads the currently-active theme's settings from config
        and switches to it again -- same one-click "pick up my config
        changes" the Tkinter app's Apply button does. Under the old
        ThemeWorker-per-theme design this meant a full stop+reconnect;
        now it's just another switch() on the same connection, same as
        picking a different theme from the dropdown."""
        with self._lock:
            if self.running_theme is None:
                raise RuntimeError("nothing running to restart -- use start() instead")
            idx = self.cfg.get("active_tab", 0)
            if not (0 <= idx < len(config_store.THEME_TAB_ORDER)):
                idx = 0
            theme_name = config_store.THEME_TAB_ORDER[idx]
        return self.start(theme_name)

    def close(self):
        """Shuts the engine down and unblocks any open SSE
        subscribers -- call this when shutting the whole process down
        (see control_server.py's shutdown handling)."""
        with self._lock:
            self._closed = True
            subs = list(self._log_subscribers)
        self.engine.close()
        for q in subs:
            q.put(None)  # sentinel: tells an SSE handler to close its stream
