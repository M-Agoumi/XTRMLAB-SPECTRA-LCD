"""
app.py -- a desktop GUI for this whole project.

    python app.py

Pick your panel's COM port (or leave it on auto-detect), pick a theme
tab, fill in that theme's settings, hit Start. Stop switches themes or
quits cleanly. Nothing here needs the command line once you're set up.

Closing the window doesn't stop anything running -- it dismisses to a
system tray icon instead (needs `pip install pystray`; right-click it
for Show window / Stop screen / Quit). Whatever's actually streaming
when you Quit for real is remembered and picked back up automatically
the next time you launch the app, on its own, with no need to click
Start again -- whether that's a normal `python app.py`, or the Windows
startup launcher below.

Ships with NO personal video or image baked in on purpose -- the
Dashboard theme's "nothing playing" picture and the Video theme's clip
are both things *you* pick via the file browser buttons below; leave
them unset and you get sensible built-in fallbacks (a plain drawn
placeholder icon for the dashboard, and the video tab just won't start
until you choose a file).

Requires whatever the theme you use requires -- see README.md. The GUI
itself only needs Tkinter, which ships with Python already.

Running automatically at Windows startup: tick "Launch at Windows
startup" near the top of the window. That drops a small hidden-window
launcher script into your Startup folder (Windows only) that runs
`pythonw app.py --autostart` at login -- no console window, no need to
log in yourself. --autostart resumes whatever theme was last actually
streaming (falling back to Dashboard if nothing ever was), and (with
`pystray` installed) hides straight into the tray instead of leaving an
open taskbar entry. You can also run this manually:

    python app.py --autostart                  # resumes last theme, tray/minimized
    python app.py --autostart --theme video     # force a specific tab instead

Note on the Dashboard tab's web mirror: it's off by default for fresh
setups specifically because turning it on opens a network listener,
which makes Windows show a one-time firewall permission prompt the
first time it binds. That's expected -- it's what lets you view the
panel from a phone on the same network -- but if you don't want that
prompt (e.g. at every boot before you've clicked "Allow"), just leave
"Enable live web mirror" unticked.
"""

import argparse
import json
import os
import sys
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

from PIL import Image as PILImage, ImageDraw as PILImageDraw  # already a hard
# dependency of every theme here (dashboard_theme etc.), so this import is
# never gated behind pystray's optional-dependency try/except below.

import hongtai_screen
import dashboard_theme
import video_theme
import webpage_theme
import demo_clock

try:
    import pystray
except Exception:  # noqa: BLE001 -- broader than ImportError on purpose: pystray
    # picks a platform backend at import time (win32/appindicator/gtk/...)
    # and a missing *system* dependency for that backend (e.g. no GTK on a
    # Linux box without a tray daemon) surfaces as something other than
    # ImportError. Either way, the tray icon is optional -- app.py must
    # still start without it, just falling back to a normal window.
    pystray = None

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_config.json")
AUTO_DETECT = "(auto-detect)"

# Tab order in the Notebook -- kept in one place since both --theme and
# the "Launch at Windows startup" registration need to map a theme name
# to the tab index _on_start() reads.
THEME_TAB_ORDER = ["dashboard", "video", "webpage", "clock"]

STARTUP_TASK_NAME = "HongtaiScreenApp"


def _startup_script_path():
    """Where the Windows Startup-folder launcher lives, or None if this
    isn't Windows (the feature is Windows-only -- other platforms have
    their own login-item mechanisms this app doesn't try to drive)."""
    if sys.platform != "win32":
        return None
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu",
                         "Programs", "Startup", f"{STARTUP_TASK_NAME}.vbs")


def is_startup_enabled():
    path = _startup_script_path()
    return path is not None and os.path.isfile(path)


