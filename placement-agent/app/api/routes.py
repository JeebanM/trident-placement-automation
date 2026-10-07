"""
app/api/routes.py
─────────────────
FastAPI router with health check, manual trigger, and post listing endpoints.
Gives a simple HTTP interface to the placement agent.
"""
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config.logging_config import configure_logging, get_logger
from app.config.settings import get_settings
from app.database.connection import get_db_dep, init_db
from app.database.models import (
    EligibilityResult,
    ExtractedData,
    NotificationLog,
    PlacementDocument,
    PlacementPost,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["api"])


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/health")
async def health_check() -> dict[str, Any]:
    """
    Health check endpoint.
    Returns service health status and current UTC timestamp.
    """
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "trident-placement-agent",
    }


@router.post("/run-now")
async def run_now() -> dict[str, Any]:
    """
    Manually trigger placement monitoring pipeline.
    Imports run_pipeline dynamically to prevent circular imports.
    """
    try:
        from app.scheduler.pipeline import run_pipeline

        stats = await run_pipeline()
        triggered_at = datetime.now(timezone.utc).isoformat()
        response: dict[str, Any] = {"triggered_at": triggered_at}
        if isinstance(stats, dict):
            response.update(stats)
        else:
            response["stats"] = stats
        return response
    except Exception as e:
        logger.error("api.run_now.failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline execution failed: {str(e)}",
        )


@router.get("/posts")
async def list_posts(
    limit: int = Query(default=20, ge=1, le=100, description="Max posts to return (1-100)"),
    session: AsyncSession = Depends(get_db_dep),
) -> list[dict[str, Any]]:
    """
    List recent placement posts with their eligibility and notification status.
    Queries PlacementPost outerjoined with EligibilityResult, NotificationLog, and ExtractedData.
    """
    limit = min(max(1, limit), 100)
    stmt = (
        select(
            PlacementPost.id,
            PlacementPost.title,
            PlacementPost.post_url,
            PlacementPost.discovered_at,
            PlacementPost.processing_status,
            EligibilityResult.status.label("eligibility_status"),
            NotificationLog.status.label("notification_status"),
            ExtractedData.company_name.label("company"),
        )
        .outerjoin(EligibilityResult, PlacementPost.id == EligibilityResult.post_id)
        .outerjoin(NotificationLog, PlacementPost.id == NotificationLog.post_id)
        .outerjoin(ExtractedData, PlacementPost.id == ExtractedData.post_id)
        .order_by(desc(PlacementPost.discovered_at))
        .limit(limit)
    )
    result = await session.execute(stmt)
    rows = result.all()

    posts: list[dict[str, Any]] = []
    for row in rows:
        posts.append({
            "id": row.id,
            "title": row.title,
            "post_url": row.post_url,
            "discovered_at": row.discovered_at.isoformat() if row.discovered_at else None,
            "processing_status": row.processing_status,
            "eligibility_status": row.eligibility_status or "pending",
            "notification_status": row.notification_status or "pending",
            "company": row.company,
        })
    return posts


