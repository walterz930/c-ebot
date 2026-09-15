param(
  [Parameter(Mandatory=$true)][string]$TargetSha,
  [Parameter(Mandatory=$true)][int]$ParentPid
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$AppDir = Join-Path $Root 'standalone'
$TempDir = Join-Path $AppDir 'update-temp'
$BackupDir = Join-Path $AppDir 'update-backup'
$Log = Join-Path $AppDir 'logs\c-ebot-update.log'
$Zip = Join-Path $TempDir 'source.zip'

function Log($Text) {
  New-Item -ItemType Directory -Force -Path (Split-Path $Log) | Out-Null
  Add-Content -Path $Log -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Text"
}

function Start-PreviousVersion {
  $launcher = Join-Path $AppDir 'start-c-ebot.ps1'
  if (Test-Path $launcher) {
    Start-Process powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$launcher) -WindowStyle Normal
  }
}

try {
  Log "Starting update to $TargetSha"
  New-Item -ItemType Directory -Force -Path $TempDir | Out-Null
  Remove-Item $Zip -Force -ErrorAction SilentlyContinue

  Log "Waiting for c-ebot process $ParentPid to stop"
  for ($i = 0; $i -lt 60; $i++) {
    if (-not (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 500
  }
  if (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue) {
    Log "Process did not stop in time; terminating it"
    Stop-Process -Id $ParentPid -Force
    Start-Sleep -Seconds 2
  }

  $url = "https://github.com/walterz930/c-ebot/archive/$TargetSha.zip"
  Log "Downloading $url"
  Invoke-WebRequest -Uri $url -OutFile $Zip -UseBasicParsing

  $Extract = Join-Path $TempDir 'source'
  Remove-Item $Extract -Recurse -Force -ErrorAction SilentlyContinue
  Expand-Archive -Path $Zip -DestinationPath $Extract -Force
  $SourceRoot = Get-ChildItem $Extract -Directory | Select-Object -First 1
  if (-not $SourceRoot) { throw 'Downloaded update archive was empty.' }

  Log "Creating rollback backup"
  Remove-Item $BackupDir -Recurse -Force -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
  Copy-Item (Join-Path $AppDir 'app') (Join-Path $BackupDir 'app') -Recurse -Force
  Copy-Item (Join-Path $AppDir 'requirements.txt') (Join-Path $BackupDir 'requirements.txt') -Force
  foreach ($file in @('start-c-ebot.ps1','check-for-updates.ps1')) {
    $path = Join-Path $AppDir $file
    if (Test-Path $path) { Copy-Item $path (Join-Path $BackupDir $file) -Force }
  }

  Log "Installing application files"
  Remove-Item (Join-Path $AppDir 'app') -Recurse -Force
  Copy-Item (Join-Path $SourceRoot.FullName 'app') (Join-Path $AppDir 'app') -Recurse -Force
  Copy-Item (Join-Path $SourceRoot.FullName 'requirements.txt') (Join-Path $AppDir 'requirements.txt') -Force
  foreach ($file in @('update-standalone.ps1','check-for-updates.ps1')) {
    $source = Join-Path $SourceRoot.FullName "windows\$file"
    if (Test-Path $source) { Copy-Item $source (Join-Path $AppDir $file) -Force }
  }

  $MainPy = Join-Path $AppDir 'app\main.py'
  if (Test-Path $MainPy) {
    $mainText = Get-Content -Path $MainPy -Raw
    $mainText = $mainText.Replace('attrs("chaster_lock_id", True)', 'attrs("chaster_lock_id", False)')
    Set-Content -Path $MainPy -Value $mainText -Encoding UTF8
    Log "Applied Chaster Lock ID editable-field fix"
  }

  Set-Content -Path (Join-Path $AppDir '.cebot_commit') -Value $TargetSha -Encoding ASCII

  Log "Updating Python dependencies"
  & (Join-Path $AppDir '.venv\Scripts\python.exe') -m pip install -r (Join-Path $AppDir 'requirements.txt') | Add-Content $Log
  if ($LASTEXITCODE -ne 0) { throw "pip install failed with exit code $LASTEXITCODE" }

  Remove-Item $TempDir -Recurse -Force -ErrorAction SilentlyContinue
  Remove-Item $BackupDir -Recurse -Force -ErrorAction SilentlyContinue
  Log "Update installed successfully; restarting"
  Start-PreviousVersion
} catch {
  Log "UPDATE FAILED: $($_.Exception.Message)"
  if (Test-Path (Join-Path $BackupDir 'app')) {
    Log "Rolling back application files"
    Remove-Item (Join-Path $AppDir 'app') -Recurse -Force -ErrorAction SilentlyContinue
    Copy-Item (Join-Path $BackupDir 'app') (Join-Path $AppDir 'app') -Recurse -Force
    if (Test-Path (Join-Path $BackupDir 'requirements.txt')) { Copy-Item (Join-Path $BackupDir 'requirements.txt') (Join-Path $AppDir 'requirements.txt') -Force }
    foreach ($file in @('start-c-ebot.ps1','check-for-updates.ps1')) {
      $backup = Join-Path $BackupDir $file
      if (Test-Path $backup) { Copy-Item $backup (Join-Path $AppDir $file) -Force }
    }
  }
  Log "Starting previous version"
  Start-PreviousVersion
  exit 1
}
