@echo off
REM Fully automated -- no clicking needed. Runs 12 open/destroy cycles
REM back to back and mirrors the output to cycles_output.log next to
REM this script. Takes a couple minutes; just let it finish.
cd /d "%~dp0"
REM Installs into whichever "python" this fresh window resolves to --
REM makes this runnable standalone regardless of what's installed
REM where, instead of depending on some earlier shell's state. Fast
REM no-op if already present.
python -m pip install --quiet --disable-pip-version-check pywebview pystray psutil pillow
powershell -NoProfile -Command "python spike_followup.py cycles 12 2>&1 | Tee-Object -FilePath cycles_output.log"
echo.
echo Done. Output also saved to cycles_output.log
pause
