"""TED-Ed page scraper — extracts YouTube URL, description, author, category.

Ported from the Google Apps Script scrapeTedPage() function with the same
regex patterns, plus BeautifulSoup for more robust meta tag extraction.
"""

from __future__ import annotations

import re
import logging

from bs4 import BeautifulSoup

from .http_client import HttpClient

log = logging.getLogger(__name__)


def scrape_ted_page(url: str, client: HttpClient) -> dict:
    """Scrape a TED-Ed lesson page for metadata.

    Returns dict with keys: youtube_url, youtube_id, description, author,
    category, title. Any value may be empty string.
    """
    result = {
        "youtube_url": "",
        "youtube_id": "",
        "description": "",
        "author": "",
        "category": "",
        "title": "",
    }

    html = client.get_text(url)
    if not html:
        log.warning("Failed to fetch TED-Ed page: %s", url)
        return result

    soup = BeautifulSoup(html, "html.parser")

    # --- YouTube URL (4 patterns, same order as the .gs) ---
    video_id = _extract_youtube_id(html)
    if video_id:
        result["youtube_url"] = f"https://www.youtube.com/watch?v={video_id}"
        result["youtube_id"] = video_id

    # --- Description ---
    result["description"] = _extract_description(soup)

    # --- Author ---
    result["author"] = _extract_author(soup)

    # --- Category ---
    cat_match = re.search(r'''["']category["']\s*:\s*["']([^"']+)["']''', html, re.IGNORECASE)
    if cat_match:
        result["category"] = _clean_text(cat_match.group(1))

    # --- Title (from og:title or <title>) ---
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        raw = og_title["content"].strip()
        # og:title is usually "Lesson Title - Author - TED-Ed"
        parts = raw.split(" - ")
        if parts:
            result["title"] = _clean_text(parts[0])
    if not result["title"]:
        title_tag = soup.find("title")
        if title_tag:
            raw = title_tag.get_text(strip=True)
            parts = raw.split(" | ")
            if parts:
                result["title"] = _clean_text(parts[0])

    return result


def scrape_collection_page(url: str, client: HttpClient) -> list[dict]:
    """Scrape a TED-Ed collection page for lesson URLs and basic metadata.

    Returns list of dicts with keys: ted_url, title, collection_name.
    """
    html = client.get_text(url)
    if not html:
        log.warning("Failed to fetch collection page: %s", url)
        return []

    soup = BeautifulSoup(html, "html.parser")
    lessons = []

    # Try to extract collection name from the page
    collection_name = ""
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        collection_name = og_title["content"].strip()
    if not collection_name:
        h1 = soup.find("h1")
        if h1:
            collection_name = h1.get_text(strip=True)

    # Find lesson links — TED-Ed collection pages have links to /lessons/{slug}
    seen_slugs = set()
    for link in soup.find_all("a", href=True):
        href = link["href"]
        match = re.search(r"/lessons/([^/?#]+)", href)
        if not match:
            continue
        slug = match.group(1)
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        # Build full URL
        if href.startswith("/"):
            ted_url = "https://ed.ted.com" + href.split("?")[0]
        elif href.startswith("http"):
            ted_url = href.split("?")[0]
        else:
            continue

        # Try to get title from the link text or nearby elements
        title = link.get_text(strip=True)
        if not title or len(title) < 3:
            # Look for a sibling or parent with more text
            parent = link.find_parent(["div", "li", "article"])
            if parent:
                heading = parent.find(["h2", "h3", "h4", "span"])
                if heading:
                    title = heading.get_text(strip=True)

        lessons.append({
            "ted_url": ted_url,
            "title": _clean_text(title) if title else "",
            "collection_name": collection_name,
        })

    log.info("Found %d lessons in collection '%s'", len(lessons), collection_name)
    return lessons


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_youtube_id(html: str) -> str:
    """Extract YouTube video ID from page HTML using 4 patterns."""
    # Pattern 1: iframe embed
    m = re.search(r"youtube\.com/embed/([a-zA-Z0-9_-]{11})", html)
    if m:
        return m.group(1)
    # Pattern 2: watch URL
    m = re.search(r"youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})", html)
    if m:
        return m.group(1)
    # Pattern 3: short URL
    m = re.search(r"youtu\.be/([a-zA-Z0-9_-]{11})", html)
    if m:
        return m.group(1)
    # Pattern 4: JSON video_id field
    m = re.search(r'''["']video_id["']\s*:\s*["']([a-zA-Z0-9_-]{11})["']''', html)
    if m:
        return m.group(1)
    return ""


def _extract_description(soup: BeautifulSoup) -> str:
    """Extract description from meta tags or page body."""
    # Strategy 1: meta name="description"
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return _clean_text(meta["content"])
    # Strategy 2: og:description
    og = soup.find("meta", attrs={"property": "og:description"})
    if og and og.get("content"):
        return _clean_text(og["content"])
    # Strategy 3: page body selectors
    for selector in [".lesson-description", ".talk-description", "[data-testid='description']"]:
        elem = soup.select_one(selector)
        if elem:
            return _clean_text(elem.get_text(strip=True))
    return ""


def _extract_author(soup: BeautifulSoup) -> str:
    """Extract author from meta tags."""
    # Strategy 1: meta name="author"
    meta = soup.find("meta", attrs={"name": "author"})
    if meta and meta.get("content"):
        author = meta["content"].strip()
        if author:
            return _clean_text(author)
    # Strategy 2: parse from og:title ("Lesson Title - Author - TED-Ed")
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        parts = og["content"].split(" - ")
        if len(parts) >= 2:
            candidate = parts[-1].strip()
            # Filter out generic values
            if candidate.lower() not in ("ted-ed", "lesson", "riddle") and len(candidate.split()) <= 5:
                return _clean_text(candidate)
            # Try second-to-last part
            if len(parts) >= 3:
                candidate = parts[-2].strip()
                if candidate.lower() not in ("ted-ed", "lesson", "riddle") and len(candidate.split()) <= 5:
                    return _clean_text(candidate)
    return ""


def _clean_text(text: str) -> str:
    """Collapse whitespace and strip."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()
