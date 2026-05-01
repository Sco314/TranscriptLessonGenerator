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
import uuid
from dataclasses import dataclass, field, fields, asdict
from datetime import datetime, timezone
from typing import Any, Optional
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


# ---------------------------------------------------------------------------
# New CMS data model: SourceContent / GeneratedLesson / LessonArtifact
# ---------------------------------------------------------------------------
# These are the durable, post-reframe objects. SourceContent replaces Lesson
# as the unit of "raw / source material we have on file"; GeneratedLesson is
# the unit of "saved AI-generated lesson"; LessonArtifact tracks downloadable
# files (DOCX/PDF/etc) belonging to a generated lesson.
#
# Lesson stays in place as a legacy adapter for the existing TED/YouTube
# enrichment pipeline; SourceContent.from_lesson() bridges the two.


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_uuid() -> str:
    return str(uuid.uuid4())


# All Postgres columns for source_content, in canonical order.
SOURCE_CONTENT_COLUMNS = [
    "id", "source_type", "title", "author", "description", "category",
    "collection", "tags", "source_url", "ted_url", "youtube_url",
    "transcript_text", "pdf_text", "raw_text", "duration", "views",
    "ted_slug", "youtube_id", "content_id", "provider", "provider_content_id",
    "source_status", "scrape_status", "transcript_status", "last_enriched",
    "error_message", "extra_json", "created_at", "updated_at",
]


@dataclass
class SourceContent:
    """Raw or source material — TED/YouTube transcript, pasted text, or PDF.

    Identity in Postgres is the UUID `id`. For dedup against external content
    we use the unique pair (source_type, source_url) plus the legacy
    ted_slug / youtube_id / content_id columns inherited from Lesson.
    """

    # ── Identity ──
    id: str = ""
    source_type: str = ""              # 'ted_ed' | 'youtube' | 'pasted_text' | 'pdf'

    # ── Display fields ──
    title: str = ""
    author: str = ""
    description: str = ""
    category: str = ""
    collection: str = ""
    tags: str = ""

    # ── URLs ──
    source_url: str = ""               # canonical URL (whatever made sense for source_type)
    ted_url: str = ""
    youtube_url: str = ""

    # ── Body content (one of these will be the truth depending on source_type) ──
    transcript_text: str = ""
    pdf_text: str = ""
    raw_text: str = ""

    # ── Metadata ──
    duration: str = ""
    views: str = ""

    # ── Legacy provenance (mirrors Lesson) ──
    ted_slug: str = ""
    youtube_id: str = ""
    content_id: str = ""
    provider: str = ""
    provider_content_id: str = ""

    # ── Status ──
    source_status: str = ""            # 'ready' | 'partial' | 'needs_retry' | 'failed'
    scrape_status: str = ""
    transcript_status: str = ""
    last_enriched: str = ""
    error_message: str = ""

    # ── Extensibility ──
    extra_json: str = ""               # stored as jsonb in Postgres; serialized JSON text in-memory

    # ── Timestamps ──
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = _new_uuid()
        if not self.created_at:
            self.created_at = _utcnow_iso()
        if not self.updated_at:
            self.updated_at = self.created_at

        # Best-effort fill of legacy provenance from URLs.
        if self.ted_url and not self.ted_slug:
            self.ted_url = canonicalize_ted_url(self.ted_url)
            self.ted_slug = extract_ted_slug(self.ted_url)
        if self.youtube_url and not self.youtube_id:
            self.youtube_id = extract_video_id(self.youtube_url)

        # Derive source_type if it wasn't supplied.
        if not self.source_type:
            if self.ted_slug:
                self.source_type = "ted_ed"
            elif self.youtube_id:
                self.source_type = "youtube"
            elif self.pdf_text:
                self.source_type = "pdf"
            elif self.raw_text:
                self.source_type = "pasted_text"

        # Derive provider / provider_content_id.
        if self.source_type == "ted_ed" and not self.provider:
            self.provider = "ted-ed"
            self.provider_content_id = self.ted_slug
        elif self.source_type == "youtube" and not self.provider:
            self.provider = "youtube"
            self.provider_content_id = self.youtube_id

        # Derive canonical source_url.
        if not self.source_url:
            if self.source_type == "ted_ed" and self.ted_url:
                self.source_url = self.ted_url
            elif self.source_type == "youtube" and self.youtube_id:
                self.source_url = f"https://www.youtube.com/watch?v={self.youtube_id}"

        # content_id is a deterministic hash for fallback dedup.
        if not self.content_id and self.source_type and self.source_url:
            self.content_id = derive_content_id(self.source_type, self.source_url)

    # ── Body-text accessor: which text field is "the" content? ──

    @property
    def body_text(self) -> str:
        if self.transcript_text:
            return self.transcript_text
        if self.pdf_text:
            return self.pdf_text
        return self.raw_text

    @property
    def has_usable_body(self) -> bool:
        if self.source_type in ("ted_ed", "youtube"):
            return bool(self.transcript_text) and self.transcript_status == "ok"
        if self.source_type == "pdf":
            return bool(self.pdf_text)
        if self.source_type == "pasted_text":
            return bool(self.raw_text)
        return bool(self.body_text)

    @property
    def thumbnail_url(self) -> str:
        if self.youtube_id:
            return f"https://img.youtube.com/vi/{self.youtube_id}/mqdefault.jpg"
        return ""

    # ── Factories ──

    @classmethod
    def from_lesson(cls, lesson: "Lesson") -> "SourceContent":
        """Adapter from the legacy Lesson dataclass."""
        if lesson.ted_slug or lesson.ted_url:
            source_type = "ted_ed"
        elif lesson.youtube_id or lesson.youtube_url:
            source_type = "youtube"
        else:
            source_type = lesson.source_type or "ted_ed"

        source_url = (
            lesson.canonical_url
            or lesson.ted_url
            or lesson.youtube_url
            or ""
        )
        if not source_url and lesson.youtube_id:
            source_url = f"https://www.youtube.com/watch?v={lesson.youtube_id}"

        return cls(
            source_type=source_type,
            title=lesson.title,
            author=lesson.author,
            description=lesson.description,
            category=lesson.category,
            collection=lesson.collection,
            tags=lesson.tags,
            source_url=source_url,
            ted_url=lesson.ted_url,
            youtube_url=lesson.youtube_url,
            transcript_text=lesson.transcript,
            duration=lesson.duration,
            views=lesson.views,
            ted_slug=lesson.ted_slug,
            youtube_id=lesson.youtube_id,
            content_id=lesson.content_id,
            provider=lesson.provider,
            provider_content_id=lesson.provider_content_id,
            scrape_status=lesson.scrape_status,
            transcript_status=lesson.transcript_status,
            last_enriched=lesson.last_enriched,
            error_message=lesson.error_message,
            extra_json=lesson.extra_json,
        )

    @classmethod
    def from_ted_url(cls, url: str, collection: str = "") -> "SourceContent":
        canonical = canonicalize_ted_url(url)
        slug = extract_ted_slug(canonical)
        return cls(
            source_type="ted_ed",
            ted_url=canonical,
            ted_slug=slug,
            source_url=canonical,
            collection=collection,
        )

    @classmethod
    def from_youtube_url(cls, url: str) -> "SourceContent":
        vid = extract_video_id(url)
        canonical = f"https://www.youtube.com/watch?v={vid}" if vid else url
        return cls(
            source_type="youtube",
            youtube_url=canonical,
            youtube_id=vid,
            source_url=canonical,
        )

    @classmethod
    def from_pasted_text(cls, text: str, title: str = "") -> "SourceContent":
        return cls(
            source_type="pasted_text",
            raw_text=text,
            title=title or "Pasted text",
        )

    @classmethod
    def from_pdf(cls, text: str, title: str = "", source_url: str = "") -> "SourceContent":
        return cls(
            source_type="pdf",
            pdf_text=text,
            title=title or "PDF document",
            source_url=source_url,
        )

    # Mirror the duck-typed attributes activity_generator.build_briefing relies
    # on, so a SourceContent works wherever a Lesson did.

    @property
    def transcript(self) -> str:
        return self.transcript_text

    @property
    def lesson_id(self) -> str:
        # Some templates / log lines still call .lesson_id; keep them happy.
        return self.id

    def to_row(self) -> dict:
        d = asdict(self)
        return {col: d.get(col, "") for col in SOURCE_CONTENT_COLUMNS}

    def to_dict(self) -> dict:
        d = asdict(self)
        d["thumbnail_url"] = self.thumbnail_url
        d["body_text"] = self.body_text
        return d

    def touch(self):
        self.updated_at = _utcnow_iso()


