"""
app/scheduler/pipeline.py
─────────────────────────
End-to-end placement monitoring pipeline.
"""
import asyncio
from datetime import datetime, timezone
import time
from typing import Optional
import hashlib
from dateutil import parser as date_parser

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.config.logging_config import get_logger
from app.config.settings import load_candidate_config
from app.database.connection import get_db
from app.database.models import (
    EligibilityResult,
    ExtractedData,
    PlacementDocument,
    PlacementPost,
    ProcessingLog,
    NotificationLog
)
from app.eligibility.rules_engine import check_eligibility
from app.extraction.llm_extractor import extract_placement_data
from app.extraction.pdf_extractor import download_and_extract
from app.monitoring.fetcher import BASE_URL, PostSummary, fetch_listing_page, fetch_post_detail
from app.notifications.email_sender import send_notification, skip_notification

logger = get_logger(__name__)


async def _log_step(session: AsyncSession, post_id: Optional[int], step: str, status: str, message: str, duration_ms: Optional[int] = None, error: Optional[str] = None) -> ProcessingLog:
    log_entry = ProcessingLog(post_id=post_id, step=step, status=status, message=message, duration_ms=duration_ms, error=error)
    session.add(log_entry)
    await session.flush()
    return log_entry


def is_expired(deadline_str: Optional[str]) -> bool:
    if not deadline_str:
        return False
    try:
        deadline_dt = date_parser.parse(deadline_str, fuzzy=True)
        if deadline_dt.tzinfo is None:
            deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
        return deadline_dt < datetime.now(timezone.utc)
    except Exception:
        return False # If we can't parse, consider deadline unknown and process it


