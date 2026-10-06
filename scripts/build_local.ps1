<#
.SYNOPSIS
    Builds "Hongtai Screen.exe" locally, on this machine -- see BUILD.md
    for the full manual walkthrough this script automates.

.DESCRIPTION
    Windows only, and has to run on Windows for real (a Linux/macOS
    PyInstaller run produces a binary for THAT OS, not a Windows exe).
    Installs Python + frontend dependencies, builds the React frontend,
    then runs PyInstaller against packaging\hongtai_screen.spec.

    The result is UNSIGNED -- this script does none of CI's SignPath
    step. SmartScreen will flag it on first run ("Windows protected
    your PC" -> More info -> Run anyway); Smart App Control may hard-
    block it outright with no override, same as any unsigned exe -- see
    BUILD.md's Smart App Control section for what does and doesn't work
    around that locally.

.PARAMETER SkipFrontend
    Skip `npm install`/`npm run build` -- use this if frontend\dist is
    already built and up to date (e.g. you haven't touched
    frontend\src since the last build).

.PARAMETER SkipPlaywright
    Skip `playwright install chromium` (~150MB download). Only needed
    if you actually use webpage_theme.py; harmless to skip otherwise.

.PARAMETER SkipInstaller
    Skip building HongtaiScreen-Setup.exe (packaging\hongtai_screen.iss)
    after the portable exe. On by default when Inno Setup (ISCC.exe)
    isn't installed -- it's a genuinely optional step for a local dev
    build, only needed when you actually want the installer (e.g. for a
    Store submission's silent-install requirement -- see that script's
    own header comment for why the portable exe alone can't satisfy
    that). Pass this switch to skip it even when ISCC.exe IS found.

.EXAMPLE
    .\scripts\build_local.ps1
    Full build: Python deps, Playwright's Chromium, frontend, then the exe.

.EXAMPLE
    .\scripts\build_local.ps1 -SkipFrontend -SkipPlaywright
    Fastest rebuild -- just the exe, reusing an already-built frontend
    and skipping the Chromium download.
#>
[CmdletBinding()]
param(
    [switch]$SkipFrontend,
    [switch]$SkipPlaywright,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    Write-Error "This has to run on Windows -- see this script's own .SYNOPSIS for why."
    exit 1
}

# Anchor on the repo root regardless of where this script was invoked
# from, same reasoning as packaging\hongtai_screen.spec's own
# REPO_ROOT (a real CI run once hit PyInstaller resolving a path
# relative to the invoking directory instead of the repo root --
# resolving explicitly here avoids relying on that assumption at all).
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# Helper: native commands (pip, npm, pyinstaller, playwright) don't
# throw a terminating error on a non-zero exit code the way a cmdlet
# does -- $ErrorActionPreference = "Stop" alone does NOT catch that,
# so every external command's $LASTEXITCODE is checked explicitly.
# Without this, a failed `npm ci` could silently let the rest of the
# script carry on and package a broken/stale build, exactly the
# "still showed green" trap build.yml's own comments already document
# for this same class of mistake in CI.
function Invoke-Checked {
    param([Parameter(Mandatory)][ScriptBlock]$Command, [Parameter(Mandatory)][string]$Description)
    Write-Host "==> $Description" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        Write-Error "$Description failed (exit code $LASTEXITCODE)"
        exit $LASTEXITCODE
    }
}

