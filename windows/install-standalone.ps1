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
Copy-Item (Join-Path $Root 'windows\check-for-updates.ps1') $AppDir -Force

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

try {
  $headers = @{ 'Accept' = 'application/vnd.github+json'; 'X-GitHub-Api-Version' = '2022-11-28' }
  $commit = Invoke-RestMethod -Uri 'https://api.github.com/repos/walterz930/c-ebot/commits/main' -Headers $headers -TimeoutSec 15
  Set-Content -Path (Join-Path $AppDir '.cebot_commit') -Value $commit.sha -Encoding ASCII
} catch {
  Write-Host "Could not record the GitHub commit; c-ebot can initialize update tracking on first /update." -ForegroundColor Yellow
}

$Launcher = Join-Path $AppDir 'start-c-ebot.ps1'
@'
$ErrorActionPreference = "Continue"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogPath = Join-Path $AppDir "logs\c-ebot.log"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LogPath) | Out-Null

Add-Content -Path $LogPath -Value ""
Add-Content -Path $LogPath -Value "=================================================="
Add-Content -Path $LogPath -Value "c-ebot starting $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Add-Content -Path $LogPath -Value "=================================================="

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " c-ebot - live activity console" -ForegroundColor Cyan
Write-Host " Logs: $LogPath" -ForegroundColor DarkGray
Write-Host " Checking GitHub for updates after startup..." -ForegroundColor DarkGray
Write-Host "==================================================" -ForegroundColor Cyan

Set-Location $AppDir
$checker = Join-Path $AppDir "check-for-updates.ps1"
if (Test-Path $checker) {
    Write-Host "[UPDATE] Starting GitHub update check..." -ForegroundColor DarkCyan
    Start-Process powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$checker) -WindowStyle Normal
} else {
    Write-Host "[UPDATE] Update checker not found: $checker" -ForegroundColor Yellow
}

$python = Join-Path $AppDir ".venv\Scripts\python.exe"
& $python -m uvicorn app.main:app --env-file ".env" --host 127.0.0.1 --port 8080 2>&1 | ForEach-Object {
    $line = $_ | Out-String
    Write-Host $line.TrimEnd()
    Add-Content -Path $LogPath -Value $line.TrimEnd()
}
$exitCode = $LASTEXITCODE

Add-Content -Path $LogPath -Value ""
Add-Content -Path $LogPath -Value "c-ebot stopped with exit code $exitCode at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "c-ebot stopped normally." -ForegroundColor Yellow
} else {
    Write-Host "c-ebot stopped because of an error (exit code $exitCode)." -ForegroundColor Red
    Write-Host "Full log: $LogPath" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Press Enter to close this window..." -ForegroundColor DarkGray
[void](Read-Host)
exit $exitCode
'@ | Set-Content $Launcher -Encoding UTF8

Start-Process powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$Launcher) -WindowStyle Normal

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
  Write-Host 'c-ebot is running. A live activity PowerShell window is open, and the dashboard will open in your browser.' -ForegroundColor Green
} else {
  Write-Host 'c-ebot did not start correctly.' -ForegroundColor Red
  Write-Host "Check the startup log: $LogDir\c-ebot.log" -ForegroundColor Yellow
  if (Test-Path (Join-Path $LogDir 'c-ebot.log')) {
    Write-Host '--- Last startup log ---' -ForegroundColor Yellow
    Get-Content (Join-Path $LogDir 'c-ebot.log') -Tail 80
  }
  exit 1
}
