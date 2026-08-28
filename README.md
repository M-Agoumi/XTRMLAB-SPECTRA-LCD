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

Windows only (COM ports, plus WinRT for the Dashboard theme's Spotify
integration). No hardware other than the panel/case itself is needed.

## Quick start

```
git clone <this repo's URL>
cd hongtai_screen
pip install -r requirements.txt
python app.py
```

That's the desktop app with every theme available (see "Desktop app"
below for what it does). First run: make sure the vendor "XTRM lab" app
isn't running — only one program can hold the panel's COM port at a
time, see **Setup** below for how to fully close it. Then pick a theme
tab in the app and hit Start; nothing personal is bundled, so the
Dashboard tab's "nothing playing" picture and the Video tab's clip are
things you point at your own files (or just leave blank).

Only want one theme rather than the full desktop app, or don't want
every dependency installed? Skip `requirements.txt` and just
`pip install` that one theme's own line instead — each theme's section
below lists exactly what it needs, and installing only a subset is
fine; a theme that's missing something reports that clearly rather
than crashing the others.

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

## Desktop app (recommended way to run this)

```
python app.py
```

A GUI (Tkinter, ships with Python already) that wraps all four themes
below: pick the panel's port (or leave it on auto-detect), pick a theme
tab, fill in that theme's settings, hit Start. Stop switches themes or
lets you quit cleanly. Settings are remembered between runs
(`app_config.json`, created next to `app.py`).

Nothing personal is bundled -- the Dashboard tab's "nothing playing"
image and the Video tab's clip are both things you pick yourself with
the file-browser buttons; leave the Dashboard one unset and you get a
plain drawn placeholder icon instead, no file needed.

It needs whatever the theme you actually use needs (see that theme's
section below for its own `pip install` line) -- the GUI itself adds no
extra dependencies beyond Tkinter. If you only ever plan to use one
theme, `pip install`-ing just that theme's requirements is enough; a
theme that's missing a dependency reports it in the log when you hit
Start for that tab, it doesn't block the others.

Brightness always applies live, immediately, while something is
running -- no Stop/Start needed. On the Dashboard tab specifically, the
"nothing playing" image and the web mirror's on/off + port also apply
live, since dashboard_theme.py re-checks them continuously anyway.
Everything else (which video file, which URL, fps, loop, etc.) needs a
Stop then Start to take effect, since those mean reopening a different
file or connection.

The Dashboard tab's live web mirror (lets you watch the panel from a
phone on the same network) is off by default -- turning it on opens a
network listener, which makes Windows show a one-time firewall
permission prompt the first time it binds. That's expected if you
actually want it; leave it unticked if you don't want that prompt.

### Launching without a console window

Double-clicking `app.py` directly runs it through `python.exe`, which
opens a console window to host it -- and closing that console kills the
whole process (tray icon included), since there's nothing left to run
it. The app's own close-to-tray behavior only covers its own window
(the X button); it can't do anything about a console hosting it from
outside.

Run this once (Windows only):

```
python make_launcher.py
```

It writes `Launch Hongtai Screen.vbs` next to `app.py` -- double-click
that instead and it starts the app the same hidden way "Launch at
Windows startup" below does, with no console at all, so there's nothing
to accidentally close -- and, since a `.vbs` file's icon can't be
changed, also drops a proper "Hongtai Screen" shortcut with its own
icon (`icon.ico`) on your desktop that points at it, so you get a real
icon to double-click instead of a generic script file. Pass
`--no-desktop-icon` to skip that part and only write the `.vbs`.

### Running automatically at Windows startup

Tick "Launch at Windows startup" near the top of the window (Windows
only). This writes a small hidden-window launcher script into your
Startup folder that runs `pythonw app.py --autostart` at login -- no
console window, no need to log in and click Start yourself. It selects
the Dashboard tab and starts it using whatever settings you last saved.

For that to run with no window/taskbar entry at all (a proper
background/system-tray app instead of an open window), also install:

