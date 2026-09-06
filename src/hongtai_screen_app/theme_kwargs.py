"""
theme_kwargs.py -- turns app_config.json's saved settings into the
(theme_name, target, kwargs) tuple needed to actually start a theme --
ThemeWorker for app.py's Tkinter UI, ScreenEngine.switch() for
controller.py's headless backend.

This is the one piece Phase 1 didn't extract: the Tkinter App class
still builds these straight from its own tk.StringVar/BooleanVar
widgets (see app.py's _dashboard_kwargs() etc.), not from the config
dict. controller.py (the new headless backend -- see ROADMAP.md Phase
2) has no widgets to read, only the same JSON shape
config_store.load_config()/save_config() round-trip -- so these
functions read straight from that dict instead. Every field here is
already stored in its canonical form (dashboard.slots values are
STAT_DEFS keys, not display labels; background.mode/scheme are preset
keys) because that's what the Tkinter app itself already persists, so
no label-to-key translation is needed here.

The Tkinter app's own inline kwarg-builders aren't switched over to
call these (yet) -- that would mean reordering when self.cfg gets
synced from widget state, which is exactly the kind of GUI behavior
change this backend-only pass is deliberately avoiding. Unifying them
is expected once the GUI itself is wired to the same backend instance
these functions were built for.
"""
from .themes import dashboard_theme, video_theme, webpage_theme, demo_clock


def _parse_int(value, default=None):
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_float(value, default=None):
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def resolve_dashboard_elements(cfg):
    """The one place that decides which gauge layout a running Dashboard
    actually uses -- prefers a saved `dashboard.elements` list (what the
    web UI's design canvas, ROADMAP.md Phase 5, writes) if there is one,
    otherwise derives one from the old `dashboard.slots` picks (or the
    defaults) via slots_to_elements(). Shared by dashboard_kwargs() below
    (what actually starts the theme) and controller.dashboard_meta()
    (what the canvas reads to initialize itself), so both always agree
    on "what's the layout right now" -- the canvas would otherwise be
    able to drift from what Start/Apply actually renders."""
    d = cfg.get("dashboard", {}) or {}
    if d.get("elements"):
        return d["elements"]
    return dashboard_theme.slots_to_elements(d.get("slots"))


def dashboard_kwargs(cfg, port, brightness):
    d = cfg.get("dashboard", {}) or {}
    web_port = _parse_int(d.get("web_port"), default=8765)
    art_path = d.get("default_art_path") or None
    elements = resolve_dashboard_elements(cfg)
    background = dict(dashboard_theme.DEFAULT_BACKGROUND, **(d.get("background") or {}))
    return "Dashboard", dashboard_theme.run, dict(
        port=port, web_port=web_port, enable_web=bool(d.get("enable_web", False)),
        default_art_path=art_path, brightness=brightness, elements=elements, background=background,
    )


def video_kwargs(cfg, port, brightness):
    v = cfg.get("video", {}) or {}
    path = v.get("path")
    if not path:
        raise ValueError("No video file configured yet -- set video.path first.")
    fps = _parse_float(v.get("fps"), default=None)
    return "Video", video_theme.run, dict(
        video_path=path, port=port, fps=fps, bw=bool(v.get("bw", False)),
        audio=bool(v.get("audio", False)), loop=bool(v.get("loop", True)), brightness=brightness,
    )


def webpage_kwargs(cfg, port, brightness):
    w = cfg.get("webpage", {}) or {}
    url = w.get("url")
    if not url:
        raise ValueError("No URL configured yet -- set webpage.url first.")
    interval = _parse_float(w.get("interval"), default=0.1)
    reload_every = _parse_float(w.get("reload_every"), default=None)
    return "Webpage Mirror", webpage_theme.run, dict(
        url=url, port=port, interval=interval, reload_every=reload_every, brightness=brightness,
    )


def clock_kwargs(cfg, port, brightness):
    return "Clock", demo_clock.run, dict(port=port, brightness=brightness)


BUILDERS = {
    "dashboard": dashboard_kwargs,
    "video": video_kwargs,
    "webpage": webpage_kwargs,
    "clock": clock_kwargs,
}


def build(theme_name, cfg, port, brightness):
    """Raises ValueError for an unknown theme name, or for a theme
    that's missing settings it needs (no video file / URL picked yet)
    -- same class of error the Tkinter app already shows in a message
    box, just without the message box."""
    try:
        builder = BUILDERS[theme_name]
    except KeyError:
        raise ValueError(f"Unknown theme {theme_name!r} -- expected one of {list(BUILDERS)}")
    return builder(cfg, port, brightness)
