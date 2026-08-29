# Changelog

All notable changes to this project are documented here.

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
- A **Create Desktop Shortcut** button (next to "Launch at Windows
  startup") that drops a "Hongtai Screen" desktop icon pointing at the
  standalone `.exe` when frozen, or the hidden source-mode launcher
  otherwise.

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
