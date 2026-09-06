"""Thin CLI shim -- the real implementation lives in
src/hongtai_screen_app/themes/dashboard_theme.py (it's also what the GUI
app imports). Kept here so standalone command-line use still works with
no separate install step:

    python scripts/dashboard_theme.py --help
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from hongtai_screen_app.themes.dashboard_theme import main

if __name__ == "__main__":
    main()
