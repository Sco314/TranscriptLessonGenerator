# TranscriptLessonGenerator

## What this project is

A tool for teachers to build a searchable database of TED-Ed lessons with
auto-fetched metadata and transcripts. Submit a TED-Ed URL → system scrapes
the TED page and YouTube for all metadata + full transcript → stores in a
lesson database. Browse, search, and view printable lesson documents via a
web interface.

## Architecture

- `ted_lessons/` — Python package (the core engine)
  - `models.py` — Lesson dataclass with stable IDs (ted_slug, youtube_id, content_id) and status tracking. URL canonicalization and ID derivation helpers. Future-proofed with source_type, provider, canonical_url, extra_json.
  - `store.py` — Data layer with two backends: CSVStore (atomic writes via temp+rename) and SQLiteStore (concurrent-safe, WAL mode, indexed). Factory function `get_store()` auto-selects.
  - `scraper.py` — Scrapes ed.ted.com pages for YouTube URL, description, author, category. Also scrapes collection pages.
  - `transcript.py` — Fetches YouTube transcripts with 3 fallbacks: youtube-transcript-api library → page scrape → Innertube POST API.
  - `enricher.py` — Orchestrator: takes a URL, fills all missing fields. Handles partial failure. Never overwrites a successful transcript with a failed attempt.
  - `http_client.py` — Shared requests session with exponential backoff + jitter, per-host rate limiting, response caching.
  - `cli.py` — CLI entry point (subcommands: add, enrich, list, search, show, export, migrate)
- `web/` — Flask web application (Phase 2)
  - `app.py` — Routes: browse (/), lesson detail (/lesson/<lesson_id>), submit (/submit), printable document (/lesson/<id>/document), JSON API (/api/*)
  - `templates/` — Jinja2 templates (base, index, lesson, submit, results, document, 404)
  - `static/style.css` — Clean, minimal CSS with TED-red accent
- `data/ted_ed_master_list.csv` — CSV database (Phase 1 default)
- `data/lessons.db` — SQLite database (Phase 2 default, gitignored)
- `scripts/migrate_csv_to_sqlite.py` — CSV → SQLite migration with dedup
- `TED_Ed_Master_List_Scripts_v4.gs` — Archived Google Apps Script (v5.0, kept for reference)
- `YouTubeTranscriptTEDEdDescriptionFetcher.py` — Archived Python script (stale column indices)

## Key design rules

- Lessons identified by ted_slug (from URL) or youtube_id — NEVER by title
- Dedup order: ted_slug match → youtube_id match → new lesson
- Partial success is normal: store lesson even if transcript fails, track status per field
- Never overwrite a successful transcript with a failed attempt
- Exponential backoff with jitter on HTTP errors; per-host rate limiting
- Web routes use lesson_id (stable slug), never title
- CSV is Phase 1 storage; SQLite is Phase 2 default (auto-selected by get_store())
- The .gs file is reference only — all new development is in ted_lessons/ and web/

## Running

```bash
# Install
pip install -r requirements.txt

# CLI usage
python -m ted_lessons add https://ed.ted.com/lessons/the-prison-break-riddle
python -m ted_lessons list
python -m ted_lessons enrich
python -m ted_lessons search "riddle"
python -m ted_lessons migrate              # CSV → SQLite

# Web app
python web/app.py                          # runs on http://localhost:5000
```

## Column schema

lesson_id, ted_slug, youtube_id, content_id, source_type, canonical_url,
provider, provider_content_id, title, collection, author, duration, views,
category, ted_url, youtube_url, description, tags, transcript,
transcript_status, scrape_status, last_enriched, error_message, extra_json
transcript_status, scrape_status, last_enriched, error_message

## Claude Code
Always commit and push directly to the main branch. Never create pull requests unless I explicitly ask for one.
