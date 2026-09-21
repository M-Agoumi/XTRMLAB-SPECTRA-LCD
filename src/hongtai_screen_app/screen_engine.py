"""
screen_engine.py -- owns ONE persistent HongtaiScreen connection across
theme switches, so switching themes live means "stop calling this
theme's generate-image function, start calling that one instead" --
not "disconnect, then reconnect from scratch."

Why this exists (replaces ThemeWorker for controller.py):
Every theme module's run() used to open its own connection, run its
own render loop, and close its own connection -- so the only way
controller.py could ever get from "Dashboard is showing" to "Video is
showing" was stop the whole ThemeWorker (which disconnects), then
start a brand new one for the other theme (which reconnects). That's
backwards: the panel doesn't care which theme is driving it, it just
wants a stream of frames on an open serial port. Producing a frame is
the theme's job; owning the connection never needed to be.

Phase 1's owns_screen change to demo_clock.py/video_theme.py/
webpage_theme.py/dashboard_theme.py's run() functions made this
possible: each one now accepts an already-connected `screen=` and, if
given one, skips connecting/disconnecting entirely and just renders
onto it. This module is the other half -- the thing that actually
holds that connection open and hands it to whichever theme is active.

State machine, run on one dedicated background thread (`_loop`):
  - idle (no screen, nothing queued) -- waiting for switch()/close()
  - running (screen connected, a theme's run() is mid-call in this
    same thread) -- switch()/stop() interrupt it via its stop_event
  - recovering (run() raised, not from an intentional stop) -- closes
    the dead screen, fires a real firmware restart (blind_restart, not
    just a reconnect -- a wedged panel can need the actual restart
    command to come back at all, see the driver's blind_restart()),
    reconnects, retries -- up to RECOVERY_ATTEMPTS times

switch() and stop() never block the caller waiting for the old theme
to finish tearing down -- they just set the current run's stop_event
(so its loop notices and returns promptly) and queue the next thing to
do; the engine thread picks it up as soon as the current call to
target() returns. Callers that need to know when a switch has actually
taken effect should watch for the `on_connected`/`on_finished` callback
firing rather than treating switch()'s return as synchronous.
"""
import threading
import time

from .driver import hongtai_screen
from .driver.hongtai_screen import HongtaiScreen

RECOVERY_ATTEMPTS = 3


