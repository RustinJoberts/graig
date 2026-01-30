from datetime import datetime, timedelta, timezone
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from config import settings
from db import (
    end_voice_session,
    get_first_activity,
    get_guild_leaderboards,
    get_message_stats,
    get_reaction_stats,
    get_voice_stats,
    init_db,
    record_message,
    record_reaction,
    start_voice_session,
    upsert_user,
)
from meme import build_meme_url, get_meme_templates, get_random_meme, search_templates
from utils import extract_emojis, format_duration

intents = discord.Intents.default()
intents.voice_states = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    await init_db()
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")


@bot.tree.command(name="stats", description="View your activity stats in this server")
@app_commands.guild_only()
@app_commands.describe(user="User to view stats for (defaults to yourself)")
async def stats(interaction: discord.Interaction, user: discord.Member | None = None):
    """Display activity statistics for a user."""
    if not interaction.guild_id:
        await interaction.response.send_message(
            "This command can only be used in a server.", ephemeral=True
        )
        return

    target = user or interaction.user
    guild_id = str(interaction.guild_id)
    user_id = str(target.id)
    guild_name = interaction.guild.name if interaction.guild else "this server"

    # Fetch all stats
    voice = await get_voice_stats(user_id, guild_id)
    messages = await get_message_stats(user_id, guild_id)
    reactions = await get_reaction_stats(user_id, guild_id)
    first_activity = await get_first_activity(user_id, guild_id)

    # Build embed
    embed = discord.Embed(
        title=f"Stats for {target.display_name}",
        description=f"Activity in **{guild_name}**",
        color=discord.Color.blurple(),
    )

    if target.avatar:
        embed.set_thumbnail(url=target.avatar.url)

    # Voice section
    voice_value = (
        f"**{format_duration(voice['total_seconds'])}** total\n"
        f"**{voice['session_count']}** sessions"
    )
    if voice["favorite_channel"]:
        voice_value += f"\n**Favorite:** {voice['favorite_channel']}"
    embed.add_field(name="🎤 Voice", value=voice_value, inline=True)

    # Messages section
    msg_value = (
        f"**{messages['message_count']:,}** sent\n"
        f"**{messages['total_emojis']:,}** emojis used"
    )
    if messages["top_emoji"]:
        msg_value += f"\n**Top:** {messages['top_emoji']} ({messages['top_emoji_count']}x)"
    embed.add_field(name="💬 Messages", value=msg_value, inline=True)

    # Reactions section
    react_value = (
        f"**{reactions['add_count']:,}** given\n"
        f"**{reactions['remove_count']:,}** removed"
    )
    if reactions["top_reaction"]:
        react_value += f"\n**Favorite:** {reactions['top_reaction']} ({reactions['top_reaction_count']}x)"
    embed.add_field(name="⭐ Reactions", value=react_value, inline=True)

    # Footer with tracking start date
    if first_activity:
        embed.set_footer(text=f"Tracking since {first_activity.strftime('%b %d, %Y')}")
    else:
        embed.set_footer(text="No activity recorded yet")

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="leaderboard", description="View server activity leaderboards")
@app_commands.describe(
    period="Time period to show stats for (default: 7d)",
    start_date="Custom start date (YYYY-MM-DD format)",
    end_date="Custom end date (YYYY-MM-DD format)",
    guild_id="Guild ID (required for DM usage by admins)",
)
async def leaderboard(
    interaction: discord.Interaction,
    period: Literal["1d", "7d", "30d", "all"] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    guild_id: str | None = None,
):
    """Display activity leaderboards for the server."""
    user_id = str(interaction.user.id)
    is_admin = user_id in settings.admin_ids

    # Handle DM vs guild context
    if interaction.guild_id:
        # In a guild - use guild context (ignore guild_id param)
        target_guild_id = str(interaction.guild_id)
        guild_name = interaction.guild.name if interaction.guild else "this server"
    elif is_admin and guild_id:
        # Admin in DM with guild_id specified
        target_guild_id = guild_id
        # Try to get guild name from bot's cache
        guild_obj = bot.get_guild(int(guild_id))
        guild_name = guild_obj.name if guild_obj else f"Guild {guild_id}"
    elif is_admin:
        await interaction.response.send_message(
            "Please provide a `guild_id` when using this command in DMs.",
            ephemeral=True,
        )
        return
    else:
        await interaction.response.send_message(
            "This command can only be used in a server.", ephemeral=True
        )
        return

    now = datetime.now(timezone.utc)

    # Parse custom date range or use preset period
    start_dt: datetime | None = None
    end_dt: datetime | None = None
    period_label = ""

    if start_date or end_date:
        # Custom date range
        try:
            if start_date:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
            if end_date:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59, tzinfo=timezone.utc
                )
        except ValueError:
            await interaction.response.send_message(
                "Invalid date format. Please use YYYY-MM-DD.", ephemeral=True
            )
            return

        if start_dt and end_dt:
            period_label = f"{start_dt.strftime('%b %d')} - {end_dt.strftime('%b %d, %Y')}"
        elif start_dt:
            period_label = f"Since {start_dt.strftime('%b %d, %Y')}"
        else:
            period_label = f"Until {end_dt.strftime('%b %d, %Y')}"
    else:
        # Use preset period (default to 7d)
        selected_period = period or "7d"
        if selected_period == "1d":
            start_dt = now - timedelta(days=1)
            period_label = "Last 24 Hours"
        elif selected_period == "7d":
            start_dt = now - timedelta(days=7)
            period_label = "Last 7 Days"
        elif selected_period == "30d":
            start_dt = now - timedelta(days=30)
            period_label = "Last 30 Days"
        else:  # all
            period_label = "All Time"

    # Fetch leaderboard data
    await interaction.response.defer()
    data = await get_guild_leaderboards(target_guild_id, start_dt, end_dt)

    # Check if there's any data
    has_data = any([data["voice_time"], data["messages"], data["emojis"], data["reactions"]])

    if not has_data:
        await interaction.followup.send(
            f"No activity data found for **{guild_name}** in the selected time period.",
            ephemeral=True,
        )
        return

    # Build embed
    embed = discord.Embed(
        title=f"Server Leaderboard ({period_label})",
        description=f"Top activity in **{guild_name}**",
        color=discord.Color.gold(),
    )

    # Voice time section
    if data["voice_time"]:
        voice_lines = []
        for i, (user_id, username, total_seconds) in enumerate(data["voice_time"], 1):
            voice_lines.append(f"{i}. <@{user_id}> — {format_duration(total_seconds)}")
        embed.add_field(name="🎤 Voice Time", value="\n".join(voice_lines), inline=False)

    # Messages section
    if data["messages"]:
        msg_lines = []
        for i, (user_id, username, count) in enumerate(data["messages"], 1):
            msg_lines.append(f"{i}. <@{user_id}> — {count:,}")
        embed.add_field(name="💬 Messages Sent", value="\n".join(msg_lines), inline=False)

    # Emojis section
    if data["emojis"]:
        emoji_lines = []
        for i, (user_id, username, count) in enumerate(data["emojis"], 1):
            emoji_lines.append(f"{i}. <@{user_id}> — {count:,}")
        embed.add_field(name="😀 Emojis Used", value="\n".join(emoji_lines), inline=False)

    # Reactions section
    if data["reactions"]:
        react_lines = []
        for i, (user_id, username, count) in enumerate(data["reactions"], 1):
            react_lines.append(f"{i}. <@{user_id}> — {count:,}")
        embed.add_field(name="⭐ Reactions Given", value="\n".join(react_lines), inline=False)

    # Footer with date range
    if start_dt and end_dt:
        footer_text = f"Data from {start_dt.strftime('%b %d')} - {end_dt.strftime('%b %d, %Y')}"
    elif start_dt:
        footer_text = f"Data from {start_dt.strftime('%b %d, %Y')} - {now.strftime('%b %d, %Y')}"
    elif end_dt:
        footer_text = f"Data until {end_dt.strftime('%b %d, %Y')}"
    else:
        footer_text = "All recorded data"

    embed.set_footer(text=footer_text)

    await interaction.followup.send(embed=embed)


