"""Lesson data model with stable identifiers and status tracking."""

from __future__ import annotations

import re
from dataclasses import dataclass, fields, asdict
from urllib.parse import urlparse, parse_qs


# All CSV columns in canonical order
CSV_COLUMNS = [
    "lesson_id", "ted_slug", "youtube_id",
    "title", "collection", "author", "duration", "views", "category",
    "ted_url", "youtube_url", "description", "tags", "transcript",
    "transcript_status", "scrape_status", "last_enriched", "error_message",
]


@dataclass
class Lesson:
    """A single TED-Ed lesson with metadata, transcript, and processing status."""

    # Identity (durable keys — not title)
    lesson_id: str = ""
    ted_slug: str = ""
    youtube_id: str = ""

    # Content fields (the user-visible data)
    title: str = ""
    collection: str = ""
    author: str = ""
    duration: str = ""
    views: str = ""
    category: str = ""
    ted_url: str = ""
    youtube_url: str = ""
    description: str = ""
    tags: str = ""
    transcript: str = ""

    # Status tracking
    transcript_status: str = ""   # ok | missing | failed | unavailable
    scrape_status: str = ""       # ok | failed
    last_enriched: str = ""       # ISO timestamp
    error_message: str = ""       # last failure reason

    def __post_init__(self):
        """Derive identifiers if not set."""
        if self.ted_url and not self.ted_slug:
            self.ted_slug = extract_ted_slug(self.ted_url)
        if self.youtube_url and not self.youtube_id:
            self.youtube_id = extract_video_id(self.youtube_url)
        if not self.lesson_id:
            self.lesson_id = self._derive_lesson_id()

    def _derive_lesson_id(self) -> str:
        if self.ted_slug:
            return self.ted_slug
        if self.youtube_id:
            return f"yt_{self.youtube_id}"
        return ""

    def ensure_ids(self):
        """Re-derive IDs after fields are updated (e.g. after enrichment)."""
        if self.ted_url and not self.ted_slug:
            self.ted_slug = extract_ted_slug(self.ted_url)
        if self.youtube_url and not self.youtube_id:
            self.youtube_id = extract_video_id(self.youtube_url)
        if not self.lesson_id:
            self.lesson_id = self._derive_lesson_id()

    @classmethod
    def from_ted_url(cls, url: str, collection: str = "") -> Lesson:
        """Create a minimal Lesson from a TED-Ed lesson URL."""
        slug = extract_ted_slug(url)
        return cls(ted_url=url, ted_slug=slug, lesson_id=slug, collection=collection)

    @classmethod
    def from_youtube_url(cls, url: str) -> Lesson:
        """Create a minimal Lesson from a YouTube URL."""
        vid = extract_video_id(url)
        return cls(
            youtube_url=url,
            youtube_id=vid,
            lesson_id=f"yt_{vid}" if vid else "",
        )

    @classmethod
    def from_url(cls, url: str, collection: str = "") -> Lesson:
        """Create a Lesson from any URL (TED-Ed or YouTube)."""
        url = url.strip()
        if "ed.ted.com" in url:
            return cls.from_ted_url(url, collection=collection)
        if "youtube.com" in url or "youtu.be" in url:
            return cls.from_youtube_url(url)
        raise ValueError(f"Unrecognized URL format: {url}")

    @classmethod
    def from_csv_row(cls, row: dict) -> Lesson:
        """Deserialize from a CSV DictReader row."""
        valid_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in row.items() if k in valid_fields}
        return cls(**filtered)

    def to_csv_row(self) -> dict:
        """Serialize to a dict matching CSV_COLUMNS."""
        d = asdict(self)
        return {col: d.get(col, "") for col in CSV_COLUMNS}

    @property
    def thumbnail_url(self) -> str:
        """YouTube thumbnail URL (free, no API key)."""
        if self.youtube_id:
            return f"https://img.youtube.com/vi/{self.youtube_id}/mqdefault.jpg"
        return ""

    @property
    def needs_scraping(self) -> bool:
        return bool(self.ted_url) and self.scrape_status != "ok"

    @property
    def needs_transcript(self) -> bool:
        return bool(self.youtube_id) and self.transcript_status not in ("ok", "unavailable")

    def summary(self) -> str:
        """One-line summary for CLI output."""
        status_icons = {"ok": "+", "failed": "!", "unavailable": "-", "missing": "?"}
        ts = status_icons.get(self.transcript_status, " ")
        ss = status_icons.get(self.scrape_status, " ")
        title = self.title or self.lesson_id or "(untitled)"
        if len(title) > 60:
            title = title[:57] + "..."
        return f"[S:{ss} T:{ts}] {title}"


# ---------------------------------------------------------------------------
# URL parsing helpers
# ---------------------------------------------------------------------------

def extract_ted_slug(url: str) -> str:
    """Extract the lesson slug from a TED-Ed URL.

    Example: 'https://ed.ted.com/lessons/the-prison-break-riddle?lesson_collection=...'
    Returns: 'the-prison-break-riddle'
    """
    if not url:
        return ""
    parsed = urlparse(url)
    # Path like /lessons/the-prison-break-riddle
    m = re.search(r"/lessons/([^/?#]+)", parsed.path)
    return m.group(1) if m else ""


def extract_video_id(url: str) -> str:
    """Extract YouTube video ID from various URL formats."""
    if not url or not isinstance(url, str):
        return ""
    url = url.strip()
    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""
