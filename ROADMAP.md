# Roadmap — v2.0 UI rewrite

Plan for replacing the Tkinter desktop app with a webview + Python
backend architecture, and turning the Dashboard's fixed 8-slot layout
into a free-form design canvas.

Status: **planned, not started.** v1.0.0 (the current Tkinter app) stays
the shipped, working version throughout.

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

## Architecture

```
┌──────────────────────────────────────────────┐
│ pywebview window (WebView2, Windows' own      │
│ Edge engine — not a bundled Chromium)         │
│   React frontend, served over localhost       │
└───────────────┬──────────────────────────────┘
                │ HTTP / WebSocket on 127.0.0.1
┌───────────────┴──────────────────────────────┐
│ Python backend (one process, always running)  │
│  • local HTTP server: frontend + control API  │
│    + /frame.jpg live feed                     │
│  • config, tray icon, single-instance,        │
│    startup registration                       │
│  • theme render loop  (unchanged)             │
│  • hongtai_screen.py driver  (unchanged)      │
└──────────────────────────────────────────────┘
```

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

**Tray behavior: destroy, not hide.** WebView2 is a multi-process
browser engine; a hidden window keeps its processes resident. To keep
idle RAM near today's ~84MB, minimizing to tray **destroys** the window
and reopening creates a fresh one. Cost: reopening takes ~0.5-2s
instead of being instant. This requires all real state to live in the
Python backend, with the page treated as stateless UI — good practice
anyway.

**Low lock-in.** Because the UI is an HTTP app, pywebview is just a
window shell. If it ever disappoints, the shell can be swapped without
touching the UI, which still runs in any browser.

## Phases

### Phase 0 — Spike (throwaway)

Prove the stack before committing to it. A pywebview window loading a
page from a local server, showing the live frame, with one button that
calls into Python to start/stop the dashboard.

**Measure:** RAM with the window open, RAM after minimize-to-tray
(window destroyed), and how long reopening actually takes.

This is the go/no-go. If WebView2 doesn't reclaim memory the way we
expect, we learn it here for a day's work instead of after a month.
Code gets thrown away either way.

### Phase 1 — Extract the backend (no visible change)

Pull everything that isn't Tkinter out of `app.py` into modules both
UIs can use: config load/save, port enumeration, worker/thread
lifecycle, tray icon, single-instance mutex, startup registration,
desktop shortcut.

The Tkinter app keeps working, now as a thin UI over those modules.
Low risk, independently valuable, and it's what makes running two UIs
side by side possible.

### Phase 2 — Control API + frontend shell

Generalize the mirror's HTTP server into the app's own local server:
frontend bundle, control endpoints (state, config get/set,
start/stop/apply), a log stream (SSE or WebSocket), and the frame feed.

React app shell with port/brightness/startup controls, the log panel,
and the live preview. Tray integration with the destroy/recreate
behavior from Phase 0.

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

**Does RAM actually come back?** The whole premise of destroy-on-tray.
Phase 0 answers this with real numbers before anything else is built.

**Two-language project.** Node/npm for the frontend on top of Python
raises the barrier for anyone cloning the repo. Options: commit the
built frontend bundle so `pip install -r requirements.txt && python
app.py` still just works, or require a Node build step. Leaning toward
committing the bundle — the project's whole appeal is that it runs
without ceremony.

**Reopen latency.** Accepted trade-off, but worth measuring in Phase 0
— if it's 3+ seconds rather than under 1, it may be worth keeping the
window alive when the panel isn't streaming, or pre-warming.

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
