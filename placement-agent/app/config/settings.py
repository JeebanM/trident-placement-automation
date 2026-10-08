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
        """Kept for simple usage, returns just the URL."""
        url, _ = self.get_async_database_url_and_args()
        return url

    def get_async_database_url_and_args(self) -> tuple[str, dict]:
        from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
        
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            
        parsed = urlparse(url)
        query_params = dict(parse_qsl(parsed.query))
        
        connect_args = {}
        if "sslmode" in query_params:
            sslmode = query_params.pop("sslmode")
            if sslmode == "require":
                connect_args["ssl"] = "require"
            elif sslmode in ("prefer", "allow", "verify-ca", "verify-full"):
                connect_args["ssl"] = sslmode
                
        # asyncpg doesn't support channel_binding
        if "channel_binding" in query_params:
            query_params.pop("channel_binding")
                
        new_query = urlencode(query_params)
        parsed = parsed._replace(query=new_query)
        url = urlunparse(parsed)
            
        return url, connect_args

    # AI
    gemini_api_key: str = Field(..., env="GEMINI_API_KEY")

    # Gmail
    gmail_sender: str = Field(..., env="GMAIL_SENDER")
    gmail_app_password: str = Field(..., env="GMAIL_APP_PASSWORD")
    gmail_recipient: str = Field(..., env="GMAIL_RECIPIENT")

    # Scheduler
    check_interval_minutes: int = Field(30, env="CHECK_INTERVAL_MINUTES")
    enable_internal_scheduler: bool = Field(True, env="ENABLE_INTERNAL_SCHEDULER")

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