def enable_startup():
    """Writes a tiny VBScript into the Windows Startup folder that
    launches this app hidden (no console, no window flash) at login.
    VBScript's WshShell.Run(..., 0, False) is what actually gives the
    "0 windows visible" launch -- a .bat file here would still flash a
    console window briefly, which a plain Python script can't avoid on
    its own without extra dependencies.

    Deliberately just `--autostart` with no `--theme` -- which theme
    actually starts is decided at runtime from whatever was last
    actually running (see App.__init__'s auto-resume logic), not fixed
    to whatever was selected the moment this checkbox was ticked."""
    path = _startup_script_path()
    if path is None:
        raise RuntimeError("Launch-at-startup is only supported on Windows.")

    app_path = os.path.abspath(__file__)
    py_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(py_dir, "pythonw.exe")
    interpreter = pythonw if os.path.isfile(pythonw) else sys.executable

    # VBScript doesn't treat backslash as an escape character, so Windows
    # paths need no special handling -- only the quotes around each path
    # need doubling (VBScript's way of embedding a literal " in a string).
    cmd = '""{interpreter}"" ""{app}"" --autostart'.format(
        interpreter=interpreter, app=app_path)
    vbs = (
        'Set WshShell = CreateObject("WScript.Shell")\n'
        f'WshShell.Run "{cmd}", 0, False\n'
    )

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(vbs)


def disable_startup():
    path = _startup_script_path()
    if path and os.path.isfile(path):
        os.remove(path)


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


