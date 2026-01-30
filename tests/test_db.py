from datetime import datetime, timedelta, timezone

import pytest

from db import (
    end_voice_session,
    get_first_activity,
    get_guild_leaderboards,
    get_message_stats,
    get_reaction_stats,
    get_voice_stats,
    record_message,
    record_reaction,
    start_voice_session,
    upsert_user,
)


class TestUpsertUser:
    async def test_creates_new_user(self, mock_db, sample_user_id):
        await upsert_user(sample_user_id, "TestUser")

        assert len(mock_db.users.documents) == 1
        user = mock_db.users.documents[0]
        assert user["_id"] == sample_user_id
        assert user["username"] == "TestUser"
        assert "updated_at" in user

    async def test_updates_existing_user(self, mock_db, sample_user_id):
        await upsert_user(sample_user_id, "OldName")
        await upsert_user(sample_user_id, "NewName")

        assert len(mock_db.users.documents) == 1
        user = mock_db.users.documents[0]
        assert user["username"] == "NewName"


class TestVoiceSessions:
    async def test_start_voice_session(self, mock_db, sample_user_id, sample_guild_id):
        await start_voice_session(
            sample_user_id, sample_guild_id, "channel123", "General"
        )

        assert len(mock_db.voice_sessions.documents) == 1
        session = mock_db.voice_sessions.documents[0]
        assert session["user_id"] == sample_user_id
        assert session["guild_id"] == sample_guild_id
        assert session["channel_id"] == "channel123"
        assert session["channel_name"] == "General"
        assert session["left_at"] is None
        assert session["duration_seconds"] is None

    async def test_end_voice_session(self, mock_db, sample_user_id, sample_guild_id):
        # Start a session
        await start_voice_session(
            sample_user_id, sample_guild_id, "channel123", "General"
        )

        # Manually set joined_at to a known time for testing
        mock_db.voice_sessions.documents[0]["joined_at"] = datetime(
            2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc
        )

        # End the session
        await end_voice_session(sample_user_id, sample_guild_id)

        session = mock_db.voice_sessions.documents[0]
        assert session["left_at"] is not None
        assert session["duration_seconds"] is not None
        assert session["duration_seconds"] >= 0

    async def test_end_voice_session_no_active_session(
        self, mock_db, sample_user_id, sample_guild_id
    ):
        # Should not raise an error
        await end_voice_session(sample_user_id, sample_guild_id)
        assert len(mock_db.voice_sessions.documents) == 0


class TestRecordMessage:
    async def test_record_message_without_emojis(
        self, mock_db, sample_user_id, sample_guild_id
    ):
        await record_message(
            sample_user_id, sample_guild_id, "channel123", "msg456", []
        )

        assert len(mock_db.messages.documents) == 1
        msg = mock_db.messages.documents[0]
        assert msg["user_id"] == sample_user_id
        assert msg["guild_id"] == sample_guild_id
        assert msg["message_id"] == "msg456"
        assert msg["emojis"] == []

    async def test_record_message_with_emojis(
        self, mock_db, sample_user_id, sample_guild_id
    ):
        emojis = ["😀", "👍", "<:custom:123>"]
        await record_message(
            sample_user_id, sample_guild_id, "channel123", "msg456", emojis
        )

        msg = mock_db.messages.documents[0]
        assert msg["emojis"] == emojis


class TestRecordReaction:
    async def test_record_reaction_add(self, mock_db, sample_user_id, sample_guild_id):
        await record_reaction(
            sample_user_id, sample_guild_id, "channel123", "msg456", "👍", "add"
        )

        assert len(mock_db.reactions.documents) == 1
        reaction = mock_db.reactions.documents[0]
        assert reaction["user_id"] == sample_user_id
        assert reaction["emoji"] == "👍"
        assert reaction["action"] == "add"

    async def test_record_reaction_remove(
        self, mock_db, sample_user_id, sample_guild_id
    ):
        await record_reaction(
            sample_user_id, sample_guild_id, "channel123", "msg456", "👍", "remove"
        )

        reaction = mock_db.reactions.documents[0]
        assert reaction["action"] == "remove"


