"""
Quick connectivity test. Run this FIRST before anything else.

    python test_connection.py COM3

It just connects, prints whatever the screen tells us about itself
(real resolution, firmware version, model string, etc.), sets the
brightness to a comfortable level, and shows one plain test frame
so you can confirm it's actually alive -- then exits cleanly.

IMPORTANT: close the vendor "XTRM lab" app first (check the system
tray) -- only one program can hold the COM port at a time.
"""

import sys
import time

from PIL import Image, ImageDraw, ImageFont

from hongtai_screen import HongtaiScreen


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_connection.py <COM_PORT>")
        print("Example: python test_connection.py COM3")
        sys.exit(1)

    port = sys.argv[1]
    screen = HongtaiScreen(port)

    # NOTE: if this ever times out again, the first thing to check is
    # that the port is opened with DTR ASSERTED (see the big note in
    # hongtai_screen.py). The panel gates its transmit path on DTR: with
    # DTR low it receives everything you send but answers nothing, which
    # looks exactly like a bricked panel. No reset trick, power cycle or
    # driver surgery fixes that -- only the line state does.

    print(f"Connecting to {port} ...")
    info = screen.connect()

    print("Connected! Device reports:")
    print(f"  resolution : {info.width} x {info.height}")
    print(f"  firmware   : {info.version}")
    print(f"  model      : {info.model!r}")
    print(f"  uid        : {info.uid}")
    print(f"  raw info   : {info.raw}")

    print("Setting brightness to 70% ...")
    screen.set_brightness(70)

    print("Drawing a test frame ...")
    img = Image.new("RGB", (info.width, info.height), (10, 10, 30))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, info.width - 1, info.height - 1], outline="lime", width=6)

    def font(size):
        for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except Exception:  # noqa: BLE001, PERF203
                continue
        return ImageFont.load_default()

    cx, cy = info.width // 2, info.height // 2
    draw.text((cx, cy - 45), "Hello from Python!", fill="white",
              anchor="mm", font=font(max(18, info.height // 9)))
    draw.text((cx, cy + 35), f"{info.width}x{info.height}", fill="cyan",
              anchor="mm", font=font(max(14, info.height // 13)))
    screen.show(img)

    # One frame is enough to see it, but the firmware drops the session
    # if the keep-alive stops, so hold the live session open below.

    print("Holding for 10 seconds so you can look at the screen ...")
    time.sleep(10)

    screen.close()
    print("Done, disconnected cleanly.")


if __name__ == "__main__":
    main()
