# TranscriptLessonGenerator — Implementation Plan (v2)

## Vision

A system where a teacher (or any user) can submit a TED-Ed lesson URL, a list
of URLs, or a collection URL through a web interface. The system:

1. Checks if the lesson already exists (by TED slug or YouTube video ID) → shows it immediately
2. If new → scrapes TED-Ed and YouTube for metadata + transcript
3. Generates a lesson document
4. Stores everything in the database (CSV Phase 1, SQLite Phase 2+)
5. Shows the lesson in a searchable, browseable web interface with thumbnails

---

## Key Design Decisions (from review feedback)

### Stable Identity — NOT title-based

Lessons are identified by **durable keys**, not titles (titles change, collide, break URLs):

1. **`ted_slug`** — extracted from TED URL: `ed.ted.com/lessons/{ted_slug}` (canonical)
2. **`youtube_id`** — 11-char video ID (secondary key)
3. **`lesson_id`** — the `ted_slug` if available, else `yt_{youtube_id}`, else a generated slug

Title is display-only. Deduplication checks `ted_slug` first, then `youtube_id`.

### Status Tracking Per Lesson

Every lesson carries processing status so the UI can show meaningful state:

```python
@dataclass
class Lesson:
    # ... content fields ...
    transcript_status: str = ""   # ok | missing | failed | unavailable | ""
    scrape_status: str = ""       # ok | failed | ""
    last_enriched: str = ""       # ISO timestamp of last enrichment attempt
    error_message: str = ""       # last failure reason
```

### Partial Success Is Normal

- TED scrape succeeds but transcript fails → **store lesson**, mark `transcript_status=failed`
- TED scrape fails entirely → **store URL stub**, mark `scrape_status=failed`
- Collections → **continue on errors**, don't abort the batch. Report per-lesson results.
- `--enrich` retries only `failed` items, skips `ok` and `unavailable`

### Storage Evolution

| Phase | Storage | Why |
|-------|---------|-----|
| Phase 1 | CSV | Simple, human-readable, git-diffable |
| Phase 2 | SQLite | Concurrent web submissions, full-text search, structured queries |
| Both | CSV export | Always available as `python -m ted_lessons --export-csv` |

The data layer (`store.py`) uses an abstract interface so the swap is one module change.

### Resilient HTTP

