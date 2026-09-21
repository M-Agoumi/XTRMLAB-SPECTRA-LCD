"""
hongtai_screen_app -- the desktop app's actual implementation.

Everything that isn't a standalone diagnostic/setup script (those live
in scripts/, one level up) lives in this package: the backend
(controller.py, control_server.py, backend_app.py), the tray icon and
webview window (tray_icon.py, ui_window.py), the app-shell modules
they're built from (config, startup registration, desktop shortcut,
single-instance), the panel protocol driver (driver/), and the theme
renderers (themes/). The React frontend that talks to the backend over
HTTP lives separately, in frontend/ at the repo root.

Run the app with `python app.py` from the repo root -- a thin launcher
that puts src/ on sys.path and dispatches into this package's
backend_app.main() (or ui_window.main() for its own spawned window
process -- see app.py's own docstring)."""
