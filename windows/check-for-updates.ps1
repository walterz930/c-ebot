$ErrorActionPreference = 'SilentlyContinue'
$AppDir = Split-Path -Parent $PSScriptRoot
$CommitFile = Join-Path $AppDir '.cebot_commit'
$UpdateScript = Join-Path $AppDir 'update-standalone.ps1'
$Log = Join-Path $AppDir 'logs\c-ebot-update.log'

function Write-UpdateLog($Text) {
  New-Item -ItemType Directory -Force -Path (Split-Path $Log) | Out-Null
  Add-Content -Path $Log -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Text"
}

try {
  # Give the web server a moment to finish starting before checking GitHub.
  Start-Sleep -Seconds 4
  if (-not (Test-Path $CommitFile) -or -not (Test-Path $UpdateScript)) { return }

  $current = (Get-Content $CommitFile -Raw).Trim()
  if (-not $current) { return }

  $headers = @{ 'Accept' = 'application/vnd.github+json'; 'X-GitHub-Api-Version' = '2026-03-10' }
  $remote = Invoke-RestMethod -Uri 'https://api.github.com/repos/walterz930/c-ebot/commits/main' -Headers $headers -TimeoutSec 15
  $latest = [string]$remote.sha
  if (-not $latest -or $latest -eq $current) {
    Write-UpdateLog 'Update check: already up to date.'
    return
  }

  $message = [string]$remote.commit.message
  $firstLine = ($message -split "`r?`n")[0]
  Write-UpdateLog "Update available: $latest - $firstLine"

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

  # Find the running uvicorn/Python process so the updater can wait for it to exit.
  $python = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -match 'uvicorn\s+app\.main:app' } |
    Select-Object -First 1
  if (-not $python) {
    [System.Windows.MessageBox]::Show('c-ebot is not running, so the update could not be started.','c-ebot update', 'OK', 'Warning') | Out-Null
    return
  }

  Write-UpdateLog "User accepted update; starting updater for PID $($python.ProcessId)."
  Start-Process powershell.exe -ArgumentList @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $UpdateScript,
    '-TargetSha', $latest, '-ParentPid', [string]$python.ProcessId
  )
} catch {
  Write-UpdateLog "Update check failed: $($_.Exception.Message)"
}
