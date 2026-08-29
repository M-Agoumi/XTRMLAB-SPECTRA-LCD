"""
dashboard_theme.py -- a neon "cyberpunk dashboard" theme: separate
glowing CPU LOAD / CPU TEMP gauges on the left, GPU LOAD / GPU TEMP on
the right, and Spotify album art in the middle with playback progress
and the clock underneath it.

    python dashboard_theme.py               # auto-detects the port
    python dashboard_theme.py COM5           # explicit port
    python dashboard_theme.py --web-port 9000  # change the mirror's port
    python dashboard_theme.py --no-web      # disable the web mirror

Live web mirror: this also serves a webpage that mirrors whatever's
actually on the panel, in real time -- open the URL it prints (also
reachable from a phone on the same network) to watch the dashboard
without standing in front of the case. It's a literal mirror of the
exact frame being sent to the panel, not a separate re-implementation,
so there's nothing to keep in sync -- see enable_web_mirror() in
hongtai_screen.py, which any script here can use the same way.

Layout:

    +------------+----------------------+------------+
    |  CPU LOAD  |     [album art]      |  GPU LOAD  |
    |  (glowing  |    TRACK TITLE       |  (glowing  |
    |   ring)    |       artist         |   ring)    |
    +------------+  ===o=========== |  +------------+
    |  CPU TEMP  |    1:23 / 4:06        |  GPU TEMP  |
    |  (glowing  |       HH:MM:SS        |  (glowing  |
    |   ring)    |                       |   ring)    |
    +------------+----------------------+------------+

Each gauge is a full-circle neon dial (dim unlit track + a bright,
blurred/glowing filled arc + a lit needle) with major ticks at
0/25/50/75/100 and minor ticks every 5, on a dark background textured
with a faint hex grid and a handful of circuit-board trace lines for a
"cyberpunk panel" look instead of flat cards. The gauges themselves are
rendered with cairo (`pip install pycairo`) instead of hand-drawn PIL
polygons -- PIL's `draw.arc()` approximates a circle with straight
segments, which is what made the original gauges look faceted/jagged
up close; cairo draws true anti-aliased arcs and real gradients, so
the ring, the needle, and the glowing hub all look smooth at any size.
Only the glowing fill arc, needle, and value number are redrawn per
frame -- the ticks, dim track, background texture, and labels are
baked into a single static background image once at startup, which is
what keeps this fast enough to still hit a smooth refresh (see
"Refresh rate" below).

What each panel needs to work, and what happens if it's missing:

  - CPU (left): psutil, which you already have installed for
    demo_clock.py, for utilization. Temperature is a separate story on
    Windows -- see "CPU temperature" below, since psutil alone can't
    get it there.

  - GPU (right): needs an NVIDIA GPU + `pip install nvidia-ml-py`
    (that package's importable name is `pynvml`). If there's no NVIDIA
    GPU, or the driver library can't be found, that gauge just shows
    "N/A" instead of crashing the rest of the theme.

  - Spotify art + progress (middle): reads whatever is currently
    playing via Windows' own now-playing system (the same info the
    volume flyout / lock screen show) -- not the Spotify API, so
    there's no app to register or API key to get. Needs
    `pip install winsdk` and Windows 10 1809+. Works with the Spotify
    desktop app; if nothing is playing (or winsdk isn't installed), it
    shows a placeholder in place of album art instead, with no progress
    bar. That placeholder is a plain drawn icon by default -- pass
    --default-art to point it at your own image instead (nothing is
    bundled or assumed).
    That Windows call is a round trip to a system broker process and
    can take a second or more, so it's polled from its own background
    thread instead of the render loop -- the displayed position runs
    on its own free-running clock, anchored on the timestamp Windows
    attaches to each real update (not on whenever our poll happened to
    finish), and only snaps to the real value if the two disagree by
    more than ~1.2s (an actual pause, seek, or track change).

Refresh rate: the main loop targets 10Hz (redraws every ~100ms) and
times itself (like screen.run() does), sleeping only whatever's left
of that 100ms budget after everything else that frame needed -- CPU/GPU
reads, the SystemInfos.exe file read, rendering, and the JPEG
encode/send -- so one slow frame doesn't push every frame after it
late. 10Hz is a target, not a guarantee: a frame that's too large to
encode+transmit within ~100ms over the panel's 2 Mbaud link just makes
that one frame take longer, and the loop picks the pace back up on the
next one rather than trying to catch up.

CPU temperature (why it showed N/A):
    psutil.sensors_temperatures() is basically Linux-only -- Windows
    doesn't expose CPU temp through the API psutil uses at all, so
    "N/A" there wasn't a bug, it was Windows not offering the number.

    The XTRM lab app itself doesn't read it through Windows either --
    it ships its own helper, `SystemInfos.exe` (found inside the app's
    own install folder, under SDK/VC#/SystemInfos/.../Release/), which
    wraps CPUID's hardware SDK + a licensed HWiNFO sensor DLL and
    writes live sensor readings to a small file in %TEMP% once a
    second. This script spawns that exact helper itself and reads the
    same file -- no third-party monitoring tool needed, since the
    right tool was already installed on this machine the whole time.
    It's found automatically at the app's default install path; if
    yours is installed somewhere else, set SYSTEMINFOS_DIR below.
    Needs the script to run as Administrator the first time (same as
    the vendor app does) so its driver can load. If that helper can't
    be found or spawned, CPU temp falls back to psutil, which on
    Windows means it'll just show "--".

Install everything this theme can use:

    pip install pyserial pillow numpy pycairo psutil nvidia-ml-py winsdk

pycairo and numpy are required (they draw the gauges); the rest
degrade independently as described above.

You don't need all of them -- each stat degrades independently if its
dependency is missing.
"""

import argparse
import asyncio
import io
import json
import math
import os
import random
import struct
import subprocess
import tempfile
import threading
import time
import datetime

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

try:
    import cairo
except ImportError:  # pragma: no cover -- surfaced clearly at startup, see main()
    cairo = None

from hongtai_screen import HongtaiScreen

# ---------------------------------------------------------------- psutil ---

import psutil


CPU_UTIL_REFRESH = 0.5  # seconds -- CPU LOAD is *sampled* at 2Hz, independent
                         # of the main 10Hz render loop. psutil.cpu_percent()
                         # sampled every single frame was jittery/noisy at
                         # 10Hz (each call is just an instantaneous delta
                         # since the previous call, ~100ms apart), and simply
                         # holding that 2Hz reading flat for 5 frames then
                         # snapping to the next one made the needle visibly
                         # jump. Instead we glide from the previous sample to
                         # the new one linearly over the interval between
                         # samples, so the value returned to the renderer is
                         # slightly different every 10Hz frame and the needle
                         # moves smoothly instead of stepping.
_cpu_util_state = {"prev": None, "next": None, "sampled_at": 0.0}


def _get_cpu_util():
    now = time.time()
    state = _cpu_util_state
    if now - state["sampled_at"] >= CPU_UTIL_REFRESH:
        raw = psutil.cpu_percent(interval=None)
        state["prev"] = state["next"] if state["next"] is not None else raw
        state["next"] = raw
        state["sampled_at"] = now
    if state["next"] is None:
        return None
    if state["prev"] is None:
        return state["next"]
    frac = min(1.0, (now - state["sampled_at"]) / CPU_UTIL_REFRESH)
    return state["prev"] + (state["next"] - state["prev"]) * frac


def get_cpu_stats():
    """CPU load only now -- CPU temp used to live here too, but it's
    gone from this dashboard on purpose: the AIO panel shows CPU temp
    of its own, so duplicating it here was redundant (and see
    read_systeminfos()'s docstring for a real bug that used to make it
    show a frozen, wrong number half the time anyway)."""
    return {"util": _get_cpu_util()}


_ram_state = {"prev": None, "next": None, "sampled_at": 0.0}


def get_ram_percent():
    """Used-memory percentage, smoothed the same way _get_cpu_util() is
    (psutil's own number updates in coarse steps; interpolating between
    samples keeps the needle moving smoothly at this theme's 10Hz
    redraw rate instead of visibly stair-stepping)."""
    now = time.time()
    state = _ram_state
    if now - state["sampled_at"] >= CPU_UTIL_REFRESH:
        try:
            raw = psutil.virtual_memory().percent
        except Exception:  # noqa: BLE001
            return None
        state["prev"] = state["next"] if state["next"] is not None else raw
        state["next"] = raw
        state["sampled_at"] = now
    if state["next"] is None:
        return None
    if state["prev"] is None:
        return state["next"]
    frac = min(1.0, (now - state["sampled_at"]) / CPU_UTIL_REFRESH)
    return state["prev"] + (state["next"] - state["prev"]) * frac


def get_cpu_freq_ghz():
    """Current CPU clock speed in GHz -- one of this theme's selectable
    stats (see STAT_DEFS' "cpu_freq" entry for its fixed gauge ceiling,
    CPU_FREQ_GAUGE_MAX_GHZ). CPU temp itself isn't shown here at all
    (see get_cpu_stats()'s docstring: the AIO panel already covers it),
    so this is a different number entirely, not a smaller version of
    the same one."""
    try:
        freq = psutil.cpu_freq()
    except Exception:  # noqa: BLE001 -- not available on every platform
        return None
    if freq is None:
        return None
    return freq.current / 1000


def get_disk_usage_percent():
    """Used-space percentage of the system drive. No smoothing needed
    here unlike the other gauges -- disk usage barely moves between
    frames, so raw psutil output is already visually steady."""
    try:
        return psutil.disk_usage(os.path.abspath(os.sep)).percent
    except Exception:  # noqa: BLE001
        return None