class TestGetVoiceStats:
    async def test_returns_zeros_for_no_data(
        self, mock_db, sample_user_id, sample_guild_id
    ):
        stats = await get_voice_stats(sample_user_id, sample_guild_id)

        assert stats["total_seconds"] == 0
        assert stats["session_count"] == 0
        assert stats["favorite_channel"] is None

    async def test_calculates_totals(self, mock_db, sample_user_id, sample_guild_id):
        # Add completed sessions
        mock_db.voice_sessions.documents.append(
            {
                "user_id": sample_user_id,
                "guild_id": sample_guild_id,
                "channel_name": "General",
                "duration_seconds": 3600,
                "left_at": datetime.now(timezone.utc),
            }
        )
        mock_db.voice_sessions.documents.append(
            {
                "user_id": sample_user_id,
                "guild_id": sample_guild_id,
                "channel_name": "General",
                "duration_seconds": 1800,
                "left_at": datetime.now(timezone.utc),
            }
        )

        stats = await get_voice_stats(sample_user_id, sample_guild_id)

        assert stats["total_seconds"] == 5400
        assert stats["session_count"] == 2
        assert stats["favorite_channel"] == "General"


class TestGetMessageStats:
    async def test_returns_zeros_for_no_data(
        self, mock_db, sample_user_id, sample_guild_id
    ):
        stats = await get_message_stats(sample_user_id, sample_guild_id)

        assert stats["message_count"] == 0
        assert stats["total_emojis"] == 0
        assert stats["top_emoji"] is None
        assert stats["top_emoji_count"] == 0

    async def test_counts_messages_and_emojis(
        self, mock_db, sample_user_id, sample_guild_id
    ):
        mock_db.messages.documents.append(
            {
                "user_id": sample_user_id,
                "guild_id": sample_guild_id,
                "emojis": ["😀", "😀", "👍"],
            }
        )
        mock_db.messages.documents.append(
            {
                "user_id": sample_user_id,
                "guild_id": sample_guild_id,
                "emojis": ["😀"],
            }
        )

        stats = await get_message_stats(sample_user_id, sample_guild_id)

        assert stats["message_count"] == 2
        assert stats["total_emojis"] == 4
        assert stats["top_emoji"] == "😀"
        assert stats["top_emoji_count"] == 3


class TestGetReactionStats:
    async def test_returns_zeros_for_no_data(
        self, mock_db, sample_user_id, sample_guild_id
    ):
        stats = await get_reaction_stats(sample_user_id, sample_guild_id)

        assert stats["add_count"] == 0
        assert stats["remove_count"] == 0
        assert stats["top_reaction"] is None
        assert stats["top_reaction_count"] == 0

    async def test_counts_reactions(self, mock_db, sample_user_id, sample_guild_id):
        mock_db.reactions.documents.extend(
            [
                {
                    "user_id": sample_user_id,
                    "guild_id": sample_guild_id,
                    "emoji": "👍",
                    "action": "add",
                },
                {
                    "user_id": sample_user_id,
                    "guild_id": sample_guild_id,
                    "emoji": "👍",
                    "action": "add",
                },
                {
                    "user_id": sample_user_id,
                    "guild_id": sample_guild_id,
                    "emoji": "❤️",
                    "action": "add",
                },
                {
                    "user_id": sample_user_id,
                    "guild_id": sample_guild_id,
                    "emoji": "👍",
                    "action": "remove",
                },
            ]
        )

        stats = await get_reaction_stats(sample_user_id, sample_guild_id)

        assert stats["add_count"] == 3
        assert stats["remove_count"] == 1
        assert stats["top_reaction"] == "👍"
        assert stats["top_reaction_count"] == 2


