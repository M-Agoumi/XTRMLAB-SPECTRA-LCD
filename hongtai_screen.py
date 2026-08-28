"""
hongtai_screen.py
==================

A from-scratch, open-source Python client for the "Hongtai" family of
USB-serial smart-screen panels used inside many rebranded PC-case LCDs
(sold as XTRM Lab, SAMA, Thermaltake, ZOTAC, MSI, ASIAHORSE, and dozens
of other brands -- they're all the same OEM hardware from Dongguan
Hongtai Technology Co., Ltd, just re-skinned).

This was reverse-engineered by reading the *unobfuscated* JavaScript
inside the official "XTRM lab" Electron app's app.asar bundle -- the
wire protocol is NOT the same as the popular "Turing Smart Screen"
protocol (github.com/mathoudebine/turing-smart-screen-python), so that
project's tools will connect but never actually draw anything on this
hardware. This module talks the *real* protocol.

PROTOCOL SUMMARY
-----------------
Transport:
    Plain USB-serial (shows up as a COM port on Windows / /dev/ttyACM*
    on Linux). VID 0x33C3, PID varies per rebrand (0x7804 for XTRM Lab).
    Baud rate: 2,000,000 (2 Mbaud).

    *** DTR MUST BE ASSERTED (HIGH). ***  This is the single thing that
    decides whether the panel talks back at all. The firmware gates its
    transmit path on DTR -- with DTR low it still happily *receives*
    everything you send (you can even blank its idle video that way),
    but it will never send a single byte back, so every getDeviceInfo
    times out and the panel looks bricked. Verified empirically: a
    sweep of all four DTR/RTS combinations answers under dtr=True with
    either RTS state, and is silent under both dtr=False states.

    Note the trap in the vendor app that this was originally misread
    from -- it constructs its port as:

        new SerialPort({path, baudRate: 2e6, autoOpen: false,
                        endOnClose: true, dtr: false, rts: false})

    `dtr` and `rts` are NOT valid node-serialport constructor options.
    They are silently ignored (DTR/RTS are only settable via .set()),
    and node-serialport asserts both on open by default on Windows. So
    the vendor app runs with DTR *high* despite what that line reads
    like.

Command framing (used for short control commands):
    byte 0-1:  0x55 0xAA                     (magic / sync bytes)
    byte 2-3:  length, little-endian         (= len(payload) + 7)
    byte 4:    command key (single byte)
    byte 5..:  payload bytes (may be empty)
    last 2:    checksum, little-endian       (sum of ALL preceding
                                               bytes, mod 65536)

Known command keys:
     1  restart
     3  set brightness              payload = [0-100]
     6  get device info             payload = (empty); reply is JSON
                                     (width, height, angle, version,
                                     uid, model, region) hex-encoded
                                     as ASCII in the response body
    12  OTA firmware header
    17  "I'm sending a live frame stream" / keep-alive ping
    21  set motion timeout
    32  set region                  payload = utf8 string
    33  close session (firmware >= v3.1 only)
    35  set serial number

Connect handshake:
    1. Open the serial port (2,000,000 baud, 8N1, DTR=RTS=False).
    2. Write the RAW bytes 0xFF 0xD9 0xFF 0xD9 (looks like a doubled
       JPEG end-of-image marker -- almost certainly "flush/reset
       whatever half-received frame you were holding").
    3. Wait ~200ms.
    4. Send a framed "get device info" command (key=6, no payload).
    5. Read the reply. The reply layout is:
           0x55 0xAA lenLo lenHi key <payload...> csLo csHi
       Slice bytes [5 : len-2] and parse that as UTF-8 JSON. (The
       vendor app round-trips it through .toString("hex") and
       Buffer.from(hex) on the way, which looks like double hex
       encoding but is a no-op.)

       The JSON is an envelope: {"cmd":"info","data":{...}} -- the
       fields you want are one level down in "data":
       {uid, width, height, diplay_on (sic), brightness, model,
       i_blocks, i_block_size, i_block_free, i_path, ...}.

       Observed on an XTRM Lab Spectra 6.2" panel:
       960x480, model "TXW818-JD9161C-5.x", uid 042676173F3E.

Showing an image ("live" mode):
    The official app doesn't send one static "draw bitmap" command
    like Turing panels do. Instead it works like a screen-share /
    MJPEG feed:
      1. Send the framed key=17 command once to say "starting a live
         stream".
      2. Repeatedly: take whatever you want shown (a rendered PIL
         image sized to the panel's width x height), encode it as a
         JPEG, and write the RAW JPEG bytes straight to the serial
         port -- NOT wrapped in the 0x55/0xAA framing. The firmware
         auto-detects frame boundaries from the JPEG stream itself.
      3. Send another key=17 ping at least every ~1.5 seconds even if
         you aren't pushing a new frame, or the firmware appears to
         drop the session.
      4. The panel does NOT apply its own mounting rotation. It reports
         how it is mounted in `angle` (180 on the XTRM Lab Spectra) and
         expects the host to hand it an already-rotated frame -- the
         vendor app rotates its render, it does not send an upright one.
         show() does this for you from info.angle; set screen.rotate to
         override.
      5. JPEG quality is walked down in steps of 5 (starting at 100)
         until the encoded size fits under a resolution-dependent cap
         (the official app uses ~50-260 KB depending on panel size) --
         this keeps each frame small enough to stream fast at 2 Mbaud.

IF THE PANEL IS WEDGED
-----------------------
A panel that answers nothing, or that accepts commands but shows a black
screen, is almost always fixed by the firmware's own restart command
(key=1) -- see blind_restart(). It is fire-and-forget, so it lands even
when the panel is replying to nothing, and connect() now falls back to it
automatically. What does NOT help, all tested: a DTR pulse; replaying
turing-smart-screen-python's reset recipe (its rtscts=True can hang
pyserial indefinitely against this chip -- avoid); `pnputil /remove-device`
(leaves the device needing a full Windows reboot); and even a genuine
mains-off power cycle, since the panel comes straight back up in the same
wedged state.

This module packages all of that into a small, dependency-light class
so you can drive the screen with *whatever content you want* -- text,
clocks, live system stats, images, anything you can render with
Pillow -- instead of being stuck with the vendor's theme editor.

Requirements:
    pip install pyserial pillow

Example:
    from hongtai_screen import HongtaiScreen
    from PIL import Image, ImageDraw

    screen = HongtaiScreen("COM3")
    screen.connect()
    print(screen.width, screen.height)   # real resolution, from the device

    img = Image.new("RGB", (screen.width, screen.height), "black")
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), "Hello from Python!", fill="white")
    screen.show(img)

    screen.close()
"""

