# c-ebot Windows download unblock helper
#
# Run this once from the extracted c-ebot folder if Windows shows
# "Open File - Security Warning" or reports that the publisher is unknown.
# This removes the Windows Internet Zone marker from c-ebot's local files.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

Write-Host "Unblocking c-ebot files in: $root" -ForegroundColor Cyan

Get-ChildItem -LiteralPath $root -Recurse -File -Force |
    Unblock-File

Write-Host "Done. You can now run START-C-EBOT.cmd." -ForegroundColor Green
Read-Host "Press Enter to close"
