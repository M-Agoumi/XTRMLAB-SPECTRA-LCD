# XTRM Lab Spectra 6.2" LCD — Findings

**Status: solved and verified on hardware (28 Aug 2026).** The panel
connects, reports its real device info, and draws arbitrary Python-rendered
content the right way up.

## The panel

| | |
|---|---|
| Model | `TXW818-JD9161C-5.99inch-hor` |
| OEM | Dongguan Hongtai Technology Co., Ltd. |
| Resolution | 960 x 480 |
| Mounting angle | 180 (reported by the firmware; **the host must apply it**) |
| Firmware | 3.3 |
| UID | `042676173F3E` |
| Region | `XTRMlab_v1` |
| Transport | USB serial, VID `33C3` PID `7804`, COM3, 2,000,000 baud |

This is **not** a Turing Smart Screen. "XTRM lab" is one of ~48 rebrands of
one white-label Electron app (SAMA, Thermaltake, ZOTAC, MSI, ASIAHORSE, …)
shipping identical hardware. `turing-smart-screen-python` can complete a
handshake against it by coincidence but its draw commands are for a
different protocol, which is why it never displayed anything.

The protocol was read directly out of the vendor app's own source:
`C:\Program Files\XTRM lab\resources\app.asar` is an unencrypted Electron
bundle. A copy is in `Downloads\turing-screen\app.asar`; the interesting
code (`ClientClass`, `DeviceClass`, `sendPic`, `handleData`) sits around
offsets 1.28M–1.51M and can be read with `dd` + `tr -d '\000'` without
extracting the archive.

## The two faults that blocked this for so long

They were independent, and stacked — fixing either one alone still looked
like total failure, which is what made this so hard to read.

### Fault 1 — DTR was held low, so the panel never transmitted

The firmware gates its **transmit** path on DTR. With DTR low it still
receives everything you send perfectly well (you can blank its idle video
that way), but it will not send a single byte back. Every `getDeviceInfo`
times out and the panel looks bricked.

Proven by sweeping all four line combinations (`diag2_lines.py`): answers
under `dtr=True` with either RTS state, silent under both `dtr=False`
states.

This came from a misreading of the vendor's port setup:

```js
new SerialPort({path, baudRate: 2e6, autoOpen: false,
                endOnClose: true, dtr: false, rts: false})
```

`dtr` and `rts` are **not valid node-serialport constructor options**.
They are silently ignored — DTR/RTS are only settable via `.set()` — and
node-serialport asserts both on open by default on Windows. So the vendor
app runs with DTR *high*, despite what that line looks like. The driver had
faithfully reproduced a setting the vendor app never actually applies.

### Fault 2 — the panel was wedged, and only its own restart command cleared it

Even with the link working, the panel sat on a black screen: it answered
`getDeviceInfo`, accepted brightness changes, and ignored every frame.

**The fix is the firmware's own restart command, key=1.** It is
fire-and-forget — no reply expected — so it lands even when the panel is
answering nothing at all. One restart and the vendor logo video came back,
and every subsequent frame drew immediately.

What did **not** clear it, all tested:

| Attempt | Result |
|---|---|
| DTR pulse on open | Nothing. |
| turing-smart-screen-python's reset recipe (115200 baud, `rtscts=True`, `[0,0,0,0,0,101]`) | **Hung pyserial indefinitely** waiting on a CTS this chip never raises. Never use `rtscts=True` here. Code deleted. |
| `pnputil /remove-device` + `/scan-devices` | Left the device half-torn-down; every port open returned Access Denied until a full Windows reboot. (Amusingly the vendor app does exactly this on connect failure.) |
| Windows restart | Nothing — panel is on an always-on USB rail. |
| **Genuine mains-off power cycle** (PSU off ~10s) | **Nothing.** The panel came back up in the same wedged state. This is the counter-intuitive one: a one-byte serial command succeeded where cutting power entirely did not. |

## Third fix — rotation

The panel reports `angle: 180` and **does not apply it itself**. The vendor
app rotates its own render before encoding; the firmware just displays what
it is given. Sending an upright frame gets you an upside-down screen.
`show()` now rotates by `info.angle`, overridable via `screen.rotate`.

## Dead ends worth recording

- **`smartscreen.exe` is Windows Defender SmartScreen**, not a vendor
  process. The "background process that resists `taskkill /F` even as
  admin" was a name collision and never had anything to do with this panel.
  Port ownership was never actually contested after the tray app was closed.
- **Frame format was never the problem.** Native 960x480 draws fine. The
  vendor's 0.9 downscale (`rate = .9` when `w*h >= 230400`, so it sends
  864x432) makes no visible difference, and real frames run 25–34 KB against
  an 80 KB budget, so the size cap was never close to binding.
- **This is not an SPI panel.** `checkIsSPI()` matches only `"2.99"`,
  `"TXW813-ST7789-2.8inch"` or `"qspi"`; `5.99inch` does not match `2.99`.
  SPI models take raw RGB565 instead of JPEG — a completely different draw
  path we do not need.