# Not a plain Invoke-Checked step -- pip installing winsdk (an
# optional, unpinned-upper-bound dependency; see requirements.txt's
# own comment on why it can't be pinned tighter) can fall through to
# building winsdk's sdist from source when the resolved pre-release
# has no prebuilt wheel for this interpreter's Python version
# (confirmed for real: winsdk 1.0.0b10, its newest release, only
# ships wheels for Python 3.8-3.12 -- github.com/pywinrt/python-winsdk's
# own release notes). That source build needs the MSVC toolchain
# (nmake), and scikit-build's own failure for a missing one is a wall
# of "Trying 'NMake Makefiles ...' generator - failure" noise that
# doesn't say what to actually do about it -- confirmed by a real
# report that read as a crash rather than a clear, actionable error.
# Caught here and translated into one specific fix instead.
Write-Host "==> Installing Python dependencies" -ForegroundColor Cyan
$pipOutputLines = $null
try {
    python -m pip install -r requirements.txt 2>&1 | Tee-Object -Variable pipOutputLines | Out-Host
} catch {
    # PowerShell 7.3+'s $PSNativeCommandUseErrorActionPreference can
    # turn pip's own non-zero exit into a terminating error here under
    # $ErrorActionPreference = "Stop" -- same gotcha as this script's
    # taskkill call above. $LASTEXITCODE is checked below regardless
    # of whether that happened, so this catch only needs to exist to
    # keep the script from stopping before that check runs.
}
if ($LASTEXITCODE -ne 0) {
    $combined = ($pipOutputLines | Out-String)
    if ($combined -match "winsdk" -and $combined -match "nmake|NMake Makefiles|CMake Error") {
        Write-Error @"
Installing Python dependencies failed building winsdk from source -- it needs the MSVC/nmake toolchain, which isn't installed (or isn't on PATH in this session).

Fix: install the "Desktop development with C++" workload, as Administrator:
  winget install --id Microsoft.VisualStudio.2022.BuildTools --override "--quiet --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --wait"

Then close and reopen this PowerShell window (nmake/cl.exe only land on PATH in a fresh session) and re-run this script.
"@
    } else {
        Write-Error "Installing Python dependencies failed (exit code $LASTEXITCODE)"
    }
    exit 1
}
Invoke-Checked -Description "Installing PyInstaller" -Command {
    python -m pip install pyinstaller
}

if (-not $SkipPlaywright) {
    Invoke-Checked -Description "Installing Playwright's Chromium (webpage-mirror theme)" -Command {
        python -m playwright install chromium
    }
} else {
    Write-Host "==> Skipping Playwright Chromium install (-SkipPlaywright)" -ForegroundColor Yellow
}

