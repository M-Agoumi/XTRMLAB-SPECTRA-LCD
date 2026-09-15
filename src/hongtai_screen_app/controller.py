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
import io
import os
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
from . import power_state
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
        migrated = config_store.migrate_dashboard_elements(self.cfg)
        migrated = config_store.migrate_dashboard_weather_element(self.cfg) or migrated
        migrated = config_store.migrate_strip_redundant_builtin_presets(self.cfg) or migrated
        migrated = config_store.migrate_dashboard_preset_shape(self.cfg) or migrated
        if migrated:
            config_store.save_config(self.cfg)
        self._lock = threading.RLock()
        power_state.set_keep_active_when_locked(self.cfg.get("keep_active_when_locked", True))
        power_state.start_polling()
        self.running_theme = None      # display name, e.g. "Dashboard"
        self.active_screen = None      # set via on_connected once connect() succeeds
        self._log_history = deque(maxlen=self.LOG_HISTORY)
        self._log_subscribers = []     # list of queue.Queue, one per SSE client
        self._closed = False
        # The running threading.Timer for an in-progress dashboard
        # preview (see preview_dashboard_elements()), or None -- tracked
        # so a second preview (or a real Save) can cancel a still-
        # pending revert instead of leaving it to fire later and stomp
        # on whatever's showing by then.
        self._preview_revert_timer = None

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
    def system_info(self, log=None):
        """`log`: pass self._log to have the schtasks /query this runs
        (via startup_registration.is_startup_enabled()) show up in the
        app's own Log panel -- left quiet (the default) for the plain
        polled GET /api/system calls the frontend makes on every page
        load, since logging every one of those would just be noise;
        set_startup() below passes it explicitly, since "did the
        checkbox's action actually take" is exactly the question being
        investigated right after toggling it."""
        with self._lock:
            keep_active = self.cfg.get("keep_active_when_locked", True)
        return {
            "platform": sys.platform,
            "startup_supported": sys.platform == "win32",
            "startup_enabled": startup_registration.is_startup_enabled(log=log or (lambda m: None)),
            "keep_active_when_locked": keep_active,
            "keep_active_supported": power_state.IS_WINDOWS,
        }

    def set_keep_active_when_locked(self, value):
        """Whether a running theme keeps pushing frames to the panel
        while Windows is locked (True, the default -- this app's
        original behavior, before this setting existed) or pauses and
        resumes automatically on unlock (False) -- see power_state.py's
        docstring, and the official XTRM Lab app's own "Keep playing
        when screen is off" setting this mirrors. Applies immediately,
        the same "no restart needed" deal as set_brightness() above,
        since every theme's render loop checks power_state.should_
        pause() itself on every frame rather than a decision baked in
        at Start time."""
        value = bool(value)
        with self._lock:
            self.cfg["keep_active_when_locked"] = value
            config_store.save_config(self.cfg)
        power_state.set_keep_active_when_locked(value)
        power_state.start_polling()
        return {"keep_active_when_locked": value}

    def set_startup(self, enabled):
        """Every step of this -- the exact command registered, the
        exact schtasks.exe invocation and its exit code/stdout/stderr,
        and the re-check right after -- goes through self._log(), so
        it's all sitting in the app's own Log panel afterward rather
        than only a one-line exception message (or, if this succeeds
        but the *effect* still doesn't seem to stick, nothing at all).
        Added after a report that toggling the checkbox "didn't work"
        with no visible error either way -- this makes it possible to
        actually tell apart "schtasks refused" (permissions, policy),
        "schtasks silently didn't do what was asked", and "it worked,
        but something's rendering the result wrong", by reading exactly
        what happened instead of guessing."""
        if enabled:
            startup_registration.enable_startup(log=self._log)
        else:
            startup_registration.disable_startup(log=self._log)
        info = self.system_info(log=self._log)
        self._log(f"(startup: now reports enabled={info['startup_enabled']})")
        return info

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

    def read_dashboard_image(self, path):
        """Returns (bytes, path) for a previously-uploaded/picked image,
        so the web UI's canvas can show the actual picture it just
        stored -- not just its filename -- the moment it's picked,
        without needing Start/Apply or even Save. Only ever reads a
        path already under image_store.IMAGES_DIR (image_store.
        is_managed()): the canvas only ever hands this back a path IT
        was given by upload_dashboard_image()/Tkinter's Browse dialog in
        the first place, never anything the browser typed in itself, but
        this is still the one place a client-supplied filesystem path
        reaches disk, so it's checked regardless. Raises ValueError for
        anything outside that folder or that doesn't exist."""
        if not path or not image_store.is_managed(path):
            raise ValueError("not a managed image path")
        if not os.path.isfile(path):
            raise ValueError("image not found")
        with open(path, "rb") as f:
            return f.read(), path

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
        # The built-ins (dashboard_theme.BUILTIN_DASHBOARD_PRESETS)
        # merged with whatever's actually saved in this config -- see
        # config_store.resolve_dashboard_presets()'s own docstring for
        # why they're not stored in app_config.json at all.
        presets = config_store.resolve_dashboard_presets(cfg)
        return {
            "elements": theme_kwargs.resolve_dashboard_elements(cfg),
            "defaults": dashboard_theme.DEFAULT_ELEMENTS,
            "presets": presets,
            "presetThumbnails": self._dashboard_preset_thumbnails(presets),
            "stats": {
                key: {"label": meta["label"], "title": meta["title"]}
                for key, meta in dashboard_theme.STAT_DEFS.items()
            },
            "background": dict(dashboard_theme.DEFAULT_BACKGROUND, **(d.get("background") or {})),
            "backgroundPresets": dict(dashboard_theme.BACKGROUND_PRESETS),
            # Modes that are a photo, not a tinted procedural draw --
            # "image" (a user's own upload) plus every bundled one
            # (BUNDLED_BACKGROUND_IMAGES) -- so the frontend knows when
            # to hide the "Color scheme" picker (a photo isn't tinted)
            # without having to duplicate that key list itself.
            "backgroundImageModes": ["image", *dashboard_theme.BUNDLED_BACKGROUND_IMAGES.keys()],
            "backgroundSchemes": {
                key: {"label": scheme["label"]}
                for key, scheme in dashboard_theme.BACKGROUND_COLOR_SCHEMES.items()
            },
            "nowPlaying": {
                "default_art_path": d.get("default_art_path") or None,
                "not_playing_message": d.get("not_playing_message") or None,
                "default_message": dashboard_theme.DEFAULT_NOT_PLAYING_MESSAGE,
            },
            "clockFaces": dict(dashboard_theme.CLOCK_FACES),
            "clockAnalogStyles": dict(dashboard_theme.ANALOG_CLOCK_STYLES),
            "clockHourFormats": dict(dashboard_theme.DIGITAL_CLOCK_HOUR_FORMATS),
            # Weather's own location/units now live on its element (see
            # default_weather_element()) -- this is just the unit-name
            # dropdown's options, the same kind of small lookup table
            # clockFaces/clockAnalogStyles/clockHourFormats are for the
            # clock element's property panel.
            "weatherUnitOptions": dict(weather.UNIT_OPTIONS),
        }

    def save_dashboard_elements(self, elements):
        """Persists a new gauge layout and, if the dashboard theme is
        currently running, applies it live -- same "no Stop/Start
        needed" deal as save_dashboard_now_playing() (see
        dashboard_theme.set_pending_dashboard_layout()). It used to only
        take effect on the next Start/Apply, since the layout is baked
        into a static image once for performance (see
        build_static_background()'s docstring); the running render loop
        now rebakes with the new elements on its very next frame
        instead, which is also what fixed the design canvas visibly
        showing an element at its new position while the real panel
        kept showing it at the old one. Doesn't validate element shape
        beyond "is it a list" -- a malformed element just fails loudly
        inside dashboard_theme.py's own render path, same as a bad
        video path or URL does for those themes."""
        if not isinstance(elements, list):
            raise ValueError("elements must be a list")
        with self._lock:
            # A real Save makes `elements` the new source of truth, so
            # any still-pending preview revert (see
            # preview_dashboard_elements()) would otherwise fire later
            # and stomp this save back to whatever was saved *before*
            # it, undoing it from underneath the user a few seconds
            # after they saved.
            if self._preview_revert_timer is not None:
                self._preview_revert_timer.cancel()
                self._preview_revert_timer = None
            dashboard_cfg = dict(self.cfg.get("dashboard") or {})
            dashboard_cfg["elements"] = elements
            self.cfg["dashboard"] = dashboard_cfg
            config_store.save_config(self.cfg)
            dashboard_theme.set_pending_dashboard_layout(elements=elements)
            # A `weather` element's location/units (see
            # default_weather_element()) are the one per-element field
            # that isn't purely cosmetic -- they drive weather.py's
            # shared background poll, so this needs its own live-apply
            # here too, same "no Stop/Start" deal as the layout/
            # background themselves. dashboard_theme.run()'s pending-
            # layout loop does the same thing for a layout edit made
            # while a different config-writer (app.py) is what's
            # actually driving the running theme.
            dashboard_theme.apply_weather_from_elements(elements)
            return dict(self.cfg["dashboard"])

    def preview_dashboard_elements(self, elements, duration=5.0):
        """Shows `elements` live on the running dashboard theme for
        `duration` seconds, then reverts to whatever's actually saved --
        the design canvas's "Preview on screen" button, for trying an
        edit on the real panel without committing to it the way Save
        layout does. Reuses the exact same live-apply path
        save_dashboard_elements() uses (set_pending_dashboard_layout(),
        picked up by the render loop's next frame), just without ever
        touching self.cfg or config_store -- so if nothing else happens,
        the running theme quietly goes back to the last real Save on its
        own, and a page reload (which reads self.cfg, never the pending
        layout) was never showing anything different in the first
        place.

        A no-op-looking call when the dashboard theme isn't actually
        running is intentional, not an error: set_pending_dashboard_layout()
        already handles "nothing's listening for this right now" by just
        queuing it, and there being no live panel to preview against
        isn't something the caller needs to special-case here -- the
        design canvas itself is what decides whether to offer this
        button based on whether the dashboard's running.

        A second preview call (or a real Save) before the timer fires
        cancels/replaces the pending revert rather than letting both
        timers eventually fire -- otherwise an earlier preview's revert
        could land after a *later* preview or a real save and stomp
        either one back to a stale "saved" snapshot taken before it."""
        if not isinstance(elements, list):
            raise ValueError("elements must be a list")
        with self._lock:
            if self._preview_revert_timer is not None:
                self._preview_revert_timer.cancel()
                self._preview_revert_timer = None
            dashboard_theme.set_pending_dashboard_layout(elements=elements)
            # Snapshotted now (not re-read from self.cfg inside the
            # timer callback) so a Save that lands *during* the preview
            # window still reverts to what was saved before THIS
            # preview started, not whatever the save changed it to --
            # save_dashboard_elements() already cancels this timer
            # outright in that case, but keeping the snapshot self-
            # contained means this method's behavior doesn't depend on
            # that ordering to stay correct.
            saved_elements = list(
                (self.cfg.get("dashboard") or {}).get("elements") or dashboard_theme.DEFAULT_ELEMENTS
            )
            timer = threading.Timer(max(0.5, float(duration)), self._revert_dashboard_preview, args=(saved_elements,))
            timer.daemon = True
            self._preview_revert_timer = timer
            timer.start()

    def _revert_dashboard_preview(self, saved_elements):
        """Timer callback for preview_dashboard_elements() above --
        hands the running theme back whatever was actually saved before
        the preview started. Clears self._preview_revert_timer first so
        a save/preview racing this exact moment doesn't cancel a timer
        object that's already done firing (Timer.cancel() on an already-
        fired timer is harmless, but leaving the stale reference around
        would make a later check think a revert is still pending when
        it's not)."""
        with self._lock:
            self._preview_revert_timer = None
            dashboard_theme.set_pending_dashboard_layout(elements=saved_elements)

    def save_dashboard_background(self, background):
        """Persists the panel background (preset mode, color scheme,
        and/or custom image path) -- same merge-into-"dashboard" shape
        and same live-apply behavior as save_dashboard_elements() just
        above (it's baked into the same static image, so it rebakes
        alongside any pending elements change on the running theme's
        next frame). Doesn't validate image_path exists or mode/scheme
        are known keys -- dashboard_theme.py already falls back to the
        default background silently if the image can't be opened or a
        key is unrecognized, same tolerance app.py's own Tkinter picker
        has always relied on."""
        if not isinstance(background, dict):
            raise ValueError("background must be an object")
        with self._lock:
            dashboard_cfg = dict(self.cfg.get("dashboard") or {})
            existing = dict(dashboard_cfg.get("background") or {})
            existing.update(background)
            dashboard_cfg["background"] = existing
            self.cfg["dashboard"] = dashboard_cfg
            config_store.save_config(self.cfg)
            dashboard_theme.set_pending_dashboard_layout(background=existing)
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

    # save_dashboard_middle_content() (the old global weather on/off,
    # "spotify"/"weather"/"none" fixed to the middle column) is gone --
    # weather is now a movable/resizable `weather` element like any
    # other (see dashboard_theme.default_weather_element()), saved and
    # live-applied through save_dashboard_elements()/
    # apply_weather_from_elements() above, same as the now-playing
    # display's own equivalent conversion earlier.

    def save_dashboard_preset(self, name, elements, background=None):
        """`background`, if given, is that preset's OWN snapshot of the
        panel background at the moment it was saved -- the web UI's
        "Save current layout as preset" button sends its current
        background draft, so a preset restores the exact look it was
        saved with (background included) rather than just its element
        layout against whatever background happens to be configured
        globally when it's later loaded. `None` (the default, and what
        every preset saved before this stored) means "no background of
        its own" -- _dashboard_preset_thumbnails() and the web UI's own
        loadPreset() both fall back to the currently configured global
        background in that case, same as before this existed.

        Always writes into `dashboard.presets`, whether `name` is
        brand new, an existing saved preset, or one of the app's own
        built-ins (dashboard_theme.BUILTIN_DASHBOARD_PRESETS) -- saving
        under a built-in's exact name is how it gets customized: from
        this point on config_store.resolve_dashboard_presets() prefers
        this saved copy over the code-defined one of the same name. If
        that name had previously been deleted (dismissed_builtin_
        presets), it's un-dismissed here too -- explicitly saving a
        preset by that name is as clear a signal as a person can give
        that they want something there again."""
        name = (name or "").strip()
        if not name:
            raise ValueError("preset name can't be empty")
        if not isinstance(elements, list):
            raise ValueError("elements must be a list")
        if background is not None and not isinstance(background, dict):
            raise ValueError("background must be an object")
        with self._lock:
            dashboard_cfg = dict(self.cfg.get("dashboard") or {})
            presets = dict(dashboard_cfg.get("presets") or {})
            presets[name] = {"elements": elements, "background": background}
            dashboard_cfg["presets"] = presets
            dismissed = list(dashboard_cfg.get("dismissed_builtin_presets") or [])
            if name in dismissed:
                dismissed.remove(name)
                dashboard_cfg["dismissed_builtin_presets"] = dismissed
            self.cfg["dashboard"] = dashboard_cfg
            config_store.save_config(self.cfg)
            merged = config_store.resolve_dashboard_presets(self.cfg)
            return {"presets": merged, "thumbnails": self._dashboard_preset_thumbnails(merged)}

    def delete_dashboard_preset(self, name):
        """Removes `name` from whatever's actually saved in this
        config (a person's own preset, or a saved customization of one
        of the app's built-ins). If `name` also happens to be one of
        the app's built-ins (dashboard_theme.BUILTIN_DASHBOARD_
        PRESETS), it's additionally recorded in `dashboard.
        dismissed_builtin_presets` -- otherwise, since a built-in isn't
        stored in `presets` to begin with (see config_store.
        resolve_dashboard_presets()), deleting a saved customization of
        one would just reveal the code-defined original again on the
        next merge, instead of the preset actually disappearing the
        way "delete" should."""
        with self._lock:
            dashboard_cfg = dict(self.cfg.get("dashboard") or {})
            presets = dict(dashboard_cfg.get("presets") or {})
            presets.pop(name, None)
            dashboard_cfg["presets"] = presets
            if name in dashboard_theme.BUILTIN_DASHBOARD_PRESETS:
                dismissed = list(dashboard_cfg.get("dismissed_builtin_presets") or [])
                if name not in dismissed:
                    dismissed.append(name)
                dashboard_cfg["dismissed_builtin_presets"] = dismissed
            self.cfg["dashboard"] = dashboard_cfg
            config_store.save_config(self.cfg)
            presets = config_store.resolve_dashboard_presets(self.cfg)
            return {"presets": presets, "thumbnails": self._dashboard_preset_thumbnails(presets)}

    def _dashboard_preset_thumbnails(self, presets, default_background=None):
        """Renders every saved preset's small preview picture (a
        `data:image/png;base64,...` URI, ready for an <img src=...>) --
        see dashboard_theme.render_preset_thumbnail()'s own docstring
        for why this reuses the real render pipeline instead of a
        lightweight mock. Each preset renders against its OWN saved
        background (see save_dashboard_preset()'s `background` param)
        if it has one, so e.g. a built-in preset's starfield or grid
        background actually shows up in its thumbnail rather than
        whatever background the panel happens to be configured with
        right now; a preset with no background of its own (`None` --
        every preset saved before this existed, and any preset saved
        without changing the background) falls back to
        `default_background`, which itself defaults to the currently
        configured global background.

        Accepts both preset shapes for whichever one `presets` actually
        holds: the current `{"elements": [...], "background": {...} or
        None}` dict, and the older bare-`elements`-list shape (in case
        anything still hands this one before config_store.py's
        migrate_dashboard_preset_shape() has run against it) -- a bare
        list is treated as `{"elements": <the list>, "background":
        None}`, identical to how that migration itself upgrades one.

        Called with the lock already held by save/delete above (cheap
        enough -- a handful of presets, each a small Pillow render --
        not to be worth releasing it for) and without the lock from
        dashboard_meta() (which only reads self.cfg once up front,
        outside its own `with` block, same as every other field it
        returns). A single bad/malformed saved preset (hand-edited
        app_config.json, say) logs and is skipped rather than taking
        down the whole picker -- every other preset's thumbnail still
        renders."""
        dashboard_cfg = self.cfg.get("dashboard") or {}
        if default_background is None:
            default_background = dict(dashboard_theme.DEFAULT_BACKGROUND, **(dashboard_cfg.get("background") or {}))
        thumbnails = {}
        for name, value in presets.items():
            try:
                if isinstance(value, list):
                    elements, own_background = value, None
                else:
                    elements, own_background = value.get("elements"), value.get("background")
                background = own_background if own_background else default_background
                img = dashboard_theme.render_preset_thumbnail(elements, background)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                thumbnails[name] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
            except Exception as e:  # noqa: BLE001 -- one bad preset shouldn't blank the whole picker
                self._log(f"(dashboard: couldn't render a thumbnail for preset {name!r}: {e})")
        return thumbnails

    def list_ports(self):
        """Scans for Hongtai-family panels right now (driver.
        find_hongtai_ports() -- matches on USB VID, so it finds any
        rebrand of this same hardware, not just XTRM Lab's), for the web
        UI's "Detect screens" button. Same underlying scan app.py's own
        "Refresh" button next to its port Combobox already uses -- this
        is that scan, exposed over HTTP for the headless controller.

        Each returned port's `value` is exactly what should be saved as
        `cfg["port"]` (a ScreenPort.label -- see _selected_port()'s
        docstring for why the human-readable label, not the raw device
        name, is what's persisted); `device`/`label` are split out
        separately so the frontend can build its own display text
        without parsing the combined label string. `auto_detect` is the
        sentinel value (config_store.AUTO_DETECT) for "let it pick
        automatically at connect time (only works if exactly one
        Hongtai-family panel is plugged in)", so the frontend doesn't
        need its own copy of that constant."""
        try:
            candidates = hongtai_screen.find_hongtai_ports()
        except Exception as e:  # noqa: BLE001 -- e.g. pyserial enumeration failing oddly
            self._log(f"(couldn't scan serial ports: {e})")
            candidates = []
        return {
            "ports": [
                {"value": c.label, "device": c.device, "description": c.description}
                for c in candidates
            ],
            "auto_detect": config_store.AUTO_DETECT,
        }

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
