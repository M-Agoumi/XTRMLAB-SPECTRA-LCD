"""
Example "starter template" for ongoing custom content: a live clock +
basic system stats, redrawn once a second, running until you press
Ctrl+C.

    python demo_clock.py COM3

Copy this file and edit render_frame() to build your own layout --
that function just needs to return a PIL Image sized (info.width,
info.height); everything else (encoding, streaming, keepalive pings)
is handled by hongtai_screen.py for you.

Requires: pip install pyserial pillow psutil
(psutil is optional -- if it's not installed, CPU/RAM lines are skipped)
"""

import sys
import time
import datetime

from PIL import Image, ImageDraw, ImageFont

from hongtai_screen import HongtaiScreen

try:
    import psutil
except ImportError:
    psutil = None


def load_font(size):
    # Falls back to PIL's built-in bitmap font if no truetype font is found
    for candidate in (
        "DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
        "arial.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


FONT_BIG = load_font(48)
FONT_MED = load_font(22)
FONT_SMALL = load_font(16)


def render_frame(width, height):
    img = Image.new("RGB", (width, height), (12, 14, 22))
    draw = ImageDraw.Draw(img)

    now = datetime.datetime.now()
    time_str = now.strftime("%H:%M:%S")
    date_str = now.strftime("%A, %d %B %Y")

    # Centered clock
    bbox = draw.textbbox((0, 0), time_str, font=FONT_BIG)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((width - tw) / 2, height * 0.28 - th / 2), time_str, font=FONT_BIG, fill=(120, 220, 255))

    bbox = draw.textbbox((0, 0), date_str, font=FONT_MED)
    dw = bbox[2] - bbox[0]
    draw.text(((width - dw) / 2, height * 0.28 + th / 2 + 10), date_str, font=FONT_MED, fill=(200, 200, 210))

    # Divider
    y_div = int(height * 0.55)
    draw.line([(20, y_div), (width - 20, y_div)], fill=(50, 55, 70), width=2)

    # System stats (optional)
    y = y_div + 16
    if psutil is not None:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent
        draw_bar(draw, 20, y, width - 40, 18, cpu, "CPU")
        y += 34
        draw_bar(draw, 20, y, width - 40, 18, mem, "RAM")
        y += 34
    else:
        draw.text((20, y), "(install psutil for CPU/RAM bars)", font=FONT_SMALL, fill=(120, 120, 130))

    return img


def draw_bar(draw, x, y, w, h, percent, label):
    percent = max(0, min(100, percent))
    draw.rectangle([x, y, x + w, y + h], outline=(80, 85, 100), width=1)
    fill_w = int((w - 2) * percent / 100)
    color = (90, 200, 120) if percent < 70 else (230, 170, 60) if percent < 90 else (220, 70, 70)
    if fill_w > 0:
        draw.rectangle([x + 1, y + 1, x + 1 + fill_w, y + h - 1], fill=color)
    draw.text((x + w + 8, y - 1), f"{label} {percent:.0f}%", font=FONT_SMALL, fill=(210, 210, 215))


def main():
    if len(sys.argv) < 2:
        print("Usage: python demo_clock.py <COM_PORT>")
        print("Example: python demo_clock.py COM3")
        sys.exit(1)

    port = sys.argv[1]
    screen = HongtaiScreen(port)
    info = screen.connect()
    print(f"Connected: {info.width}x{info.height}, firmware {info.version}")
    screen.set_brightness(90)

    print("Streaming live clock. Press Ctrl+C to stop.")
    try:
        while True:
            img = render_frame(info.width, info.height)
            screen.show(img)
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        screen.close()
        print("Stopped, disconnected cleanly.")


if __name__ == "__main__":
    main()
