@echo off
REM Runs spike.py (the interactive one -- click "Minimize to tray" and
REM use the tray icon's Show/Quit yourself) and mirrors everything it
REM prints to spike_output.log next to this script, so you can just
REM send me that file instead of pasting console output.
cd /d "%~dp0"
powershell -NoProfile -Command "python spike.py 2>&1 | Tee-Object -FilePath spike_output.log"
echo.
echo Done. Output also saved to spike_output.log
pause
