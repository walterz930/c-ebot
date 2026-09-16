from __future__ import annotations

import asyncio
import os
import time
from typing import Optional

import discord
from discord import app_commands

from .secrets import load_secrets, save_secrets
from .sync_engine import manager, set_event_callback, format_duration
from .updater import request_update, installed_commit


class CEBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.ready_once = False

    async def setup_hook(self) -> None:
        commands = sorted(self.tree.get_commands(), key=lambda command: command.name.lower())
        settings = load_secrets()
        guild_id = settings.get("discord_guild_id", "").strip()
        self.tree.clear_commands(guild=None)
        await self.tree.sync()
        if guild_id.isdigit():
            guild = discord.Object(id=int(guild_id))
            self.tree.clear_commands(guild=guild)
            for command in commands:
                self.tree.add_command(command, guild=guild)
            await self.tree.sync(guild=guild)
        else:
            for command in commands:
                self.tree.add_command(command)
            await self.tree.sync()

    async def on_ready(self) -> None:
        if self.ready_once:
            return
        self.ready_once = True
        logged_in_as = str(self.user)
        manager.log("DISCORD_CONNECTED", f"Logged in as {logged_in_as}")
        await send_alert(f"🟢 **c-ebot online**\nLogged in as {logged_in_as}")


client = CEBot()


def is_admin(interaction: discord.Interaction) -> bool:
    permissions = getattr(interaction.user, "guild_permissions", None)
    return bool(permissions and permissions.administrator)


def discord_actor(interaction: discord.Interaction) -> str:
    return str(interaction.user.name)


async def deny(interaction: discord.Interaction) -> None:
    await interaction.response.send_message("You are not authorized to control c-ebot. You need the Discord Administrator permission.", ephemeral=True)


def seconds_from(amount: int, unit: str) -> int:
    multipliers = {"seconds": 1, "minutes": 60, "hours": 3600, "days": 86400, "months": 30 * 86400, "years": 365 * 86400}
    if amount <= 0 or unit not in multipliers:
        raise ValueError("Enter a positive amount and a valid time unit.")
    return amount * multipliers[unit]


def format_seconds(value: int | None) -> str:
    return format_duration(value)


async def run_manual(interaction: discord.Interaction, delta: int, actor: str) -> None:
    if not is_admin(interaction): return await deny(interaction)
    await interaction.response.defer(ephemeral=True)
    try:
        await manager.manual_delta(delta, actor=actor)
        direction = "added" if delta > 0 else "removed"
        await interaction.followup.send(f"Time {direction} `{format_duration(abs(delta))}` by {actor}; verified Chaster=`{format_duration(manager.state.chaster_seconds)}`, EmlaLock=`{format_duration(manager.state.emlalock_seconds)}`.", ephemeral=True)
    except Exception as exc:
        manager.pause(f"Discord manual change failed: {exc}")
        await interaction.followup.send(f"Change failed: {exc}", ephemeral=True)
        await send_alert(f"⚠️ c-ebot manual change failed: {exc}")


@client.tree.command(name="status", description="Show c-ebot sync status")
async def status(interaction: discord.Interaction) -> None:
    s = manager.state; next_check = f"<t:{int(s.next_check)}:R>" if s.next_check else "not scheduled"
    await interaction.response.send_message(f"**c-ebot:** {s.status}\nChaster: `{format_seconds(s.chaster_seconds)}`\nEmlaLock: `{format_seconds(s.emlalock_seconds)}`\nTarget: `{format_seconds(s.target_seconds)}`\nAuto Sync: `{'paused' if s.paused else 'enabled'}`\nNext check: {next_check}\nLast action: {s.last_action or 'none'}\nMessage: {s.message}")


@client.tree.command(name="sync", description="Run a synchronization check now")
async def sync_command(interaction: discord.Interaction) -> None:
    if not is_admin(interaction): return await deny(interaction)
    await interaction.response.defer(ephemeral=True)
    try:
        await manager.sync_once(); await interaction.followup.send("Synchronization completed.", ephemeral=True)
    except Exception as exc:
        manager.pause(f"Discord sync failed: {exc}"); await interaction.followup.send(f"Sync failed: {exc}", ephemeral=True); await send_alert(f"⚠️ c-ebot sync failed: {exc}")


