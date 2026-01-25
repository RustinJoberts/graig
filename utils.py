import re

# Regex patterns for emoji extraction
CUSTOM_EMOJI_PATTERN = re.compile(r"<a?:\w+:\d+>")
UNICODE_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FA6F"  # chess symbols
    "\U0001FA70-\U0001FAFF"  # symbols extended
    "\U00002702-\U000027B0"  # dingbats
    "\U00002600-\U000026FF"  # misc symbols
    "]+"
)


def extract_emojis(text: str) -> list[str]:
    """Extract all emojis (custom and unicode) from text."""
    emojis = CUSTOM_EMOJI_PATTERN.findall(text)
    emojis.extend(UNICODE_EMOJI_PATTERN.findall(text))
    return emojis


def format_duration(seconds: int) -> str:
    """Format seconds into a human-readable duration."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes}m"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if minutes:
            return f"{hours}h {minutes}m"
        return f"{hours}h"