NETWORK_GAUGE_MAX_MB_S = 20.0  # the gauge's 100% mark -- roughly 160Mbps
# combined up+down. A burst above this just pegs the needle at 100% while
# the printed number keeps showing the real value; tune to your own
# connection if 20MB/s is way off from what "full" looks like for you.
_NETWORK_SMOOTHING = 0.3  # 0-1, higher = follows raw jumps more closely
_net_state = {"prev_bytes": None, "prev_t": None, "smoothed": None}


def get_network_rate_mb_s():
    """Combined upload+download throughput in MB/s. Needs two samples to
    compute a rate at all (returns None on the very first call), and
    smooths the result a little -- a raw ~100ms-apart delta is jumpy
    enough to make the needle twitch distractingly otherwise."""
    try:
        counters = psutil.net_io_counters()
    except Exception:  # noqa: BLE001
        return None
    now = time.time()
    total = counters.bytes_sent + counters.bytes_recv
    state = _net_state
    prev_bytes, prev_t = state["prev_bytes"], state["prev_t"]
    state["prev_bytes"], state["prev_t"] = total, now
    if prev_bytes is None or now <= prev_t:
        return None
    rate = max(0.0, (total - prev_bytes) / (now - prev_t) / (1024 * 1024))
    state["smoothed"] = rate if state["smoothed"] is None else (
        state["smoothed"] + (rate - state["smoothed"]) * _NETWORK_SMOOTHING)
    return state["smoothed"]


DISK_IO_GAUGE_MAX_MB_S = 200.0  # same idea as NETWORK_GAUGE_MAX_MB_S's ceiling,
# just for local disk read+write instead of network -- tune to your drive
# (a fast NVMe can burst well past this; an old spinning disk far under it).
_DISK_IO_SMOOTHING = 0.3
_disk_io_state = {"prev_bytes": None, "prev_t": None, "smoothed": None}


def get_disk_io_mb_s():
    """Combined read+write throughput of the system's disks in MB/s --
    distinct from get_disk_usage_percent() (how full the drive is);
    this is how hard it's currently being hammered. Same two-sample/
    smoothing approach as get_network_rate_mb_s()."""
    try:
        counters = psutil.disk_io_counters()
    except Exception:  # noqa: BLE001
        return None
    if counters is None:
        return None
    now = time.time()
    total = counters.read_bytes + counters.write_bytes
    state = _disk_io_state
    prev_bytes, prev_t = state["prev_bytes"], state["prev_t"]
    state["prev_bytes"], state["prev_t"] = total, now
    if prev_bytes is None or now <= prev_t:
        return None
    rate = max(0.0, (total - prev_bytes) / (now - prev_t) / (1024 * 1024))
    state["smoothed"] = rate if state["smoothed"] is None else (
        state["smoothed"] + (rate - state["smoothed"]) * _DISK_IO_SMOOTHING)
    return state["smoothed"]


def get_swap_percent():
    """Used-swap percentage -- RAM's counterpart. No smoothing, same
    reasoning as get_disk_usage_percent(): it doesn't move fast enough
    between frames to need it."""
    try:
        return psutil.swap_memory().percent
    except Exception:  # noqa: BLE001
        return None


PROCESS_COUNT_MAX = 400.0  # gauge ceiling -- a "busy but normal" desktop
# usually sits well under this; tune it if your baseline process count
# runs a lot higher or lower.


def get_process_count():
    """Total running process count -- a rough, at-a-glance "how busy is
    this machine overall" number distinct from any single resource's
    load."""
    try:
        return float(len(psutil.pids()))
    except Exception:  # noqa: BLE001
        return None


_cpu_peak_state = {"prev": None, "next": None, "sampled_at": 0.0}


def get_cpu_load_peak_core():
    """Highest single core's utilization, smoothed the same way
    _get_cpu_util() smooths the overall average. On a many-core CPU the
    plain average (get_cpu_stats()) can look moderate while one core is
    actually pegged (a single-threaded task, for instance) -- this is
    the number that shows that."""
    now = time.time()
    state = _cpu_peak_state
    if now - state["sampled_at"] >= CPU_UTIL_REFRESH:
        try:
            per_core = psutil.cpu_percent(interval=None, percpu=True)
        except Exception:  # noqa: BLE001
            return None
        if not per_core:
            return None
        raw = max(per_core)
        state["prev"] = state["next"] if state["next"] is not None else raw
        state["next"] = raw
        state["sampled_at"] = now
    if state["next"] is None:
        return None
    if state["prev"] is None:
        return state["next"]
    frac = min(1.0, (now - state["sampled_at"]) / CPU_UTIL_REFRESH)
    return state["prev"] + (state["next"] - state["prev"]) * frac


def get_battery_percent():
    """Battery charge percentage, if this machine reports one at all --
    a desktop tower usually won't (returns None, which just shows "--"
    like any other unavailable stat), but a laptop or a UPS psutil can
    see will."""
    try:
        battery = psutil.sensors_battery()
    except Exception:  # noqa: BLE001
        return None
    return battery.percent if battery else None


# ------------------------------------------------------ SystemInfos.exe ---
# The XTRM lab app's own bundled sensor helper. It writes a small JSON
# blob to %TEMP%\<name>.bin (4-byte little-endian length prefix, then
# UTF-8 JSON) about once a second, keyed by app name -- this is exactly
# what the vendor app itself reads to show CPU/GPU temperature. See the
# module docstring for how this was found.

SYSTEMINFOS_DIR = r"C:\Program Files\XTRM lab\resources\main\SDK\VC#\SystemInfos\vs2008\bin\x64\Release"
SYSTEMINFOS_EXE = os.path.join(SYSTEMINFOS_DIR, "SystemInfos.exe")
SYSTEMINFOS_APP_NAME = "XTRM_lab"  # must match the vendor app's package.json "name"
SYSTEMINFOS_SHM_PATH = os.path.join(tempfile.gettempdir(), f"{SYSTEMINFOS_APP_NAME}.bin")

_systeminfos_proc = None


