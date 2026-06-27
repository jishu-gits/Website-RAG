# backend/app/services/ingestion.py
"""Website ingestion pipeline.

- Accepts a list of seed URLs.
- Recursively crawls pages within the same domain (up to a configurable depth).
- Extracts clean text with BeautifulSoup, preserving metadata (URL, title, headings).
- Deduplicates content using a SHA‑256 hash of the cleaned text.
- Stores processed documents via the storage service.
- Robust error handling and progress reporting.
"""

import asyncio
import hashlib
from typing import List, Set, Dict, Any

import httpx
from bs4 import BeautifulSoup
from fastapi import HTTPException

from app.core.logger import logger
from app.services.storage import store_document

# ---------------------------------------------------------------------------
# Configuration (could be moved to Settings later)
# ---------------------------------------------------------------------------
MAX_CONCURRENT_REQUESTS = 10
MAX_CRAWL_DEPTH = 2  # Prevent infinite recursion

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
async def fetch_url(client: httpx.AsyncClient, url: str) -> str:
    """Fetch raw HTML for *url*.

    Raises:
        HTTPException – on network or HTTP errors.
    """
    try:
        response = await client.get(url, timeout=10.0)
        response.raise_for_status()
        return response.text
    except Exception as exc:
        logger.error("Failed to fetch URL", url=url, error=str(exc))
        raise HTTPException(status_code=502, detail=f"Failed to fetch {url}: {exc}")


def extract_metadata(html: str, url: str) -> Dict[str, Any]:
    """Parse *html* and return a dict with URL, title, headings, and clean text.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Drop unwanted tags
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    # Title
    title_tag = soup.title
    title = title_tag.get_text(strip=True) if title_tag else ""

    # Headings (h1‑h6)
    headings: List[str] = []
    for level in range(1, 7):
        for heading in soup.find_all(f"h{level}"):
            headings.append(heading.get_text(strip=True))

    # Main body text – prefer <body>
    body = soup.body
    text = body.get_text(separator=" ", strip=True) if body else soup.get_text(separator=" ", strip=True)

    return {
        "url": url,
        "title": title,
        "headings": headings,
        "text": text,
    }


def is_duplicate(doc: Dict[str, Any], seen_hashes: Set[str]) -> bool:
    """Check if *doc*'s text hash has been seen already.
    """
    content_hash = hashlib.sha256(doc["text"].encode("utf-8")).hexdigest()
    if content_hash in seen_hashes:
        return True
    seen_hashes.add(content_hash)
    return False

# ---------------------------------------------------------------------------
# Crawling logic
# ---------------------------------------------------------------------------
async def crawl_domain(
    seed_urls: List[str],
    max_depth: int = MAX_CRAWL_DEPTH,
) -> List[Dict[str, Any]]:
    """Recursively crawl *seed_urls* within their domain up to *max_depth*.
    Returns a list of extracted document dictionaries.
    """
    processed: List[Dict[str, Any]] = []
    seen_hashes: Set[str] = set()
    visited: Set[str] = set()
    pending: List[tuple[str, int]] = [(url, 0) for url in seed_urls]

    async with httpx.AsyncClient(
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; WebsiteRAGBot/1.0; +https://github.com/jishu-gits/Website-RAG)"
        },
    ) as client:
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

        async def worker(url: str, depth: int) -> List[tuple[str, int]]:
            async with semaphore:
                if url in visited or depth > max_depth:
                    return []
                visited.add(url)
                try:
                    html = await fetch_url(client, url)
                except HTTPException:
                    return []
                doc = extract_metadata(html, url)
                if is_duplicate(doc, seen_hashes):
                    logger.info("Duplicate document skipped", url=url)
                else:
                    await store_document(doc)
                    processed.append(doc)
                # Discover new internal links
                soup = BeautifulSoup(html, "html.parser")
                base_domain = httpx.URL(url).host
                new: List[tuple[str, int]] = []
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    try:
                        absolute = httpx.URL(href, base=url).join(url)
                    except Exception:
                        continue
                    if absolute.scheme not in ("http", "https"):
                        continue
                    if absolute.host != base_domain:
                        continue
                    clean = str(absolute)
                    if clean not in visited:
                        new.append((clean, depth + 1))
                return new

        while pending:
            tasks = [worker(u, d) for u, d in pending]
            results = await asyncio.gather(*tasks)
            # Flatten newly discovered URLs for the next iteration
            pending = [item for sublist in results for item in sublist]

    return processed

# ---------------------------------------------------------------------------
# Public API for FastAPI endpoint
# ---------------------------------------------------------------------------
async def ingest_urls(seed_urls: List[str]) -> Dict[str, Any]:
    """Entry point used by the FastAPI route.
    Returns a summary dict containing the number of processed documents and the
    full list of document metadata.
    """
    if not seed_urls:
        raise HTTPException(status_code=400, detail="No URLs provided")
    logger.info("Starting ingestion pipeline", seeds=seed_urls)
    documents = await crawl_domain(seed_urls)
    logger.info("Ingestion finished", total=len(documents))
    return {
        "total_documents": len(documents),
        "documents": documents,
    }
