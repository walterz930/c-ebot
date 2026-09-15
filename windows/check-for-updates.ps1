$ErrorActionPreference = 'Continue'
$AppDir = Split-Path -Parent $PSScriptRoot
$CommitFile = Join-Path $AppDir '.cebot_commit'
$UpdateScript = Join-Path $AppDir 'update-standalone.ps1'
$Log = Join-Path $AppDir 'logs\c-ebot-update.log'

function Write-UpdateLog($Text) {
  New-Item -ItemType Directory -Force -Path (Split-Path $Log) | Out-Null
  $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Text"
  Add-Content -Path $Log -Value $line
  Write-Host "[UPDATE] $Text" -ForegroundColor DarkCyan
}

try {
  Start-Sleep -Seconds 3
  Write-UpdateLog 'Checking GitHub for updates...'

  if (-not (Test-Path $CommitFile)) {
    Write-UpdateLog 'No local commit marker found; recording current GitHub revision.'
    $headers = @{ 'Accept' = 'application/vnd.github+json'; 'X-GitHub-Api-Version' = '2022-11-28' }
    $remote = Invoke-RestMethod -Uri 'https://api.github.com/repos/walterz930/c-ebot/commits/main' -Headers $headers -TimeoutSec 15
    Set-Content -Path $CommitFile -Value ([string]$remote.sha) -Encoding ASCII
    return
  }

  if (-not (Test-Path $UpdateScript)) {
    Write-UpdateLog 'Update script is missing; skipping automatic update check.'
    return
  }

  $current = (Get-Content $CommitFile -Raw).Trim()
  if (-not $current) {
    Write-UpdateLog 'Local commit marker is empty; skipping automatic update check.'
    return
  }

  $headers = @{ 'Accept' = 'application/vnd.github+json'; 'X-GitHub-Api-Version' = '2022-11-28' }
  $remote = Invoke-RestMethod -Uri 'https://api.github.com/repos/walterz930/c-ebot/commits/main' -Headers $headers -TimeoutSec 15
  $latest = [string]$remote.sha

  Write-UpdateLog "Installed revision: $current"
  Write-UpdateLog "GitHub revision:    $latest"

  if (-not $latest -or $latest -eq $current) {
    Write-UpdateLog 'c-ebot is up to date.'
    return
  }

  $message = [string]$remote.commit.message
  $firstLine = ($message -split "`r?`n")[0]
  Write-UpdateLog "UPDATE AVAILABLE: $latest - $firstLine"

  Add-Type -AssemblyName PresentationFramework
  $answer = [System.Windows.MessageBox]::Show(
    "A new c-ebot update is available.`n`nLatest change:`n$firstLine`n`nDo you want to download and install it now?",
    'c-ebot update available',
    [System.Windows.MessageBoxButton]::YesNo,
    [System.Windows.MessageBoxImage]::Information
  )

  if ($answer -ne [System.Windows.MessageBoxResult]::Yes) {
    Write-UpdateLog 'User declined the available update.'
    return
  }

  $python = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -match 'uvicorn\s+app\.main:app' } |
    Select-Object -First 1

  if (-not $python) {
    Write-UpdateLog 'Could not find the running c-ebot Python process.'
    [System.Windows.MessageBox]::Show('c-ebot is not running, so the update could not be started.','c-ebot update','OK','Warning') | Out-Null
    return
  }

  Write-UpdateLog "User accepted update; launching updater for PID $($python.ProcessId)."
  Start-Process powershell.exe -ArgumentList @(
    '-NoProfile','-ExecutionPolicy','Bypass','-File',$UpdateScript,
    '-TargetSha',$latest,'-ParentPid',[string]$python.ProcessId
  ) -WindowStyle Normal
} catch {
  Write-UpdateLog "Update check failed: $($_.Exception.Message)"
}
