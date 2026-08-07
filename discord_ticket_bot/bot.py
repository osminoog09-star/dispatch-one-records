"""Discord bridge for LAPD Records support tickets.

Runs as a small server-side bot. Do not put tokens into the repository:
copy .env.example to .env and keep real values local.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import discord
from discord.ext import commands, tasks


ROOT = Path(__file__).resolve().parent


def load_dotenv(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv()


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_int(name: str, default: int = 0) -> int:
    value = env(name)
    return int(value) if value.isdigit() else default


def env_ids(name: str) -> set[int]:
    out: set[int] = set()
    for part in env(name).split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


DISCORD_TOKEN = env("DISCORD_BOT_TOKEN")
GUILD_ID = env_int("DISCORD_GUILD_ID")
TICKET_CATEGORY_ID = env_int("DISCORD_TICKET_CATEGORY_ID")
SUPPORT_PANEL_CHANNEL_ID = env_int("DISCORD_SUPPORT_PANEL_CHANNEL_ID")
SUPPORT_ROLE_IDS = env_ids("DISCORD_SUPPORT_ROLE_IDS")
SUPABASE_URL = env("SUPABASE_URL").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = env("SUPABASE_SERVICE_ROLE_KEY")
SITE_BASE_URL = env("SITE_BASE_URL", "https://osminoog09-star.github.io/dispatch-one-records").rstrip("/")
POLL_SECONDS = env_int("POLL_SECONDS", 8)


def require_config() -> None:
    missing = [
        name for name, value in {
            "DISCORD_BOT_TOKEN": DISCORD_TOKEN,
            "DISCORD_GUILD_ID": GUILD_ID,
            "DISCORD_TICKET_CATEGORY_ID": TICKET_CATEGORY_ID,
            "SUPABASE_URL": SUPABASE_URL,
            "SUPABASE_SERVICE_ROLE_KEY": SUPABASE_SERVICE_ROLE_KEY,
        }.items()
        if not value
    ]
    if missing:
        raise SystemExit("Не заполнены переменные окружения: " + ", ".join(missing))


def clip(text: str, limit: int = 1800) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def slug(text: str, fallback: str = "player") -> str:
    text = (text or fallback).lower()
    text = re.sub(r"[^a-z0-9а-яё-]+", "-", text, flags=re.I)
    text = re.sub(r"-+", "-", text).strip("-")
    return (text or fallback)[:42]


def ticket_url(ticket_id: int) -> str:
    return f"{SITE_BASE_URL}/tickets/?ticket={ticket_id}"


class Supabase:
    def __init__(self, url: str, key: str) -> None:
        self.url = url.rstrip("/")
        self.key = key

    async def request(self, path: str, method: str = "GET", body: dict[str, Any] | None = None,
                      prefer: str | None = None) -> Any:
        return await asyncio.to_thread(self._request, path, method, body, prefer)

    def _request(self, path: str, method: str, body: dict[str, Any] | None,
                 prefer: str | None) -> Any:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(f"{self.url}/rest/v1/{path}", data=data, method=method)
        req.add_header("apikey", self.key)
        req.add_header("Authorization", "Bearer " + self.key)
        req.add_header("Content-Type", "application/json")
        if prefer:
            req.add_header("Prefer", prefer)
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase {method} {path}: {exc.code} {details}") from exc

    async def insert(self, table: str, payload: dict[str, Any]) -> dict[str, Any]:
        rows = await self.request(table, "POST", payload, "return=representation")
        return rows[0] if rows else {}

    async def patch(self, table: str, row_id: int, payload: dict[str, Any]) -> None:
        await self.request(f"{table}?id=eq.{row_id}", "PATCH", payload)

    async def find_ticket_by_channel(self, channel_id: int) -> dict[str, Any] | None:
        rows = await self.request(
            f"tickets?discord_channel_id=eq.{channel_id}&select=*&limit=1"
        )
        return rows[0] if rows else None

    async def pending_external_tickets(self) -> list[dict[str, Any]]:
        return await self.request(
            "tickets?status=neq.closed&discord_channel_id=is.null"
            "&select=*&order=created_at.asc&limit=10"
        ) or []

    async def pending_comments(self, ticket_id: int) -> list[dict[str, Any]]:
        return await self.request(
            f"ticket_comments?ticket_id=eq.{ticket_id}&discord_message_id=is.null"
            "&select=*&order=created_at.asc&limit=20"
        ) or []

    async def comment_exists(self, message_id: int) -> bool:
        rows = await self.request(
            f"ticket_comments?discord_message_id=eq.{message_id}&select=id&limit=1"
        )
        return bool(rows)


sb = Supabase(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


@dataclass
class TicketDraft:
    callsign: str
    title: str
    body: str


intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


def is_support(member: discord.Member) -> bool:
    if member.guild_permissions.manage_channels or member.guild_permissions.administrator:
        return True
    return bool({role.id for role in member.roles} & SUPPORT_ROLE_IDS)


async def ticket_category() -> discord.CategoryChannel:
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        raise RuntimeError("Discord guild not found")
    category = guild.get_channel(TICKET_CATEGORY_ID)
    if not isinstance(category, discord.CategoryChannel):
        raise RuntimeError("Ticket category not found")
    return category


async def create_ticket_channel(ticket: dict[str, Any], user: discord.Member | None = None) -> discord.TextChannel:
    category = await ticket_category()
    guild = category.guild
    overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
    }
    me = guild.me or (guild.get_member(bot.user.id) if bot.user else None)
    if me:
        overwrites[me] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True, manage_channels=True
        )
    for role_id in SUPPORT_ROLE_IDS:
        role = guild.get_role(role_id)
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )
    if user:
        overwrites[user] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True, attach_files=True
        )
    name_part = slug(ticket.get("callsign") or ticket.get("created_by") or ticket.get("source") or "player")
    channel = await guild.create_text_channel(
        f"ticket-{ticket['id']}-{name_part}",
        category=category,
        overwrites=overwrites,
        topic=f"LAPD Records ticket #{ticket['id']} · {ticket_url(ticket['id'])}",
        reason="LAPD Records support ticket",
    )
    await sb.patch("tickets", int(ticket["id"]), {"discord_channel_id": str(channel.id)})
    return channel


def ticket_embed(ticket: dict[str, Any]) -> discord.Embed:
    source = {"site": "Сайт", "launcher": "Лаунчер", "discord": "Discord"}.get(ticket.get("source"), "Сайт")
    embed = discord.Embed(
        title=f"Тикет #{ticket['id']} · {ticket.get('title') or 'Обращение'}",
        description=clip(ticket.get("body") or "Описание пока не указано.", 900),
        color=0x3B82F6,
    )
    embed.add_field(name="Источник", value=source, inline=True)
    embed.add_field(name="Позывной", value=ticket.get("callsign") or "—", inline=True)
    embed.add_field(name="Автор", value=ticket.get("created_by") or "—", inline=True)
    embed.add_field(name="Сайт", value=ticket_url(int(ticket["id"])), inline=False)
    embed.set_footer(text="Ответы из этого канала синхронизируются с LAPD Records")
    return embed


class TicketModal(discord.ui.Modal, title="Новое обращение LAPD"):
    callsign = discord.ui.TextInput(label="Позывной", placeholder="7-WILLIAM-1", required=False, max_length=40)
    title_text = discord.ui.TextInput(label="Тема", placeholder="Что случилось?", required=True, max_length=120)
    body = discord.ui.TextInput(
        label="Описание", placeholder="Опиши проблему, ошибку или вопрос", required=True,
        style=discord.TextStyle.paragraph, max_length=1500
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        ticket = await sb.insert("tickets", {
            "title": str(self.title_text).strip(),
            "body": str(self.body).strip(),
            "status": "open",
            "priority": "normal",
            "category": "support",
            "source": "discord",
            "callsign": str(self.callsign).strip(),
            "created_by": interaction.user.display_name,
            "author_discord_id": str(interaction.user.id),
        })
        channel = await create_ticket_channel(ticket, member)
        intro = await channel.send(
            content=(member.mention if member else None),
            embed=ticket_embed({**ticket, "discord_channel_id": str(channel.id)}),
        )
        await sb.patch("tickets", int(ticket["id"]), {
            "discord_channel_id": str(channel.id),
            "discord_message_id": str(intro.id),
        })
        await sb.insert("ticket_comments", {
            "ticket_id": ticket["id"],
            "client_id": ticket.get("client_id"),
            "author": interaction.user.display_name,
            "body": str(self.body).strip(),
            "source": "discord",
            "discord_message_id": f"modal:{interaction.id}",
        })
        await interaction.followup.send(f"Тикет создан: {channel.mention}", ephemeral=True)


class TicketPanel(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Создать тикет", style=discord.ButtonStyle.primary, custom_id="lapd:create_ticket")
    async def create_ticket(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        await interaction.response.send_modal(TicketModal())


async def send_panel(channel: discord.TextChannel) -> None:
    embed = discord.Embed(
        title="Поддержка LAPD Records",
        description=(
            "Нажми кнопку ниже, если лаунчер не запускается, записи не появились на сайте "
            "или нужна помощь администрации."
        ),
        color=0x2563EB,
    )
    embed.add_field(name="Лучше приложить", value="позывной, время проблемы, лог или скрин", inline=False)
    await channel.send(embed=embed, view=TicketPanel())


@bot.event
async def on_ready() -> None:
    bot.add_view(TicketPanel())
    if not sync_tickets.is_running():
        sync_tickets.change_interval(seconds=max(POLL_SECONDS, 3))
        sync_tickets.start()
    print(f"LAPD ticket bot online: {bot.user} ({bot.user.id if bot.user else 'no id'})")


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot or not message.guild:
        return
    await bot.process_commands(message)
    ticket = await sb.find_ticket_by_channel(message.channel.id)
    if not ticket:
        return
    if await sb.comment_exists(message.id):
        return
    attachments = "\n".join(a.url for a in message.attachments)
    body = message.content.strip()
    if attachments:
        body = (body + "\n\nВложения:\n" + attachments).strip()
    await sb.insert("ticket_comments", {
        "ticket_id": ticket["id"],
        "client_id": ticket.get("client_id"),
        "author": message.author.display_name,
        "body": body or "(вложение)",
        "source": "discord",
        "discord_message_id": str(message.id),
    })


@bot.command(name="ticket-panel")
async def ticket_panel_cmd(ctx: commands.Context) -> None:
    if not isinstance(ctx.author, discord.Member) or not is_support(ctx.author):
        return
    if SUPPORT_PANEL_CHANNEL_ID and ctx.channel.id != SUPPORT_PANEL_CHANNEL_ID:
        await ctx.reply("Панель тикетов нужно публиковать в настроенном канале поддержки.", mention_author=False)
        return
    await send_panel(ctx.channel)  # type: ignore[arg-type]
    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass


@bot.command(name="close")
async def close_ticket_cmd(ctx: commands.Context) -> None:
    if not isinstance(ctx.author, discord.Member) or not is_support(ctx.author):
        return
    ticket = await sb.find_ticket_by_channel(ctx.channel.id)
    if not ticket:
        return
    await sb.patch("tickets", int(ticket["id"]), {"status": "closed"})
    await ctx.send("Тикет закрыт. На сайте он тоже помечен как закрытый.")
    try:
        await ctx.channel.edit(name="closed-" + ctx.channel.name[:82])
    except discord.HTTPException:
        pass


@tasks.loop(seconds=8)
async def sync_tickets() -> None:
    try:
        await sync_external_tickets()
        await sync_pending_comments()
    except Exception as exc:
        print("sync_tickets:", exc, file=sys.stderr)


async def sync_external_tickets() -> None:
    for ticket in await sb.pending_external_tickets():
        channel = await create_ticket_channel(ticket)
        await channel.send(embed=ticket_embed(ticket))


async def sync_pending_comments() -> None:
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return
    rows = await sb.request(
        "tickets?status=neq.closed&discord_channel_id=not.is.null&select=id,discord_channel_id&limit=50"
    ) or []
    for ticket in rows:
        channel = guild.get_channel(int(ticket["discord_channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            continue
        for comment in await sb.pending_comments(int(ticket["id"])):
            if comment.get("source") == "discord":
                continue
            author = "Оператор" if comment.get("from_admin") else (comment.get("author") or "Игрок")
            body = clip(comment.get("body") or "(без текста)")
            msg = await channel.send(f"**{author}:**\n{body}")
            await sb.patch("ticket_comments", int(comment["id"]), {"discord_message_id": str(msg.id)})


if __name__ == "__main__":
    require_config()
    bot.run(DISCORD_TOKEN)