def start_systeminfos():
    """Spawn the vendor's own sensor-reading helper in the background,
    the same way their app does. Safe to call even if it's already
    running (e.g. because the XTRM lab app is also open) -- if the
    output file is already being updated, we just don't bother
    launching a second copy."""
    global _systeminfos_proc
    if _systeminfos_proc is not None or not os.path.exists(SYSTEMINFOS_EXE):
        return

    try:
        if time.time() - os.path.getmtime(SYSTEMINFOS_SHM_PATH) < 3.0:
            return  # something is already feeding this file
    except OSError:
        pass

    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        _systeminfos_proc = subprocess.Popen(
            [SYSTEMINFOS_EXE, SYSTEMINFOS_APP_NAME],
            cwd=SYSTEMINFOS_DIR,
            creationflags=creationflags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:  # noqa: BLE001
        _systeminfos_proc = None


def stop_systeminfos():
    global _systeminfos_proc
    if _systeminfos_proc is not None:
        try:
            _systeminfos_proc.terminate()
        except Exception:  # noqa: BLE001
            pass
        _systeminfos_proc = None


def read_systeminfos():
    """Read+parse the current frame. Returns None if the helper isn't
    running yet, hasn't written anything, isn't installed at the
    expected path, or -- and this is the case that actually matters
    here -- HAS written something before but has since stopped updating
    it (e.g. it needs Administrator to load its sensor driver and this
    app isn't running elevated, so it wrote one valid frame at startup
    and then silently exited): without a freshness check, a stopped
    helper's last frame just sits on disk and reads back as if it were
    live forever, showing a frozen, increasingly-wrong number (the
    literal "CPU temp always at 41C" bug) instead of "no data". The file
    is meant to update about once a second either way, so anything more
    than a few seconds stale is treated as no reading at all."""
    try:
        if time.time() - os.path.getmtime(SYSTEMINFOS_SHM_PATH) > 3.0:
            return None
        with open(SYSTEMINFOS_SHM_PATH, "rb") as f:
            head = f.read(4)
            if len(head) < 4:
                return None
            n = struct.unpack("<I", head)[0]
            if n == 0 or n > 65532:
                return None
            return json.loads(f.read(n).decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _sensor_value(frame, section_key, list_key):
    """Pull a value out of a SystemInfos frame the same way the vendor
    app does: frame[section_key][f"{list_key}_list"], preferring the
    sensor flagged "checked" and falling back to the first one."""
    if not frame:
        return None
    section = frame.get(section_key) or {}
    sensors = section.get(f"{list_key}_list") or []
    if not sensors:
        return None
    for s in sensors:
        if s.get("checked"):
            return s.get("value")
    return sensors[0].get("value")


# ----------------------------------------------------------------- pynvml --

try:
    import pynvml

    pynvml.nvmlInit()
    _gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
    _GPU_OK = True
except Exception:  # noqa: BLE001 -- no nvidia GPU, no driver, lib missing, etc.
    _GPU_OK = False


def get_gpu_stats(sysinfo_frame=None):
    if _GPU_OK:
        try:
            util = pynvml.nvmlDeviceGetUtilizationRates(_gpu_handle).gpu
            temp = pynvml.nvmlDeviceGetTemperature(_gpu_handle, pynvml.NVML_TEMPERATURE_GPU)
            return {"util": util, "temp": temp}
        except Exception:  # noqa: BLE001
            pass

    # Fall back to the same SystemInfos.exe feed used for CPU temp --
    # this also covers non-NVIDIA GPUs, since it's not NVML-specific.
    util = _sensor_value(sysinfo_frame, "graphics", "utilization")
    temp = _sensor_value(sysinfo_frame, "graphics", "temperature")
    if util is None and temp is None:
        return None
    return {"util": util, "temp": temp}


def get_vram_percent():
    """GPU memory used, as a percentage -- one of the two gauges flanking
    the clock. Only available when pynvml found an NVIDIA GPU (_GPU_OK
    below); None otherwise, which just draws that gauge's dim track."""
    if not _GPU_OK:
        return None
    try:
        mem = pynvml.nvmlDeviceGetMemoryInfo(_gpu_handle)
        return mem.used / mem.total * 100
    except Exception:  # noqa: BLE001
        return None


GPU_POWER_MAX_W = 350.0  # gauge ceiling -- a reasonable high-end-card TDP;
# tune it down for a lower-power card so the needle actually uses the dial.


def get_gpu_power_w():
    """Live GPU power draw in watts -- pynvml-only (no SystemInfos.exe
    fallback; the vendor feed this theme otherwise falls back to for
    non-NVIDIA GPUs doesn't expose this), so this is None on anything
    but an NVIDIA card, same graceful "--" as any other missing stat."""
    if not _GPU_OK:
        return None
    try:
        return pynvml.nvmlDeviceGetPowerUsage(_gpu_handle) / 1000.0
    except Exception:  # noqa: BLE001
        return None


# ----------------------------------------------------------------- winsdk --

try:
    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as MediaManager,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
    )
    from winsdk.windows.storage.streams import Buffer, InputStreamOptions

    _MEDIA_OK = True
except Exception:  # noqa: BLE001 -- not on Windows, or winsdk not installed
    _MEDIA_OK = False

# Cache the last decoded album art by (title, artist) so we don't
# re-decode a JPEG every single poll for a track that hasn't changed.
_art_cache_key = None
_art_cache_img = None


def _winrt_datetime_to_epoch(dt):
    """winsdk maps Windows.Foundation.DateTime to a Python datetime;
    treat it as UTC (Windows always reports it in UTC, but the object
    doesn't always come back tz-aware) and convert to a plain epoch
    timestamp comparable with time.time()."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.timestamp()


async def _get_media_info_async():
    manager = await MediaManager.request_async()

    session = None
    for s in manager.get_sessions():
        if "spotify" in (s.source_app_user_model_id or "").lower():
            session = s
            break
    # Deliberately NOT falling back to manager.get_current_session() when
    # no Spotify session is found -- that returns whatever Windows
    # considers the "current" now-playing session system-wide, which is
    # very often a browser tab with a media session registered (a
    # YouTube embed, a page with a <video>/<audio> element, even one
    # that isn't actually playing) rather than Spotify. That's why a
    # random webpage's title could show up here with Spotify closed --
    # this theme is specifically a Spotify display, so no Spotify
    # session found means "not playing" rather than "show whatever else
    # Windows has".
    if session is None:
        return None

    info = {
        "title": None, "artist": None, "art": None,
        "position": None, "duration": None, "playing": False,
    }

    global _art_cache_key, _art_cache_img
    try:
        props = await session.try_get_media_properties_async()
        info["title"] = props.title or None
        info["artist"] = props.artist or None

        key = (info["title"], info["artist"])
        if key == _art_cache_key and _art_cache_img is not None:
            info["art"] = _art_cache_img
        else:
            thumb_ref = props.thumbnail
            if thumb_ref is not None:
                stream = await thumb_ref.open_read_async()
                size = stream.size
                if size:
                    buf = Buffer(size)
                    await stream.read_async(buf, size, InputStreamOptions.READ_AHEAD)
                    data = bytes(bytearray(buf))
                    art = Image.open(io.BytesIO(data)).convert("RGB")
                    info["art"] = art
                    _art_cache_key, _art_cache_img = key, art
    except Exception:  # noqa: BLE001
        pass

    try:
        timeline = session.get_timeline_properties()
        if timeline.position is not None:
            info["position"] = timeline.position.total_seconds()
        if timeline.end_time is not None and timeline.start_time is not None:
            info["duration"] = (timeline.end_time - timeline.start_time).total_seconds()
        # Windows stamps *when* that position value was actually valid --
        # use that as our interpolation anchor instead of whenever our
        # own poll happened to finish. Position only changes when the
        # source app pushes a fresh timeline update (not on every poll),
        # so anchoring on our own poll time made the estimate drift
        # forward between real updates and then jump back once it
        # drifted too far -- anchoring on the real timestamp fixes both
        # the drift and the systematic lag from the WinRT round trip.
        if timeline.last_updated_time is not None:
            info["position_as_of"] = _winrt_datetime_to_epoch(timeline.last_updated_time)
    except Exception:  # noqa: BLE001
        pass

    try:
        playback = session.get_playback_info()
        info["playing"] = playback.playback_status == PlaybackStatus.PLAYING
    except Exception:  # noqa: BLE001
        pass

    return info


# The WinRT call above is a real round trip to a system broker process
# and can easily take a second or more -- calling it inline from the
# render loop was the actual cause of the sluggish refresh / progress
# jumping by more than a second at a time (the loop always slept a
# further 1s *on top* of however long that call took). It's polled from
# a dedicated background thread instead, with the render loop reading
# whatever the latest snapshot is and locally extrapolating the
# playback position between polls so it still ticks smoothly once a
# second even if the underlying poll itself is slower than that.

_media_lock = threading.Lock()
_media_latest = None  # dict with an extra "_polled_at" timestamp
_media_thread_started = False


def _media_poll_worker(poll_interval=1.0):
    global _media_latest
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    while True:
        try:
            result = loop.run_until_complete(_get_media_info_async())
        except Exception:  # noqa: BLE001
            result = None
        if result is not None:
            result["_polled_at"] = time.time()
        with _media_lock:
            _media_latest = result
        time.sleep(poll_interval)


def start_media_polling():
    global _media_thread_started
    if _media_thread_started or not _MEDIA_OK:
        return
    _media_thread_started = True
    threading.Thread(target=_media_poll_worker, daemon=True).start()


# Our own free-running clock for the progress bar: it ticks forward by
# real elapsed time every render frame regardless of how often (or how
# slowly) the background poll above actually completes -- like a
# stopwatch we started at the last known position. Whenever a fresh
# poll disagrees with where that stopwatch predicted we'd be by more
# than SYNC_TOLERANCE (a pause, seek, skip, or a real timeline update),
# we snap straight to the real value instead of drifting toward it.
SYNC_TOLERANCE = 1.2  # seconds of disagreement before we snap instead of drift

_progress_sync = {"track_key": None, "pos": None, "synced_at": None, "duration": None}


def get_media_info():
    """Latest media snapshot, non-blocking. `position` is our own
    ticking estimate of "right now", resynced against the real poll
    whenever the two disagree -- see SYNC_TOLERANCE above."""
    with _media_lock:
        snap = _media_latest
    if not snap:
        return None
    media = dict(snap)

    raw_pos = media.get("position")
    if raw_pos is None:
        return media

    now = time.time()
    # Anchor on Windows' own "as of" timestamp for this position value
    # when we have it -- it only changes when the source app actually
    # pushes a new timeline update, not on every poll -- and fall back
    # to our own poll time if it's missing for some reason.
    polled_at = media.get("position_as_of") or media.get("_polled_at", now)
    track_key = (media.get("title"), media.get("artist"))

    playing = media.get("playing")

    global _progress_sync
    if _progress_sync["track_key"] != track_key:
        # New track (or the very first poll) -- nothing to compare
        # against yet, so just adopt the real value outright.
        _progress_sync = {"track_key": track_key, "pos": raw_pos, "synced_at": polled_at,
                           "duration": media.get("duration")}
    elif not playing:
        # Paused: there's no extrapolation to protect, so just always
        # trust the real value directly rather than only on a big
        # mismatch -- this is what makes the frozen position land on the
        # actual moment playback stopped instead of whatever stale point
        # we last resynced from.
        _progress_sync["pos"] = raw_pos
        _progress_sync["synced_at"] = polled_at
        _progress_sync["duration"] = media.get("duration")
    else:
        predicted = _progress_sync["pos"] + (polled_at - _progress_sync["synced_at"])
        if abs(predicted - raw_pos) > SYNC_TOLERANCE:
            _progress_sync["pos"] = raw_pos
            _progress_sync["synced_at"] = polled_at
        _progress_sync["duration"] = media.get("duration")

    # Only run the stopwatch forward while something is actually playing.
    # It used to always add (now - synced_at), even while paused -- so a
    # real pause looked like the position kept climbing on its own (our
    # local clock ticking with nothing to anchor it) until the next poll
    # noticed the mismatch and snapped it back, which read as "jumping".
    # While paused, just hold at the exact synced position instead.
    if playing:
        display_pos = _progress_sync["pos"] + (now - _progress_sync["synced_at"])
    else:
        display_pos = _progress_sync["pos"]

    duration = _progress_sync["duration"]
    if duration:
        display_pos = min(display_pos, duration)
    media["position"] = max(0.0, display_pos)
    return media


# ---------------------------------------------------------------- drawing --
# A "cyberpunk panel" look: near-black background with a faint hex grid
# and circuit traces, full-circle neon gauges (dim track + a glowing
# filled arc + a lit needle), and a glowing frame around the album art.
# The static parts (background texture, dim gauge tracks, tick marks,
# labels) are baked into one image once at startup by
# build_static_background(); render_frame() only redraws the parts that
# actually change every second on top of a copy of it.

BG_TOP = (7, 6, 13)
BG_BOTTOM = (13, 8, 20)
PANEL_BORDER = (120, 40, 170)

ACCENT_CPU = (0, 220, 255)     # electric cyan
ACCENT_GPU = (235, 45, 225)    # neon magenta
ACCENT_MID = (225, 60, 235)    # violet-magenta, ties the middle column together

TICKS = (0, 25, 50, 75, 100)
# A near-full-circle sweep with a small gap at the bottom, in PIL's
# angle convention (0 = 3 o'clock, clockwise).
GAUGE_START = 125
GAUGE_END = 425

# The 4 big gauges' stat/title/range/format are no longer hardcoded to
# CPU/GPU load -- each of the 4 slots (top-left, bottom-left, top-right,
# bottom-right) independently picks any one of these (see app.py's
# Dashboard tab for the dropdowns, and run()'s `slots=` kwarg). Accent
# color is NOT part of this registry on purpose: it stays tied to which
# *column* a slot is in (left=cyan, right=magenta) regardless of which
# stat currently occupies it, so the two columns keep reading as
# "CPU-side" / "GPU-side" even after reassigning what's actually shown.
#
# Every gauge on the panel -- the 4 big ones AND the 4 smaller ones (the
# two flanking the album art, the two flanking the clock) -- picks from
# this same registry; there's nothing special about which stats can go
# in a "big" vs "small" slot. See SLOT_KINDS below for where each named
# slot actually sits and how big it is.
CPU_FREQ_GAUGE_MAX_GHZ = 6.0  # a fixed ceiling, same idea as NETWORK_GAUGE_MAX_MB_S --
# tune it if your CPU's boost clock is way above (or well below) this.
STAT_DEFS = {
    "cpu_load": {"label": "CPU Load", "title": "CPU LOAD", "min": 0, "max": 100,
                 "fmt": lambda v: f"{v:.0f}%"},
    "gpu_load": {"label": "GPU Load", "title": "GPU LOAD", "min": 0, "max": 100,
                 "fmt": lambda v: f"{v:.0f}%"},
    "ram": {"label": "RAM Usage", "title": "RAM", "min": 0, "max": 100,
            "fmt": lambda v: f"{v:.0f}%"},
    "network": {"label": "Network", "title": "NETWORK", "min": 0, "max": NETWORK_GAUGE_MAX_MB_S,
                "fmt": lambda v: f"{v:.1f}M/s"},
    "gpu_temp": {"label": "GPU Temp", "title": "GPU TEMP", "min": 0, "max": 100,
                 "fmt": lambda v: f"{v:.0f}°"},
    "cpu_freq": {"label": "CPU Freq", "title": "CPU FREQ", "min": 0, "max": CPU_FREQ_GAUGE_MAX_GHZ,
                 "fmt": lambda v: f"{v:.1f}G"},
    "disk_usage": {"label": "Disk Usage", "title": "DISK", "min": 0, "max": 100,
                   "fmt": lambda v: f"{v:.0f}%"},
    "vram_usage": {"label": "VRAM Usage", "title": "VRAM", "min": 0, "max": 100,
                   "fmt": lambda v: f"{v:.0f}%"},
    "swap": {"label": "Swap Usage", "title": "SWAP", "min": 0, "max": 100,
             "fmt": lambda v: f"{v:.0f}%"},
    "disk_io": {"label": "Disk Activity", "title": "DISK I/O", "min": 0, "max": DISK_IO_GAUGE_MAX_MB_S,
                "fmt": lambda v: f"{v:.0f}M/s"},
    "gpu_power": {"label": "GPU Power", "title": "GPU PWR", "min": 0, "max": GPU_POWER_MAX_W,
                  "fmt": lambda v: f"{v:.0f}W"},
    "process_count": {"label": "Processes", "title": "PROCESSES", "min": 0, "max": PROCESS_COUNT_MAX,
                       "fmt": lambda v: f"{v:.0f}"},
    "cpu_load_peak": {"label": "CPU Load (Peak Core)", "title": "CPU PEAK", "min": 0, "max": 100,
                       "fmt": lambda v: f"{v:.0f}%"},
    "battery": {"label": "Battery", "title": "BATTERY", "min": 0, "max": 100,
                "fmt": lambda v: f"{v:.0f}%"},
}
# 14 stats, 8 slots -- deliberately more of the former than the latter
# (see STAT_DEFS' own comment above about how it's registered) so
# picking a layout is a real choice, not just "which of exactly 8
# things goes in the one slot it fits."
DEFAULT_SLOTS = {
    "top_left": "cpu_load", "bottom_left": "ram",
    "top_right": "gpu_load", "bottom_right": "network",
    "left_secondary": "cpu_freq", "right_secondary": "gpu_temp",
    "left_mini": "disk_usage", "right_mini": "vram_usage",
}
# Which of the 8 slots are "big" (the 4 main gauges), "secondary" (the
# pair flanking the album art), or "mini" (the pair flanking the clock)
# -- drives gauge size and value-font choice generically in
# build_static_background()/render_frame() instead of hardcoding each
# slot by name.
SLOT_KINDS = {
    "top_left": "big", "bottom_left": "big", "top_right": "big", "bottom_right": "big",
    "left_secondary": "secondary", "right_secondary": "secondary",
    "left_mini": "mini", "right_mini": "mini",
}

# The panel background is its own small registry, same idea as
# STAT_DEFS -- see _build_background_image() for what each mode
# actually draws, and app.py's Dashboard tab for the picker + file
# browse button. "image" needs a real file at image_path to do
# anything; missing/unreadable silently falls back to "default"
# rather than erroring the whole theme out. "solid" used to just look
# like flat black -- BG_TOP/BG_BOTTOM (still used elsewhere as plain
# matte-fill colors, see fit_album_art()/placeholder_art()) are both
# extremely dark on purpose, so they read fine as a base *under* the
# hex grid/circuit texture but had basically no visible gradient of
# their own once that texture was stripped away. BACKGROUND_COLOR_
# SCHEMES below replaces that with an actual pick of gradients that
# read as a gradient with no texture at all.
BACKGROUND_PRESETS = {
    "default": "Default (hex grid + circuits)",
    "grid": "Simple grid",
    "starfield": "Starfield",
    "radial": "Radial glow",
    "solid": "Plain gradient",
    "image": "Custom image",
}
# Applies to every mode above except "image" (which is the photo itself)
# -- "default"'s hex grid and circuit traces keep their own fixed tint
# regardless of scheme (they're meant to read as CPU/GPU-side wiring,
# not as a color choice), but the gradient underneath them, and the
# starfield/grid/radial modes entirely, all use whichever scheme is
# picked here.
BACKGROUND_COLOR_SCHEMES = {
    "purple": {"label": "Purple", "top": (24, 14, 46), "bottom": (5, 4, 11)},
    "blue": {"label": "Ocean Blue", "top": (8, 28, 52), "bottom": (2, 5, 12)},
    "crimson": {"label": "Crimson", "top": (46, 10, 18), "bottom": (10, 3, 5)},
    "emerald": {"label": "Emerald", "top": (8, 42, 26), "bottom": (2, 8, 5)},
    "mono": {"label": "Monochrome", "top": (34, 34, 36), "bottom": (6, 6, 7)},
}
DEFAULT_SCHEME = "purple"
DEFAULT_BACKGROUND = {"mode": "default", "scheme": DEFAULT_SCHEME, "image_path": None}


def dim_color(color, factor):
    return tuple(max(0, min(255, int(c * factor))) for c in color)


def load_font(size, bold=False):
    """`bold=True` specifically picks a bold font FILE (arial.ttf itself
    has no weight axis PIL can fake convincingly), so it needs its own
    candidate list -- "arial.ttf" bumped to bold is still just arial.ttf
    to PIL. Windows ships arialbd.ttf/segoeuib.ttf alongside the regular
    weights, which is what actually renders bold there."""
    if bold:
        candidates = ("DejaVuSans-Bold.ttf", "arialbd.ttf", "segoeuib.ttf", "Arial Bold.ttf")
    else:
        candidates = ("DejaVuSans.ttf", "arial.ttf", "segoeui.ttf")
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def rounded_rect(draw, box, radius, **kwargs):
    try:
        draw.rounded_rectangle(box, radius=radius, **kwargs)
    except AttributeError:  # very old Pillow without rounded_rectangle
        draw.rectangle(box, **kwargs)


def glow_paste(base_img, tile, box, blur=7, glow_alpha=0.55):
    """Composite `tile` (an RGBA image) onto base_img at `box`, with a
    soft blurred bloom underneath a crisp sharp copy on top."""
    glow = tile.filter(ImageFilter.GaussianBlur(blur))
    r, g, b, a = glow.split()
    a = a.point(lambda v: int(v * glow_alpha))
    glow = Image.merge("RGBA", (r, g, b, a))
    base_img.paste(glow, box, glow)
    base_img.paste(tile, box, tile)


def draw_hex_grid(draw, width, height, size=24, color=(64, 52, 96), width_px=1):
    # Brighter + thicker than the original (30, 24, 46) at 1px polygon
    # outline -- that contrast against the near-black background was
    # subtle enough on a monitor and got crushed further by the panel's
    # small size, JPEG compression, and viewing angle, to the point of
    # being basically invisible on the actual hardware. Drawn as
    # explicit line segments (rather than draw.polygon(), which has no
    # width control) so the line width can be bumped for visibility.
    hex_w = math.sqrt(3) * size
    row_h = 1.5 * size
    row = 0
    y = -size
    while y < height + size:
        x_offset = (hex_w / 2) if row % 2 else 0
        x = -hex_w + x_offset
        while x < width + hex_w:
            pts = [
                (x + size * math.cos(math.radians(60 * i - 30)),
                 y + size * math.sin(math.radians(60 * i - 30)))
                for i in range(6)
            ]
            pts.append(pts[0])
            draw.line(pts, fill=color, width=width_px, joint="curve")
            x += hex_w
        y += row_h
        row += 1


def draw_circuit_traces(draw, width, height, seed=7, count=16):
    rng = random.Random(seed)
    # Also brightened (was 0.22) and drawn 2px wide (was 1px) for the
    # same reason as the hex grid above -- too faint to read on the
    # actual panel.
    palette = [dim_color(ACCENT_CPU, 0.4), dim_color(ACCENT_GPU, 0.4)]
    for _ in range(count):
        x, y = rng.randint(0, width), rng.randint(0, height)
        color = rng.choice(palette)
        pts = [(x, y)]
        for _ in range(rng.randint(2, 4)):
            if rng.random() < 0.5:
                x += rng.choice((-1, 1)) * rng.randint(20, 70)
            else:
                y += rng.choice((-1, 1)) * rng.randint(20, 70)
            pts.append((x, y))
        draw.line(pts, fill=color, width=2)
        for px, py in (pts[0], pts[-1]):
            draw.ellipse([px - 3, py - 3, px + 3, py + 3], fill=color)


def gauge_layout(cx, cy, radius):
    ring_w = max(6, radius * 0.11)
    pad = int(ring_w * 3 + 24)
    size = int(radius * 2 + pad * 2)
    return {"cx": cx, "cy": cy, "radius": radius, "ring_w": ring_w, "pad": pad, "size": size}


def _gauge_box(g):
    """Top-left corner to paste a gauge tile at so it lands centered on
    (cx, cy) -- both the static and dynamic tiles for a given gauge are
    the same size, so this box is shared by both."""
    half = g["size"] / 2
    return (int(g["cx"] - half), int(g["cy"] - half))


def _surface_to_pil(surface):
    """cairo hands back premultiplied-alpha ARGB32 (and BGRA byte order
    on a little-endian machine); PIL composites straight-alpha, so a
    naive wrap of the raw buffer double-darkens every anti-aliased edge
    pixel. Unpremultiply through numpy instead of doing it byte-by-byte
    in Python, since this runs once per gauge per frame."""
    surface.flush()
    w, h = surface.get_width(), surface.get_height()
    stride = surface.get_stride()
    arr = np.ndarray(shape=(h, stride), dtype=np.uint8, buffer=surface.get_data()).copy()
    arr = arr[:, : w * 4].reshape(h, w, 4)
    b, g_, r, a = (arr[..., i].astype(np.float32) for i in range(4))
    af = np.where(a == 0, 1.0, a) / 255.0
    rgb = np.dstack([np.clip(ch / af, 0, 255) for ch in (r, g_, b)]).astype(np.uint8)
    out = np.dstack([rgb, a.astype(np.uint8)])
    return Image.fromarray(out, "RGBA")


def _cairo_rgba(color, alpha=1.0):
    return (color[0] / 255, color[1] / 255, color[2] / 255, alpha)


def draw_gauge_static(g, accent):
    """The parts that never change: the dim track ring (with a soft drop
    shadow and a gradient sweep for a bit of depth), its crisp edge
    lines, and major/minor tick marks -- all real anti-aliased cairo
    arcs instead of PIL's straight-segment `draw.arc()`. Returns an RGBA
    tile sized g['size']; paste it at _gauge_box(g)."""
    radius, ring_w, size = g["radius"], g["ring_w"], g["size"]
    cx = cy = size / 2
    a0, a1 = math.radians(GAUGE_START), math.radians(GAUGE_END)

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    ctx = cairo.Context(surface)

    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_source_rgba(0, 0, 0, 0.35)
    ctx.set_line_width(ring_w + 3)
    ctx.arc(cx, cy + 1.5, radius, a0, a1)
    ctx.stroke()

    # Track ring opacity was tuned back when the background behind it was
    # much darker/flatter -- once the hex grid + circuit traces got
    # brightened for visibility, that same low alpha let the busier
    # background bleed straight through the ring, making it look washed
    # out/low-opacity instead of like a solid dim dial. Bumped up
    # (0.22/0.10 -> 0.55/0.34) so the ring reads as a ring regardless of
    # what's behind it, and the edge lines/minor ticks got the same
    # treatment.
    track_grad = cairo.LinearGradient(cx - radius, cy - radius, cx + radius, cy + radius)
    track_grad.add_color_stop_rgba(0, *_cairo_rgba(accent, 0.55))
    track_grad.add_color_stop_rgba(1, *_cairo_rgba(accent, 0.34))
    ctx.set_source(track_grad)
    ctx.set_line_width(ring_w)
    ctx.arc(cx, cy, radius, a0, a1)
    ctx.stroke()

    ctx.set_source_rgba(*_cairo_rgba(accent, 0.6))
    ctx.set_line_width(1)
    ctx.arc(cx, cy, radius + ring_w / 2, a0, a1)
    ctx.stroke()
    ctx.arc(cx, cy, radius - ring_w / 2, a0, a1)
    ctx.stroke()

    ctx.set_line_cap(cairo.LINE_CAP_BUTT)
    for t in range(0, 101, 5):
        ang = math.radians(GAUGE_START + (GAUGE_END - GAUGE_START) * t / 100)
        cosA, sinA = math.cos(ang), math.sin(ang)
        major = t in TICKS
        r1 = radius - ring_w / 2 - 2
        r2 = radius - ring_w / 2 - (13 if major else 8)
        ctx.set_source_rgba(*_cairo_rgba(accent, 0.95 if major else 0.55))
        ctx.set_line_width(2.2 if major else 1.4)
        ctx.move_to(cx + r1 * cosA, cy + r1 * sinA)
        ctx.line_to(cx + r2 * cosA, cy + r2 * sinA)
        ctx.stroke()

    return _surface_to_pil(surface)


def draw_tick_labels(draw, g, font_tick):
    """The 0/25/50/75/100 numbers -- kept as PIL text (drawn straight
    onto the static background) rather than cairo, since PIL's font
    rendering is already what the rest of this theme's text uses."""
    cx, cy, radius, ring_w = g["cx"], g["cy"], g["radius"], g["ring_w"]
    for t in TICKS:
        ang = math.radians(GAUGE_START + (GAUGE_END - GAUGE_START) * t / 100)
        cosA, sinA = math.cos(ang), math.sin(ang)
        tx, ty = cx + (radius + ring_w / 2 + 15) * cosA, cy + (radius + ring_w / 2 + 15) * sinA
        draw.text((tx, ty), str(t), font=font_tick, fill=(140, 142, 158), anchor="mm")


def draw_gauge_dynamic_tile(g, value, min_v, max_v, accent):
    """The parts that change every frame: the lit value arc, the needle,
    and the glowing hub, plus a blurred glow pass underneath them.
    Returns an RGBA tile sized g['size'] (paste at _gauge_box(g)), or
    None if value is None -- callers should leave the dim static track
    showing with no needle at all rather than pointing at "0", which
    would read as a real (if low) reading instead of "no data"."""
    if value is None:
        return None

    radius, ring_w, size = g["radius"], g["ring_w"], g["size"]
    cx = cy = size / 2
    a0 = math.radians(GAUGE_START)

    pct = max(0.0, min(100.0, (value - min_v) / (max_v - min_v) * 100.0))
    val_angle = math.radians(GAUGE_START + (GAUGE_END - GAUGE_START) * pct / 100)

    needle_len = radius - ring_w * 0.35
    base_w = ring_w * 0.34
    tip = (cx + needle_len * math.cos(val_angle), cy + needle_len * math.sin(val_angle))
    perp = val_angle + math.pi / 2
    bx, by = math.cos(perp) * base_w, math.sin(perp) * base_w
    back = ring_w * 0.4
    backx, backy = cx - back * math.cos(val_angle), cy - back * math.sin(val_angle)
    hub_r = ring_w * 0.62
    dim_accent = tuple(int(c * 0.55) for c in accent)
    dark_accent = tuple(int(c * 0.4) for c in accent)

    def paint(ctx, solid):
        """Draws the value arc + needle + hub. `solid` fills everything
        flat white-on-accent (used to build the glow-source silhouette);
        otherwise it's the real gradient-shaded version drawn on top."""
        if pct > 0:
            ctx.set_line_cap(cairo.LINE_CAP_ROUND)
            if solid:
                ctx.set_source_rgba(*_cairo_rgba(accent, 1))
            else:
                grad = cairo.LinearGradient(cx - radius, cy - radius, cx + radius, cy + radius)
                grad.add_color_stop_rgba(0, *_cairo_rgba(dim_accent, 1))
                grad.add_color_stop_rgba(1, *_cairo_rgba(accent, 1))
                ctx.set_source(grad)
            ctx.set_line_width(ring_w)
            ctx.arc(cx, cy, radius, a0, val_angle)
            ctx.stroke()

        if solid:
            ctx.set_source_rgba(*_cairo_rgba(accent, 1))
        else:
            needle_grad = cairo.LinearGradient(cx, cy, tip[0], tip[1])
            needle_grad.add_color_stop_rgba(0, 1, 1, 1, 0.95)
            needle_grad.add_color_stop_rgba(1, *_cairo_rgba(accent, 1))
            ctx.set_source(needle_grad)
        ctx.move_to(backx + bx, backy + by)
        ctx.line_to(tip[0], tip[1])
        ctx.line_to(backx - bx, backy - by)
        ctx.close_path()
        ctx.fill()

        if solid:
            ctx.set_source_rgba(*_cairo_rgba(accent, 1))
        else:
            hub_grad = cairo.RadialGradient(cx - hub_r * 0.3, cy - hub_r * 0.3, hub_r * 0.1, cx, cy, hub_r)
            hub_grad.add_color_stop_rgba(0, 1, 1, 1, 1)
            hub_grad.add_color_stop_rgba(0.5, *_cairo_rgba(accent, 1))
            hub_grad.add_color_stop_rgba(1, *_cairo_rgba(dark_accent, 1))
            ctx.set_source(hub_grad)
        ctx.arc(cx, cy, hub_r, 0, 2 * math.pi)
        ctx.fill()
        if not solid:
            ctx.set_source_rgba(*_cairo_rgba(accent, 0.8))
            ctx.set_line_width(1.2)
            ctx.arc(cx, cy, hub_r, 0, 2 * math.pi)
            ctx.stroke()

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    paint(cairo.Context(surface), solid=False)
    tile = _surface_to_pil(surface)

    glow_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    paint(cairo.Context(glow_surface), solid=True)
    glow = _surface_to_pil(glow_surface).filter(ImageFilter.GaussianBlur(radius * 0.045 + 3))
    r, g_, b, al = glow.split()
    al = al.point(lambda v: int(v * 0.6))
    glow = Image.merge("RGBA", (r, g_, b, al))

    out = Image.new("RGBA", tile.size, (0, 0, 0, 0))
    out.alpha_composite(glow)
    out.alpha_composite(tile)
    return out


def draw_gauge_dynamic(img, g, value, min_v, max_v, accent, font_value, value_fmt):
    tile = draw_gauge_dynamic_tile(g, value, min_v, max_v, accent)
    if tile is not None:
        img.alpha_composite(tile, _gauge_box(g)) if img.mode == "RGBA" else img.paste(tile, _gauge_box(g), tile)

    draw = ImageDraw.Draw(img)
    cx, cy, radius = g["cx"], g["cy"], g["radius"]
    value_str = value_fmt(value) if value is not None else "--"
    draw.text((cx, cy + radius * 0.32), value_str, font=font_value, fill=(255, 255, 255), anchor="mm")


def fit_album_art(art_img, size, radius):
    """Cover-fit: scale so the image fully fills the square art frame
    (no letterbox bars), then center-crop whichever dimension overflows.
    (Used to be a contain-fit -- thumbnail() + pad -- which left black
    bars above/below or left/right of any art that wasn't already
    square.)"""
    img = art_img.copy()
    src_w, src_h = img.size
    scale = max(size / src_w, size / src_h)
    new_w, new_h = max(1, round(src_w * scale)), max(1, round(src_h * scale))
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left, top = (new_w - size) // 2, (new_h - size) // 2
    img = img.crop((left, top, left + size, top + size))

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    rounded = Image.new("RGB", (size, size), BG_TOP)
    rounded.paste(img, (0, 0), mask)
    return rounded


def placeholder_art(size, radius):
    canvas = Image.new("RGB", (size, size), (18, 15, 26))
    draw = ImageDraw.Draw(canvas)
    r = size * 0.15
    cx, cy = size / 2, size / 2
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(120, 90, 150), width=3)
    draw.ellipse([cx - r * 0.28, cy - r * 0.28, cx + r * 0.28, cy + r * 0.28], fill=(120, 90, 150))

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    rounded = Image.new("RGB", (size, size), BG_TOP)
    rounded.paste(canvas, (0, 0), mask)
    return rounded


