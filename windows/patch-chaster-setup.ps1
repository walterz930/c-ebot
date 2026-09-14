$ErrorActionPreference = 'Stop'
$Main = Join-Path $PSScriptRoot 'app\main.py'
if (-not (Test-Path $Main)) { throw "Could not find $Main" }
$text = Get-Content -Path $Main -Raw
$old = 'attrs("chaster_lock_id", True)'
$new = 'attrs("chaster_lock_id", False)'
if ($text.Contains($old)) {
  $text = $text.Replace($old, $new)
  Set-Content -Path $Main -Value $text -Encoding UTF8
}
