from __future__ import annotations

import asyncio
from typing import Optional

import discord
from discord import app_commands

from .secrets import load_secrets
from .sync_engine import manager, set_event_callback


def _admin_ids() -> set[int]:
    raw = load_secrets().get("discord_admin_user_ids", "")
    ids: set[int] = set()
    for value in raw.split(","):
        value = value.strip()
        if value.isdigit():
            ids.add(int(value))
    return ids


class CEBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.ready_once = False

    async def setup_hook(self) -> None:
        settings = load_secrets()
        guild_id = settings.get("discord_guild_id", "").strip()
        if guild_id.isdigit():
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self) -> None:
        if self.ready_once:
            return
        self.ready_once = True
        manager.log("DISCORD_CONNECTED", f"Logged in as {self.user}")


client = CEBot()


def is_admin(interaction: discord.Interaction) -> bool:
    if interaction.user.id in _admin_ids():
        return True
    permissions = getattr(interaction.user, "guild_permissions", None)
    return bool(permissions and permissions.administrator)


async def deny(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        "You are not authorized to control c-ebot. You need the Discord Administrator permission or your User ID must be listed under Admin User IDs.",
        ephemeral=True,
    )


def seconds_from(amount: int, unit: str) -> int:
    multipliers = {
        "seconds": 1,
        "minutes": 60,
        "hours": 3600,
        "days": 86400,
        "months": 30 * 86400,
        "years": 365 * 86400,
    }
    if amount <= 0 or unit not in multipliers:
        raise ValueError("Enter a positive amount and a valid time unit.")
    return amount * multipliers[unit]


@client.tree.command(name="status", description="Show c-ebot sync status")
async def status(interaction: discord.Interaction) -> None:
    s = manager.state
    await interaction.response.send_message(
        f"**c-ebot:** {s.status}\n"
        f"Chaster: `{s.chaster_seconds}s`\n"
        f"EmlaLock: `{s.emlalock_seconds}s`\n"
        f"Target: `{s.target_seconds}s`\n"
        f"Message: {s.message}"
    )


@client.tree.command(name="sync", description="Run a synchronization check now")
async def sync_command(interaction: discord.Interaction) -> None:
    if not is_admin(interaction):
        return await deny(interaction)
    await interaction.response.defer(ephemeral=True)
    try:
        await manager.sync_once()
        await interaction.followup.send("Synchronization completed.", ephemeral=True)
    except Exception as exc:
        manager.pause(f"Discord sync failed: {exc}")
        await interaction.followup.send(f"Sync failed: {exc}", ephemeral=True)
        await send_alert(f"⚠️ c-ebot sync failed: {exc}")


async def adjust_command(interaction: discord.Interaction, amount: int, unit: str, direction: str) -> None:
    if not is_admin(interaction):
        return await deny(interaction)
    await interaction.response.defer(ephemeral=True)
    try:
        delta = seconds_from(amount, unit)
        if direction == "subtract":
            delta = -delta
        await manager.manual_delta(delta, actor=f"discord:{interaction.user.id}")
        await interaction.followup.send("Time change applied and verified.", ephemeral=True)
    except Exception as exc:
        manager.pause(f"Discord manual change failed: {exc}")
        await interaction.followup.send(f"Change failed: {exc}", ephemeral=True)
        await send_alert(f"⚠️ c-ebot manual change failed: {exc}")


@client.tree.command(name="addtime", description="Add time to both timers")
@app_commands.describe(amount="Amount", unit="Time unit")
@app_commands.choices(unit=[app_commands.Choice(name=x.title(), value=x) for x in ("seconds", "minutes", "hours", "days", "months", "years")])
async def addtime(interaction: discord.Interaction, amount: int, unit: app_commands.Choice[str]) -> None:
    await adjust_command(interaction, amount, unit.value, "add")


@client.tree.command(name="subtracttime", description="Subtract time from both timers")
@app_commands.describe(amount="Amount", unit="Time unit")
@app_commands.choices(unit=[app_commands.Choice(name=x.title(), value=x) for x in ("seconds", "minutes", "hours", "days", "months", "years")])
async def subtracttime(interaction: discord.Interaction, amount: int, unit: app_commands.Choice[str]) -> None:
    await adjust_command(interaction, amount, unit.value, "subtract")


@client.tree.command(name="logs", description="Show recent c-ebot activity")
async def logs(interaction: discord.Interaction) -> None:
    if not is_admin(interaction):
        return await deny(interaction)
    rows = manager.state.history or []
    if not rows:
        return await interaction.response.send_message("No activity recorded.", ephemeral=True)
    text = "\n".join(f"• {x.get('action')}: {x.get('detail', '')}" for x in rows[:10])
    await interaction.response.send_message(text[:1900], ephemeral=True)


async def send_alert(message: str) -> None:
    settings = load_secrets()
    channel_id = settings.get("discord_channel_id", "").strip()
    if not channel_id.isdigit() or not client.is_ready():
        return
    channel = client.get_channel(int(channel_id))
    if channel is None:
        try:
            channel = await client.fetch_channel(int(channel_id))
        except Exception:
            return
    if hasattr(channel, "send"):
        try:
            await channel.send(message)
        except Exception:
            pass


async def discord_activity(action: str, detail: str) -> None:
    if action == "AUTO_SYNC":
        message = f"🔄 **Automatic sync**\n{detail}"
    elif action == "MANUAL_ADD":
        message = f"➕ **Time added**\n{detail}"
    elif action == "MANUAL_SUBTRACT":
        message = f"➖ **Time removed**\n{detail}"
    elif action == "PAUSED":
        message = f"🛑 **Automatic sync paused**\n{detail}"
    elif action == "RESUMED":
        message = "▶️ **Automatic sync resumed**"
    elif action == "DISCORD_CONNECTED":
        message = f"🤖 **c-ebot online**\n{detail}"
    else:
        message = f"ℹ️ **c-ebot: {action}**\n{detail}" if detail else f"ℹ️ **c-ebot: {action}**"
    await send_alert(message)


_bot_task: Optional[asyncio.Task] = None


async def start_discord() -> None:
    global _bot_task
    settings = load_secrets()
    token = settings.get("discord_bot_token", "").strip()
    if not token:
        print("[c-ebot] Discord is not configured; continuing without Discord.", flush=True)
        return
    if _bot_task and not _bot_task.done():
        return
    set_event_callback(discord_activity)
    async def runner() -> None:
        try:
            await client.start(token)
        except Exception as exc:
            print(f"[c-ebot] Discord bot stopped: {exc}", flush=True)
            await send_alert(f"🔴 **c-ebot Discord bot stopped**\n{exc}")
    _bot_task = asyncio.create_task(runner())


async def stop_discord() -> None:
    global _bot_task
    if _bot_task and not _bot_task.done():
        await client.close()
        _bot_task.cancel()
    set_event_callback(None)
    _bot_task = None
