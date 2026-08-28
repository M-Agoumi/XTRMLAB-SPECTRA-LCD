"""
webpage_theme.py -- mirror a live webpage onto the panel.

    python webpage_theme.py https://example.com
    python webpage_theme.py https://example.com --interval 1
    python webpage_theme.py https://example.com --reload-every 60
    python webpage_theme.py https://example.com COM5

Defaults to 10Hz (a screenshot every ~100ms) to match the other themes
in this folder. Whether it actually holds 10Hz depends on the page --
see --interval below.

Loads the page once in a headless Chromium browser (via Playwright) at
a viewport sized exactly to the panel's resolution -- the same idea as
a phone/tablet viewport, so the page renders "full screen" on the
panel -- then repeatedly screenshots it and streams that to the
screen. The page stays open and running between screenshots, so any
JS-driven content on it (a clock, a live dashboard, a stock ticker,
an embedded video, etc.) keeps updating on its own between captures;
this script is just taking periodic snapshots of whatever it looks
like at that moment, not actually streaming video.

Good candidates: a simple status page/dashboard you control, a clock
site, a weather page, a Grafana panel -- anything designed to be
readable at a small landscape resolution. A random full desktop site
often won't look great squeezed into ~960x480, but there's nothing
stopping you from pointing this at one anyway.

Requires:
    pip install playwright pyserial pillow
    playwright install chromium      # one-time browser download (~150MB)

Notes:
  - --interval controls how often a new screenshot is taken (default
    0.1s / 10Hz, matching the other themes here). The loop times itself
    and just moves on to the next frame rather than trying to catch up,
    so if a page is heavy enough that screenshot+encode+send takes
    longer than that, you'll get whatever rate the page can actually
    sustain rather than a broken/backed-up one. A mostly-static page
    (a status page, a clock) can use a longer --interval to cut down on
    CPU/bandwidth use with no visible downside.
  - --reload-every optionally forces a full page reload every N
    seconds, for pages that don't self-update via JS and need an
    actual refresh to show new content (most single-page apps and
    dashboards don't need this).
  - The captured screenshot is always exactly the panel's resolution
    (Playwright's viewport is set to it), so there's no
    scaling/letterboxing to worry about -- what you see is a 1:1 pixel
    capture of that viewport, panel rotation included (handled the
    same way every other theme here handles it).
"""

import argparse
import io
import time

from PIL import Image

from hongtai_screen import HongtaiScreen


def run(url, port=None, interval=0.1, reload_every=None, brightness=90,
        stop_event=None, log=print, screen_factory=HongtaiScreen, on_connected=None):
    """Runs until stop_event is set (or forever if stop_event is None --
    the CLI entry point relies on Ctrl+C instead). Pulled out of main()
    so a GUI can drive this theme in a background thread.

    `on_connected(screen)`, if given, is called once right after connect()
    so a GUI can keep a live reference (e.g. for a brightness slider that
    should apply immediately instead of only on the next Start)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("This theme needs Playwright, which isn't installed:")
        log("    pip install playwright")
        log("    playwright install chromium")
        return

    screen = screen_factory(port)
    info = screen.connect()
    log(f"Connected: {info.width}x{info.height}, firmware {info.version}")
    screen.set_brightness(brightness)
    if on_connected is not None:
        on_connected(screen)

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:  # noqa: BLE001 -- almost always "chromium not installed"
            log(f"Could not launch Chromium ({e}).")
            log("If this is the first time using this theme, run: playwright install chromium")
            screen.close()
            return

        page = browser.new_page(viewport={"width": info.width, "height": info.height})
        page.set_default_timeout(60_000)  # slow pages shouldn't hard-fail at Playwright's 30s default

        log(f"Loading {url} ...")
        try:
            page.goto(url, wait_until="load")
        except Exception as e:  # noqa: BLE001
            log(f"Couldn't load {url}: {e}")
            browser.close()
            screen.close()
            return

        # Hide scrollbars so they don't show up as artifacts in the capture.
        try:
            page.add_style_tag(content="::-webkit-scrollbar { display: none; }")
        except Exception:  # noqa: BLE001
            pass

        log(f"Mirroring the page. (screenshot every {interval:.1f}s)")
        last_reload = time.time()
        try:
            while stop_event is None or not stop_event.is_set():
                frame_start = time.time()

                if reload_every and (frame_start - last_reload) >= reload_every:
                    try:
                        page.reload(wait_until="load")
                    except Exception as e:  # noqa: BLE001
                        log(f"  (reload failed: {e} -- continuing with the current page)")
                    last_reload = frame_start

                try:
                    png_bytes = page.screenshot()
                    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
                    screen.show(img)
                except Exception as e:  # noqa: BLE001
                    log(f"  (frame skipped: {e})")

                elapsed = time.time() - frame_start
                sleep_for = max(0.0, interval - elapsed)
                if stop_event is not None:
                    stop_event.wait(sleep_for)
                else:
                    time.sleep(sleep_for)
        except KeyboardInterrupt:
            pass
        finally:
            browser.close()

    screen.close()
    log("Stopped, disconnected cleanly.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("url", help="the webpage to display")
    ap.add_argument("port", nargs="?", default=None, help="COM port (auto-detected if omitted)")
    ap.add_argument("--interval", type=float, default=0.1, help="seconds between screenshots (default 0.1 / 10Hz)")
    ap.add_argument("--reload-every", type=float, default=None,
                     help="force a full page reload every N seconds (default: never, rely on the page's own JS)")
    args = ap.parse_args()

    print("Press Ctrl+C to stop.")
    run(args.url, port=args.port, interval=args.interval, reload_every=args.reload_every)


if __name__ == "__main__":
    main()
