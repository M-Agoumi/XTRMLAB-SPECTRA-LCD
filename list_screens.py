"""
list_screens.py -- see every serial port on this machine, and which ones
look like a Hongtai-family smart screen (XTRM Lab, SAMA, Thermaltake,
ZOTAC, MSI, ASIAHORSE, and dozens of other rebrands of the same OEM
hardware -- COM3 is what it happened to be on the machine this was
originally written on, but there's no reason it'll be COM3 for you too).

Usage:
    python list_screens.py

Every other script in this folder (test_connection.py, demo_clock.py,
etc.) auto-detects the port the same way this does, so you normally
don't need to pass a port at all -- run this first only if you want to
see what's actually plugged in, or if auto-detection complains that it
found zero or more than one candidate.
"""

from serial.tools import list_ports

from hongtai_screen import HONGTAI_VID, find_hongtai_ports


def main():
    all_ports = list(list_ports.comports())

    if not all_ports:
        print("No serial ports found on this system at all.")
        return

    print(f"All serial ports ({len(all_ports)}):\n")
    for p in all_ports:
        vid = f"{p.vid:04X}" if p.vid is not None else "????"
        pid = f"{p.pid:04X}" if p.pid is not None else "????"
        is_hongtai = p.vid == HONGTAI_VID
        flag = "  <-- Hongtai-family panel" if is_hongtai else ""
        print(f"  {p.device:8s}  VID:PID {vid}:{pid}  {p.description}{flag}")

    print()
    candidates = find_hongtai_ports()
    if not candidates:
        print(f"No Hongtai-family screen found (looking for VID {HONGTAI_VID:04X}).")
        print("If you have one plugged in, check it's not being held open by")
        print('the vendor app (look for "XTRM lab" or similar in the tray).')
    elif len(candidates) == 1:
        c = candidates[0]
        print(f"Found exactly one: {c.label}")
        print(f"\nEvery script in this folder will auto-use {c.device} -- you")
        print("don't need to pass it explicitly.")
    else:
        print(f"Found {len(candidates)} candidates -- auto-detection needs one, so")
        print("you'll need to pass the port explicitly to the other scripts:\n")
        for c in candidates:
            print(f"  {c.label}")


if __name__ == "__main__":
    main()
