"""
hongtai_screen_app.themes -- the four things this app can actually show
on the panel: dashboard_theme (system-stat gauges), video_theme,
webpage_theme (screenshot mirror), and demo_clock. Each is both a
library module (app.py calls its run()) and a standalone CLI tool --
see scripts/ for the thin wrappers that make e.g.
`python scripts/dashboard_theme.py` work without a separate install
step.
"""
