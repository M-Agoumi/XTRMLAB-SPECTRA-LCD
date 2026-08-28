# hongtai_screen — custom driver for the XTRM lab 6.2" LCD

**Working and verified on hardware.** 960x480, firmware 3.3, drawing
arbitrary Python-rendered frames.

This is a from-scratch Python client for the real protocol your case's
6.2" screen actually speaks. It was reverse-engineered by reading the
unobfuscated JavaScript source inside the vendor's own "XTRM lab" app
(`app.asar`), so it's not a guess — it's the exact wire protocol the
official app uses, reimplemented so you have full programmatic control
instead of just the vendor's theme editor.

Why the earlier attempt (the open-source `turing-smart-screen-python`
project) never worked: that tool speaks the *Turing Smart Screen*
protocol. Your panel's controller is made by a different OEM
(Dongguan Hongtai Technology) and uses a different protocol that only
superficially resembles it — the handshake succeeds either way, but
the actual draw commands are different, which is why nothing ever
appeared on screen with that tool.

## Which COM port?

Every script here auto-detects the panel by USB vendor ID (Hongtai
Technology's VID, shared across every rebrand of this hardware) — you
don't need to know or pass a port at all in the normal case:

```
python list_screens.py
```

lists every serial port on the machine and flags any that look like a
Hongtai-family screen. `COM3` is just what it happened to be detected as
here; it can easily be different on another machine (a different USB
port, other devices already using COM ports, etc.). If you have more than
one such screen plugged in, auto-detection can't pick one for you and
you'll need to pass the port explicitly, e.g. `python test_connection.py COM5`
or `HongtaiScreen("COM5")` in code — `list_screens.py` will tell you
exactly when that's the case.

## Hardware summary

- Controller: Hongtai Technology, USB-serial VID `33C3` (PID `7804` on
  this XTRM Lab unit specifically — other rebrands use other PIDs under
  the same VID, which is what auto-detection matches on)
- Baud rate: 2,000,000
- **DTR must be asserted (high).** This is the one setting that decides
  whether the panel talks back at all — with DTR low it receives your
  commands but never replies, and looks bricked. See the note in
  `hongtai_screen.py`.
- Model `TXW818-JD9161C-5.99inch-hor`, 960x480, firmware 3.3, mounted at
  `angle: 180`. All queried live from the panel, not hardcoded.
- The firmware does **not** apply its own mounting rotation — the host
  must send a pre-rotated frame. `show()` handles this from `info.angle`.
- Display mechanism: continuous JPEG stream (not a single
  "draw bitmap" command) — you render a frame, it gets JPEG-encoded
  and pushed over serial, repeat. A small heartbeat ping keeps the
  session alive between frames.

## Setup

```
pip install pyserial pillow
pip install psutil   # optional, only used by demo_clock.py for CPU/RAM bars
```

**Important:** only one program can hold the COM port at a time.
Close the vendor "XTRM lab" app first (check the system tray — if it
keeps relaunching itself, it's likely running as a background
Scheduled Task; disable that task too, as `\XTRM_lab` already is here).

Note: `smartscreen.exe` in Task Manager is **Windows Defender
SmartScreen**, not this panel's software. Ignore it.

## Files

- `hongtai_screen.py` — the library. Everything else imports this.
- `list_screens.py` — lists every serial port on the machine and flags
  which ones look like a Hongtai-family screen. Run this first if you're
  not sure a screen will be detected, or if you have more than one.
  ```
  python list_screens.py
  ```
- `test_connection.py` — run this next. Connects (auto-detecting the
  port), prints what the screen reports about itself, sets brightness,
  shows one static test frame for 5 seconds, then disconnects cleanly.
  ```
  python test_connection.py           # auto-detects the port
  python test_connection.py COM5      # or specify one explicitly
  ```
- `demo_clock.py` — a starter template showing continuous/live custom
  content: a clock plus CPU/RAM bars, redrawn once a second until you
  press Ctrl+C.
  ```
  python demo_clock.py                # auto-detects the port
  python demo_clock.py COM5           # or specify one explicitly
  ```
  Copy this file and edit `render_frame()` to build your own layout —
  it just needs to return a `PIL.Image` sized `(width, height)`; the
  library handles encoding, streaming, and the keepalive pings.
- `video_theme.py` — streams any video file you already have to the
  panel, frame by frame (letterboxed to fit, black bars if the aspect
  ratio doesn't match). Doesn't ship or fetch any video content itself —
  point it at your own file. Works well for flat, high-contrast
  animation (Bad Apple is the classic example) since that compresses to
  small JPEGs the panel's link can keep up with, but it's fully generic.
  ```
  python video_theme.py bad_apple.mp4               # auto-detects the port
  python video_theme.py bad_apple.mp4 --fps 20       # override playback rate
  python video_theme.py bad_apple.mp4 --bw           # force black & white
  python video_theme.py bad_apple.mp4 --audio        # also play the audio (needs ffmpeg + pygame)
  python video_theme.py bad_apple.mp4 COM5           # explicit port
  ```
  Extra dep: `pip install opencv-python-headless`. `--audio` additionally
  needs `pip install pygame` and `ffmpeg` on PATH; without those it just
  skips audio and plays silently.

## Library quick reference

```python
from hongtai_screen import HongtaiScreen
from PIL import Image

screen = HongtaiScreen()          # auto-detects the port; pass "COM5" etc. to be explicit
info = screen.connect()          # -> DeviceInfo(width, height, angle, version, uid, model, …)
screen.set_brightness(80)        # 0-100
screen.show(Image.new("RGB", (info.width, info.height), "black"))
screen.close()

# info.width / info.height are the logical canvas to draw on; rotation for
# the panel's mounting angle is applied for you inside show().
# info.panel_width / panel_height are the physical size (they only differ
# from the canvas at angle 90/270).
# screen.rotate = 0   # override the reported angle if it ever looks wrong

# or, for continuous content:
screen.run(lambda: my_frame(), fps=1.0)   # blocks; Ctrl+C to stop
```

## If the panel stops responding

`connect()` recovers on its own: when its retries run out it fires the
firmware's restart command (key=1) and tries again. To do it by hand:

```
python -c "from hongtai_screen import HongtaiScreen; HongtaiScreen().blind_restart()"
```

That one command is what un-wedges this panel — including from the state
where it answers nothing at all, since restart expects no reply. A full
mains power cycle does **not** fix it, and neither does `pnputil` or a DTR
pulse. See FINDINGS.md for the full list of what was tried.

If the panel is *silent* rather than merely black — nothing replies at all
— run `RUN_DIAG2.bat`, which sweeps the DTR/RTS line states and, if the
panel still says nothing, tries to draw blind without needing a reply.

Never open this device with `rtscts=True` — it hangs pyserial indefinitely.

## Status

Working end to end and verified on the physical panel. The protocol was
read out of the vendor app's own source (framing, handshake and command
set all match byte-for-byte) — see FINDINGS.md for the full protocol
reference, the two faults that blocked this, and the dead ends, so they
don't get re-explored later.

One small housekeeping note: a leftover copy of `app.asar`
(~58 MB, harmless) is still sitting in your
`Downloads\turing-screen` folder — it was locked by something when I
tried to clean it up. Feel free to delete it whenever, or let me know
and I'll try again.
