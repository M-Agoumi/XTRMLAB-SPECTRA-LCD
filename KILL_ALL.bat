@echo off
echo Killing any python.exe processes...
taskkill /F /IM python.exe
echo.
echo Remaining python processes (should be empty):
tasklist /FI "IMAGENAME eq python.exe"
pause
