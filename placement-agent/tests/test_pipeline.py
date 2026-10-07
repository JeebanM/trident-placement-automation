"""
tests/test_pipeline.py
──────────────────────
Unit tests for the pipeline orchestrator (run_pipeline, _process_single_post).
All external I/O is mocked — no real HTTP, DB, or LLM calls.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.eligibility.rules_engine import EligibilityDecision
from app.extraction.llm_extractor import PlacementExtraction
from app.monitoring.fetcher import PostDetail, PostSummary
from app.scheduler.pipeline import _process_single_post, run_pipeline


@pytest.fixture
def mock_session():
    """Create an AsyncSession mock with working helper methods."""
    session = AsyncMock()

    def _mock_add(obj):
        if hasattr(obj, "id") and getattr(obj, "id", None) is None:
            obj.id = 1

    session.add = MagicMock(side_effect=_mock_add)
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    # Mock execute result
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    return session


@pytest.fixture
def sample_summary():
    """Create a sample PostSummary dataclass."""
    return PostSummary(
        title="TCS Campus Drive 2027",
        url="https://trident.ac.in/placementnotice/tcs-drive-2027/",
        published_date="October 7, 2026",
        snippet="TCS recruitment for 2027 batch B.Tech CSE",
        content_hash="abc123contenthash456",
    )


@pytest.mark.asyncio
@patch("app.scheduler.pipeline.fetch_listing_page")
@patch("app.scheduler.pipeline.is_new_post")
@patch("app.scheduler.pipeline.get_db")
async def test_run_pipeline_skips_seen_posts(
    mock_get_db,
    mock_is_new_post,
    mock_fetch_listing_page,
    mock_session,
    sample_summary,
):
    """Pipeline should skip posts that are already recorded in the database."""
    mock_fetch_listing_page.return_value = [sample_summary]
    mock_is_new_post.return_value = False

    mock_get_db.return_value.__aenter__.return_value = mock_session
    mock_get_db.return_value.__aexit__.return_value = None

    result = await run_pipeline()

    assert result["total"] == 1
    assert result["skipped"] == 1
    assert result["new"] == 0
    assert result["failed"] == 0
    assert "duration_seconds" in result


@pytest.mark.asyncio
@patch("app.scheduler.pipeline.fetch_listing_page")
async def test_run_pipeline_returns_stats_dict(mock_fetch_listing_page):
    """Pipeline should return the required stats dictionary keys when no posts exist."""
    mock_fetch_listing_page.return_value = []

    result = await run_pipeline()

    assert isinstance(result, dict)
    expected_keys = {"total", "new", "skipped", "failed", "duration_seconds"}
    assert expected_keys.issubset(result.keys())
    assert result["total"] == 0
    assert result["new"] == 0
    assert result["skipped"] == 0
    assert result["failed"] == 0


@pytest.mark.asyncio
@patch("app.scheduler.pipeline.fetch_listing_page")
async def test_run_pipeline_handles_fetch_error(mock_fetch_listing_page):
    """Pipeline should handle exceptions gracefully without raising unhandled errors."""
    mock_fetch_listing_page.side_effect = Exception("timeout")

    result = await run_pipeline()

    assert isinstance(result, dict)
    assert "failed" in result
    assert "total" in result
    assert "duration_seconds" in result


@pytest.mark.asyncio
@patch("app.scheduler.pipeline.is_new_post")
async def test_process_single_post_skips_old(
    mock_is_new_post,
    mock_session,
    sample_summary,
):
    """_process_single_post should return 'skipped' if change detection finds hash in DB."""
    mock_is_new_post.return_value = False

    result = await _process_single_post(mock_session, sample_summary, {})

    assert result == "skipped"
    mock_is_new_post.assert_awaited_once_with(mock_session, sample_summary.content_hash)


@pytest.mark.asyncio
@patch("app.scheduler.pipeline.is_new_post")
@patch("app.scheduler.pipeline.fetch_post_detail")
@patch("app.scheduler.pipeline.download_and_extract")
@patch("app.scheduler.pipeline.extract_placement_data")
@patch("app.scheduler.pipeline.check_eligibility")
@patch("app.scheduler.pipeline.send_notification")
async def test_process_single_post_processes_new(
    mock_send_notification,
    mock_check_eligibility,
    mock_extract_placement_data,
    mock_download_and_extract,
    mock_fetch_post_detail,
    mock_is_new_post,
    mock_session,
    sample_summary,
):
    """Full happy path: processes a new post end-to-end and sends notification."""
    mock_is_new_post.return_value = True

    mock_fetch_post_detail.return_value = PostDetail(
        title="TCS Drive",
        url="http://test.com",
        published_date="",
        full_text="TCS hiring CSE 2027",
        document_urls=[],
        application_urls=[],
        content_hash="abc123",
    )

    mock_extract_placement_data.return_value = PlacementExtraction(
        company="TCS",
        job_role="Software Engineer",
        job_type="Full-time",
        qualification=["B.Tech"],
        eligible_branches=["CSE"],
        branches_restricted=True,
        graduation_years=[2027],
        minimum_cgpa=7.0,
        backlog_requirement="No active backlogs",
        confidence=0.85,
    )

    mock_check_eligibility.return_value = EligibilityDecision(
        status="eligible",
        is_eligible=True,
        confidence=0.9,
        reason="Branch matched",
        rules_triggered=["branch_check"],
    )

    mock_send_notification.return_value = True

    result = await _process_single_post(mock_session, sample_summary, {})

    assert result == "processed"
    mock_is_new_post.assert_awaited_once_with(mock_session, sample_summary.content_hash)
    mock_fetch_post_detail.assert_awaited_once_with(sample_summary.url)
    mock_extract_placement_data.assert_awaited_once()
    mock_check_eligibility.assert_called_once()
    mock_send_notification.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.scheduler.pipeline.is_new_post")
@patch("app.scheduler.pipeline.fetch_post_detail")
@patch("app.scheduler.pipeline.extract_placement_data")
@patch("app.scheduler.pipeline.check_eligibility")
@patch("app.scheduler.pipeline.skip_notification")
async def test_process_single_post_ineligible_skips_notification(
    mock_skip_notification,
    mock_check_eligibility,
    mock_extract_placement_data,
    mock_fetch_post_detail,
    mock_is_new_post,
    mock_session,
    sample_summary,
):
    """Ineligible post should record skip_notification and return 'processed'."""
    mock_is_new_post.return_value = True

    mock_fetch_post_detail.return_value = PostDetail(
        title="Mechanical Only Drive",
        url="http://test.com/mech",
        published_date="",
        full_text="Only Mechanical students eligible",
        document_urls=[],
        application_urls=[],
        content_hash="mech456",
    )

    mock_extract_placement_data.return_value = PlacementExtraction(
        company="MechCorp",
        eligible_branches=["Mechanical"],
        branches_restricted=True,
        graduation_years=[2027],
        confidence=0.9,
    )

    mock_check_eligibility.return_value = EligibilityDecision(
        status="ineligible",
        is_eligible=False,
        confidence=0.95,
        reason="Branch mismatch: only Mechanical eligible",
        rules_triggered=["branch_check"],
    )

    mock_skip_notification.return_value = None

    result = await _process_single_post(mock_session, sample_summary, {})

    assert result == "processed"
    mock_skip_notification.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.scheduler.pipeline.is_new_post")
@patch("app.scheduler.pipeline.fetch_post_detail")
async def test_process_single_post_handles_exception(
    mock_fetch_post_detail,
    mock_is_new_post,
    mock_session,
    sample_summary,
):
    """Exception during post processing should be logged and return 'failed'."""
    mock_is_new_post.return_value = True
    mock_fetch_post_detail.side_effect = RuntimeError("Network error")

    result = await _process_single_post(mock_session, sample_summary, {})

    assert result == "failed"
