$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$AppDir = Join-Path $Root 'windows\standalone'
$Venv = Join-Path $AppDir '.venv'
$LogDir = Join-Path $AppDir 'logs'

Write-Host 'c-ebot Windows Standalone Installer' -ForegroundColor Cyan
Write-Host 'This mode does NOT require Docker, WSL, or CPU virtualization.'

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Host 'Python 3 is required. Please install Python 3.12+ from python.org and enable Add Python to PATH.' -ForegroundColor Yellow
  exit 1
}

New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
Copy-Item (Join-Path $Root 'app') $AppDir -Recurse -Force
Copy-Item (Join-Path $Root 'requirements.txt') $AppDir -Force
Copy-Item (Join-Path $Root 'windows\update-standalone.ps1') $AppDir -Force

python -m venv $Venv
& (Join-Path $Venv 'Scripts\python.exe') -m pip install --upgrade pip
& (Join-Path $Venv 'Scripts\python.exe') -m pip install -r (Join-Path $AppDir 'requirements.txt')

if (-not (Test-Path (Join-Path $AppDir '.env'))) {
  $secret = (& (Join-Path $Venv 'Scripts\python.exe') -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())").Trim()
  $DataDir = Join-Path $AppDir 'data'
  @"
APP_SECRET=$secret
DATA_DIR=$($DataDir.Replace('\\','/'))
DATABASE_URL=sqlite:///$($DataDir.Replace('\\','/'))/c-ebot.db
BASE_URL=http://localhost:8080
SYNC_INTERVAL_SECONDS=30
DISCORD_BOT_TOKEN=
"@ | Set-Content (Join-Path $AppDir '.env') -Encoding UTF8
}
New-Item -ItemType Directory -Force -Path (Join-Path $AppDir 'data') | Out-Null
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# Record the exact GitHub commit installed so /update can safely detect newer code.
try {
  $headers = @{ 'Accept' = 'application/vnd.github+json'; 'X-GitHub-Api-Version' = '2026-03-10' }
  $commit = Invoke-RestMethod -Uri 'https://api.github.com/repos/walterz930/c-ebot/commits/main' -Headers $headers -TimeoutSec 15
  Set-Content -Path (Join-Path $AppDir '.cebot_commit') -Value $commit.sha -Encoding ASCII
} catch {
  Write-Host "Could not record the GitHub commit; c-ebot can initialize update tracking on first /update." -ForegroundColor Yellow
}

$Launcher = Join-Path $AppDir 'start-c-ebot.cmd'
@"
@echo off
setlocal
cd /d "%~dp0"
if not exist "logs" mkdir "logs"
echo. >> "logs\c-ebot.log"
echo ================================================== >> "logs\c-ebot.log"
echo c-ebot starting %date% %time% >> "logs\c-ebot.log"
echo ================================================== >> "logs\c-ebot.log"
call ".venv\Scripts\activate.bat"
python -m uvicorn app.main:app --env-file ".env" --host 127.0.0.1 --port 8080 >> "logs\c-ebot.log" 2>&1
set "EXITCODE=%ERRORLEVEL%"
echo. >> "logs\c-ebot.log"
echo c-ebot stopped with exit code %EXITCODE% at %date% %time% >> "logs\c-ebot.log"
if not "%EXITCODE%"=="0" (
  echo.
  echo c-ebot stopped because of an error.
  echo The full error is in:
  echo %~dp0logs\c-ebot.log
  echo.
  type "logs\c-ebot.log"
  echo.
  pause
)
exit /b %EXITCODE%
"@ | Set-Content $Launcher -Encoding ASCII

Start-Process $Launcher

$Ready = $false
for ($i = 0; $i -lt 20; $i++) {
  Start-Sleep -Milliseconds 500
  try {
    $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8080/health' -UseBasicParsing -TimeoutSec 1
    if ($response.StatusCode -eq 200) { $Ready = $true; break }
  } catch { }
}

if ($Ready) {
  Start-Process 'http://localhost:8080'
  Write-Host 'c-ebot is running. The dashboard will open in your browser.' -ForegroundColor Green
} else {
  Write-Host 'c-ebot did not start correctly.' -ForegroundColor Red
  Write-Host "Check the startup log: $LogDir\c-ebot.log" -ForegroundColor Yellow
  if (Test-Path (Join-Path $LogDir 'c-ebot.log')) {
    Write-Host '--- Last startup log ---' -ForegroundColor Yellow
    Get-Content (Join-Path $LogDir 'c-ebot.log') -Tail 80
  }
  exit 1
}
