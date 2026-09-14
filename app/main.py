from __future__ import annotations

import asyncio
import html
import time

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from .secrets import factory_reset, has_secrets, save_secrets
from .sync_engine import manager

APP_NAME = "c-ebot"
app = FastAPI(title="c-ebot", version="0.2.1")


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
    refresh_tag = "<meta http-equiv='refresh' content='10'>" if refresh else ""
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
{refresh_tag}<title>{title}</title><style>
body{{font-family:system-ui,sans-serif;max-width:1100px;margin:30px auto;padding:0 18px;background:#f5f6f8;color:#17202a}}
.card{{background:white;border:1px solid #ddd;border-radius:14px;padding:18px;margin:14px 0;box-shadow:0 1px 3px #0001}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}} .timer{{font-size:2rem;font-weight:700}}
.status{{display:inline-block;padding:6px 10px;border-radius:999px;background:#eee;font-weight:700}} .SYNCED{{background:#dff7e7}} .SYNCING{{background:#fff0c2}} .PAUSED{{background:#ffdede}} .WAITING{{background:#eee}}
button,input,select{{padding:10px;border-radius:8px;border:1px solid #bbb;box-sizing:border-box}} button{{cursor:pointer}} input{{width:100%}}
.actions{{display:flex;gap:8px;flex-wrap:wrap}} .actions form{{display:flex;gap:6px;align-items:center}} .actions button{{width:auto}} small{{color:#667}} .danger{{border-color:#b33;background:#fff5f5}}
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
<div class='card'><h3>Chaster</h3><div class='timer'>{fmt(s.chaster_seconds)}</div><small>Remaining time</small></div>
<div class='card'><h3>EmlaLock</h3><div class='timer'>{fmt(s.emlalock_seconds)}</div><small>Remaining time</small></div>
<div class='card'><h3>Highest / Target</h3><div class='timer'>{fmt(s.target_seconds)}</div><small>Normal sync never shortens the higher timer</small></div>
</div>
<div class='card'><h3>Controls</h3><div class='actions'>
<form method='post' action='/sync'><button>Sync Now</button></form>
<form method='post' action='/toggle'><button>{'Turn Auto Sync Off' if s.auto_sync else 'Turn Auto Sync On'}</button></form>
<form method='post' action='/resume'><button>Resume</button></form>
<form method='post' action='/adjust'><input name='seconds' type='number' min='1' placeholder='Seconds' required><button name='direction' value='add'>+ Add to both</button><button name='direction' value='subtract'>− Subtract from both</button></form>
</div></div>
<div class='card'><h3>Activity</h3>{''.join(f"<p><small>{when(x.get('time'))}</small> — {html.escape(str(x.get('action','')))} {html.escape(str(x.get('detail','')))}</p>" for x in (s.history or [])[:15]) or '<p>No activity yet.</p>'}</div>
<div class='card'><h3>Connections</h3><p>Chaster: <strong>{'credentials saved' if configured else 'not configured'}</strong></p><p>EmlaLock: <strong>{'credentials saved' if configured else 'not configured'}</strong></p><p>Discord: optional.</p><p><a href='/setup'>Setup / replace credentials</a></p></div>
<div class='card danger'><h3>Factory reset</h3><p>Deletes the encrypted credential vault only; it does not alter either service account or lock.</p><form method='post' action='/factory-reset'><input name='confirmation' placeholder='Type FACTORY RESET' autocomplete='off'><button>Factory reset bot</button></form></div>
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
async def adjust(seconds: int = Form(...), direction: str = Form(...)):
    try:
        delta = abs(seconds) if direction == "add" else -abs(seconds)
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
