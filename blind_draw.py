"""
blind_draw.py -- try to DRAW without ever getting a reply.

The panel never answers getDeviceInfo, but it clearly *receives* (it
stopped its idle loop when we sent it the 0xFFD9 flush marker). The
draw path is one-way by design: key=17 to start a live session, then
raw JPEG bytes, then a key=17 ping every <=1.5s. None of that needs a
reply. So if the receive path on the panel is fine and only its
transmit path is dead, we can still own the screen -- we just have to
know the resolution, which normally comes from getDeviceInfo.

This walks a list of candidate resolutions, showing a big label on each
one for ~6 seconds. Watch the panel: whichever one fills it correctly
(not stretched, not tiled, not garbage) is the real resolution.

Usage:
    python blind_draw.py COM3              # walk the candidate list
    python blind_draw.py COM3 1280x480     # just this one, held longer
"""

import sys
import time

import serial
from PIL import Image, ImageDraw, ImageFont

from hongtai_screen import _build_frame, CMD_LIVE_PING

RESET_MARKER = bytes([0xFF, 0xD9, 0xFF, 0xD9])

CANDIDATES = [
    (1280, 480), (480, 1280),
    (800, 480), (480, 800),
    (1920, 480), (480, 1920),
    (320, 480), (480, 320),
    (1024, 600), (720, 720),
]

COLORS = [(200, 30, 40), (30, 170, 90), (40, 90, 220), (220, 160, 30)]


def make_frame(w, h, color, label):
    img = Image.new("RGB", (w, h), color)
    d = ImageDraw.Draw(img)
    size = max(20, min(w, h) // 5)
    try:
        font = ImageFont.truetype("arial.ttf", size)
    except Exception:
        font = ImageFont.load_default()
    d.rectangle([2, 2, w - 3, h - 3], outline=(255, 255, 255), width=6)
    # corner ticks: if the panel crops or tiles, these go missing
    for cx, cy in ((0, 0), (w - 60, 0), (0, h - 60), (w - 60, h - 60)):
        d.rectangle([cx, cy, cx + 60, cy + 60], fill=(255, 255, 255))
    d.text((w // 2, h // 2), label, fill=(255, 255, 255), anchor="mm", font=font)
    return img


def encode(img, cap_kb=60):
    q = 90
    while q > 10:
        buf = __import__("io").BytesIO()
        img.save(buf, format="JPEG", quality=q)
        data = buf.getvalue()
        if len(data) <= cap_kb * 1024:
            return data
        q -= 5
    return data


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "COM3"
    if len(sys.argv) > 2:
        w, h = (int(x) for x in sys.argv[2].lower().split("x"))
        sizes = [(w, h)]
        hold = 20.0
    else:
        sizes = CANDIDATES
        hold = 6.0

    ser = serial.Serial()
    ser.port = port
    ser.baudrate = 2_000_000
    ser.timeout = 0.2
    ser.write_timeout = 3
    ser.dtr = True          # node-serialport asserts both on open; ours did not
    ser.rts = True
    ser.open()
    print(f"port open. dtr/rts asserted. cts={ser.cts} dsr={ser.dsr}")

    try:
        time.sleep(0.5)
        ser.write(RESET_MARKER)
        ser.flush()
        time.sleep(0.2)
        ser.write(_build_frame(CMD_LIVE_PING))
        ser.flush()
        print("live session started (key=17). Watch the panel.\n")

        for i, (w, h) in enumerate(sizes):
            label = f"{w}x{h}"
            color = COLORS[i % len(COLORS)]
            data = encode(make_frame(w, h, color, label))
            print(f"  -> {label:>10s}  ({len(data)//1024} KB jpeg) for {hold:.0f}s")
            end = time.time() + hold
            last_ping = 0.0
            while time.time() < end:
                ser.write(data)
                ser.flush()
                if time.time() - last_ping > 1.2:
                    ser.write(_build_frame(CMD_LIVE_PING))
                    ser.flush()
                    last_ping = time.time()
                time.sleep(0.4)
                incoming = ser.read(256)
                if incoming:
                    print(f"     !! panel sent {len(incoming)} bytes: {incoming[:80].hex(' ')}")
        print("\ndone. Did anything at all appear on the panel?")
    finally:
        try:
            ser.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
