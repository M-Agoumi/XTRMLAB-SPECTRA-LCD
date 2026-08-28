@echo off
cd /d "%~dp0"
set LOG=%~dp0diag_output.log
echo ==== hongtai diag %DATE% %TIME% ====> "%LOG%"
python -u diag_probe.py %1 >> "%LOG%" 2>&1
type "%LOG%"
echo.
echo DONE. Output also saved to diag_output.log
pause