from __future__ import annotations

import io
import time
import threading
from dataclasses import dataclass
from typing import List, Optional

import serial  # pyserial
from PIL import Image
from serial.tools import list_ports

BAUD_RATE = 2_000_000
SYNC = bytes([0x55, 0xAA])
RESET_MARKER = bytes([0xFF, 0xD9, 0xFF, 0xD9])

# command keys
CMD_RESTART = 1
CMD_SET_BRIGHTNESS = 3
CMD_GET_DEVICE_INFO = 6
CMD_LIVE_PING = 17
CMD_SET_REGION = 32
CMD_CLOSE = 33

# Dongguan Hongtai Technology's USB vendor ID -- shared across every rebrand
# of this hardware (XTRM Lab, SAMA, Thermaltake, ZOTAC, MSI, ASIAHORSE, and
# dozens of others; ~48 brand names were found in the vendor app's own
# bundle, each just a different PID + logo on identical hardware/firmware).
# Matching on VID alone -- not a specific PID -- is what makes port
# auto-detection work for anyone with a Hongtai-family panel, not just this
# exact XTRM Lab unit.
HONGTAI_VID = 0x33C3

# PIDs seen/confirmed so far. Not exhaustive -- there are reportedly ~48
# rebrands, each with its own PID under the same VID above. A port matching
# HONGTAI_VID but with an unlisted PID is still treated as a candidate; this
# dict is only used to print a friendlier label when we recognize it.
KNOWN_PIDS = {
    0x7804: "XTRM Lab (confirmed)",
}


@dataclass
class ScreenPort:
    """One serial port that looks like it could be a Hongtai-family panel."""
    device: str          # e.g. "COM3"
    vid: Optional[int]
    pid: Optional[int]
    description: str
    serial_number: Optional[str]

    @property
    def label(self) -> str:
        pid_note = KNOWN_PIDS.get(self.pid, "unrecognized PID -- probably still fine, "
                                              "just not one we've seen a report for yet")
        vid_str = f"{self.vid:04X}" if self.vid is not None else "????"
        pid_str = f"{self.pid:04X}" if self.pid is not None else "????"
        return f"{self.device}  (VID {vid_str}:{pid_str} -- {pid_note})  {self.description}"


