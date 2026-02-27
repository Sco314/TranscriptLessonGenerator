# TranscriptLessonGenerator

## What this project is

A tool for teachers to build a searchable database of TED-Ed lessons with
auto-fetched metadata and transcripts. Submit a TED-Ed URL → system scrapes
the TED page and YouTube for all metadata + full transcript → stores in a
lesson database.

## Architecture

- `ted_lessons/` — Python package (the core engine)
  - `models.py` — Lesson dataclass with stable IDs (ted_slug, youtube_id) and status tracking
  - `store.py` — Data layer (CSV now, SQLite later). Dedup by ted_slug then youtube_id.
  - `scraper.py` — Scrapes ed.ted.com pages for YouTube URL, description, author, category
  - `transcript.py` — Fetches YouTube transcripts (library → page scrape → Innertube fallback)
  - `enricher.py` — Orchestrator: takes a URL, fills all missing fields, handles partial failure
  - `http_client.py` — Shared requests session with backoff, rate limiting, caching
  - `cli.py` — CLI entry point (subcommands: add, enrich, list, search, show, export)
- `data/ted_ed_master_list.csv` — Master lesson database (source of truth)
- `TED_Ed_Master_List_Scripts_v4.gs` — Archived Google Apps Script (v5.0, kept for reference)
- `YouTubeTranscriptTEDEdDescriptionFetcher.py` — Archived Python script (stale column indices)

## Key design rules

- Lessons identified by ted_slug (from URL) or youtube_id — never by title
- Partial success is normal: store lesson even if transcript fails, track status per field
- Exponential backoff with jitter on HTTP errors; per-host rate limiting
- CSV is Phase 1 storage; SQLite planned for Phase 2 (web interface)
- The .gs file is reference only — all new development is in ted_lessons/

## Running

```bash
pip install -r requirements.txt
python -m ted_lessons add https://ed.ted.com/lessons/the-prison-break-riddle
python -m ted_lessons list
python -m ted_lessons enrich
```

## Column schema

lesson_id, ted_slug, youtube_id, title, collection, author, duration, views,
category, ted_url, youtube_url, description, tags, transcript,
transcript_status, scrape_status, last_enriched, error_message
