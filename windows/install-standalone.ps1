$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$AppDir = Join-Path $Root 'windows\standalone'
$Venv = Join-Path $AppDir '.venv'

Write-Host 'c-ebot Windows Standalone Installer' -ForegroundColor Cyan
Write-Host 'This mode does NOT require Docker, WSL, or CPU virtualization.'

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Host 'Python 3 is required. Please install Python 3.12+ from python.org and enable Add Python to PATH.' -ForegroundColor Yellow
  exit 1
}

New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
Copy-Item (Join-Path $Root 'app') $AppDir -Recurse -Force
Copy-Item (Join-Path $Root 'requirements.txt') $AppDir -Force

python -m venv $Venv
& (Join-Path $Venv 'Scripts\python.exe') -m pip install --upgrade pip
& (Join-Path $Venv 'Scripts\python.exe') -m pip install -r (Join-Path $AppDir 'requirements.txt')

if (-not (Test-Path (Join-Path $AppDir '.env'))) {
  # Generate a real Fernet key after cryptography has been installed.
  $secret = (& (Join-Path $Venv 'Scripts\python.exe') -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())").Trim()
  $DataDir = Join-Path $AppDir 'data'
  @"
APP_SECRET=$secret
DATA_DIR=$($DataDir.Replace('\','/'))
DATABASE_URL=sqlite:///$($DataDir.Replace('\','/'))/c-ebot.db
BASE_URL=http://localhost:8080
SYNC_INTERVAL_SECONDS=30
DISCORD_BOT_TOKEN=
"@ | Set-Content (Join-Path $AppDir '.env') -Encoding UTF8
}
New-Item -ItemType Directory -Force -Path (Join-Path $AppDir 'data') | Out-Null

$Launcher = Join-Path $AppDir 'start-c-ebot.cmd'
@"
@echo off
cd /d "%~dp0"
call ".venv\Scripts\activate.bat"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
"@ | Set-Content $Launcher -Encoding ASCII

Start-Process $Launcher
Start-Sleep -Seconds 3
Start-Process 'http://localhost:8080'
Write-Host 'c-ebot is starting. The dashboard will open in your browser.' -ForegroundColor Green
