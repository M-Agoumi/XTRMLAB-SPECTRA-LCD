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

Generalize the mirror's HTTP server into the backend's own local
server: frontend bundle, control endpoints (state, config get/set,
start/stop/apply), a log stream (SSE or WebSocket), and the frame feed.

React app shell with port/brightness/startup controls, the log panel,
and the live preview. The UI runs as its own process (per the Phase 0
two-process design): the tray icon (in the backend) spawns it on
"Show" and kills it on close/minimize.

### Phase 3 — Port the simple themes

Video, Webpage and Clock settings forms. Boring, low-risk, and at the
end of it the new UI does everything the old one does except the
Dashboard's slot pickers — meaning it's daily-drivable and the old app
becomes the fallback rather than the primary.

### Phase 4 — Layout model: slots → elements (backend)

The core data model change, and the thing that actually unblocks the
last three phases.

Today: `DEFAULT_SLOTS` (8 fixed keys) + `SLOT_KINDS` (big/secondary/mini).
New: an ordered list of elements, each with type, stat binding, x, y,
size, rotation, colors, font, opacity, z-order.

- `dashboard_theme.py` renders from the element list instead of computed
  slot geometry.
- Keep the static-bake optimization (dim tracks, ticks, titles baked
  once; only live values redraw) — staticness is per-element and
  independent of position. The bake just has to be invalidated whenever
  the layout changes.
- **Config schema version + migration** so existing `app_config.json`
  files keep working: the 8 slots map onto 8 default elements.

### Phase 5 — The design canvas

The hard, novel part, built on foundations already proven by then:
drag/resize/rotate handles over the live frame, a property panel for
the selected element, add/delete, z-order, snapping and alignment
guides, undo/redo, and saveable layout presets.

### Phase 6 — Richer elements and options

Where "more complicated options" actually lands, and it's incremental
once Phase 5 exists: new element types (text labels, bar/line graphs
with history, images, shapes), per-element fonts, gradients, opacity,
custom color ramps.

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
