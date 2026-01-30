from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')
    discord_token: str
    mongo_uri: str = "mongodb://localhost:27017/"
    admin_user_ids: str = ""  # Comma-separated list of Discord user IDs

    @property
    def admin_ids(self) -> set[str]:
        """Parse admin_user_ids into a set of user ID strings."""
        if not self.admin_user_ids:
            return set()
        return {uid.strip() for uid in self.admin_user_ids.split(",") if uid.strip()}


settings = Settings()
