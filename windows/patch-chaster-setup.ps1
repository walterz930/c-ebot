param(
  [Parameter(Mandatory=$true)][string]$AppDir
)
$ErrorActionPreference = 'Stop'
$Main = Join-Path $AppDir 'app\main.py'
if (-not (Test-Path $Main)) { throw "Could not find $Main" }
$text = Get-Content -LiteralPath $Main -Raw
$text = $text.Replace('attrs("chaster_lock_id", True)', 'attrs("chaster_lock_id", False)')

$Discord = Join-Path $AppDir 'app\discord_bot.py'
if (Test-Path $Discord) {
  $discordText = Get-Content -LiteralPath $Discord -Raw
  $old = @'
def format_seconds(value: int | None) -> str:
    if value is None: return "unknown"
    value = max(0, int(value)); days, rem = divmod(value, 86400); hours, rem = divmod(rem, 3600); minutes, seconds = divmod(rem, 60)
    parts = []
    if days: parts.append(f"{days}d")
    if hours or days: parts.append(f"{hours}h")
    if minutes or hours or days: parts.append(f"{minutes}m")
    parts.append(f"{seconds}s"); return " ".join(parts)
'@
  $new = @'
def format_seconds(value: int | None) -> str:
    if value is None: return "unknown"
    value = max(0, int(value))
    years, rem = divmod(value, 365 * 86400)
    months, rem = divmod(rem, 30 * 86400)
    days, rem = divmod(rem, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)

    parts = []
    for amount, singular, plural in (
        (years, "year", "years"),
        (months, "month", "months"),
        (days, "day", "days"),
        (hours, "hour", "hours"),
        (minutes, "minute", "minutes"),
        (seconds, "second", "seconds"),
    ):
        if amount:
            parts.append(f"{amount} {singular if amount == 1 else plural}")
    if not parts:
        return "0 seconds"
    return " ".join(parts)
'@
  if ($discordText.Contains($old)) {
    $discordText = $discordText.Replace($old, $new)
    Set-Content -LiteralPath $Discord -Value $discordText -Encoding UTF8
  }
}
Set-Content -LiteralPath $Main -Value $text -Encoding UTF8
