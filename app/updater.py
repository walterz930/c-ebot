from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Any

import httpx

GITHUB_OWNER = "walterz930"
GITHUB_REPO = "c-ebot"
GITHUB_API = "https://api.github.com"


def install_root() -> Path:
    return Path(__file__).resolve().parent.parent


def commit_file() -> Path:
    return install_root() / ".cebot_commit"


def installed_commit() -> str:
    try:
        return commit_file().read_text(encoding="utf-8").strip()
    except Exception:
        return ""


async def latest_commit() -> dict[str, str]:
    url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/commits/main"
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10"}
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
    return {
        "sha": str(data.get("sha", "")),
        "message": str((data.get("commit") or {}).get("message", "")).splitlines()[0],
        "url": str(data.get("html_url", "")),
    }


def start_update_process(target_sha: str, parent_pid: int) -> None:
    root = install_root()
    script = root / "update-standalone.ps1"
    if not script.exists():
        raise RuntimeError("Windows updater is not installed. Run the latest Windows installer first.")
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-TargetSha", target_sha, "-ParentPid", str(parent_pid)],
        cwd=str(root),
        creationflags=creationflags,
        close_fds=True,
    )


async def check_update() -> dict[str, Any]:
    remote = await latest_commit()
    local = installed_commit()
    return {"current": local, "latest": remote["sha"], "message": remote["message"], "url": remote["url"], "available": bool(local and remote["sha"] != local), "initialized": not bool(local)}


async def request_update() -> dict[str, Any]:
    remote = await latest_commit()
    local = installed_commit()
    if local and remote["sha"] == local:
        return {"available": False, "current": local, "latest": remote["sha"], "message": remote["message"]}
    if not local:
        commit_file().write_text(remote["sha"], encoding="utf-8")
        return {"available": False, "initialized": True, "current": remote["sha"], "latest": remote["sha"], "message": remote["message"]}
    start_update_process(remote["sha"], os.getpid())
    return {"available": True, "current": local, "latest": remote["sha"], "message": remote["message"], "started": True}
