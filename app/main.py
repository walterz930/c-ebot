from __future__ import annotations

import asyncio
import html
import json
import os
import time

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from .secrets import factory_reset, has_secrets, save_secrets, VAULT_PATH, _fernet
from .sync_engine import manager

APP_NAME = "c-ebot"
app = FastAPI(title="c-ebot", version="0.2.5")


def fmt(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    seconds = max(0, int(seconds))
    d, r = divmod(seconds, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h or d: parts.append(f"{h}h")
    if m or h or d: parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)


def when(ts: float | None) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else "—"


def page(title: str, body: str, refresh: bool = False) -> str:
    refresh_tag = "<meta http-equiv='refresh' content='30'>" if refresh else ""
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
{refresh_tag}<title>{title}</title><style>
body{{font-family:system-ui,sans-serif;max-width:1100px;margin:30px auto;padding:0 18px;background:#f5f6f8;color:#17202a}}
.card{{background:white;border:1px solid #ddd;border-radius:14px;padding:18px;margin:14px 0;box-shadow:0 1px 3px #0001}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}} .timer{{font-size:2rem;font-weight:700}}
.status{{display:inline-block;padding:6px 10px;border-radius:999px;background:#eee;font-weight:700}} .SYNCED{{background:#dff7e7}} .SYNCING{{background:#fff0c2}} .PAUSED{{background:#ffdede}} .WAITING{{background:#eee}}
button,input,select{{padding:10px;border-radius:8px;border:1px solid #bbb;box-sizing:border-box}} button{{cursor:pointer}} input{{width:100%}}
.actions{{display:flex;gap:8px;flex-wrap:wrap}} .actions form{{display:flex;gap:6px;align-items:center}} .actions button{{width:auto}} small{{color:#667}} .danger{{border-color:#b33;background:#fff5f5}}
.time-input{{display:flex;gap:6px;align-items:center;flex-wrap:wrap}} .time-input input{{width:110px}} .time-input select{{min-width:130px}}
@media(max-width:800px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><h1>c-ebot</h1>{body}</body></html>"""


@app.on_event("startup")
async def startup() -> None:
    await manager.start()


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> str:
    s = manager.state
    configured = has_secrets()
    status = s.status if configured else "WAITING"
    body = f"""
<div class='card'><h2>Live Time Sync</h2><p><span class='status {status}'>{status}</span></p>
<p><strong>{html.escape(s.message)}</strong></p><p>Auto Sync: <strong>{'ON' if s.auto_sync else 'OFF'}</strong> · Paused: <strong>{'YES' if s.paused else 'NO'}</strong></p>
<p>Last check: {when(s.last_check)} · Next check: {when(s.next_check)}</p></div>
<div class='grid'>
<div class='card'><h3>Chaster</h3><div class='timer countdown' data-seconds='{'' if s.chaster_seconds is None else int(s.chaster_seconds)}'>{fmt(s.chaster_seconds)}</div><small>Remaining time</small></div>
<div class='card'><h3>EmlaLock</h3><div class='timer countdown' data-seconds='{'' if s.emlalock_seconds is None else int(s.emlalock_seconds)}'>{fmt(s.emlalock_seconds)}</div><small>Remaining time</small></div>
<div class='card'><h3>Highest / Target</h3><div class='timer countdown' data-seconds='{'' if s.target_seconds is None else int(s.target_seconds)}'>{fmt(s.target_seconds)}</div><small>Normal sync never shortens the higher timer</small></div>
</div>
<div class='card'><h3>Controls</h3><div class='actions'>
<form method='post' action='/sync'><button>Sync Now</button></form>
<form method='post' action='/toggle'><button>{'Turn Auto Sync Off' if s.auto_sync else 'Turn Auto Sync On'}</button></form>
<form method='post' action='/resume'><button>Resume</button></form>
<form method='post' action='/adjust'>
<div class='time-input'><input name='amount' type='number' min='1' step='1' placeholder='Amount' aria-label='Amount' required>
<select name='unit' aria-label='Time unit' required><option value='years'>Years</option><option value='months'>Months</option><option value='days' selected>Days</option><option value='hours'>Hours</option><option value='minutes'>Minutes</option><option value='seconds'>Seconds</option></select></div>
<button name='direction' value='add'>+ Add to both</button><button name='direction' value='subtract'>− Subtract from both</button>
</form>
</div><small>Enter one number and choose Years, Months, Days, Hours, Minutes, or Seconds. Months are treated as 30 days and years as 365 days.</small></div>
<div class='card'><h3>Activity</h3>{''.join(f"<p><small>{when(x.get('time'))}</small> — {html.escape(str(x.get('action','')))} {html.escape(str(x.get('detail','')))}</p>" for x in (s.history or [])[:15]) or '<p>No activity yet.</p>'}</div>
<div class='card'><h3>Connections</h3><p>Chaster: <strong>{'credentials saved' if configured else 'not configured'}</strong></p><p>EmlaLock: <strong>{'credentials saved' if configured else 'not configured'}</strong></p><p>Discord: optional.</p><p><a href='/setup'>Setup / replace credentials</a></p>
<h3>Backup / restore</h3><p>Back up the encrypted credential vault before updating or replacing the bot folder.</p>
<p><a href='/backup-vault'>Download encrypted credential backup</a></p>
<form method='post' action='/import-vault' enctype='multipart/form-data'><input name='vault_file' type='file' accept='.enc' required><button type='submit'>Import encrypted backup</button></form>
<small>Import replaces the current encrypted vault. The backup must have been created by c-ebot with the same APP_SECRET.</small></div>
<div class='card danger'><h3>Factory reset</h3><p>Deletes the encrypted credential vault only; it does not alter either service account or lock.</p><form method='post' action='/factory-reset'><input name='confirmation' placeholder='Type FACTORY RESET' autocomplete='off'><button>Factory reset bot</button></form></div>
<script>
(function() {{
  const timers = Array.from(document.querySelectorAll('.countdown'));
  const values = timers.map(el => {{
    const raw = el.dataset.seconds;
    return raw === '' ? null : Math.max(0, Number(raw));
  }});
  const started = Date.now();
  function format(total) {{
    total = Math.max(0, Math.floor(total));
    const d = Math.floor(total / 86400); total %= 86400;
    const h = Math.floor(total / 3600); total %= 3600;
    const m = Math.floor(total / 60); const s = total % 60;
    const parts = [];
    if (d) parts.push(d + 'd');
    if (h || d) parts.push(h + 'h');
    if (m || h || d) parts.push(m + 'm');
    parts.push(s + 's');
    return parts.join(' ');
  }}
  function tick() {{
    const elapsed = (Date.now() - started) / 1000;
    timers.forEach((el, i) => {{
      if (values[i] !== null) el.textContent = format(values[i] - elapsed);
    }});
  }}
  tick();
  setInterval(tick, 250);
}})();
</script>
"""
    return page("c-ebot — Live Sync", body, refresh=True)


@app.get("/setup", response_class=HTMLResponse)
async def setup_form() -> str:
    body = """<div class='card'><h2>Setup wizard</h2><p>Credentials are encrypted and hidden after saving. This page will not automatically refresh while you enter them.</p><p>Enter the Chaster lock ID from the lock URL so c-ebot knows which lock to synchronize.</p></div>
<form method='post' action='/setup'><div class='card'><h3>Chaster</h3><label>Developer token<br><input name='chaster_token' type='password' autocomplete='off' required></label><br><br><label>Lock ID<br><input name='chaster_lock_id' autocomplete='off' required></label></div>
<div class='card'><h3>EmlaLock</h3><label>User ID<br><input name='emlalock_user_id' autocomplete='off' required></label><br><br><label>API key<br><input name='emlalock_api_key' type='password' autocomplete='off' required></label><br><br><label>Keyholder API key (required for subtract)<br><input name='emlalock_keyholder_api_key' type='password' autocomplete='off' required></label></div>
<div class='card'><h3>Discord (optional)</h3><label>Discord log channel ID<br><input name='discord_channel_id' autocomplete='off'></label><br><br><button type='submit'>Save and start syncing</button></div></form>"""
    return page("Setup — c-ebot", body, refresh=False)


@app.post("/setup")
async def setup_submit(chaster_token: str = Form(""), chaster_lock_id: str = Form(""), emlalock_user_id: str = Form(""), emlalock_api_key: str = Form(""), emlalock_keyholder_api_key: str = Form(""), discord_channel_id: str = Form("")):
    save_secrets({"chaster_token": chaster_token.strip(), "chaster_lock_id": chaster_lock_id.strip(), "emlalock_user_id": emlalock_user_id.strip(), "emlalock_api_key": emlalock_api_key.strip(), "emlalock_keyholder_api_key": emlalock_keyholder_api_key.strip(), "discord_channel_id": discord_channel_id.strip()})
    manager.resume()
    asyncio.create_task(manager.sync_once())
    return RedirectResponse("/", status_code=303)


@app.get("/backup-vault")
async def backup_vault():
    if not has_secrets():
        return HTMLResponse(page("Backup", "<div class='card'><h2>No backup available</h2><p>No encrypted credential vault exists yet.</p><a href='/'>Back</a></div>"), status_code=404)
    return FileResponse(VAULT_PATH, filename="c-ebot-vault.enc", media_type="application/octet-stream")


@app.post("/import-vault")
async def import_vault(vault_file: UploadFile = File(...)):
    try:
        if not vault_file.filename or not vault_file.filename.lower().endswith(".enc"):
            raise ValueError("Please select a c-ebot .enc backup file")
        data = await vault_file.read()
        if not data or len(data) > 1024 * 1024:
            raise ValueError("Invalid or oversized backup file")
        values = json.loads(_fernet().decrypt(data).decode("utf-8"))
        if not isinstance(values, dict) or not values.get("chaster_token") or not values.get("chaster_lock_id") or not values.get("emlalock_user_id") or not values.get("emlalock_api_key"):
            raise ValueError("Backup does not contain a valid c-ebot credential set")
        VAULT_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = VAULT_PATH.with_suffix(".import.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, VAULT_PATH)
        manager.resume()
        asyncio.create_task(manager.sync_once())
        return RedirectResponse("/", status_code=303)
    except Exception as exc:
        return HTMLResponse(page("Import failed", f"<div class='card danger'><h2>Import failed</h2><p>{html.escape(str(exc))}</p><a href='/'>Back</a></div>"), status_code=400)


@app.post("/sync")
async def sync_now():
    try:
        await manager.sync_once()
    except Exception as exc:
        manager.pause(f"Sync failed: {exc}")
    return RedirectResponse("/", status_code=303)


@app.post("/toggle")
async def toggle():
    manager.state.auto_sync = not manager.state.auto_sync
    if manager.state.auto_sync and not manager.state.paused:
        manager.state.status = "SYNCING"
    manager.log("AUTO_SYNC_ON" if manager.state.auto_sync else "AUTO_SYNC_OFF")
    return RedirectResponse("/", status_code=303)


@app.post("/resume")
async def resume():
    manager.resume()
    return RedirectResponse("/", status_code=303)


@app.post("/adjust")
async def adjust(amount: int = Form(...), unit: str = Form(...), direction: str = Form(...)):
    try:
        if amount <= 0:
            raise ValueError("Amount must be greater than zero")
        multipliers = {"seconds": 1, "minutes": 60, "hours": 3600, "days": 86400, "months": 30 * 86400, "years": 365 * 86400}
        if unit not in multipliers:
            raise ValueError("Invalid time unit")
        total_seconds = amount * multipliers[unit]
        delta = total_seconds if direction == "add" else -total_seconds
        await manager.manual_delta(delta)
    except Exception as exc:
        manager.pause(f"Manual change failed: {exc}")
    return RedirectResponse("/", status_code=303)


@app.post("/factory-reset")
async def reset(confirmation: str = Form("")):
    if confirmation.strip() != "FACTORY RESET":
        return HTMLResponse(page("Factory reset", "<div class='card danger'><h2>Reset cancelled</h2><p>You must type <strong>FACTORY RESET</strong> exactly.</p><a href='/'>Back</a></div>"), status_code=400)
    factory_reset()
    manager.state = manager.state.__class__()
    manager.state.history = []
    manager._save()
    return RedirectResponse("/setup", status_code=303)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": APP_NAME}