@router.get("/posts/{post_id}")
async def get_post_detail(
    post_id: int,
    session: AsyncSession = Depends(get_db_dep),
) -> dict[str, Any]:
    """
    Get full detail for a single placement post.
    Loads PlacementPost with ExtractedData, EligibilityResult, NotificationLog, and documents.
    """
    stmt = (
        select(PlacementPost)
        .where(PlacementPost.id == post_id)
        .options(
            selectinload(PlacementPost.extracted_data),
            selectinload(PlacementPost.eligibility_result),
            selectinload(PlacementPost.notification_log),
            selectinload(PlacementPost.documents),
        )
    )
    result = await session.execute(stmt)
    post = result.scalar_one_or_none()

    if post is None:
        raise HTTPException(
            status_code=404,
            detail=f"Placement post with ID {post_id} not found",
        )

    extracted_dict: dict[str, Any] | None = None
    if post.extracted_data:
        ext = post.extracted_data
        extracted_dict = {
            "id": ext.id,
            "company_name": ext.company_name,
            "program_name": ext.program_name,
            "job_role": ext.job_role,
            "job_type": ext.job_type,
            "location": ext.location,
            "eligible_degrees": ext.eligible_degrees,
            "minimum_10th_percentage": ext.minimum_10th_percentage,
            "minimum_12th_percentage": ext.minimum_12th_percentage,
            "minimum_cgpa": ext.minimum_cgpa,
            "graduation_years": ext.graduation_years,
            "backlog_allowed": ext.backlog_allowed,
            "salary": ext.salary,
            "notice_date": ext.notice_date,
            "application_deadline": ext.application_deadline,
            "application_link": ext.application_link,
            "notice_link": ext.notice_link,
            "eligibility_text": ext.eligibility_text,
            "structured_json": ext.structured_json,
            "llm_confidence": ext.llm_confidence,
            "extraction_model": ext.extraction_model,
            "extraction_attempts": ext.extraction_attempts,
            "extracted_at": ext.extracted_at.isoformat() if ext.extracted_at else None,
        }

    eligibility_dict: dict[str, Any] | None = None
    if post.eligibility_result:
        elig = post.eligibility_result
        eligibility_dict = {
            "id": elig.id,
            "status": elig.status,
            "is_eligible": elig.is_eligible,
            "confidence": elig.confidence,
            "reason": elig.reason,
            "rules_triggered": elig.rules_triggered,
            "evaluated_at": elig.evaluated_at.isoformat() if elig.evaluated_at else None,
        }

    notification_dict: dict[str, Any] | None = None
    if post.notification_log:
        notif = post.notification_log
        notification_dict = {
            "id": notif.id,
            "status": notif.status,
            "recipient": notif.recipient,
            "subject": notif.subject,
            "sent_at": notif.sent_at.isoformat() if notif.sent_at else None,
            "error_message": notif.error_message,
            "retry_count": notif.retry_count,
        }

    documents_list: list[dict[str, Any]] = []
    for doc in (post.documents or []):
        documents_list.append({
            "id": doc.id,
            "file_url": doc.file_url,
            "filename": doc.filename,
            "mime_type": doc.mime_type,
            "download_status": doc.download_status,
            "extraction_method": doc.extraction_method,
            "page_count": doc.page_count,
        })

    return {
        "id": post.id,
        "title": post.title,
        "post_url": post.post_url,
        "notice_hash": post.notice_hash,
        "raw_content": post.raw_content,
        "published_at": post.published_at.isoformat() if post.published_at else None,
        "discovered_at": post.discovered_at.isoformat() if post.discovered_at else None,
        "updated_at": post.updated_at.isoformat() if post.updated_at else None,
        "processing_status": post.processing_status,
        "extracted_data": extracted_dict,
        "eligibility_result": eligibility_dict,
        "notification_log": notification_dict,
        "documents": documents_list,
    }


# ── App Factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """
    FastAPI application factory.
    Configures logging, registers lifecycle event handlers, and mounts API router.
    """
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Trident Placement Agent",
        description="Auto-monitors Trident college placement portal and sends Gmail alerts",
        version="1.0.0",
    )

    @app.on_event("startup")
    async def startup():
        await init_db()
        # Start scheduler conditionally
        if settings.enable_internal_scheduler:
            try:
                from app.scheduler.scheduler import get_scheduler

                scheduler = get_scheduler()
                scheduler.start()
                app.state.scheduler = scheduler
                get_logger(__name__).info("app.startup.scheduler_started", env=settings.app_env)
            except Exception as e:
                get_logger(__name__).warning("app.startup.scheduler_not_started", error=str(e))
        else:
            get_logger(__name__).info("app.startup.scheduler_disabled", env=settings.app_env)

    @app.on_event("shutdown")
    async def shutdown():
        if hasattr(app.state, "scheduler"):
            try:
                app.state.scheduler.shutdown(wait=False)
            except Exception as e:
                get_logger(__name__).warning("app.shutdown.scheduler_failed", error=str(e))

    from app.api.routes import router as api_router

    app.include_router(api_router)

    return app