# Shown in place of album art whenever nothing is playing (or Spotify/
# winsdk data isn't available at all). No file is bundled or assumed by
# default -- this theme ships with no personal image baked in; set
# DEFAULT_ART_PATH (or pass --default-art / the GUI's file picker) to
# point at whatever image you want, or leave it unset and the plain
# drawn placeholder below is used instead. Loaded once and cached since
# it doesn't change frame to frame; falls back to the drawn placeholder
# if the path is unset, missing, or fails to load, so this never crashes
# over a bad/missing file.
DEFAULT_ART_PATH = None
_default_art_cache = None  # PIL Image once loaded, or False if load failed
_default_art_cache_path = None  # which path _default_art_cache was loaded from


def set_default_art_path(path):
    """Point the "nothing playing" placeholder at a specific image file
    (or None to go back to the plain drawn placeholder)."""
    global DEFAULT_ART_PATH
    DEFAULT_ART_PATH = path


def _load_default_art():
    global _default_art_cache, _default_art_cache_path
    if DEFAULT_ART_PATH is None:
        return None
    if _default_art_cache_path != DEFAULT_ART_PATH:
        try:
            _default_art_cache = Image.open(DEFAULT_ART_PATH).convert("RGB")
        except Exception:  # noqa: BLE001
            _default_art_cache = False
        _default_art_cache_path = DEFAULT_ART_PATH
    return _default_art_cache or None


