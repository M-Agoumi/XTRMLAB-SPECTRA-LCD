"""
run_backend.py -- run the Phase 2 control API standalone, no Tkinter/GUI
at all. This is the thing to use to actually try the new backend: it
loads the same app_config.json the GUI uses, exposes it over HTTP on
127.0.0.1, and lets you drive Start/Stop/Apply with curl (or a browser
for the GET endpoints) instead of clicking through the app.

    python scripts/run_backend.py                 # default port 8899
    python scripts/run_backend.py --port 9001

Try it (from another terminal, while this is running):

    curl http://127.0.0.1:8899/api/state
    curl http://127.0.0.1:8899/api/config
    curl -X POST http://127.0.0.1:8899/api/start -d "{\\"theme\\": \\"clock\\"}"
    curl http://127.0.0.1:8899/frame.jpg -o frame.jpg
    curl -X POST http://127.0.0.1:8899/api/stop
    curl http://127.0.0.1:8899/api/logs/stream        # streams live (Ctrl+C to stop)

Ctrl+C stops the server cleanly (also stops whatever theme is running).

Note: this and the Tkinter app (`python app.py`) are two independent
ways to drive the same underlying config/driver right now -- running
both at once against the same COM port will fight over it, same as
running two copies of the GUI would. Don't run both at the same time
against real hardware.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from hongtai_screen_app.control_server import run, DEFAULT_PORT


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT,
                     help=f"control API port, 127.0.0.1 only (default {DEFAULT_PORT})")
    args = ap.parse_args()
    run(port=args.port)


if __name__ == "__main__":
    main()