def find_hongtai_ports() -> List[ScreenPort]:
    """
    Scan every serial port on the system and return the ones whose VID
    matches Dongguan Hongtai Technology (see HONGTAI_VID above) -- i.e.
    every port that's plausibly *some* rebrand of this same panel
    hardware, not just an XTRM Lab one specifically.
    """
    found = []
    for p in list_ports.comports():
        if p.vid == HONGTAI_VID:
            found.append(ScreenPort(
                device=p.device,
                vid=p.vid,
                pid=p.pid,
                description=p.description or "",
                serial_number=p.serial_number,
            ))
    return found


def find_hongtai_port() -> str:
    """
    Auto-detect a single Hongtai-family panel's COM port. Raises
    HongtaiScreenError with a clear, actionable message if none or more
    than one is found (COM3 on one machine is not guaranteed to be COM3,
    or even the same port, on anyone else's).
    """
    candidates = find_hongtai_ports()
    if not candidates:
        raise HongtaiScreenError(
            "no Hongtai-family screen found (scanned all serial ports for "
            f"VID {HONGTAI_VID:04X}). Run list_screens.py to see every port "
            "on this system, and pass the port explicitly if it's not being "
            "detected -- e.g. HongtaiScreen('COM5')."
        )
    if len(candidates) > 1:
        listed = "\n  ".join(c.label for c in candidates)
        raise HongtaiScreenError(
            f"found {len(candidates)} Hongtai-family screens, can't auto-pick one:\n  "
            f"{listed}\nPass the port explicitly, e.g. HongtaiScreen('COM5')."
        )
    return candidates[0].device


@dataclass
class DeviceInfo:
    # Logical drawing canvas: what you should render to. For a panel
    # mounted at 90/270 degrees this is the panel's size with the axes
    # swapped, so you can just draw "the right way up" and let show()
    # deal with the physical orientation.
    width: int
    height: int
    angle: int
    version: float
    uid: str
    model: str
    raw: dict
    # Physical panel size, exactly as the firmware reports it.
    panel_width: int = 0
    panel_height: int = 0


class HongtaiScreenError(RuntimeError):
    pass


