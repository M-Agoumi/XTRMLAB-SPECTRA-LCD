# Building a standalone .exe

This is only needed if you want a double-clickable `Hongtai Screen.exe`
instead of running `python app.py`. Nobody needs to do this to just use
the app -- see the main **Quick start** in `README.md` for that.

This has to be done **on a Windows machine, by you** — a PyInstaller
build has to run on the same OS/architecture it targets, and bundles
whatever's actually `pip install`ed in the environment you build from.

## 1. Set up a clean build environment

Use a fresh virtual environment so the exe only bundles what this
project actually needs, not everything else you've ever installed:

```
python -m venv build_venv
build_venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
```

If you use `webpage_theme.py` (Playwright), also run
`playwright install chromium` in this environment first -- see the
Playwright note below, though, before assuming it belongs in the exe.

If you want CPU Temp, see "Hardware sensors (CPU Temp)" below before
building -- it's a manual, one-time file placement, not something
`pip install -r requirements.txt` can do for you.

## 2. Build the frontend

The exe bundles the React UI as static files, not as source -- build
it once (needs Node; this step doesn't need to happen in the Python
build_venv above):

```
cd frontend
npm install
npm run build      # writes frontend/dist/
cd ..
```

Skip this only if `frontend/dist/` is already present and up to date
(e.g. you haven't touched `frontend/src/` since the last build) --
`git status` will show it as unmodified in that case.

## 3. Build the exe

Run this from the **repo root** so the output lands in `dist\` right
there (PyInstaller's default output location is relative to wherever
`pyinstaller` is invoked from) — the spec's own input paths (`app.py`,
`assets\icon.ico`, `frontend\dist`, the `src` pathex) no longer
depend on this either way, they're anchored on the spec file's own
location, confirmed by a real CI run that hit the opposite assumption
(PyInstaller resolving `app.py` relative to the spec file's own
`packaging\` directory, not the invoking directory, even though this
doc used to claim it worked the other way round):

```
pyinstaller packaging\hongtai_screen.spec
```

This reads `packaging\hongtai_screen.spec` (already in this repo, see
there for what it does and why) and produces `dist\Hongtai Screen.exe`
— a single, no-console, icon-bearing executable that bundles both
halves of the app (backend/tray and the webview window -- see
`app.py`'s own docstring for the `--ui` dispatch that makes one exe
cover both).

## 4. Test it

Run `dist\Hongtai Screen.exe` directly. Things worth specifically
checking, since none of this was testable from here (a Linux sandbox
built the spec, but never ran the actual .exe):

- **Settings live in `%LOCALAPPDATA%\HongtaiScreen\app_config.json`,
  not next to the exe.** That's the same per-user folder uploaded
  Dashboard images already live in (`...\HongtaiScreen\images\`) —
  moving or reinstalling the exe doesn't reset your settings, and you
  don't need to pick a final install location before configuring
  anything the way earlier builds required.
- **The window icon and taskbar icon** both show the app icon, not a
  generic one.
- **Panel connection, all four theme tabs, Start/Stop/Apply.**
- **"Launch at Windows startup"** — tick it, reboot (or log off/on),
  confirm it comes back with no console window and resumes the theme
  you last had running. This path was rewritten for the frozen build
  (the exe now points the Startup shortcut at itself, not at a
  `pythonw.exe` + script pair) — it's exercised the least by anything
  testable outside real Windows, so double-check it works.
- **The system tray icon** (needs `pystray`, already in
  `requirements.txt`) — closing the window should dismiss to tray, not
  quit, and clicking "Show" should spawn the window process again
  (`--ui`, see `app.py`'s docstring) rather than trying to run
  `run_ui.py` as a separate script, which won't exist next to a frozen
  build.
- **The webview window itself** — if WebView2 isn't present on the
  build/test machine, `ui_window.py` should show a clear message box
  with a download link, not a silent failure or a raw traceback.
- **The Dashboard tab's background image picker and web mirror.**
- Windows Defender / SmartScreen may flag a brand-new, unsigned exe on
  first run ("Windows protected your PC") — this is normal for any
  unsigned indie tool, not a sign something's wrong. "More info" →
  "Run anyway" gets past it, and telling people that up front in your
  release notes saves them a scare.
- **Smart App Control is a separate, harsher wall than SmartScreen --
  confirmed by a real report: "Smart App Control blocked a file that
  may be unsafe", with no "Run anyway"/"More info" escape hatch at
  all.** SmartScreen still lets you click through an unsigned exe;
  Smart App Control (Windows 11 22H2+, auto-enabled on a *clean*
  install after an evaluation period, off by default on an
  upgrade-from-older-Windows install) just refuses outright.
  - Testing on your own machine: `Settings -> Privacy & security ->
    Windows Security -> App & browser control -> Smart App Control` --
    if it's On, you can switch it Off, but **Microsoft's own docs say
    this is one-way**: once you turn it off, the only way back on is a
    clean reinstall of Windows. Don't do this on a daily-driver machine
    just to test one exe. Test inside a disposable **Windows Sandbox**
    or VM instead (see the "how would it react on a brand new PC"
    testing notes elsewhere in this repo) -- toggling Smart App Control
    off in there costs you nothing since the whole environment gets
    thrown away anyway.
  - For real end users: this isn't just a scarier dialog than
    SmartScreen, it's a **hard block with no override** for anyone who
    has it on -- which, since it's the default outcome of Windows 11's
    out-of-box evaluation on a clean install, is exactly the "brand new
    PC, brand new user" case this app is meant to run on. Code-signing
    is the actual fix, since Smart App Control's evaluation leans on
    the exe's reputation/signature.

    CI now signs every beta/prod build via
    [SignPath.io](https://signpath.io) (see `.github/workflows/build.yml`'s
    "Sign the exe (SignPath)" step) -- but currently under SignPath's
    **"CI Beta Signing" policy, which is backed by a self-signed TEST
    certificate**, not a real CA-trusted one. That's enough to prove the
    CI -> SignPath pipeline works end to end, but it does **not** get
    SmartScreen or Smart App Control to actually trust the exe for
    anyone else -- a self-signed cert has no chain to a root Windows
    already trusts, no matter how many builds get signed with it.

    The real fix is [SignPath Foundation](https://signpath.org)'s free
    OSS certificate program (a separate thing from the signpath.io
    trial above -- see that page for the distinction), which issues an
    actual CA-trusted cert once a project qualifies. Applying needs a
    public-facing project presence (a real project website, some
    search visibility) that this project doesn't have yet -- until
    that's ready, testers can trust the current self-signed test cert
    **on their own machine only**, which is enough to develop/test
    signed builds without SmartScreen/Smart App Control getting in the
    way:

    ```powershell
    # Run as Administrator. Point $exePath at whatever signed build
    # you're testing -- the release download, or a local dist\ build.
    $exePath = "C:\path\to\Hongtai Screen.exe"

    # Pull the signing certificate straight out of the exe
    $cert = (Get-AuthenticodeSignature $exePath).SignerCertificate
    $certPath = "$env:TEMP\hongtai-screen-test.cer"
    Export-Certificate -Cert $cert -FilePath $certPath

    # 1) Trust it as a root -- required because it's self-signed (no
    #    real CA chain)
    Import-Certificate -FilePath $certPath -CertStoreLocation Cert:\LocalMachine\Root

    # 2) Also add it as a Trusted Publisher -- this is what actually
    #    suppresses the SmartScreen "Windows protected your PC" prompt
    #    for this signer
    Import-Certificate -FilePath $certPath -CertStoreLocation Cert:\LocalMachine\TrustedPublisher
    ```

    This only trusts the cert on the machine it's run on -- it changes
    nothing for anyone who downloads a beta build without doing this
    themselves, which is exactly the point: it's a local dev/test
    convenience, not a substitute for the real Foundation cert. If
    SignPath's beta policy ever reissues a new self-signed cert, a
    build signed under the new cert will need this re-run against the
    new exe. Smart App Control isn't guaranteed to honor this the same
    documented way SmartScreen does -- verify by actually launching the
    exe with Smart App Control on, rather than assuming it's cleared.

## Hardware sensors (CPU Temp)

CPU Temp reads via [LibreHardwareMonitorLib](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor)
(MIT-licensed, open source) instead of any vendor-supplied binary --
see `dashboard_theme.py`'s `_lhm_cpu_temp()` docstring for the full
reasoning. Setting it up is two manual steps, deliberately not
automated by `pip install` or this build:

1. `pip install pythonnet` (already in `requirements.txt`, so this is
   covered by step 1 above if you installed the full file).
2. Download a release from LibreHardwareMonitor's own
   [GitHub Releases page](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases).
   Recent releases ship two zips -- get the plain **`LibreHardwareMonitor.zip`**
   (the classic .NET Framework build pythonnet actually loads), **not**
   `LibreHardwareMonitor.NET.10.zip` (a modern-.NET-only build whose
   dependency DLLs pythonnet's default runtime can't load -- confirmed
   by a real report: the library itself loaded, but
   `ReflectionTypeLoadException`/`ModuleNotFoundError` followed as soon
   as anything touched its types). Older releases labeled this same
   zip `LibreHardwareMonitor-net472.zip` instead -- same idea, whichever
   name this repo's own release uses, it's the one *without* a .NET
   version number in its name. Extract **every `.dll` in it** -- not
   just `LibreHardwareMonitorLib.dll` -- into:

   ```
   assets\hardware\
   ```

   in this repo (source run: `python app.py` finds it there directly;
   frozen build: `hongtai_screen.spec`'s `datas` bundles that same
   folder into the exe, wildcard-matching every `.dll` in it, the same
   way it already bundles `assets\icon.ico` and the backgrounds/fonts
   -- build the exe *after* placing the DLLs, not before).

   `LibreHardwareMonitorLib.dll` isn't standalone -- it depends on
   other DLLs from the same zip (`HidSharp.dll` in particular, used
   for its USB/HID sensor support) that it loads at runtime. Copying
   only the one file loads fine on the surface (`clr.AddReference()`
   raises nothing) but fails as soon as anything actually enumerates
   its types, with a `ReflectionTypeLoadException` -- which pythonnet's
   own `from LibreHardwareMonitor.Hardware import Computer` surfaces as
   a plain `ModuleNotFoundError`, giving no hint that a dependency,
   not the DLL itself, is what's missing. Copying the whole zip's
   `.dll` files avoids chasing that one down again; the extras (its
   own GUI's `Aga.Controls.dll`/`OxyPlot.dll`, unused here) are
   harmless to have sitting alongside it.

   **Unblock the file after placing it.** Windows tags anything
   downloaded from the internet -- including a file pulled out of a
   downloaded zip -- with a "Mark of the Web" flag, and pythonnet's
   .NET Framework runtime refuses to load a DLL carrying that flag
   from a local path (it treats it like loading from a network share).
   The symptom is a `FileLoadException` /
   `System.NotSupportedException` mentioning `loadFromRemoteSources` in
   the app's log, not a missing-file error, which makes it look like
   something's wrong with the DLL itself rather than a file attribute.
   Clear it with:

   ```
   Unblock-File assets\hardware\LibreHardwareMonitorLib.dll
   ```

   or right-click the file → Properties → General tab → check
   "Unblock" → OK.

Getting the DLL straight from its own maintainers rather than this repo
fetching or bundling a copy of it is the point, not an inconvenience --
that's exactly the trust boundary this replaced the vendor helper to
get. Skip this entirely and CPU Temp just reads "--", same as any
other optional stat with a missing dependency.

Either way (source or frozen), CPU Temp additionally needs
Administrator to actually load LibreHardwareMonitorLib's own sensor
driver -- a Windows platform limitation, not something this app or
that library can work around. The web UI's System section shows a
one-click "Restart as Administrator" for exactly this once pythonnet
and the DLL are both in place.

## Notes on what's bundled

- **`pystray`, `nvidia-ml-py` (pynvml), `winsdk`** are optional at
  runtime already (the app degrades gracefully without them) — but
  PyInstaller needs them actually installed in the build environment
  to bundle them at all. Install the full `requirements.txt` before
  building if you want every feature available in the exe, even ones
  you personally don't use.
- **Playwright is unusual for packaging**: it needs its own downloaded
  Chromium binary (`playwright install chromium`, ~150MB) at runtime,
  separately from the Python package. PyInstaller does *not* bundle
  that browser download automatically. If you don't use
  `webpage_theme.py`, it's simplest to leave `playwright` out of the
  build environment entirely (the tab just reports the theme
  unavailable, same as any other missing optional dependency) rather
  than trying to bundle a whole browser into the exe.
- **`pythonnet`** (CPU Temp) needs the .NET runtime PyInstaller's
  analyzer can't always fully trace through `clr`'s dynamic assembly
  loading -- if the exe's CPU Temp doesn't work even though
  `python app.py` from source does, see "If something doesn't work in
  the exe" below and check the console for a `clr`/`Python.Runtime`
  import error specifically.
- **`opencv-python-headless`** is a large dependency (`video_theme.py`)
  — expect the exe to be a few hundred MB once numpy/opencv/pycairo are
  all in it. That's normal for a bundled Python + native-library app,
  not a packaging mistake.
- The spec disables UPX compression on purpose — UPX-packed opencv/
  webview builds are a common source of Windows Defender false
  positives, and the size savings aren't worth that headache for a
  release build.

## If something doesn't work in the exe but works with `python app.py`

That's almost always a packaging gap (a missing hidden import, a data
file PyInstaller didn't pick up, or a `__file__`-relative path that
assumed running from source) rather than an app bug — the exe runs the
exact same code. Run the exe from a **console** first
(`dist\Hongtai Screen.exe` from `cmd.exe`, not double-clicked) so any
traceback is visible rather than silently swallowed, the same lesson
that's already bitten this project once with windowless launches — see
the Log panel and console output for the actual error, then report
back with that text.
