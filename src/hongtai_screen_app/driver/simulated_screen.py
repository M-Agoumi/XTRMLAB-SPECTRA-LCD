"""
simulated_screen.py -- a drop-in stand-in for HongtaiScreen that needs no
panel plugged in at all, so the app (and anyone developing against it)
can run any theme and watch it over the existing web mirror / `/frame.jpg`
endpoint without owning the hardware.

Why a fake serial object rather than overriding show()/close()/
set_brightness()/etc. one by one: HongtaiScreen's real methods already do
exactly the right thing for simulation *except* for the couple of lines
that touch `self._ser` -- the brightness dim, the rotation math, and
`_update_mirror()` in show() all happen before that, `close()`'s CMD_CLOSE
write is harmless to skip, `set_brightness()`/`start_live()` go through
`_send_noreply()`, etc. Giving `self._ser` a fake object that accepts
writes and throws them away means every one of those methods runs
completely unmodified -- so simulation can never silently drift out of
sync with what a real panel actually does frame-to-frame (brightness
dimming, mirror feed, rotation). Only connect() (there is no firmware to
ask for a DeviceInfo) and blind_restart() (there is no firmware to
restart) need their own behavior; everything else is inherited as-is.
"""
import time

from .hongtai_screen import DeviceInfo, HongtaiScreen

# A real 5.99" XTRM Lab Spectra panel's own numbers -- used as the
# default so "just simulate it" looks like the hardware most people
# actually have, without requiring any config up front.
DEFAULT_WIDTH = 960
DEFAULT_HEIGHT = 480
DEFAULT_ANGLE = 180


class _FakeSerial:
    """Satisfies the handful of pyserial.Serial attributes/methods
    HongtaiScreen's own code touches (`is_open`, `write()`, `flush()`,
    `reset_input_buffer()`, `read()`, `close()`) without opening any real
    port. Every write is thrown away -- that's the entire point."""

    def __init__(self):
        self.is_open = True

    def write(self, data):
        return len(data)

    def flush(self):
        pass

    def reset_input_buffer(self):
        pass

    def read(self, n=1):
        return b""

    def close(self):
        self.is_open = False


class SimulatedHongtaiScreen(HongtaiScreen):
    """Same public interface as HongtaiScreen (connect/show/set_brightness/
    enable_web_mirror/enable_frame_capture/close/blind_restart), so
    ScreenEngine and every theme's run() work against it unchanged -- see
    screen_engine.py and any theme module's `screen=` kwarg docstring.

    `port` is accepted (and ignored) purely so callers that always pass
    `port=...` don't need a special case; nothing is ever opened.
    """

    def __init__(self, port=None, width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT,
                 angle=DEFAULT_ANGLE, baudrate=2_000_000, timeout=3.0):
        # A non-None port string here skips HongtaiScreen.__init__'s
        # auto-detect scan (find_hongtai_port()), which would otherwise
        # run right now and fail on a machine with no panel plugged in --
        # exactly what simulation mode exists to not require.
        super().__init__(port="(simulated)", baudrate=baudrate, timeout=timeout)
        self._sim_width = int(width)
        self._sim_height = int(height)
        self._sim_angle = int(angle) % 360

    def connect(self, retries=30, retry_delay=0.3, auto_restart=True):
        """No handshake, no retries -- just fabricates the DeviceInfo a
        real connect() would have gotten back from the firmware, using
        this instance's configured virtual panel size/angle."""
        self._ser = _FakeSerial()
        panel_w, panel_h = self._sim_width, self._sim_height
        if self._sim_angle in (90, 270):
            canvas_w, canvas_h = panel_h, panel_w
        else:
            canvas_w, canvas_h = panel_w, panel_h
        self.info = DeviceInfo(
            width=canvas_w,
            height=canvas_h,
            angle=self._sim_angle,
            version=3.3,
            uid="simulated",
            model="Simulated Panel",
            raw={},
            panel_width=panel_w,
            panel_height=panel_h,
        )
        return self.info

    def blind_restart(self, settle_time=3.0, log=print):
        """There's no firmware to restart -- ScreenEngine's recovery path
        (screen_engine.py's _run_with_recovery) calls this between retry
        attempts after an error, so it still needs to exist and behave
        (a short pause, a log line) rather than trying to open a real
        serial port to a port name that was never real."""
        log("  (simulated panel: nothing to restart)")
        time.sleep(min(settle_time, 0.5))

    # close() is inherited as-is: it only ever writes CMD_CLOSE through
    # self._ser (harmless against _FakeSerial, which just discards it)
    # and then calls self._ser.close() -- nothing there assumes real
    # hardware.
