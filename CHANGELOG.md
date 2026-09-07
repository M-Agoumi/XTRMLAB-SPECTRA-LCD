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
- **Phase 6 of the v2.0 rewrite — richer elements and options.** Three
  new element types alongside the existing gauge -- text labels
  (a free string, not bound to a stat), history graphs (line/bar chart
  of a bound stat's recent values, plotted from a rolling deque `run()`
  maintains), and custom images (an arbitrary photo/logo dropped in as
  its own positioned element, same tolerant fallback as the background
  image) -- plus an optional second color (`color2`) on a gauge for a
  gradient ring instead of the old single-color one. All additive to
  Phase 4's element model, so an existing config with only gauges keeps
  rendering unchanged. The design canvas gained matching "+ Add
  text"/"+ Add graph"/"+ Add image" buttons, type-specific canvas
  representations and resize behavior, and a property panel that swaps
  in the right fields per element type. Verified headlessly (mixed-
  layout render, bad-image-path fallback, a full `run()` loop
  accumulating graph history without error, and a `DEFAULT_ELEMENTS`
  regression check) and via a Playwright session against the real
  built frontend + live backend: adding one of each new type, editing
  the text label, and saving all worked, and the saved config rendered
  correctly through the real cairo pipeline afterward. Not yet
  verified on real hardware.
