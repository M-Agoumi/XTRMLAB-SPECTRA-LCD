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

If you want CPU Temp, see "Hardware sensors (CPU Temp)" below before
building -- it's a manual, one-time file placement, not something
`pip install -r requirements.txt` can do for you.

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

## Hardware sensors (CPU Temp)

CPU Temp reads via [LibreHardwareMonitorLib](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor)
(MIT-licensed, open source) instead of any vendor-supplied binary --
see `dashboard_theme.py`'s `_lhm_cpu_temp()` docstring for the full
reasoning. Setting it up is two manual steps, deliberately not
automated by `pip install` or this build:

1. `pip install pythonnet` (already in `requirements.txt`, so this is
   covered by step 1 above if you installed the full file).
2. Download a release from LibreHardwareMonitor's own
   [GitHub Releases page](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases)
   (the `LibreHardwareMonitor-net472.zip` asset), pull
   `LibreHardwareMonitorLib.dll` out of it, and place that one file at:

   ```
   assets\hardware\LibreHardwareMonitorLib.dll
   ```

   in this repo (source run: `python app.py` finds it there directly;
   frozen build: `hongtai_screen.spec`'s `datas` bundles that same
   folder into the exe the same way it already bundles `assets\icon.ico`
   and the backgrounds/fonts -- build the exe *after* placing the DLL,
   not before).

   **Unblock the file after placing it.** Windows tags anything
   downloaded from the internet -- including a file pulled out of a
   downloaded zip -- with a "Mark of the Web" flag, and pythonnet's
   .NET Framework runtime refuses to load a DLL carrying that flag
   from a local path (it treats it like loading from a network share).
   The symptom is a `FileLoadException` /
   `System.NotSupportedException` mentioning `loadFromRemoteSources` in
   the app's log, not a missing-file error, which makes it look like
   something's wrong with the DLL itself rather than a file attribute.
   Clear it with:

   ```
   Unblock-File assets\hardware\LibreHardwareMonitorLib.dll
   ```

   or right-click the file → Properties → General tab → check
   "Unblock" → OK.

Getting the DLL straight from its own maintainers rather than this repo
fetching or bundling a copy of it is the point, not an inconvenience --
that's exactly the trust boundary this replaced the vendor helper to
get. Skip this entirely and CPU Temp just reads "--", same as any
other optional stat with a missing dependency.

Either way (source or frozen), CPU Temp additionally needs
Administrator to actually load LibreHardwareMonitorLib's own sensor
driver -- a Windows platform limitation, not something this app or
that library can work around. The web UI's System section shows a
one-click "Restart as Administrator" for exactly this once pythonnet
and the DLL are both in place.

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
- **`pythonnet`** (CPU Temp) needs the .NET runtime PyInstaller's
  analyzer can't always fully trace through `clr`'s dynamic assembly
  loading -- if the exe's CPU Temp doesn't work even though
  `python app.py` from source does, see "If something doesn't work in
  the exe" below and check the console for a `clr`/`Python.Runtime`
  import error specifically.
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
