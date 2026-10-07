"""
app/eligibility/rules_engine.py
───────────────────────────────
Deterministic eligibility engine.
"""
from dataclasses import dataclass, field
import re
from typing import Optional

from app.config.logging_config import get_logger
from app.config.settings import load_candidate_config
from app.extraction.llm_extractor import PlacementExtraction

logger = get_logger(__name__)


@dataclass
class EligibilityDecision:
    status: str                        # "🟢 ELIGIBLE" | "🔴 NOT ELIGIBLE" | "🟡 REVIEW REQUIRED"
    is_eligible: Optional[bool]        
    confidence: float                  
    reason: str                        
    rules_triggered: list[str] = field(default_factory=list)


def _branch_matches(candidate_branches: list[str], notice_branches: list[str]) -> bool:
    cand_cleaned = [b.strip().lower() for b in candidate_branches if b and b.strip()]
    notice_cleaned = [b.strip().lower() for b in notice_branches if b and b.strip()]

    for c in cand_cleaned:
        for n in notice_cleaned:
            if c == n:
                return True
            if re.search(rf"\b{re.escape(c)}\b", n):
                return True
            if len(c) > 2 and c in n:
                return True
    return False


def check_eligibility(
    extraction: PlacementExtraction,
    candidate_config: Optional[dict] = None,
) -> EligibilityDecision:
    if candidate_config is None:
        try:
            candidate_config = load_candidate_config()
        except Exception as e:
            logger.warning("rules_engine.config_load_failed", error=str(e))
            candidate_config = {}

    candidate = candidate_config.get("candidate", candidate_config) if candidate_config else {}
    candidate_branches: list[str] = candidate.get("branch", ["CSE", "Computer Science and Engineering", "Computer Science", "CS"])
    if isinstance(candidate_branches, str):
        candidate_branches = [candidate_branches]

    candidate_grad_year: int = int(candidate.get("graduation_year", 2027))
    candidate_cgpa: float = float(candidate.get("cgpa", 8.26))
    candidate_backlogs: int = int(candidate.get("active_backlogs", 0))

    rules_triggered: list[str] = []
    pass_reasons: list[str] = []
    ineligible_reasons: list[str] = []
    review_reasons: list[str] = []

    # RULE 1: branch_check
    rules_triggered.append("branch_check")
    if not extraction.eligible_degrees:
        pass_reasons.append("no_branch_restriction: notice open to all branches or AI could not parse")
    else:
        if _branch_matches(candidate_branches, extraction.eligible_degrees):
            pass_reasons.append(f"Branch matched: candidate branch in notice eligible list ({', '.join(extraction.eligible_degrees)})")
        else:
            ineligible_reasons.append(f"Branch mismatch: notice restricted to [{', '.join(extraction.eligible_degrees)}], candidate branches are [{', '.join(candidate_branches)}]")

    # RULE 2: graduation_year_check
    if extraction.graduation_years:
        rules_triggered.append("graduation_year_check")
        if candidate_grad_year in extraction.graduation_years:
            pass_reasons.append(f"Graduation year matched: candidate {candidate_grad_year} in notice years {extraction.graduation_years}")
        else:
            ineligible_reasons.append(f"Graduation year mismatch: notice expects {extraction.graduation_years}, candidate graduates in {candidate_grad_year}")

    # RULE 3: cgpa_check
    if extraction.minimum_cgpa is not None:
        rules_triggered.append("cgpa_check")
        if candidate_cgpa >= extraction.minimum_cgpa:
            pass_reasons.append(f"CGPA requirement met: candidate {candidate_cgpa} >= minimum required {extraction.minimum_cgpa}")
        else:
            ineligible_reasons.append(f"CGPA below cutoff: candidate {candidate_cgpa} < minimum required {extraction.minimum_cgpa}")

    # RULE 4: backlog_check
    if extraction.backlog_allowed is not None:
        rules_triggered.append("backlog_check")
        if not extraction.backlog_allowed and candidate_backlogs > 0:
            ineligible_reasons.append(f"Backlog restriction violated: notice explicitly disallows backlogs, but candidate has {candidate_backlogs} active backlogs")
        elif extraction.backlog_allowed or candidate_backlogs == 0:
            pass_reasons.append(f"Backlog requirement satisfied.")

    # RULE 5: low_confidence_check
    if extraction.confidence < 0.4:
        rules_triggered.append("low_confidence_check")
        decision = EligibilityDecision(
            status="🟡 REVIEW REQUIRED",
            is_eligible=None,
            confidence=extraction.confidence,
            reason=f"AI extraction confidence ({extraction.confidence:.2f}) too low for auto-decision.",
            rules_triggered=rules_triggered,
        )
        logger.info("eligibility_checked", company=extraction.company_name, status=decision.status)
        return decision

    # Final Decision
    if ineligible_reasons:
        decision = EligibilityDecision(
            status="🔴 NOT ELIGIBLE",
            is_eligible=False,
            confidence=extraction.confidence,
            reason="; ".join(ineligible_reasons),
            rules_triggered=rules_triggered,
        )
    elif review_reasons:
        decision = EligibilityDecision(
            status="🟡 REVIEW REQUIRED",
            is_eligible=None,
            confidence=extraction.confidence,
            reason="; ".join(review_reasons),
            rules_triggered=rules_triggered,
        )
    else:
        decision = EligibilityDecision(
            status="🟢 ELIGIBLE",
            is_eligible=True,
            confidence=min(1.0, round(extraction.confidence + 0.1, 2)),
            reason="; ".join(pass_reasons) if pass_reasons else "All eligibility criteria satisfied",
            rules_triggered=rules_triggered,
        )

    logger.info("eligibility_checked", company=extraction.company_name, status=decision.status)
    return decision
