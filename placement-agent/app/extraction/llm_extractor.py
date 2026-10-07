"""
app/extraction/llm_extractor.py
────────────────────────────────
AI extraction layer using Google Gemini.
"""
import json
import re
from typing import Optional, Any
from datetime import datetime

import google.generativeai as genai
from pydantic import BaseModel, Field, field_validator, model_validator
from typing_extensions import Self

from app.config.logging_config import get_logger
from app.config.settings import get_settings

logger = get_logger(__name__)
settings = get_settings()

genai.configure(api_key=settings.gemini_api_key)
_model = genai.GenerativeModel("gemini-3.1-flash-lite")

class PlacementExtraction(BaseModel):
    company_name: Optional[str] = None
    program_name: Optional[str] = None
    job_role: Optional[str] = None
    job_type: Optional[str] = None
    location: Optional[list[str]] = Field(default_factory=list)
    eligible_degrees: Optional[list[str]] = Field(default_factory=list)
    minimum_10th_percentage: Optional[float] = None
    minimum_12th_percentage: Optional[float] = None
    minimum_cgpa: Optional[float] = None
    graduation_years: Optional[list[int]] = Field(default_factory=list)
    backlog_allowed: Optional[bool] = None
    salary: Optional[str] = None
    notice_date: Optional[str] = None
    test_date: Optional[str] = None
    application_deadline: Optional[str] = None
    application_link: Optional[str] = None
    notice_link: Optional[str] = None
    eligibility_text: Optional[str] = None
    
    # Field-level confidences and evidence
    field_confidences: dict = Field(default_factory=dict, exclude=True)
    extraction_evidence: dict = Field(default_factory=dict, exclude=True)
    confidence: float = Field(0.0, description="Overall confidence score")

    @field_validator("notice_date", "test_date", "application_deadline", mode="before")
    @classmethod
    def validate_dates(cls, v):
        if v is None:
            return None
        if isinstance(v, list):
            # Convert list of dates to a single string
            return ", ".join(str(item) for item in v if item)
        return str(v)

    @field_validator("minimum_cgpa", mode="before")
    @classmethod
    def validate_cgpa(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            v = v.lower().replace("cgpa", "").strip()
            try:
                v = float(v)
            except ValueError:
                return None
        if isinstance(v, (int, float)):
            if v < 0 or v > 10:
                return None # invalid cgpa
            return float(v)
        return None
        
    @field_validator("minimum_10th_percentage", "minimum_12th_percentage", mode="before")
    @classmethod
    def validate_percentage(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            v = v.replace("%", "").strip()
            try:
                v = float(v)
            except ValueError:
                return None
        if isinstance(v, (int, float)):
            if v < 0 or v > 100:
                return None
            return float(v)
        return None

    @field_validator("graduation_years")
    @classmethod
    def validate_years(cls, v):
        if not v:
            return []
        valid_years = [y for y in v if 1900 < y < 2100]
        return valid_years

    @model_validator(mode='after')
    def validate_business_logic(self) -> Self:
        # Penalize if company name is a greeting
        INVALID_COMPANY_VALUES = {"dear students", "dear candidates", "dear all", "hello students"}
        if self.company_name and self.company_name.lower().strip() in INVALID_COMPANY_VALUES:
            self.company_name = None
            if "company_name" in self.field_confidences:
                self.field_confidences["company_name"] = 0.0
                
        # Overall score from important fields
        critical_fields = ['company_name', 'eligible_degrees', 'minimum_cgpa', 'graduation_years', 'application_deadline']
        
        scores = []
        for field in critical_fields:
            if field in self.field_confidences:
                scores.append(self.field_confidences[field])
        
        self.confidence = sum(scores) / len(scores) if scores else 0.0
        return self


_EXTRACTION_PROMPT = """\
You are a placement notice parser.
Extract structured information from the placement notice below. Inspect paragraphs, tables, PDFs, and eligibility sections carefully.

IMPORTANT EXTRACTION RULES:
1. Never use greetings as company names.
   Examples: "Dear Students", "Dear Candidates", "Dear All", "Hello Students".
2. Never infer a company from the sender's display name alone.
3. PREFER THE OFFICIAL NOTICE TITLE/HEADER when identifying the company.
   If the title explicitly says "Alok Ingots (Mumbai) Private Limited", then the company is "Alok Ingots (Mumbai) Private Limited" EVEN IF another company like "DH Bars & Wires" is mentioned by mistake in a schedule table inside the body.
4. Always cross-check the body against the title to ignore obvious copy-paste typos from previous notices.
5. Extract dates from notice title, notice header, application deadline, registration instructions, and official notice body.
6. Distinguish between notice_date, test_date, and application_deadline.
7. Do not confuse an event/test date with an application deadline.
8. If a value is genuinely absent, return null.
9. Never fabricate missing information.

Return ONLY valid JSON matching this exact schema where EACH field is an object containing value, evidence, and confidence (0.0 to 1.0):
{{
  "company_name": {{"value": null, "evidence": null, "confidence": null}},
  "program_name": {{"value": null, "evidence": null, "confidence": null}},
  "job_role": {{"value": null, "evidence": null, "confidence": null}},
  "job_type": {{"value": null, "evidence": null, "confidence": null}},
  "location": {{"value": [], "evidence": null, "confidence": null}},
  "eligible_degrees": {{"value": [], "evidence": null, "confidence": null}},
  "minimum_10th_percentage": {{"value": null, "evidence": null, "confidence": null}},
  "minimum_12th_percentage": {{"value": null, "evidence": null, "confidence": null}},
  "minimum_cgpa": {{"value": null, "evidence": null, "confidence": null}},
  "graduation_years": {{"value": [], "evidence": null, "confidence": null}},
  "backlog_allowed": {{"value": null, "evidence": null, "confidence": null}},
  "salary": {{"value": null, "evidence": null, "confidence": null}},
  "notice_date": {{"value": null, "evidence": null, "confidence": null}},
  "test_date": {{"value": null, "evidence": null, "confidence": null}},
  "application_deadline": {{"value": null, "evidence": null, "confidence": null}},
  "application_link": {{"value": null, "evidence": null, "confidence": null}},
  "notice_link": {{"value": null, "evidence": null, "confidence": null}},
  "eligibility_text": {{"value": null, "evidence": null, "confidence": null}}
}}

NOTICE TITLE:
{notice_title}

NOTICE BODY:
{notice_text}

Return ONLY the JSON object. No explanation. No markdown.
"""


async def extract_placement_data(
    notice_text: str,
    post_url: str,
    document_urls: list[str] | None = None,
    max_retries: int = 2,
    title: str = "",
) -> PlacementExtraction:
    document_urls = document_urls or []
    truncated_text = notice_text[:8000] if len(notice_text) > 8000 else notice_text

    for attempt in range(1, max_retries + 2):
        try:
            prompt = _EXTRACTION_PROMPT.format(notice_title=title, notice_text=truncated_text)
            logger.info("llm_extractor.attempt", attempt=attempt, url=post_url)

            response = _model.generate_content(prompt)
            raw_text = response.text.strip()
            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
            raw_text = re.sub(r"\s*```$", "", raw_text)

            parsed = json.loads(raw_text)
            
            # Map raw JSON to standard PlacementExtraction
            extraction = PlacementExtraction()
            
            for key, field_data in parsed.items():
                if isinstance(field_data, dict):
                    val = field_data.get("value")
                    evidence = field_data.get("evidence")
                    conf = field_data.get("confidence")
                    
                    if key == "location" and val is None: val = []
                    if key == "eligible_degrees" and val is None: val = []
                    if key == "graduation_years" and val is None: val = []
                    
                    if hasattr(extraction, key):
                        setattr(extraction, key, val)
                        
                    extraction.field_confidences[key] = float(conf) if conf is not None else 0.0
                    extraction.extraction_evidence[key] = evidence
            
            # Re-run validation on the mapped model
            extraction = PlacementExtraction.model_validate(extraction.model_dump())

            if not extraction.notice_link and document_urls:
                extraction.notice_link = document_urls[0]
            if not extraction.application_link and document_urls:
                for url in document_urls:
                    if "forms.gle" in url or "docs.google.com/forms" in url:
                        extraction.application_link = url
                        break

            return extraction

        except json.JSONDecodeError as e:
            logger.warning("llm_extractor.json_error", attempt=attempt, error=str(e))
        except Exception as e:
            import traceback
            logger.warning("llm_extractor.error", attempt=attempt, error=str(e), tb=traceback.format_exc())

    logger.error("llm_extractor.all_retries_failed", url=post_url)
    return PlacementExtraction(
        company_name=_extract_company_from_title(title or notice_text)
    )

def _extract_company_from_title(text: str) -> str | None:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return lines[0][:200] if lines else None
