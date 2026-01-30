from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

from config import settings

client = AsyncIOMotorClient(settings.mongo_uri)
db = client.graig


async def init_db() -> None:
    """Create indexes for optimized queries."""
    # Voice sessions indexes
    await db.voice_sessions.create_index(
        [("user_id", 1), ("guild_id", 1), ("left_at", 1)]
    )
    await db.voice_sessions.create_index(
        [("user_id", 1), ("guild_id", 1), ("joined_at", -1)]
    )
    # Messages indexes
    await db.messages.create_index(
        [("user_id", 1), ("guild_id", 1), ("created_at", -1)]
    )
    # Reactions indexes
    await db.reactions.create_index(
        [("user_id", 1), ("guild_id", 1), ("created_at", -1)]
    )
    await db.reactions.create_index(
        [("user_id", 1), ("guild_id", 1), ("emoji", 1), ("action", 1)]
    )


async def upsert_user(user_id: str, username: str) -> None:
    """Update or create a user document with their current username."""
    await db.users.update_one(
        {"_id": user_id},
        {"$set": {"username": username, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


async def start_voice_session(
    user_id: str, guild_id: str, channel_id: str, channel_name: str
) -> None:
    """Record a user joining a voice channel."""
    await db.voice_sessions.insert_one(
        {
            "user_id": user_id,
            "guild_id": guild_id,
            "channel_id": channel_id,
            "channel_name": channel_name,
            "joined_at": datetime.now(timezone.utc),
            "left_at": None,
            "duration_seconds": None,
        }
    )


async def end_voice_session(user_id: str, guild_id: str) -> None:
    """Record a user leaving a voice channel and calculate duration."""
    now = datetime.now(timezone.utc)
    session = await db.voice_sessions.find_one(
        {"user_id": user_id, "guild_id": guild_id, "left_at": None},
        sort=[("joined_at", -1)],
    )
    if session:
        joined_at = session["joined_at"]
        if joined_at.tzinfo is None:
            joined_at = joined_at.replace(tzinfo=timezone.utc)
        duration = int((now - joined_at).total_seconds())
        await db.voice_sessions.update_one(
            {"_id": session["_id"]},
            {"$set": {"left_at": now, "duration_seconds": duration}},
        )


async def record_message(
    user_id: str,
    guild_id: str,
    channel_id: str,
    message_id: str,
    emojis: list[str],
) -> None:
    """Record a message sent by a user with any emojis used."""
    await db.messages.insert_one(
        {
            "user_id": user_id,
            "guild_id": guild_id,
            "channel_id": channel_id,
            "message_id": message_id,
            "emojis": emojis,
            "created_at": datetime.now(timezone.utc),
        }
    )


async def record_reaction(
    user_id: str,
    guild_id: str,
    channel_id: str,
    message_id: str,
    emoji: str,
    action: str,
) -> None:
    """Record a reaction add or remove event."""
    await db.reactions.insert_one(
        {
            "user_id": user_id,
            "guild_id": guild_id,
            "channel_id": channel_id,
            "message_id": message_id,
            "emoji": emoji,
            "action": action,
            "created_at": datetime.now(timezone.utc),
        }
    )


async def get_voice_stats(user_id: str, guild_id: str) -> dict:
    """Get voice statistics for a user in a guild."""
    pipeline = [
        {"$match": {"user_id": user_id, "guild_id": guild_id, "duration_seconds": {"$ne": None}}},
        {
            "$group": {
                "_id": None,
                "total_seconds": {"$sum": "$duration_seconds"},
                "session_count": {"$sum": 1},
            }
        },
    ]
    result = await db.voice_sessions.aggregate(pipeline).to_list(1)
    totals = result[0] if result else {"total_seconds": 0, "session_count": 0}

    # Get favorite channel
    channel_pipeline = [
        {"$match": {"user_id": user_id, "guild_id": guild_id, "duration_seconds": {"$ne": None}}},
        {
            "$group": {
                "_id": "$channel_name",
                "time": {"$sum": "$duration_seconds"},
            }
        },
        {"$sort": {"time": -1}},
        {"$limit": 1},
    ]
    channel_result = await db.voice_sessions.aggregate(channel_pipeline).to_list(1)
    favorite_channel = channel_result[0]["_id"] if channel_result else None

    return {
        "total_seconds": totals["total_seconds"],
        "session_count": totals["session_count"],
        "favorite_channel": favorite_channel,
    }


async def get_message_stats(user_id: str, guild_id: str) -> dict:
    """Get message statistics for a user in a guild."""
    # Count messages
    message_count = await db.messages.count_documents(
        {"user_id": user_id, "guild_id": guild_id}
    )

    # Get emoji usage
    emoji_pipeline = [
        {"$match": {"user_id": user_id, "guild_id": guild_id, "emojis.0": {"$exists": True}}},
        {"$unwind": "$emojis"},
        {"$group": {"_id": "$emojis", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    emoji_results = await db.messages.aggregate(emoji_pipeline).to_list(100)

    total_emojis = sum(e["count"] for e in emoji_results)
    top_emoji = emoji_results[0] if emoji_results else None

    return {
        "message_count": message_count,
        "total_emojis": total_emojis,
        "top_emoji": top_emoji["_id"] if top_emoji else None,
        "top_emoji_count": top_emoji["count"] if top_emoji else 0,
    }


async def get_reaction_stats(user_id: str, guild_id: str) -> dict:
    """Get reaction statistics for a user in a guild."""
    # Count adds and removes
    add_count = await db.reactions.count_documents(
        {"user_id": user_id, "guild_id": guild_id, "action": "add"}
    )
    remove_count = await db.reactions.count_documents(
        {"user_id": user_id, "guild_id": guild_id, "action": "remove"}
    )

    # Get favorite reaction
    reaction_pipeline = [
        {"$match": {"user_id": user_id, "guild_id": guild_id, "action": "add"}},
        {"$group": {"_id": "$emoji", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 1},
    ]
    reaction_result = await db.reactions.aggregate(reaction_pipeline).to_list(1)
    top_reaction = reaction_result[0] if reaction_result else None

    return {
        "add_count": add_count,
        "remove_count": remove_count,
        "top_reaction": top_reaction["_id"] if top_reaction else None,
        "top_reaction_count": top_reaction["count"] if top_reaction else 0,
    }


async def get_guild_leaderboards(
    guild_id: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict:
    """Get leaderboard stats for all users in a guild within a date range.

    Returns top 5 users per category:
    - voice_time: [(user_id, username, total_seconds), ...]
    - messages: [(user_id, username, message_count), ...]
    - emojis: [(user_id, username, emoji_count), ...]
    - reactions: [(user_id, username, reaction_count), ...]
    """
    # Build date filter
    date_filter = {}
    if start_date:
        date_filter["$gte"] = start_date
    if end_date:
        date_filter["$lte"] = end_date

    # Voice time leaderboard
    voice_match = {"guild_id": guild_id, "duration_seconds": {"$ne": None}}
    if date_filter:
        voice_match["left_at"] = date_filter

    voice_pipeline = [
        {"$match": voice_match},
        {"$group": {"_id": "$user_id", "total_seconds": {"$sum": "$duration_seconds"}}},
        {"$sort": {"total_seconds": -1}},
        {"$limit": 5},
        {
            "$lookup": {
                "from": "users",
                "localField": "_id",
                "foreignField": "_id",
                "as": "user_info",
            }
        },
        {
            "$project": {
                "user_id": "$_id",
                "total_seconds": 1,
                "username": {"$arrayElemAt": ["$user_info.username", 0]},
            }
        },
    ]
    voice_results = await db.voice_sessions.aggregate(voice_pipeline).to_list(5)
    voice_time = [
        (r["user_id"], r.get("username", "Unknown"), r["total_seconds"])
        for r in voice_results
    ]

    # Messages leaderboard
    messages_match = {"guild_id": guild_id}
    if date_filter:
        messages_match["created_at"] = date_filter

    messages_pipeline = [
        {"$match": messages_match},
        {"$group": {"_id": "$user_id", "message_count": {"$sum": 1}}},
        {"$sort": {"message_count": -1}},
        {"$limit": 5},
        {
            "$lookup": {
                "from": "users",
                "localField": "_id",
                "foreignField": "_id",
                "as": "user_info",
            }
        },
        {
            "$project": {
                "user_id": "$_id",
                "message_count": 1,
                "username": {"$arrayElemAt": ["$user_info.username", 0]},
            }
        },
    ]
    messages_results = await db.messages.aggregate(messages_pipeline).to_list(5)
    messages = [
        (r["user_id"], r.get("username", "Unknown"), r["message_count"])
        for r in messages_results
    ]

    # Emojis leaderboard (total emoji count from messages)
    emojis_match = {"guild_id": guild_id, "emojis.0": {"$exists": True}}
    if date_filter:
        emojis_match["created_at"] = date_filter

    emojis_pipeline = [
        {"$match": emojis_match},
        {"$unwind": "$emojis"},
        {"$group": {"_id": "$user_id", "emoji_count": {"$sum": 1}}},
        {"$sort": {"emoji_count": -1}},
        {"$limit": 5},
        {
            "$lookup": {
                "from": "users",
                "localField": "_id",
                "foreignField": "_id",
                "as": "user_info",
            }
        },
        {
            "$project": {
                "user_id": "$_id",
                "emoji_count": 1,
                "username": {"$arrayElemAt": ["$user_info.username", 0]},
            }
        },
    ]
    emojis_results = await db.messages.aggregate(emojis_pipeline).to_list(5)
    emojis = [
        (r["user_id"], r.get("username", "Unknown"), r["emoji_count"])
        for r in emojis_results
    ]

    # Reactions leaderboard (reactions given/added)
    reactions_match = {"guild_id": guild_id, "action": "add"}
    if date_filter:
        reactions_match["created_at"] = date_filter

    reactions_pipeline = [
        {"$match": reactions_match},
        {"$group": {"_id": "$user_id", "reaction_count": {"$sum": 1}}},
        {"$sort": {"reaction_count": -1}},
        {"$limit": 5},
        {
            "$lookup": {
                "from": "users",
                "localField": "_id",
                "foreignField": "_id",
                "as": "user_info",
            }
        },
        {
            "$project": {
                "user_id": "$_id",
                "reaction_count": 1,
                "username": {"$arrayElemAt": ["$user_info.username", 0]},
            }
        },
    ]
    reactions_results = await db.reactions.aggregate(reactions_pipeline).to_list(5)
    reactions = [
        (r["user_id"], r.get("username", "Unknown"), r["reaction_count"])
        for r in reactions_results
    ]

    return {
        "voice_time": voice_time,
        "messages": messages,
        "emojis": emojis,
        "reactions": reactions,
    }


async def get_first_activity(user_id: str, guild_id: str) -> datetime | None:
    """Get the earliest recorded activity for a user in a guild."""
    dates = []

    # Check voice sessions
    voice = await db.voice_sessions.find_one(
        {"user_id": user_id, "guild_id": guild_id},
        sort=[("joined_at", 1)],
    )
    if voice:
        dates.append(voice["joined_at"])

    # Check messages
    message = await db.messages.find_one(
        {"user_id": user_id, "guild_id": guild_id},
        sort=[("created_at", 1)],
    )
    if message:
        dates.append(message["created_at"])

    # Check reactions
    reaction = await db.reactions.find_one(
        {"user_id": user_id, "guild_id": guild_id},
        sort=[("created_at", 1)],
    )
    if reaction:
        dates.append(reaction["created_at"])

    return min(dates) if dates else None