class App(tk.Tk):
    def __init__(self, autostart=False, autostart_theme=None):
        super().__init__()
        self.title("Hongtai Screen Control")
        self.geometry("760x620")
        self.minsize(640, 520)

        self.cfg = load_config()
        self.log_queue = queue.Queue()
        self.worker = None
        self.stop_event = None
        self.running_theme = None
        self.running_tab_index = None
        self.active_screen = None  # set once connect() succeeds; lets a few
                                    # settings (brightness always, Dashboard's
                                    # art/web-mirror) apply live instead of
                                    # only taking effect on the next Start
        self._tray_icon = None  # a running pystray.Icon, once _start_tray()
                                 # succeeds -- see there for when that is
        self._poll_after_id = None  # the pending _poll_log_queue() timer,
                                     # cancelled before destroy() so Tk
                                     # doesn't try to fire it into a
                                     # destroyed window (harmless, but a
                                     # noisy "invalid command name" on exit)
        # Which tab, if any, was actually streaming last -- set on a
        # successful Start, cleared on an explicit Stop or when a theme
        # ends on its own. Persisted to app_config.json so it survives a
        # restart; that's what lets the *next* launch resume it
        # automatically. See _save_current_config()/_on_start()/_on_stop().
        self._auto_resume_tab = self.cfg.get("auto_resume_tab")

        self._build_widgets()
        self._refresh_ports()
        self._poll_log_queue()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Start the tray icon on every launch, not just --autostart --
        # this is what makes the window's X button dismiss to tray
        # (_on_close() checks self._tray_icon) instead of quitting and
        # stopping whatever theme is running, whether you started the app
        # by hand or it came up at boot. Manual launches still just show
        # the window normally; only --autostart also starts hidden.
        have_tray = self._start_tray()

        # Figure out what to auto-start, if anything: an explicit --theme
        # always wins; otherwise fall back to whatever was last actually
        # streaming (persisted across restarts); --autostart with neither
        # falls back to Dashboard. A plain launch with no --autostart
        # flag still resumes automatically if something was left running
        # -- that's the whole point of remembering it.
        if autostart_theme in THEME_TAB_ORDER:
            resume_theme = autostart_theme
        elif self._auto_resume_tab is not None and 0 <= self._auto_resume_tab < len(THEME_TAB_ORDER):
            resume_theme = THEME_TAB_ORDER[self._auto_resume_tab]
        elif autostart:
            resume_theme = "dashboard"
        else:
            resume_theme = None  # nothing to resume, and not explicitly asked to autostart

        if resume_theme is not None:
            self.notebook.select(THEME_TAB_ORDER.index(resume_theme))
            if autostart:
                # The boot-time / explicit-flag path also hides the
                # window -- a plain "python app.py" that happens to
                # resume a remembered session still just shows normally.
                if have_tray:
                    # Tray icon is running and will bring the window
                    # back on request -- no need for a taskbar entry.
                    self.withdraw()
                else:
                    # No tray available (pystray not installed, or not
                    # Windows) -- fall back to a minimized-but-still-in-
                    # the-taskbar window rather than disappearing with
                    # no way back short of Task Manager.
                    self.iconify()
            self.after(300, self._on_start)

    # ------------------------------------------------------------------ #
    # layout
    # ------------------------------------------------------------------ #
    def _build_widgets(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="Panel port:").pack(side="left")
        self.port_var = tk.StringVar(value=self.cfg.get("port", AUTO_DETECT))
        self.port_combo = ttk.Combobox(top, textvariable=self.port_var, width=42, state="readonly")
        self.port_combo.pack(side="left", padx=(6, 6))
        ttk.Button(top, text="Refresh", command=self._refresh_ports).pack(side="left")

        ttk.Label(top, text="   Brightness:").pack(side="left", padx=(14, 0))
        self.brightness_var = tk.IntVar(value=self.cfg.get("brightness", 90))
        # A trace on the variable (not Scale's command=) -- ttk.Scale's
        # command only fires on a live mouse drag, not on the variable
        # being set programmatically, which made this silently do nothing.
        # A variable trace fires uniformly either way.
        self.brightness_var.trace_add("write", self._on_brightness_change)
        ttk.Scale(top, from_=10, to=100, orient="horizontal", variable=self.brightness_var,
                  length=120).pack(side="left", padx=(4, 0))
        # Numeric readout next to the slider -- width fixed so the layout
        # doesn't shift as the value goes from 1 to 3 digits.
        self.brightness_label = ttk.Label(top, text=str(self.brightness_var.get()), width=4)
        self.brightness_label.pack(side="left", padx=(4, 0))

        startup_row = ttk.Frame(self, padding=(10, 0, 10, 0))
        startup_row.pack(fill="x")
        self.startup_var = tk.BooleanVar(value=is_startup_enabled())
        startup_cb = ttk.Checkbutton(startup_row, text="Launch at Windows startup (resumes whatever was last running)",
                                      variable=self.startup_var, command=self._on_toggle_startup)
        startup_cb.pack(side="left")
        if sys.platform != "win32":
            # The VBS-launcher trick is Windows-only; show it disabled
            # with an explanation rather than hiding it, so it's obvious
            # why it can't be ticked on other platforms.
            startup_cb.configure(state="disabled")
            ttk.Label(startup_row, text="(Windows only)", foreground="#666").pack(side="left", padx=(6, 0))

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.dashboard_tab = self._build_dashboard_tab()
        self.video_tab = self._build_video_tab()
        self.webpage_tab = self._build_webpage_tab()
        self.clock_tab = self._build_clock_tab()
        self.notebook.add(self.dashboard_tab, text="Dashboard")
        self.notebook.add(self.video_tab, text="Video")
        self.notebook.add(self.webpage_tab, text="Webpage Mirror")
        self.notebook.add(self.clock_tab, text="Clock")
        self.notebook.select(self.cfg.get("active_tab", 0))

        controls = ttk.Frame(self, padding=(10, 0, 10, 10))
        controls.pack(fill="x")
        self.start_btn = ttk.Button(controls, text="Start", command=self._on_start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(controls, text="Stop", command=self._on_stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(6, 0))
        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(controls, textvariable=self.status_var).pack(side="left", padx=(14, 0))

        log_frame = ttk.Frame(self, padding=(10, 0, 10, 10))
        log_frame.pack(fill="both", expand=False)
        ttk.Label(log_frame, text="Log:").pack(anchor="w")
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, state="disabled",
                                                    font=("Consolas", 9) if os.name == "nt" else ("Menlo", 10))
        self.log_text.pack(fill="both", expand=True)

    def _build_dashboard_tab(self):
        f = ttk.Frame(self.notebook, padding=12)
        d = self.cfg.get("dashboard", {})

        # Off by default for a fresh config -- opening this listens for
        # network connections, which makes Windows show a one-time
        # firewall permission prompt the first time it binds. That's
        # expected if you actually want to view the panel from a phone
        # on the same network, but it's a surprise otherwise (e.g. at
        # every boot via "Launch at Windows startup" before you've
        # clicked Allow), so it's opt-in rather than on by default.
        self.dash_web_enable = tk.BooleanVar(value=d.get("enable_web", False))
        ttk.Checkbutton(f, text="Enable live web mirror (view from your phone -- opens a network port,"
                                 "\ntriggers a one-time Windows firewall prompt)",
                        variable=self.dash_web_enable,
                        command=self._apply_dash_web_settings).grid(row=0, column=0, columnspan=3, sticky="w")

        ttk.Label(f, text="Web mirror port:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.dash_web_port = tk.StringVar(value=str(d.get("web_port", 8765)))
        ttk.Entry(f, textvariable=self.dash_web_port, width=10).grid(row=1, column=1, sticky="w", pady=(6, 0))
        ttk.Button(f, text="Apply", command=self._apply_dash_web_settings).grid(
            row=1, column=2, sticky="w", padx=(6, 0))

        ttk.Label(f, text="\"Nothing playing\" image:").grid(row=2, column=0, sticky="w", pady=(12, 0))
        self.dash_art_path = tk.StringVar(value=d.get("default_art_path", "") or "")
        self.dash_art_path.trace_add("write", self._on_dash_art_change)
        ttk.Entry(f, textvariable=self.dash_art_path, width=48).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(2, 0))
        ttk.Button(f, text="Browse...", command=self._pick_dash_art).grid(row=3, column=2, sticky="w", padx=(6, 0))
        ttk.Button(f, text="Clear (use plain placeholder)", command=lambda: self.dash_art_path.set("")).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))

        ttk.Label(f, text="Nothing is bundled here -- pick your own image, or leave this blank\n"
                          "and a plain drawn placeholder is used instead.",
                  foreground="#666").grid(row=5, column=0, columnspan=3, sticky="w", pady=(10, 0))
        ttk.Label(f, text="Everything above applies live while the Dashboard is running --\n"
                          "no need to Stop/Start.", foreground="#666").grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(4, 0))
        return f

    def _build_video_tab(self):
        f = ttk.Frame(self.notebook, padding=12)
        v = self.cfg.get("video", {})

        ttk.Label(f, text="Video file:").grid(row=0, column=0, sticky="w")
        self.video_path = tk.StringVar(value=v.get("path", "") or "")
        ttk.Entry(f, textvariable=self.video_path, width=48).grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Button(f, text="Browse...", command=self._pick_video).grid(row=1, column=2, sticky="w", padx=(6, 0))

        self.video_loop = tk.BooleanVar(value=v.get("loop", True))
        ttk.Checkbutton(f, text="Loop when it ends", variable=self.video_loop).grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self.video_bw = tk.BooleanVar(value=v.get("bw", False))
        ttk.Checkbutton(f, text="Force black & white", variable=self.video_bw).grid(
            row=3, column=0, columnspan=3, sticky="w")
        self.video_audio = tk.BooleanVar(value=v.get("audio", False))
        ttk.Checkbutton(f, text="Also play audio (needs ffmpeg + pygame)", variable=self.video_audio).grid(
            row=4, column=0, columnspan=3, sticky="w")

        ttk.Label(f, text="FPS override (blank = use the video's own rate):").grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.video_fps = tk.StringVar(value=str(v.get("fps", "")) if v.get("fps") else "")
        ttk.Entry(f, textvariable=self.video_fps, width=10).grid(row=6, column=0, sticky="w")

        ttk.Label(f, text="No video is bundled with this app -- point it at any file you have.",
                  foreground="#666").grid(row=7, column=0, columnspan=3, sticky="w", pady=(12, 0))
        ttk.Label(f, text="Changing these while running needs Stop then Start again -- a\n"
                          "different file/rate means reopening the video.",
                  foreground="#666").grid(row=8, column=0, columnspan=3, sticky="w", pady=(4, 0))
        return f

    def _build_webpage_tab(self):
        f = ttk.Frame(self.notebook, padding=12)
        w = self.cfg.get("webpage", {})

        ttk.Label(f, text="URL:").grid(row=0, column=0, sticky="w")
        self.webpage_url = tk.StringVar(value=w.get("url", ""))
        ttk.Entry(f, textvariable=self.webpage_url, width=52).grid(row=1, column=0, columnspan=3, sticky="w")

        ttk.Label(f, text="Screenshot interval (seconds):").grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.webpage_interval = tk.StringVar(value=str(w.get("interval", 0.1)))
        ttk.Entry(f, textvariable=self.webpage_interval, width=10).grid(row=3, column=0, sticky="w")

        ttk.Label(f, text="Force a full reload every N seconds (blank = never):").grid(
            row=4, column=0, sticky="w", pady=(10, 0))
        self.webpage_reload = tk.StringVar(
            value=str(w.get("reload_every", "")) if w.get("reload_every") else "")
        ttk.Entry(f, textvariable=self.webpage_reload, width=10).grid(row=5, column=0, sticky="w")

        ttk.Label(f, text="Needs Playwright (pip install playwright, then\n"
                          "playwright install chromium) -- a real page, best kept simple\n"
                          "and landscape (a status page, clock, weather widget, your own .html file).",
                  foreground="#666").grid(row=6, column=0, columnspan=3, sticky="w", pady=(12, 0))
        ttk.Label(f, text="Changing these while running needs Stop then Start again.",
                  foreground="#666").grid(row=7, column=0, columnspan=3, sticky="w", pady=(4, 0))
        return f

    def _build_clock_tab(self):
        f = ttk.Frame(self.notebook, padding=12)
        ttk.Label(f, text="A live clock with CPU/RAM bars -- no settings beyond the\n"
                          "port and brightness above.", foreground="#666").pack(anchor="w")
        return f

    # ------------------------------------------------------------------ #
    # file pickers
    # ------------------------------------------------------------------ #
    def _pick_dash_art(self):
        path = filedialog.askopenfilename(
            title="Choose an image for \"nothing playing\"",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif"), ("All files", "*.*")])
        if path:
            self.dash_art_path.set(path)

    def _pick_video(self):
        path = filedialog.askopenfilename(
            title="Choose a video file",
            filetypes=[("Videos", "*.mp4 *.mkv *.avi *.mov *.webm"), ("All files", "*.*")])
        if path:
            self.video_path.set(path)

    # ------------------------------------------------------------------ #
    # ports
    # ------------------------------------------------------------------ #
    def _refresh_ports(self):
        try:
            candidates = hongtai_screen.find_hongtai_ports()
        except Exception as e:  # noqa: BLE001
            candidates = []
            self._log(f"(couldn't scan serial ports: {e})")
        values = [AUTO_DETECT] + [c.label for c in candidates]
        self._port_devices = {c.label: c.device for c in candidates}
        self.port_combo["values"] = values
        if self.port_var.get() not in values:
            self.port_var.set(AUTO_DETECT)

    def _selected_port(self):
        label = self.port_var.get()
        if label == AUTO_DETECT:
            return None
        return self._port_devices.get(label, None)

    # ------------------------------------------------------------------ #
    # logging (thread-safe: workers only ever put() onto the queue)
    # ------------------------------------------------------------------ #
    def _log(self, msg):
        self.log_queue.put(str(msg))

    def _poll_log_queue(self):
        drained = False
        while True:
            try:
                msg = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.log_text.configure(state="normal")
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
            drained = True
        if drained and self.worker is not None and not self.worker.is_alive():
            # the background thread finished on its own (video ended
            # without --loop, a connection error, etc.) -- reset the UI
            self._on_theme_finished()
        try:
            self._poll_after_id = self.after(100, self._poll_log_queue)
        except tk.TclError:
            # The window was destroyed (e.g. Quit from the tray menu)
            # while this was scheduled -- nothing left to poll into.
            pass

    # ------------------------------------------------------------------ #
    # start / stop
    # ------------------------------------------------------------------ #
    def _on_start(self):
        if self.worker is not None and self.worker.is_alive():
            return

        tab_index = self.notebook.index(self.notebook.select())
        port = self._selected_port()
        brightness = self.brightness_var.get()

        try:
            if tab_index == 0:
                theme_name, target, kwargs = self._dashboard_kwargs(port, brightness)
            elif tab_index == 1:
                theme_name, target, kwargs = self._video_kwargs(port, brightness)
            elif tab_index == 2:
                theme_name, target, kwargs = self._webpage_kwargs(port, brightness)
            else:
                theme_name, target, kwargs = self._clock_kwargs(port, brightness)
        except ValueError as e:
            messagebox.showerror("Can't start", str(e))
            return

        self.stop_event = threading.Event()
        kwargs["stop_event"] = self.stop_event
        kwargs["log"] = self._log
        kwargs["on_connected"] = self._on_screen_connected

        # Remember this as "what to resume next launch" -- cleared again
        # on an explicit Stop or if this theme ends on its own (see
        # _on_stop() / _on_theme_finished()), so it only carries over
        # into the next launch if the app was closed/quit while this was
        # still actually running.
        self._auto_resume_tab = tab_index
        self._save_current_config()
        self.running_theme = theme_name
        self.running_tab_index = tab_index
        self.status_var.set(f"Running: {theme_name}")
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.notebook.tab(0, state="disabled" if tab_index != 0 else "normal")

        self.worker = threading.Thread(target=self._run_safely, args=(target, kwargs), daemon=True)
        self.worker.start()

    def _run_safely(self, target, kwargs):
        try:
            target(**kwargs)
        except Exception as e:  # noqa: BLE001 -- surface it in the log instead of a silent thread death
            self._log(f"ERROR: {e}")

    def _on_screen_connected(self, screen):
        """Called from the worker thread right after connect() succeeds
        (see the on_connected= kwarg each theme's run() takes). Just
        stashes the reference -- plain attribute assignment is safe from
        another thread under the GIL, and this is all a GUI callback
        needs to start applying settings live via screen.set_brightness()
        etc. instead of only on the next Start."""
        self.active_screen = screen

    def _on_brightness_change(self, *_args):
        """Fires on every change to the slider's variable, including every
        intermediate value during a drag.

        Brightness is applied by the screen driver as a per-frame software
        dim (a black overlay blended over each rendered frame before it's
        sent) rather than relying on the panel's hardware brightness
        command, which -- per the official app's own source -- doesn't
        appear to do much visibly on this panel by itself. Because it's
        just a number the render loop reads on its next frame, this call
        is instant and non-blocking: no reconnect, no interruption, so no
        debouncing/threading is needed here either."""
        value = self.brightness_var.get()
        self.brightness_label.configure(text=str(value))
        if self.active_screen is None:
            return  # nothing running yet -- takes effect on the next Start instead
        try:
            self.active_screen.set_brightness(value)
        except Exception as e:  # noqa: BLE001
            self._log(f"(brightness change failed: {e})")

    def _on_dash_art_change(self, *_args):
        # Fires on every edit to the art-path field (typing, Browse,
        # Clear) -- dashboard_theme re-checks this path every frame, so
        # this genuinely takes effect on the very next frame, no restart.
        dashboard_theme.set_default_art_path(self.dash_art_path.get().strip() or None)

    def _apply_dash_web_settings(self):
        if not (self.running_tab_index == 0 and self.active_screen is not None):
            return  # nothing running yet -- takes effect on the next Start instead
        try:
            port = self._parse_int(self.dash_web_port.get(), "Web mirror port", default=8765)
        except ValueError as e:
            self._log(f"(web mirror: {e})")
            return
        # Always disable first -- enable_web_mirror() is a no-op if a
        # mirror is already running, which is exactly what would silently
        # swallow a port change otherwise.
        self.active_screen.disable_web_mirror()
        if self.dash_web_enable.get():
            self.active_screen.enable_web_mirror(port=port)

    def _on_toggle_startup(self):
        """Ticking this writes (or removes) a small hidden-window launcher
        script in the Windows Startup folder -- see enable_startup()'s
        docstring for why a .vbs rather than a .bat or a shortcut."""
        try:
            if self.startup_var.get():
                enable_startup()
                self._log("Launch at Windows startup: enabled "
                          "(resumes whatever theme was last running, or Dashboard if nothing was).")
            else:
                disable_startup()
                self._log("Launch at Windows startup: disabled.")
        except Exception as e:  # noqa: BLE001
            self._log(f"(couldn't update Windows startup launcher: {e})")
            messagebox.showerror("Launch at startup", str(e))
            # Reflect what's actually on disk rather than the failed click.
            self.startup_var.set(is_startup_enabled())

    def _on_stop(self):
        if self.stop_event is not None:
            self.stop_event.set()
        self.status_var.set("Stopping...")
        self.stop_btn.configure(state="disabled")
        # A deliberate Stop means "don't resume this automatically next
        # launch" -- persisted right away rather than waiting for
        # _on_theme_finished() (which only fires once the worker thread
        # actually winds down), so it's not lost if the app is closed or
        # crashes before that happens.
        self._auto_resume_tab = None
        self._save_current_config()

    def _on_theme_finished(self):
        self.worker = None
        self.stop_event = None
        self.running_theme = None
        self.running_tab_index = None
        self.active_screen = None
        self.status_var.set("Idle")
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        for i in range(4):
            self.notebook.tab(i, state="normal")
        if self._auto_resume_tab is not None:
            # The theme ended on its own (video finished without --loop,
            # a connection error, etc.) rather than via Stop -- nothing
            # is actually running any more, so there's nothing to resume.
            self._auto_resume_tab = None
            self._save_current_config()

    # ------------------------------------------------------------------ #
    # per-theme kwarg building
    # ------------------------------------------------------------------ #
    def _dashboard_kwargs(self, port, brightness):
        web_port = self._parse_int(self.dash_web_port.get(), "Web mirror port", default=8765)
        art_path = self.dash_art_path.get().strip() or None
        return "Dashboard", dashboard_theme.run, dict(
            port=port, web_port=web_port, enable_web=self.dash_web_enable.get(),
            default_art_path=art_path, brightness=brightness,
        )

    def _video_kwargs(self, port, brightness):
        path = self.video_path.get().strip()
        if not path:
            raise ValueError("Pick a video file first.")
        if not os.path.isfile(path):
            raise ValueError(f"Video file not found:\n{path}")
        fps = self._parse_float(self.video_fps.get(), "FPS", default=None, allow_blank=True)
        return "Video", video_theme.run, dict(
            video_path=path, port=port, fps=fps, bw=self.video_bw.get(),
            audio=self.video_audio.get(), loop=self.video_loop.get(), brightness=brightness,
        )

    def _webpage_kwargs(self, port, brightness):
        url = self.webpage_url.get().strip()
        if not url:
            raise ValueError("Enter a URL first.")
        interval = self._parse_float(self.webpage_interval.get(), "Interval", default=0.1)
        reload_every = self._parse_float(self.webpage_reload.get(), "Reload interval",
                                          default=None, allow_blank=True)
        return "Webpage Mirror", webpage_theme.run, dict(
            url=url, port=port, interval=interval, reload_every=reload_every, brightness=brightness,
        )

    def _clock_kwargs(self, port, brightness):
        return "Clock", demo_clock.run, dict(port=port, brightness=brightness)

    @staticmethod
    def _parse_int(text, label, default=None):
        text = (text or "").strip()
        if not text:
            return default
        try:
            return int(text)
        except ValueError:
            raise ValueError(f"{label} must be a whole number.")

    @staticmethod
    def _parse_float(text, label, default=None, allow_blank=False):
        text = (text or "").strip()
        if not text:
            if allow_blank or default is not None:
                return default
            raise ValueError(f"{label} is required.")
        try:
            return float(text)
        except ValueError:
            raise ValueError(f"{label} must be a number.")

    # ------------------------------------------------------------------ #
    # config persistence
    # ------------------------------------------------------------------ #
    def _save_current_config(self):
        self.cfg.update({
            "port": self.port_var.get(),
            "brightness": self.brightness_var.get(),
            "active_tab": self.notebook.index(self.notebook.select()),
            "auto_resume_tab": self._auto_resume_tab,
            "dashboard": {
                "enable_web": self.dash_web_enable.get(),
                "web_port": self.dash_web_port.get(),
                "default_art_path": self.dash_art_path.get().strip() or None,
            },
            "video": {
                "path": self.video_path.get().strip() or None,
                "loop": self.video_loop.get(),
                "bw": self.video_bw.get(),
                "audio": self.video_audio.get(),
                "fps": self.video_fps.get().strip() or None,
            },
            "webpage": {
                "url": self.webpage_url.get().strip(),
                "interval": self.webpage_interval.get().strip(),
                "reload_every": self.webpage_reload.get().strip() or None,
            },
        })
        save_config(self.cfg)

    def _cancel_poll_timer(self):
        if self._poll_after_id is not None:
            try:
                self.after_cancel(self._poll_after_id)
            except Exception:  # noqa: BLE001
                pass
            self._poll_after_id = None

    def _on_close(self):
        if self._tray_icon is not None:
            # A tray icon is running -- the window's X button hides to
            # tray rather than quitting (matching normal tray-app
            # behavior); the tray menu's "Quit" is what actually exits.
            self._save_current_config()
            self.withdraw()
            return
        self._save_current_config()
        if self.stop_event is not None:
            self.stop_event.set()
        self._cancel_poll_timer()
        self.destroy()

    # ------------------------------------------------------------------ #
    # system tray (Windows + pystray only -- see _start_tray())
    # ------------------------------------------------------------------ #
    def _start_tray(self):
        """Starts a system tray icon so the app can run with no taskbar
        presence at all -- right-click it for Show/Stop screen/Quit.
        Windows-only (matches the "Launch at Windows startup" feature
        this exists for) and needs the optional `pystray` package
        (`pip install pystray`); returns False without one, so callers
        know to fall back to a plain minimized window instead of the app
        disappearing with no way back."""
        if pystray is None or sys.platform != "win32":
            return False
        try:
            image = self._build_tray_image()
            menu = pystray.Menu(
                pystray.MenuItem("Show window", self._tray_show, default=True),
                pystray.MenuItem("Stop screen", self._tray_stop_screen),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self._tray_quit),
            )
            icon = pystray.Icon("hongtai_screen", image, "Hongtai Screen Control", menu)
            threading.Thread(target=icon.run, daemon=True).start()
            self._tray_icon = icon
            return True
        except Exception as e:  # noqa: BLE001 -- a tray icon is a nice-to-have, never fatal
            self._log(f"(couldn't start the system tray icon: {e})")
            return False

    @staticmethod
    def _build_tray_image():
        """A small drawn placeholder icon (a monitor glyph) -- nothing is
        bundled as a .ico file, so this is built on the fly with PIL."""
        size = 64
        img = PILImage.new("RGBA", (size, size), (0, 0, 0, 0))
        d = PILImageDraw.Draw(img)
        d.rounded_rectangle([4, 4, size - 4, size - 4], radius=12, fill=(30, 32, 40, 255))
        d.rounded_rectangle([14, 16, size - 14, size - 26], radius=4,
                             outline=(120, 200, 255, 255), width=3)
        d.rectangle([size // 2 - 8, size - 20, size // 2 + 8, size - 14], fill=(120, 200, 255, 255))
        return img

    # Tray menu callbacks run on pystray's own background thread, not the
    # Tk main thread -- each hops back onto the Tk thread via after(0, ...)
    # rather than touching widgets directly.
    def _tray_show(self, icon=None, item=None):
        self.after(0, self._show_window)

    def _show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _tray_stop_screen(self, icon=None, item=None):
        self.after(0, self._on_stop)

    def _tray_quit(self, icon=None, item=None):
        icon.stop()
        self.after(0, self._quit_for_real)

    def _quit_for_real(self):
        self._tray_icon = None
        self._save_current_config()
        if self.stop_event is not None:
            self.stop_event.set()
        self._cancel_poll_timer()
        self.destroy()


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--autostart", action="store_true",
                     help="select a theme tab and start it immediately (minimized), "
                          "instead of waiting for you to click Start. Used by the "
                          "Windows startup launcher; also handy to run by hand.")
    ap.add_argument("--theme", choices=THEME_TAB_ORDER, default=None,
                     help="force a specific tab for --autostart. Default: resume "
                          "whatever theme was last actually running, or dashboard "
                          "if nothing ever was.")
    return ap.parse_args()


if __name__ == "__main__":
    args = parse_args()
    App(autostart=args.autostart, autostart_theme=args.theme).mainloop()