class ScreenEngine:
    """One instance = one persistent connection's worth of state.
    controller.py creates exactly one of these for the process's whole
    lifetime and calls switch()
    every time the user picks a different theme or hits Start/Apply --
    there is no separate "already running" guard any more, because
    switching *while* something is running is exactly the point.

    Thread-safety: switch()/stop()/close() and the read-only accessors
    are all safe to call from any thread (HTTP handler threads, etc.)
    -- only `_loop` (the engine's own background thread) ever calls
    into a theme's run() or touches the HongtaiScreen directly.
    """

    def __init__(self, screen_factory=HongtaiScreen, log=print,
                 on_connected=None, on_disconnected=None, on_finished=None):
        self.screen_factory = screen_factory
        self.log = log
        # on_connected(screen): fired once per fresh connection (first
        #   switch() after startup or after a full stop()/recovery
        #   reconnect) -- NOT fired again on every switch(), since a
        #   switch reuses the existing connection.
        # on_disconnected(): fired once the screen is actually closed --
        #   an explicit stop(), a theme ending on its own, or giving up
        #   after RECOVERY_ATTEMPTS. Never fired for a switch() (nothing
        #   gets closed), and deliberately NOT fired for close() either
        #   (see _teardown()): close() means the whole process is
        #   exiting, not that the user asked to stop, and
        #   AppController._on_screen_disconnected() treats this callback
        #   as "nothing to auto-resume next launch" -- which would be
        #   wrong here, since something *was* still running right up
        #   until the process quit and should come back on the next
        #   launch (see backend_app.py's resume-on-launch logic).
        # on_finished(label): fired when the given theme's run() returns
        #   on its own (e.g. a non-looping video reaching its last
        #   frame) rather than being interrupted by switch()/stop().
        self.on_connected = on_connected
        self.on_disconnected = on_disconnected
        self.on_finished = on_finished

        self._lock = threading.RLock()
        self._cv = threading.Condition(self._lock)
        self._screen = None
        self._port = None
        self._current_label = None
        self._current_stop_event = None
        self._busy = False           # True while a target(**kwargs) call is in flight
        self._pending = None         # ("run", label, target, kwargs) | ("stop",) | None
        self._shutdown = False

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #
    def switch(self, label, target, kwargs, port=None):
        """Starts running `target(**kwargs)` against the persistent
        connection, interrupting whatever's currently running first (if
        anything is). Connects lazily -- the very first switch() call
        (or the first one after a stop()/give-up) opens the port; every
        one after that, while still connected, reuses it. `kwargs`
        should be the same shape theme_kwargs.build() produces (no
        stop_event/log/screen/screen_factory/on_connected keys -- this
        adds all of those itself)."""
        with self._cv:
            if self._shutdown:
                raise RuntimeError("engine is shut down")
            if port is not None:
                self._port = port
            if self._current_stop_event is not None:
                self._current_stop_event.set()
            self._pending = ("run", label, target, dict(kwargs))
            self._cv.notify_all()
        return {"running_theme": label}

    def stop(self):
        """Interrupts whatever's running (if anything) and fully
        disconnects once it winds down. Safe to call when nothing is
        running (harmless no-op, just like ThemeWorker's absence used
        to be)."""
        with self._cv:
            if self._current_stop_event is not None:
                self._current_stop_event.set()
            self._pending = ("stop",)
            self._cv.notify_all()

    def close(self):
        """Full shutdown: stops the engine thread itself after tearing
        the connection down. Call once when the whole process exits
        (mirrors AppController.close())."""
        with self._cv:
            if self._current_stop_event is not None:
                self._current_stop_event.set()
            self._shutdown = True
            self._pending = ("stop",)
            self._cv.notify_all()
        self._thread.join(timeout=5.0)

    def is_running(self):
        with self._lock:
            return self._current_label is not None

    def current_theme(self):
        with self._lock:
            return self._current_label

    def active_screen(self):
        with self._lock:
            return self._screen

    # ------------------------------------------------------------------ #
    # the engine thread
    # ------------------------------------------------------------------ #
    def _loop(self):
        while True:
            with self._cv:
                while self._pending is None and not self._shutdown:
                    self._cv.wait()
                if self._pending is None and self._shutdown:
                    return
                action = self._pending
                self._pending = None
            if action[0] == "stop":
                self._teardown()
                if self._shutdown:
                    return
                continue
            _, label, target, kwargs = action
            self._run_with_recovery(label, target, kwargs)

    def _teardown(self):
        """Closes the live connection, if there is one, and resets
        "what's running" state. Safe to call when already torn down.

        Skips on_disconnected() when this teardown is happening because
        close() is shutting the whole engine down (self._shutdown is
        already True by the time _teardown() runs in that case -- see
        close()): the port still needs to be physically released either
        way, but "the process is exiting" is not the same event as "the
        user stopped the theme" or "it gave up/finished on its own",
        and on_disconnected() is what AppController uses to decide
        there's nothing left to auto-resume next launch. Firing it here
        was wiping that resume marker on every clean quit/restart, so
        quitting while something was running "forgot" it by the next
        launch instead of resuming on its own."""
        with self._lock:
            screen = self._screen
            self._screen = None
            self._current_label = None
            self._current_stop_event = None
            shutting_down = self._shutdown
        if screen is None:
            return
        try:
            screen.close()
        except Exception as e:  # noqa: BLE001 -- surfaced in the log either way
            self.log(f"(disconnect error: {e})")
        self.log("Stopped, disconnected cleanly.")
        if self.on_disconnected is not None and not shutting_down:
            try:
                self.on_disconnected()
            except Exception:  # noqa: BLE001 -- a callback bug shouldn't wedge the engine
                pass

    def _ensure_connected(self):
        """Returns the live screen, connecting fresh only if we don't
        already have one -- the whole point of this module. Raises
        whatever screen.connect() raises on failure."""
        with self._lock:
            if self._screen is not None:
                return self._screen
        screen = self.screen_factory(self._port)
        info = screen.connect()
        self.log(f"Connected: {info.width}x{info.height}, firmware {info.version}")
        with self._lock:
            self._screen = screen
        if self.on_connected is not None:
            try:
                self.on_connected(screen)
            except Exception:  # noqa: BLE001
                pass
        return screen

    def _has_newer_work_queued(self):
        with self._lock:
            return self._pending is not None

    def _run_with_recovery(self, label, target, base_kwargs):
        for attempt in range(1, RECOVERY_ATTEMPTS + 1):
            stop_event = threading.Event()
            with self._lock:
                self._current_label = label
                self._current_stop_event = stop_event

            try:
                screen = self._ensure_connected()
            except Exception as e:  # noqa: BLE001
                self.log(f"ERROR: could not connect: {e}")
                if attempt >= RECOVERY_ATTEMPTS:
                    self.log(f"Giving up after {RECOVERY_ATTEMPTS} attempts -- "
                             "check the panel/cable, then pick a theme again.")
                    self._teardown()
                    return
                time.sleep(1.0)
                continue

            kwargs = dict(base_kwargs)
            kwargs.pop("port", None)
            kwargs.pop("screen_factory", None)
            kwargs.pop("on_connected", None)
            kwargs["stop_event"] = stop_event
            kwargs["log"] = self.log
            kwargs["screen"] = screen

            with self._lock:
                self._busy = True
            try:
                target(**kwargs)
            except Exception as e:  # noqa: BLE001 -- surfaced in the log either way
                with self._lock:
                    self._busy = False
                if stop_event.is_set():
                    # An explicit stop()/switch() landed mid-error -- not
                    # a fault to recover from, just noise.
                    self.log(f"(stopped: {e})")
                    return
                self.log(f"ERROR: {e}")
                if self._has_newer_work_queued():
                    # Something else was already switch()'d/stop()'d in
                    # while we were mid-call -- don't bother restarting
                    # the panel's firmware for a theme nobody wants
                    # running any more; just drop the dead connection so
                    # the queued action reconnects fresh.
                    self._teardown()
                    return
                if attempt >= RECOVERY_ATTEMPTS:
                    self.log(f"Giving up after {RECOVERY_ATTEMPTS} attempts -- "
                             "check the panel/cable, then pick a theme again.")
                    self._teardown()
                    return
                self.log(f"Recovering (attempt {attempt + 1}/{RECOVERY_ATTEMPTS}) -- "
                         "restarting the panel's firmware, not just reconnecting "
                         "(see README's \"If the panel stops responding\") ...")
                with self._lock:
                    dead_screen, self._screen = self._screen, None
                if dead_screen is not None:
                    try:
                        dead_screen.close()
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    hongtai_screen.HongtaiScreen(self._port).blind_restart(log=self.log)
                except Exception as restart_err:  # noqa: BLE001
                    self.log(f"(restart attempt failed: {restart_err} -- trying to reconnect anyway)")
                time.sleep(1.0)
                continue
            else:
                with self._lock:
                    self._busy = False
                if stop_event.is_set():
                    # Interrupted on purpose (switch() or stop()) --
                    # whichever queued that decides what happens next;
                    # nothing to tear down or report here.
                    return
                # Ended on its own -- e.g. a non-looping video reaching
                # its last frame, or webpage_theme.py bailing out after
                # a failed page load. Disconnect, same as the old
                # owns_screen behavior every theme used to have on its
                # own, so "nothing is using the panel" still means "the
                # port is actually closed" rather than silently idling.
                self._teardown()
                if self.on_finished is not None:
                    try:
                        self.on_finished(label)
                    except Exception:  # noqa: BLE001
                        pass
                return