- **Fixed a feature-parity gap: the "nothing playing" placeholder
  image was never exposed in the web UI, and its message was never
  configurable in either app.** `app.py`'s Tkinter Dashboard tab has
  always let you pick a custom placeholder image for when Spotify
  isn't playing, applied live via `dashboard_theme.set_default_art_
  path()` -- but that setting was never carried over to the web UI at
  all. Separately, the text shown in place of the track title
  ("Life is like a door never trust a cow because the sun can't
  swim") has always been a single hardcoded line, not a real setting,
  in either app. Both are now real, live-applying settings:
  `dashboard_theme.py` gained `set_not_playing_message()`/
  `get_not_playing_message()` (same pattern as the existing art-path
  pair -- re-read every frame, so editing it takes effect on the very
  next frame, no Stop/Start), a new merge-safe `controller.
  save_dashboard_now_playing()` / `POST /api/dashboard/now_playing`
  applies both settings to the running dashboard immediately (not just
  on the next Start), and the web UI's canvas gained a "Nothing
  playing" placeholder section (image path + message, both plain text
  fields) alongside Background. `app.py`'s Tkinter tab gained a
  matching message field next to its existing image-path one. Verified
  headlessly (the message falls back to the default when cleared,
  applies live in a rendered frame, and round-trips through the
  merge-safe endpoint without disturbing other dashboard config) and
  via a Playwright session against the real built frontend + live
  backend confirming the new section saves and persists correctly.
- **Every image setting now stores a managed copy instead of a raw
  path, and is picked, not typed.** Dashboard background, the
  "nothing playing" placeholder, and a Phase 6 image element all used
  to store whatever path a user typed or browsed to, verbatim -- fine
  until that file got moved, renamed, or deleted, at which point the
  feature silently fell back to a placeholder with no obvious
  explanation why. New `image_store.py` copies a picked image into
  this app's own per-user folder (`%LOCALAPPDATA%\HongtaiScreen\
  images\`, created on first use), deduplicated by content hash so
  re-picking the same file reuses the existing copy, validated via
  PIL so a non-image or oversized (>25MB) file is rejected up front
  with a clear error instead of failing silently later at render
  time. It's that stored copy's path that ends up in
  `app_config.json` -- the original file can move or disappear
  afterward with zero effect. The web UI's three plain-text "type a
  path" fields are now real `<input type="file">` pickers: picking a
  file uploads its bytes to a new `POST /api/dashboard/upload_image`
  (`controller.upload_dashboard_image()`), which stores it via
  `image_store` and hands back the managed path for the existing
  merge-safe save endpoints to persist, same as before. Each field
  shows the stored file's name as a caption, and the placeholder-image
  field gained a Clear button. `app.py`'s Tkinter Browse dialogs
  (`_pick_dash_art`/`_pick_dash_bg_image`) now route the real path
  `askopenfilename()` returns through `image_store.store_image_file()`
  and keep the returned managed-copy path instead of the raw browsed
  one, so Tkinter gets the same fix. Verified headlessly (folder
  auto-creation, content-hash dedup, stored copy survives deleting the
  original, rejects a non-image and an oversized file with a clear
  `ValueError`, and the full upload -> save round-trip for background/
  now-playing/element) and via a Playwright session against the real
  built frontend + live backend picking a real file for all three
  locations, confirming the upload, the managed path being what's
  saved, the Clear button, and no console errors.
- **Fixed data loss: saving anything from Tkinter's Dashboard tab could
  silently wipe out a layout/presets saved from the web canvas.**
  `app.py`'s `_save_current_config()` rebuilt the entire "dashboard"
  config dict from scratch out of its own controls (`enable_web`,
  `web_port`, `default_art_path`, `not_playing_message`, `slots`,
  `background`) every time it saved -- which happens on far more than
  just an explicit Save (closing the window to tray, Stop, switching
  themes). Since `elements` and `presets` only ever exist as web-canvas
  concepts with no Tkinter controls at all, they got dropped from the
  dict every single time, silently discarding any custom layout or
  saved preset the moment the Tkinter app touched its config next.
  Fixed to merge its own fields into the existing "dashboard" dict
  instead of replacing it, the same merge-safe pattern the web UI's
  save endpoints already use. Verified with a logic-level test
  confirming `elements`/`presets` survive a save while the
  Tkinter-controlled fields still update correctly.
- **The dashboard's middle column is no longer just a Spotify display
  -- it's now a choice: Spotify, Weather, or nothing at all.** Not
  everyone wants a now-playing display glued to their PC's case (or
  runs Spotify at all); this adds a "Middle content" setting
  (`dashboard.middle_content`, default `"spotify"` -- fully backward
  compatible with every config saved before this) with two new
  options: `"weather"` shows a current-conditions readout (a hand-drawn
  glowing icon, temperature, one-line description, feels-like/humidity,
  and the resolved place name) via new `weather.py`, using Open-Meteo
  -- free, no signup, no API key, just a typed city/address -- for both
  geocoding and the actual lookup, polled every 10 minutes from a
  background thread (same reasoning as the existing Spotify poll
  thread: a real network round trip has no business happening inline
  in the 10Hz render loop); `"none"` draws nothing there at all, just
  the background showing through. Both the web UI's canvas and
  `app.py`'s Tkinter tab gained a matching "Middle content" section
  (a Show picker, plus a location/units pair that only appears for
  Weather), and the "Nothing playing" placeholder section now only
  shows when Spotify is actually selected, since it's meaningless
  otherwise. A new merge-safe `controller.save_dashboard_middle_
  content()` / `POST /api/dashboard/middle_content` applies the
  selection to the running dashboard immediately (no Stop/Start),
  mirroring the now-playing settings' live-apply pattern. Verified
  headlessly (geocoding/current-conditions against a mocked HTTP layer,
  the poll thread picking up a location/units change without waiting
  out its own interval, a rendered frame for all three content modes
  including the no-location and lookup-failure fallbacks, and the
  merge-safe endpoint round-tripping and rejecting an unknown
  `middle_content` value) and via a Playwright session against the
  real built frontend + live backend confirming the section saves, the
  Weather-only fields show/hide correctly, and the placeholder section
  hides itself outside Spotify mode, with no console errors.
- **New setting: "Keep the panel updating while Windows is locked"
  (on by default), mirroring the official XTRM Lab app's own "Keep
  playing when screen is off" toggle.** That vendor app's Electron
  `powerMonitor` stops rendering on a Windows lock-screen/suspend event
  unless that setting is on; this app had no equivalent at all before
  now -- it always kept going, silently polling stats and pushing
  frames to a panel nobody's near while the machine sits locked. New
  `power_state.py` detects "is Windows locked right now" with no extra
  dependency (`ctypes`' `OpenInputDesktop()` -- the standard userspace
  trick, no elevation needed), polled every 2 seconds from a background
  thread. True system suspend isn't something userspace can "keep
  active" through -- Windows freezes the whole process during real
  sleep, so there's nothing to pause or resume there; this is
  specifically about a screen *lock* (Win+L, an idle timeout, "Lock"
  from the Start menu), which Windows runs every process straight
  through, unaffected. All four themes' render loops (`dashboard_
  theme.py`, `video_theme.py`, `webpage_theme.py`, `demo_clock.py`)
  now check `power_state.should_pause()` before doing their per-frame
  work (not just before pushing to the panel, so a locked machine
  doesn't keep burning CPU/GPU on stats, video decode, or webpage
  screenshots nobody's watching either) and skip that frame entirely
  when it's on and the setting is off, resuming automatically the
  moment Windows unlocks. New `controller.set_keep_active_when_
  locked()` / `POST /api/keep_active_when_locked` (`system_info()`
  gained `keep_active_when_locked`/`keep_active_supported` keys) and a
  matching `app.py` Tkinter checkbox, both applying immediately, no
  restart needed. The web UI's System panel gained the checkbox too
  (disabled with "(Windows only)" off Windows, same pattern the
  existing startup checkbox already uses). Verified headlessly
  (`OpenInputDesktop`-based lock detection stubbed for both states, the
  setting ignoring lock state entirely when on, and an end-to-end test
  starting `dashboard_theme.run()` against a fake screen confirming
  frames stop the instant the setting is flipped off while locked and
  resume immediately on unlock) and via a Playwright session against
  the real built frontend + live backend, with no console errors.
- **The now-playing widget can be dragged anywhere, not just the fixed
  middle column** -- a new `"media"` element type (`+ Add now-playing`
  in the canvas toolbar) draws the same album art + track/artist +
  progress bar `_draw_spotify_middle()` always has, but positioned and
  sized like any other canvas object (x/y/width/height/opacity), so it
  can sit off-center, get resized, or overlap other elements instead of
  being locked to dead center. It's independent of the "Middle content"
  setting above -- add one whether that's set to Spotify, Weather, or
  None. New `dashboard_theme._media_box()`/`_draw_media_element()`
  render it fresh every frame (like a graph's plotted line, since
  playback position advances continuously) rather than baking it into
  the static background the way text/image elements are. No backend
  validation needed -- `elements` already round-trips arbitrary element
  dicts through config, so a `"media"` entry needed nothing beyond the
  new renderer branch in `render_frame()`.
- **Two small canvas usability fixes.** The browser's unstyled default
  "Choose File" control (used for the background image, an image
  element, and the now-playing placeholder) is now themed to match the
  rest of the app (`input[type="file"]::file-selector-button`, with a
  separate `::-moz-file-selector-button` rule since combining them in
  one selector list would silently invalidate both in browsers that
  don't recognize one of the two). And every selected element's
  property panel gained "Center horizontally"/"Center vertically"
  buttons (set x or y to exactly 0.5) -- faster and more precise than
  dragging until the existing snap-to-center guide catches. Verified by
  rendering a `"media"` element standalone (with and without live
  media, opacity < 1) and via a Playwright session against the real
  built frontend + live backend: adding a now-playing element, styled
  file inputs in both the Image and "Nothing playing" sections, and
  the center buttons independently resetting X and Y on a text element.
- **Fixed the canvas showing a placeholder box instead of the picture
  you just picked, and made the resize/save workflow legible.** Picking
  an image for the background, an image element, or the "Nothing
  playing" placeholder used to only update a filename label -- the
  canvas kept drawing a generic "IMAGE" box, so it looked like the pick
  hadn't done anything. New `GET /api/dashboard/image?path=` (`control_
  server.py`'s `_handle_dashboard_image()` / `controller.read_dashboard_
  image()`, restricted to paths already inside `image_store.py`'s own
  managed folder) serves the actual bytes back, so: an image element
  now renders the real picture directly on the canvas (clipped to its
  box, respecting opacity), and all three file pickers show a small
  thumbnail next to the filename -- all the moment a file's picked, no
  Save/Start/Apply needed, since this canvas was already a live preview
  and just wasn't using real image data. Also added an explicit "Save
  layout*" / "Unsaved changes" indicator (amber-highlighted button once
  `elements` differs from what was last loaded/saved) so it's no longer
  a guess whether a still-live edit has actually been persisted, plus a
  rewritten top hint spelling out the three-stage model (canvas preview
  is instant; Save layout persists it; Start/Apply pushes it to the
  physical panel). And graph/image/media elements gained two more
  resize handles (right edge = width only, bottom edge = height only)
  alongside the existing corner handle (both at once), since a single
  diagonal handle couldn't change just one dimension without a
  pixel-perfect straight drag. Verified via a Playwright session against
  the real built frontend + live backend: uploading an image and seeing
  it render inline plus its thumbnail within the same interaction, an
  actual mouse-drag on the width-only handle confirming height stays
  untouched, and the dirty indicator appearing on edit and clearing on
  save.
- **The web UI's panel port is a "Detect screens" dropdown now, not a
  free-typed text field -- and it's the first thing on the page,
  since nothing else here does anything useful without it.** The old
  "Port (blank = auto-detect)" text field also had a latent bug: its
  hint text said "Port needs Save", but there was never actually a
  Save button wired up for it, so a typed port could only ever take
  effect via the theme-specific settings forms' own Save buttons
  incidentally re-saving the whole config -- easy to miss entirely.
  New `GET /api/ports` (`controller.list_ports()`) exposes the same
  USB-VID serial scan (`driver/hongtai_screen.py`'s
  `find_hongtai_ports()`) the Tkinter app's own "Refresh" button next
  to its port Combobox has always used, now over HTTP. The web UI's
  new "Panel port" section -- moved above Preview, first on the page
  -- runs that scan automatically on load and again on "Detect
  screens", picks the obvious choice automatically when exactly one
  screen is found and nothing's selected yet, and saves a selection
  the instant it's picked (no separate Save step). Controls,
  the per-theme settings sections, and the dashboard canvas are all
  now disabled with a "Select a panel port above" hint until a port
  (a specific one, or the explicit "Auto-detect" option) is actually
  chosen -- previously an unset port silently worked via auto-detect,
  which was convenient with exactly one screen plugged in but gave no
  indication anything needed picking at all otherwise. Verified via a
  Playwright session against the real built frontend + live backend:
  the disabled state and its message before any port is selected,
  picking "Auto-detect" immediately persisting to config and
  unlocking Controls, and the selection surviving a page reload.
- **Fixed an image element not showing the whole picture, and made
  resizing it on one axis alone actually behave like a resize.** Every
  image element (and the background/now-playing images too, though
  those aren't user-resizable boxes) used to be cover-fit -- cropped to
  exactly fill its box on both axes -- which meant (a) a freshly-added
  element's small fixed default box cropped almost any real picture
  down to a sliver of itself before anyone touched it, and (b) dragging
  just the width handle didn't "scale" the image at all from the user's
  perspective -- it only slid the crop window over a picture that
  already filled the box, which reads as the image being overwritten
  rather than resized. New `dashboard_theme._fit_into_box()` supports
  three modes via a new `fit` field on image elements -- `"contain"`
  (new default: the whole image always visible, letterboxed, never
  cropped), `"cover"` (the old crop-to-fill behavior, still available),
  and `"stretch"` (fills the box exactly, ignoring aspect ratio) -- with
  a matching selector in the element's property panel. And a freshly
  picked image now sizes its own box to match: `DashboardCanvas.jsx`
  reads the picked file's actual pixel dimensions client-side
  (`readImageDimensions()`, no upload round-trip needed for just this)
  and sets width/height to fit that aspect ratio at a sensible on-canvas
  size, instead of leaving a brand-new element's small default square in
  place regardless of what was picked.
- **Now-playing elements can show just the pieces you want.** New
  `show_art`/`show_name`/`show_time` fields (each on by default, a
  checkbox per piece in the element's property panel) let a media
  element show any combination of cover art, track/artist text, and the
  progress bar/timestamps -- e.g. cover art alone with no text, or a
  compact time-only readout with no art. Whichever pieces are on stack
  top-to-bottom starting from the top of the box, so turning one off
  doesn't leave a gap.
- **The clock is a movable/addable element now, not a hardcoded fixed
  drawing.** It used to be the one thing `render_frame()` always drew
  unconditionally at one fixed spot, with no element, no property panel,
  and no way to move, restyle, remove, or add a second one. New
  `"clock"` element type (`+ Add clock` in the canvas toolbar) with its
  own x/y/font size/color/opacity and a "Show seconds" toggle -- added,
  dragged, resized (drag its handle, or the Center buttons), and deleted
  like any other element. `DEFAULT_ELEMENTS` now includes one at the
  exact position the fixed clock always occupied, so "Reset to defaults"
  gives back the same look as an editable element. Backward compatible
  with every layout saved before this: `render_frame()` only falls back
  to drawing the old fixed-position clock when the saved `elements` list
  has no `"clock"`-type entry at all, so nothing shifts or disappears for
  an existing config until it's actually edited to add one (at which
  point the fallback stops -- no double clock).

  Verified headlessly: a wide (4:1) test image inside a near-square box
  renders fully visible with letterboxing (not cropped) under the new
  `"contain"` default; a media element with only `show_art` set draws
  art with no text/progress bar, and one with only `show_time` draws the
  progress bar/timestamps with no art or text (this also caught and
  fixed a real bug -- a non-integer coordinate feeding into the glow-draw
  helper whenever `show_art` was off, crashing that render path
  entirely); `DEFAULT_ELEMENTS` includes exactly one clock element and
  renders identically to the pre-existing fixed clock at the reference
  resolution; and an `elements` list with the clock entry stripped back
  out (simulating a pre-upgrade saved layout) still renders the fallback
  clock, pixel-identical to before. Also verified via a Playwright
  session against the real built frontend + live backend: adding a
  clock element and seeing its property panel, uploading a wide (4:1)
  test image to a fresh image element and confirming its width/height
  fields land on the matching aspect ratio automatically, and the
  media element's three show/hide checkboxes and the image element's
  Fit selector both rendering as expected.

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
