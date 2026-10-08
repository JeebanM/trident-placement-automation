import pytest
from app.config.settings import Settings

def test_database_url_parsing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(
        database_url="postgresql://neondb_owner:pass@ep-tiny.c.aws.neon.tech/neondb?sslmode=require&channel_binding=require",
        gemini_api_key="test",
        gmail_sender="test",
        gmail_app_password="test",
        gmail_recipient="test",
        _env_file=None,
    )
    url, connect_args = settings.get_async_database_url_and_args()
    
    assert url == "postgresql+asyncpg://neondb_owner:pass@ep-tiny.c.aws.neon.tech/neondb"
    assert connect_args == {"ssl": "require"}

def test_database_url_parsing_no_sslmode(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(
        database_url="postgresql://user:pass@localhost:5432/db",
        gemini_api_key="test",
        gmail_sender="test",
        gmail_app_password="test",
        gmail_recipient="test",
        _env_file=None,
    )
    url, connect_args = settings.get_async_database_url_and_args()
    
    assert url == "postgresql+asyncpg://user:pass@localhost:5432/db"
    assert connect_args == {}

def test_database_url_parsing_multiple_params(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(
        database_url="postgresql://user:pass@localhost/db?options=-c%20search_path%3Dpublic&sslmode=require&channel_binding=require",
        gemini_api_key="test",
        gmail_sender="test",
        gmail_app_password="test",
        gmail_recipient="test",
        _env_file=None,
    )
    url, connect_args = settings.get_async_database_url_and_args()
    
    assert url == "postgresql+asyncpg://user:pass@localhost/db?options=-c+search_path%3Dpublic"
    assert connect_args == {"ssl": "require"}
