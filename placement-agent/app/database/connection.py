"""
app/database/connection.py
──────────────────────────
Async SQLAlchemy engine + session factory.
Uses asyncpg driver for PostgreSQL.
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import get_settings
from app.database.models import Base

settings = get_settings()

engine = create_async_engine(
    settings.async_database_url,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,      # Detect stale connections
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create all tables on startup if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for database sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db_dep() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI-compatible async dependency for database sessions.
    Use with: session: AsyncSession = Depends(get_db_dep)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

