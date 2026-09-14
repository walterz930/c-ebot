@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo            c-ebot launcher
echo ========================================
echo.

if exist "windows\standalone\start-c-ebot.cmd" (
  echo Starting c-ebot...
  start "c-ebot" /wait "windows\standalone\start-c-ebot.cmd"
  exit /b %errorlevel%
)

echo First run: installing c-ebot for Windows...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\install-standalone.ps1"
exit /b %errorlevel%
