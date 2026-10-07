"""
app/config/settings.py
──────────────────────
Centralized settings via Pydantic + .env file.
All secrets come from environment variables — never hardcoded.
"""
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = Field(..., env="DATABASE_URL")

    @property
    def async_database_url(self) -> str:
        # Railway gives postgresql:// but we need postgresql+asyncpg:// for async driver
        if self.database_url.startswith("postgres://"):
            return self.database_url.replace("postgres://", "postgresql+asyncpg://", 1)
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self.database_url

    # AI
    gemini_api_key: str = Field(..., env="GEMINI_API_KEY")

    # Gmail
    gmail_sender: str = Field(..., env="GMAIL_SENDER")
    gmail_app_password: str = Field(..., env="GMAIL_APP_PASSWORD")
    gmail_recipient: str = Field(..., env="GMAIL_RECIPIENT")

    # Scheduler
    check_interval_minutes: int = Field(30, env="CHECK_INTERVAL_MINUTES")

    # App
    app_env: str = Field("production", env="APP_ENV")
    log_level: str = Field("INFO", env="LOG_LEVEL")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_candidate_config() -> dict:
    """Load candidate profile and monitoring config from YAML."""
    config_path = Path(__file__).parent.parent.parent / "candidate.yaml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)
