# Contributing

Thanks for helping out. This project drives the XTRM lab / Hongtai-family
LCD panel from a Python backend with a React UI. Bug reports, themes,
docs fixes and code are all welcome.

## Ways to help

- **Report a bug** or **request a feature** with the
  [issue forms](https://github.com/M-Agoumi/XTRMLAB-SPECTRA-LCD/issues/new/choose).
- **Test on your hardware.** Reports from panels, firmware versions or
  GPUs we haven't seen are very useful, even when everything works.
- **Pick up an issue** labelled `good first issue` or `help wanted`.
  Comment on it first so two people don't do the same work.
- **Security issues** go through [SECURITY.md](SECURITY.md), not public issues.

## Branches

| Branch | Purpose |
| --- | --- |
| `develop` | Integration branch. **All PRs target `develop`.** Every push publishes the `beta-latest` pre-release. |
| `main` | Released code. Only updated by a release PR from `develop` (or an urgent hotfix). |
| `v*` tags | A tag on `main` builds and publishes a production release. |

Neither `develop` nor `main` accepts direct pushes. Everything goes
through a pull request.

## Development setup

Windows is needed to run the app against a real panel. The test suite
and frontend build also run on Linux and macOS.

```bash
git clone https://github.com/<you>/XTRMLAB-SPECTRA-LCD.git
cd XTRMLAB-SPECTRA-LCD
git checkout develop
python -m venv .venv && .venv\Scripts\activate    # or source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Frontend (only if you change `frontend/src`):

```bash
cd frontend
npm ci
npm run dev      # live-reloading dev server
npm run build    # writes frontend/dist/, which is committed
```

`frontend/dist/` is committed so people can run the app without Node.
If you change `frontend/src`, run `npm run build` and commit the updated
`dist/` in the same PR.

See [BUILD.md](BUILD.md) for building the standalone exe and installer.

## Running the tests

```bash
PYTHONPATH=src pytest tests/ -q
```

The tests use a simulated screen, so no hardware is needed. CI runs the
same command on every PR, plus a frontend build.

## Making a pull request

1. Fork the repo and create a branch from `develop`:
   `git checkout -b fix/short-description develop`
2. Keep the change focused. One fix or feature per PR is much easier to
   review than several.
3. Add or update tests where it makes sense.
4. Add a line to `CHANGELOG.md` for anything users will notice.
5. Open the PR **against `develop`** and fill in the template.
6. CI (`test` and `frontend`) must pass and a code owner must approve
   before it can merge.

Branch name prefixes help: `fix/`, `feat/`, `docs/`, `theme/`, `ci/`.

## Code style

- Match the surrounding code. The codebase explains *why* in comments,
  especially where a real failure on hardware or CI drove a decision.
  Please keep doing that.
- Python 3.9+ compatible (see `pyproject.toml`).
- Optional hardware integrations (GPU vendors, sensors, Spotify) must
  degrade gracefully when the library or device is missing. A missing
  dependency should disable one widget, never crash the app.

## Protocol and driver changes

The panel protocol in `src/hongtai_screen_app/driver/` was
reverse-engineered and verified on real hardware. See
[FINDINGS.md](FINDINGS.md) before touching it, and say in your PR which
panel and firmware you tested on.

## Code of conduct

Everyone taking part is expected to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).
