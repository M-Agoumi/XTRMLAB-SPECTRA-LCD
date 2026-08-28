"""
diag_probe.py -- read-only diagnostics for the Hongtai/XTRM panel.

Does NOT try to reset anything, does NOT use rtscts (that hangs), does
NOT touch pnputil. It just opens the port, sends the documented probes,
and dumps every raw byte that comes back so we can tell the difference
between:

  * "the panel is silent"          (firmware not listening)
  * "the panel answers but oddly"  (framing/decoding problem on our side)
  * "the port isn't even ours"     (another process holds it)

Usage:  python diag_probe.py [COM3]
"""

import sys
import time

import serial
from serial.tools import list_ports

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else ".")
from hongtai_screen import _build_frame, CMD_GET_DEVICE_INFO, CMD_LIVE_PING  # noqa: E402

RESET_MARKER = bytes([0xFF, 0xD9, 0xFF, 0xD9])


def list_all_ports():
    print("=== serial ports visible to Windows ===")
    found = None
    for p in list_ports.comports():
        print(f"  {p.device:8s} vid={p.vid and hex(p.vid)} pid={p.pid and hex(p.pid)}  "
              f"{p.description}  [{p.hwid}]")
        if p.vid == 0x33C3:
            found = p.device
    if found:
        print(f"  -> Hongtai VID 0x33C3 panel detected on {found}")
    else:
        print("  -> !! no VID 0x33C3 device present. The panel is not enumerating at all.")
    print()
    return found


def dump(tag, data):
    if not data:
        print(f"  [{tag}] nothing received ({0} bytes)")
        return
    print(f"  [{tag}] {len(data)} bytes:")
    print(f"     hex   : {data[:160].hex(' ')}{' ...' if len(data) > 160 else ''}")
    printable = "".join(chr(b) if 32 <= b < 127 else "." for b in data[:160])
    print(f"     ascii : {printable}")


def probe(port, baud, label, send_reset=True, extra_key=None, listen=3.0):
    print(f"=== probe: {label} (baud {baud}) ===")
    try:
        ser = serial.Serial()
        ser.port = port
        ser.baudrate = baud
        ser.timeout = 0.2
        ser.write_timeout = 2
        ser.dtr = False
        ser.rts = False
        ser.open()
    except Exception as e:
        print(f"  !! could not open: {e}\n")
        return
    try:
        print(f"  opened OK. modem lines: cts={ser.cts} dsr={ser.dsr} ri={ser.ri} cd={ser.cd}")
        time.sleep(0.5)
        ser.reset_input_buffer()

        # anything arriving unsolicited? (a panel streaming its own state would show here)
        unsolicited = b""
        t = time.time() + 1.0
        while time.time() < t:
            unsolicited += ser.read(256)
        dump("unsolicited, before we send anything", unsolicited)

        if send_reset:
            ser.write(RESET_MARKER)
            ser.flush()
            time.sleep(0.2)

        if extra_key is not None:
            ser.write(_build_frame(extra_key))
            ser.flush()
            time.sleep(0.2)

        frame = _build_frame(CMD_GET_DEVICE_INFO)
        print(f"  sending getDeviceInfo: {frame.hex(' ')}")
        ser.write(frame)
        ser.flush()

        buf = b""
        deadline = time.time() + listen
        while time.time() < deadline:
            buf += ser.read(256)
        dump("reply to getDeviceInfo", buf)
    finally:
        try:
            ser.close()
        except Exception:
            pass
    print()


def main():
    detected = list_all_ports()
    port = sys.argv[1] if len(sys.argv) > 1 else (detected or "COM3")
    print(f"### using port {port}\n")

    probe(port, 2_000_000, "documented handshake (reset marker + key 6)")
    probe(port, 2_000_000, "no reset marker, straight key 6", send_reset=False)
    probe(port, 2_000_000, "live ping (key 17) first, then key 6", extra_key=CMD_LIVE_PING)
    probe(port, 921_600, "wrong-baud sanity check")
    probe(port, 115_200, "wrong-baud sanity check")

    print("### done. If every probe shows 0 bytes back but the port opens fine,")
    print("### the panel's firmware is not listening on the UART at all.")


if __name__ == "__main__":
    main()
