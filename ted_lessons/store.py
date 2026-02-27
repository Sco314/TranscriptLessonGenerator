"""Data layer for lesson storage. CSV implementation (Phase 1), designed for SQLite swap."""

from __future__ import annotations

import csv
import logging
import os
from pathlib import Path

from .models import Lesson, CSV_COLUMNS

log = logging.getLogger(__name__)

DEFAULT_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "ted_ed_master_list.csv"


class LessonStore:
    """CSV-backed lesson storage with dedup by ted_slug / youtube_id."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else DEFAULT_CSV_PATH
        self._lessons: list[Lesson] | None = None

    @property
    def lessons(self) -> list[Lesson]:
        if self._lessons is None:
            self._lessons = self._load()
        return self._lessons

    def _load(self) -> list[Lesson]:
        """Read lessons from CSV."""
        if not self.path.exists():
            log.info("No CSV found at %s — starting empty", self.path)
            return []

        lessons = []
        with open(self.path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    lessons.append(Lesson.from_csv_row(row))
                except Exception as e:
                    log.warning("Skipping malformed row: %s", e)
        log.info("Loaded %d lessons from %s", len(lessons), self.path)
        return lessons

    def save(self):
        """Write all lessons to CSV."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for lesson in self.lessons:
                writer.writerow(lesson.to_csv_row())
        log.info("Saved %d lessons to %s", len(self.lessons), self.path)

    def find(self, ted_slug: str = "", youtube_id: str = "") -> Lesson | None:
        """Find a lesson by ted_slug (primary) or youtube_id (secondary)."""
        if ted_slug:
            for lesson in self.lessons:
                if lesson.ted_slug and lesson.ted_slug == ted_slug:
                    return lesson
        if youtube_id:
            for lesson in self.lessons:
                if lesson.youtube_id and lesson.youtube_id == youtube_id:
                    return lesson
        return None

    def find_by_id(self, lesson_id: str) -> Lesson | None:
        """Find a lesson by lesson_id."""
        for lesson in self.lessons:
            if lesson.lesson_id == lesson_id:
                return lesson
        return None

    def add_or_update(self, lesson: Lesson) -> tuple[Lesson, bool]:
        """Add a new lesson or update an existing one.

        Dedup order: ted_slug match → youtube_id match → new.
        Returns (lesson, was_new).
        """
        existing = self.find(ted_slug=lesson.ted_slug, youtube_id=lesson.youtube_id)
        if existing:
            _merge_into(existing, lesson)
            return existing, False
        self.lessons.append(lesson)
        return lesson, True

    def search(self, query: str) -> list[Lesson]:
        """Substring search across title, description, category, collection, transcript."""
        q = query.lower()
        results = []
        for lesson in self.lessons:
            searchable = " ".join([
                lesson.lesson_id, lesson.ted_slug, lesson.title,
                lesson.description, lesson.category, lesson.collection,
                lesson.tags, lesson.transcript,
            ]).lower()
            if q in searchable:
                results.append(lesson)
        return results

    def needs_enrichment(self, retry_failed: bool = False) -> list[Lesson]:
        """Return lessons that still need scraping or transcript fetching."""
        results = []
        for lesson in self.lessons:
            needs_scrape = lesson.needs_scraping
            needs_transcript = lesson.needs_transcript
            # By default, skip items with status=failed (they need --retry-failed)
            if not retry_failed:
                if lesson.scrape_status == "failed":
                    needs_scrape = False
                if lesson.transcript_status == "failed":
                    needs_transcript = False
            if needs_scrape or needs_transcript:
                results.append(lesson)
        return results

    def __len__(self) -> int:
        return len(self.lessons)


def _merge_into(existing: Lesson, incoming: Lesson):
    """Merge incoming data into existing lesson — only fill empty fields, never overwrite."""
    for field_name in [
        "title", "collection", "author", "duration", "views", "category",
        "ted_url", "youtube_url", "description", "tags", "transcript",
    ]:
        existing_val = getattr(existing, field_name)
        incoming_val = getattr(incoming, field_name)
        if not existing_val and incoming_val:
            setattr(existing, field_name, incoming_val)

    # Re-derive IDs in case we got new URLs
    existing.ensure_ids()
