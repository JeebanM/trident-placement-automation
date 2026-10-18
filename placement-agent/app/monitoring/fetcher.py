"""
app/monitoring/fetcher.py
─────────────────────────
HTTP fetch layer for the Trident placement portal.
The site is WordPress-based static HTML — no Playwright needed.
Tenacity handles retries with exponential backoff automatically.
"""
import hashlib
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from tenacity import (
    retry,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config.logging_config import get_logger
from app.config.settings import load_candidate_config

logger = get_logger(__name__)

# ── Constants derived from live inspection of trident.ac.in ──────────────────
BASE_URL = "https://trident.ac.in/placementnotice/"
WP_POSTS_API_URL = "https://trident.ac.in/placementnotice/wp-json/wp/v2/posts?per_page=15"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://trident.ac.in/",
    "Sec-Ch-Ua": '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# File extensions to treat as downloadable documents
DOCUMENT_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".docx", ".doc", ".pptx", ".ppt"}


@dataclass
class PostSummary:
    """Lightweight post info extracted from the listing page."""
    title: str
    url: str
    published_date: str
    snippet: str
    content_hash: str


@dataclass
class PostDetail:
    """Full post content extracted from the individual post page."""
    title: str
    url: str
    published_date: str
    full_text: str
    document_urls: list[str]   # PDFs, XLSX, etc. — original URLs preserved
    application_urls: list[str]  # Google Forms, registration links, etc.
    content_hash: str


