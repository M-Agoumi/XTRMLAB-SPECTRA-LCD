"""
draw_lab.py -- find out why the panel accepts commands but shows nothing.

Connection is solved (DTR). The panel answers getDeviceInfo, so our
control path works; it just isn't displaying the JPEG frames we push.
Reading the vendor app's sendPic() turned up two things our driver does
differently, plus a few cheap variations worth ruling out. Each phase
below paints a HUGE phase number on the panel and holds it, so if
anything appears you can tell me which number you saw.

Phase 0 is the control experiment: a plain restart (key=1). If the
panel's own logo video comes back, its display and our command path are
both fine and the problem is purely the frame format.

Anything the panel sends back mid-stream is printed -- the firmware has
an error-code table, so a reply here would name the actual complaint.

Usage: python draw_lab.py COM3
"""

import io
import sys
import time

import serial
from PIL import Image, ImageDraw, ImageFont

from hongtai_screen import _build_frame, _parse_reply, CMD_LIVE_PING, CMD_RESTART, \
    CMD_SET_BRIGHTNESS, CMD_GET_DEVICE_INFO

STOP_MARKER = bytes([0xFF, 0xD9, 0xFF, 0xD9])
PORT = sys.argv[1] if len(sys.argv) > 1 else "COM3"

W, H = 960, 480          # native, from getDeviceInfo
RATE_W, RATE_H = 864, 432  # what the vendor actually sends: rate=0.9 for w*h >= 230400


def open_port():
    ser = serial.Serial()
    ser.port = PORT
    ser.baudrate = 2_000_000
    ser.timeout = 0.05
    ser.write_timeout = 5
    ser.dtr = True
    ser.rts = True
    ser.open()
    ser.dtr = True
    ser.rts = True
    time.sleep(0.5)
    return ser


def handshake(ser):
    ser.reset_input_buffer()
    ser.write(STOP_MARKER)
    ser.flush()
    time.sleep(0.2)
    ser.write(_build_frame(CMD_GET_DEVICE_INFO))
    ser.flush()
    buf = b""
    end = time.time() + 3
    while time.time() < end:
        buf += ser.read(512)
        if b"\x55\xaa" in buf and len(buf) > 20:
            try:
                info = _parse_reply(buf[buf.find(b"\x55\xaa"):])
                return info
            except Exception:  # noqa: BLE001
                pass
    return None


def font(size):
    for name in ("arialbd.ttf", "arial.ttf", "segoeui.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def frame(w, h, phase, note, color):
    img = Image.new("RGB", (w, h), color)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w - 1, h - 1], outline=(255, 255, 255), width=8)
    d.text((w // 2, h // 2 - 20), str(phase), fill=(255, 255, 255),
           anchor="mm", font=font(int(h * 0.5)))
    d.text((w // 2, h - 40), note, fill=(255, 255, 255), anchor="mm", font=font(26))
    return img


def encode(img, cap_kb, start_quality=100):
    q = start_quality
    data = b""
    while q > 10:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=q)
        data = buf.getvalue()
        if len(data) <= cap_kb * 1024:
            return data, q
        q -= 5
    return data, q


def drain(ser, tag):
    got = ser.read(4096)
    if got:
        print(f"    !! panel sent {len(got)} bytes during {tag}: {got[:120].hex(' ')}")
        try:
            print(f"       ascii: {got[:120].decode('utf-8', 'replace')}")
        except Exception:  # noqa: BLE001
            pass
    return got


def stream(ser, img, cap_kb, seconds, fps, tag, resend_stop=False, quality=100):
    data, q = encode(img, cap_kb, quality)
    print(f"    {img.size[0]}x{img.size[1]} jpeg, q={q}, {len(data)/1024:.1f} KB, "
          f"{fps} fps for {seconds}s")
    if resend_stop:
        ser.write(STOP_MARKER)
        ser.flush()
        time.sleep(0.2)
    ser.write(_build_frame(CMD_LIVE_PING))
    ser.flush()
    time.sleep(0.1)
    end = time.time() + seconds
    last_ping = time.time()
    period = 1.0 / fps
    while time.time() < end:
        ser.write(data)
        ser.flush()
        if time.time() - last_ping > 1.2:
            ser.write(_build_frame(CMD_LIVE_PING))
            ser.flush()
            last_ping = time.time()
        drain(ser, tag)
        time.sleep(period)


def phase0_restart():
    print("\n=== PHASE 0: restart the panel (key=1) -- CONTROL EXPERIMENT ===")
    print("    If the vendor logo video comes back, the display itself is fine.")
    ser = open_port()
    try:
        info = handshake(ser)
        print(f"    connected, info ok: {bool(info)}")
        ser.write(_build_frame(CMD_RESTART))
        ser.flush()
        print("    restart sent. Watch the panel for the next 15 seconds ...")
    finally:
        try:
            ser.close()
        except Exception:  # noqa: BLE001
            pass
    time.sleep(15)


def main():
    print(f"### draw lab on {PORT}")
    phase0_restart()

    ser = open_port()
    try:
        info = handshake(ser)
        print(f"\nreconnected after restart. info: {info}\n")

        print("=== PHASE 1: native 960x480, streamed continuously (60 KB cap) ===")
        stream(ser, frame(W, H, 1, "960x480 native", (150, 20, 30)), 60, 8, 10, "p1")

        print("=== PHASE 2: 864x432 -- the size the vendor app actually sends (rate 0.9) ===")
        stream(ser, frame(RATE_W, RATE_H, 2, "864x432 rate=0.9", (20, 120, 60)), 80, 8, 10, "p2")

        print("=== PHASE 3: 864x432, stop-marker re-sent first, 30 fps, vendor 80 KB cap ===")
        stream(ser, frame(RATE_W, RATE_H, 3, "864x432 + stop + 30fps", (30, 60, 180)),
               80, 8, 30, "p3", resend_stop=True)

        print("=== PHASE 4: brightness to 100 first, then 864x432 ===")
        ser.write(_build_frame(CMD_SET_BRIGHTNESS, bytes([100])))
        ser.flush()
        time.sleep(0.3)
        stream(ser, frame(RATE_W, RATE_H, 4, "brightness 100", (200, 140, 20)), 80, 8, 10, "p4")

        print("=== PHASE 5: pure white 864x432, lowest quality (is it a decode-size limit?) ===")
        white = Image.new("RGB", (RATE_W, RATE_H), (255, 255, 255))
        d = ImageDraw.Draw(white)
        d.text((RATE_W // 2, RATE_H // 2), "5", fill=(0, 0, 0), anchor="mm", font=font(200))
        stream(ser, white, 20, 8, 10, "p5", quality=50)

        print("\n### done. Which phase number, if any, appeared on the panel?")
    finally:
        try:
            ser.write(_build_frame(CMD_LIVE_PING))
            ser.flush()
            ser.close()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    main()
