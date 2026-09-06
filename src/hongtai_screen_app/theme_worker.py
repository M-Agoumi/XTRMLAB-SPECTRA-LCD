"""
theme_worker.py -- runs one theme's run() function on a background
thread, with automatic panel-firmware-restart recovery on failure. Split
out of app.py (Phase 1 of ROADMAP.md's v2.0 rewrite): none of this
retry/threading logic is Tkinter -- it only ever talks back to its
caller through the log/callbacks it's handed, which is exactly what
lets Phase 2's control API drive the same worker with no UI at all.
"""
import threading
import time

from .driver import hongtai_screen

# A mid-stream write timeout dying and staying dead until someone
# notices the log and clicks Start again -- which then just as
# silently reconnects to a panel whose live-video decode path is
# still wedged -- was the actual bug behind "the image froze and
# never came back": connect()'s own retry/blind_restart logic only
# fires a firmware restart when the initial handshake itself gets no
# reply at all, but a panel that's wedged mid-stream can still answer
# getDeviceInfo just fine, so a plain reconnect "succeeds" (logs
# Connected/Streaming again) while the panel keeps ignoring frames --
# exactly matching README's "if the panel stops responding" section:
# blind_restart() is the actual fix, not just reopening the port.
RECOVERY_ATTEMPTS = 3


class ThemeWorker:
    """Wraps a single `target(**kwargs)` theme call in a background
    thread with up to RECOVERY_ATTEMPTS retries, each retry doing a real
    firmware restart (not just a reconnect) before trying again.

    `kwargs` must include `stop_event` (a threading.Event the caller sets
    to ask this to stop) and `port` (used only for the recovery restart,
    may be None for auto-detect). `log` is called with a single string
    argument for every status/error line -- same shape as the `log=`
    kwarg every theme's own run() takes.
    """

    def __init__(self, target, kwargs, log):
        self.target = target
        self.kwargs = kwargs
        self.log = log
        self.stop_event = kwargs.get("stop_event")
        self.port = kwargs.get("port")
        self._thread = threading.Thread(target=self._run_safely, daemon=True)

    def start(self):
        self._thread.start()

    def is_alive(self):
        return self._thread.is_alive()

    def _run_safely(self):
        for attempt in range(1, RECOVERY_ATTEMPTS + 1):
            try:
                self.target(**self.kwargs)
                return  # ended on its own: Stop was pressed, or e.g. a
                         # video without --loop simply finished playing
            except Exception as e:  # noqa: BLE001 -- surfaced in the log either way
                if self.stop_event is not None and self.stop_event.is_set():
                    # Already stopping -- an exception racing with that
                    # (Stop landing mid-write, say) isn't a fault to
                    # recover from, just noise.
                    self.log(f"(stopped: {e})")
                    return

                self.log(f"ERROR: {e}")
                if attempt >= RECOVERY_ATTEMPTS:
                    self.log(f"Giving up after {RECOVERY_ATTEMPTS} "
                              "attempts -- check the panel/cable, then "
                              "hit Start again.")
                    return

                self.log(f"Recovering (attempt {attempt + 1}/"
                          f"{RECOVERY_ATTEMPTS}) -- restarting the "
                          "panel's firmware, not just reconnecting (see "
                          "README's \"If the panel stops responding\") ...")
                try:
                    hongtai_screen.HongtaiScreen(self.port).blind_restart(log=self.log)
                except Exception as restart_err:  # noqa: BLE001
                    self.log(f"(restart attempt failed: {restart_err} -- "
                              "trying to reconnect anyway)")
                time.sleep(1.0)
