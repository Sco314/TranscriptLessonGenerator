"""Import CSV exports of TED-Ed master lists into source_content.

Handles two flavors of CSV:
  1. Modern export from this app (CSV_COLUMNS schema).
  2. Legacy Apps Script export (looser column names like 'TED Lesson URL',
     'YouTube URL', 'Transcript', etc.).

Idempotent: dedups by (source_type, source_url). Returns counts of
inserted / updated / skipped / failed rows.
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from typing import Iterable

from ted_lessons.models import SourceContent

log = logging.getLogger(__name__)


# Map any of these header variants (case-insensitive, whitespace/_-stripped)
# to a canonical key.
_HEADER_ALIASES = {
    "title":            ["title"],
    "collection":       ["collection", "lesson_collection"],
    "author":           ["author", "creator"],
    "duration":         ["duration"],
    "views":            ["views"],
    "category":         ["category"],
    "description":      ["description"],
    "tags":             ["tags"],
    "transcript":       ["transcript", "transcript_text", "full_transcript"],
    "ted_url":          ["ted_url", "ted_lesson_url", "tedurl", "ted_ed_url"],
    "youtube_url":      ["youtube_url", "youtube_link", "youtube"],
    "transcript_status": ["transcript_status"],
    "scrape_status":    ["scrape_status"],
}


@dataclass
class ImportReport:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    @property
    def total(self) -> int:
        return self.inserted + self.updated + self.skipped + self.failed


def _norm(key: str) -> str:
    return (key or "").strip().lower().replace(" ", "_").replace("-", "_")


def _build_header_map(fieldnames: Iterable[str]) -> dict[str, str]:
    """Return {canonical_key: actual_csv_header} for the columns we recognize."""
    norm_to_actual = { _norm(name): name for name in fieldnames }
    out: dict[str, str] = {}
    for canonical, aliases in _HEADER_ALIASES.items():
        for alias in aliases:
            if alias in norm_to_actual:
                out[canonical] = norm_to_actual[alias]
                break
    return out


def _row_to_source(row: dict, header_map: dict[str, str]) -> SourceContent | None:
    def get(key: str) -> str:
        actual = header_map.get(key)
        if not actual:
            return ""
        return (row.get(actual) or "").strip()

    ted_url = get("ted_url")
    youtube_url = get("youtube_url")
    if not ted_url and not youtube_url:
        return None  # nothing to anchor on; skip

    if ted_url:
        src = SourceContent.from_ted_url(ted_url, collection=get("collection"))
    else:
        src = SourceContent.from_youtube_url(youtube_url)

    # Fill content fields from the row.
    if get("title"):
        src.title = get("title")
    if get("collection") and not src.collection:
        src.collection = get("collection")
    if get("author"):
        src.author = get("author")
    if get("duration"):
        src.duration = get("duration")
    if get("views"):
        src.views = get("views")
    if get("category"):
        src.category = get("category")
    if get("description"):
        src.description = get("description")
    if get("tags"):
        src.tags = get("tags")
    if get("transcript"):
        src.transcript_text = get("transcript")
        # If a status column wasn't supplied, infer 'ok' from a non-empty transcript.
        src.transcript_status = get("transcript_status") or "ok"
    if youtube_url and not src.youtube_url:
        src.youtube_url = youtube_url

    if get("scrape_status"):
        src.scrape_status = get("scrape_status")

    return src


def import_csv_text(text: str, store) -> ImportReport:
    """Read CSV text and import each row into `store` (a PostgresStore-like object).

    `store` must implement `add_or_update_source(SourceContent) -> (SourceContent, was_new)`.
    """
    report = ImportReport()
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        report.errors.append("CSV has no header row.")
        return report

    header_map = _build_header_map(reader.fieldnames)
    if "ted_url" not in header_map and "youtube_url" not in header_map:
        report.errors.append(
            "CSV has neither a TED URL nor a YouTube URL column."
        )
        return report

    for i, row in enumerate(reader, start=2):  # row 1 is the header
        try:
            src = _row_to_source(row, header_map)
            if src is None:
                report.skipped += 1
                continue
            _, was_new = store.add_or_update_source(src)
            if was_new:
                report.inserted += 1
            else:
                report.updated += 1
        except Exception as e:
            report.failed += 1
            msg = f"row {i}: {type(e).__name__}: {e}"
            report.errors.append(msg)
            log.exception("CSV import failed at row %d", i)
    return report


def import_csv_file(path: str, store) -> ImportReport:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return import_csv_text(f.read(), store)