## Protocol reference

Framing (`handleData` in the vendor source, matched byte-for-byte):

```
0x55 0xAA | lenLo lenHi | cmdKey | payload… | csLo csHi
len = len(payload) + 7        checksum = sum of all preceding bytes & 0xFFFF
```

Command keys: `1` restart · `3` brightness (payload `[0-100]`) · `6` device
info · `12` OTA header · `17` live/keep-alive · `21` motion timeout · `32`
set region · `33` close (firmware >= 3.1) · `35` set serial.

Connect: open (**DTR high**) → wait 500 ms → write raw `FF D9 FF D9` → wait
200 ms → send framed key=6 → parse reply.

Reply: `0x55 0xAA lenLo lenHi key <payload> csLo csHi`, payload is UTF-8
JSON in an envelope — `{"cmd":"info","data":{…}}`, fields one level down.
(The vendor's `.toString("hex")` / `Buffer.from(hex)` round trip looks like
double hex encoding but is a no-op.)

Drawing is a continuous JPEG stream, not a bitmap command: send key=17 once,
then write raw JPEG bytes straight to the port (no framing), and re-send
key=17 at least every 1.5 s or the session drops. The panel acks each ping
with `55 aa 08 00 11 00 18 01`.

Frame size cap, from `sendPic_getMaxSizeAndRate()`:

```js
s = model.includes("9.16");  a = model.includes("6.67");  r = max(w, h);
l = s ? (version > 2.8 ? 120 : 90) : (version > 2.8 ? 80 : 50);
if (a || r >= 1024) l = 260;
```

→ 80 KB for this panel.

## Files

| File | Purpose |
|---|---|
| `hongtai_screen.py` | The driver. Asserts DTR, unwraps the reply envelope, applies rotation, auto-restarts a wedged panel. |
| `test_connection.py` | Connect → print device info → set brightness → one test frame. |
| `demo_clock.py` | Starter template for live content — edit `render_frame()`. |
| `RUN_TEST.bat` | Runs the above, plus port/process/task diagnostics, logs to `test_output.log`. |
| `diag2_lines.py` / `RUN_DIAG2.bat` | The DTR/RTS sweep that cracked fault 1, kept as the recovery tool for a silent panel. Falls back to blind drawing if it stays silent. |
| `blind_draw.py` | Draws without ever needing a reply, walking candidate resolutions. For a panel whose info reply is unavailable. Invoked by `RUN_DIAG2.bat`. |

Removed after the fix, recoverable from commit `611885d` if ever needed:
`diag_probe.py` / `RUN_DIAG.bat` (superseded by the diag2 sweep, which
tests everything it did and more), `draw_lab.py` / `RUN_DRAWLAB.bat` (its
phase-0 restart is now `blind_restart()` in the driver), and
`KILL_ALL.bat` / `KILL_PID.bat` (built to chase the `smartscreen.exe` red
herring -- there was never a process holding the port).

## If it ever wedges again

1. Run `RUN_TEST.bat`. `connect()` now calls `blind_restart()` on its own
   when retries run out, so this may just fix itself.
2. If not, `python -c "from hongtai_screen import HongtaiScreen; HongtaiScreen('COM3').blind_restart()"`.
3. Only if the panel is silent rather than merely black, re-run
   `RUN_DIAG2.bat` to confirm the line states.

Do not reach for `pnputil`, `rtscts=True`, or the PSU switch. None of them
helped, and the first two actively cost time.

## Fourth fix — write-timeout crash during live streaming (28 Aug 2026, later)

`demo_clock.py` ran fine for a while, then crashed with
`serial.serialutil.SerialTimeoutException: Write timeout` from inside
`show()`, and the panel dropped back to idle. Root cause: **the
background keep-alive pinger thread (started by `start_live()`) and the
main thread's `show()` both wrote to the same `pyserial` handle with no
synchronization.** pyserial's Windows backend reuses a single OVERLAPPED
I/O structure per `Serial` object; two threads calling `write()`
concurrently can corrupt that shared state, and `GetOverlappedResult()`
then fails in a way pyserial reports as `SerialTimeoutException('Write
timeout')` -- even though no `write_timeout` was ever configured (it was
`None`/blocking by default). This is a data race, not an actual elapsed
timeout, which is why it only showed up intermittently after the panel
had already been drawing correctly for a while.

Fix: a `threading.Lock()` (`self._write_lock`) now wraps every
`self._ser.write()` + `.flush()` call site (`_send_and_wait`,
`_send_noreply`, `show()`), serializing the pinger thread against
whatever thread is pushing frames.

Also found and fixed in the same pass: **`connect()`'s auto-restart
fallback called `self.blind_restart()`, but that method did not exist
anywhere in `hongtai_screen.py`** -- despite being documented above as
the actual fix for a wedged panel and given a standalone usage example.
It's implemented now (opens the port itself with DTR/RTS asserted, sends
the flush marker + key=1 restart, closes -- no reply required, so it
works even when the panel answers nothing).
