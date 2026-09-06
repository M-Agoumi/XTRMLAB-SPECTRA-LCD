"""
run_v2_app.py -- CLI shim for hongtai_screen_app.backend_app.main().
See that module's docstring for what this actually does (ROADMAP.md
Phase 2c: the always-running backend + tray icon + UI-process spawn).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from hongtai_screen_app.backend_app import main

if __name__ == "__main__":
    main()
