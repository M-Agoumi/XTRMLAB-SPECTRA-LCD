@echo off
REM Fully automated -- opens one window, never destroys it, samples RAM
REM every 5s for 60s. Mirrors output to control_output.log next to this
REM script. Just let it finish.
cd /d "%~dp0"
powershell -NoProfile -Command "python spike_followup.py control 60 2>&1 | Tee-Object -FilePath control_output.log"
echo.
echo Done. Output also saved to control_output.log
pause
