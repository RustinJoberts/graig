# Graig

A Discord bot that tracks server activity and provides users with fun statistics about their participation.

## Features

- **Voice Activity Tracking**: Monitors when users join, leave, and switch voice channels. Tracks total time spent and favorite channels.
- **Message Tracking**: Records messages sent and extracts emoji usage from message content.
- **Reaction Tracking**: Tracks reactions added and removed, including favorite emojis.
- **User Stats Command**: `/stats` slash command displays a visual summary of a user's activity.
- **Meme Generation**: Create custom memes using popular templates or fetch random memes from Reddit.

## Requirements

- Python 3.12+
- MongoDB
- Discord Bot Token

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd graig
   ```

2. Install dependencies using [uv](https://github.com/astral-sh/uv):
   ```bash
   uv sync
   ```

3. Create a `.env` file with your configuration:
   ```env
   DISCORD_TOKEN=your_discord_bot_token
   MONGO_URI=mongodb://localhost:27017/
   ```

4. Run the bot:
   ```bash
   uv run python main.py
   ```

## Discord Bot Setup

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application and add a bot
3. Enable the following Privileged Gateway Intents:
   - **Server Members Intent**
   - **Message Content Intent**
4. Invite the bot to your server with the following scopes:
   - `bot`
   - `applications.commands`

## Commands

| Command | Description |
|---------|-------------|
| `/stats` | View your activity stats in the server |
| `/stats @user` | View another user's activity stats |
| `/meme <template> <top_text> [bottom_text]` | Generate a custom meme using a template |
| `/randommeme [subreddit]` | Fetch a random meme from Reddit |
| `/memetemplates [search]` | List or search available meme templates |

## Project Structure

```
graig/
├── main.py          # Bot entry point, event handlers, slash commands
├── config.py        # Configuration management (pydantic-settings)
├── db.py            # MongoDB operations (motor async driver)
├── meme.py          # Meme generation API helpers (Memegen, Meme_Api)
├── utils.py         # Helper functions (emoji extraction, formatting)
├── tests/           # Test suite
│   ├── conftest.py  # Mock MongoDB fixtures
│   ├── test_db.py   # Database function tests
│   ├── test_meme.py # Meme function tests
│   └── test_utils.py# Utility function tests
└── pyproject.toml   # Project configuration
```

## MongoDB Collections

### `users`
Tracks user identity with their current display name.

| Field | Type | Description |
|-------|------|-------------|
| `_id` | string | Discord user ID |
| `username` | string | Current display name |
| `updated_at` | datetime | Last activity timestamp |

### `voice_sessions`
Records voice channel activity with duration.

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | string | Discord user ID |
| `guild_id` | string | Server ID |
| `channel_id` | string | Voice channel ID |
| `channel_name` | string | Channel name at join time |
| `joined_at` | datetime | Join timestamp |
| `left_at` | datetime | Leave timestamp |
| `duration_seconds` | int | Session duration |

### `messages`
Records messages with emoji usage.

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | string | Discord user ID |
| `guild_id` | string | Server ID |
| `channel_id` | string | Text channel ID |
| `message_id` | string | Discord message ID |
| `emojis` | array | Emojis used in the message |
| `created_at` | datetime | Timestamp |

### `reactions`
Records reaction events.

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | string | Discord user ID |
| `guild_id` | string | Server ID |
| `channel_id` | string | Channel ID |
| `message_id` | string | Message ID |
| `emoji` | string | The emoji used |
| `action` | string | `"add"` or `"remove"` |
| `created_at` | datetime | Timestamp |

## Development

### Install dev dependencies

```bash
uv sync --group dev
```

### Run tests

```bash
uv run pytest
```

### Run tests with verbose output

```bash
uv run pytest -v
```

## Privacy

- The bot only tracks activity in guild (server) channels
- Direct messages are not monitored
- Message content is not stored, only emoji usage
- All data is stored per-guild and can be queried per-user

## License

MIT
