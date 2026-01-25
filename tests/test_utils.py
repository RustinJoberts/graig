import pytest

from utils import extract_emojis, format_duration


class TestExtractEmojis:
    def test_extracts_unicode_emojis(self):
        text = "Hello 😀 world 👍"
        result = extract_emojis(text)
        assert "😀" in result
        assert "👍" in result

    def test_extracts_custom_discord_emojis(self):
        text = "Check out <:custom:123456789> this emoji"
        result = extract_emojis(text)
        assert "<:custom:123456789>" in result

    def test_extracts_animated_discord_emojis(self):
        text = "Animated <a:dance:987654321> emoji"
        result = extract_emojis(text)
        assert "<a:dance:987654321>" in result

    def test_extracts_multiple_emojis(self):
        text = "😀😀😀 <:test:123> 👍"
        result = extract_emojis(text)
        assert len(result) >= 3  # At least 3 emoji matches

    def test_returns_empty_for_no_emojis(self):
        text = "Just plain text without emojis"
        result = extract_emojis(text)
        assert result == []

    def test_handles_empty_string(self):
        result = extract_emojis("")
        assert result == []

    def test_extracts_flag_emojis(self):
        text = "Flags: 🇺🇸 🇬🇧"
        result = extract_emojis(text)
        assert len(result) >= 1  # At least one flag match


class TestFormatDuration:
    def test_formats_seconds(self):
        assert format_duration(30) == "30s"
        assert format_duration(59) == "59s"

    def test_formats_minutes(self):
        assert format_duration(60) == "1m"
        assert format_duration(120) == "2m"
        assert format_duration(3599) == "59m"

    def test_formats_hours(self):
        assert format_duration(3600) == "1h"
        assert format_duration(7200) == "2h"

    def test_formats_hours_and_minutes(self):
        assert format_duration(3660) == "1h 1m"
        assert format_duration(5400) == "1h 30m"
        assert format_duration(7320) == "2h 2m"

    def test_formats_zero(self):
        assert format_duration(0) == "0s"

    def test_formats_large_values(self):
        # 25 hours
        assert format_duration(90000) == "25h"
        # 25 hours 30 minutes
        assert format_duration(91800) == "25h 30m"