class TestGetFirstActivity:
    async def test_returns_none_for_no_data(
        self, mock_db, sample_user_id, sample_guild_id
    ):
        result = await get_first_activity(sample_user_id, sample_guild_id)
        assert result is None

    async def test_finds_earliest_voice_session(
        self, mock_db, sample_user_id, sample_guild_id
    ):
        early = datetime(2024, 1, 1, tzinfo=timezone.utc)
        late = datetime(2024, 6, 1, tzinfo=timezone.utc)

        mock_db.voice_sessions.documents.append(
            {
                "user_id": sample_user_id,
                "guild_id": sample_guild_id,
                "joined_at": late,
            }
        )
        mock_db.voice_sessions.documents.append(
            {
                "user_id": sample_user_id,
                "guild_id": sample_guild_id,
                "joined_at": early,
            }
        )

        result = await get_first_activity(sample_user_id, sample_guild_id)
        assert result == early

    async def test_finds_earliest_across_collections(
        self, mock_db, sample_user_id, sample_guild_id
    ):
        voice_time = datetime(2024, 3, 1, tzinfo=timezone.utc)
        message_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        reaction_time = datetime(2024, 2, 1, tzinfo=timezone.utc)

        mock_db.voice_sessions.documents.append(
            {
                "user_id": sample_user_id,
                "guild_id": sample_guild_id,
                "joined_at": voice_time,
            }
        )
        mock_db.messages.documents.append(
            {
                "user_id": sample_user_id,
                "guild_id": sample_guild_id,
                "created_at": message_time,
            }
        )
        mock_db.reactions.documents.append(
            {
                "user_id": sample_user_id,
                "guild_id": sample_guild_id,
                "created_at": reaction_time,
            }
        )

        result = await get_first_activity(sample_user_id, sample_guild_id)
        assert result == message_time


