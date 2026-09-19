from __future__ import annotations

import asyncio
import base64
import html
import json
import os
import time

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from .secrets import factory_reset, has_secrets, save_secrets, _fernet, load_secrets
from .sync_engine import manager
from .discord_bot import start_discord

APP_NAME = "c-ebot"
app = FastAPI(title=APP_NAME, version="0.3.1")
BACKUP_ITERATIONS = 390000


def fmt(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    total = max(0, int(seconds))
    values = [
        total // (365 * 86400),
        (total % (365 * 86400)) // (30 * 86400),
        (total % (30 * 86400)) // 86400,
        (total % 86400) // 3600,
        (total % 3600) // 60,
        total % 60,
    ]
    first = next((i for i, value in enumerate(values) if value), len(values) - 1)
    return ":".join(f"{value:02d}" for value in values[first:])


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
input:disabled,select:disabled,button:disabled{{background:#eee;color:#777;cursor:not-allowed;opacity:1}}
.actions{{display:flex;gap:8px;flex-wrap:wrap}} .actions form{{display:flex;gap:6px;align-items:center}} .actions button{{width:auto}} small{{color:#667}} .danger{{border-color:#b33;background:#fff5f5}}
.time-input{{display:flex;gap:6px;align-items:center;flex-wrap:wrap}} .time-input input{{width:110px}} .time-input select{{min-width:130px}}
.topbar{{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:18px}} .topbar h1{{margin:0}} .setup-button{{display:inline-block;text-decoration:none}} .setup-button button{{font-weight:700}}
@media(max-width:800px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><div class='topbar'><h1>c-ebot</h1><a class='setup-button' href='/setup'><button type='button'>Setup</button></a></div>{body}
<script>
(() => {{
  const timers = [
    document.getElementById('chaster-timer'),
    document.getElementById('emlalock-timer'),
    document.getElementById('target-timer')
  ].filter(Boolean);
  if (!timers.length) return;

  const values = new Map();
  for (const el of timers) {{
    const raw = el.dataset.seconds;
    if (raw === '') continue;
    const value = Number(raw);
    if (Number.isFinite(value)) values.set(el, Math.max(0, Math.floor(value)));
  }}

  function format(seconds) {{
    seconds = Math.max(0, Math.floor(seconds));
    const values = [
      Math.floor(seconds / (365 * 86400)),
      Math.floor((seconds % (365 * 86400)) / (30 * 86400)),
      Math.floor((seconds % (30 * 86400)) / 86400),
      Math.floor((seconds % 86400) / 3600),
      Math.floor((seconds % 3600) / 60),
      seconds % 60
    ];
    let first = values.findIndex(value => value !== 0);
    if (first === -1) first = values.length - 1;
    return values.slice(first).map(value => String(value).padStart(2, '0')).join(':');
  }}

  function render() {{
    for (const [el, value] of values) el.textContent = format(value);
  }}

  render();
  setInterval(() => {{
    for (const [el, value] of values) values.set(el, Math.max(0, value - 1));
    render();
  }}, 1000);
}})();
</script>
</body></html>"""


def _backup_key(password: str, salt: bytes) -> bytes:
    if not password:
        raise ValueError("Backup password is required")
    return base64.urlsafe_b64encode(PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=BACKUP_ITERATIONS).derive(password.encode("utf-8")))


def make_portable_backup(values: dict[str, str], password: str) -> bytes:
    salt = os.urandom(16)
    token = Fernet(_backup_key(password, salt)).encrypt(json.dumps(values, separators=(",", ":")).encode())
    return json.dumps({"format":"c-ebot-backup-v2","iterations":BACKUP_ITERATIONS,"salt":base64.urlsafe_b64encode(salt).decode(),"token":token.decode()}, separators=(",", ":")).encode()


def read_portable_backup(data: bytes, password: str) -> dict[str, str]:
    wrapper = json.loads(data.decode())
    if wrapper.get("format") != "c-ebot-backup-v2":
        raise ValueError("Not a portable c-ebot backup")
    salt = base64.urlsafe_b64decode(wrapper["salt"])
    key = base64.urlsafe_b64encode(PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=int(wrapper.get("iterations", BACKUP_ITERATIONS))).derive(password.encode()))
    values = json.loads(Fernet(key).decrypt(wrapper["token"].encode()).decode())
    if not isinstance(values, dict):
        raise ValueError("Backup contents are invalid")
    return values


def valid_credentials(values: dict) -> bool:
    return bool(values.get("chaster_token") and values.get("chaster_lock_id") and values.get("emlalock_user_id") and values.get("emlalock_api_key"))


@app.on_event("startup")
async def startup() -> None:
    await manager.start()
    await start_discord()


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> str:
    s = manager.state
    configured = has_secrets()
    status = s.status if configured else "WAITING"
    body = f"""
<div class='card'><h2>Live Time Sync</h2><p><span class='status {status}'>{status}</span></p><p><strong>{html.escape(s.message)}</strong></p><p>Auto Sync: <strong>{'ON' if s.auto_sync else 'OFF'}</strong> · Paused: <strong>{'YES' if s.paused else 'NO'}</strong></p><p>Last check: {when(s.last_check)} · Next check: {when(s.next_check)}</p></div>
<div class='grid'><div class='card'><h3>Chaster</h3><div id='chaster-timer' class='timer' data-seconds='{'' if s.chaster_seconds is None else int(s.chaster_seconds)}'>{fmt(s.chaster_seconds)}</div><small>Remaining time</small></div><div class='card'><h3>EmlaLock</h3><div id='emlalock-timer' class='timer' data-seconds='{'' if s.emlalock_seconds is None else int(s.emlalock_seconds)}'>{fmt(s.emlalock_seconds)}</div><small>Remaining time</small></div><div class='card'><h3>Highest / Target</h3><div id='target-timer' class='timer' data-seconds='{'' if s.target_seconds is None else int(s.target_seconds)}'>{fmt(s.target_seconds)}</div><small>Normal sync never shortens the higher timer</small></div></div>
<div class='card'><h3>Controls</h3><div class='actions'><form method='post' action='/sync'><button>Sync Now</button></form><form method='post' action='/toggle'><button>{'Turn Auto Sync Off' if s.auto_sync else 'Turn Auto Sync On'}</button></form><form method='post' action='/pause'><button>Pause</button></form><form method='post' action='/resume'><button>Resume</button></form><form method='post' action='/adjust'><div class='time-input'><input name='amount' type='number' min='1' step='1' placeholder='Amount' required><select name='unit'><option value='years'>Years</option><option value='months'>Months</option><option value='days' selected>Days</option><option value='hours'>Hours</option><option value='minutes'>Minutes</option><option value='seconds'>Seconds</option></select></div><button name='direction' value='add'>+ Add to both</button><button name='direction' value='subtract'>− Subtract from both</button></form></div></div>
<div class='card'><h3>Activity</h3>{''.join(f"<p><small>{when(x.get('time'))}</small> — {html.escape(str(x.get('action','')))} {html.escape(str(x.get('detail','')))}</p>" for x in (s.history or [])[:15]) or '<p>No activity yet.</p>'}</div>"""
    return page("c-ebot — Live Sync", body, refresh=False)


@app.get("/setup", response_class=HTMLResponse)
async def setup_form() -> str:
    configured = has_secrets()
    s = load_secrets() if configured else {}

    def attrs(name: str, required: bool = False, secret: bool = False) -> str:
        value = str(s.get(name, ""))
        locked = bool(value)
        req = " required" if required and not locked else ""
        disabled = " disabled aria-disabled='true'" if locked else ""
        placeholder = "Saved — locked until Factory Reset" if locked else "Enter value"
        typ = "password" if secret else "text"
        return f"type='{typ}' autocomplete='off' placeholder='{placeholder}'{req}{disabled}"

    discord_configured = bool(s.get("discord_bot_token"))
    client_id = s.get("discord_application_id", "")
    invite = f"https://discord.com/oauth2/authorize?client_id={client_id}&scope=bot%20applications.commands&permissions=68608" if client_id.isdigit() else ""
    lock_note = "<div class='card danger'><strong>Saved credentials are protected.</strong><p>Credentials remain locked after setup, but the Chaster Lock ID can be changed at any time from this page or with the Discord <code>/setlockid</code> command.</p></div>" if configured else ""
    save_button = "<button type='submit'>Save / configure available fields</button>"

    body = (
        "<div class='card'><h2>Setup</h2><p>Credentials are encrypted locally. Each saved credential is locked individually. Any credential that is still not configured remains editable until it is saved.</p></div>"
        + lock_note
        + "<form method='post' action='/setup'>"
        + "<div class='card'><h3>Chaster</h3>"
        + "<label>Developer token (wearer / primary account)<br><input name='chaster_token' "
        + attrs("chaster_token", True, True)
        + '></label><br><br>'
        + "<label>Lock ID<br><input name='chaster_lock_id' type='text' autocomplete='off' value='" + html.escape(str(s.get("chaster_lock_id", "")), quote=True) + "' placeholder='Enter Chaster Lock ID' required></label><br><br>"
        + "<button type='submit' formaction='/set-lock-id' formmethod='post'>Change Chaster Lock ID</button><hr><h4>Chaster permissions required</h4>"
        + "<p><strong>For normal sync/add-time:</strong> the API token needs the <code>locks</code> scope and the lock contract must grant the token's account <strong>Add time</strong>.</p>"
        + "<p><strong>For subtract-time:</strong> the account making the Chaster request must have <strong>Remove time</strong>. Chaster's Standard preset normally grants Remove time to the keyholder, not the wearer.</p>"
        + "<label>Chaster keyholder access token (required if this bot must remove Chaster time as keyholder)<br><input name='chaster_keyholder_token' "
        + attrs("chaster_keyholder_token", False, True)
        + '></label><p><small>The keyholder token should belong to the Chaster keyholder account and be authorized with the <code>keyholder</code> scope. Leave it empty only if the primary token\'s account itself has Remove time.</small></p></div>'
        + "<div class='card'><h3>EmlaLock</h3><label>User ID<br><input name='emlalock_user_id' "
        + attrs("emlalock_user_id", True)
        + '></label><br><br><label>API key<br><input name=\'emlalock_api_key\' '
        + attrs("emlalock_api_key", True, True)
        + '></label><br><br><label>Keyholder API key (required for subtract)<br><input name=\'emlalock_keyholder_api_key\' '
        + attrs("emlalock_keyholder_api_key", False, True)
        + '></label></div>'
        + "<div class='card'><h3>Discord (optional)</h3><p>c-ebot uses Discord slash commands, so <strong>Message Content Intent is not required</strong>. The bot only requests the Guilds intent.</p>"
        + "<p><strong>Need the Discord details?</strong> <a href='https://discord.com/developers/applications' target='_blank' rel='noopener noreferrer'>Open Discord Developer Portal ↗</a> · <a href='https://support.discord.com/hc/en-us/articles/206346498-Where-can-I-find-my-User-Server-Message-ID' target='_blank' rel='noopener noreferrer'>How to find Server, Channel & User IDs ↗</a></p>"
        + "<label>Bot token<br><input name='discord_bot_token' "
        + attrs("discord_bot_token", False, True)
        + '></label><br><br><label>Application / Client ID<br><input name=\'discord_application_id\' inputmode=\'numeric\' '
        + attrs("discord_application_id")
        + '></label><br><br><label>Server / Guild ID<br><input name=\'discord_guild_id\' inputmode=\'numeric\' '
        + attrs("discord_guild_id")
        + '></label><br><br><label>Log / alert channel ID<br><input name=\'discord_channel_id\' inputmode=\'numeric\' '
        + attrs("discord_channel_id")
        + '></label><br><br><label>Admin user IDs<br><input name=\'discord_admin_user_ids\' '
        + attrs("discord_admin_user_ids")
        + '></label><p><small>Admin IDs control /sync, /addtime, /subtracttime and /logs.</small></p>'
        + (f"<p><strong>Invite link:</strong> <a href='{html.escape(invite)}' target='_blank' rel='noopener noreferrer'>Add c-ebot to your server</a></p>" if invite else "<p>Enter the Application / Client ID to generate the server invite link.</p>")
        + "<p><strong>Discord permissions:</strong> View Channel, Send Messages, Embed Links, Read Message History. Scopes: <code>bot</code> and <code>applications.commands</code>.</p><p><strong>Developer Portal:</strong> create the application, add a Bot, copy the Bot Token and Application ID, then invite it to the server.</p>"
        + f"<p><strong>Connection:</strong> {'configured' if discord_configured else 'not configured'}</p></div>"
        + "<div class='card'><div class='actions'><a href='/' style='text-decoration:none'><button type='button'>← Back to Dashboard</button></a>"
        + save_button
        + "</div></div></form>"
        + f"<div class='card'><h3>Connections</h3><p>Chaster: <strong>{'credentials saved' if s.get('chaster_token') and s.get('chaster_lock_id') else 'not configured'}</strong></p><p>EmlaLock: <strong>{'credentials saved' if s.get('emlalock_user_id') and s.get('emlalock_api_key') else 'not configured'}</strong></p><p>Discord: <strong>{'configured' if discord_configured else 'not configured'}</strong></p></div>"
        + "<div class='card'><h3>Backup / restore</h3><p>Create a portable encrypted backup with a backup password.</p><form method='post' action='/backup-vault'><input name='backup_password' type='password' placeholder='Backup password' required><button type='submit'>Download encrypted backup</button></form><br><form method='post' action='/import-vault' enctype='multipart/form-data'><input name='vault_file' type='file' accept='.enc' required><input name='backup_password' type='password' placeholder='Backup password' required><button type='submit'>Import encrypted backup</button></form></div>"
        + "<div class='card danger'><h3>Factory reset</h3><p>Deletes the encrypted local credential vault only and unlocks all setup fields again.</p><form method='post' action='/factory-reset'><input name='confirmation' placeholder='Type FACTORY RESET'><button>Factory reset bot</button></form></div>"
    )
    return page("Setup — c-ebot", body, refresh=False)


@app.post("/setup")
async def setup_submit(chaster_token: str = Form(""), chaster_lock_id: str = Form(""), chaster_keyholder_token: str = Form(""), emlalock_user_id: str = Form(""), emlalock_api_key: str = Form(""), emlalock_keyholder_api_key: str = Form(""), discord_bot_token: str = Form(""), discord_application_id: str = Form(""), discord_guild_id: str = Form(""), discord_channel_id: str = Form(""), discord_admin_user_ids: str = Form("")):
    current = load_secrets() if has_secrets() else {}
    submitted = {"chaster_token": chaster_token.strip(), "chaster_lock_id": chaster_lock_id.strip(), "chaster_keyholder_token": chaster_keyholder_token.strip(), "emlalock_user_id": emlalock_user_id.strip(), "emlalock_api_key": emlalock_api_key.strip(), "emlalock_keyholder_api_key": emlalock_keyholder_api_key.strip(), "discord_bot_token": discord_bot_token.strip(), "discord_application_id": discord_application_id.strip(), "discord_guild_id": discord_guild_id.strip(), "discord_channel_id": discord_channel_id.strip(), "discord_admin_user_ids": discord_admin_user_ids.strip()}
    values = dict(current)
    for name, value in submitted.items():
        if not current.get(name) and value:
            values[name] = value
    if not valid_credentials(values):
        return HTMLResponse(page("Setup incomplete", "<div class='card danger'><h2>Required credentials are missing</h2><p>Chaster token + Lock ID and EmlaLock User ID + API key are required.</p><a href='/setup'>Back to Setup</a></div>"), status_code=400)
    save_secrets(values)
    manager.resume()
    asyncio.create_task(manager.sync_once())
    await start_discord()
    return RedirectResponse("/", status_code=303)


@app.post("/backup-vault")
async def backup_vault(backup_password: str = Form("")):
    try:
        if not has_secrets(): raise ValueError("No credentials are configured yet")
        if len(backup_password) < 8: raise ValueError("Backup password must be at least 8 characters")
        return StreamingResponse(iter([make_portable_backup(load_secrets(), backup_password)]), media_type="application/octet-stream", headers={"Content-Disposition": 'attachment; filename="c-ebot-vault.enc"'})
    except Exception as exc:
        return HTMLResponse(page("Backup failed", f"<div class='card danger'><h2>Backup failed</h2><p>{html.escape(str(exc))}</p><a href='/setup'>Back to Setup</a></div>"), status_code=400)


@app.post("/import-vault")
async def import_vault(vault_file: UploadFile = File(...), backup_password: str = Form("")):
    try:
        if has_secrets(): raise ValueError("Credentials are already saved. Factory Reset is required before importing a replacement vault.")
        if not vault_file.filename or not vault_file.filename.lower().endswith(".enc"): raise ValueError("Please select a c-ebot .enc backup file")
        data = await vault_file.read()
        if not data or len(data) > 1024 * 1024: raise ValueError("Invalid or oversized backup file")
        try: values = read_portable_backup(data, backup_password)
        except Exception: values = json.loads(_fernet().decrypt(data).decode())
        if not isinstance(values, dict) or not valid_credentials(values): raise ValueError("Backup does not contain a valid c-ebot credential set")
        save_secrets({str(k): str(v) for k, v in values.items()})
        manager.resume()
        asyncio.create_task(manager.sync_once())
        await start_discord()
        return RedirectResponse("/", status_code=303)
    except Exception as exc:
        return HTMLResponse(page("Import failed", f"<div class='card danger'><h2>Import failed</h2><p>{html.escape(str(exc))}</p><a href='/setup'>Back to Setup</a></div>"), status_code=400)


@app.post("/sync")
async def sync_now():
    try: await manager.sync_once()
    except Exception as exc: manager.pause(f"Sync failed: {exc}")
    return RedirectResponse("/", status_code=303)


@app.post("/set-lock-id")
async def set_lock_id(chaster_lock_id: str = Form("")):
    new_lock_id = chaster_lock_id.strip()
    if not new_lock_id or len(new_lock_id) > 200 or any(ch.isspace() for ch in new_lock_id):
        return HTMLResponse(page("Invalid Lock ID", "<div class='card danger'><h2>Invalid Chaster Lock ID</h2><p>Enter a non-empty Lock ID without spaces.</p><a href='/setup'>Back to Setup</a></div>"), status_code=400)
    try:
        settings = load_secrets()
        if not settings.get("chaster_token"):
            raise ValueError("Chaster is not configured yet.")
        old_lock_id = settings.get("chaster_lock_id", "").strip()
        if old_lock_id == new_lock_id:
            return RedirectResponse("/setup", status_code=303)
        settings["chaster_lock_id"] = new_lock_id
        save_secrets(settings)
        manager.log("CHASTER_LOCK_CHANGED", f"{old_lock_id or '(none)'} -> {new_lock_id} via web UI")
        manager.state.message = f"Chaster Lock ID changed to {new_lock_id}"
        manager._save()
        try:
            await manager.sync_once()
        except Exception as exc:
            manager.pause(f"Sync after Chaster Lock ID change failed: {exc}")
        return RedirectResponse("/", status_code=303)
    except Exception as exc:
        return HTMLResponse(page("Lock ID change failed", f"<div class='card danger'><h2>Could not change Chaster Lock ID</h2><p>{html.escape(str(exc))}</p><a href='/setup'>Back to Setup</a></div>"), status_code=400)


@app.post("/toggle")
async def toggle():
    manager.state.auto_sync = not manager.state.auto_sync
    if manager.state.auto_sync and not manager.state.paused: manager.state.status = "SYNCING"
    manager.log("AUTO_SYNC_ON" if manager.state.auto_sync else "AUTO_SYNC_OFF")
    return RedirectResponse("/", status_code=303)


@app.post("/pause")
async def pause():
    manager.pause("Paused from dashboard")
    return RedirectResponse("/", status_code=303)


@app.post("/resume")
async def resume():
    manager.resume()
    return RedirectResponse("/", status_code=303)


@app.post("/adjust")
async def adjust(amount: int = Form(...), unit: str = Form(...), direction: str = Form(...)):
    try:
        if amount <= 0: raise ValueError("Amount must be greater than zero")
        multipliers = {"seconds":1,"minutes":60,"hours":3600,"days":86400,"months":30*86400,"years":365*86400}
        if unit not in multipliers: raise ValueError("Invalid time unit")
        await manager.manual_delta(amount * multipliers[unit] * (1 if direction == "add" else -1))
    except Exception as exc:
        manager.pause(f"Manual change failed: {exc}")
    return RedirectResponse("/", status_code=303)


@app.post("/factory-reset")
async def reset(confirmation: str = Form("")):
    if confirmation.strip() != "FACTORY RESET":
        return HTMLResponse(page("Factory reset", "<div class='card danger'><h2>Reset cancelled</h2><p>You must type <strong>FACTORY RESET</strong> exactly.</p><a href='/setup'>Back to Setup</a></div>"), status_code=400)
    factory_reset()
    manager.state = manager.state.__class__()
    manager.state.history = []
    manager._save()
    return RedirectResponse("/setup", status_code=303)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status":"ok","service":APP_NAME}
