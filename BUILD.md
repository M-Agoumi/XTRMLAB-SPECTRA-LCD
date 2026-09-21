# Building a standalone .exe

This is only needed if you want a double-clickable `Hongtai Screen.exe`
instead of running `python app.py`. Nobody needs to do this to just use
the app -- see the main **Quick start** in `README.md` for that.

This has to be done **on a Windows machine, by you** — a PyInstaller
build has to run on the same OS/architecture it targets, and bundles
whatever's actually `pip install`ed in the environment you build from.

## 1. Set up a clean build environment

Use a fresh virtual environment so the exe only bundles what this
project actually needs, not everything else you've ever installed:

```
python -m venv build_venv
build_venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
```

If you use `webpage_theme.py` (Playwright), also run
`playwright install chromium` in this environment first -- see the
Playwright note below, though, before assuming it belongs in the exe.

## 2. Build the frontend

The exe bundles the React UI as static files, not as source -- build
it once (needs Node; this step doesn't need to happen in the Python
build_venv above):

```
cd frontend
npm install
npm run build      # writes frontend/dist/
cd ..
```

Skip this only if `frontend/dist/` is already present and up to date
(e.g. you haven't touched `frontend/src/` since the last build) --
`git status` will show it as unmodified in that case.

## 3. Build the exe

Run this from the **repo root** (not from inside `packaging\`) — the
spec's paths (`app.py`, `assets\icon.ico`, `frontend\dist`, the `src`
pathex) are all relative to wherever `pyinstaller` is invoked from:

```
pyinstaller packaging\hongtai_screen.spec
```

This reads `packaging\hongtai_screen.spec` (already in this repo, see
there for what it does and why) and produces `dist\Hongtai Screen.exe`
— a single, no-console, icon-bearing executable that bundles both
halves of the app (backend/tray and the webview window -- see
`app.py`'s own docstring for the `--ui` dispatch that makes one exe
cover both).

## 4. Test it

Run `dist\Hongtai Screen.exe` directly. Things worth specifically
checking, since none of this was testable from here (a Linux sandbox
built the spec, but never ran the actual .exe):

- **First run creates `app_config.json` next to the exe.** Move the
  exe to wherever you actually want it to live *before* configuring
  anything, since settings are saved next to it.
- **The window icon and taskbar icon** both show the app icon, not a
  generic one.
- **Panel connection, all four theme tabs, Start/Stop/Apply.**
- **"Launch at Windows startup"** — tick it, reboot (or log off/on),
  confirm it comes back with no console window and resumes the theme
  you last had running. This path was rewritten for the frozen build
  (the exe now points the Startup shortcut at itself, not at a
  `pythonw.exe` + script pair) — it's exercised the least by anything
  testable outside real Windows, so double-check it works.
- **The system tray icon** (needs `pystray`, already in
  `requirements.txt`) — closing the window should dismiss to tray, not
  quit, and clicking "Show" should spawn the window process again
  (`--ui`, see `app.py`'s docstring) rather than trying to run
  `run_ui.py` as a separate script, which won't exist next to a frozen
  build.
- **The webview window itself** — if WebView2 isn't present on the
  build/test machine, `ui_window.py` should show a clear message box
  with a download link, not a silent failure or a raw traceback.
- **The Dashboard tab's background image picker and web mirror.**
- Windows Defender / SmartScreen may flag a brand-new, unsigned exe on
  first run ("Windows protected your PC") — this is normal for any
  unsigned indie tool, not a sign something's wrong. Code-signing is
  out of scope here (it needs a paid certificate); "More info" → "Run
  anyway" gets past it, and telling people that up front in your
  release notes saves them a scare.

## Notes on what's bundled

- **`pystray`, `nvidia-ml-py` (pynvml), `winsdk`** are optional at
  runtime already (the app degrades gracefully without them) — but
  PyInstaller needs them actually installed in the build environment
  to bundle them at all. Install the full `requirements.txt` before
  building if you want every feature available in the exe, even ones
  you personally don't use.
- **Playwright is unusual for packaging**: it needs its own downloaded
  Chromium binary (`playwright install chromium`, ~150MB) at runtime,
  separately from the Python package. PyInstaller does *not* bundle
  that browser download automatically. If you don't use
  `webpage_theme.py`, it's simplest to leave `playwright` out of the
  build environment entirely (the tab just reports the theme
  unavailable, same as any other missing optional dependency) rather
  than trying to bundle a whole browser into the exe.
- **`opencv-python-headless`** is a large dependency (`video_theme.py`)
  — expect the exe to be a few hundred MB once numpy/opencv/pycairo are
  all in it. That's normal for a bundled Python + native-library app,
  not a packaging mistake.
- The spec disables UPX compression on purpose — UPX-packed opencv/
  webview builds are a common source of Windows Defender false
  positives, and the size savings aren't worth that headache for a
  release build.

## If something doesn't work in the exe but works with `python app.py`

That's almost always a packaging gap (a missing hidden import, a data
file PyInstaller didn't pick up, or a `__file__`-relative path that
assumed running from source) rather than an app bug — the exe runs the
exact same code. Run the exe from a **console** first
(`dist\Hongtai Screen.exe` from `cmd.exe`, not double-clicked) so any
traceback is visible rather than silently swallowed, the same lesson
that's already bitten this project once with windowless launches — see
the Log panel and console output for the actual error, then report
back with that text.

## Automated builds (CI/CD)

You don't have to run any of the steps above by hand for a real
release — `.github/workflows/build.yml` does it on GitHub's own
Windows runners and attaches the resulting `Hongtai Screen.exe` to a
GitHub Release automatically. It runs the test suite first
(`tests/`, on a quick Linux job); the Windows build only starts if
that passes.

**`develop` -> beta.** Every push to `develop` re-builds the exe and
re-publishes it to a single rolling **"beta"** prerelease (the `beta`
git tag is force-moved to whatever commit triggered the build, so it
always points at the latest one). This is where in-progress/unfinished
features land — grab the latest beta exe straight from the repo's
Releases page instead of building locally.

**`main` + a version tag -> production.** Pushing a tag like `v2.1.0`
builds the exe and publishes it as a normal (non-prerelease) GitHub
Release named after that tag, marked "Latest". To cut a production
release:

```
git checkout main
git merge develop          # or reset/fast-forward, whichever main's workflow is
git push origin main
git tag v2.1.0
git push origin v2.1.0
```

Only the tag push actually triggers a production build — pushing to
`main` on its own does not (there's no CI reason to rebuild `main`
every time it moves; only a version tag means "ship this").

Playwright's Chromium (`webpage_theme.py` / the Webpage Mirror theme)
is installed in every automated build, unlike a bare local build per
this file's Playwright note above — so a beta or production exe from
CI always has that theme available.
