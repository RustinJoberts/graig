from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from config import settings
from db import (
    end_voice_session,
    get_first_activity,
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
