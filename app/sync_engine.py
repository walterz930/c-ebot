from __future__ import annotations

import asyncio
import inspect
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

import httpx

from .secrets import load_secrets

CHASTER_BASE = "https://api.chaster.app"
EMLALOCK_BASE = "https://api.emlalock.com"
DATA_DIR = Path(os.getenv("DATA_DIR") or (Path(__file__).resolve().parent.parent / "data"))
STATE_PATH = DATA_DIR / "sync-state.json"
INTERVAL = max(10, int(os.getenv("SYNC_INTERVAL_SECONDS", "30")))

_event_callback: Callable[[str, str], Any] | None = None


def set_event_callback(callback: Callable[[str, str], Any] | None) -> None:
    global _event_callback
    _event_callback = callback


def format_duration(seconds: int | float | None) -> str:
    if seconds is None:
        return "unknown"
    total = max(0, int(seconds))
    years, rem = divmod(total, 365 * 86400)
    months, rem = divmod(rem, 30 * 86400)
    days, rem = divmod(rem, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = [years, months, days, hours, minutes, secs]
    first = next((i for i, value in enumerate(parts) if value), len(parts) - 1)
    return ":".join(f"{value:02d}" for value in parts[first:])


@dataclass
class RuntimeState:
    auto_sync: bool = True
    paused: bool = False
    status: str = "WAITING"
    message: str = "Waiting for API connection"
    chaster_seconds: int | None = None
    emlalock_seconds: int | None = None
    target_seconds: int | None = None
    last_check: float | None = None
    next_check: float | None = None
    last_action: str = ""
    last_error: str = ""
    history: list[dict[str, Any]] | None = None


class SyncError(RuntimeError):
    pass


class SyncManager:
    def __init__(self) -> None:
        self.state = self._load()
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None

    def _load(self) -> RuntimeState:
        try:
            raw = json.loads(STATE_PATH.read_text())
            return RuntimeState(**raw)
        except Exception:
            return RuntimeState(history=[])

    def _save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(asdict(self.state), separators=(",", ":")))

    def log(self, action: str, detail: str = "") -> None:
        if self.state.history is None:
            self.state.history = []
        self.state.history.insert(0, {"time": time.time(), "action": action, "detail": detail})
        self.state.history = self.state.history[:100]
        self.state.last_action = f"{action}: {detail}" if detail else action
        self._save()
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{stamp}] {action}{': ' + detail if detail else ''}", flush=True)
        if _event_callback is not None:
            try:
                result = _event_callback(action, detail)
                if inspect.isawaitable(result):
                    asyncio.create_task(result)
            except Exception as exc:
                print(f"[c-ebot] Discord activity notification failed: {exc}", flush=True)

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        print(f"[c-ebot] Starting sync engine (interval: {INTERVAL}s)", flush=True)
        self._task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        while True:
            try:
                if self.state.auto_sync and not self.state.paused:
                    await self.sync_once()
            except Exception as exc:
                self.pause(f"Sync failed: {exc}")
            if self.state.auto_sync and not self.state.paused:
                self.state.next_check = time.time() + INTERVAL
            else:
                self.state.next_check = None
            self._save()
            await asyncio.sleep(INTERVAL)

    def pause(self, reason: str) -> None:
        # Pause only the automatic loop. Do not disable the auto-sync setting,
        # so Resume can reliably turn the same loop back on.
        self.state.paused = True
        self.state.status = "PAUSED"
        self.state.message = reason
        self.state.last_error = reason
        self.state.next_check = None
        self.log("PAUSED", reason)

    def resume(self) -> None:
        # A previous /toggle could have left auto_sync=False. Resume is an
        # explicit request to enable automatic synchronization again.
        self.state.auto_sync = True
        self.state.paused = False
        self.state.status = "SYNCING"
        self.state.message = "Automatic synchronization enabled"
        self.state.last_error = ""
        self.state.next_check = time.time()

        # Wake the sync engine immediately instead of waiting for the old
        # interval. The manager lock prevents concurrent sync operations.
        if self._task and not self._task.done():
            asyncio.create_task(self.sync_once())

        self.log("RESUMED")

    async def _get_json(self, client: httpx.AsyncClient, url: str, **kwargs: Any) -> dict[str, Any]:
        response = await client.get(url, **kwargs)
        response.raise_for_status()
        return response.json()

    async def _chaster(self, client: httpx.AsyncClient, token: str, lock_id: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        return await self._get_json(client, f"{CHASTER_BASE}/locks/{lock_id}", headers=headers)

    @staticmethod
    def _remaining_chaster(lock: dict[str, Any]) -> int:
        now = time.time()
        for key in ("endDate", "enddate", "endAt", "endDateTimestamp"):
            value = lock.get(key)
            if value is not None:
                if isinstance(value, (int, float)):
                    ts = value / 1000 if value > 10_000_000_000 else value
                else:
                    from datetime import datetime
                    ts = datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
                return max(0, int(ts - now))
        session = lock.get("session") or {}
        for key in ("endDate", "enddate", "endAt"):
            value = session.get(key)
            if value is not None:
                if isinstance(value, (int, float)):
                    ts = value / 1000 if value > 10_000_000_000 else value
                else:
                    from datetime import datetime
                    ts = datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
                return max(0, int(ts - now))
        for key in ("remainingTime", "remainingSeconds", "timeRemaining"):
            if lock.get(key) is not None:
                return max(0, int(lock[key]))
        raise SyncError("Could not find Chaster remaining time in API response")

    async def _emlalock(self, client: httpx.AsyncClient, s: dict[str, str]) -> dict[str, Any]:
        params = {"userid": s["emlalock_user_id"], "apikey": s["emlalock_api_key"]}
        return await self._get_json(client, f"{EMLALOCK_BASE}/info", params=params)

    @staticmethod
    def _remaining_emlalock(data: dict[str, Any]) -> int:
        session = data.get("chastitysession") or {}
        end = session.get("enddate")
        if end is not None:
            ts = float(end)
            if ts > 10_000_000_000:
                ts /= 1000
            return max(0, int(ts - time.time()))
        for key in ("remainingtime", "remainingseconds", "timeleft"):
            if session.get(key) is not None:
                return max(0, int(session[key]))
        raise SyncError("Could not find EmlaLock remaining time in API response")

    async def _chaster_delta(self, client: httpx.AsyncClient, s: dict[str, str], delta: int) -> None:
        token = s.get("chaster_token", "").strip()
        if delta < 0:
            token = s.get("chaster_keyholder_token", "").strip() or token
            if not s.get("chaster_keyholder_token", "").strip():
                raise SyncError("Chaster remove-time requires the account performing the request to have the lock's 'Remove time' permission. If the bot is acting as the keyholder, add a Chaster keyholder access token with the 'keyholder' scope in Setup.")
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json"}
        url = f"{CHASTER_BASE}/locks/{s['chaster_lock_id']}/update-time"
        response = await client.post(url, headers=headers, json={"duration": delta})
        if response.status_code == 404:
            action_name = "add_time" if delta >= 0 else "remove_time"
            action_url = f"{CHASTER_BASE}/locks/{s['chaster_lock_id']}/action"
            action_response = await client.post(action_url, headers=headers, json={"action": {"name": action_name, "params": abs(delta)}})
            if action_response.status_code != 404:
                response = action_response
            else:
                raise SyncError("Chaster rejected the time-change route with 404 Not Found. The installed Public API does not expose either the legacy update-time route or the action route for this token/lock. Refresh the Chaster developer token and verify the lock's Add time/Remove time permission.")
        if response.status_code == 403:
            detail = ""
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    detail = str(payload.get("message") or payload.get("error") or payload.get("detail") or "").strip()
            except Exception:
                detail = response.text.strip()
            suffix = f" Chaster said: {detail}" if detail else ""
            if delta >= 0:
                requirement = "the account's Chaster 'locks' scope and the lock's 'Add time' permission"
            else:
                requirement = "the account's Chaster 'keyholder' scope (when acting as keyholder) and the lock's 'Remove time' permission"
            raise SyncError(f"Chaster rejected the time change (403 Forbidden). Required: {requirement}." + suffix)
        response.raise_for_status()

    async def _emlalock_delta(self, client: httpx.AsyncClient, s: dict[str, str], delta: int) -> None:
        params = {"userid": s["emlalock_user_id"], "apikey": s["emlalock_api_key"], "value": str(abs(delta)), "text": "c-ebot sync"}
        if delta >= 0:
            endpoint = "add"
        else:
            endpoint = "sub"
            params["holderapikey"] = s["emlalock_keyholder_api_key"]
        response = await client.get(f"{EMLALOCK_BASE}/{endpoint}", params=params)
        response.raise_for_status()

    async def read_timers(self) -> tuple[int, int]:
        s = load_secrets()
        if not s:
            raise SyncError("Credentials are not configured")
        lock_id = s.get("chaster_lock_id", "").strip()
        if not lock_id:
            raise SyncError("Chaster lock ID is not configured")
        async with httpx.AsyncClient(timeout=20) as client:
            c = await self._chaster(client, s["chaster_token"], lock_id)
            e = await self._emlalock(client, s)
        return self._remaining_chaster(c), self._remaining_emlalock(e)

    async def sync_once(self) -> None:
        async with self._lock:
            self.state.status = "SYNCING"
            self.state.message = "Reading both timers"
            print("[c-ebot] Checking Chaster and EmlaLock timers...", flush=True)

            # Always base the decision on a fresh read of BOTH timers.
            # Never keep adding the original delta: after every change we
            # re-read both sides and decide again which one is actually behind.
            c, e = await self.read_timers()
            self.state.chaster_seconds, self.state.emlalock_seconds = c, e
            self.state.last_check = time.time()

            tolerance = 2
            max_corrections = 3

            for attempt in range(max_corrections + 1):
                diff = c - e
                print(
                    f"[c-ebot] Timers: Chaster={format_duration(c)} | "
                    f"EmlaLock={format_duration(e)} | difference={format_duration(abs(diff))}",
                    flush=True,
                )

                if abs(diff) <= tolerance:
                    self.state.target_seconds = max(c, e)
                    self.state.status = "SYNCED"
                    self.state.message = "Timers synchronized"
                    self._save()
                    if attempt:
                        print(
                            f"[c-ebot] VERIFIED after {attempt} correction(s): "
                            f"Chaster={format_duration(c)} | EmlaLock={format_duration(e)}",
                            flush=True,
                        )
                    else:
                        print("[c-ebot] OK: timers are synchronized.", flush=True)
                    return

                if attempt == max_corrections:
                    raise SyncError(
                        f"Could not synchronize after {max_corrections} corrections: "
                        f"Chaster={format_duration(c)}, EmlaLock={format_duration(e)}"
                    )

                s = load_secrets()
                if c < e:
                    # EmlaLock has more time, so bring Chaster up to the
                    # CURRENT EmlaLock value. The next read determines whether
                    # that was enough; do not reuse this delta on another pass.
                    delta = e - c
                    lower = "Chaster"
                    self.state.message = f"Adjusting Chaster by {format_duration(delta)}"
                    print(
                        f"[c-ebot] Chaster is behind by {format_duration(delta)}; "
                        "adjusting it, then re-checking both timers.",
                        flush=True,
                    )
                    async with httpx.AsyncClient(timeout=20) as client:
                        await self._chaster_delta(client, s, delta)
                else:
                    # Chaster has more time, so bring EmlaLock up to the
                    # CURRENT Chaster value. This can subtract as well as add
                    # depending on the sign of the correction.
                    delta = c - e
                    lower = "EmlaLock"
                    self.state.message = f"Adjusting EmlaLock by {format_duration(delta)}"
                    print(
                        f"[c-ebot] EmlaLock is behind by {format_duration(delta)}; "
                        "adjusting it, then re-checking both timers.",
                        flush=True,
                    )
                    async with httpx.AsyncClient(timeout=20) as client:
                        await self._emlalock_delta(client, s, delta)

                # Critical: fetch BOTH APIs again after every adjustment.
                # The live timers continue counting down while the request is
                # in flight, so the next correction must use the new values.
                print("[c-ebot] Change sent. Re-reading both timers...", flush=True)
                c, e = await self.read_timers()
                self.state.chaster_seconds, self.state.emlalock_seconds = c, e
                self.state.last_check = time.time()

                self.log(
                    "AUTO_SYNC_CORRECTION",
                    f"{lower} adjusted; rechecked Chaster={format_duration(c)}, "
                    f"EmlaLock={format_duration(e)}",
                )

    async def manual_delta(self, delta: int, actor: str = "dashboard") -> None:
        if delta == 0:
            raise SyncError("Time adjustment must not be zero")
        async with self._lock:
            s = load_secrets()
            lock_id = s.get("chaster_lock_id", "").strip()
            if not lock_id:
                raise SyncError("Chaster lock ID is not configured")
            direction = "add" if delta > 0 else "subtract"
            print(f"[c-ebot] MANUAL {direction}: changing both timers by {format_duration(abs(delta))}", flush=True)
            self.state.message = f"Manual {direction} {format_duration(abs(delta))}"
            async with httpx.AsyncClient(timeout=20) as client:
                await self._chaster_delta(client, s, delta)
                await self._emlalock_delta(client, s, delta)
            print("[c-ebot] Manual change sent. Verifying both timers...", flush=True)
            c, e = await self.read_timers()
            self.state.chaster_seconds, self.state.emlalock_seconds = c, e
            if abs(c - e) > 2:
                raise SyncError(f"Manual verification failed: Chaster={format_duration(c)}, EmlaLock={format_duration(e)}")
            self.state.target_seconds = max(c, e)
            self.state.status = "SYNCED"
            self.state.message = "Manual change applied and verified"
            print(f"[c-ebot] VERIFIED manual change: Chaster={format_duration(c)} | EmlaLock={format_duration(e)}", flush=True)
            self.log("MANUAL_ADD" if delta > 0 else "MANUAL_SUBTRACT", f"{format_duration(abs(delta))} by {actor}; verified Chaster={format_duration(c)}, EmlaLock={format_duration(e)}")
            self._save()


manager = SyncManager()
