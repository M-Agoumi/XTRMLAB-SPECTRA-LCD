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


def migrate_dashboard_preset_shape(cfg):
    """One-time upgrade for saved `dashboard.presets` entries from
    before a preset could carry its own background: each value used to
    be a bare `elements` list, now it's `{"elements": [...],
    "background": {...} or None}` (see save_dashboard_preset()'s
    docstring) so loading a preset can restore the exact look it was
    saved with, not just its layout against whatever background
    happens to be configured globally right now. A bare-list entry is
    wrapped as `{"elements": <the list>, "background": None}` --
    `None` means "no background of its own", which is exactly what a
    pre-upgrade preset actually was, so this changes nothing about how
    it looks, only how it's stored.

    Mutates `cfg` in place and returns True if it changed anything --
    same caller contract as the other migrate_* functions in this
    module. Flagged via `dashboard._migrated_preset_shape_v1` so it
    runs exactly once."""
    d = cfg.get("dashboard")
    if not isinstance(d, dict):
        return False
    if d.get("_migrated_preset_shape_v1"):
        return False

    presets = d.get("presets")
    if isinstance(presets, dict):
        upgraded = {}
        for name, value in presets.items():
            if isinstance(value, list):
                upgraded[name] = {"elements": value, "background": None}
            else:
                upgraded[name] = value
        d["presets"] = upgraded

    # Always flags done (even if nothing needed upgrading, e.g. a fresh
    # config with no presets at all yet) -- same "flag it regardless"
    # pattern migrate_dashboard_elements() uses, so this check stays
    # O(1) on every future load instead of re-inspecting `presets`.
    d["_migrated_preset_shape_v1"] = True
    return True


def seed_builtin_dashboard_presets(cfg):
    """Populates a fresh install's `dashboard.presets` with the 6
    presets the app ships from day one (dashboard_theme.
    BUILTIN_DASHBOARD_PRESETS -- see its own comment for what each one
    is) -- so a brand-new install's preset picker isn't empty on first
    run. Only when `presets` is ENTIRELY ABSENT, not merely empty: once
    someone has saved or deleted even once, `dashboard.presets` exists
    as a dict (possibly `{}`, if they deleted everything) -- that dict
    existing at all, in any shape, means "this config has already
    decided what its presets are", and reseeding over that would
    silently undo someone's deliberate choice to delete a built-in
    preset (or all of them) every time they launch the app. A config
    that has genuinely never touched presets is the only one this
    should ever apply to, which is also exactly the case a brand-new
    install is in.

    Deep-copies each preset (via a JSON round-trip -- simplest way to
    get a fully independent copy of nested dicts/lists/tuples without
    importing `copy`) so mutating a seeded preset later (rename, edit,
    delete) never reaches back into the shared BUILTIN_DASHBOARD_
    PRESETS constant itself.

    Mutates `cfg` in place and returns True if it changed anything --
    same caller contract as the other migrate_*/seed_* functions in
    this module. Flagged via `dashboard._seeded_builtin_presets_v1`,
    separately from the "already has presets" check above, so this is
    still a no-op on every load after the first even for an install
    that seeded successfully and then deleted every preset down to
    `{}` (which "presets absent" alone wouldn't distinguish from
    "never seeded")."""
    d = cfg.setdefault("dashboard", {})
    if d.get("_seeded_builtin_presets_v1"):
        return False
    d["_seeded_builtin_presets_v1"] = True
    if "presets" in d:
        return True

    from .themes import dashboard_theme  # lazy: keep load_config() light for callers that don't need it

    d["presets"] = json.loads(json.dumps(dashboard_theme.BUILTIN_DASHBOARD_PRESETS))
    return True


def migrate_dashboard_weather_element(cfg):
    """One-time upgrade for a saved config that used the old global
    `middle_content` "weather" choice (dashboard_theme.py's now-removed
    MIDDLE_CONTENT_OPTIONS/set_middle_content()) -- converts it into a
    real `weather` element (dashboard_theme.default_weather_element())
    carrying that config's `weather_location`/`weather_units`, the same
    "the old global setting becomes a real element" move
    migrate_dashboard_elements() above already made for the old
    "spotify" middle_content choice and the now-playing display.

    Mutates `cfg` in place and returns True if it changed anything --
    same caller contract as migrate_dashboard_elements() (both
    AppController.__init__ and App.__init__ call this right after it).
    Flagged via `dashboard._migrated_weather_v1` so it runs exactly
    once -- without that flag, someone who deliberately removes the
    weather element from their canvas would just get it silently
    re-added on the next launch."""
    d = cfg.get("dashboard")
    if not isinstance(d, dict):
        return False
    if d.get("_migrated_weather_v1"):
        return False

    had_weather = d.get("middle_content") == "weather"
    elements = d.get("elements")
    has_weather = isinstance(elements, list) and any(el.get("type") == "weather" for el in elements)

    if had_weather and not has_weather:
        from .themes import dashboard_theme  # lazy: keep load_config() light for callers that don't need it

        weather_el = dashboard_theme.default_weather_element()
        weather_el["location"] = d.get("weather_location") or ""
        weather_el["units"] = d.get("weather_units") or "celsius"
        elements = list(elements) if isinstance(elements, list) else []
        elements.append(weather_el)
        d["elements"] = elements

    # `middle_content`/`weather_location`/`weather_units` are retired
    # either way -- weather.py's location/units now live on the element
    # itself (see dashboard_theme.apply_weather_from_elements()), and
    # anyone who had middle_content "none" just wasn't showing weather,
    # exactly as leaving it off the canvas now means.
    d.pop("middle_content", None)
    d.pop("weather_location", None)
    d.pop("weather_units", None)
    d["_migrated_weather_v1"] = True
    return True
