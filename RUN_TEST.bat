@echo off
cd /d "%~dp0"
set PORT=%1
set LOG=%~dp0test_output.log
echo ==== hongtai screen test %DATE% %TIME% (port=%PORT% -- blank means auto-detect) ====> "%LOG%"
call :run >> "%LOG%" 2>&1
type "%LOG%"
echo.
echo ============================================
echo DONE. Output above was also saved to test_output.log
echo ============================================
pause
goto :eof

:run
echo.
echo ==== step 0: serial ports present ====
python list_screens.py
echo.
echo ==== step 0b: vendor processes / autostart state ====
tasklist /FI "IMAGENAME eq XTRM lab.exe"
tasklist /FO CSV | findstr /I "xtrm hongtai lcd screen"
schtasks /query /tn "\XTRM_lab" /v /fo LIST 2>&1 | findstr /I "TaskName Status Scheduled"
sc query state= all 2>&1 | findstr /I "XTRM hongtai"
echo.
echo ==== step 1: closing the vendor "XTRM lab" app ====
taskkill /F /IM "XTRM lab.exe" /T
timeout /t 1 >nul
echo.
echo ==== step 2: dependencies ====
pip install pyserial pillow
echo.
echo ==== step 3: running test_connection.py %PORT% ====
python -u test_connection.py %PORT%
echo.
echo ==== end of run ====
goto :eof