@dataclass
class GeneratedLesson:
    """A saved lesson produced from a SourceContent.

    `lesson_json` is the worksheet spec the renderer walks. `lesson_html`
    is a pre-rendered HTML view of the same spec — enough to display the
    lesson in-browser without re-running Claude or even the DOCX engine.
    """

    id: str = ""
    source_content_id: str = ""

    lesson_type: str = ""              # 'general_employability_activity_sheet' for now
    title: str = ""
    grade_level: str = ""
    duration_minutes: int = 0

    # Durable content (lives in Supabase, NOT on local disk).
    lesson_json: Optional[dict] = None
    lesson_html: str = ""

    generation_status: str = ""        # 'pending' | 'running' | 'done' | 'failed'
    model_used: str = ""
    briefing_json: Optional[dict] = None
    notes: str = ""
    error_message: str = ""

    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = _new_uuid()
        if not self.created_at:
            self.created_at = _utcnow_iso()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> dict:
        return asdict(self)

    def touch(self):
        self.updated_at = _utcnow_iso()


@dataclass
class LessonArtifact:
    """A downloadable file belonging to a GeneratedLesson.

    Storage backend determines durability:
      - 'local'    — file on the running host's disk. NON-DURABLE on Render
                     free tier; will disappear on redeploy. The app must
                     handle the file being missing by regenerating from
                     `GeneratedLesson.lesson_json`.
      - 'supabase' — Supabase Storage object (future). Durable.
    """

    id: str = ""
    generated_lesson_id: str = ""
    artifact_type: str = ""            # 'docx' | 'pdf' | 'html' | 'answer_key' | 'teacher_guide'
    storage_backend: str = "local"     # 'local' | 'supabase'
    file_path_or_url: str = ""
    file_size_bytes: int = 0
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = _new_uuid()
        if not self.created_at:
            self.created_at = _utcnow_iso()

    def to_dict(self) -> dict:
        return asdict(self)
