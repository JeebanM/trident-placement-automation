import asyncio
import os
import sys

from app.database.connection import engine
from app.database.models import Base

async def reset_db():
    print("Dropping all tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    print("Creating all tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database reset complete.")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(reset_db())
