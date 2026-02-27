"""Enrichment orchestrator — takes a Lesson and fills all missing fields.

Handles partial success: stores whatever succeeded even if other parts fail.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .http_client import HttpClient
from .models import Lesson
from .scraper import scrape_ted_page
from .transcript import fetch_transcript

log = logging.getLogger(__name__)


def enrich(lesson: Lesson, client: HttpClient) -> Lesson:
    """Fill missing fields on a Lesson by scraping TED-Ed and YouTube.

    Mutates and returns the same Lesson object. Handles partial failure:
    - If TED scrape succeeds but transcript fails → lesson is still updated
    - If TED scrape fails → lesson.scrape_status = "failed"
    - Transcript failure → lesson.transcript_status = "failed"
    """
    # Step 1: Scrape TED-Ed page (if we have a URL and need data)
    if lesson.ted_url and lesson.scrape_status != "ok":
        _enrich_from_ted(lesson, client)

    # Step 2: Fetch transcript (if we have a YouTube ID and need it)
    lesson.ensure_ids()  # in case scraping populated youtube_url
    if lesson.youtube_id and lesson.transcript_status not in ("ok", "unavailable"):
        _enrich_transcript(lesson, client)

    lesson.last_enriched = datetime.now(timezone.utc).isoformat()
    return lesson


def _enrich_from_ted(lesson: Lesson, client: HttpClient):
    """Scrape the TED-Ed page and fill in missing fields."""
    log.info("Scraping TED-Ed page: %s", lesson.ted_url)
    try:
        data = scrape_ted_page(lesson.ted_url, client)
    except Exception as e:
        log.warning("TED scrape failed for %s: %s", lesson.ted_url, e)
        lesson.scrape_status = "failed"
        lesson.error_message = f"TED scrape: {e}"
        return

    # Fill only empty fields (never overwrite existing data)
    if not lesson.youtube_url and data.get("youtube_url"):
        lesson.youtube_url = data["youtube_url"]
    if not lesson.youtube_id and data.get("youtube_id"):
        lesson.youtube_id = data["youtube_id"]
    if not lesson.description and data.get("description"):
        lesson.description = data["description"]
    if not lesson.author and data.get("author"):
        lesson.author = data["author"]
    if not lesson.category and data.get("category"):
        lesson.category = data["category"]
    if not lesson.title and data.get("title"):
        lesson.title = data["title"]

    # If we got a YouTube URL, scrape was at least partially successful
    if data.get("youtube_url") or data.get("description"):
        lesson.scrape_status = "ok"
    else:
        lesson.scrape_status = "failed"
        lesson.error_message = "TED scrape returned no useful data"

    lesson.ensure_ids()


def _enrich_transcript(lesson: Lesson, client: HttpClient):
    """Fetch the YouTube transcript."""
    log.info("Fetching transcript for video: %s", lesson.youtube_id)
    try:
        result = fetch_transcript(lesson.youtube_id, client)
    except Exception as e:
        log.warning("Transcript fetch failed for %s: %s", lesson.youtube_id, e)
        lesson.transcript_status = "failed"
        lesson.error_message = f"Transcript: {e}"
        return

    lesson.transcript_status = result["status"]
    if result["status"] == "ok":
        lesson.transcript = result["text"]
        lesson.error_message = ""
    else:
        lesson.error_message = result.get("error", "Unknown transcript error")
