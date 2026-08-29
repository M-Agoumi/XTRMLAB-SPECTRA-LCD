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

## 2. Build

```
pyinstaller hongtai_screen.spec
```

This reads `hongtai_screen.spec` (already in this repo, see there for
what it does and why) and produces `dist\Hongtai Screen.exe` — a
single, no-console, icon-bearing executable.

## 3. Test it

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
  quit.
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
- The spec disables UPX compression on purpose — UPX-packed
  Tkinter/opencv builds are a common source of Windows Defender false
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
