from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from meme import (
    MEME_API,
    MEMEGEN_API,
    build_meme_url,
    encode_meme_text,
    get_meme_templates,
    get_random_meme,
    search_templates,
)


class AsyncContextManagerMock:
    """Helper to create a mock that works as an async context manager."""

    def __init__(self, return_value):
        self.return_value = return_value

    async def __aenter__(self):
        return self.return_value

    async def __aexit__(self, *args):
        pass


class TestEncodeMemeText:
    def test_encodes_spaces_to_underscores(self):
        assert encode_meme_text("hello world") == "hello_world"

    def test_encodes_underscores_to_double_underscores(self):
        assert encode_meme_text("hello_world") == "hello__world"

    def test_encodes_dashes_to_double_dashes(self):
        assert encode_meme_text("hello-world") == "hello--world"

    def test_encodes_question_marks(self):
        assert encode_meme_text("what?") == "what~q"

    def test_encodes_hash(self):
        assert encode_meme_text("#1") == "~h1"

    def test_encodes_slash(self):
        assert encode_meme_text("yes/no") == "yes~sno"

    def test_encodes_quotes(self):
        assert encode_meme_text('say "hello"') == "say_''hello''"

    def test_encodes_newlines(self):
        assert encode_meme_text("line1\nline2") == "line1~nline2"

    def test_handles_empty_string(self):
        assert encode_meme_text("") == "_"

    def test_encodes_complex_text(self):
        result = encode_meme_text("What? Yes/No #1")
        assert result == "What~q_Yes~sNo_~h1"


class TestBuildMemeUrl:
    def test_builds_basic_url(self):
        url = build_meme_url("drake", "hello", "world")
        assert url == f"{MEMEGEN_API}/images/drake/hello/world.png"

    def test_handles_empty_bottom_text(self):
        url = build_meme_url("drake", "hello")
        assert url == f"{MEMEGEN_API}/images/drake/hello/_.png"

    def test_encodes_text_in_url(self):
        url = build_meme_url("drake", "hello world", "what?")
        assert url == f"{MEMEGEN_API}/images/drake/hello_world/what~q.png"


class TestGetMemeTemplates:
    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset the templates cache before each test."""
        import meme

        meme._templates_cache = None

    async def test_fetches_templates_from_api(self):
        mock_templates = [
            {"id": "drake", "name": "Drake Hotline Bling"},
            {"id": "distracted", "name": "Distracted Boyfriend"},
        ]

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_templates)

        mock_session = MagicMock()
        mock_session.get.return_value = AsyncContextManagerMock(mock_response)

        with patch("meme.aiohttp.ClientSession") as mock_client:
            mock_client.return_value = AsyncContextManagerMock(mock_session)

            templates = await get_meme_templates()

            assert templates == mock_templates
            mock_session.get.assert_called_once_with(f"{MEMEGEN_API}/templates")

    async def test_returns_empty_list_on_error(self):
        mock_response = MagicMock()
        mock_response.status = 500

        mock_session = MagicMock()
        mock_session.get.return_value = AsyncContextManagerMock(mock_response)

        with patch("meme.aiohttp.ClientSession") as mock_client:
            mock_client.return_value = AsyncContextManagerMock(mock_session)

            templates = await get_meme_templates()

            assert templates == []

    async def test_uses_cached_templates(self):
        import meme

        cached = [{"id": "cached", "name": "Cached Template"}]
        meme._templates_cache = cached

        # Should return cached without making API call
        with patch("meme.aiohttp.ClientSession") as mock_client:
            templates = await get_meme_templates()
            mock_client.assert_not_called()

        assert templates == cached


class TestSearchTemplates:
    async def test_searches_by_name(self):
        mock_templates = [
            {"id": "drake", "name": "Drake Hotline Bling"},
            {"id": "distracted", "name": "Distracted Boyfriend"},
            {"id": "doge", "name": "Doge"},
        ]

        with patch("meme.get_meme_templates", new=AsyncMock(return_value=mock_templates)):
            results = await search_templates("drake")

            assert len(results) == 1
            assert results[0]["id"] == "drake"

    async def test_search_is_case_insensitive(self):
        mock_templates = [
            {"id": "drake", "name": "Drake Hotline Bling"},
        ]

        with patch("meme.get_meme_templates", new=AsyncMock(return_value=mock_templates)):
            results = await search_templates("DRAKE")

            assert len(results) == 1
            assert results[0]["id"] == "drake"

    async def test_returns_multiple_matches(self):
        mock_templates = [
            {"id": "drake", "name": "Drake Hotline Bling"},
            {"id": "distracted", "name": "Distracted Boyfriend"},
            {"id": "doge", "name": "Doge"},
        ]

        with patch("meme.get_meme_templates", new=AsyncMock(return_value=mock_templates)):
            results = await search_templates("d")

            assert len(results) == 3

    async def test_returns_empty_for_no_match(self):
        mock_templates = [
            {"id": "drake", "name": "Drake Hotline Bling"},
        ]

        with patch("meme.get_meme_templates", new=AsyncMock(return_value=mock_templates)):
            results = await search_templates("xyz")

            assert results == []


class TestGetRandomMeme:
    async def test_fetches_random_meme(self):
        mock_meme = {
            "title": "Funny meme",
            "url": "https://example.com/meme.jpg",
            "postLink": "https://reddit.com/r/memes/...",
            "subreddit": "memes",
            "author": "memer123",
        }

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_meme)

        mock_session = MagicMock()
        mock_session.get.return_value = AsyncContextManagerMock(mock_response)

        with patch("meme.aiohttp.ClientSession") as mock_client:
            mock_client.return_value = AsyncContextManagerMock(mock_session)

            result = await get_random_meme()

            assert result == mock_meme
            mock_session.get.assert_called_once_with(f"{MEME_API}/gimme")

    async def test_fetches_from_specific_subreddit(self):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={})

        mock_session = MagicMock()
        mock_session.get.return_value = AsyncContextManagerMock(mock_response)

        with patch("meme.aiohttp.ClientSession") as mock_client:
            mock_client.return_value = AsyncContextManagerMock(mock_session)

            await get_random_meme("dankmemes")

            mock_session.get.assert_called_once_with(f"{MEME_API}/gimme/dankmemes")

    async def test_returns_none_on_error(self):
        mock_response = MagicMock()
        mock_response.status = 500

        mock_session = MagicMock()
        mock_session.get.return_value = AsyncContextManagerMock(mock_response)

        with patch("meme.aiohttp.ClientSession") as mock_client:
            mock_client.return_value = AsyncContextManagerMock(mock_session)

            result = await get_random_meme()

            assert result is None
