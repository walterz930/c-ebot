param(
  [Parameter(Mandatory=$true)][string]$AppDir
)
$ErrorActionPreference = 'Stop'
$Main = Join-Path $AppDir 'app\main.py'
if (-not (Test-Path $Main)) { throw "Could not find $Main" }
$text = Get-Content -LiteralPath $Main -Raw
$text = $text.Replace('attrs("chaster_lock_id", True)', 'attrs("chaster_lock_id", False)')
Set-Content -LiteralPath $Main -Value $text -Encoding UTF8