class TestGetGuildLeaderboards:
    async def test_returns_empty_lists_for_no_data(self, mock_db, sample_guild_id):
        result = await get_guild_leaderboards(sample_guild_id)

        assert result["voice_time"] == []
        assert result["messages"] == []
        assert result["emojis"] == []
        assert result["reactions"] == []

    async def test_voice_time_leaderboard(self, mock_db, sample_guild_id):
        # Add users
        mock_db.users.documents.append({"_id": "user1", "username": "Alice"})
        mock_db.users.documents.append({"_id": "user2", "username": "Bob"})

        # Add voice sessions
        mock_db.voice_sessions.documents.extend([
            {
                "user_id": "user1",
                "guild_id": sample_guild_id,
                "duration_seconds": 3600,
                "left_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
            },
            {
                "user_id": "user1",
                "guild_id": sample_guild_id,
                "duration_seconds": 1800,
                "left_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
            },
            {
                "user_id": "user2",
                "guild_id": sample_guild_id,
                "duration_seconds": 7200,
                "left_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
            },
        ])

        result = await get_guild_leaderboards(sample_guild_id)

        # Bob should be first with 7200 seconds, Alice second with 5400
        assert len(result["voice_time"]) == 2
        assert result["voice_time"][0][0] == "user2"  # user_id
        assert result["voice_time"][0][1] == "Bob"  # username
        assert result["voice_time"][0][2] == 7200  # total_seconds
        assert result["voice_time"][1][0] == "user1"
        assert result["voice_time"][1][2] == 5400

    async def test_messages_leaderboard(self, mock_db, sample_guild_id):
        # Add users
        mock_db.users.documents.append({"_id": "user1", "username": "Alice"})
        mock_db.users.documents.append({"_id": "user2", "username": "Bob"})

        # Add messages
        for _ in range(5):
            mock_db.messages.documents.append({
                "user_id": "user1",
                "guild_id": sample_guild_id,
                "emojis": [],
                "created_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
            })
        for _ in range(10):
            mock_db.messages.documents.append({
                "user_id": "user2",
                "guild_id": sample_guild_id,
                "emojis": [],
                "created_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
            })

        result = await get_guild_leaderboards(sample_guild_id)

        # Bob should be first with 10 messages, Alice second with 5
        assert len(result["messages"]) == 2
        assert result["messages"][0][0] == "user2"
        assert result["messages"][0][2] == 10
        assert result["messages"][1][0] == "user1"
        assert result["messages"][1][2] == 5

    async def test_emojis_leaderboard(self, mock_db, sample_guild_id):
        # Add users
        mock_db.users.documents.append({"_id": "user1", "username": "Alice"})
        mock_db.users.documents.append({"_id": "user2", "username": "Bob"})

        # Add messages with emojis
        mock_db.messages.documents.append({
            "user_id": "user1",
            "guild_id": sample_guild_id,
            "emojis": ["😀", "👍", "❤️"],
            "created_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
        })
        mock_db.messages.documents.append({
            "user_id": "user2",
            "guild_id": sample_guild_id,
            "emojis": ["😀"],
            "created_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
        })

        result = await get_guild_leaderboards(sample_guild_id)

        # Alice should be first with 3 emojis, Bob second with 1
        assert len(result["emojis"]) == 2
        assert result["emojis"][0][0] == "user1"
        assert result["emojis"][0][2] == 3
        assert result["emojis"][1][0] == "user2"
        assert result["emojis"][1][2] == 1

    async def test_reactions_leaderboard(self, mock_db, sample_guild_id):
        # Add users
        mock_db.users.documents.append({"_id": "user1", "username": "Alice"})
        mock_db.users.documents.append({"_id": "user2", "username": "Bob"})

        # Add reactions
        for _ in range(3):
            mock_db.reactions.documents.append({
                "user_id": "user1",
                "guild_id": sample_guild_id,
                "emoji": "👍",
                "action": "add",
                "created_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
            })
        for _ in range(7):
            mock_db.reactions.documents.append({
                "user_id": "user2",
                "guild_id": sample_guild_id,
                "emoji": "❤️",
                "action": "add",
                "created_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
            })
        # Remove actions should not be counted
        mock_db.reactions.documents.append({
            "user_id": "user1",
            "guild_id": sample_guild_id,
            "emoji": "👍",
            "action": "remove",
            "created_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
        })

        result = await get_guild_leaderboards(sample_guild_id)

        # Bob should be first with 7 reactions, Alice second with 3
        assert len(result["reactions"]) == 2
        assert result["reactions"][0][0] == "user2"
        assert result["reactions"][0][2] == 7
        assert result["reactions"][1][0] == "user1"
        assert result["reactions"][1][2] == 3

    async def test_limits_to_top_5(self, mock_db, sample_guild_id):
        # Add 7 users
        for i in range(7):
            mock_db.users.documents.append({"_id": f"user{i}", "username": f"User{i}"})
            mock_db.messages.documents.append({
                "user_id": f"user{i}",
                "guild_id": sample_guild_id,
                "emojis": [],
                "created_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
            })

        result = await get_guild_leaderboards(sample_guild_id)

        assert len(result["messages"]) == 5

    async def test_date_filtering(self, mock_db, sample_guild_id):
        # Add users
        mock_db.users.documents.append({"_id": "user1", "username": "Alice"})

        # Add messages at different dates
        mock_db.messages.documents.append({
            "user_id": "user1",
            "guild_id": sample_guild_id,
            "emojis": [],
            "created_at": datetime(2024, 1, 10, tzinfo=timezone.utc),
        })
        mock_db.messages.documents.append({
            "user_id": "user1",
            "guild_id": sample_guild_id,
            "emojis": [],
            "created_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
        })
        mock_db.messages.documents.append({
            "user_id": "user1",
            "guild_id": sample_guild_id,
            "emojis": [],
            "created_at": datetime(2024, 1, 20, tzinfo=timezone.utc),
        })

        # Filter to only include Jan 12-18
        start_date = datetime(2024, 1, 12, tzinfo=timezone.utc)
        end_date = datetime(2024, 1, 18, tzinfo=timezone.utc)

        result = await get_guild_leaderboards(sample_guild_id, start_date, end_date)

        # Only 1 message should be in range
        assert len(result["messages"]) == 1
        assert result["messages"][0][2] == 1

    async def test_ignores_other_guilds(self, mock_db, sample_guild_id):
        # Add users
        mock_db.users.documents.append({"_id": "user1", "username": "Alice"})

        # Add messages to different guilds
        mock_db.messages.documents.append({
            "user_id": "user1",
            "guild_id": sample_guild_id,
            "emojis": [],
            "created_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
        })
        mock_db.messages.documents.append({
            "user_id": "user1",
            "guild_id": "other_guild",
            "emojis": [],
            "created_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
        })

        result = await get_guild_leaderboards(sample_guild_id)

        # Only 1 message from the target guild
        assert len(result["messages"]) == 1
        assert result["messages"][0][2] == 1
