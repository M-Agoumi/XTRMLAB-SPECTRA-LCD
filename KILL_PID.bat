@echo off
echo Force-killing PID 22140 directly...
taskkill /F /PID 22140
echo.
echo Also sweeping any other python.exe just in case:
taskkill /F /IM python.exe
echo.
echo Remaining python processes (should be empty):
tasklist /FI "IMAGENAME eq python.exe"
echo.
echo Remaining conhost/cmd windows from old test runs:
tasklist /FI "WINDOWTITLE eq C:\WINDOWS\system32\cmd.exe"
pause
