"""
tray_icon.py -- the system tray icon (Windows + pystray only). This
class only ever talks back to its caller through the three callbacks
it's given, so it carries no UI toolkit dependency at all -- a caller
that needs to hop back onto its own UI thread inside those callbacks
is responsible for doing so itself (pystray runs its own background
thread; see the on_show/on_stop_screen/on_quit docstrings below --
backend_app.py's callbacks don't need this at all since nothing there
touches a UI toolkit either, the window lives in a separate process).
"""
import sys
import threading

from PIL import Image as PILImage, ImageDraw as PILImageDraw

try:
    import pystray
except Exception:  # noqa: BLE001 -- broader than ImportError on purpose: pystray
    # picks a platform backend at import time (win32/appindicator/gtk/...)
    # and a missing *system* dependency for that backend (e.g. no GTK on a
    # Linux box without a tray daemon) surfaces as something other than
    # ImportError. Either way, the tray icon is optional -- callers must
    # still work without it, just falling back to a normal window.
    pystray = None


def available():
    """Whether a tray icon can be started at all on this machine --
    Windows-only (matches the "Launch at Windows startup" feature this
    exists for) and needs the optional `pystray` package
    (`pip install pystray`)."""
    return pystray is not None and sys.platform == "win32"


class TrayIcon:
    """A running (or not-yet-started) system tray icon with a
    Show window / Stop screen / Quit menu.

    `on_show`, `on_stop_screen` and `on_quit` are called with no
    arguments from pystray's own background thread, not whatever thread
    started this -- a caller built on a UI toolkit with its own event
    loop would need to hop back onto it inside each one; backend_app.py
    doesn't, since it has no UI toolkit in this process at all.
    """

    def __init__(self, on_show, on_stop_screen, on_quit):
        self._on_show = on_show
        self._on_stop_screen = on_stop_screen
        self._on_quit = on_quit
        self._icon = None

    def start(self):
        """Raises on any failure (no pystray, wrong platform, backend
        init error) -- callers catch and log, same as every other
        optional feature here (a tray icon is a nice-to-have, never
        fatal to the app itself)."""
        if not available():
            raise RuntimeError("system tray icon needs Windows + pystray installed")
        image = self._build_tray_image()
        menu = pystray.Menu(
            pystray.MenuItem("Show window", self._handle_show, default=True),
            pystray.MenuItem("Stop screen", self._handle_stop_screen),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._handle_quit),
        )
        icon = pystray.Icon("hongtai_screen", image, "Hongtai Screen Control", menu)

        def _run():
            # icon.run() blocks for the tray icon's whole lifetime; an
            # exception in here would otherwise just silently kill this
            # background thread (Python only prints it if something is
            # watching stderr) and leave callers thinking start() having
            # returned normally meant the icon actually came up. Printing
            # it here at least makes that failure visible in whatever
            # console this process has, instead of "no tray icon, no
            # explanation at all".
            try:
                icon.run()
            except Exception:  # noqa: BLE001
                import traceback
                print("(system tray icon thread crashed:)")
                traceback.print_exc()

        threading.Thread(target=_run, daemon=True).start()
        self._icon = icon

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

    # pystray's own menu callbacks -- run on pystray's background thread.
    def _handle_show(self, icon=None, item=None):
        self._on_show()

    def _handle_stop_screen(self, icon=None, item=None):
        self._on_stop_screen()

    def _handle_quit(self, icon=None, item=None):
        if icon is not None:
            icon.stop()
        self._icon = None
        self._on_quit()
