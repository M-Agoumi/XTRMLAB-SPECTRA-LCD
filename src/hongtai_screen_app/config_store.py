"""
config_store.py -- app_config.json load/save, and the couple of constants
every UI needs to agree on (the auto-detect sentinel, the fixed theme-tab
order). Split out of app.py (Phase 1 of ROADMAP.md's v2.0 rewrite) --
none of this is Tkinter, and the future webview UI reads/writes the same
file through the same functions.
"""
import json

from .paths import CONFIG_PATH

AUTO_DETECT = "(auto-detect)"

# Tab order in the Notebook -- kept in one place since both --theme and
# the "Launch at Windows startup" registration need to map a theme name
# to the tab index _on_start() reads.
THEME_TAB_ORDER = ["dashboard", "video", "webpage", "clock"]


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001 -- missing/corrupt config is fine, just start fresh
        return {}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:  # noqa: BLE001 -- best-effort, never block on this
        pass
