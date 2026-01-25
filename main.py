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
