@echo off
REM Fully automated -- no clicking needed. Spawns and kills a separate
REM UI process 4 times (alternating "kill just the PID" vs "kill the
REM whole process tree"), checking whether any msedgewebview2.exe
REM helper processes survive as orphans after each kill. Mirrors
REM output to process_split_output.log next to this script. Takes
REM under a minute.
cd /d "%~dp0"
REM Installs into whichever "python" this fresh window resolves to --
REM makes this runnable standalone regardless of what's installed
REM where, instead of depending on some earlier shell's state. Fast
REM no-op if already present.
python -m pip install --quiet --disable-pip-version-check pywebview psutil pillow
powershell -NoProfile -Command "python spike_process_split.py 4 2>&1 | Tee-Object -FilePath process_split_output.log"
echo.
echo Done. Output also saved to process_split_output.log
pause
