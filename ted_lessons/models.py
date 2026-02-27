"""Lesson data model with stable identifiers and status tracking.

Identity hierarchy:
  1. ted_slug (from TED-Ed URL) — preferred, human-readable
  2. youtube_id (11-char video ID) — secondary
  3. content_id: deterministic hash of (source_type, canonical_url)

Title is DISPLAY-ONLY and never used for dedup or routing.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, fields, asdict
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode


# All CSV/DB columns in canonical order
CSV_COLUMNS = [
    "lesson_id", "ted_slug", "youtube_id", "content_id",
    "source_type", "canonical_url", "provider", "provider_content_id",
    "title", "collection", "author", "duration", "views", "category",
    "ted_url", "youtube_url", "description", "tags", "transcript",
    "transcript_status", "scrape_status", "last_enriched", "error_message",
    "extra_json",
]


@dataclass
class Lesson:
    """A single TED-Ed lesson with metadata, transcript, and processing status."""

    # ── Identity (durable keys — NEVER title) ──
    lesson_id: str = ""
    ted_slug: str = ""
    youtube_id: str = ""
    content_id: str = ""              # sha256(source_type + canonical_url)[:16]

    # ── Source provenance (future-proof for non-TED/YouTube) ──
    source_type: str = ""             # "ted" | "youtube" | future providers
    canonical_url: str = ""           # normalized, stripped of tracking params
    provider: str = ""                # "ted-ed" | "youtube" | etc.
    provider_content_id: str = ""     # provider-specific ID (slug or video_id)

    # ── Content fields (user-visible data) ──
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

    # ── Status tracking ──
    transcript_status: str = ""       # ok | missing | failed | unavailable
    scrape_status: str = ""           # ok | failed
    last_enriched: str = ""           # ISO timestamp
    error_message: str = ""           # last failure reason

    # ── Extensibility ──
    extra_json: str = ""              # JSON text for ad-hoc fields

    def __post_init__(self):
        """Derive identifiers if not set."""
        if self.ted_url:
            self.ted_url = canonicalize_ted_url(self.ted_url)
            if not self.ted_slug:
                self.ted_slug = extract_ted_slug(self.ted_url)
        if self.youtube_url and not self.youtube_id:
            self.youtube_id = extract_video_id(self.youtube_url)
        self._derive_provenance()
        if not self.lesson_id:
            self.lesson_id = self._derive_lesson_id()
        if not self.content_id:
            self.content_id = self._derive_content_id()

    def _derive_provenance(self):
        """Set source_type/provider/provider_content_id from URLs."""
        if self.ted_slug and not self.source_type:
            self.source_type = "ted"
            self.provider = "ted-ed"
            self.provider_content_id = self.ted_slug
            if not self.canonical_url and self.ted_url:
                self.canonical_url = self.ted_url
        elif self.youtube_id and not self.source_type:
            self.source_type = "youtube"
            self.provider = "youtube"
            self.provider_content_id = self.youtube_id
            if not self.canonical_url:
                self.canonical_url = f"https://www.youtube.com/watch?v={self.youtube_id}"

    def _derive_lesson_id(self) -> str:
        if self.ted_slug:
            return f"ted_{self.ted_slug}"
        if self.youtube_id:
            return f"yt_{self.youtube_id}"
        if self.canonical_url:
            return derive_content_id(self.source_type, self.canonical_url)
        return ""

    def _derive_content_id(self) -> str:
        if self.source_type and self.canonical_url:
            return derive_content_id(self.source_type, self.canonical_url)
        if self.provider and self.provider_content_id:
            return derive_content_id(self.provider, self.provider_content_id)
        return ""

    def ensure_ids(self):
        """Re-derive IDs after fields are updated (e.g. after enrichment)."""
        if self.ted_url:
            self.ted_url = canonicalize_ted_url(self.ted_url)
            if not self.ted_slug:
                self.ted_slug = extract_ted_slug(self.ted_url)
        if self.youtube_url and not self.youtube_id:
            self.youtube_id = extract_video_id(self.youtube_url)
        self._derive_provenance()
        if not self.lesson_id:
            self.lesson_id = self._derive_lesson_id()
        if not self.content_id:
            self.content_id = self._derive_content_id()

    # ── Factory methods ──

    @classmethod
    def from_ted_url(cls, url: str, collection: str = "") -> Lesson:
        """Create a minimal Lesson from a TED-Ed lesson URL."""
        canonical = canonicalize_ted_url(url)
        slug = extract_ted_slug(canonical)
        return cls(
            ted_url=canonical, ted_slug=slug,
            lesson_id=f"ted_{slug}" if slug else "",
            collection=collection, source_type="ted", provider="ted-ed",
            provider_content_id=slug, canonical_url=canonical,
        )

    @classmethod
    def from_youtube_url(cls, url: str) -> Lesson:
        """Create a minimal Lesson from a YouTube URL."""
        vid = extract_video_id(url)
        canonical = f"https://www.youtube.com/watch?v={vid}" if vid else url
        return cls(
            youtube_url=canonical, youtube_id=vid,
            lesson_id=f"yt_{vid}" if vid else "",
            source_type="youtube", provider="youtube",
            provider_content_id=vid, canonical_url=canonical,
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

    def to_dict(self) -> dict:
        """Full dict representation (for JSON API responses)."""
        d = asdict(self)
        d["thumbnail_url"] = self.thumbnail_url
        return d

    # ── Properties ──

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
# URL canonicalization + ID derivation
# ---------------------------------------------------------------------------

def canonicalize_ted_url(url: str) -> str:
    """Normalize a TED-Ed URL: https scheme, ed.ted.com host, strip tracking params."""
    if not url:
        return ""
    parsed = urlparse(url)

    # Force https + ed.ted.com
    scheme = "https"
    netloc = parsed.netloc or "ed.ted.com"
    if netloc.startswith("www."):
        netloc = netloc[4:]

    # Strip trailing slashes from path
    path = parsed.path.rstrip("/")

    # Strip tracking/collection query params (keep only meaningful ones)
    params = parse_qs(parsed.query)
    # Remove known tracking params
    for tracking_key in ["lesson_collection", "utm_source", "utm_medium",
                         "utm_campaign", "ref", "fbclid", "gclid"]:
        params.pop(tracking_key, None)
    query = urlencode(params, doseq=True) if params else ""

    return urlunparse((scheme, netloc, path, "", query, ""))


def derive_content_id(source_type: str, canonical_url: str) -> str:
    """Deterministic content ID from (source_type, canonical_url).

    Returns first 16 chars of SHA-256 hex digest.
    """
    if not source_type or not canonical_url:
        return ""
    raw = f"{source_type}:{canonical_url}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def extract_ted_slug(url: str) -> str:
    """Extract the lesson slug from a TED-Ed URL.

    Example: 'https://ed.ted.com/lessons/the-prison-break-riddle?lesson_collection=...'
    Returns: 'the-prison-break-riddle'
    """
    if not url:
        return ""
    parsed = urlparse(url)
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
