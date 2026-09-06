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