def default_art(size, radius):
    img = _load_default_art()
    if img is not None:
        return fit_album_art(img, size, radius)
    return placeholder_art(size, radius)


def art_glow_frame(size, radius, accent, inset=7):
    """A soft neon border tile sized around the album art, drawn just
    outside its edges (not on top of it) so pasting the opaque art
    image afterward doesn't cover most of the stroke."""
    pad = inset + 20
    tile = Image.new("RGBA", (size + pad * 2, size + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    d.rounded_rectangle([pad - inset, pad - inset, pad + size - 1 + inset, pad + size - 1 + inset],
                         radius=radius + inset, outline=accent + (255,), width=3)
    return tile, pad


# Shown (wrapped across as many lines as it needs) in place of a track
# title whenever nothing is currently playing.
NOT_PLAYING_MESSAGE = "Life is like a door never trust a cow because the sun can't swim"


def truncate(draw, text, font, max_w):
    if not text:
        return ""
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text + "…"


def wrap_text(draw, text, font, max_w, max_lines=None):
    """Greedy word-wrap into lines that each fit max_w -- unlike
    truncate(), nothing is cut off/ellipsized; every word in `text`
    ends up somewhere (unless max_lines is hit, in which case the
    remainder is dropped rather than overflowing)."""
    words = text.split()
    lines = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_w or not line:
            line = candidate
        else:
            lines.append(line)
            line = word
            if max_lines is not None and len(lines) >= max_lines:
                return lines
    if line:
        lines.append(line)
    if max_lines is not None:
        lines = lines[:max_lines]
    return lines


def fmt_mmss(seconds):
    if seconds is None:
        return "--:--"
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


def progress_bar_glow(img, x, y, w, h, fraction, accent):
    draw = ImageDraw.Draw(img)
    rounded_rect(draw, [x, y, x + w, y + h], radius=h / 2, fill=dim_color(accent, 0.22))

    fill_w = int(w * max(0.0, min(1.0, fraction)))
    if fill_w > h:
        tile = Image.new("RGBA", (w + 20, h + 20), (0, 0, 0, 0))
        d = ImageDraw.Draw(tile)
        rounded_rect(d, [10, 10, 10 + fill_w, 10 + h], radius=h / 2, fill=accent + (255,))
        glow_paste(img, tile, (x - 10, y - 10), blur=5, glow_alpha=0.5)

    knob_x = x + fill_w
    knob_r = h * 1.7
    draw = ImageDraw.Draw(img)
    draw.ellipse([knob_x - knob_r, y + h / 2 - knob_r, knob_x + knob_r, y + h / 2 + knob_r],
                 fill=(255, 255, 255))


class Fonts:
    def __init__(self):
        self.gauge_title = load_font(15)
        self.gauge_value = load_font(26)
        self.small_title = load_font(11)   # the compact GPU-temp gauge's title
        self.small_value = load_font(15)   # and its value -- gauge_value is too big for it
        self.tick = load_font(12)
        self.time = load_font(24)
        self.track = load_font(19)
        self.artist = load_font(15, bold=True)
        self.progress = load_font(15)
        self.message = load_font(22)  # the "nothing playing" message -- bigger, meant to be read


def _linear_gradient(width, height, top_color, bottom_color):
    """Vectorized top-to-bottom gradient via numpy -- the original
    per-pixel Python double loop (~460k iterations at 960x480) worked
    but there's no reason to pay that cost now that this runs for every
    mode, including ones with no texture drawn on top to hide banding."""
    t = np.linspace(0, 1, height, dtype=np.float32).reshape(height, 1, 1)
    top = np.array(top_color, dtype=np.float32).reshape(1, 1, 3)
    bottom = np.array(bottom_color, dtype=np.float32).reshape(1, 1, 3)
    arr = np.broadcast_to(top + (bottom - top) * t, (height, width, 3))
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def _radial_gradient(width, height, center_color, edge_color):
    """A soft glow centered on the panel, fading to `edge_color` at the
    corners -- vectorized the same way as _linear_gradient() above."""
    yy, xx = np.mgrid[0:height, 0:width]
    cx, cy = width / 2, height / 2
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    t = np.clip(dist / math.hypot(cx, cy), 0, 1)[..., np.newaxis]
    center = np.array(center_color, dtype=np.float32)
    edge = np.array(edge_color, dtype=np.float32)
    arr = center + (edge - center) * t
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def draw_starfield(draw, width, height, seed=11, count=140):
    """A scattering of small static "stars" -- deterministic (fixed
    seed) so the pattern doesn't visibly change between Starts, same as
    the hex grid/circuit traces it stands in for as a lighter-weight,
    less "circuit board" alternative texture."""
    rng = random.Random(seed)
    for _ in range(count):
        x, y = rng.randint(0, width), rng.randint(0, height)
        r = rng.choice((0.6, 0.6, 0.8, 1.0, 1.4))
        b = rng.randint(110, 230)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(b, b, min(255, b + 15)))


def draw_simple_grid(draw, width, height, spacing=44, color=(70, 76, 100)):
    """A plain rectangular grid -- a calmer alternative to the hex grid
    for anyone who wants *some* structure without the full "circuit
    board" look."""
    for x in range(0, width, spacing):
        draw.line([(x, 0), (x, height)], fill=color, width=1)
    for y in range(0, height, spacing):
        draw.line([(0, y), (width, y)], fill=color, width=1)


def _build_background_image(width, height, background):
    """The part of the panel background that varies by BACKGROUND_PRESETS
    mode -- everything else in build_static_background() (border, gauges)
    is drawn on top of whatever this returns.

    "default": a gradient (see BACKGROUND_COLOR_SCHEMES) plus the
    hex-grid + circuit-trace texture. "grid"/"starfield": the same
    gradient with a lighter-weight texture instead. "radial": a glow
    centered on the panel rather than a top-to-bottom gradient. "solid":
    just the gradient, no texture at all. "image": a user-supplied
    photo, cover-fit to the panel and darkened -- the gauges/text here
    are all designed to sit on a near-black background, so a bright
    photo behind them unmodified would wreck their legibility; a bad or
    missing path (or an unreadable file) just falls back to "default"
    silently rather than failing the whole theme."""
    mode = (background or {}).get("mode", "default")
    image_path = (background or {}).get("image_path")

    if mode == "image" and image_path:
        try:
            src = Image.open(image_path).convert("RGB")
            img = ImageOps.fit(src, (width, height), method=Image.LANCZOS)
            overlay = Image.new("RGB", (width, height), (0, 0, 0))
            return Image.blend(img, overlay, 0.45)
        except Exception:  # noqa: BLE001 -- bad/missing file, corrupt image, etc.
            mode = "default"

    scheme = BACKGROUND_COLOR_SCHEMES.get((background or {}).get("scheme"),
                                            BACKGROUND_COLOR_SCHEMES[DEFAULT_SCHEME])
    top_color, bottom_color = scheme["top"], scheme["bottom"]

    if mode == "radial":
        return _radial_gradient(width, height, top_color, bottom_color)

    img = _linear_gradient(width, height, top_color, bottom_color)
    if mode == "default":
        draw = ImageDraw.Draw(img)
        draw_hex_grid(draw, width, height)
        draw_circuit_traces(draw, width, height)
    elif mode == "grid":
        draw_simple_grid(ImageDraw.Draw(img), width, height)
    elif mode == "starfield":
        draw_starfield(ImageDraw.Draw(img), width, height)
    # mode == "solid": the gradient above, with nothing drawn over it.
    return img


def build_static_background(width, height, fonts, slots=None, background=None):
    """Everything that doesn't change frame to frame: the background
    (see _build_background_image()/BACKGROUND_PRESETS), the panel
    border, and all 8 gauges' dim tracks/ticks/titles -- the 4 big ones
    plus the 2 secondary ones flanking the album art and the 2 mini
    ones flanking the clock (whichever stat each slot is currently
    assigned -- see STAT_DEFS/DEFAULT_SLOTS/SLOT_KINDS). Returns
    (image, layout).

    `slots` maps any of SLOT_KINDS' 8 keys to a STAT_DEFS key; missing
    entries fall back to DEFAULT_SLOTS -- any stat can go in any slot,
    big or small. `background` maps "mode" (a BACKGROUND_PRESETS key),
    "scheme" (a BACKGROUND_COLOR_SCHEMES key), and "image_path"; missing
    entries fall back to DEFAULT_BACKGROUND. Both are baked into this
    static image, so changing either mid-stream needs a fresh call to
    this (i.e. a Stop/Start, or the GUI's Apply button) to take effect
    -- same as every other "needs a restart" setting in this theme.
    """
    slots = dict(DEFAULT_SLOTS, **(slots or {}))
    background = dict(DEFAULT_BACKGROUND, **(background or {}))

    img = _build_background_image(width, height, background)
    draw = ImageDraw.Draw(img)

    margin = int(width * 0.015)
    rounded_rect(draw, [margin, margin, width - margin, height - margin],
                 radius=10, outline=dim_color(PANEL_BORDER, 0.7), width=2)

    col_w = int(width * 0.235)
    gauge_area_top = int(height * 0.07)
    gauge_area_bottom = int(height * 0.93)
    gap = int(height * 0.03)
    row_h = (gauge_area_bottom - gauge_area_top - gap) / 2
    radius = min(col_w * 0.5, row_h * 0.5) * 0.82

    def col_gauges(col_cx):
        top = gauge_layout(col_cx, gauge_area_top + row_h / 2, radius)
        bot = gauge_layout(col_cx, gauge_area_top + row_h + gap + row_h / 2, radius)
        return top, bot

    cpu_cx = margin + col_w / 2 + int(width * 0.015)
    gpu_cx = width - margin - col_w / 2 - int(width * 0.015)

    top_left, bottom_left = col_gauges(cpu_cx)
    top_right, bottom_right = col_gauges(gpu_cx)

    mid_x0 = margin + col_w + int(width * 0.03)
    mid_x1 = width - margin - col_w - int(width * 0.03)
    mid_cx = (mid_x0 + mid_x1) / 2

    # The 2 secondary gauges flank the album art -- there's real empty
    # space on both sides once the art (a fixed fraction of the middle
    # column's width, see render_frame()) is narrower than the middle
    # column itself, which it always is. `lean` pulls each gauge's
    # center away from the strict left/right midpoint and toward its
    # gauge column (0.5 = centered between art and column, 1.0 = flush
    # against the column) -- these sit closer to the big gauges than to
    # the art.
    art_size = int(min((mid_x1 - mid_x0) * 0.62, height * 0.42))
    art_right = mid_cx + art_size / 2
    art_left = mid_cx - art_size / 2
    lean = 0.68

    gauge_visible_left = top_right["cx"] - top_right["radius"] - top_right["ring_w"] / 2 - 25
    gauge_visible_right = top_left["cx"] + top_left["radius"] + top_left["ring_w"] / 2 + 25
    secondary_radius = top_right["radius"] * 0.52
    secondary_positions = {
        "right_secondary": gauge_layout(
            art_right + (gauge_visible_left - art_right) * lean,
            (top_right["cy"] + bottom_right["cy"]) / 2, secondary_radius),
        "left_secondary": gauge_layout(
            art_left + (gauge_visible_right - art_left) * lean,
            (top_left["cy"] + bottom_left["cy"]) / 2, secondary_radius),
    }

    # The 2 mini gauges flank the clock, below the album art -- there's
    # more vertical room down there than anywhere else on the panel, so
    # these get to be bigger than the secondary pair above despite being
    # called "mini". The clock's vertical position is fixed here (rather
    # than flowing below whatever media info happens to be showing) so
    # these have a stable spot baked into the static background;
    # render_frame() draws the clock text at this same y.
    clock_cy = int(height * 0.885)
    mini_radius = secondary_radius * 0.85
    mini_offset = (mid_x1 - mid_x0) * 0.26
    mini_positions = {
        "left_mini": gauge_layout(mid_cx - mini_offset, clock_cy, mini_radius),
        "right_mini": gauge_layout(mid_cx + mini_offset, clock_cy, mini_radius),
    }

    # Accent stays tied to which *column* (left=CPU cyan, right=GPU
    # magenta) a slot is in, not to whatever stat is currently assigned
    # there -- see STAT_DEFS' comment on why. Every slot's name has
    # "left" or "right" in it for exactly this reason.
    positions = {
        "top_left": top_left, "bottom_left": bottom_left,
        "top_right": top_right, "bottom_right": bottom_right,
        **secondary_positions, **mini_positions,
    }

    for slot_key, g in positions.items():
        kind = SLOT_KINDS[slot_key]
        accent = ACCENT_CPU if "left" in slot_key else ACCENT_GPU
        title = STAT_DEFS[slots[slot_key]]["title"]
        tile = draw_gauge_static(g, accent)
        img.paste(tile, _gauge_box(g), tile)
        if kind == "big":
            # The 4 big gauges get full tick labels and a title tucked
            # inside the ring; the secondary/mini ones skip tick labels
            # (no room, and they don't need to be read as precisely) and
            # get a compact title above the ring instead.
            draw_tick_labels(draw, g, fonts.tick)
            draw.text((g["cx"], g["cy"] - g["radius"] * 0.42), title, font=fonts.gauge_title,
                       fill=(225, 226, 236), anchor="mm")
        else:
            label_gap = 16 if kind == "secondary" else 13
            draw.text((g["cx"], g["cy"] - g["radius"] - label_gap), title, font=fonts.small_title,
                       fill=(225, 226, 236), anchor="mm")

    layout = {
        "positions": positions,
        "slot_assignments": slots,
        "clock_cy": clock_cy,
        "mid_x0": mid_x0, "mid_x1": mid_x1, "mid_w": mid_x1 - mid_x0,
    }
    return img, layout


def render_frame(background, layout, width, height, fonts, stats, media):
    """`stats` is a flat dict keyed by STAT_DEFS key (cpu_load, gpu_load,
    ram, network, gpu_temp, cpu_freq, disk_usage, vram_usage) -- any key
    can be missing or None, which just draws that gauge's dim track with
    no needle and "--" (see draw_gauge_dynamic_tile). All 8 gauges (big
    and small) read from this same dict via layout["slot_assignments"],
    since any stat can be assigned to any slot."""
    img = background.copy()

    for slot_key, g in layout["positions"].items():
        stat_key = layout["slot_assignments"][slot_key]
        stat = STAT_DEFS[stat_key]
        accent = ACCENT_CPU if "left" in slot_key else ACCENT_GPU
        value_font = fonts.gauge_value if SLOT_KINDS[slot_key] == "big" else fonts.small_value
        draw_gauge_dynamic(img, g, stats.get(stat_key), stat["min"], stat["max"],
                            accent, value_font, stat["fmt"])

    # --- middle: album art + progress + track/artist + clock ----------
    mid_x0, mid_w = layout["mid_x0"], layout["mid_w"]
    mid_cx = mid_x0 + mid_w / 2
    art_size = int(min(mid_w * 0.62, height * 0.42))

    art = None
    title = artist = None
    position = duration = None
    if media:
        title, artist = media.get("title"), media.get("artist")
        position, duration = media.get("position"), media.get("duration")
        if media.get("art") is not None:
            art = fit_album_art(media["art"], art_size, radius=14)
    if art is None:
        art = default_art(art_size, radius=14)

    art_x = int(mid_cx - art_size / 2)
    art_y = int(height * 0.09)

    glow_tile, glow_pad = art_glow_frame(art_size, 14, ACCENT_MID)
    glow_paste(img, glow_tile, (art_x - glow_pad, art_y - glow_pad), blur=8, glow_alpha=0.55)
    img.paste(art, (art_x, art_y))

    draw = ImageDraw.Draw(img)

    y = art_y + art_size + 16
    if title:
        track_line = truncate(draw, title.upper(), fonts.track, mid_w - 16)
        draw.text((mid_cx, y), track_line, font=fonts.track, fill=(238, 238, 244), anchor="ma")
        y += 26
        if artist:
            draw.text((mid_cx, y), artist, font=fonts.artist, fill=(200, 192, 220), anchor="ma")
            y += 24
        else:
            y += 4
        # Progress bar + mm:ss -- only while an actual track is loaded
        # (playing or paused, both land here since `title` is truthy for
        # both; it's specifically the "nothing loaded at all" case below
        # that has no timestamp to show). Skipped if we don't have a
        # duration to measure a fraction against.
        if duration:
            bar_w = int(mid_w * 0.72)
            bar_h = 6
            bar_x = int(mid_cx - bar_w / 2)
            bar_y = y + 6
            fraction = max(0.0, min(1.0, (position or 0.0) / duration))
            progress_bar_glow(img, bar_x, bar_y, bar_w, bar_h, fraction, ACCENT_MID)
            y = bar_y + bar_h + 16
            draw.text((bar_x, y), fmt_mmss(position), font=fonts.progress,
                       fill=(170, 165, 190), anchor="lm")
            draw.text((bar_x + bar_w, y), fmt_mmss(duration), font=fonts.progress,
                       fill=(170, 165, 190), anchor="rm")
            y += 30
        else:
            y += 16
    elif _MEDIA_OK:
        # Nothing playing -- shown in full, wrapped over as many lines as
        # it needs rather than truncated with "...", since there's no
        # timestamp taking up the space below it anymore.
        for line in wrap_text(draw, NOT_PLAYING_MESSAGE, fonts.message, mid_w - 16):
            draw.text((mid_cx, y), line, font=fonts.message, fill=(200, 190, 220), anchor="ma")
            y += 28
        y += 10
    else:
        draw.text((mid_cx, y), "SPOTIFY ART NEEDS WINSDK", font=fonts.track, fill=(238, 238, 244), anchor="ma")
        y += 66

    # Fixed vertical position (not the flowing `y` used above) -- see
    # build_static_background()'s comment on why: the disk/VRAM gauges
    # flanking it need a stable spot baked into the static background,
    # so the clock can no longer drift with how much media info is
    # showing above it.
    time_str = datetime.datetime.now().strftime("%H:%M:%S")
    draw.text((mid_cx, layout["clock_cy"]), time_str, font=fonts.time, fill=(235, 235, 242), anchor="mm")

    return img


def run(port=None, web_port=8765, enable_web=True, default_art_path=None,
        brightness=90, slots=None, background=None, stop_event=None, log=print,
        screen_factory=HongtaiScreen, on_connected=None):
    """Runs the dashboard until stop_event is set (or forever, if
    stop_event is None -- the CLI entry point below relies on Ctrl+C /
    KeyboardInterrupt instead in that case). Pulled out of main() so a
    GUI can start/stop this theme in a background thread instead of
    only being usable from the command line.

    `slots` picks which stat each of the 4 big gauges shows -- see
    STAT_DEFS/DEFAULT_SLOTS and build_static_background()'s docstring;
    defaults to DEFAULT_SLOTS if not given (or only partially given).

    `background` picks the panel background -- see BACKGROUND_PRESETS/
    DEFAULT_BACKGROUND and build_static_background()'s docstring;
    defaults to DEFAULT_BACKGROUND if not given (or only partially
    given, e.g. just {"mode": "solid"}).

    `screen_factory` exists purely so a GUI can hand in an already-built
    HongtaiScreen (e.g. if it wants to connect once and let the person
    switch themes without reopening the serial port each time); the CLI
    just uses the default, which is the class itself.

    `on_connected(screen)`, if given, is called once right after connect()
    -- this is how a GUI gets a live reference to the connected screen so
    things like the brightness slider can apply instantly (screen.set_
    brightness() is safe to call from another thread; see the write lock
    in hongtai_screen.py) instead of only taking effect on the next Start.
    """
    if cairo is None:
        log("This theme needs pycairo to draw the gauges, and it isn't installed")
        log("for whichever Python is running this script:")
        log("    pip install pycairo numpy")
        log("(pycairo installs from a prebuilt wheel on Windows -- no separate")
        log(" Cairo library install needed. If you have more than one Python on")
        log(" this machine, e.g. a venv, make sure you install into the same one")
        log(" you're using to run this script.)")
        return

    set_default_art_path(default_art_path)

    screen = screen_factory(port)
    info = screen.connect()
    log(f"Connected: {info.width}x{info.height}, firmware {info.version}")
    screen.set_brightness(brightness)
    if on_connected is not None:
        on_connected(screen)

    if enable_web:
        screen.enable_web_mirror(port=web_port, log=log)

    start_systeminfos()
    start_media_polling()
    if not os.path.exists(SYSTEMINFOS_EXE):
        log(f"  (SystemInfos.exe not found at {SYSTEMINFOS_DIR} -- GPU temp may be limited)")
    if not _GPU_OK:
        log("  (no NVIDIA GPU / nvidia-ml-py not available -- falling back to SystemInfos.exe for GPU stats)")
    if not _MEDIA_OK:
        log("  (winsdk not available -- install it for Spotify album art: pip install winsdk)")

    fonts = Fonts()
    bg_image, layout = build_static_background(info.width, info.height, fonts, slots, background)

    log("Streaming dashboard at 10Hz. Press Ctrl+C to stop." if stop_event is None
        else "Streaming dashboard at 10Hz.")
    target_period = 0.1  # 10Hz
    try:
        while stop_event is None or not stop_event.is_set():
            frame_start = time.time()

            sysinfo_frame = read_systeminfos()
            media = get_media_info()
            gpu = get_gpu_stats(sysinfo_frame)
            stats = {
                "cpu_load": get_cpu_stats()["util"],
                "gpu_load": gpu["util"] if gpu else None,
                "gpu_temp": gpu["temp"] if gpu else None,
                "ram": get_ram_percent(),
                "network": get_network_rate_mb_s(),
                "cpu_freq": get_cpu_freq_ghz(),
                "disk_usage": get_disk_usage_percent(),
                "vram_usage": get_vram_percent(),
                "swap": get_swap_percent(),
                "disk_io": get_disk_io_mb_s(),
                "gpu_power": get_gpu_power_w(),
                "process_count": get_process_count(),
                "cpu_load_peak": get_cpu_load_peak_core(),
                "battery": get_battery_percent(),
            }

            img = render_frame(bg_image, layout, info.width, info.height, fonts, stats, media)
            screen.show(img)

            elapsed = time.time() - frame_start
            sleep_for = max(0.0, target_period - elapsed)
            if stop_event is not None:
                stop_event.wait(sleep_for)  # wakes immediately if stopped mid-sleep
            else:
                time.sleep(sleep_for)
    except KeyboardInterrupt:
        pass
    finally:
        screen.close(log=log)
        stop_systeminfos()
        log("Stopped, disconnected cleanly.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("port", nargs="?", default=None, help="COM port (auto-detected if omitted)")
    ap.add_argument("--web-port", type=int, default=8765,
                     help="port for the live web mirror (default 8765)")
    ap.add_argument("--no-web", action="store_true",
                     help="disable the live web mirror entirely")
    ap.add_argument("--default-art", default=None,
                     help="image to show in place of album art when nothing is playing "
                          "(default: a plain drawn placeholder, no file needed)")
    args = ap.parse_args()

    run(port=args.port, web_port=args.web_port, enable_web=not args.no_web,
        default_art_path=args.default_art)


if __name__ == "__main__":
    main()
