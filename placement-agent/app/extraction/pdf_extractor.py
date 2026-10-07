"""
app/extraction/pdf_extractor.py
────────────────────────────────
PDF download + text extraction pipeline.
Strategy:
  1. Download PDF bytes via httpx
  2. Try PyMuPDF text extraction (fast, accurate for digital PDFs)
  3. If extracted text is too short / garbled → flag for OCR (future extension)
  4. Preserve original URL throughout — never discarded
"""
import hashlib
import io
from dataclasses import dataclass

import fitz  # PyMuPDF
import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config.logging_config import get_logger

logger = get_logger(__name__)

# Minimum text length to consider extraction successful
MIN_TEXT_LENGTH = 50


@dataclass
class ExtractedDocument:
    url: str                  # Original URL — always preserved
    filename: str
    mime_type: str
    file_hash: str            # SHA-256 of raw bytes
    raw_bytes: bytes
    extracted_text: str
    extraction_method: str    # "text" | "ocr_needed" | "failed"
    page_count: int
    success: bool


@retry(
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    wait=wait_exponential(multiplier=1, min=15, max=120),
    stop=stop_after_attempt(2),
    reraise=False,
)
async def download_and_extract(url: str) -> ExtractedDocument | None:
    """
    Download a document from URL and extract its text content.
    Returns None if download fails after retries.
    """
    logger.info("pdf_extractor.download.start", url=url)

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(60.0),
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36"
                )
            },
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        raw_bytes = response.content
        content_type = response.headers.get("content-type", "")
        filename = _extract_filename(url, response)
        file_hash = hashlib.sha256(raw_bytes).hexdigest()

        logger.info(
            "pdf_extractor.download.done",
            url=url,
            size_kb=len(raw_bytes) // 1024,
            mime=content_type,
        )

        # ── Determine file type and extract ──────────────────────────────────
        if "pdf" in content_type.lower() or url.lower().endswith(".pdf"):
            extracted_text, method, page_count = _extract_pdf_text(raw_bytes)
        elif any(url.lower().endswith(ext) for ext in [".xlsx", ".xls"]):
            # Excel files — extract as plain text table representation
            extracted_text = _extract_xlsx_text(raw_bytes)
            method = "xlsx"
            page_count = 1
        else:
            extracted_text = ""
            method = "unsupported"
            page_count = 0

        return ExtractedDocument(
            url=url,
            filename=filename,
            mime_type=content_type,
            file_hash=file_hash,
            raw_bytes=raw_bytes,
            extracted_text=extracted_text,
            extraction_method=method,
            page_count=page_count,
            success=len(extracted_text) > MIN_TEXT_LENGTH,
        )

    except Exception as e:
        logger.error("pdf_extractor.download.failed", url=url, error=str(e))
        return None


def _extract_pdf_text(raw_bytes: bytes) -> tuple[str, str, int]:
    """
    Extract text from PDF bytes using PyMuPDF.
    Returns (text, method, page_count).
    method is "text" for digital PDFs, "ocr_needed" for scanned/image PDFs.
    """
    try:
        doc = fitz.open(stream=io.BytesIO(raw_bytes), filetype="pdf")
        pages_text: list[str] = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")  # type: ignore[arg-type]
            if text.strip():
                pages_text.append(f"[Page {page_num + 1}]\n{text.strip()}")

        doc.close()
        full_text = "\n\n".join(pages_text)

        if len(full_text.strip()) < MIN_TEXT_LENGTH:
            logger.warning("pdf_extractor.text.too_short", chars=len(full_text))
            return full_text, "ocr_needed", len(pages_text)

        return full_text, "text", len(pages_text)

    except Exception as e:
        logger.error("pdf_extractor.pymupdf.failed", error=str(e))
        return "", "failed", 0


def _extract_xlsx_text(raw_bytes: bytes) -> str:
    """
    Basic Excel extraction — returns a tab-separated text representation.
    Enough for the LLM to understand eligibility tables.
    """
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), read_only=True, data_only=True)
        lines: list[str] = []
        for sheet in wb.worksheets:
            lines.append(f"[Sheet: {sheet.title}]")
            for row in sheet.iter_rows(values_only=True):
                line = "\t".join(str(cell) if cell is not None else "" for cell in row)
                if line.strip():
                    lines.append(line)
        return "\n".join(lines)
    except Exception as e:
        logger.warning("pdf_extractor.xlsx.failed", error=str(e))
        return ""


def _extract_filename(url: str, response: httpx.Response) -> str:
    """Extract filename from Content-Disposition header or URL path."""
    cd = response.headers.get("content-disposition", "")
    if "filename=" in cd:
        return cd.split("filename=")[-1].strip().strip('"')
    # Fall back to URL path
    path = url.split("?")[0].rstrip("/")
    return path.split("/")[-1] or "document"
