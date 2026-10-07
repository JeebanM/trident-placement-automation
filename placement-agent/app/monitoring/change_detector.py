"""
app/monitoring/change_detector.py
──────────────────────────────────
Determines whether a placement post is new or already seen.
Uses the content_hash stored in PostgreSQL as the source of truth.
Guarantees: same post → same hash → no duplicate processing.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.logging_config import get_logger
from app.database.models import PlacementPost

logger = get_logger(__name__)


async def is_new_post(session: AsyncSession, content_hash: str) -> bool:
    """
    Returns True if this content_hash has never been processed before.
    Single DB lookup — no scanning, no full-table comparison.
    """
    result = await session.execute(
        select(PlacementPost.id).where(PlacementPost.content_hash == content_hash)
    )
    row = result.scalar_one_or_none()
    is_new = row is None
    logger.debug("change_detector.check", hash=content_hash[:16], is_new=is_new)
    return is_new


async def is_already_notified(session: AsyncSession, post_id: int) -> bool:
    """
    Guard against duplicate email sends.
    Checks the notification_logs table — if a 'sent' record exists, skip.
    """
    from app.database.models import NotificationLog
    result = await session.execute(
        select(NotificationLog.id).where(
            NotificationLog.post_id == post_id,
            NotificationLog.status == "sent",
        )
    )
    already_sent = result.scalar_one_or_none() is not None
    logger.debug("change_detector.notify_check", post_id=post_id, already_sent=already_sent)
    return already_sent
