"""
diag2_lines.py -- does the panel only talk when DTR/RTS are asserted?

Most USB-CDC firmwares gate their transmit path on the host asserting
DTR ("a terminal is attached"). Our driver explicitly holds DTR and RTS
LOW, which is exactly the configuration in which such a device stays
mute no matter what you send it. Node's serialport library, which the
vendor app uses, asserts both by default.

This sweeps every combination and also tries a mid-session DTR toggle.
Read-only: no pnputil, no rtscts, nothing that can hang.

Usage: python diag2_lines.py [COM3]
"""

import sys
import time

import serial

from hongtai_screen import _build_frame, CMD_GET_DEVICE_INFO

RESET_MARKER = bytes([0xFF, 0xD9, 0xFF, 0xD9])
PORT = sys.argv[1] if len(sys.argv) > 1 else "COM3"


def listen(ser, seconds):
    buf = b""
    end = time.time() + seconds
    while time.time() < end:
        buf += ser.read(512)
    return buf


def show(tag, data, label=""):
    if data:
        if label:
            HEARD.append(label)
        print(f"    >>> {tag}: {len(data)} BYTES BACK <<<")
        print(f"        hex   : {data[:200].hex(' ')}")
        print(f"        ascii : {''.join(chr(b) if 32 <= b < 127 else '.' for b in data[:200])}")
    else:
        print(f"    {tag}: silent")


def trial(dtr, rts, toggle=False):
    label = f"dtr={dtr} rts={rts}" + (" + mid-session DTR toggle" if toggle else "")
    print(f"=== {label} ===")
    try:
        ser = serial.Serial()
        ser.port = PORT
        ser.baudrate = 2_000_000
        ser.timeout = 0.2
        ser.write_timeout = 2
        ser.dtr = dtr
        ser.rts = rts
        ser.open()
    except Exception as e:
        print(f"    !! open failed: {e}\n")
        return
    try:
        # re-assert after open: pyserial applies these again on the open handle
        ser.dtr = dtr
        ser.rts = rts
        time.sleep(0.6)
        ser.reset_input_buffer()
        show("unsolicited", listen(ser, 0.8))

        if toggle:
            ser.dtr = not dtr
            time.sleep(0.15)
            ser.dtr = dtr
            time.sleep(0.4)
            show("after DTR toggle", listen(ser, 0.8))

        ser.write(RESET_MARKER)
        ser.flush()
        time.sleep(0.2)
        ser.write(_build_frame(CMD_GET_DEVICE_INFO))
        ser.flush()
        show("reply to getDeviceInfo", listen(ser, 2.5), label)
    finally:
        try:
            ser.close()
        except Exception:
            pass
    print()


HEARD = []


def main():
    print(f"### port {PORT}, baud 2000000\n")
    for dtr in (False, True):
        for rts in (False, True):
            trial(dtr, rts)
    trial(True, True, toggle=True)
    if HEARD:
        print(f"### THE PANEL ANSWERED under: {', '.join(HEARD)}")
        sys.exit(0)
    print("### panel stayed silent under every DTR/RTS combination.")
    sys.exit(2)


if __name__ == "__main__":
    main()
