from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

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
small{{color:#667}}
@media(max-width:700px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><h1>c-ebot</h1>{body}</body></html>"""


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> str:
    body = """
<div class='card'><h2>Time Sync Dashboard</h2><p>Setup wizard is ready. API adapters and live synchronization are being wired in next.</p></div>
<div class='grid'>
  <div class='card'><h3>Chaster</h3><p>Status: <strong>Not configured</strong></p><p>Timer: —</p></div>
  <div class='card'><h3>EmlaLock</h3><p>Status: <strong>Not configured</strong></p><p>Timer: —</p></div>
</div>
<div class='card'><h3>Sync</h3><p>Mode: highest-time-wins</p><p>Auto sync: disabled until setup is complete</p><p>Verification: enabled by design</p><p>Failure policy: pause + Discord alert</p><a href='/setup'>Open setup wizard →</a></div>
"""
    return page("c-ebot", body)


@app.get("/setup", response_class=HTMLResponse)
async def setup_form() -> str:
    body = """
<div class='card'><h2>Setup wizard</h2><p>Secrets are accepted here for local setup and must never be committed to Git.</p></div>
<form method='post' action='/setup'>
<div class='grid'>
<div class='card'><h3>Chaster</h3>
<label>Developer token<br><input name='chaster_token' type='password' autocomplete='off'></label></div>
<div class='card'><h3>EmlaLock</h3>
<label>User ID<br><input name='emlalock_user_id' autocomplete='off'></label><br><br>
<label>API key<br><input name='emlalock_api_key' type='password' autocomplete='off'></label><br><br>
<label>Keyholder API key (required for subtract time)<br><input name='emlalock_keyholder_api_key' type='password' autocomplete='off'></label></div>
</div>
<div class='card'><h3>Discord</h3><label>Log channel ID<br><input name='discord_channel_id' autocomplete='off'></label><br><br>
<button type='submit'>Save setup</button></div>
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
    # Placeholder only: production implementation will encrypt these values before storage.
    # Do not log or echo credentials.
    (DATA_DIR / "setup.pending").write_text("configured=true\n", encoding="utf-8")
    return RedirectResponse("/", status_code=303)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": APP_NAME}
