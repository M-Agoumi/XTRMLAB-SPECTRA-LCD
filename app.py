"""
app.py -- thin launcher, kept at the repo root on purpose.

The actual application lives in src/hongtai_screen_app/ (a proper
src-layout Python package -- see ROADMAP.md's Phase 1 for why it was
split out of what used to be one big app.py). This file's only job is
to put src/ on sys.path and hand off to it, so that:

    python app.py

keeps working exactly as it always has, with no install step needed --
and so every existing Windows integration that already points at this
exact path (a "Launch at Windows startup" entry, a Desktop shortcut,
Launch Hongtai Screen.vbs) keeps working unchanged too, since none of
them needed to move.

Everything documented in README.md (--autostart, --theme, the various
tabs/settings) is unchanged -- see src/hongtai_screen_app/app.py for
the real docstring and implementation.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from hongtai_screen_app.app import main

if __name__ == "__main__":
    main()
