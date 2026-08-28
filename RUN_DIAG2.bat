@echo off
cd /d "%~dp0"
set LOG=%~dp0diag2_output.log
echo ==== hongtai diag2 %DATE% %TIME% ====> "%LOG%"
call :body >> "%LOG%" 2>&1
type "%LOG%"
echo.
echo DONE. Also saved to diag2_output.log
pause
goto :eof

:body
echo ==== vendor app's remembered device config (has the panel's real resolution) ====
if exist "%APPDATA%\XTRM lab\config.json" (
  type "%APPDATA%\XTRM lab\config.json"
) else (
  echo   not found at "%APPDATA%\XTRM lab\config.json"
  dir /b /s "%APPDATA%\*config.json" 2>nul | findstr /I "XTRM"
)
echo.
echo ==== part 1: DTR/RTS sweep ====
python -u diag2_lines.py %1
if errorlevel 2 (
  echo.
  echo ==== part 2: panel stayed silent, trying to DRAW blind anyway ====
  echo ==== WATCH THE SCREEN for the next ~60 seconds ====
  python -u blind_draw.py %1
) else (
  echo.
  echo ==== panel answered -- skipping the blind-draw test ====
)
goto :eof
