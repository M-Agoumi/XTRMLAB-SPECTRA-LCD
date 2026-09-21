"""
run_ui.py -- thin CLI wrapper for hongtai_screen_app.ui_window.main()
(the pywebview window process). Same "wrapper here, real code in the
package" split as every other script under scripts/ -- see that
module's own docstring for what this actually does and why it's a
separate process from the backend.

    python scripts/run_ui.py --url http://127.0.0.1:8899/
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from hongtai_screen_app.ui_window import main

if __name__ == "__main__":
    main()