@bot.tree.command(name="meme", description="Generate a custom meme")
@app_commands.describe(
    template="The meme template to use (e.g., drake, distracted-boyfriend)",
    top_text="Text for the top of the meme",
    bottom_text="Text for the bottom of the meme (optional)",
)
async def meme(
    interaction: discord.Interaction,
    template: str,
    top_text: str,
    bottom_text: str = "",
):
    """Generate a custom meme using Memegen."""
    meme_url = build_meme_url(template, top_text, bottom_text)

    embed = discord.Embed(color=discord.Color.green())
    embed.set_image(url=meme_url)
    embed.set_footer(text=f"Template: {template}")

    await interaction.response.send_message(embed=embed)


@meme.autocomplete("template")
async def meme_template_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Autocomplete for meme template names."""
    if current:
        templates = await search_templates(current)
    else:
        templates = await get_meme_templates()

    # Return up to 25 choices (Discord limit)
    return [
        app_commands.Choice(name=t["name"][:100], value=t["id"])
        for t in templates[:25]
    ]


@bot.tree.command(name="randommeme", description="Get a random meme from Reddit")
@app_commands.describe(subreddit="Subreddit to fetch from (optional)")
async def randommeme(
    interaction: discord.Interaction,
    subreddit: Literal["memes", "dankmemes", "me_irl", "wholesomememes"] | None = None,
):
    """Fetch a random meme from Reddit via Meme API."""
    await interaction.response.defer()

    meme_data = await get_random_meme(subreddit)

    if not meme_data:
        await interaction.followup.send(
            "Failed to fetch a meme. Please try again later.", ephemeral=True
        )
        return

    embed = discord.Embed(
        title=meme_data.get("title", "Random Meme"),
        url=meme_data.get("postLink"),
        color=discord.Color.orange(),
    )
    embed.set_image(url=meme_data.get("url"))
    embed.set_footer(
        text=f"r/{meme_data.get('subreddit')} | u/{meme_data.get('author')}"
    )

    await interaction.followup.send(embed=embed)


@bot.tree.command(name="memetemplates", description="List available meme templates")
@app_commands.describe(search="Search for templates by name (optional)")
async def memetemplates(interaction: discord.Interaction, search: str | None = None):
    """List or search available meme templates."""
    await interaction.response.defer()

    if search:
        templates = await search_templates(search)
    else:
        templates = await get_meme_templates()

    if not templates:
        await interaction.followup.send(
            "No templates found." if search else "Failed to fetch templates.",
            ephemeral=True,
        )
        return

    # Format templates list (show first 20)
    template_list = "\n".join(
        f"**{t['name']}** (`{t['id']}`)" for t in templates[:20]
    )

    total = len(templates)
    shown = min(20, total)

    embed = discord.Embed(
        title="Meme Templates" + (f" matching '{search}'" if search else ""),
        description=template_list,
        color=discord.Color.blue(),
    )
    embed.set_footer(text=f"Showing {shown} of {total} templates")

    await interaction.followup.send(embed=embed)


@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
):
    user_id = str(member.id)
    guild_id = str(member.guild.id)

    # Update user's current username
    await upsert_user(user_id, member.display_name)

    # User joined a voice channel
    if before.channel is None and after.channel is not None:
        print(f"{member.display_name} joined {after.channel.name}")
        await start_voice_session(
            user_id, guild_id, str(after.channel.id), after.channel.name
        )

    # User left a voice channel
    elif before.channel is not None and after.channel is None:
        print(f"{member.display_name} left {before.channel.name}")
        await end_voice_session(user_id, guild_id)

    # User switched channels
    elif (
        before.channel is not None
        and after.channel is not None
        and before.channel.id != after.channel.id
    ):
        print(f"{member.display_name} moved from {before.channel.name} to {after.channel.name}")
        await end_voice_session(user_id, guild_id)
        await start_voice_session(
            user_id, guild_id, str(after.channel.id), after.channel.name
        )


@bot.event
async def on_message(message: discord.Message):
    # Ignore bot messages and DMs
    if message.author.bot or message.guild is None:
        return

    user_id = str(message.author.id)
    guild_id = str(message.guild.id)

    # Update user's current username
    await upsert_user(user_id, message.author.display_name)

    # Extract emojis from message content
    emojis = extract_emojis(message.content)

    # Record the message
    await record_message(
        user_id,
        guild_id,
        str(message.channel.id),
        str(message.id),
        emojis,
    )

    # Process commands
    await bot.process_commands(message)


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    # Ignore DMs
    if payload.guild_id is None:
        return

    user_id = str(payload.user_id)
    guild_id = str(payload.guild_id)
    emoji_str = str(payload.emoji)

    # Update user's username if member info is available
    if payload.member:
        await upsert_user(user_id, payload.member.display_name)

    await record_reaction(
        user_id,
        guild_id,
        str(payload.channel_id),
        str(payload.message_id),
        emoji_str,
        "add",
    )


@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    # Ignore DMs
    if payload.guild_id is None:
        return

    user_id = str(payload.user_id)
    guild_id = str(payload.guild_id)
    emoji_str = str(payload.emoji)

    await record_reaction(
        user_id,
        guild_id,
        str(payload.channel_id),
        str(payload.message_id),
        emoji_str,
        "remove",
    )


bot.run(settings.discord_token)
