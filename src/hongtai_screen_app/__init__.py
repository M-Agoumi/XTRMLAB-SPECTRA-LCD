"""
hongtai_screen_app -- the desktop app's actual implementation.

Everything that isn't a standalone diagnostic/setup script (those live
in scripts/, one level up) lives in this package: the Tkinter GUI
(app.py), the app-shell modules it's built from (config, startup
registration, desktop shortcut, single-instance, tray, worker thread),
the panel protocol driver (driver/), and the theme renderers
(themes/).

Run the app with `python app.py` from the repo root -- that's a thin
launcher that puts src/ on sys.path and calls into this package's
app.main(). See ROADMAP.md for where this is headed (a webview/React
UI over the same modules, minus app.py itself).
"""
