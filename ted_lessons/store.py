"""Data layer for lesson storage.

Provides two backends:
  - CSVStore: Phase 1, file-based, atomic writes via temp+rename
  - SQLiteStore: Phase 2+, concurrent-safe, full-text search ready

Both share the same interface so the rest of the app doesn't care which is active.
"""

from __future__ import annotations

import csv
import logging
import os
import sqlite3
import tempfile
from pathlib import Path

from .models import Lesson, CSV_COLUMNS

log = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_CSV_PATH = DEFAULT_DATA_DIR / "ted_ed_master_list.csv"
DEFAULT_SQLITE_PATH = DEFAULT_DATA_DIR / "lessons.db"


# ---------------------------------------------------------------------------
# Abstract interface (duck-typed — both stores implement these methods)
# ---------------------------------------------------------------------------
# load() -> None               (eager load from disk)
# save() -> None               (flush to disk)
# find(ted_slug, youtube_id, content_id) -> Lesson | None
# find_by_id(lesson_id) -> Lesson | None
# add_or_update(lesson) -> (Lesson, was_new)
# search(query) -> list[Lesson]
# needs_enrichment(retry_failed) -> list[Lesson]
# all_lessons() -> list[Lesson]
# __len__() -> int


# ═══════════════════════════════════════════════════════════════════════════
# CSV Store (Phase 1 — atomic writes via temp file + rename)
# ═══════════════════════════════════════════════════════════════════════════

class CSVStore:
    """CSV-backed lesson storage with dedup by ted_slug / youtube_id / content_id."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else DEFAULT_CSV_PATH
        self._lessons: list[Lesson] | None = None

    @property
    def lessons(self) -> list[Lesson]:
        if self._lessons is None:
            self._lessons = self._load()
        return self._lessons

    def all_lessons(self) -> list[Lesson]:
        return self.lessons

    def _load(self) -> list[Lesson]:
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
        """Atomic write: write to temp file, then rename over the target."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.path.parent), suffix=".csv.tmp", prefix=".lessons_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                writer.writeheader()
                for lesson in self.lessons:
                    writer.writerow(lesson.to_csv_row())
            os.replace(tmp_path, str(self.path))
            log.info("Saved %d lessons to %s", len(self.lessons), self.path)
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def find(self, ted_slug: str = "", youtube_id: str = "", content_id: str = "") -> Lesson | None:
        """Find by ted_slug (primary), youtube_id (secondary), content_id (tertiary)."""
        if ted_slug:
            for lesson in self.lessons:
                if lesson.ted_slug and lesson.ted_slug == ted_slug:
                    return lesson
        if youtube_id:
            for lesson in self.lessons:
                if lesson.youtube_id and lesson.youtube_id == youtube_id:
                    return lesson
        if content_id:
            for lesson in self.lessons:
                if lesson.content_id and lesson.content_id == content_id:
                    return lesson
        return None

    def find_by_id(self, lesson_id: str) -> Lesson | None:
        for lesson in self.lessons:
            if lesson.lesson_id == lesson_id:
                return lesson
        return None

    def add_or_update(self, lesson: Lesson) -> tuple[Lesson, bool]:
        existing = self.find(
            ted_slug=lesson.ted_slug, youtube_id=lesson.youtube_id,
            content_id=lesson.content_id,
        )
        if existing:
            merge_lesson(existing, lesson)
            return existing, False
        self.lessons.append(lesson)
        return lesson, True

    def search(self, query: str) -> list[Lesson]:
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
        results = []
        for lesson in self.lessons:
            needs_scrape = lesson.needs_scraping
            needs_transcript = lesson.needs_transcript
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


