@echo off
REM Fully automated -- opens one window, never destroys it, samples RAM
REM every 5s for 60s. Mirrors output to control_output.log next to this
REM script. Just let it finish.
cd /d "%~dp0"
REM Installs into whichever "python" this fresh window resolves to --
REM makes this runnable standalone regardless of what's installed
REM where, instead of depending on some earlier shell's state. Fast
REM no-op if already present.
python -m pip install --quiet --disable-pip-version-check pywebview pystray psutil pillow
powershell -NoProfile -Command "python spike_followup.py control 60 2>&1 | Tee-Object -FilePath control_output.log"
echo.
echo Done. Output also saved to control_output.log
pause