async def adjust_command(interaction: discord.Interaction, amount: int, unit: str, direction: str) -> None:
    await run_manual(interaction, seconds_from(amount, unit) * (-1 if direction == "subtract" else 1), discord_actor(interaction))


@client.tree.command(name="addtime", description="Add time to both timers")
@app_commands.describe(amount="Amount", unit="Time unit")
@app_commands.choices(unit=[app_commands.Choice(name=x.title(), value=x) for x in ("seconds", "minutes", "hours", "days", "months", "years")])
async def addtime(interaction: discord.Interaction, amount: int, unit: app_commands.Choice[str]) -> None:
    try: await adjust_command(interaction, amount, unit.value, "add")
    except ValueError as exc: await interaction.response.send_message(str(exc), ephemeral=True)


@client.tree.command(name="subtracttime", description="Subtract time from both timers")
@app_commands.describe(amount="Amount", unit="Time unit")
@app_commands.choices(unit=[app_commands.Choice(name=x.title(), value=x) for x in ("seconds", "minutes", "hours", "days", "months", "years")])
async def subtracttime(interaction: discord.Interaction, amount: int, unit: app_commands.Choice[str]) -> None:
    try: await adjust_command(interaction, amount, unit.value, "subtract")
    except ValueError as exc: await interaction.response.send_message(str(exc), ephemeral=True)


@client.tree.command(name="setlockid", description="Change the Chaster Lock ID")
@app_commands.describe(lock_id="The new Chaster Lock ID")
async def setlockid(interaction: discord.Interaction, lock_id: str) -> None:
    if not is_admin(interaction): return await deny(interaction)
    new_lock_id = lock_id.strip()
    if not new_lock_id or len(new_lock_id) > 200 or any(ch.isspace() for ch in new_lock_id):
        return await interaction.response.send_message("Enter a valid Chaster Lock ID.", ephemeral=True)
    try:
        settings = load_secrets()
        if not settings.get("chaster_token"):
            return await interaction.response.send_message("Chaster is not configured yet.", ephemeral=True)
        old_lock_id = settings.get("chaster_lock_id", "").strip()
        settings["chaster_lock_id"] = new_lock_id
        save_secrets(settings)
        manager.log("CHASTER_LOCK_CHANGED", f"{old_lock_id or '(none)'} -> {new_lock_id} by {discord_actor(interaction)}")
        manager.state.message = f"Chaster Lock ID changed to {new_lock_id}"
        manager._save()
        await interaction.response.send_message(f"Chaster Lock ID changed to `{new_lock_id}`. Running a sync check now...", ephemeral=True)
        try:
            await manager.sync_once()
            await interaction.followup.send(f"Lock ID updated and sync completed. Chaster=`{format_duration(manager.state.chaster_seconds)}`, EmlaLock=`{format_duration(manager.state.emlalock_seconds)}`.", ephemeral=True)
        except Exception as exc:
            manager.pause(f"Sync after Chaster Lock ID change failed: {exc}")
            await interaction.followup.send(f"Lock ID was saved, but the new lock could not be synchronized: {exc}", ephemeral=True)
            await send_alert(f"⚠️ **Chaster Lock ID changed but sync failed**\n{exc}")
    except Exception as exc:
        await interaction.response.send_message(f"Could not change Chaster Lock ID: {exc}", ephemeral=True)


@client.tree.command(name="pause", description="Pause automatic timer synchronization")
async def pause_command(interaction: discord.Interaction) -> None:
    if not is_admin(interaction): return await deny(interaction)
    manager.pause(f"Paused by {discord_actor(interaction)}"); await interaction.response.send_message("Automatic synchronization is now paused.", ephemeral=True)


@client.tree.command(name="resume", description="Resume automatic timer synchronization")
async def resume_command(interaction: discord.Interaction) -> None:
    if not is_admin(interaction): return await deny(interaction)
    manager.resume(); manager.log("RESUMED_BY", discord_actor(interaction)); await interaction.response.send_message("Automatic synchronization has been resumed.", ephemeral=True)


@client.tree.command(name="emergency", description="Immediately pause automatic synchronization")
async def emergency(interaction: discord.Interaction) -> None:
    if not is_admin(interaction): return await deny(interaction)
    actor = discord_actor(interaction)
    manager.pause(f"Emergency stop by {actor}"); await interaction.response.send_message("🚨 Automatic synchronization has been stopped.", ephemeral=True); await send_alert(f"🚨 **c-ebot emergency stop**\nAutomatic synchronization was stopped by Discord user {actor}.")