- Exponential backoff with jitter on 429/503 (1s, 2s, 4s, 8s max)
- Per-host rate limiting (TED: 1 req/sec, YouTube: 1 req/2sec)
- Cache fetched HTML during a run (don't re-fetch same page twice)
- Configurable delay between lessons (default 2s)

---

## Phase 1: Python CLI Pipeline

### Package Structure

```
ted_lessons/
├── __init__.py
├── __main__.py         # python -m ted_lessons entry point
├── models.py           # Lesson dataclass with stable IDs + status
├── store.py            # Data layer (CSV now, SQLite later)
├── scraper.py          # TED-Ed page scraping
├── transcript.py       # YouTube transcript (library → scrape → innertube)
├── enricher.py         # Orchestrator: URL → fully populated Lesson
├── http_client.py      # Shared requests.Session with backoff + rate limiting
└── cli.py              # Argparse CLI
```

### CLI Usage

```bash
# Add a single lesson by TED-Ed URL
python -m ted_lessons add https://ed.ted.com/lessons/the-prison-break-riddle

# Add multiple URLs (TED-Ed or YouTube)
python -m ted_lessons add url1 url2 url3

# Add from a file (one URL per line, blank lines and # comments ignored)
python -m ted_lessons add --file urls.txt

# Import an entire TED-Ed collection
python -m ted_lessons add --collection https://ed.ted.com/collections/public-speaking-101

# Re-enrich lessons with missing/failed fields
python -m ted_lessons enrich
python -m ted_lessons enrich --retry-failed    # retry transcript_status=failed too

# Browse the database
python -m ted_lessons list
python -m ted_lessons list --collection "Public Speaking 101"
python -m ted_lessons search "riddle"
python -m ted_lessons show the-prison-break-riddle   # by lesson_id/slug

# Export (always available even after SQLite migration)
python -m ted_lessons export --csv data/ted_ed_master_list.csv
```

### Module Details

#### `models.py`

```python
@dataclass
class Lesson:
    # Identity (durable keys)
    lesson_id: str = ""           # ted_slug or yt_{video_id}
    ted_slug: str = ""            # from URL: ed.ted.com/lessons/{this}
    youtube_id: str = ""          # 11-char video ID

    # Content (the 11-column schema)
    title: str = ""
    collection: str = ""          # TED-Ed collection name
    author: str = ""
    duration: str = ""            # "MM:SS"
    views: str = ""
    category: str = ""            # TED-Ed category
    ted_url: str = ""             # full ed.ted.com URL
    youtube_url: str = ""         # full youtube.com URL
    description: str = ""         # video/lesson description
    tags: str = ""                # tags and notes
    transcript: str = ""          # full text transcript

    # Status tracking
    transcript_status: str = ""   # ok | missing | failed | unavailable
    scrape_status: str = ""       # ok | failed
    last_enriched: str = ""       # ISO timestamp
    error_message: str = ""       # last failure reason
```

Factory methods:
- `Lesson.from_ted_url(url)` → extracts ted_slug, sets ted_url
- `Lesson.from_youtube_url(url)` → extracts youtube_id, sets youtube_url
- `Lesson.from_csv_row(row_dict)` → deserialize
- `lesson.to_csv_row()` → serialize

#### `store.py`

```python
class LessonStore:
    def load(self) -> list[Lesson]
    def save(self, lessons: list[Lesson])
    def find(self, ted_slug=None, youtube_id=None, title=None) -> Lesson | None
    def add_or_update(self, lesson: Lesson) -> tuple[Lesson, bool]  # (lesson, was_new)
    def search(self, query: str) -> list[Lesson]  # substring match on title/description/transcript
```

Phase 1 implementation: `CSVStore(path)` backed by `data/ted_ed_master_list.csv`.
Phase 2: `SQLiteStore(path)` backed by `data/lessons.db`.

Dedup logic in `find()`:
1. If `ted_slug` matches → same lesson
2. Else if `youtube_id` matches → same lesson
3. Else → new lesson

#### `scraper.py`

Port of the .gs `scrapeTedPage()`:
- `scrape_ted_page(url, session) → dict` with keys: youtube_url, youtube_id, description, author, category, title
- 4 YouTube URL regex patterns (iframe embed, watch, youtu.be, JSON video_id)
- 3 meta description patterns
- Author from `<meta name="author">` or parsed `og:title`
- Category from JSON `"category"` field

Also: `scrape_collection_page(url, session) → list[dict]`
- Scrape `ed.ted.com/collections/{slug}` for lesson URLs + titles
- Returns list of `{title, ted_url, duration, views, category}` (whatever the page provides)

#### `transcript.py`

```python
def fetch_transcript(video_id: str, session) -> dict:
    """Returns {text: str, segments: list, status: str, error: str}"""
```

Three methods tried in order:
1. `youtube-transcript-api` library (most robust, maintained)
2. Direct watch page scraping (port of .gs `fetchTranscriptFromYouTube`)
3. Innertube POST API (port of .gs `fetchCaptionTracksViaInnertube`)

Returns `status="ok"` with text, or `status="unavailable"` (no captions exist),
or `status="failed"` with error message.

#### `enricher.py`

```python
def enrich(lesson: Lesson, session, store) -> Lesson:
    """Fill all missing fields. Stores partial results on failure."""
```

Logic:
1. If `ted_url` present and `scrape_status != "ok"` → call `scrape_ted_page()`
2. If `youtube_url` present and `transcript_status` not in `("ok", "unavailable")` → call `fetch_transcript()`
3. Update `last_enriched` timestamp
4. Save to store (even on partial failure)
5. Return updated lesson

#### `http_client.py`

Shared `requests.Session` with:
- Browser-like User-Agent
- CONSENT cookie for YouTube
- Exponential backoff with jitter on 429/503/5xx
- Per-host rate limiting (configurable delays)
- Response caching within a run (LRU dict)

#### `cli.py`

Argparse with subcommands: `add`, `enrich`, `list`, `search`, `show`, `export`.
Pretty terminal output (lesson cards, status indicators, progress during enrichment).

---

## Phase 2: Web Interface

**Technology:** Flask (simple, well-known, easy to deploy)

### Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/` | GET | Browse all lessons — card grid with thumbnails, search bar |
| `/lesson/<lesson_id>` | GET | Lesson detail — metadata, embedded video, transcript |
| `/submit` | GET | Submit form — paste URLs |
| `/submit` | POST | Process submitted URLs, redirect to results |
| `/api/lessons` | GET | JSON list (supports `?q=` search, `?collection=` filter) |
| `/api/lessons/<lesson_id>` | GET | Single lesson JSON |
| `/api/submit` | POST | Submit URLs, returns JSON results |

Note: routes use `lesson_id` (the stable slug), not title.

### Thumbnails

Free, no API key: `https://img.youtube.com/vi/{youtube_id}/mqdefault.jpg`

### Storage

SQLite via `SQLiteStore` — handles concurrent web submissions without file corruption.
CSV export still available via CLI.

---

## Phase 3: Lesson Document Generation

Lock a v1 template early to avoid scope creep:
- **v1 template**: Title, author, collection, embedded video link, description, full transcript, TED-Ed quiz link
- Generated as HTML (viewable in browser, printable)
- PDF export optional (weasyprint or similar)
- AI-generated discussion questions are a v2 feature

---

## CSV Schema (Phase 1)

The CSV adds status columns beyond the original 11:

```
lesson_id,ted_slug,youtube_id,title,collection,author,duration,views,category,ted_url,youtube_url,description,tags,transcript,transcript_status,scrape_status,last_enriched,error_message
```

The original 11-column CSV (`data/ted_ed_master_list.csv`) is preserved as a
compatibility export. The working database CSV is `data/lessons.csv`.

---

## Implementation Order (Phase 1)

1. Repo housekeeping (.gitignore, requirements.txt, CLAUDE.md)
2. `ted_lessons/models.py`
3. `ted_lessons/store.py` (CSV implementation)
4. `ted_lessons/http_client.py`
5. `ted_lessons/scraper.py`
6. `ted_lessons/transcript.py`
7. `ted_lessons/enricher.py`
8. `ted_lessons/cli.py` + `__main__.py`
9. End-to-end test with real URLs
10. Commit + push
