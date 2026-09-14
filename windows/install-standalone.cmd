@echo off
setlocal
rem PowerShell execution policies can block .ps1 files on Windows clients.
rem Run the installer through a one-time Bypass policy so users do not need
rem to change their system or user execution policy just to install c-ebot.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-standalone.ps1" %*
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" (
  echo.
  echo c-ebot installer failed with exit code %EXITCODE%.
  pause
)
exit /b %EXITCODE%