@client.tree.command(name="health", description="Check c-ebot API and Discord health")
async def health(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    try: c, e = await manager.read_timers(); api = f"🟢 Chaster `{format_seconds(c)}`\n🟢 EmlaLock `{format_seconds(e)}`"
    except Exception as exc: api = f"🔴 API check failed: `{exc}`"
    await interaction.followup.send(f"**c-ebot health**\n{api}\nDiscord: {'🟢 connected' if client.is_ready() else '🔴 disconnected'}", ephemeral=True)


@client.tree.command(name="testdiscord", description="Test the Discord activity feed")
async def testdiscord(interaction: discord.Interaction) -> None:
    if not is_admin(interaction): return await deny(interaction)
    await interaction.response.send_message("Sending a Discord activity test...", ephemeral=True); await send_alert(f"🧪 **c-ebot Discord test**\nTest requested by Discord user {discord_actor(interaction)}.")


@client.tree.command(name="testchaster", description="Test the Chaster API connection")
async def testchaster(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    try: c, _ = await manager.read_timers(); await interaction.followup.send(f"🟢 Chaster connection OK. Remaining time: `{format_seconds(c)}`.", ephemeral=True)
    except Exception as exc: await interaction.followup.send(f"🔴 Chaster test failed: `{exc}`", ephemeral=True)


@client.tree.command(name="testemlalock", description="Test the EmlaLock API connection")
async def testemlalock(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    try: _, e = await manager.read_timers(); await interaction.followup.send(f"🟢 EmlaLock connection OK. Remaining time: `{format_seconds(e)}`.", ephemeral=True)
    except Exception as exc: await interaction.followup.send(f"🔴 EmlaLock test failed: `{exc}`", ephemeral=True)


@client.tree.command(name="history", description="Show recent c-ebot activity history")
async def history(interaction: discord.Interaction) -> None:
    rows = manager.state.history or []
    if not rows: return await interaction.response.send_message("No activity recorded.", ephemeral=True)
    await interaction.response.send_message("\n".join(f"• **{x.get('action', '')}** — {x.get('detail', '')}" for x in rows[:10])[:1900], ephemeral=True)


@client.tree.command(name="logs", description="Show recent c-ebot activity")
async def logs(interaction: discord.Interaction) -> None:
    if not is_admin(interaction): return await deny(interaction)
    rows = manager.state.history or []
    if not rows: return await interaction.response.send_message("No activity recorded.", ephemeral=True)
    await interaction.response.send_message("\n".join(f"• {x.get('action')}: {x.get('detail', '')}" for x in rows[:10])[:1900], ephemeral=True)


@client.tree.command(name="whoami", description="Show your Discord ID and c-ebot access level")
async def whoami(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(f"User: **{interaction.user}**\nDiscord User ID: `{interaction.user.id}`\nControl access: `{'authorized' if is_admin(interaction) else 'not authorized'}`", ephemeral=True)


@client.tree.command(name="permissions", description="Show who can control c-ebot")
async def permissions(interaction: discord.Interaction) -> None:
    await interaction.response.send_message("**c-ebot control permissions**\n• Discord server Administrators: `authorized`\n• Admin User IDs: `not used`\n• Timer-changing commands: admin-only\n• Lock ID changes: admin-only\n• Updates: admin-only", ephemeral=True)


@client.tree.command(name="nextsync", description="Show when the next automatic check is due")
async def nextsync(interaction: discord.Interaction) -> None:
    s = manager.state
    if not s.next_check: return await interaction.response.send_message("The next check is not scheduled yet.")
    remaining = max(0, int(s.next_check - time.time())); await interaction.response.send_message(f"Next automatic check: <t:{int(s.next_check)}:R> ({format_seconds(remaining)}).")


@client.tree.command(name="version", description="Show the installed c-ebot commit")
async def version(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(f"Installed commit: `{installed_commit() or 'not recorded'}`", ephemeral=True)


@client.tree.command(name="update", description="Check GitHub and update c-ebot")
async def update(interaction: discord.Interaction) -> None:
    if not is_admin(interaction): return await deny(interaction)
    await interaction.response.defer(ephemeral=True)
    try:
        result = await request_update()
        if result.get("initialized"):
            await interaction.followup.send("GitHub update tracking initialized. Run /update again when a newer commit is available.", ephemeral=True); return
        if not result.get("started"):
            await interaction.followup.send(f"✅ c-ebot is up to date at `{result['latest'][:12]}`.", ephemeral=True); return
        await send_alert(f"⬇️ **c-ebot update started**\nDownloading commit `{result['latest'][:12]}`. c-ebot will restart automatically.")
        await interaction.followup.send(f"Update `{result['latest'][:12]}` is downloading. c-ebot will restart automatically.", ephemeral=True)
        await asyncio.sleep(1); os._exit(0)
    except Exception as exc:
        await interaction.followup.send(f"Update failed: {exc}", ephemeral=True); await send_alert(f"⚠️ **c-ebot update failed**\n{exc}")


@client.tree.command(name="panel", description="Open the c-ebot Discord control panel")
async def panel(interaction: discord.Interaction) -> None:
    await interaction.response.send_message("**c-ebot Control Panel**\nUse the buttons below.", view=ControlPanel(), ephemeral=True)


class ControlPanel(discord.ui.View):
    def __init__(self, *, timeout=300): super().__init__(timeout=timeout)
    async def _guard(self, interaction: discord.Interaction) -> bool:
        if not is_admin(interaction): await deny(interaction); return False
        return True
    @discord.ui.button(label="Sync", emoji="🔄", style=discord.ButtonStyle.primary)
    async def sync_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._guard(interaction): return
        await interaction.response.defer(ephemeral=True)
        try: await manager.sync_once(); await interaction.followup.send("Synchronization completed.", ephemeral=True)
        except Exception as exc: manager.pause(f"Discord panel sync failed: {exc}"); await interaction.followup.send(f"Sync failed: {exc}", ephemeral=True)
    @discord.ui.button(label="Add 1h", emoji="➕", style=discord.ButtonStyle.success)
    async def add_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if await self._guard(interaction): await run_manual(interaction, 3600, discord_actor(interaction))
    @discord.ui.button(label="Remove 1h", emoji="➖", style=discord.ButtonStyle.danger)
    async def remove_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if await self._guard(interaction): await run_manual(interaction, -3600, discord_actor(interaction))
    @discord.ui.button(label="Pause", emoji="⏸️", style=discord.ButtonStyle.secondary)
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._guard(interaction): return
        manager.pause(f"Paused by {discord_actor(interaction)}"); await interaction.response.send_message("Automatic synchronization paused.", ephemeral=True)
    @discord.ui.button(label="Resume", emoji="▶️", style=discord.ButtonStyle.secondary)
    async def resume_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._guard(interaction): return
        manager.resume(); await interaction.response.send_message("Automatic synchronization resumed.", ephemeral=True)
    @discord.ui.button(label="Status", emoji="📊", style=discord.ButtonStyle.secondary, row=1)
    async def status_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        s = manager.state; await interaction.response.send_message(f"**{s.status}** — Chaster `{format_seconds(s.chaster_seconds)}`, EmlaLock `{format_seconds(s.emlalock_seconds)}`, Auto Sync `{ 'paused' if s.paused else 'enabled' }`.", ephemeral=True)


async def send_alert(message: str) -> None:
    settings = load_secrets(); channel_id = settings.get("discord_channel_id", "").strip()
    if not channel_id.isdigit() or not client.is_ready(): return
    channel = client.get_channel(int(channel_id))
    if channel is None:
        try: channel = await client.fetch_channel(int(channel_id))
        except Exception: return
    try: await channel.send(message)
    except Exception: pass


async def discord_event(action: str, detail: str) -> None:
    if action in {"MANUAL_ADD", "MANUAL_SUBTRACT", "PAUSED", "RESUMED_BY", "AUTO_SYNC", "SYNC_ERROR", "CHASTER_LOCK_CHANGED"}:
        await send_alert(f"**{action}**\n{detail}")


set_event_callback(discord_event)


def run_discord_bot() -> Optional[asyncio.Task]:
    token = load_secrets().get("discord_bot_token", "").strip()
    if not token: return None
    return asyncio.create_task(client.start(token))


async def start_discord() -> None:
    run_discord_bot()