if (-not $SkipFrontend) {
    Push-Location (Join-Path $RepoRoot "frontend")
    try {
        # `npm ci` (not `npm install`) into a node_modules removed first,
        # not reused: vite 8's bundler (rolldown) ships its native binary
        # as a per-OS/arch optionalDependency (e.g.
        # @rolldown/binding-win32-x64-msvc), and npm has a long-standing
        # bug (npm/cli#4828) where an `npm install` against an existing
        # node_modules can silently skip installing a *newly added*
        # optional dependency -- exactly what happened when the vite
        # 5.4.21 -> 8.3.0 bump (Dependabot #5) first pulled rolldown in.
        # The failure only shows up later, at `vite build` time: "Cannot
        # find native binding ... Cannot find module
        # '@rolldown/binding-win32-x64-msvc'". Wiping node_modules first
        # removes any chance of that stale-tree skip; `npm ci` (rather
        # than `npm install`) then does a from-scratch install strictly
        # from package-lock.json, which is what actually verified-fixes
        # this bug rather than just usually avoiding it.
        $nodeModules = Join-Path (Get-Location) "node_modules"
        if (Test-Path $nodeModules) {
            Invoke-Checked -Description "Removing stale frontend node_modules (npm/cli#4828 workaround)" -Command {
                Remove-Item -Recurse -Force $nodeModules
            }
        }
        Invoke-Checked -Description "Installing frontend dependencies" -Command { npm ci }
        Invoke-Checked -Description "Building frontend" -Command { npm run build }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "==> Skipping frontend build (-SkipFrontend) -- reusing frontend\dist as-is" -ForegroundColor Yellow
    if (-not (Test-Path (Join-Path $RepoRoot "frontend\dist\index.html"))) {
        Write-Warning "frontend\dist\index.html doesn't exist -- the exe will fall back to the plain-HTML placeholder page instead of the real UI. Re-run without -SkipFrontend."
    }
}

# PyInstaller deletes dist\Hongtai Screen.exe before writing the new one
# -- if a previous build/test run of the app is still open (tray icon,
# or a spawned --ui webview window, see app.py's own docstring on that
# dispatch), Windows won't let it, and the build fails with
# "PermissionError: [WinError 5] Access is denied" on that os.remove()
# call, deep inside PyInstaller's own EXE.assemble() -- confirmed by a
# real run. taskkill's exit code is ignored: "no such process" (nothing
# was running) is just as fine an outcome here as "killed it" -- same
# reasoning as hongtai_screen.iss's own CloseRunningApp, which has this
# exact problem at install/uninstall time instead of build time.
#
# Wrapped in try/catch, not just `2>$null | Out-Null`: on PowerShell
# 7.3+, $PSNativeCommandUseErrorActionPreference defaults to $true,
# which makes $ErrorActionPreference = "Stop" (set above) turn
# taskkill's non-zero "process not found" exit code into a terminating
# NativeCommandError -- confirmed by a real run, even with stderr
# already redirected to $null (that redirection silences the message,
# not the exit code the Stop preference reacts to). try/catch swallows
# it regardless of which PowerShell version/preference is in play,
# unlike relying on the exit code being ignored.
try {
    taskkill /IM "Hongtai Screen.exe" /F /T 2>$null | Out-Null
} catch {
    # No matching process -- nothing was running, nothing to do here.
}

Invoke-Checked -Description "Building the exe with PyInstaller" -Command {
    pyinstaller (Join-Path $RepoRoot "packaging\hongtai_screen.spec")
}

$exePath = Join-Path $RepoRoot "dist\Hongtai Screen.exe"
if (Test-Path $exePath) {
    Write-Host ""
    Write-Host "Build succeeded: $exePath" -ForegroundColor Green
    Write-Host "This build is UNSIGNED -- SmartScreen will flag it on first run (More info -> Run anyway)." -ForegroundColor Yellow
    Write-Host "See BUILD.md for testing notes, incl. the HONGTAI_SCREEN_DEBUG=1 DevTools trick if the window renders blank." -ForegroundColor Yellow
} else {
    Write-Error "PyInstaller reported success but $exePath wasn't found -- something's off."
    exit 1
}

if (-not $SkipInstaller) {
    # ISCC.exe isn't installed by default the way Python/npm are already
    # assumed to be above -- unlike those, silently requiring it would
    # break every existing local build for anyone who doesn't have Inno
    # Setup, for a step most local dev builds don't actually need (see
    # hongtai_screen.iss's own header comment: it's only the Store/
    # silent-install path that needs a real installer over the portable
    # exe). So this looks for it and just skips with a clear pointer to
    # -SkipInstaller / the download page, rather than failing the whole
    # build the way a genuinely required tool being missing would.
    $iscc = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if (-not $iscc) {
        $fallback = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
        if (Test-Path $fallback) { $iscc = $fallback } else { $iscc = $null }
    } else {
        $iscc = $iscc.Source
    }

    if ($iscc) {
        # AppVersion isn't wired to a single source of truth in this repo
        # yet (see pyproject.toml's own version field vs. CHANGELOG.md) --
        # "0.0.0-local" (hongtai_screen.iss's own default) is fine for a
        # local test build; build.yml passes the real released version
        # explicitly for anything actually published.
        Invoke-Checked -Description "Building the installer (HongtaiScreen-Setup.exe)" -Command {
            & $iscc (Join-Path $RepoRoot "packaging\hongtai_screen.iss")
        }
        $installerPath = Join-Path $RepoRoot "dist\HongtaiScreen-Setup.exe"
        if (Test-Path $installerPath) {
            Write-Host "Installer built: $installerPath" -ForegroundColor Green
        } else {
            Write-Error "ISCC reported success but $installerPath wasn't found -- something's off."
            exit 1
        }
    } else {
        Write-Host ""
        Write-Host "==> Skipping installer build -- Inno Setup (ISCC.exe) not found." -ForegroundColor Yellow
        Write-Host "    Install it from https://jrsoftware.org/isinfo.php if you need HongtaiScreen-Setup.exe," -ForegroundColor Yellow
        Write-Host "    or pass -SkipInstaller to silence this notice." -ForegroundColor Yellow
    }
} else {
    Write-Host "==> Skipping installer build (-SkipInstaller)" -ForegroundColor Yellow
}
