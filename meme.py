import aiohttp

MEMEGEN_API = "https://api.memegen.link"
MEME_API = "https://meme-api.com"

# Cache for meme templates
_templates_cache: list[dict] | None = None


def encode_meme_text(text: str) -> str:
    """Encode text for use in Memegen URLs.

    Encoding rules:
    - Spaces -> _
    - Underscores -> __
    - Dashes -> --
    - ? -> ~q
    - # -> ~h
    - / -> ~s
    - " -> ''
    - Newlines -> ~n
    """
    if not text:
        return "_"

    # Order matters - handle special sequences first
    text = text.replace("_", "__")
    text = text.replace("-", "--")
    text = text.replace(" ", "_")
    text = text.replace("?", "~q")
    text = text.replace("#", "~h")
    text = text.replace("/", "~s")
    text = text.replace('"', "''")
    text = text.replace("\n", "~n")

    return text


def build_meme_url(template_id: str, top: str, bottom: str = "") -> str:
    """Build a Memegen URL for the given template and text."""
    encoded_top = encode_meme_text(top)
    encoded_bottom = encode_meme_text(bottom) if bottom else "_"

    return f"{MEMEGEN_API}/images/{template_id}/{encoded_top}/{encoded_bottom}.png"


async def get_meme_templates(force_refresh: bool = False) -> list[dict]:
    """Fetch available meme templates from Memegen API.

    Returns a list of template dicts with 'id', 'name', and 'example' fields.
    Results are cached after the first call.
    """
    global _templates_cache

    if _templates_cache is not None and not force_refresh:
        return _templates_cache

    async with aiohttp.ClientSession() as session:
        async with session.get(f"{MEMEGEN_API}/templates") as response:
            if response.status != 200:
                return []
            templates = await response.json()
            _templates_cache = templates
            return templates


async def search_templates(query: str) -> list[dict]:
    """Search templates by name or keywords.

    Returns templates whose name contains the query (case-insensitive).
    """
    templates = await get_meme_templates()
    query_lower = query.lower()

    return [t for t in templates if query_lower in t.get("name", "").lower()]


async def get_random_meme(subreddit: str | None = None) -> dict | None:
    """Fetch a random meme from the Meme API.

    Args:
        subreddit: Optional subreddit to fetch from (e.g., 'memes', 'dankmemes')

    Returns:
        Dict with 'title', 'url', 'postLink', 'subreddit', 'author' fields,
        or None if the request fails.
    """
    url = f"{MEME_API}/gimme"
    if subreddit:
        url = f"{MEME_API}/gimme/{subreddit}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                return None
            return await response.json()