async def run_pipeline() -> dict:
    start_time = time.perf_counter()
    logger.info("pipeline.run_pipeline.started")

    stats = {"total": 0, "new": 0, "skipped": 0, "failed": 0, "duration_seconds": 0.0}

    try:
        candidate_config = load_candidate_config()
        posts = await fetch_listing_page(BASE_URL)

        monitoring_cfg = candidate_config.get("monitoring", {}) if isinstance(candidate_config, dict) else {}
        max_posts_per_run = monitoring_cfg.get("max_posts_per_run", 15)

        posts_to_process = posts[:max_posts_per_run]
        stats["total"] = len(posts_to_process)
        
        async with get_db() as session:
            # Check if this is the first run
            count_res = await session.execute(select(func.count(PlacementPost.id)))
            total_posts_in_db = count_res.scalar()
            is_first_run = total_posts_in_db == 0

            new_posts = []

            for summary in posts_to_process:
                try:
                    # Fetch detail
                    detail = await fetch_post_detail(summary.url)
                    
                    # Create notice_hash
                    normalized_text = detail.full_text.strip().lower()
                    notice_hash = hashlib.sha256((summary.url + normalized_text).encode()).hexdigest()

                    # Detect New
                    stmt = select(PlacementPost).where(PlacementPost.notice_hash == notice_hash)
                    res = await session.execute(stmt)
                    existing_post = res.scalar_one_or_none()

                    if existing_post:
                        stats["skipped"] += 1
                        continue

                    # Process New Post
                    published_dt = None
                    if detail.published_date:
                        try: published_dt = date_parser.parse(detail.published_date)
                        except: pass

                    post = PlacementPost(title=detail.title, post_url=detail.url, notice_hash=notice_hash, raw_content=detail.full_text, published_at=published_dt, processing_status="processing")
                    session.add(post)
                    await session.flush()
                    
                    # Extract Docs
                    extracted_docs = []
                    for doc_url in detail.document_urls:
                        doc_res = await download_and_extract(doc_url)
                        if doc_res:
                            extracted_docs.append(doc_res)
                            session.add(PlacementDocument(post_id=post.id, file_url=doc_res.url, file_hash=doc_res.file_hash, filename=doc_res.filename, mime_type=doc_res.mime_type, extracted_text=doc_res.extracted_text, extraction_method=doc_res.extraction_method, page_count=doc_res.page_count, download_status="done" if doc_res.success else "failed", processing_status="done" if doc_res.success else "failed"))
                        else:
                            session.add(PlacementDocument(post_id=post.id, file_url=doc_url, download_status="failed", processing_status="failed"))
                    await session.flush()

                    pdf_texts = [doc.extracted_text for doc in extracted_docs if doc.extracted_text and doc.extracted_text.strip()]
                    combined_text = "\n\n".join([detail.full_text] + pdf_texts) if pdf_texts else detail.full_text

                    # Extract Data
                    all_doc_urls = list(dict.fromkeys(detail.document_urls + detail.application_urls))
                    extraction = await extract_placement_data(title=detail.title, notice_text=combined_text, post_url=detail.url, document_urls=all_doc_urls)
                    
                    extracted_data_row = ExtractedData(
                        post_id=post.id,
                        company_name=extraction.company_name,
                        program_name=extraction.program_name,
                        job_role=extraction.job_role,
                        job_type=extraction.job_type,
                        location=extraction.location,
                        eligible_degrees=extraction.eligible_degrees,
                        minimum_10th_percentage=extraction.minimum_10th_percentage,
                        minimum_12th_percentage=extraction.minimum_12th_percentage,
                        minimum_cgpa=extraction.minimum_cgpa,
                        graduation_years=extraction.graduation_years,
                        backlog_allowed=extraction.backlog_allowed,
                        salary=extraction.salary,
                        notice_date=extraction.notice_date,
                        application_deadline=extraction.application_deadline,
                        application_link=extraction.application_link,
                        notice_link=extraction.notice_link,
                        eligibility_text=extraction.eligibility_text,
                        structured_json=extraction.model_dump(),
                        llm_confidence=extraction.confidence,
                        extraction_model="gemini-3.1-flash-lite",
                        extraction_attempts=1,
                    )
                    session.add(extracted_data_row)
                    await session.flush()

                    # Validate & Rules Engine
                    decision = check_eligibility(extraction, candidate_config)
                    session.add(EligibilityResult(post_id=post.id, status=decision.status, is_eligible=decision.is_eligible, confidence=decision.confidence, reason=decision.reason, rules_triggered=decision.rules_triggered))
                    await session.flush()

                    post.processing_status = "done"
                    await session.flush()
                    
                    # Store post details for post-processing email logic
                    # Calculate proper sort date
                    sort_date = None
                    try:
                        if extraction.notice_date:
                            sort_date = date_parser.parse(extraction.notice_date, fuzzy=True)
                    except: pass
                    if not sort_date:
                        sort_date = post.published_at or datetime.now(timezone.utc)
                    
                    expired = is_expired(extraction.application_deadline)

                    new_posts.append({
                        'post_id': post.id,
                        'decision_status': decision.status,
                        'decision_reason': decision.reason,
                        'sort_date': sort_date,
                        'expired': expired
                    })
                    
                    stats["new"] += 1
                    
                    # Wait slightly to prevent rate limit on LLM
                    await asyncio.sleep(2)

                except Exception as exc:
                    await session.rollback()
                    stats["failed"] += 1
                    logger.error("pipeline.post_iteration.failed", url=summary.url, error=str(exc))
                    
            await session.commit()

            # Now, handle notifications
            if new_posts:
                # Sort active by notice_date DESC
                active_posts = [p for p in new_posts if not p['expired']]
                active_posts.sort(key=lambda x: x['sort_date'], reverse=True)

                if is_first_run:
                    # First run: latest 2 active notices sent, rest skipped
                    posts_to_send = active_posts[:2]
                    skipped_posts = active_posts[2:] + [p for p in new_posts if p['expired']]

                    for p in posts_to_send:
                        if p['decision_status'] in ("🟢 ELIGIBLE", "🟡 REVIEW REQUIRED"):
                            await send_notification(session, p['post_id'], p['decision_status'], p['decision_reason'])
                        else:
                            await skip_notification(session, p['post_id'], p['decision_reason'])

                    for p in skipped_posts:
                        await skip_notification(session, p['post_id'], "First run bulk load or expired")

                else:
                    # Recurring run: Check Notification History & Send all new non-expired
                    for p in new_posts:
                        if p['expired']:
                            await skip_notification(session, p['post_id'], "Deadline expired")
                        else:
                            if p['decision_status'] in ("🟢 ELIGIBLE", "🟡 REVIEW REQUIRED"):
                                await send_notification(session, p['post_id'], p['decision_status'], p['decision_reason'])
                            else:
                                await skip_notification(session, p['post_id'], p['decision_reason'])

    except Exception as pipeline_exc:
        logger.error("pipeline.run_pipeline.fatal_error", error=str(pipeline_exc), exc_info=True)
        raise

    stats["duration_seconds"] = round(time.perf_counter() - start_time, 2)
    return stats
