"""
tests/test_notifications.py
───────────────────────────
Unit tests for Gmail notification module and HTML email generation.
"""
import pytest
from unittest.mock import MagicMock, patch

from app.notifications.email_sender import _build_html_email, _send_smtp
from app.database.models import PlacementPost, ExtractedData


def test_build_html_email_eligible():
    """Eligible status renders green header, company info, and notice link."""
    post = PlacementPost(
        id=1,
        title="TCS Drive 2027",
        post_url="https://trident.ac.in/placementnotice/tcs-drive/",
    )
    extracted = ExtractedData(
        post_id=1,
        company="TCS",
        job_role="SDE",
        salary="7 LPA",
        minimum_cgpa=7.0,
        graduation_years=[2027],
        location=["Bangalore"],
        application_deadline="Oct 15, 2026",
        application_url=None,
    )

    html = _build_html_email(
        post=post,
        extracted=extracted,
        eligibility_status="eligible",
        eligibility_reason="All criteria met",
    )

    assert "ELIGIBLE FOR PLACEMENT" in html
    assert "TCS" in html
    assert "SDE" in html
    assert "#16a34a" in html  # Green banner color
    assert "View Notice" in html
    assert "All criteria met" in html


def test_build_html_email_review():
    """Review status renders orange header and verify eligibility headline."""
    post = PlacementPost(
        id=2,
        title="Ambiguous Placement Notice",
        post_url="https://trident.ac.in/placementnotice/ambiguous/",
    )
    extracted = ExtractedData(
        post_id=2,
        company="StartUp Inc",
        job_role="Associate Engineer",
        salary="5 LPA",
        minimum_cgpa=6.5,
        graduation_years=[2027],
        location=["Bhubaneswar"],
        application_deadline=None,
        application_url=None,
    )

    html = _build_html_email(
        post=post,
        extracted=extracted,
        eligibility_status="review",
        eligibility_reason="Ambiguous backlog requirement",
    )

    assert "VERIFY ELIGIBILITY" in html
    assert "#ea580c" in html  # Orange banner color
    assert "Ambiguous backlog requirement" in html


def test_build_html_email_no_extracted_data():
    """When extracted is None, template renders safely with fallback placeholders."""
    post = PlacementPost(
        id=3,
        title="Raw Placement Notice Title",
        post_url="https://trident.ac.in/placementnotice/raw/",
    )

    html = _build_html_email(
        post=post,
        extracted=None,
        eligibility_status="eligible",
        eligibility_reason="Fallback review",
    )

    assert "Raw Placement Notice Title" in html
    assert "Not Specified" in html
    assert "View Notice" in html


def test_build_html_email_has_apply_button():
    """When application_url is present, Apply Now button with link is rendered."""
    post = PlacementPost(
        id=4,
        title="Google Campus Hiring 2027",
        post_url="https://trident.ac.in/placementnotice/google/",
    )
    extracted = ExtractedData(
        post_id=4,
        company="Google",
        job_role="Software Engineer",
        application_url="https://forms.gle/testApply123",
    )

    html = _build_html_email(
        post=post,
        extracted=extracted,
        eligibility_status="eligible",
        eligibility_reason="Direct match",
    )

    assert "Apply Now" in html
    assert "https://forms.gle/testApply123" in html


def test_send_smtp_calls_starttls():
    """_send_smtp connects via STARTTLS, authenticates, and dispatches message."""
    mock_settings = MagicMock()
    mock_settings.gmail_sender = "agent@trident.ac.in"
    mock_settings.gmail_app_password = "app-secret-password"
    mock_settings.gmail_recipient = "jeeban@example.com"

    with patch("app.notifications.email_sender.get_settings", return_value=mock_settings):
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_server

            _send_smtp(
                to="jeeban@example.com",
                subject="Test Alert",
                html_body="<p>Hello Jeeban</p>",
            )

            mock_smtp_cls.assert_called_once_with("smtp.gmail.com", 587, timeout=30)
            assert mock_server.starttls.called
            mock_server.login.assert_called_once_with("agent@trident.ac.in", "app-secret-password")
            assert mock_server.sendmail.called
            args, _ = mock_server.sendmail.call_args
            assert args[0] == "agent@trident.ac.in"
            assert args[1] == ["jeeban@example.com"]
