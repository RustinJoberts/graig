from datetime import datetime, timedelta, timezone

import pytest

from db import (
    end_voice_session,
    get_first_activity,
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
