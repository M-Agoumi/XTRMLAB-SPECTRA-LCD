# Privacy

Hongtai Screen (this repo) is a local Windows desktop app. It has no
account system, no sign-up, and no backend server operated by the
developer -- there's nobody to send your data to except the two
specific, opt-in cases below. This statement describes exactly what
the app does, based on reading its own source; it isn't legal advice.

## What stays on your machine

Everything the app needs to run day to day is stored and processed
locally, and never leaves your computer:

- **Settings** -- `%LOCALAPPDATA%\HongtaiScreen\app_config.json`.
- **Dashboard background images you upload** --
  `%LOCALAPPDATA%\HongtaiScreen\images\`.
- **Hardware stats** shown on the panel (CPU/GPU load, temperature,
  RAM, volume, network throughput) -- read directly from Windows and
  your hardware (via `psutil`, `pycaw`, `nvidia-ml-py`,
  `LibreHardwareMonitorLib`) and drawn straight to the panel. None of
  it is transmitted anywhere.
- **Now-playing / album art** -- read from the Windows Media Control
  API (whatever media session Windows itself is already tracking
  locally). The app doesn't connect to Spotify's or any other
  service's servers to get this.
- **The panel itself** -- driven over a local USB/serial connection
  only.

## The two things that do talk to the internet -- both opt-in

The app makes no network requests at all until you turn on one of
these two optional features:

- **Weather widget.** If you add this to the Dashboard and type in a
  location, the app sends that location string (and the resulting
  coordinates) to [Open-Meteo](https://open-meteo.com), a free,
  no-signup weather API, to fetch a forecast. That's the only data
  sent, and only while this widget is enabled and configured. See
  [Open-Meteo's own privacy policy](https://open-meteo.com/en/terms)
  for how they handle that request.
- **Webpage-mirror theme.** If you manually enable this theme and
  point it at a URL, the app loads that page in a headless browser and
  repeatedly screenshots it for the panel. Any data that page's
  session would normally send (cookies, etc.) is between your machine
  and whatever site you chose to point it at -- governed by that
  site's own privacy policy, not this app's.

## What this project does NOT do

- No analytics, telemetry, or crash reporting of any kind.
- No accounts, no login, no cloud sync.
- No ads, no trackers, no data sale or sharing with any third party.
- No automatic update checks or phone-home behavior.

## Downloading a release

Builds are distributed as [GitHub
Releases](https://github.com/M-Agoumi/XTRMLAB-SPECTRA-LCD/releases).
Downloading one is subject to [GitHub's own privacy
statement](https://docs.github.com/site-policy/privacy-policies/github-privacy-statement),
which is outside this project's control.

## Questions

Open an issue on the [GitHub
repo](https://github.com/M-Agoumi/XTRMLAB-SPECTRA-LCD/issues) for any
privacy question about this project.
