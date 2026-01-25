# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Graig is a Discord bot written in Python 3.12 using the discord.py library.

## Commands

```bash
# Install dependencies
uv sync

# Install dev dependencies (includes pytest)
uv sync --group dev

# Run the bot
uv run python main.py

# Run tests
uv run pytest
```

## Configuration

The bot uses pydantic-settings for configuration management. Environment variables are loaded from `.env`:
- `DISCORD_TOKEN` - Discord bot token (required)
- `MONGO_URI` - MongoDB connection string (defaults to localhost)

## Architecture

- `main.py` - Bot entry point, Discord event handlers, and slash commands
- `config.py` - Settings management using pydantic-settings with `.env` file support
- `db.py` - MongoDB operations using motor (async driver)
- `utils.py` - Helper functions (emoji extraction, duration formatting)

## MongoDB Collections

- `users` - Tracks users by Discord ID with their current display name
- `voice_sessions` - Records voice channel join/leave events with duration
- `messages` - Records messages sent with emojis used
- `reactions` - Records reaction add/remove events
