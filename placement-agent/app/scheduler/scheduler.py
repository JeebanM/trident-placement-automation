"""
app/scheduler/scheduler.py
──────────────────────────
APScheduler setup.
Runs run_pipeline() every CHECK_INTERVAL_MINUTES in async mode.
"""
from datetime import datetime, timedelta

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
except ImportError:
    class AsyncIOScheduler:
        """Fallback stub for AsyncIOScheduler when apscheduler is not installed."""

        def __init__(self, *args, **kwargs):
            self._jobs = []

        def add_job(self, func, trigger=None, *args, **kwargs):
            self._jobs.append((func, trigger, kwargs))
            return self

        def start(self):
            pass

        def shutdown(self, wait=True):
            pass

from app.config.logging_config import get_logger
from app.config.settings import get_settings
from app.scheduler.pipeline import run_pipeline

logger = get_logger(__name__)


def get_scheduler() -> AsyncIOScheduler:
    """
    Creates and returns configured AsyncIOScheduler with run_pipeline
    as an interval job every settings.check_interval_minutes minutes.
    Also adds a 'startup_run' one-time date job that fires 5 seconds
    after now (immediate first run on startup). Returns the scheduler (not started).
    """
    settings = get_settings()
    scheduler = AsyncIOScheduler()

    # Recurring interval job
    scheduler.add_job(
        run_pipeline,
        trigger="interval",
        minutes=settings.check_interval_minutes,
        id="placement_pipeline_interval",
        name="Periodic Placement Monitoring",
        replace_existing=True,
    )

    # One-time startup run (5 seconds after now)
    startup_run_time = datetime.now() + timedelta(seconds=5)
    scheduler.add_job(
        run_pipeline,
        trigger="date",
        run_date=startup_run_time,
        id="startup_run",
        name="Startup Placement Monitoring Run",
        replace_existing=True,
    )

    logger.info(
        "scheduler.configured",
        interval_minutes=settings.check_interval_minutes,
        startup_run_at=startup_run_time.isoformat(),
    )

    return scheduler