def _compute_hash(title: str, content: str, url: str) -> str:
    """
    SHA-256 fingerprint for deduplication.
    Normalized to be resilient to minor whitespace changes.
    """
    normalized = (
        title.lower().strip()
        + content.lower().strip()[:2000]
        + url.lower().strip()
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _is_document_url(url: str) -> bool:
    """Check if a URL points to a downloadable document."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    return any(path.endswith(ext) for ext in DOCUMENT_EXTENSIONS)


def _is_application_url(url: str) -> bool:
    """
    Identify registration / application links.
    e.g. Google Forms, Cognito Forms, college registration portals.
    """
    patterns = [
        "forms.gle", "docs.google.com/forms",
        "cognitoforms.com", "jotform.com",
        "typeform.com", "tinyurl.com",
        "bit.ly", "shorturl",
    ]
    return any(p in url.lower() for p in patterns)


def _is_retriable_http_error(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code in (403, 404):
            return False
    return isinstance(exc, (httpx.HTTPError, httpx.TimeoutException))


def get_async_client() -> httpx.AsyncClient:
    """
    Create an AsyncClient with proxy and browser headers configured.
    Respects PROXY_URL from settings or standard environment variables (HTTPS_PROXY / HTTP_PROXY).
    """
    effective_proxy = None
    try:
        from app.config.settings import get_settings
        settings = get_settings()
        effective_proxy = getattr(settings, "proxy_url", None)
    except Exception:
        pass

    if not effective_proxy:
        import os
        effective_proxy = os.getenv("PROXY_URL") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")

    client_kwargs = {
        "headers": HEADERS,
        "timeout": httpx.Timeout(30.0),
        "follow_redirects": True,
    }
    if effective_proxy:
        logger.info("fetcher.using_proxy", proxy=effective_proxy)
        client_kwargs["proxy"] = effective_proxy

    return httpx.AsyncClient(**client_kwargs)


async def _fetch_listing_via_api(client: httpx.AsyncClient) -> list[PostSummary]:
    """Fetch recent posts directly via WordPress REST API."""
    response = await client.get(WP_POSTS_API_URL, headers={"Accept": "application/json"})
    response.raise_for_status()
    items = response.json()
    if not isinstance(items, list):
        raise ValueError(f"Expected list from WP REST API, got {type(items)}")

    posts: list[PostSummary] = []
    for item in items:
        link = item.get("link", "").strip()
        title_raw = item.get("title", {}).get("rendered", "").strip()
        if not link or not title_raw:
            continue
        title = BeautifulSoup(title_raw, "html.parser").get_text(separator=" ", strip=True)
        date_str = item.get("date", "").strip()
        excerpt_raw = item.get("excerpt", {}).get("rendered", "").strip()
        snippet = BeautifulSoup(excerpt_raw, "html.parser").get_text(separator=" ", strip=True)[:300] if excerpt_raw else title
        content_hash = _compute_hash(title, snippet, link)
        posts.append(PostSummary(
            title=title,
            url=link,
            published_date=date_str,
            snippet=snippet,
            content_hash=content_hash,
        ))
    return posts


@retry(
    retry=retry_if_exception(_is_retriable_http_error),
    wait=wait_exponential(multiplier=1, min=30, max=300),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def fetch_listing_page(url: str = BASE_URL) -> list[PostSummary]:
    """
    Fetch the placement listing page and extract all post summaries.

    Trident's WordPress page structure:
      - Primary: WordPress REST API (/wp-json/wp/v2/posts)
      - Fallback: HTML parsing of article and heading tags

    Returns list of PostSummary sorted newest-first (as the site shows them).
    """
    logger.info("fetch_listing_page.start", url=url)

    async with get_async_client() as client:
        # If fetching default listing URL, prioritize clean WP REST API
        if url == BASE_URL:
            try:
                api_posts = await _fetch_listing_via_api(client)
                if api_posts:
                    logger.info("fetch_listing_page.api_success", count=len(api_posts))
                    return api_posts
            except Exception as api_err:
                logger.warning("fetch_listing_page.api_fallback", error=str(api_err))

        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as http_err:
            if http_err.response.status_code == 403:
                cf_ray = http_err.response.headers.get("cf-ray", "N/A")
                server = http_err.response.headers.get("server", "N/A")
                logger.error(
                    "fetch_listing_page.cloudflare_403_blocked",
                    url=url,
                    cf_ray=cf_ray,
                    server=server,
                    status_code=403,
                    hint="Cloudflare blocked runner IP. Switch GitHub Actions to a self-hosted runner or configure PROXY_URL.",
                )
            raise

    soup = BeautifulSoup(response.text, "lxml")
    posts: list[PostSummary] = []

    # ── Parse each post block from the listing ────────────────────────────────
    # Trident WordPress structure: article tags or divs containing h4 > a
    articles = soup.find_all("article")
    if not articles:
        # Fallback: find h4 tags with links (as observed in the live page)
        articles = soup.find_all("h4")

    for item in articles:
        # The first link is usually the category link. We need the title link.
        title_tag = item.find(["h2", "h3", "h4"], class_="entry-title") or item.find(["h2", "h3", "h4"])
        if not title_tag:
            continue
            
        link_tag = title_tag.find("a", href=True)
        if not link_tag:
            continue

        href = link_tag.get("href", "").strip()
        title = link_tag.get_text(separator=" ", strip=True)

        # Skip nav/category links — only process individual post URLs
        if not href.startswith("http") or \
           "category" in href or "page" in href or "wp-login" in href:
            continue

        # Extract date
        date_tag = item.find("time") or item.find("a", href=lambda h: h and "/2026/" in (h or "") or "/2025/" in (h or ""))
        published = date_tag.get_text(strip=True) if date_tag else ""

        # Extract snippet (first paragraph text near the post)
        snippet_tag = item.find("p")
        snippet = snippet_tag.get_text(strip=True)[:300] if snippet_tag else title

        content_hash = _compute_hash(title, snippet, href)

        posts.append(PostSummary(
            title=title,
            url=href,
            published_date=published,
            snippet=snippet,
            content_hash=content_hash,
        ))

    # De-duplicate by URL (WordPress listing pages can repeat links)
    seen_urls: set[str] = set()
    unique_posts: list[PostSummary] = []
    for p in posts:
        if p.url not in seen_urls:
            seen_urls.add(p.url)
            unique_posts.append(p)

    logger.info("fetch_listing_page.done", count=len(unique_posts))
    return unique_posts


@retry(
    retry=retry_if_exception(_is_retriable_http_error),
    wait=wait_exponential(multiplier=1, min=30, max=300),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def fetch_post_detail(post_url: str) -> PostDetail:
    """
    Fetch a single placement post page and extract:
    - Full text content
    - All document URLs (PDF, XLSX, etc.) — original URLs preserved
    - All application/registration links

    Based on live inspection of Trident WordPress posts:
    - Post content is in .entry-content or .post-content or the main article body
    - Documents are linked via <a href="...pdf"> or similar
    """
    logger.info("fetch_post_detail.start", url=post_url)

    async with get_async_client() as client:
        try:
            response = await client.get(post_url)
            response.raise_for_status()
        except httpx.HTTPStatusError as http_err:
            if http_err.response.status_code == 403:
                cf_ray = http_err.response.headers.get("cf-ray", "N/A")
                server = http_err.response.headers.get("server", "N/A")
                logger.error(
                    "fetch_post_detail.cloudflare_403_blocked",
                    url=post_url,
                    cf_ray=cf_ray,
                    server=server,
                    status_code=403,
                    hint="Cloudflare blocked runner IP. Switch GitHub Actions to a self-hosted runner or configure PROXY_URL.",
                )
            raise

    soup = BeautifulSoup(response.text, "lxml")

    # ── Extract title ─────────────────────────────────────────────────────────
    title_tag = (
        soup.find("h1", class_=lambda c: c and "title" in c.lower()) or
        soup.find("h1") or
        soup.find("h2")
    )
    title = title_tag.get_text(strip=True) if title_tag else post_url

    # ── Extract post date ─────────────────────────────────────────────────────
    time_tag = soup.find("time")
    published_date = time_tag.get_text(strip=True) if time_tag else ""

    # ── Extract main content ──────────────────────────────────────────────────
    # Try common WordPress content containers
    content_div = (
        soup.find("div", class_="entry-content") or
        soup.find("div", class_="post-content") or
        soup.find("div", class_="content") or
        soup.find("article") or
        soup.find("main")
    )

    if content_div:
        # Remove nav, comments, sidebar junk, and Related Posts
        for tag in content_div.find_all(["nav", "form", "aside", "footer"]):
            tag.decompose()
            
        # specifically target Trident's "Related Posts" and "Previous/Next" elements
        for related in content_div.find_all("div", class_=lambda c: c and ("related" in c.lower() or "nav-links" in c.lower() or "navigation" in c.lower())):
            related.decompose()
        # Also remove headers that say "Related Posts" and everything after them if they are at the end
        for h2 in content_div.find_all("h2"):
            if "related posts" in h2.get_text(strip=True).lower():
                # Remove the h2 and its following siblings
                for sibling in h2.find_next_siblings():
                    sibling.decompose()
                h2.decompose()

        full_text = content_div.get_text(separator="\n", strip=True)
    else:
        full_text = soup.get_text(separator="\n", strip=True)

    # ── Discover document URLs ────────────────────────────────────────────────
    document_urls: list[str] = []
    application_urls: list[str] = []

    all_links = soup.find_all("a", href=True)
    for link in all_links:
        href = link["href"].strip()

        # Make relative URLs absolute
        if href.startswith("/"):
            href = urljoin("https://trident.ac.in", href)

        if not href.startswith("http"):
            continue

        if _is_document_url(href):
            document_urls.append(href)
        elif _is_application_url(href):
            application_urls.append(href)

    # Deduplicate
    document_urls = list(dict.fromkeys(document_urls))
    application_urls = list(dict.fromkeys(application_urls))

    content_hash = _compute_hash(title, full_text, post_url)

    logger.info(
        "fetch_post_detail.done",
        url=post_url,
        docs=len(document_urls),
        app_links=len(application_urls),
    )

    return PostDetail(
        title=title,
        url=post_url,
        published_date=published_date,
        full_text=full_text,
        document_urls=document_urls,
        application_urls=application_urls,
        content_hash=content_hash,
    )
