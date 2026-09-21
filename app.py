"""
app.py -- the app's single entry point, kept at the repo root on
purpose: it's what every existing Windows integration points at (a
"Launch at Windows startup" entry, a Desktop shortcut, Launch Hongtai
Screen.vbs, and packaging/hongtai_screen.spec's frozen build), and
what `pip install -r requirements.txt && python app.py` runs with no
install step needed.

Two things live behind this one script, picked by a leading `--ui`:

    python app.py                  # the backend: control API + tray icon,
                                    # opens the window immediately
    python app.py --autostart      # same, but hidden/tray-only, resuming
                                    # whatever theme was last running
    python app.py --ui --url ...   # the window process itself -- never
                                    # run by hand; backend_app.py spawns
                                    # this (as a child process, `--ui` and
                                    # all) every time the window is shown

Both live in src/hongtai_screen_app/ (backend_app.py and ui_window.py
respectively) -- this file's only job is to put src/ on sys.path and
dispatch to the right one. The split into two processes (not two
scripts) matters for the frozen build specifically: PyInstaller
produces one .exe, and backend_app.py's window-spawning code needs
something to spawn that IS that same .exe (`sys.executable` when
frozen) rather than a separate script path a single-file build
wouldn't have alongside it -- `--ui` is how that one .exe tells its own
freshly spawned copy of itself which half to run. Running from source,
`sys.executable` is the interpreter and either half can equally well be
reached as its own script (scripts/run_v2_app.py, scripts/run_ui.py)
instead -- both paths work either way, see backend_app.py's
_on_show().
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "--ui":
        from hongtai_screen_app.ui_window import main as ui_main
        ui_main(argv[1:])
    else:
        from hongtai_screen_app.backend_app import main as backend_main
        backend_main(argv)


if __name__ == "__main__":
    main()
