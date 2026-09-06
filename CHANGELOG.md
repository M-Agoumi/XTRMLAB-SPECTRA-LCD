# Changelog

All notable changes to this project are documented here.

## [Unreleased] — v2.0 rewrite in progress

Internal reorganization, no user-visible feature change. See
`ROADMAP.md` for the full v2.0 plan (webview/React UI, free-form
dashboard designer) this is laying groundwork for.

### Changed
- **Restructured into a proper `src/` layout.** What used to be ~20
  loose `.py` files at the repo root is now: `app.py` (a thin launcher,
  kept at the root since it's what existing Windows Startup entries and
  Desktop shortcuts already point at) plus `src/hongtai_screen_app/`
  (the actual package: the GUI, the app-shell modules, `driver/` for
  the protocol code, `themes/` for the four theme renderers),
  `scripts/` (standalone diagnostics and thin CLI wrappers for the
  themes), `assets/` (`icon.ico`), and `packaging/`
  (`hongtai_screen.spec`). No install step needed — `python app.py`
  still just works, and so does everything under `scripts/`. See
  `README.md`'s "Project layout" section for the map.
- **Phase 1 of the v2.0 rewrite**: pulled everything that isn't
  Tkinter out of the old monolithic `app.py` into its own modules
  (`paths.py`, `config_store.py`, `startup_registration.py`,
  `desktop_shortcut.py`, `single_instance.py`, `theme_worker.py`,
  `tray_icon.py`) so the same logic can eventually be driven by a
  non-Tkinter UI. `app.py` is now a thin Tkinter layer over these.
- Fixed a latent bug this reorganization surfaced: the Windows startup
  launcher and desktop shortcut used to resolve "where's app.py" via
  their own module's `__file__`, which only worked by accident while
  that code lived directly inside `app.py`. Both now resolve the
  actual running script via `sys.modules["__main__"]` instead, which
  is correct regardless of which file the code lives in.
- **Phase 2a of the v2.0 rewrite**: a new, headless HTTP control API
  (`src/hongtai_screen_app/controller.py` + `control_server.py`,
  `scripts/run_backend.py` to run it standalone) that drives the same
  start/stop/apply/config logic as the Tkinter app, bound to
  `127.0.0.1` only. Fully additive — the Tkinter GUI is untouched.
- **Phase 2b of the v2.0 rewrite**: a minimal Vite + React frontend
  (`frontend/`) — connection status, live preview, theme/port/
  brightness/start/stop/apply controls, a live log panel — served by
  the backend itself on the same origin as the control API. The built
  bundle (`frontend/dist/`) is committed so no Node toolchain is
  required to run the app, only to change the frontend's source.
- Fixed a bug Phase 2b's real-hardware pass surfaced: `controller.py`'s
  `_selected_port()` passed the saved port *label* (a whole
  descriptive string) straight to the driver as an openable device
  path instead of translating it back to the real `COM3`-style path
  the way `app.py` already does — starting a theme with a specific
  port saved (not auto-detect) failed with a confusing
  `FileNotFoundError` even with the panel working fine. Fixed to do
  the same rescan-and-match `app.py` uses.
- **Phase 2c of the v2.0 rewrite**: `backend_app.py`
  (`scripts/run_v2_app.py`) -- a new, parallel entry point (not yet
  what `app.py`/Desktop shortcuts point at) that runs the control API,
  a tray icon, and resumes the last-running theme on launch, with its
  tray's "Show" spawning `scripts/run_ui.py` (a small pywebview
  window) as a genuinely separate process, and "Quit" terminating it.
  Confirms the two-process design Phase 0 measured actually works end
  to end.
- Fixed a bug Phase 2b's real-hardware pass surfaced: running the
  backend via `scripts/run_backend.py` wrote its own separate
  `scripts/app_config.json` instead of sharing the real one next to
  `app.py`, because `_app_base_dir()` resolved via
  `sys.modules["__main__"].__file__` — correct when `app.py` was the
  only entry point, wrong once `scripts/run_backend.py` became a
  second one. Now anchored on `paths.py`'s own file location instead,
  so every entry point agrees on the same directory.