# ═══════════════════════════════════════════════════════════════════════════
# SQLite Store (Phase 2 — concurrent-safe, full-text search)
# ═══════════════════════════════════════════════════════════════════════════

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS lessons (
    lesson_id           TEXT PRIMARY KEY,
    ted_slug            TEXT,
    youtube_id          TEXT,
    content_id          TEXT,
    source_type         TEXT DEFAULT '',
    canonical_url       TEXT DEFAULT '',
    provider            TEXT DEFAULT '',
    provider_content_id TEXT DEFAULT '',
    title               TEXT DEFAULT '',
    collection          TEXT DEFAULT '',
    author              TEXT DEFAULT '',
    duration            TEXT DEFAULT '',
    views               TEXT DEFAULT '',
    category            TEXT DEFAULT '',
    ted_url             TEXT DEFAULT '',
    youtube_url         TEXT DEFAULT '',
    description         TEXT DEFAULT '',
    tags                TEXT DEFAULT '',
    transcript          TEXT DEFAULT '',
    transcript_status   TEXT DEFAULT '',
    scrape_status       TEXT DEFAULT '',
    last_enriched       TEXT DEFAULT '',
    error_message       TEXT DEFAULT '',
    extra_json          TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_ted_slug ON lessons(ted_slug);
CREATE INDEX IF NOT EXISTS idx_youtube_id ON lessons(youtube_id);
CREATE INDEX IF NOT EXISTS idx_content_id ON lessons(content_id);
CREATE INDEX IF NOT EXISTS idx_collection ON lessons(collection);
CREATE INDEX IF NOT EXISTS idx_title ON lessons(title);
CREATE INDEX IF NOT EXISTS idx_transcript_status ON lessons(transcript_status);
CREATE INDEX IF NOT EXISTS idx_scrape_status ON lessons(scrape_status);
"""


class SQLiteStore:
    """SQLite-backed lesson storage — concurrent-safe, full-text search ready."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else DEFAULT_SQLITE_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _init_db(self):
        self.conn.executescript(SQLITE_SCHEMA)
        self.conn.commit()

    def save(self):
        """Explicit commit (SQLite auto-commits per statement, but this ensures flush)."""
        self.conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def all_lessons(self) -> list[Lesson]:
        rows = self.conn.execute("SELECT * FROM lessons ORDER BY lesson_id").fetchall()
        return [self._row_to_lesson(r) for r in rows]

    def find(self, ted_slug: str = "", youtube_id: str = "", content_id: str = "") -> Lesson | None:
        """Find by ted_slug (primary), youtube_id (secondary), content_id (tertiary)."""
        if ted_slug:
            row = self.conn.execute(
                "SELECT * FROM lessons WHERE ted_slug = ?", (ted_slug,)
            ).fetchone()
            if row:
                return self._row_to_lesson(row)
        if youtube_id:
            row = self.conn.execute(
                "SELECT * FROM lessons WHERE youtube_id = ?", (youtube_id,)
            ).fetchone()
            if row:
                return self._row_to_lesson(row)
        if content_id:
            row = self.conn.execute(
                "SELECT * FROM lessons WHERE content_id = ?", (content_id,)
            ).fetchone()
            if row:
                return self._row_to_lesson(row)
        return None

    def find_by_id(self, lesson_id: str) -> Lesson | None:
        row = self.conn.execute(
            "SELECT * FROM lessons WHERE lesson_id = ?", (lesson_id,)
        ).fetchone()
        return self._row_to_lesson(row) if row else None

    def add_or_update(self, lesson: Lesson) -> tuple[Lesson, bool]:
        existing = self.find(
            ted_slug=lesson.ted_slug, youtube_id=lesson.youtube_id,
            content_id=lesson.content_id,
        )
        if existing:
            merge_lesson(existing, lesson)
            self._upsert(existing)
            return existing, False
        self._upsert(lesson)
        return lesson, True

    def _upsert(self, lesson: Lesson):
        """Insert or replace a lesson row."""
        d = lesson.to_csv_row()
        cols = list(d.keys())
        placeholders = ", ".join(["?"] * len(cols))
        col_names = ", ".join(cols)
        values = [d[c] for c in cols]
        self.conn.execute(
            f"INSERT OR REPLACE INTO lessons ({col_names}) VALUES ({placeholders})",
            values,
        )

    def search(self, query: str) -> list[Lesson]:
        # Use LIKE for substring search (upgradeable to FTS5 later)
        q = f"%{query}%"
        rows = self.conn.execute(
            """SELECT * FROM lessons WHERE
               lesson_id LIKE ? OR ted_slug LIKE ? OR title LIKE ?
               OR description LIKE ? OR category LIKE ? OR collection LIKE ?
               OR tags LIKE ? OR transcript LIKE ?
               ORDER BY lesson_id""",
            (q, q, q, q, q, q, q, q),
        ).fetchall()
        return [self._row_to_lesson(r) for r in rows]

    def needs_enrichment(self, retry_failed: bool = False) -> list[Lesson]:
        if retry_failed:
            rows = self.conn.execute(
                """SELECT * FROM lessons WHERE
                   (ted_url != '' AND scrape_status != 'ok')
                   OR (youtube_id != '' AND transcript_status NOT IN ('ok', 'unavailable'))"""
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT * FROM lessons WHERE
                   (ted_url != '' AND scrape_status NOT IN ('ok', 'failed'))
                   OR (youtube_id != '' AND transcript_status NOT IN ('ok', 'unavailable', 'failed'))"""
            ).fetchall()
        return [self._row_to_lesson(r) for r in rows]

    def __len__(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM lessons").fetchone()
        return row[0]

    @staticmethod
    def _row_to_lesson(row: sqlite3.Row) -> Lesson:
        valid_fields = {f.name for f in Lesson.__dataclass_fields__.values()}
        d = {k: row[k] for k in row.keys() if k in valid_fields}
        return Lesson(**d)


# ═══════════════════════════════════════════════════════════════════════════
# Shared merge logic
# ═══════════════════════════════════════════════════════════════════════════

def merge_lesson(existing: Lesson, incoming: Lesson):
    """Merge incoming data into existing lesson.

    Rules:
    - Only fill empty content fields (never overwrite existing data)
    - NEVER overwrite a successful transcript with empty/failed data
    - Re-derive IDs after merge
    """
    for field_name in [
        "title", "collection", "author", "duration", "views", "category",
        "ted_url", "youtube_url", "description", "tags",
    ]:
        existing_val = getattr(existing, field_name)
        incoming_val = getattr(incoming, field_name)
        if not existing_val and incoming_val:
            setattr(existing, field_name, incoming_val)

    # Transcript: only overwrite if existing is empty/failed and incoming is ok
    if incoming.transcript and incoming.transcript_status == "ok":
        if existing.transcript_status != "ok":
            existing.transcript = incoming.transcript
            existing.transcript_status = incoming.transcript_status

    existing.ensure_ids()


# ═══════════════════════════════════════════════════════════════════════════
# Factory: get the right store based on config
# ═══════════════════════════════════════════════════════════════════════════

def get_store(backend: str = "auto", path: str | Path | None = None) -> CSVStore | SQLiteStore:
    """Get a store instance.

    backend: "csv", "sqlite", or "auto" (sqlite if db exists or Phase 2, else csv)
    """
    if backend == "csv":
        return CSVStore(path or DEFAULT_CSV_PATH)
    if backend == "sqlite":
        return SQLiteStore(path or DEFAULT_SQLITE_PATH)

    # Auto: prefer sqlite if the db file exists, else csv
    sqlite_path = Path(path) if path and str(path).endswith(".db") else DEFAULT_SQLITE_PATH
    if sqlite_path.exists():
        return SQLiteStore(sqlite_path)
    csv_path = Path(path) if path and str(path).endswith(".csv") else DEFAULT_CSV_PATH
    return CSVStore(csv_path)


# Backwards compat alias
LessonStore = CSVStore
