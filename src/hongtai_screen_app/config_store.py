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


def migrate_dashboard_elements(cfg):
    """One-time upgrade for a saved `dashboard.elements` list from
    before the clock and now-playing widgets became their own movable/
    resizable elements (dashboard_theme.py's default_clock_element()/
    default_media_element()). Mutates `cfg` in place and returns True
    if it changed anything -- the caller is responsible for persisting
    that with save_config() (both AppController.__init__ and App.
    __init__ call this right after load_config(), so every entry point
    gets the same upgraded config, whichever UI opens it first).

    Only a config that already has a CONCRETE `elements` list saved can
    go stale like this -- a slots-only config has nothing to migrate,
    because slots_to_elements() (theme_kwargs.resolve_dashboard_
    elements()'s fallback whenever `elements` hasn't been saved yet)
    already appends both of these fresh, every time it runs. So this
    only ever adds to an existing `elements` list, never creates one
    from scratch.

    Flagged done via `dashboard._migrated_elements_v1` so it runs
    exactly once per config -- without that flag, someone who
    deliberately deletes the clock or now-playing element from their
    canvas would just get it silently re-added on the next launch,
    which would defeat the point of letting them remove it."""
    d = cfg.get("dashboard")
    if not isinstance(d, dict):
        return False
    if d.get("_migrated_elements_v1"):
        return False

    elements = d.get("elements")
    if not isinstance(elements, list) or not elements:
        # No concrete layout saved yet -- slots_to_elements() already
        # includes a clock + now-playing element on this path, nothing
        # to migrate. Still flag it done so this check is O(1) on every
        # future load instead of re-inspecting an (absent) list.
        d["_migrated_elements_v1"] = True
        return True

    from .themes import dashboard_theme  # lazy: keep load_config() light for callers that don't need it

    has_clock = any(el.get("type") == "clock" for el in elements)
    has_media = any(el.get("type") == "media" for el in elements)
    # "spotify" was the old default/only always-on now-playing display,
    # fixed to the middle column -- MIDDLE_CONTENT_OPTIONS no longer
    # offers it (see dashboard_theme.py), so a config from before this
    # migration either has that literal value saved or, just as often,
    # never saved middle_content at all and got the "spotify" default
    # implicitly. Either way is the signal that this config was relying
    # on the now-removed static display and needs a real media element
    # in its place; anyone who had already chosen "weather" or "none"
    # deliberately didn't want it, so their choice is left alone.
    had_static_now_playing = (d.get("middle_content") or "spotify") == "spotify"

    if not has_clock:
        elements.append(dashboard_theme.default_clock_element())

    if not has_media and had_static_now_playing:
        elements.append(dashboard_theme.default_media_element())
        d["middle_content"] = "none"

    d["elements"] = elements
    d["_migrated_elements_v1"] = True
    return True
