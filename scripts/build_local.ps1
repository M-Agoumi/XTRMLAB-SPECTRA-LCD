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
    [switch]$SkipPlaywright
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

Invoke-Checked -Description "Installing Python dependencies" -Command {
    python -m pip install -r requirements.txt
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
        Invoke-Checked -Description "Installing frontend dependencies" -Command { npm install }
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
