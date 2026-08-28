@echo off
cd /d "%~dp0"
set LOG=%~dp0drawlab_output.log
echo ==== draw lab %DATE% %TIME% ====> "%LOG%"
echo WATCH THE PANEL. This takes about 1 minute.
python -u draw_lab.py %1 >> "%LOG%" 2>&1
type "%LOG%"
echo.
echo DONE. Also saved to drawlab_output.log
pause
