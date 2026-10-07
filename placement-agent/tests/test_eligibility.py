"""
tests/test_eligibility.py
─────────────────────────
Unit tests for deterministic eligibility rules engine.
Tests all branch, graduation year, CGPA, backlog, and confidence rules.
"""
import pytest
from app.eligibility.rules_engine import check_eligibility, EligibilityDecision
from app.extraction.llm_extractor import PlacementExtraction

CANDIDATE_PROFILE = {
    "candidate": {
        "name": "Jeeban",
        "email": "jeebanmohanty45@gmail.com",
        "branch": ["CSE", "Computer Science and Engineering", "Computer Science", "CS"],
        "degree": ["B.Tech", "B.E."],
        "graduation_year": 2027,
        "cgpa": 8.26,
        "active_backlogs": 0,
    }
}


def make_extraction(**overrides) -> PlacementExtraction:
    """Helper fixture to create PlacementExtraction with realistic defaults."""
    defaults = dict(
        company="TCS",
        job_role="Software Engineer",
        job_type="Full-time",
        qualification=["B.Tech"],
        eligible_branches=["CSE", "IT"],
        branches_restricted=True,
        eligibility_raw_text="B.Tech CSE and IT students",
        graduation_years=[2027],
        minimum_cgpa=7.0,
        backlog_requirement="No active backlogs",
        salary="7 LPA",
        location=["Bangalore"],
        application_deadline="2026-10-15",
        application_url=None,
        notice_url=None,
        confidence=0.85,
    )
    defaults.update(overrides)
    return PlacementExtraction(**defaults)


def test_eligible_cse_all_rules_pass():
    """CSE branch, 2027 batch, CGPA 8.26, 0 backlogs -> eligible."""
    extraction = make_extraction()
    result = check_eligibility(extraction, candidate_config=CANDIDATE_PROFILE)

    assert result.status == "eligible"
    assert result.is_eligible is True
    assert "branch_check" in result.rules_triggered
    assert "graduation_year_check" in result.rules_triggered
    assert "cgpa_check" in result.rules_triggered
    assert "backlog_check" in result.rules_triggered
    assert "low_confidence_check" not in result.rules_triggered


def test_ineligible_wrong_branch():
    """Notice restricted to ECE and Mechanical -> ineligible due to branch mismatch."""
    extraction = make_extraction(
        eligible_branches=["ECE", "Mechanical"],
        branches_restricted=True,
    )
    result = check_eligibility(extraction, candidate_config=CANDIDATE_PROFILE)

    assert result.status == "ineligible"
    assert result.is_eligible is False
    assert "branch_check" in result.rules_triggered
    assert "Branch mismatch" in result.reason


def test_ineligible_wrong_graduation_year():
    """Notice expects 2026 batch, candidate is 2027 -> ineligible."""
    extraction = make_extraction(graduation_years=[2026])
    result = check_eligibility(extraction, candidate_config=CANDIDATE_PROFILE)

    assert result.status == "ineligible"
    assert result.is_eligible is False
    assert "graduation_year_check" in result.rules_triggered
    assert "Graduation year mismatch" in result.reason


def test_ineligible_cgpa_below_cutoff():
    """Notice requires 9.0 CGPA, candidate has 8.26 -> ineligible."""
    extraction = make_extraction(minimum_cgpa=9.0)
    result = check_eligibility(extraction, candidate_config=CANDIDATE_PROFILE)

    assert result.status == "ineligible"
    assert result.is_eligible is False
    assert "cgpa_check" in result.rules_triggered
    assert "CGPA below cutoff" in result.reason


def test_no_branch_restriction_eligible():
    """Notice open to all branches (branches_restricted=False) -> eligible."""
    extraction = make_extraction(
        branches_restricted=False,
        eligible_branches=[],
    )
    result = check_eligibility(extraction, candidate_config=CANDIDATE_PROFILE)

    assert result.status == "eligible"
    assert result.is_eligible is True
    assert "branch_check" in result.rules_triggered
    assert "no_branch_restriction" in result.reason


def test_review_on_low_confidence():
    """Low AI extraction confidence (< 0.4) -> status 'review'."""
    extraction = make_extraction(confidence=0.3)
    result = check_eligibility(extraction, candidate_config=CANDIDATE_PROFILE)

    assert result.status == "review"
    assert result.is_eligible is None
    assert "low_confidence_check" in result.rules_triggered
    assert "Manual review required" in result.reason


def test_review_on_restricted_but_no_branches_parsed():
    """Branch restriction indicated, but branches list empty -> status 'review'."""
    extraction = make_extraction(
        branches_restricted=True,
        eligible_branches=[],
    )
    result = check_eligibility(extraction, candidate_config=CANDIDATE_PROFILE)

    assert result.status == "review"
    assert result.is_eligible is None
    assert "branch_check" in result.rules_triggered
    assert "manual review required" in result.reason.lower()


def test_review_on_ambiguous_backlog():
    """Ambiguous backlog requirement -> status 'review' for safety."""
    extraction = make_extraction(
        backlog_requirement="Candidates with backlogs may apply",
    )
    result = check_eligibility(extraction, candidate_config=CANDIDATE_PROFILE)

    assert result.status == "review"
    assert result.is_eligible is None
    assert "backlog_check" in result.rules_triggered
    assert "Ambiguous backlog requirement" in result.reason


def test_no_cgpa_skips_cgpa_rule():
    """When minimum_cgpa is None, cgpa_check rule does not fire."""
    extraction = make_extraction(minimum_cgpa=None)
    result = check_eligibility(extraction, candidate_config=CANDIDATE_PROFILE)

    assert "cgpa_check" not in result.rules_triggered
    assert result.status == "eligible"


def test_no_graduation_year_skips_rule():
    """When graduation_years is empty, graduation_year_check rule does not fire."""
    extraction = make_extraction(graduation_years=[])
    result = check_eligibility(extraction, candidate_config=CANDIDATE_PROFILE)

    assert "graduation_year_check" not in result.rules_triggered
    assert result.status == "eligible"


def test_branch_case_insensitive():
    """Eligible branch matching is case insensitive (e.g. 'cse' matches candidate 'CSE')."""
    extraction = make_extraction(eligible_branches=["cse"])
    result = check_eligibility(extraction, candidate_config=CANDIDATE_PROFILE)

    assert result.status == "eligible"
    assert result.is_eligible is True
    assert "branch_check" in result.rules_triggered


def test_eligible_confidence_boosted():
    """Deterministic validation passes boost extraction confidence by 0.1 (capped at 1.0)."""
    extraction = make_extraction(confidence=0.8)
    result = check_eligibility(extraction, candidate_config=CANDIDATE_PROFILE)

    assert result.status == "eligible"
    assert result.confidence == 0.9
