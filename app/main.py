from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from .secrets import factory_reset, has_secrets, save_secrets

APP_NAME = "c-ebot"
DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="c-ebot", version="0.1.0")


def page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{title}</title><style>
body{{font-family:system-ui,sans-serif;max-width:1000px;margin:40px auto;padding:0 20px;background:#f6f7f9;color:#17202a}}
.card{{background:white;border:1px solid #ddd;border-radius:12px;padding:20px;margin:14px 0}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}} input,button{{padding:10px;border-radius:8px;border:1px solid #bbb;width:100%;box-sizing:border-box}} button{{cursor:pointer}}
small{{color:#667}} .danger{{border-color:#b33;background:#fff5f5}} .optional{{border-left:4px solid #888}}
@media(max-width:700px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><h1>c-ebot</h1>{body}</body></html>"""


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> str:
    configured = has_secrets()
    status = "Configured — credentials hidden" if configured else "Not configured"
    setup_link = "<a href='/setup'>Replace credentials</a>" if configured else "<a href='/setup'>Open setup wizard →</a>"
    body = f"""
<div class='card'><h2>Time Sync Dashboard</h2><p>Credential status: <strong>{status}</strong></p><p>API keys and tokens are never displayed after they are saved.</p></div>
<div class='grid'>
  <div class='card'><h3>Chaster</h3><p>Status: <strong>Pending API connection</strong></p><p>Developer token: ••••••••</p></div>
  <div class='card'><h3>EmlaLock</h3><p>Status: <strong>Pending API connection</strong></p><p>Credentials: ••••••••</p></div>
</div>
<div class='card optional'><h3>Discord</h3><p><strong>Optional.</strong> c-ebot can run without Discord. If Discord is not configured, synchronization and the web dashboard do not depend on Discord.</p><p>When enabled, Discord can provide logs, alerts, and administrative commands.</p></div>
<div class='card'><h3>Sync</h3><p>Mode: highest-time-wins</p><p>Auto sync: disabled until setup is complete</p><p>Verification: enabled by design</p><p>Failure policy: pause + Discord alert when Discord is enabled</p><p>{setup_link}</p></div>
<div class='card danger'><h3>Factory reset</h3><p>This permanently deletes the encrypted API credentials from the bot. It does not delete anything from Chaster or EmlaLock.</p><form method='post' action='/factory-reset'><input name='confirmation' placeholder="Type FACTORY RESET" autocomplete='off'><br><br><button type='submit'>Factory reset bot</button></form></div>
"""
    return page("c-ebot", body)


@app.get("/setup", response_class=HTMLResponse)
async def setup_form() -> str:
    body = """
<div class='card'><h2>Setup wizard</h2><p>Enter credentials once. After saving, c-ebot stores them encrypted and will only show a masked status. The raw values cannot be viewed from the dashboard.</p></div>
<form method='post' action='/setup'>
<div class='grid'>
<div class='card'><h3>Chaster</h3>
<label>Developer token<br><input name='chaster_token' type='password' autocomplete='new-password' required></label></div>
<div class='card'><h3>EmlaLock</h3>
<label>User ID<br><input name='emlalock_user_id' autocomplete='off' required></label><br><br>
<label>API key<br><input name='emlalock_api_key' type='password' autocomplete='new-password' required></label><br><br>
<label>Keyholder API key (required for subtract time)<br><input name='emlalock_keyholder_api_key' type='password' autocomplete='new-password' required></label></div>
</div>
<div class='card optional'><h3>Discord (Optional)</h3>
<p>You can leave Discord completely disabled. c-ebot will still run without a Discord bot or Discord token.</p>
<label>Discord log channel ID (optional)<br><input name='discord_channel_id' autocomplete='off'></label><br><br>
<button type='submit'>Save encrypted credentials</button></div>
</form>
"""
    return page("Setup — c-ebot", body)


@app.post("/setup")
async def setup_submit(
    chaster_token: str = Form(""),
    emlalock_user_id: str = Form(""),
    emlalock_api_key: str = Form(""),
    emlalock_keyholder_api_key: str = Form(""),
    discord_channel_id: str = Form(""),
):
    save_secrets({
        "chaster_token": chaster_token,
        "emlalock_user_id": emlalock_user_id,
        "emlalock_api_key": emlalock_api_key,
        "emlalock_keyholder_api_key": emlalock_keyholder_api_key,
        "discord_channel_id": discord_channel_id,
    })
    return RedirectResponse("/", status_code=303)


@app.post("/factory-reset")
async def reset(confirmation: str = Form("")):
    if confirmation.strip() != "FACTORY RESET":
        return HTMLResponse(page("Factory reset", "<div class='card danger'><h2>Reset cancelled</h2><p>You must type <strong>FACTORY RESET</strong> exactly.</p><a href='/'>Back</a></div>"), status_code=400)
    factory_reset()
    return RedirectResponse("/setup", status_code=303)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": APP_NAME}