- Worked around a Windows-only cosmetic gap in Phase 2c: pywebview's
  `icon=` only works on GTK/Qt (Linux); on Windows it's meant to come
  from freezing the app into a `.exe` with a baked-in icon resource
  (Phase 7's job). Until then, `scripts/run_ui.py` pushes `icon.ico`
  onto the window's `HWND` directly via `WM_SETICON` once it's shown,
  using the same `FindWindowW`-by-title approach `single_instance.py`
  already uses. Best-effort and unverified on a real machine yet.

- **Phase 3 of the v2.0 rewrite**: Video, Webpage and Clock settings
  forms added to the frontend, matching `app.py`'s own fields/hint text
  per theme. No backend changes needed — `update_config()` and
  `theme_kwargs.py` (both Phase 2a) already handled these settings
  generically. The video path is a plain text field rather than a file
  picker, since a browser file input can't hand back a real filesystem
  path for the backend to open.
- **Phase 3.5 of the v2.0 rewrite — live theme switching, no
  reconnect.** Not on the original plan: real-hardware testing of
  Phase 2c/3 surfaced that switching themes fully disconnected and
  reconnected the panel every time, because each theme module owned
  its own connect/loop/disconnect lifecycle instead of just producing
  frames. Fixed at the source: `demo_clock.py`/`video_theme.py`/
  `webpage_theme.py`/`dashboard_theme.py`'s `run()` now accept an
  optional pre-connected `screen=`, and skip connecting/disconnecting
  entirely when given one (plain CLI/GUI use is unaffected). New
  `screen_engine.py` (`ScreenEngine`) holds one persistent connection
  across switches and replaces `ThemeWorker` inside `controller.py`
  only — `app.py`'s Tkinter UI still uses `ThemeWorker`, untouched.
  `controller.py`'s `start()` no longer errors on "already running";
  switching to a different theme while one is active now just works,
  and `apply()` re-applies the running theme's settings without
  disconnecting either. The frontend's theme picker and Start button
  are no longer locked while something's running. Verified headlessly
  with mocked hardware (connection reuse across switches, natural
  finish still disconnects, error recovery still retries+gives up
  correctly, an intentional stop mid-error isn't mistaken for a fault)
  — not yet verified with a real panel.
- **Phase 4 of the v2.0 rewrite — layout model: slots → elements
  (backend).** `dashboard_theme.py`'s 8 gauges no longer come from a
  formula keyed by fixed slot names (`top_left`, `left_secondary`, ...);
  `build_static_background()`/`render_frame()` now walk an arbitrary
  list of gauge elements, each with its own `x`/`y`/`radius` (resolution-
  independent fractions), `color`, `opacity`, `z`-order, and a `stat`
  binding — the data model a future drag/resize design canvas (Phase 5)
  needs to exist at all. The old "big"/"secondary"/"mini" `SLOT_KINDS`
  enum is gone; whether a gauge gets full tick labels or the compact
  look is now derived from its actual baked radius instead. Migration
  is at read time, not a stored schema bump: `slots_to_elements()`
  converts old `slots` picks into equivalent elements using the exact
  same geometry formula that used to be inline, so an existing
  `app_config.json` renders unchanged. `app.py`'s Tkinter Dashboard tab
  is completely untouched — it still calls `dashboard_theme.run(slots=
  ...)` exactly as before; only `theme_kwargs.py` (controller.py's path)
  was switched to build and pass `elements=` instead. Verified
  headlessly: a full rendered frame pixel-diffed against a
  reconstruction of the exact pre-Phase-4 code for the default layout
  came back 99.94% identical (the remainder a documented, expected
  sub-pixel label-position shift from replacing two hardcoded label-gap
  constants with one continuous formula); custom slot overrides, a
  hand-built custom elements list, and an end-to-end run against a fake
  screen all verified working. Not yet verified on real hardware.
- **Phase 5 of the v2.0 rewrite — the dashboard design canvas.** The
  web UI's Dashboard tab is now a real editor: drag a gauge to move it,
  drag its corner handle to resize, click to select and edit its stat/
  color/opacity/position in a property panel, add/delete gauges,
  reorder them (bring to front/send to back), snap to the canvas
  center or another gauge's position while dragging, undo/redo
  (buttons and Ctrl+Z/Ctrl+Y), and save the result — or save it as one
  of several named presets to switch between later. It edits the exact
  same element list `dashboard_theme.py` renders (Phase 4), overlaid on
  the panel's live `/frame.jpg` mirror when connected. New backend
  endpoints (`/api/dashboard/meta`, `/api/dashboard/elements`,
  `/api/dashboard/presets[/delete]`) merge into the saved `dashboard`
  config instead of replacing it wholesale, so saving a layout tweak
  can't accidentally wipe out `web_port`/`enable_web`/`background`/
  `slots`. Rotation is stored per-element but has no handle in this
  canvas yet — `dashboard_theme.py` doesn't render it either, so a
  control for it would visibly do nothing until that lands. Verified
  with unit-tested geometry/color helpers, a clean production build,
  and a full Playwright session against the real built frontend and a
  live backend — select, drag, add, delete, undo, and preset-save all
  confirmed working, and the resulting saved layout was fed back
  through the actual cairo rendering pipeline and rendered correctly.
  Not yet verified on real hardware.
- **Fixed a Phase 5 gap**: the design canvas covered gauge layout but
  dropped the background picker (style preset, color scheme, custom
  image path) that `app.py`'s Tkinter Dashboard tab already had --
  the web UI had no way to set a custom background image at all. Added
  a Background section under the canvas with the same options, plus a
  new merge-safe `save_dashboard_background()`/`/api/dashboard/
  background` endpoint (same "merge into the dashboard dict, don't
  replace it" shape as the elements/preset endpoints) and
  `dashboard_meta()` now also returns the resolved background and the
  preset/scheme label metadata so the frontend never needs to hardcode
  `dashboard_theme.py`'s constants. The image path is a plain text
  field, same reasoning as the video theme's path field in Phase 3 --
  a browser file input can't hand back a real filesystem path. Verified
  headlessly (endpoint round-trip, `theme_kwargs.dashboard_kwargs()`
  picks up the saved value) and via a Playwright session against the
  real built frontend and a live backend: switching to Custom image,
  typing a path, and saving all worked with no console errors, and the
  save persisted correctly server-side.
- **Fixed a real-usage bug in the v2 backend's auto-resume**: quitting
  `backend_app.py` (the v2 tray app) while a theme was running never
  came back up on the next launch, even though `app.py`'s Tkinter app
  has always preserved that. Root cause: `ScreenEngine.close()`
  (called on process shutdown, to release the serial port) and
  `ScreenEngine.stop()` (an explicit Stop) both funneled through the
  same `_teardown()` -> `on_disconnected()` callback, which
  `AppController` treats as "nothing left to auto-resume" and clears
  `auto_resume_tab` accordingly -- correct for an explicit Stop, wrong
  for a plain quit while something was still running. `_teardown()`
  now skips firing `on_disconnected()` when the teardown is happening
  because `close()` is shutting the whole engine down (it still
  physically closes the port either way), so the last theme started
  is what the next launch resumes, exactly as `app.py` already does.
  Verified headlessly with a fake screen/target: quitting mid-run
  preserves and persists `auto_resume_tab`; an explicit `stop()` still
  clears it; switching themes still reuses the connection without a
  false disconnect in between.

## [1.0.0] — 2026-08-29

First tagged release. Everything below shipped before this tag existed
as a version number, so it's grouped here as the 1.0.0 baseline rather
than split into artificial pre-releases.

### Added
- From-scratch protocol driver (`hongtai_screen.py`) for the XTRM Lab
  6.2" panel (Hongtai Technology controller), reverse-engineered from
  the vendor app's own JavaScript. See `FINDINGS.md` for the protocol
  reference.
- Four themes: `demo_clock.py`, `video_theme.py`, `dashboard_theme.py`,
  `webpage_theme.py`.
- Desktop app (`app.py`, Tkinter) wrapping all four themes with a
  single Start/Stop/Apply workflow, saved settings
  (`app_config.json`), a live Log panel, single-instance guard, a
  system tray icon, launch-at-startup, and a windowless launcher
  (`make_launcher.py` / `Launch Hongtai Screen.vbs`).
- Dashboard theme: 8 independently assignable gauge slots covering 14
  live stats (CPU/GPU load, peak-core load, CPU freq, GPU temp/power,
  RAM, swap, VRAM, disk usage/activity, network, process count,
  battery), each degrading gracefully if its data source is
  unavailable.
- Dashboard background customization: 5 styles (default hex-grid,
  grid, starfield, radial, solid) × 5 color schemes, or a custom
  uploaded photo.
- Dashboard tab: two-column gauge-slot layout, dynamic window
  autosizing (so the Log panel is never hidden), and an
  **Apply (restart)** button that reloads the running theme in one
  click instead of a manual Stop then Start.
- Live web mirror: watch the panel from a phone/laptop on the same
  network, with visible connect/disconnect/error logging routed into
  the app's own Log panel (previously silent when launched without a
  console), and an **Open in browser** button once it's live.
- Auto-recovery from the panel freezing (`blind_restart`), independent
  of a full power cycle.

### Fixed
- Web mirror leaked its listening socket on Stop (`server_close()` was
  never called), causing "port already in use" on the next Start.
- Web mirror diagnostics used bare `print()`, which is silently
  discarded under a windowless (`pythonw.exe`) launch — you could
  never see a real bind error. Now routed through the same logger the
  GUI displays.
- Web mirror could keep serving a frozen frame from a dead server
  instance after a restart, because `HTTP/1.1` keep-alive connections
  outlive `shutdown()`/`server_close()`. Forced to `HTTP/1.0` so every
  poll opens a fresh connection to whichever server is actually
  listening.
- Crash-on-launch with no visible error message when a file delivery
  was out of sync with the running app (windowless launches swallow
  uncaught exceptions with no console to show them).

### Removed
- `aio_probe.py`, an experimental probe from an earlier, since
  abandoned line of investigation into the vendor app's AIO/fan
  control panel. Not part of the released feature set.
