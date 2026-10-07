import asyncio
import sys
import os

# Add current directory to path so it can find app module
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.config.logging_config import configure_logging, get_logger
from app.config.settings import get_settings
from app.database.connection import init_db
from app.scheduler.pipeline import run_pipeline

async def main():
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = get_logger(__name__)
    
    logger.info("Initializing database...")
    await init_db()
    
    logger.info("Running placement pipeline monitor...")
    try:
        stats = await run_pipeline()
        logger.info("Pipeline execution completed.", stats=stats)
    except Exception as e:
        logger.error("Pipeline execution failed.", error=str(e), exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
