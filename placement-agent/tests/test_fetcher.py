"""
tests/test_fetcher.py
─────────────────────
Unit tests for the Trident placement portal HTTP fetcher.
Tests hashing, URL classification, and async page fetching with mocked httpx.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.monitoring.fetcher import (
    fetch_listing_page,
    fetch_post_detail,
    _compute_hash,
    _is_document_url,
    _is_application_url,
    PostSummary,
    PostDetail,
)


def test_compute_hash_deterministic():
    """Same inputs produce identical SHA-256 hash, different inputs produce different hashes."""
    h1 = _compute_hash("TCS Drive 2027", "Recruitment notice content", "https://trident.ac.in/p1")
    h2 = _compute_hash("TCS Drive 2027", "Recruitment notice content", "https://trident.ac.in/p1")
    h3 = _compute_hash("Infosys Drive 2027", "Recruitment notice content", "https://trident.ac.in/p1")
    h4 = _compute_hash("TCS Drive 2027", "Different content", "https://trident.ac.in/p1")
    h5 = _compute_hash("TCS Drive 2027", "Recruitment notice content", "https://trident.ac.in/p2")

    assert h1 == h2
    assert len(h1) == 64
    assert h1 != h3
    assert h1 != h4
    assert h1 != h5


def test_compute_hash_normalized():
    """Hash is resilient to case and surrounding whitespace variations."""
    h_raw = _compute_hash(
        "TCS National Qualifier Test",
        "Registration is open for B.Tech CSE students.",
        "https://trident.ac.in/post/101",
    )
    h_padded = _compute_hash(
        "  tcs national qualifier test  ",
        "  registration is open for b.tech cse students.  ",
        "  https://trident.ac.in/post/101  ",
    )

    assert h_raw == h_padded


def test_is_document_url_pdf():
    """PDF URLs are recognized as downloadable documents."""
    assert _is_document_url("https://trident.ac.in/wp-content/uploads/2026/10/notice.pdf") is True
    assert _is_document_url("https://example.com/docs/TCS_ELIGIBILITY.PDF") is True


def test_is_document_url_xlsx():
    """Spreadsheet URLs (XLSX, XLS) are recognized as downloadable documents."""
    assert _is_document_url("https://trident.ac.in/files/shortlisted_students.xlsx") is True
    assert _is_document_url("https://trident.ac.in/files/candidate_list.xls") is True


def test_is_document_url_html():
    """Regular web pages (.html, or no extension) are not classified as documents."""
    assert _is_document_url("https://trident.ac.in/placementnotice/page.html") is False
    assert _is_document_url("https://trident.ac.in/placementnotice/tcs-drive/") is False


def test_is_application_url_google_forms():
    """Google Forms and common registration link patterns are recognized."""
    assert _is_application_url("https://forms.gle/abc123xyz") is True
    assert _is_application_url("https://docs.google.com/forms/d/e/1FAIpQLSc.../viewform") is True
    assert _is_application_url("https://cognitoforms.com/trident/apply") is True
    assert _is_application_url("https://tinyurl.com/trident-apply") is True


def test_is_application_url_random():
    """Non-registration URLs return False."""
    assert _is_application_url("https://example.com/apply") is False
    assert _is_application_url("https://trident.ac.in/about-us") is False


@pytest.mark.asyncio
async def test_fetch_listing_page_parses_posts():
    """fetch_listing_page parses WordPress article cards into PostSummary objects."""
    sample_html = """
    <html>
      <body>
        <article>
          <h4><a href="https://trident.ac.in/placementnotice/tcs-drive-2027/">TCS Recruitment Drive</a></h4>
          <time>October 05, 2026</time>
          <p>TCS is conducting a campus placement drive for 2027 batch B.Tech CSE students.</p>
        </article>
      </body>
    </html>
    """
    mock_resp = MagicMock()
    mock_resp.text = sample_html
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        posts = await fetch_listing_page("https://trident.ac.in/placementnotice/category/placementnotice/")

        assert len(posts) == 1
        assert posts[0].title == "TCS Recruitment Drive"
        assert posts[0].url == "https://trident.ac.in/placementnotice/tcs-drive-2027/"
        assert posts[0].published_date == "October 05, 2026"
        assert len(posts[0].content_hash) == 64


@pytest.mark.asyncio
async def test_fetch_post_detail_extracts_links():
    """fetch_post_detail extracts full body, document attachments, and application forms."""
    sample_detail_html = """
    <html>
      <body>
        <h1 class="entry-title">Wipro Elite NLTH 2027</h1>
        <time>October 06, 2026</time>
        <div class="entry-content">
          <p>Detailed eligibility criteria for Wipro hiring.</p>
          <a href="https://trident.ac.in/wp-content/uploads/notice.pdf">Download Notice PDF</a>
          <a href="https://forms.gle/sampleForm123">Apply on Google Forms</a>
        </div>
      </body>
    </html>
    """
    mock_resp = MagicMock()
    mock_resp.text = sample_detail_html
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        detail = await fetch_post_detail("https://trident.ac.in/placementnotice/wipro-elite-2027/")

        assert detail.title == "Wipro Elite NLTH 2027"
        assert "Detailed eligibility criteria" in detail.full_text
        assert "https://trident.ac.in/wp-content/uploads/notice.pdf" in detail.document_urls
        assert "https://forms.gle/sampleForm123" in detail.application_urls
