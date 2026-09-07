# Roadmap — v2.0 UI rewrite

Plan for replacing the Tkinter desktop app with a webview + Python
backend architecture, and turning the Dashboard's fixed 8-slot layout
into a free-form design canvas.

Status: **Phase 0 done, validated on real hardware/OS.** Design updated
to a two-process split based on real measurements (see below). v1.0.0
(the current Tkinter app) stays the shipped, working version throughout
the rest of this work.

## Why

Three of the four wanted features are the same underlying problem:

- **Free-form dashboard layout** — drag gauges anywhere, not 8 fixed slots.
- **More design options** — per-element colors, fonts, sizes, rotation,
  opacity, instead of a handful of global dropdowns.
- **Live preview inside the app** — no browser tab needed.

All three are satisfied by the same thing: a real canvas editor where
each element is a selectable object with its own properties. Tkinter
can't get there without hand-rolling hit-testing, resize handles,
rotation math and snapping from scratch, and it would still look dated.

RGB fan control is **out of scope** — that's the motherboard's domain
(Gigabyte GCC), not this case's panel, and GCC already handles it fine.
If it's ever wanted, Gigabyte boards are well supported by OpenRGB, so
it'd be an SDK integration rather than a reverse-engineering project.

There's a hard requirement driving the architecture below: **background
(no window open) RAM must stay under 100MB.** Not everyone running this
has 32GB+ to spare.

## Architecture

Two separate OS processes, not one app with a UI bolted on:

```
┌──────────────────────────────────────────────┐   spawned on open,
│ UI process (pywebview / WebView2)             │   KILLED outright
│   React frontend, served over localhost       │   on close --
└───────────────┬──────────────────────────────┘   costs ~390MB while
                │ HTTP / WebSocket on 127.0.0.1      open, ~0MB when not
┌───────────────┴──────────────────────────────┐
│ Backend process (always running)              │   never imports
│  • local HTTP server: frontend + control API  │   pywebview/WebView2
│    + /frame.jpg live feed                     │   at all -- expected
│  • config, tray icon, single-instance,        │   to cost about what
│    startup registration                       │   today's app costs
│  • theme render loop  (unchanged)             │   (~84MB), comfortably
│  • hongtai_screen.py driver  (unchanged)      │   under the 100MB cap
└──────────────────────────────────────────────┘
```

The backend has to keep running regardless of whether any UI is open --
it's the thing driving the physical panel, not something that exists
for the UI's benefit. The UI existing only while it's actually open is
what keeps background RAM under budget; see "Phase 0 results" below for
why this ended up as two processes rather than one process that
destroys its own window.

### Key decisions

**The live preview is the existing web mirror.** `hongtai_screen.py`
already serves `/frame.jpg` from the frame being sent to the panel, and
that code is already debugged (including the HTTP/1.0 keep-alive fix).
The in-app preview is that same feed, displayed in our own window
instead of a browser tab. Nearly free, and impossible to drift out of
sync with the panel because it *is* the panel's frame.

**Frontend is served over HTTP, not `file://`.** Avoids CORS problems,
and means the whole UI is also reachable from a phone/browser for free
— the same trick the mirror already pulls.

**The control API binds to 127.0.0.1 only.** The read-only LAN mirror
stays what it is today: separate, opt-in, and read-only. Nothing that
can change settings or drive the panel is ever exposed to the network.

**No duplicate renderer.** The designer does *not* re-implement gauge
drawing in JS. It draws transparent drag/resize handles positioned over
the real rendered frame. While dragging, the handle moves instantly in
the browser (60fps, feels native); coordinates are pushed to Python,
which re-renders, and the image underneath catches up within ~100ms at
10Hz. Pixel-accurate by construction, one renderer to maintain.

**The UI is a separate process, killed outright on close.** Originally
planned as "destroy the window, keep the same process" -- Phase 0's
measurements ruled that out (see below). The UI process is spawned
fresh each time the window is opened and terminated (its own PID is
enough; WebView2 cleans up its own helper processes) when it closes.
Cost: opening the window takes ~1-2.5s (spawning a process + WebView2
init) instead of being instant. This requires all real state to live
in the backend, with the page treated as stateless UI — good practice
anyway, and now a hard requirement rather than just a nice one, since
the UI process can vanish and be recreated at any time.

**Low lock-in.** Because the UI is an HTTP app, pywebview is just a
window shell. If it ever disappoints, the shell can be swapped without
touching the UI, which still runs in any browser.

## Phases

### Phase 0 — Spike (throwaway) — ✅ DONE

Ran on real hardware. Full scripts and logs in
`experiments/phase0_webview_spike/` (kept for reference, safe to delete
once this is fully absorbed elsewhere).

**Round 1 — does destroying a window reclaim its process's memory?
No.** Across three independent runs (an interactive spike, 12 automated
open/destroy cycles, and a control run that never destroyed anything),
"this process" RSS jumped once on first WebView2 use (~65-90MB) and
never came back down regardless of window state. A small (~1MB/cycle)
creep across repeated cycles flattened out rather than accelerating —
not a leak, just allocator noise. Conclusion: loading WebView2 into a
process is a one-time, per-process cost, not a per-window one — so
destroying and recreating a window in the *same* process buys nothing.

Combined with the 100MB background hard cap, this ruled out the
original single-process design entirely: ~90MB of permanent WebView2
overhead alone, sharing a process with the always-on backend, would
already be most of the budget before counting any real work. Redesigned
as the two-process split described above.