def _build_frame(key: int, payload: bytes = b"") -> bytes:
    """Build one 0x55/0xAA framed command packet."""
    length = len(payload) + 7
    header = SYNC + bytes([length % 256, length // 256, key])
    body = header + payload
    checksum = sum(body) & 0xFFFF
    return body + bytes([checksum & 0xFF, (checksum >> 8) & 0xFF])


def _as_float(value) -> float:
    """Firmware reports `version` as a number on some units and as a
    string ("Ver1.0") on others. Normalize so version comparisons in
    close() can't blow up."""
    try:
        return float(value)
    except (TypeError, ValueError):
        import re as _re
        m = _re.search(r"\d+(?:\.\d+)?", str(value))
        return float(m.group()) if m else 0.0


def _parse_reply(data: bytes) -> dict:
    """
    Decode a reply packet: strip the 5-byte header (0x55 0xAA lenLo
    lenHi key) and the 2-byte trailing checksum -- what's left is
    plain UTF-8 JSON for structured replies like get-device-info.
    (The original app round-trips this through .toString('hex') and
    Buffer.from(hex) on the way, which looks like double hex-decoding
    at first glance but is actually a no-op -- the payload was never
    hex-encoded to begin with.)
    """
    body = data[5:-2]
    try:
        parsed = __import__("json").loads(body.decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        raise HongtaiScreenError(f"could not parse device reply: {data!r} ({e})")
    # Replies are wrapped: {"cmd": "info", "data": {...}}. Unwrap, but
    # tolerate a flat reply in case some firmware revision sends one.
    if isinstance(parsed, dict) and isinstance(parsed.get("data"), dict):
        inner = dict(parsed["data"])
        inner.setdefault("cmd", parsed.get("cmd"))
        return inner
    return parsed


class HongtaiScreen:
    """
    Client for Hongtai-protocol smart screens (XTRM Lab / SAMA /
    Thermaltake / ZOTAC / MSI / ASIAHORSE / etc. rebrands).
    """

    def __init__(self, port: Optional[str] = None, baudrate: int = BAUD_RATE, timeout: float = 3.0):
        """
        `port`: e.g. "COM3". Omit it (or pass None) to auto-detect --
        this scans for a serial port whose USB VID matches Dongguan
        Hongtai Technology (see HONGTAI_VID) and uses it if there's
        exactly one. Auto-detection raises HongtaiScreenError with a
        clear message if zero or more than one candidate is found, since
        COM3 on one machine is not guaranteed to be COM3 -- or even the
        same port -- on anyone else's.
        """
        if port is None:
            port = find_hongtai_port()
            print(f"  auto-detected panel on {port}")
        self.port_name = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._ser: Optional[serial.Serial] = None
        self.info: Optional[DeviceInfo] = None
        self._live_started = False
        self._ping_thread: Optional[threading.Thread] = None
        self._ping_stop = threading.Event()
        self._quality = 100  # adaptive JPEG quality, walked down as needed
        self.rotate: Optional[int] = None  # override the reported angle if needed
        # The background keep-alive pinger (started by start_live()) and
        # whatever thread calls show()/run() both write to the same
        # pyserial handle. pyserial's Windows backend is NOT safe for
        # concurrent writes from multiple threads -- two overlapping
        # write() calls can corrupt the shared OVERLAPPED I/O state and
        # leave a later write hung until it raises SerialTimeoutException.
        # This lock serializes every write+flush against the port.
        self._write_lock = threading.Lock()

    @property
    def width(self) -> int:
        """Logical canvas width. Raises if not connected yet."""
        if not self.info:
            raise HongtaiScreenError("not connected -- call connect() first")
        return self.info.width

    @property
    def height(self) -> int:
        """Logical canvas height. Raises if not connected yet."""
        if not self.info:
            raise HongtaiScreenError("not connected -- call connect() first")
        return self.info.height

    # ------------------------------------------------------------------ #
    # connection
    # ------------------------------------------------------------------ #
    def blind_restart(self, settle_time: float = 3.0):
        """
        Fire-and-forget firmware restart (key=1) -- the actual fix for a
        wedged panel (see "IF THE PANEL IS WEDGED" in the module
        docstring). This does NOT wait for or need any reply, so it
        works even when the panel is answering nothing at all: it opens
        the port itself (DTR/RTS asserted, same as connect()), sends the
        flush marker and the restart command, then closes.

        Safe to call directly too:
            python -c "from hongtai_screen import HongtaiScreen; HongtaiScreen('COM3').blind_restart()"
        """
        print("  blind_restart: opening the port and sending key=1 (restart), no reply expected ...")
        ser = None
        try:
            ser = serial.Serial()
            ser.port = self.port_name
            ser.baudrate = self.baudrate
            ser.timeout = self.timeout
            ser.write_timeout = 3
            ser.dtr = True
            ser.rts = True
            ser.open()
            # re-assert on the open handle, same reasoning as _connect_once
            ser.dtr = True
            ser.rts = True
            time.sleep(0.5)
            ser.write(RESET_MARKER)
            ser.flush()
            time.sleep(0.2)
            ser.write(_build_frame(CMD_RESTART))
            ser.flush()
            time.sleep(0.3)
        except Exception as e:  # noqa: BLE001
            print(f"  (blind_restart reported: {e} -- continuing anyway)")
        finally:
            if ser is not None:
                try:
                    ser.close()
                except Exception:  # noqa: BLE001
                    pass
        print(f"  waiting {settle_time:.0f}s for the panel to come back ...")
        time.sleep(settle_time)

    def connect(self, retries: int = 30, retry_delay: float = 0.3,
                auto_restart: bool = True) -> DeviceInfo:
        """
        Full connect handshake, matching the vendor app's own behavior:
        it does NOT treat a failed first attempt as fatal -- the device
        commonly doesn't answer the very first getDeviceInfo request
        right after a cold (re)connect, so the official app retries the
        *entire* open -> reset -> getDeviceInfo sequence up to 50 times,
        100ms apart, before giving up. We do the same (30 retries by
        default, slightly more patient at 300ms apart) since it's the
        difference between "times out" and "works" in practice.
        """
        last_error: Optional[Exception] = None
        for attempt in range(1, retries + 1):
            try:
                return self._connect_once()
            except Exception as e:  # noqa: BLE001
                last_error = e
                if attempt > 1 or attempt == retries:
                    print(f"  (connect attempt {attempt}/{retries} failed: {e}; retrying)")
                # Clean up before retrying -- a half-open port can wedge
                # the next attempt.
                if self._ser is not None:
                    try:
                        self._ser.close()
                    except Exception:  # noqa: BLE001
                        pass
                    self._ser = None
                if attempt < retries:
                    time.sleep(retry_delay)
        if auto_restart:
            print(f"  no reply after {retries} attempts -- trying a firmware restart")
            self.blind_restart()
            return self.connect(retries=retries, retry_delay=retry_delay,
                                auto_restart=False)
        raise HongtaiScreenError(
            f"could not connect after {retries} attempts: {last_error}. "
            f"If the port opens but nothing ever replies, check that DTR is "
            f"asserted -- see the module docstring."
        )

    def _connect_once(self) -> DeviceInfo:
        self._ser = serial.Serial()
        self._ser.port = self.port_name
        self._ser.baudrate = self.baudrate
        self._ser.timeout = self.timeout
        # DTR HIGH is mandatory -- see the module docstring. With DTR low
        # the panel receives but never transmits, and every command below
        # times out. RTS does not appear to matter; assert it too, to match
        # what node-serialport does for the vendor app.
        self._ser.dtr = True
        self._ser.rts = True
        self._ser.open()
        # re-assert on the open handle as well, so we don't depend on
        # pyserial's pre-open state having been applied.
        self._ser.dtr = True
        self._ser.rts = True
        time.sleep(0.5)

        # Step 1: tell the firmware to flush/reset any half-sent frame.
        self._ser.write(RESET_MARKER)
        time.sleep(0.2)

        # Step 2: ask for device info -- this also confirms the link works.
        reply = self._send_and_wait(CMD_GET_DEVICE_INFO)
        data = _parse_reply(reply)
        panel_w = int(data["width"])
        panel_h = int(data["height"])
        try:
            angle = int(data.get("angle", 0) or 0) % 360
        except (TypeError, ValueError):
            angle = 0
        # At 90/270 the panel's long axis is the canvas's short axis.
        canvas_w, canvas_h = (panel_h, panel_w) if angle in (90, 270) else (panel_w, panel_h)
        self.info = DeviceInfo(
            width=canvas_w,
            height=canvas_h,
            angle=angle,
            version=_as_float(data.get("version", 0)),
            uid=data.get("uid", ""),
            model=data.get("model", ""),
            raw=data,
            panel_width=panel_w,
            panel_height=panel_h,
        )
        return self.info

    def close(self):
        self.stop_live()
        if self._ser and self._ser.is_open:
            try:
                if self.info and self.info.version >= 3.1:
                    self._ser.write(_build_frame(CMD_CLOSE))
            except Exception:  # noqa: BLE001
                pass
            self._ser.close()
        self._ser = None

    # ------------------------------------------------------------------ #
    # low-level helpers
    # ------------------------------------------------------------------ #
    def _send_and_wait(self, key: int, payload: bytes = b"") -> bytes:
        if not self._ser:
            raise HongtaiScreenError("not connected")
        self._ser.reset_input_buffer()
        with self._write_lock:
            self._ser.write(_build_frame(key, payload))
            self._ser.flush()
        # read until we see the 0x55 0xAA sync at the start of a reply
        deadline = time.time() + self.timeout
        buf = b""
        while time.time() < deadline:
            chunk = self._ser.read(64)
            if chunk:
                buf += chunk
                idx = buf.find(SYNC)
                if idx != -1 and len(buf) - idx >= 5:
                    length = buf[idx + 2] | (buf[idx + 3] << 8)
                    total = idx + length
                    if len(buf) >= total:
                        return buf[idx:total]
            else:
                continue
        raise HongtaiScreenError(f"timed out waiting for reply to key={key}")

    def _send_noreply(self, key: int, payload: bytes = b""):
        if not self._ser:
            raise HongtaiScreenError("not connected")
        with self._write_lock:
            self._ser.write(_build_frame(key, payload))
            self._ser.flush()

    # ------------------------------------------------------------------ #
    # public controls
    # ------------------------------------------------------------------ #
    def set_brightness(self, percent: int):
        """percent: 0-100"""
        percent = max(0, min(100, int(percent)))
        self._send_noreply(CMD_SET_BRIGHTNESS, bytes([percent]))

    def restart_device(self):
        self._send_noreply(CMD_RESTART)

    # ------------------------------------------------------------------ #
    # showing content
    # ------------------------------------------------------------------ #
    def _max_frame_kb(self) -> int:
        """
        Mirror the vendor's sendPic_getMaxSizeAndRate() exactly:

            const s = model.includes("9.16"), a = model.includes("6.67");
            const r = Math.max(width, height);
            let l = s ? (version > 2.8 ? 120 : 90)
                      : (version > 2.8 ?  80 : 50);
            if (a || r >= 1024) l = 260;

        For the 5.99" 960x480 panel at firmware 3.3 this gives 80 KB.
        (Frames well over this cap were still accepted in testing, so it
        is a bandwidth budget rather than a hard firmware limit -- but
        there is no reason to diverge from the app.)
        """
        if not self.info:
            return 60
        model = self.info.model or ""
        newer = self.info.version > 2.8
        if "6.67" in model or max(self.info.panel_width, self.info.panel_height) >= 1024:
            return 260
        if "9.16" in model:
            return 120 if newer else 90
        return 80 if newer else 50

    def _encode_jpeg(self, img: Image.Image) -> bytes:
        """Adaptive-quality JPEG encode, walking quality down until the
        frame fits under the device's size cap (mirrors the official
        app's getSizeBt())."""
        cap_bytes = self._max_frame_kb() * 1024
        quality = self._quality
        while quality > 10:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality)
            data = buf.getvalue()
            if len(data) <= cap_bytes:
                self._quality = quality
                return data
            quality -= 5
        return data  # best effort at lowest quality

    def start_live(self):
        """Begin a live session: sends the initial ping and starts a
        background thread that keeps pinging every 1.5s so the
        firmware doesn't time out the session between frames."""
        if self._live_started:
            return
        self._send_noreply(CMD_LIVE_PING)
        self._live_started = True
        self._ping_stop.clear()

        def _pinger():
            while not self._ping_stop.wait(1.5):
                try:
                    self._send_noreply(CMD_LIVE_PING)
                except Exception:  # noqa: BLE001
                    pass

        self._ping_thread = threading.Thread(target=_pinger, daemon=True)
        self._ping_thread.start()

    def stop_live(self):
        if not self._live_started:
            return
        self._ping_stop.set()
        if self._ping_thread:
            self._ping_thread.join(timeout=2)
        self._live_started = False

    def show(self, img: Image.Image):
        """
        Push one frame to the screen. `img` should ideally already be
        sized to (self.info.width, self.info.height); it will be
        resized automatically if not.
        """
        if not self._ser or not self.info:
            raise HongtaiScreenError("not connected")
        if not self._live_started:
            self.start_live()

        if img.size != (self.info.width, self.info.height):
            img = img.resize((self.info.width, self.info.height))
        if img.mode != "RGB":
            img = img.convert("RGB")

        # The panel reports how it is physically mounted in `angle` (180 on
        # the XTRM Lab Spectra -- the ribbon comes out the top, so the
        # controller's native scan order is upside down relative to the
        # case). The firmware does NOT rotate for you; the vendor app
        # rotates its render instead. So do the same here, and callers can
        # just draw the right way up.
        rot = self.rotate if self.rotate is not None else self.info.angle
        if rot % 360:
            img = img.rotate(rot % 360, expand=True)
            if img.size != (self.info.panel_width, self.info.panel_height):
                img = img.resize((self.info.panel_width, self.info.panel_height))

        data = self._encode_jpeg(img)
        with self._write_lock:
            self._ser.write(data)
            self._ser.flush()

    # ------------------------------------------------------------------ #
    # convenience
    # ------------------------------------------------------------------ #
    def run(self, render_fn, fps: float = 1.0):
        """
        Convenience loop: repeatedly calls render_fn() -> PIL.Image and
        pushes the result to the screen at the given rate. Blocks until
        Ctrl+C. `render_fn` takes no arguments and should return a
        PIL.Image sized (or resizable) to the panel.

        Example:
            def render():
                img = Image.new("RGB", (screen.width, screen.height), "black")
                d = ImageDraw.Draw(img)
                d.text((10, 10), time.strftime("%H:%M:%S"), fill="white")
                return img

            screen.run(render, fps=1)
        """
        period = 1.0 / fps if fps > 0 else 1.0
        try:
            while True:
                start = time.time()
                img = render_fn()
                self.show(img)
                elapsed = time.time() - start
                time.sleep(max(0.0, period - elapsed))
        except KeyboardInterrupt:
            pass