```
pip install pystray
```

With `pystray` installed, `--autostart` hides straight into a system
tray icon (right-click it for Show / Stop screen / Quit) instead of
leaving an open window in the taskbar. Without it, the window just
minimizes instead -- still runs, but stays visible in the taskbar.

You can also run autostart mode by hand:

```
python app.py --autostart                  # Dashboard tab
python app.py --autostart --theme video     # a different tab
```

## Setup

```
pip install -r requirements.txt
```

installs everything needed for the desktop app and all four themes (see
**Quick start** above). If you only want one theme, that theme's own
section below lists just its own dependencies — `pip install pyserial
pillow` is the true minimum shared by everything here.

**Important:** only one program can hold the COM port at a time.
Close the vendor "XTRM lab" app first (check the system tray — if it
keeps relaunching itself, it's likely running as a background
Scheduled Task; disable that task too).

Note: `smartscreen.exe` in Task Manager is **Windows Defender
SmartScreen**, not this panel's software. Ignore it.

## Files

- `app.py` — the desktop app (see "Desktop app" above). Recommended way
  to run this day to day.
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
  content: a clock plus CPU/RAM bars, redrawn at 10Hz until you press
  Ctrl+C.
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
  python video_theme.py bad_apple.mp4 --loop         # restart from the beginning when it ends
  python video_theme.py bad_apple.mp4 COM5           # explicit port
  ```
  Extra dep: `pip install opencv-python-headless`. `--audio` additionally
  needs `pip install pygame` and `ffmpeg` on PATH; without those it just
  skips audio and plays silently.
- `dashboard_theme.py` — a neon "cyberpunk panel" dashboard: full-circle
  glowing CPU LOAD / CPU TEMP gauges on the left, GPU LOAD / GPU TEMP on
  the right, and Spotify (or whatever's playing) album art in the
  middle with a glowing progress bar and the clock underneath it. Dark
  background with a faint hex-grid + circuit-trace texture. Each stat
  degrades independently instead of crashing if its dependency is
  missing:
  ```
  python dashboard_theme.py           # auto-detects the port
  python dashboard_theme.py COM5      # or specify one explicitly
  python dashboard_theme.py --default-art cover.jpg   # your own "nothing playing" image
  ```
  - CPU (left): uses `psutil`, already required above. Temperature only
    shows if the OS exposes it (mostly a Linux thing — on Windows
    you'll just see utilization, which is expected).
  - CPU temp specifically: Windows doesn't expose it through the API
    `psutil` uses (that's why it showed blank/N/A). Instead of a
    separate monitoring tool, this script spawns the XTRM lab app's
    *own* bundled sensor helper (`SystemInfos.exe`, found inside its
    install folder) and reads the same live sensor feed the vendor app
    itself uses to show CPU/GPU temp — no extra install needed. Needs
    to run as Administrator (same as the vendor app) so its driver can
    load; if that helper can't be found or spawned, it falls back to
    psutil, which on Windows usually means "–" instead of a number.
  - GPU (right): tries an NVIDIA GPU first via `pip install nvidia-ml-py`
    (importable as `pynvml`); if that's unavailable it falls back to
    the same `SystemInfos.exe` feed above, which also covers non-NVIDIA
    GPUs. "N/A" only if neither source has anything.
  - Album art (middle): reads Windows' own now-playing info (the same
    thing the volume flyout shows) via `pip install winsdk` — no
    Spotify API key needed, works with the Spotify desktop app. Needs
    Windows 10 1809+, and only ever shows Spotify specifically (other
    apps with a media session, e.g. a browser tab, are ignored on
    purpose). Nothing playing, or winsdk missing → shows a placeholder
    instead: a plain drawn icon by default, or `--default-art path.jpg`
    (or the desktop app's file picker) to use your own image. Nothing
    is bundled — pick whatever you want, or leave it unset.

  Each of CPU/GPU load and temp gets its own full-circle glowing gauge
  (electric cyan for CPU, neon magenta for GPU) with major ticks at
  0/25/50/75/100, minor ticks every 5, and a lit needle, on a dark
  hex-grid/circuit-trace background instead of flat cards. The gauges
  are drawn with `pycairo` rather than hand-drawn PIL shapes -- PIL's
  `draw.arc()` approximates a circle with straight segments, which is
  why the old version looked faceted/jagged up close; cairo draws true
  anti-aliased arcs and real linear/radial gradients, so the ring, the
  tapered gradient needle, and the glowing jewel-like hub all look
  smooth. Only the lit value arc, needle, hub, and value number redraw
  each frame -- the dim track, ticks, and titles are baked into the
  static background once at startup, so the nicer visuals don't cost
  extra render time. The album art has a glowing violet border and a
  live Spotify-style progress bar with `1:23 / 4:06` underneath it.
  That number comes from a background thread (the Windows now-playing
  call is a slow round trip and used to stall the whole render loop)
  and runs on its own free-running clock that ticks forward every
  second on its own, anchored on the timestamp Windows itself attaches
  to each position update (not on whenever our poll happened to
  complete) -- Spotify only pushes a fresh update occasionally, not on
  every poll, so anchoring on our own poll time made the estimate
  drift ahead between real updates and then visibly snap back once it
  drifted too far. It only snaps now when the real value disagrees by
  more than ~1.2s (an actual pause, seek, or track change). The main
  loop targets 10Hz and times itself so one slow frame doesn't drag the
  next ones late.

  Full dependency set for this one:
  `pip install numpy pycairo psutil nvidia-ml-py winsdk` (`numpy` and
  `pycairo` are required -- they draw the gauges -- the rest degrade
  independently as described above). `pycairo` installs from a
  prebuilt wheel on Windows, no separate Cairo install needed.
- `webpage_theme.py` — mirrors any webpage onto the panel using a
  headless Chromium browser (Playwright), at a viewport sized exactly
  to the panel's resolution so there's no scaling/letterboxing. The
  page stays open between screenshots, so any JS-driven content on it
  (a clock, a live dashboard, a stock ticker) keeps updating on its
  own — this just takes a fresh snapshot of it periodically.
  ```
  python webpage_theme.py https://example.com               # auto-detects the port, 10Hz by default
  python webpage_theme.py https://example.com --interval 2  # screenshot every 2s instead
  python webpage_theme.py https://example.com --reload-every 60  # force a full reload every 60s
  python webpage_theme.py https://example.com COM5          # explicit port
  ```
  Extra deps: `pip install playwright`, then a one-time
  `playwright install chromium` (~150MB browser download). A random
  full desktop site probably won't look great squeezed into ~960x480 —
  this is best pointed at something built for a small landscape screen
  (a simple status page, a clock/weather page, a Grafana panel, an .html
  file you wrote yourself), but there's nothing stopping you from
  pointing it at any URL.
## Watching the panel from a browser (live mirror)

Any script here can serve a live webpage that mirrors exactly what's
currently on the panel -- open it from a laptop or phone on the same
network to watch without standing in front of the case. It's a literal
mirror of the same frame being sent to the panel (not a separate
re-implementation), so there's nothing that can drift out of sync, and
it adds no extra dependencies (just Python's built-in `http.server`).

`dashboard_theme.py` turns it on automatically:

```
python dashboard_theme.py                  # prints the mirror's URL on startup
python dashboard_theme.py --web-port 9000   # use a different port
python dashboard_theme.py --no-web          # disable it
```

To add it to any other script (or your own), one line after `connect()`:

```python
screen = HongtaiScreen()
screen.connect()
screen.enable_web_mirror()   # prints the URL to open, e.g. http://192.168.1.42:8765/
```

Every `show()` call from then on also updates what the page displays.
The page itself just polls `/frame.jpg` a few times a second and shows
a live/no-signal indicator -- nothing to install, no separate server to
run.

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
