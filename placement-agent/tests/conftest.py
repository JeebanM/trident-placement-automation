"""
tests/conftest.py
─────────────────
Shared pytest fixtures for the Trident placement agent test suite.
"""
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.database.models import (
    EligibilityResult,
    ExtractedData,
    NotificationLog,
    PlacementPost,
)
from app.extraction.llm_extractor import PlacementExtraction


@pytest.fixture
def base_extraction() -> PlacementExtraction:
    """A default eligible PlacementExtraction for Jeeban (CSE, 2027, 8.26 CGPA)."""
    return PlacementExtraction(
        company="TCS",
        job_role="Software Engineer",
        job_type="Full-time",
        qualification=["B.Tech"],
        eligible_branches=["CSE", "IT"],
        branches_restricted=True,
        eligibility_raw_text="B.Tech CSE and IT students with min CGPA 7.0",
        graduation_years=[2027],
        minimum_cgpa=7.0,
        backlog_requirement="No active backlogs",
        salary="7 LPA",
        location=["Bangalore"],
        application_deadline="2026-10-15",
        application_url="https://forms.gle/test",
        notice_url="https://trident.ac.in/placementnotice/tcs-drive",
        confidence=0.88,
    )


@pytest.fixture
def mock_post() -> MagicMock:
    """Mock PlacementPost DB model."""
    post = MagicMock(spec=PlacementPost)
    post.id = 1
    post.title = "TCS Campus Drive 2027"
    post.post_url = "https://trident.ac.in/placementnotice/tcs-drive"
    post.processing_status = "done"
    return post


@pytest.fixture
def mock_extracted() -> MagicMock:
    """Mock ExtractedData DB model."""
    ext = MagicMock(spec=ExtractedData)
    ext.company = "TCS"
    ext.job_role = "Software Engineer"
    ext.job_type = "Full-time"
    ext.salary = "7 LPA"
    ext.location = ["Bangalore"]
    ext.minimum_cgpa = 7.0
    ext.graduation_years = [2027]
    ext.application_deadline = "2026-10-15"
    ext.application_url = "https://forms.gle/test"
    return ext


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Mock async SQLAlchemy session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.add = MagicMock()
    return session