**Round 2 — does killing a separate UI process actually clean up
everything?** Yes, cleanly. 4 automated spawn/kill cycles (alternating
"kill just the child's PID" vs. "kill its whole process tree
explicitly") all showed **zero surviving processes**, checked
immediately and 5s after each kill — killing just the PID was enough
in every case; WebView2's own process-lifetime management tears down
its helpers on its own. The backend process itself barely moved across
all 4 cycles (16.1MB → 17.7MB), confirming the spawn/kill orchestration
itself has no real cost.

**Numbers to build against:** UI process costs ~390-395MB while open
(the real, honest cost of a modern browser-engine UI — irrelevant to
the background budget since it only exists while visible), effectively
0MB within ~1s of the window closing. Backend alone should land close
to today's ~84MB once it's doing real work, comfortably under the
100MB cap.

### Phase 1 — Extract the backend (no visible change) — ✅ DONE

Pulled everything that isn't Tkinter out of `app.py` into its own
modules:

- `paths.py` — base dir / resource path resolution, `startup_debug.log` writer
- `config_store.py` — `app_config.json` load/save, `AUTO_DETECT`/`THEME_TAB_ORDER`
- `startup_registration.py` — Windows Startup-folder VBS launcher
- `desktop_shortcut.py` — Desktop `.lnk` creation
- `single_instance.py` — named-mutex single-instance check
- `theme_worker.py` — `ThemeWorker`: background thread + blind-restart
  recovery loop, talking back only through a plain `log` callback
- `tray_icon.py` — `TrayIcon`: pystray wrapper driven by three plain
  callbacks (`on_show`/`on_stop_screen`/`on_quit`)

`app.py` is now a thin Tkinter layer that calls into these. No
intentional behavior change — verified headlessly (python3.12 +
Tkinter under Xvfb, since the sandbox's default Python has no Tk) that
the `App` class still constructs, builds its widgets, and that
`ThemeWorker` runs/reports through its log callback exactly like the
old inline thread did. One real fix rode along: `enable_startup()` and
`create_desktop_shortcut()` used to resolve the running script via
their own `__file__`; now that this logic lives in a different file
than `app.py`, they resolve it via `sys.modules["__main__"].__file__`
instead, which is what actually still points at `app.py` regardless of
which module the code was called from.

Tray icon, startup registration and desktop shortcut creation are all
Windows-only and untestable from the sandbox — confirmed working
(Start/Stop, tray Show/Stop/Quit, "Launch at Windows startup", "Create
Desktop Shortcut") on the real machine, so this phase is fully closed
out.

### Phase 1.5 — src/ layout restructure (no visible change) — ✅ DONE (pending on-hardware confirmation)

Not one of the originally planned phases -- inserted here because the
project root had grown to ~20 loose `.py` files by the end of Phase 1
and needed a real directory structure before Phase 2 adds a `frontend/`
tree on top of it.

```
app.py                      -- thin launcher (unchanged path -- see below)
src/hongtai_screen_app/      -- the actual package
    app.py                   -- the Tkinter GUI + main()
    paths.py, config_store.py, startup_registration.py,
    desktop_shortcut.py, single_instance.py, theme_worker.py,
    tray_icon.py             -- Phase 1's app-shell modules, unchanged
                                 in substance, just moved + import paths
                                 switched to relative (`from .paths import ...`)
    driver/hongtai_screen.py -- the protocol driver
    themes/                   -- dashboard_theme.py, video_theme.py,
                                  webpage_theme.py, demo_clock.py
scripts/                     -- list_screens.py, test_connection.py,
                                 blind_draw.py, diag2_lines.py,
                                 make_launcher.py, and a thin CLI shim
                                 per theme (so `python scripts/dashboard_theme.py`
                                 etc. keep working standalone)
assets/icon.ico
packaging/hongtai_screen.spec
```

**Root `app.py` deliberately did not move.** It's now a ~15-line
launcher that puts `src/` on `sys.path` and calls
`hongtai_screen_app.app.main()` -- kept at this exact path so every
existing Windows integration that already points at it (a "Launch at
Windows startup" Startup-folder entry, a Desktop shortcut, `Launch
Hongtai Screen.vbs`) keeps working with zero user action, rather than
silently breaking because the real file moved. No install step is
needed to run any of this -- `python app.py` and everything under
`scripts/` use the same `sys.path.insert(0, ".../src")` trick, so
`pip install -r requirements.txt && python app.py` from **Quick
start** still just works. An optional `pyproject.toml` was added purely
for editor/IDE import resolution and an optional `pip install -e .` --
never required.

Two real fixes rode along with the move (both are exactly the kind of
bug a flat "everything imports everything by bare name" layout hides):
`_app_base_dir()` (in `paths.py`) used to resolve via its own
`__file__`, which put `app_config.json`/`startup_debug.log` inside
`src/hongtai_screen_app/` instead of next to the real entry point once
that function moved into its own file -- fixed to resolve via
`sys.modules["__main__"].__file__` instead (same approach
`startup_registration.py`/`desktop_shortcut.py` already used). And
`desktop_shortcut.py`'s dependency on `make_launcher.py` was inverted:
the "write the hidden .vbs launcher" logic now lives once, as
`desktop_shortcut.write_run_vbs()`, and `scripts/make_launcher.py`
(a standalone convenience script) imports *it*, rather than package
code reaching out to a loose top-level script that could be deleted or
moved independently.

Verified headlessly: `python app.py` (plain and `--autostart --theme
clock`) runs end to end under Xvfb with the same behavior as before the
move -- `app_config.json`/`startup_debug.log` land next to root
`app.py` as expected, not under `src/`; every `scripts/*.py` resolves
its import correctly at runtime (checked `list_screens.py` actually
enumerating ports, not just parsing). Windows-only things (Start/Stop
against real hardware, tray, "Launch at Windows startup", "Create
Desktop Shortcut", and a real PyInstaller build against the new
`packaging/hongtai_screen.spec`) still need one real-machine pass
before this is fully closed out -- same caveat as Phase 1 had.

### Phase 2 — Control API + UI process

Split into sub-steps rather than landing all at once, since the
frontend/process-spawn parts can't be verified from the sandbox at all
(no display, no Node runtime tested here, no WebView2) -- each one
lands and gets reviewed before the next starts.

#### Phase 2a — Backend control API — ✅ DONE

New, additive, fully headless -- does **not** touch the Tkinter app.
Three new modules in `src/hongtai_screen_app/`:

- `theme_kwargs.py` — the one thing Phase 1 didn't extract: pure
  functions that turn `app_config.json`'s saved settings into the
  `(theme_name, target, kwargs)` tuple `ThemeWorker` needs, reading
  straight from the config dict instead of Tk widgets (every field is
  already stored in canonical form -- `dashboard.slots` values are
  `STAT_DEFS` keys, not display labels -- so no translation layer is
  needed). The Tkinter app's own inline kwarg-builders are **not**
  switched to call these yet -- see the module's docstring for why
  (it would mean reordering when `self.cfg` gets synced from widget
  state, a GUI behavior change outside this pass's scope).
- `controller.py` — `AppController`: the same start/stop/apply/config
  logic `app.py`'s `App` class drives, minus every Tk widget touch.
  Owns a `ThemeWorker`, a log ring-buffer + pub/sub (so a new SSE
  client catches up on recent lines and then keeps receiving new
  ones), and a background watcher thread standing in for what
  `_poll_log_queue()` does in the GUI (notice the worker died, reset
  state, or restart if `apply()` asked for it). Thread-safe -- callable
  concurrently from multiple HTTP handler threads.
- `control_server.py` — the actual HTTP API, `ThreadingHTTPServer`
  bound to **127.0.0.1 only** (never the LAN, unlike the opt-in web
  mirror): `GET /api/state`, `GET`/`POST /api/config`,
  `POST /api/start` (optional `{"theme": ...}` body), `POST /api/stop`,
  `POST /api/apply`, `GET /api/logs/stream` (SSE, plain HTTP/1.0 with
  no Content-Length -- the connection just stays open), and
  `GET /frame.jpg`. No extra dependencies -- same `http.server`
  approach the driver's own mirror already uses.
- `scripts/run_backend.py` — runs the control API standalone, no
  Tkinter at all, so it can actually be tried with curl before any
  frontend exists: `python scripts/run_backend.py`.

One small, additive change to the driver itself:
`hongtai_screen.enable_frame_capture()`/`disable_frame_capture()`/
`get_mirror_frame_jpeg()` -- keeps the latest frame as JPEG bytes in
memory for a same-process caller (the control API's `/frame.jpg`)
without opening a second network listener the way
`enable_web_mirror()` does (that stays LAN-facing and opt-in, for the
phone-mirror use case specifically). Both share the same underlying
buffer; either one being on is enough to populate it.

Verified headlessly end to end (no hardware needed for any of this):
state/config get and set, start (theme name via the request body),
double-start correctly rejected (400), config patch + apply actually
picking up the new value (started Clock, patched brightness, called
apply, confirmed the restarted worker's state reflected the new
brightness), stop, and an unknown theme name rejected (400) --  all via
real HTTP requests against a running server, not mocked. The SSE log
stream was verified separately: a client connected before `start()` was
called received the worker's live error/recovery log lines in real
time, matching exactly what the Tkinter app's Log panel would show for
the same run. `scripts/run_backend.py` itself was run as a real
subprocess, queried over HTTP, and shut down cleanly via SIGINT.
Confirmed on real hardware: `POST /api/start` connects to the panel,
`connected`/`screen_info` populate correctly, and `/frame.jpg` returns
real image bytes once a theme is running.

One bug surfaced by that real-machine pass, fixed as part of closing
out this phase: `_app_base_dir()` (`paths.py`) resolved via
`sys.modules["__main__"].__file__`, which pointed at `scripts/` (not
the repo root) when the entry point was `scripts/run_backend.py`
rather than root `app.py` -- so running the backend standalone wrote
its own separate `scripts/app_config.json` instead of sharing the real
one next to `app.py`, contradicting `run_backend.py`'s own docstring
promise ("loads the same app_config.json the GUI uses"). Fixed by
anchoring `_app_base_dir()` on `paths.py`'s own file location (three
parents up is always the repo root) instead of on whichever script
Python was run as -- `startup_registration.py`/`desktop_shortcut.py`
keep using `sys.modules["__main__"].__file__`, deliberately, since
they're solving a different problem (pointing a Windows launcher at
the real running script). Verified headlessly: `scripts/run_backend.py`
run from a fresh checkout now writes `app_config.json` at the repo
root regardless of entry point, and a stray `scripts/app_config.json`
is no longer created.

#### Phase 2b — Frontend scaffold — ✅ DONE

A minimal Vite + React shell (`frontend/`) that talks to the Phase 2a
API: connection status, the live preview (`/frame.jpg`, polled at
~2.5Hz -- the API serves one JPEG per request, not a multipart
stream, matching how the old web-mirror page already worked),
theme/port/brightness/start/stop/apply controls, and a live log panel
(consumes `/api/logs/stream` via `EventSource`, which handles SSE
reconnects on its own). `frontend/src/api.js` is the only file that
knows the backend's actual endpoint shapes -- everything else just
calls its functions.

**Served by the backend itself, same origin, on purpose.** `npm run
build`'s output (`frontend/dist/`) is served directly by
`control_server.py`: any GET that isn't an API route now falls
through to a static-file handler that serves `frontend/dist/`
(path-traversal-checked -- verified headlessly that `/../../<anything
outside dist>` 404s rather than leaking a repo file). This means
there's no cross-origin request to configure in production at all --
open `http://127.0.0.1:8899/` with a theme running and the whole UI
loads from the same process already driving the panel. `npm run dev`
(a separate Vite dev server on its own port) instead uses
`vite.config.js`'s proxy for `/api`/`/frame.jpg`, for a fast edit
loop while working on the frontend itself.

`frontend/dist/` is committed to the repo (see `.gitignore`) so
`pip install -r requirements.txt && python app.py` keeps working with
zero Node toolchain required -- only touching `frontend/src/` requires
Node, and only to rebuild the committed bundle afterward.

Verified headlessly: `npm run build` succeeds cleanly; the built
bundle's `index.html` and its hashed JS asset are served correctly by
`control_server.py` with the right content types; `/api/state` and the
rest of the API keep working unchanged alongside the static handler;
a raw-socket path-traversal attempt (`GET /../pyproject.toml`, past
`urlparse` which doesn't normalize `..` itself) correctly 404s instead
of returning a repo file. Confirmed on the real machine: the page loads at
`http://127.0.0.1:8899/`, and start/stop/apply/theme/port/brightness
all work from the browser the same way they do from `curl`/the
Tkinter app. One real bug surfaced by that pass and fixed as part of
closing out this phase (see Phase 2a's writeup above, which this
inherited): `controller.py`'s `_selected_port()` was passing
`app_config.json`'s saved port *label* (a whole descriptive string)
straight to the driver as if it were an openable device path, instead
of translating it back to the real `COM3`-style path the way `app.py`
already does -- fixed to do the same rescan-and-match `app.py` uses.

#### Phase 2c — UI process spawn/kill wiring — ✅ DONE

The actual two-process design Phase 0 validated, wired up end to end
for the first time: `backend_app.py` (`scripts/run_v2_app.py`) is a
new, parallel entry point -- **not yet what `app.py`/Desktop shortcuts/
Startup point at; that switch is Phase 7's job** -- that starts the
control API, a tray icon, and resumes whatever theme was last running
(same logic as `app.py`'s own launch-time resume). Its tray's "Show"
spawns `scripts/run_ui.py` (a tiny, dependency-free pywebview window
pointed at the backend's own URL) as a genuinely separate OS process,
tracked by its `Popen` handle; "Show" again while one is already open
is a no-op rather than opening a second window; "Quit" `terminate()`s
it along with shutting down the server and controller. `run_ui.py` is
deliberately importless from the app's own package -- pywebview (and,
transitively, WebView2) only ever gets loaded in that one process,
never in the always-on backend, which is the entire point of Phase 0's
two-process split: destroying a pywebview window doesn't release its
~90MB of overhead within the same process, so ending the whole process
is the only way to actually reclaim it.

Verified everything headlessly that doesn't require an actual
WebView2/tray/display: `BackendApp` resumes the last-running theme on
a plain launch (checked with a saved `auto_resume_tab`, matching
`app.py`'s behavior exactly); the control server starts and stops
cleanly under its orchestration; `_on_show()` spawns exactly one
subprocess and a second call while the first is still alive is
correctly a no-op (verified with `subprocess.Popen` stubbed, since
there's no `pywebview`/display here to actually open a window against);
`shutdown()` actually terminates the tracked UI subprocess and stops
the server (confirmed the API stops responding afterward). Tray icon
creation itself is a no-op here (`pystray`'s `available()` correctly
reports `False` off Windows) -- that path, `run_ui.py` actually
opening a window, WebView2 availability, and the real spawn/kill
memory numbers all still need one real-machine pass, same caveat every
other phase has had.

**Confirmed on the real machine, and the two-process design works as
designed:** tray icon (Show/Stop screen/Quit) all work; the window
opens as a genuinely separate process, and that process fully exits
when the window is closed. Memory: backend **~80MB**, UI process
**~40MB** while open -- both comfortably under Phase 0's 100MB
background cap, and the UI process in particular came in far under
Phase 0's ~390MB estimate (that spike's throwaway window loaded a
blank/trivial page; this one's a small React app talking to a live
API, evidently not enough extra weight to move the needle much against
WebView2's own baseline). One real gap the first test caught: starting
via `scripts/run_backend.py` instead of `scripts/run_v2_app.py` looks
almost identical from the browser (same control API, same frontend)
but has no tray icon, no startup/shortcut endpoints, and no
live-brightness wiring at all -- worth remembering these are two
different entry points for two different purposes (`run_backend.py`:
curl-testing the API alone; `run_v2_app.py`: the actual app), not
interchangeable.

One known, accepted limitation: the popup window's title-bar/taskbar
icon still shows Python's own default rather than `icon.ico`.
pywebview's `icon=` on `webview.start()` is GTK/Qt (Linux) only by its
own design -- on Windows "icon is set during freezing" (i.e. baked
into a PyInstaller `.exe`'s resources, which `packaging/hongtai_screen.spec`
already does, and which is what Phase 7's cutover ships). Worked
around in the meantime with the same `FindWindowW`-by-title trick
`single_instance.py` already uses elsewhere in this codebase: once the
window is shown, `run_ui.py` pushes `icon.ico` onto its `HWND`
directly via `WM_SETICON` (both `ICON_SMALL`/`ICON_BIG`), which is
what the title bar and taskbar button actually read. Best-effort,
Windows-only, and unverified from here (no Windows/WebView2 in the
sandbox) -- next real-machine pass should confirm whether it actually
fixes the icon or the real fix has to wait for Phase 7's frozen build.

**Fix (real-usage bug in auto-resume):** quitting `backend_app.py`
while a theme was running never resumed it on the next launch, even
though this section's own verification above claims resume "matches
`app.py`'s behavior exactly" -- that check only covered a *plain
launch* reading a pre-seeded `auto_resume_tab`, not a full
start-then-quit round trip, so it missed that quitting itself was
wiping the marker first. Root cause: `ScreenEngine.close()` (process
shutdown, releases the serial port) and `ScreenEngine.stop()` (an
explicit Stop) both funneled through the same `_teardown()` ->
`on_disconnected()` callback, and `AppController._on_screen_
disconnected()` clears `auto_resume_tab` on every call -- correct for
an explicit Stop or a theme dying/finishing on its own, wrong for a
plain quit while something was still running. `_teardown()` now skips
`on_disconnected()` specifically when `close()` triggered it (it still
always physically closes the port), so the marker set by the last
`start()`/`switch()` survives a clean quit. Verified headlessly with a
fake screen/target standing in for real hardware: quit-while-running
now preserves and persists `auto_resume_tab` to disk; an explicit
`stop()` still clears it as before; switching themes still reuses the
one connection without a spurious disconnect in between.

### Phase 3 — Port the simple themes — ✅ DONE (pending a real-machine pass)

Video, Webpage and Clock settings forms, added to the frontend
(`App.jsx`) as a "Theme settings" panel that swaps its fields based on
whichever theme is selected -- mirroring `app.py`'s own per-tab
settings fields and hint text exactly (Video: file path, loop/B&W/
audio checkboxes, FPS override; Webpage: URL, screenshot interval,
full-reload interval; Clock: nothing beyond port/brightness, just an
info line; Dashboard: an explicit "not in the web UI yet, Phase 4"
note rather than silently doing nothing).

**No backend changes needed at all.** `update_config()`'s shallow
per-key merge (Phase 2a) and `theme_kwargs.py`'s parsing straight out
of `app_config.json` (also Phase 2a) already handled arbitrary
`video`/`webpage` settings from day one -- this phase is purely
frontend, POSTing `{"video": {...}}` / `{"webpage": {...}}` patches in
exactly the shape `app.py`'s own `_save_current_config()` already
persists (path/fps as a string or null, url/interval as strings,
reload_every as a string or null), so a config file edited by either
UI stays fully compatible with the other's expectations.

One deliberate deviation from `app.py`: no "Browse..." file picker for
the video path. A browser's native file input can't hand back a full
filesystem path (a sandboxed security restriction, not a bug), and the
backend needs an absolute path to open with OpenCV -- so this is a
plain text field the same way the port field already is, with a
placeholder showing the expected format.

Verified headlessly against a running `run_backend.py`: saved video
settings (path/loop/bw/audio/fps) and webpage settings (url/interval/
reload_every) via `POST /api/config` in the exact shape the frontend
sends, then confirmed `POST /api/start` for both `video` and `webpage`
successfully builds their kwargs and starts a worker (no
theme_kwargs.py error) -- i.e. the whole settings-form-to-running-theme
path works end to end. Not yet checked by eye in a real browser against
a real video file/URL and real hardware.

### Phase 3.5 — Live theme switching (no reconnect) — ✅ DONE, confirmed on hardware

Not on the original plan -- added after testing Phase 2c/3 on real
hardware surfaced a design smell: every theme module (`dashboard_theme.py`,
`video_theme.py`, `webpage_theme.py`, `demo_clock.py`) connected its own
`HongtaiScreen`, ran its own render loop, and closed its own connection,
so switching themes meant fully disconnecting one and reconnecting the
other from scratch even though the panel doesn't care which theme is
driving it -- it just wants a stream of frames on an open serial port.
Producing a frame is a theme's job; owning the connection never needed
to be, and each theme's own `screen_factory` docstring already said as
much (aspirationally -- nothing actually let a caller hand in a
pre-connected screen until now).

**Theme modules (`demo_clock.py`, `video_theme.py`, `webpage_theme.py`,
`dashboard_theme.py`):** `run()` now takes an optional `screen=`. When
given an already-connected `HongtaiScreen`, a theme skips
`screen_factory(port)`/`.connect()`/`on_connected()` entirely, reads
`info` straight off it, and -- critically -- never closes it in
`finally`. `port`/`screen_factory`/`on_connected` are ignored in that
case. Plain CLI/GUI use (`screen=None`, the default, what `app.py` and
the CLI entry points still do) is unaffected: connects and disconnects
its own screen exactly like before. `dashboard_theme.py`'s
`start_media_polling()`/`start_systeminfos()` were both confirmed
already idempotent (guarded by module-level flags), so switching away
from and back to Dashboard repeatedly doesn't spawn duplicate
subprocess/polling threads.

**New `screen_engine.py` (`ScreenEngine`), replacing `ThemeWorker` for
`controller.py` only** (`app.py`'s Tkinter UI keeps `ThemeWorker`
untouched -- this is additive, not a breaking change to the existing
GUI). One dedicated background thread owns the connection for the
controller's whole lifetime: `switch(label, target, kwargs, port)`
interrupts whatever's running (via its `stop_event`) and starts the new
target against the *same* connection, connecting only if nothing was
connected yet; `stop()` interrupts and fully disconnects. A theme
ending on its own (a non-looping video finishing, a page load
failure) still disconnects, same as the old per-theme behavior. Errors
that aren't from an intentional stop/switch get `ThemeWorker`'s same
recovery treatment -- `blind_restart()` (a real firmware restart, not
just a reconnect), then reconnect and retry, up to `RECOVERY_ATTEMPTS`
(3) -- and give up with a logged message if the panel never comes back.

**`controller.py`:** now builds one `ScreenEngine` at construction
instead of a `ThemeWorker` per `start()`. `start()` no longer raises
"already running" -- calling it while a different theme is active *is*
a live switch, handled by `ScreenEngine.switch()`. `apply()` no longer
stops-then-waits-then-restarts (the old `_pending_restart` +
`_watch_loop` dance, now deleted entirely); it just re-switches to the
currently-active theme with freshly-read config, which reuses the
connection like any other switch. `/api/start`, `/api/stop`,
`/api/apply` on `control_server.py` needed zero changes -- the new
behavior falls straight out of what `controller.py` already called.

**Frontend (`App.jsx`):** the theme picker and Start button are no
longer locked while a theme is running -- Start's label becomes
"Switch" once something's active, and picking a different theme + Start
now switches live instead of requiring Stop first.

Verified headlessly with fake/mocked hardware (no real panel needed for
any of this): a switch reuses the same connection with zero reconnects
and fires `on_connected` only once across multiple switches; a natural
finish (theme's `run()` returning on its own) disconnects and fires
`on_finished`; a simulated failure not caused by an intentional
stop/switch retries with `blind_restart()` between attempts and gives
up after `RECOVERY_ATTEMPTS`; an error that races with an intentional
stop is treated as "stopped", not as a fault needing recovery; and
`controller.py`'s `start()`/`apply()`/`stop()` drive all of the above
correctly end to end (switching live, Apply without disconnecting, Stop
actually disconnecting), plus a full `control_server.py` boot-and-query
smoke test with no hardware attached. **Confirmed working on real
hardware**: live switching between real theme streams with no
disconnect/reconnect flicker.

### Phase 4 — Layout model: slots → elements (backend) — ✅ DONE (pending a real-machine pass)

The core data model change that actually unblocks the last three
phases: `build_static_background()`/`render_frame()` no longer compute
8 fixed gauge positions from a formula keyed by a slot name (`top_left`,
`left_secondary`, ...); they walk an arbitrary list of gauge elements
instead, each with its own `x`/`y`/`radius` (fractions of width/height/
min(width, height), so the same list scales correctly to any panel
resolution), `color` (an explicit override, or `None` to keep the old
left-column-cyan/right-column-magenta split), `opacity`, `z` (paint
order), `stat` (a `STAT_DEFS` key, same as before), and a `rotation`
field that's stored/migrated/round-tripped through config but not
rendered yet -- correct rotation needs the per-frame needle/value to
rotate in lockstep with the static ring, and nothing can actually set a
non-zero rotation until Phase 5's canvas exists to offer it, so
implementing that now would be untested, unreachable code. The old
"big"/"secondary"/"mini" `SLOT_KINDS` enum is gone too: whether a gauge
gets full tick labels + an inside title (the old "big" look) or a
compact title-above-the-ring look is now derived from the element's
actual baked radius (`BIG_GAUGE_RADIUS_FRACTION`), and the small-style
label gap is a continuous function of radius instead of two hardcoded
constants -- calibrated so the default 8-gauge layout's look doesn't
change (see below).

- **Migration, done at read time, not as a stored schema version.**
  `slots_to_elements(slots)` runs the exact same geometry formula
  `build_static_background()` used to compute inline (now pulled out
  into `_slot_geometry()`) at a fixed `REFERENCE_WIDTH`/`REFERENCE_HEIGHT`
  matching this panel's real resolution, and expresses each gauge's
  resulting center/radius as a fraction of that reference size.
  `DEFAULT_ELEMENTS` is this applied to `DEFAULT_SLOTS`. `theme_kwargs.py`
  reads `dashboard.elements` from config if present, otherwise derives
  one from `dashboard.slots` (or the defaults) the same way -- so an
  existing `app_config.json` with only `slots` (or nothing dashboard-
  related at all) keeps rendering exactly as before, with nothing
  needing to be written back or bumped. Only a future design canvas
  actually saving custom elements changes what's stored.
- **`app.py`'s Tkinter Dashboard tab is completely unaffected.** It
  still reads/writes `dashboard.slots` directly and still calls
  `dashboard_theme.run(slots=..., ...)` — that parameter still exists
  and still works exactly as before. `run()` only derives `elements`
  from it internally (via `slots_to_elements()`) when no `elements=` was
  given, which is the *only* thing `app.py`'s call site does not pass.
- Kept the static-bake optimization exactly as it was — the whole
  per-element loop (position resolution, static tile draw, tick/title
  labels) runs once per `build_static_background()` call, and only the
  live needle/value redraw every frame in `render_frame()`, same as
  before this phase. Still invalidated by a Stop/Start or the GUI's
  Apply button, same as any other "needs a restart" dashboard setting.

Verified headlessly: pixel-diffed a full rendered frame from the new
element-based path against a reconstruction of the exact pre-Phase-4
formula-based path for the default 8-gauge layout -- 460,800 pixels
compared, 0.065% differing (a sub-pixel label-position shift from the
new continuous label-gap formula replacing the old hardcoded 13px/16px
constants, exactly as expected and documented in code); custom `slots`
overrides migrate to the right `stat` bindings; a hand-built custom
`elements` list (arbitrary position/size/explicit color/opacity, plus
an unrecognized future element type mixed in) bakes and renders without
error, with the unknown type correctly skipped rather than crashing;
`theme_kwargs.py` correctly prefers `dashboard.elements` when present
and falls back to migrating `dashboard.slots` otherwise; and a full
`dashboard_theme.run()` against a fake screen actually streamed real
frames end to end. **Not yet verified on real hardware.**

### Phase 5 — The design canvas — ✅ DONE (pending a real-machine pass)

Built on Phase 4's element list directly: the canvas edits exactly the
same `{id, type, stat, x, y, radius, rotation, color, opacity, z}`
shape that already round-trips through config, so there's no separate
"canvas format" to convert to/from -- what you drag is what
`dashboard_theme.py` renders.

New frontend component `DashboardCanvas.jsx` (the web UI's Dashboard
tab), an SVG overlay drawn on top of the live `/frame.jpg` mirror when
the panel's connected (a placeholder background otherwise):

- **Drag** a gauge to move it (pointer events on the circle), **drag
  its corner handle** to resize (radius = pixel distance from the
  gauge's own center to the pointer, converted back to the same
  fraction-of-`min(width,height)` basis `dashboard_theme.py` uses).
  **Rotate is deliberately not exposed** -- Phase 4 stores/migrates
  `rotation` but doesn't render it yet (the needle would need to
  rotate in lockstep with the ring, and nothing could set a non-zero
  value before this canvas existed to offer it), so a rotate handle
  here would visibly do nothing. It'll get one once rendering support
  lands.
- **Snapping + alignment guides**: dragging within ~1.8% of the canvas
  center or another gauge's x or y snaps to it and draws a dashed
  guide line, independently on each axis.
- **Property panel** for the selected gauge: stat picker (from
  `STAT_DEFS`, via the new `/api/dashboard/meta` metadata endpoint so
  the frontend never needs to import anything from `dashboard_theme.py`
  directly), opacity slider, a custom-color checkbox + picker (falls
  back to the existing left-cyan/right-magenta split when off), and
  numeric X%/Y%/Radius% fields for precise placement alongside dragging.
- **Add/delete**, **bring to front/send to back** (z-order).
- **Undo/redo** (buttons + Ctrl+Z/Ctrl+Y), a plain history-stack of
  committed element-list snapshots -- drag/resize only push one entry
  per gesture (on release), not per pointer-move frame.
- **Save layout** persists the current elements; **saveable named
  presets** (save current as / load / delete) let you keep more than
  one layout around and switch between them.

New backend surface, kept separate from the generic `update_config()`
on purpose: a `dashboard` config patch through that endpoint replaces
the *entire* `dashboard` sub-dict, which would silently wipe
`web_port`/`enable_web`/`background`/`slots` on every layout save.
`controller.dashboard_meta()`/`save_dashboard_elements()`/
`save_dashboard_preset()`/`delete_dashboard_preset()` (routed through
`GET /api/dashboard/meta`, `POST /api/dashboard/elements`,
`POST /api/dashboard/presets`, `POST /api/dashboard/presets/delete`)
merge into the existing `dashboard` dict instead. `theme_kwargs.py`'s
element-resolution logic was pulled into a shared
`resolve_dashboard_elements(cfg)` so `dashboard_kwargs()` (what
actually starts the theme) and `dashboard_meta()` (what the canvas
reads) can never disagree about "what's the layout right now".

Verified: pure-function geometry/color/snapping helpers unit-tested in
isolation (hex/rgb conversion, accent derivation, resize-radius math,
snap-distance logic); the production frontend build is clean; and a
full Playwright run against the real built frontend + a live backend
(no panel attached) confirmed, with screenshots at each step, the
default layout renders correctly, clicking a gauge selects it and
opens the property panel, dragging moves it and updates the panel
live, Save Layout persists to `app_config.json`, Add Gauge/Delete/
Undo round-trip correctly, and preset save actually reaches the
backend. The saved custom layout from that browser session was then
fed back through the real `dashboard_theme.build_static_background()`/
`render_frame()` (full cairo rendering, not a stub) and rendered
correctly. **Not yet verified on real hardware** -- specifically,
editing live over an actual panel's `/frame.jpg` mirror rather than
the "no screen connected" placeholder.

**Fix (feature-parity gap):** the canvas above covered gauge layout
but the web UI still had no way to set the panel background -- style
preset, color scheme, or a custom image -- something `app.py`'s
Tkinter Dashboard tab has always had. Added a Background section
under the canvas (style + scheme selects, plus a plain text image-path
field when "Custom image" is picked -- no native file browse, same
reasoning as the video theme's path field in Phase 3), backed by a new
`controller.save_dashboard_background()` / `POST /api/dashboard/
background` that merges into the `dashboard` dict the same way the
elements/preset endpoints do, and `dashboard_meta()` now also returns
the resolved background plus `BACKGROUND_PRESETS`/
`BACKGROUND_COLOR_SCHEMES` label metadata. Verified headlessly
(endpoint round-trip, `theme_kwargs.dashboard_kwargs()` picks up the
saved value with `web_port`/`elements`/`presets` all left untouched)
and via a Playwright session against the real built frontend + live
backend: switching to Custom image, typing a path, and saving all
worked with no console errors, and the value persisted server-side.

### Phase 6 — Richer elements and options — ✅ DONE (pending a real-machine pass)

Three new element types alongside the existing gauge, plus one new
per-gauge styling option -- all additive to Phase 4's element model
(`{id, type, x, y, z, opacity, ...type-specific fields}`), so an old
config with only gauge elements keeps rendering exactly as before.

- **Text labels** (`type: "text"`): a free-standing string, not bound
  to a stat -- its own `text`/`font_size`/`color`/`align`. Fully
  static (baked into the background image at Start/Apply time, same
  as the gauge titles), since the text itself never changes frame to
  frame.
- **History graphs** (`type: "graph"`): a line or bar chart
  (`style`) plotting a bound `stat`'s recent values over
  `history_seconds`, in its own `width`/`height` box (a rectangle, not
  a gauge's circle, so it gets independent width/height instead of one
  shared `radius`). The border+title bakes into the static background
  like everything else; the actual bars/line are the one genuinely
  dynamic thing Phase 6 adds -- redrawn every frame in `render_frame()`
  from a rolling per-element `deque` that `run()`'s loop maintains
  itself (sized from `history_seconds`/the loop's own 10Hz period,
  since `render_frame()` has no way to know how much wall-clock time
  actually elapsed between frames). A `None` sample (stat unavailable)
  leaves a gap rather than plotting a false zero.
- **Custom images** (`type: "image"`): an arbitrary photo/logo dropped
  onto the layout as its own positioned/sized element -- cover-fit and
  alpha-composited at build time, same tolerance for a bad/missing/
  unreadable path as the background image and app.py's background
  picker already have (skipped silently, no crash). The image path is
  a plain text field in the canvas, same reasoning as the video
  theme's path field and the background picker's custom-image path --
  a browser file input can't hand back a real filesystem path.
- **Gauge gradients** (`color2` on a `type: "gauge"` element): an
  optional second ring color -- when set, the static track and the lit
  value arc both sweep from `color` to `color2` instead of the single-
  color fade every gauge has always had. `None` (the default) keeps
  today's look exactly as it was; needle/hub stay single-toned to keep
  the change additive rather than a full gauge-rendering rewrite.

The web UI's design canvas (`DashboardCanvas.jsx`) gained "+ Add
text"/"+ Add graph"/"+ Add image" buttons alongside "+ Add gauge",
type-specific SVG representations on the canvas (a labeled box with a
resize handle for graph/image, draggable text for labels), a resize
handle that adjusts width+height independently for graph/image and
font_size for text (rather than one shared radius), and a property
panel that swaps in the right fields per element's `type` --
gauge gained the gradient toggle + second color picker alongside its
existing fields. No backend schema change was needed beyond the
gradient's `color2` field: `save_dashboard_elements()`'s "is a list"
validation already accepted an arbitrary element shape, so the new
types just work.

Verified headlessly: `build_static_background()`/`render_frame()`
render a mixed layout (one of each new type, plus a gradient gauge)
with no exceptions, correctly skip a bad image path, and a plain
`DEFAULT_ELEMENTS` layout (no new types at all) is an exact regression
check; a full `run()` loop against a fake screen confirms the
history deque accumulates and feeds `render_frame()` without error.
A full Playwright session against the real built frontend + live
backend added one of each new type via the canvas UI, edited the text
label's content, saved the layout, and confirmed the saved config --
elements of all three new types plus the gradient field -- round-trips
through the real `theme_kwargs.dashboard_kwargs()` -> `dashboard_
theme.build_static_background()`/`render_frame()` pipeline (actual
cairo rendering, not a stub) and renders correctly, including the
plotted line graph and the gracefully-skipped empty image path.
**Not yet verified on real hardware.**

**Fix (feature-parity gap): the "nothing playing" placeholder.**
`app.py`'s Tkinter Dashboard tab has always let you set a custom
placeholder image for when Spotify isn't playing (`default_art_path`,
applied live -- `dashboard_theme` re-checks it every frame, no Stop/
Start needed), but that setting never made it into the web UI at all.
Separately, the message shown in place of the track title has always
been one hardcoded line ("Life is like a door never trust a cow
because the sun can't swim"), never an actual setting in either app.
Both are now real: `dashboard_theme.py` gained `set_not_playing_
message()`/`get_not_playing_message()` mirroring the existing art-path
pair (same "re-read every frame" live-apply behavior, `DEFAULT_NOT_
PLAYING_MESSAGE` as the fallback), a new merge-safe `controller.
save_dashboard_now_playing()` / `POST /api/dashboard/now_playing`
applies both to the running dashboard immediately in addition to
persisting them, and the canvas gained a "Nothing playing" placeholder
section (plain text fields for the image path and the message,
alongside Background) -- `app.py` gained a matching message field
next to its existing image-path one. Verified headlessly (message
falls back to the default when cleared, a forced-`_MEDIA_OK` render
confirms a custom message actually shows up in place of the track
title, and the merge-safe endpoint round-trips without touching other
dashboard config) and via a Playwright session against the real built
frontend + live backend confirming the section saves and persists.

**Fix: image settings now store a managed copy, and are picked, not
typed.** Every image setting (dashboard background, the "nothing
playing" placeholder, a Phase 6 image element) used to store whatever
path a user typed or browsed to, verbatim -- fragile, since moving,
renaming, or deleting that file afterward silently breaks the feature
with no obvious explanation (the render code's tolerant catch-and-
fall-back was exactly what made this easy to overlook). New
`image_store.py` copies a picked image into an app-owned, per-user
folder (`%LOCALAPPDATA%\HongtaiScreen\images\`, created on first use)
the moment it's picked, content-hash deduplicated and PIL-validated,
and it's that copy's path that gets saved -- the original file can
move or disappear afterward with no effect. The web UI's three
plain-text "type a path" fields are now real file pickers: picking a
file uploads its bytes to a new `POST /api/dashboard/upload_image`
(`controller.upload_dashboard_image()`), which stores it and hands
back the managed path for the existing merge-safe endpoints to save,
with the stored file's name shown as a caption and a Clear button on
the placeholder-image field. `app.py`'s Tkinter Browse dialogs now
route the real path `askopenfilename()` returns through
`image_store.store_image_file()` and keep the returned managed-copy
path instead of the raw browsed one, so Tkinter gets the same fix.
Verified headlessly (dedup, validation, survives deleting the
original, full upload -> save round-trip for all three locations) and
via a Playwright session against the real built frontend + live
backend picking a real file for background/now-playing/element,
confirming the managed path is what's saved and no console errors.

**Fix (data loss): Tkinter's Dashboard tab could wipe out a web-canvas
layout/presets.** `_save_current_config()` rebuilt the whole
"dashboard" config dict from scratch out of only the fields Tkinter
has controls for -- `elements` and `presets` are web-canvas-only
concepts with no Tkinter UI, so they got silently dropped every time
Tkinter saved anything (closing to tray, Stop, switching tabs, not
just an explicit Save). Fixed to merge into the existing "dashboard"
dict instead of replacing it, matching the merge-safe pattern the web
UI's own save endpoints already use. Verified with a logic-level test
confirming `elements`/`presets` survive a Tkinter save unchanged.

**Feature: the middle column is a choice now, not just Spotify.** New
`dashboard.middle_content` setting (`"spotify"` default/`"weather"`/
`"none"`), since not everyone wants a now-playing display (or runs
Spotify). `"weather"` is a new `weather.py` module -- Open-Meteo,
free/no-API-key, geocodes a typed place name and polls current
conditions every 10 minutes from a background thread -- rendered as a
hand-drawn glowing icon + temperature + description + feels-like/
humidity + resolved place name, with tolerant fallbacks for no location
set or a lookup failure. `"none"` draws nothing there. Both UIs gained
a "Middle content" section (Show picker, plus location/units for
Weather); the "Nothing playing" section now only shows for Spotify. New
merge-safe `controller.save_dashboard_middle_content()` / `POST /api/
dashboard/middle_content` applies live, same pattern as the now-playing
settings. Verified headlessly (mocked-HTTP geocode/fetch, live
location/unit changes waking the poll thread immediately, rendered
frames for all three modes and their fallbacks, the endpoint's
round-trip and its rejection of an unknown value) and via a Playwright
session against the real built frontend + live backend.

**Feature: "Keep the panel updating while Windows is locked" (on by
default).** Mirrors the vendor XTRM Lab app's own "Keep playing when
screen is off" toggle (found reverse-engineering its app.asar --
Electron's `powerMonitor` stops rendering on lock/suspend unless it's
on); this app had no equivalent before, always rendering regardless.
New `power_state.py` detects a Windows lock via `ctypes`'
`OpenInputDesktop()` (no extra dependency), polled every 2s. Only
covers a screen *lock* -- true system suspend freezes the whole process
anyway, nothing to pause/resume there. All four themes' render loops
check `power_state.should_pause()` before their per-frame work (not
just the panel push) and skip that frame while it applies, resuming the
instant Windows unlocks. New `controller.set_keep_active_when_locked()`
/ `POST /api/keep_active_when_locked`, a matching Tkinter checkbox, and
a System-panel checkbox in the web UI, all applying immediately.
Verified headlessly (lock detection stubbed both ways, an end-to-end
run against a fake screen confirming frames stop/resume exactly on the
setting flip) and via Playwright against the real built frontend.

**Feature: the now-playing widget is a movable element, not just a
fixed middle-column display.** New `"media"` element type (`+ Add
now-playing` in the canvas toolbar) -- the same album art + track/
artist + progress bar as `_draw_spotify_middle()`, but with its own
x/y/width/height/opacity like any other canvas object, independent of
the "Middle content" setting (add one regardless of whether that's set
to Spotify/Weather/None). New `dashboard_theme._media_box()`/
`_draw_media_element()`; fully dynamic (redrawn every frame, like a
graph's plotted line) since playback position advances continuously,
so nothing about it bakes into the static background. No backend
validation needed since `elements` already round-trips arbitrary
dicts. Also: the browser's unstyled default file-picker button (used
for the background image, an image element, and the now-playing
placeholder) is now themed to match the app, and every element's
property panel gained "Center horizontally"/"Center vertically"
buttons for exact 50% placement without dragging to the snap guide.
Verified by rendering a standalone `media` element (with/without live
media, opacity < 1) and via Playwright against the real built frontend
+ live backend.

**Fix: the canvas now shows the actual picked image, and the resize/
save workflow is legible.** User feedback: picking an image only
updated a filename label -- the canvas kept drawing a generic "IMAGE"
placeholder, so it looked broken, and it wasn't obvious dragging the
one corner handle always changed width and height together, or that
this canvas is already a live preview (no Save/Start needed just to
see an edit reflected here). New `GET /api/dashboard/image?path=`
serves a previously-picked image's actual bytes back (restricted to
`image_store.py`'s own managed folder), so an image element renders
the real picture inline (clipped, opacity-aware) and all three file
pickers show a thumbnail, the instant a file's picked. Graph/image/
media elements gained separate width-only and height-only edge
handles alongside the existing corner handle. A "Save layout*" /
"Unsaved changes" indicator now shows once the layout differs from
what's actually saved, and the top hint spells out the three-stage
model explicitly (canvas preview is instant; Save layout persists it;
Start/Apply pushes it to the panel). Verified via Playwright against
the real built frontend + live backend: upload → inline render +
thumbnail in one interaction, a real mouse-drag on the width-only
handle leaving height untouched, and the dirty indicator's on-edit/
on-save transitions.

**Fix: the panel port is a "Detect screens" dropdown now, first on the
page, and the app is disabled until one's picked.** The old free-typed
port text field also had a latent bug -- its hint claimed "Port needs
Save" but no Save button was ever wired up for it. New `GET /api/ports`
(`controller.list_ports()`) exposes the same USB-VID scan
(`find_hongtai_ports()`) the Tkinter Refresh button already used, now
over HTTP. The new "Panel port" section (moved above Preview) scans on
load and on "Detect screens", auto-picks the obvious choice when
exactly one screen is found and nothing's selected, and saves a pick
immediately (no separate Save step). Controls/settings/the dashboard
canvas are disabled with an explanatory hint until a port -- a
specific one, or the explicit "Auto-detect" option -- is actually
chosen, rather than silently defaulting. Verified via Playwright: the
disabled state before any pick, picking "Auto-detect" persisting and
unlocking Controls immediately, and the selection surviving reload.

**Fixes: image elements now show the whole picture and size themselves
from it; now-playing elements can hide any of art/name/time; the clock
is a real element.** Image elements were cover-fit (crop to fill),
which cropped a freshly-added element's small default box down to a
sliver of most real pictures, and made a width-only resize look like
the picture was being overwritten rather than scaled. New `fit` field
("contain" default -- whole image visible, letterboxed; "cover"; or
"stretch") on image elements, plus a picked file's own aspect ratio
now sets the new element's box client-side (no upload round-trip)
instead of leaving the generic default square. Media elements gained
`show_art`/`show_name`/`show_time` toggles (each on by default) so any
combination can be shown. And the clock -- previously the one thing
`render_frame()` always drew unconditionally at a fixed spot -- is now
a `"clock"` element type (x/y/font size/color/opacity/show-seconds),
addable/movable/deletable like anything else; `DEFAULT_ELEMENTS`
includes one at the exact old fixed position, and `render_frame()`
only falls back to the old hardcoded draw when a saved `elements` list
has no clock entry at all, so nothing changes for a pre-upgrade config
until it's actually edited. Verified headlessly (a 4:1 test image
fully visible/letterboxed under contain-fit; art-only and time-only
media renders, which also caught and fixed a real crash -- a
non-integer coordinate reaching the glow-draw helper whenever
`show_art` was off; `DEFAULT_ELEMENTS` rendering identically to the
old fixed clock, and a clock-stripped `elements` list still rendering
the fallback pixel-identical to before) and via Playwright against the
real built frontend + live backend.

**Cleanup: removed the static clock/Spotify fallback paths and replaced
them with a real one-time migration.** The clock's "no element -> draw
the old hardcoded clock" fallback in `render_frame()` and
`_draw_spotify_middle()`/the `"spotify"` `middle_content` option (the
original fixed, un-movable, always-on now-playing display, predating
and silently overlapping the `"media"` element it's the actual
replacement for) are both gone. `slots_to_elements()` now appends a
default clock and media element directly (via new
`dashboard_theme.default_clock_element()`/`default_media_element()`),
so every layout derived fresh from `slots` -- `DEFAULT_ELEMENTS` and
`theme_kwargs.resolve_dashboard_elements()`'s fallback alike (the
latter didn't even get a clock before this) -- has both with nothing
to migrate. The one case that can't just derive its way out of this --
a config with a concrete saved `elements` list from before either
type existed -- gets a new `config_store.migrate_dashboard_elements()`,
called once from both `AppController.__init__` and `App.__init__`
right after `load_config()`. It adds a clock if missing, and a media
element (+ resets `middle_content` to `"none"`) if there's no media
element and `middle_content` was `"spotify"`/unset -- leaving alone
anyone who'd already deliberately chosen weather/none. Flagged via
`dashboard._migrated_elements_v1` so it's truly one-time: deleting the
clock/now-playing element afterward sticks. Verified headlessly (six
migration scenarios covering no-config/slots-only/old-saved-list with
each middle_content value/already-migrated/re-migration, plus a full
render pass over the new default layout with no crash) and via
Playwright against the real built frontend + a live backend seeded
with a pre-migration config: the backend migrated and persisted it on
startup, the canvas showed both widgets as separately selectable/
movable elements, the Middle content dropdown offered only Weather/
None, and the "Nothing playing" placeholder section rendered
unconditionally instead of being gated behind the removed `"spotify"`
option.

### Phase 7 — Packaging and cutover

- PyInstaller spec bundles the built frontend as data files
  (`_resource_path()` already handles `sys._MEIPASS`).
- WebView2 presence check with a clear message + download link if
  missing.
- BUILD.md gains the frontend build step.
- Switch the launcher, desktop shortcut and startup entry to the new
  app; retire `app.py`.
- Tag v2.0.0.

## Risks and open questions

**WebView2 availability.** Ships with Windows 11 and is normally
present on Windows 10 via Edge, but not guaranteed. Needs a detection
path and a friendly failure, not a crash.

**Two-language project.** Node/npm for the frontend on top of Python
raises the barrier for anyone cloning the repo. Options: commit the
built frontend bundle so `pip install -r requirements.txt && python
app.py` still just works, or require a Node build step. Leaning toward
committing the bundle — the project's whole appeal is that it runs
without ceremony.

**Reopen latency.** Measured in Phase 0 at ~1-2.5s (spawning a process
+ WebView2 init) — an accepted trade-off for keeping background RAM
under budget, not a regression to chase further unless it turns out to
feel worse in the real app than the spike suggested.

**Scope.** This is a large project. Phases 0-3 alone are a substantial
chunk of work, and they only reach parity with what exists today — the
features that motivated the rewrite don't land until Phase 5. Phases
0-1 are cheap and independently useful, so they're a good place to
start without committing to the whole thing.

## Notes on the development loop

The build and test steps for this run on a real Windows machine: the
PyInstaller build, the `npm` frontend build, and anything that touches
the panel over its COM port. Rendering logic and backend code can be
developed and tested headlessly, but the webview shell, tray behavior
and RAM measurements can only be verified on the target machine.
