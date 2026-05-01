# TranscriptLessonGenerator

## What this project is

A lesson-generation web app / lesson CMS for teachers. The core domain
objects are:

- **SourceContent** — raw or source material a teacher uploaded or
  scraped: TED-Ed metadata, YouTube transcript, pasted text, or
  PDF-extracted text.
- **GeneratedLesson** — a saved AI-generated lesson built from a
  SourceContent. The first lesson type is the
  `general_employability_activity_sheet`; more types are planned (quiz,
  discussion, teacher notes, answer keys).
- **LessonArtifact** — a downloadable file (DOCX/PDF/HTML) belonging to
  a generated lesson.

Browse the source library, generate lessons, save them, view them
in-browser, and download DOCX exports.

## Durable storage (the source-of-truth boundary)

All durable data lives in **Supabase Postgres**. SQLite is legacy and
kept only as a local-dev fallback / for the existing TED enrichment
pipeline.

**Durable in Supabase:**
- `source_content` rows
- `generated_lesson` rows (including `lesson_json` and `lesson_html` —
  enough to render the saved lesson in-browser without re-running
  Claude or the DOCX engine)

**Temporary / non-durable:**
- DOCX files written to local disk under `WORKSHEET_DOWNLOADS_DIR`.
  These will disappear on Render redeploy. The artifact-download
  endpoint regenerates a missing DOCX from `lesson_json` on demand.

A future phase will move artifacts to Supabase Storage; the
`LessonArtifact.storage_backend` column is already in place for that.

## Architecture

- `ted_lessons/` — core engine
  - `models.py` — `Lesson` (legacy, used by the enricher and CLI),
    plus the new `SourceContent`, `GeneratedLesson`, `LessonArtifact`
    dataclasses. `SourceContent.from_lesson()` adapts the legacy type.
  - `store.py` — `CSVStore` and `SQLiteStore` (legacy backends). The
    `get_store()` factory now also returns `PostgresStore` when
    `SUPABASE_DB_URL` is set.
  - `postgres_store.py` — Supabase-backed store. Implements the
    duck-typed `Lesson` API (`load`, `save`, `find`, `find_by_id`,
    `add_or_update`, `search`, `needs_enrichment`, `all_lessons`) plus
    native methods: `list_sources`, `find_source`, `find_source_by_id`,
    `search_sources`, `add_or_update_source`, `save_generated_lesson`,
    `find_generated_lesson`, `list_generated_lessons`, `save_artifact`,
    `find_artifact`, `list_artifacts`. Uses psycopg v3 directly.
  - `scraper.py`, `transcript.py`, `enricher.py`, `http_client.py` —
    unchanged TED/YouTube scraping pipeline; feeds enrichment for
    `SourceContent` rows via the `Lesson <-> SourceContent` adapter.
  - `cli.py` — CLI subcommands (add, enrich, list, search, show,
    export, migrate).
- `web/` — Flask web app
  - `app.py` — Routes:
    - `/sources`, `/sources/<id>` — Source Library
    - `/sources/<id>/generate` — kick off generation
    - `/sources/import-csv` — CSV importer (Apps Script export or
      this app's CSV)
    - `/lessons`, `/lessons/<id>` — Generated Lessons library +
      in-browser preview (renders `lesson_html`)
    - `/lessons/<id>/artifacts/<aid>` — DOCX download with auto-regen
      from `lesson_json` if the local file is missing
    - `/submit`, `/submit/status/<job_id>` — URL paste + enrichment
    - `/lesson/<id>` — 301 redirect to the new `/sources/<id>` URL
    - `/api/sources`, `/api/generated-lessons`, `/api/lessons` — JSON
  - `activity_generator.py` — `generate(source, form_data, output_dir,
    store)` orchestrates: build briefing → call Claude → render HTML
    view → render DOCX → persist `GeneratedLesson` + `LessonArtifact`.
    `regenerate_docx(generated_lesson, output_path)` re-renders the
    DOCX from the saved spec when needed.
  - `spec_to_html.py` — Walks the same `WORKSHEET_SCHEMA` spec the
    DOCX engine uses and emits semantic HTML for in-browser preview.
  - `importers/csv_import.py` — CSV → SourceContent importer (handles
    both modern and legacy Apps Script column names).
  - `templates/` — `base.html`, `sources.html`, `source_detail.html`,
    `lessons.html`, `lesson_view.html`, `import_csv.html`, plus the
    legacy `submit.html`, `results.html`, `activity_sheet_form.html`,
    `activity_sheet_progress.html`, `404.html`.
- `lesson_builder/` — DOCX rendering engine. Spec contract unchanged.
- `skills/general-employability/SKILL.md` — prompt for the activity-
  sheet generator.
- `scripts/`
  - `init_supabase_schema.sql` — one-time schema setup for Supabase
  - `migrate_to_supabase.py` — copy local SQLite Lesson rows into
    Supabase `source_content` (idempotent, `--dry-run` mode)
  - `migrate_csv_to_sqlite.py` — legacy CSV → SQLite migration
  - `seed_demo_lessons.py` — local-dev seed
- `data/lessons.db` — local SQLite (gitignored, legacy/dev only)
- `data/ted_ed_master_list.csv` — legacy CSV export

## Key design rules

- SourceContent identified by (source_type, source_url) for dedup;
  primary key is a UUID.
- Legacy provenance kept on every SourceContent: `ted_slug`,
  `youtube_id`, `content_id` — preserves the dedup chain inherited
  from `Lesson`.
- Save first, export second: `lesson_json` is the source of truth for
  every generated lesson. DOCX and HTML are both derived views.
- Never overwrite a successful transcript with a failed attempt
  (carried over from the legacy merge logic).
- The app must never depend on Render's local disk for displaying a
  saved lesson; if a local DOCX is missing it must regenerate from
  `lesson_json` (or surface a clear "regenerate" affordance).
- Web routes route by stable IDs (UUID for SourceContent /
  GeneratedLesson, never title).
- All new development goes in `ted_lessons/` and `web/`. The .gs file
  and `YouTubeTranscriptTEDEdDescriptionFetcher.py` are reference
  only.

## Running

```bash
# Install
pip install -r requirements.txt

# One-time: stand up the Supabase schema
psql "$SUPABASE_DB_URL" -f scripts/init_supabase_schema.sql

# One-time: copy local SQLite Lessons into Supabase source_content
python scripts/migrate_to_supabase.py --dry-run
python scripts/migrate_to_supabase.py

# CLI (still works against the legacy Lesson API; will use Postgres
# automatically if SUPABASE_DB_URL is set)
python -m ted_lessons add https://ed.ted.com/lessons/the-prison-break-riddle
python -m ted_lessons list
python -m ted_lessons enrich
python -m ted_lessons search "riddle"

# Web app
python web/app.py                          # runs on http://localhost:5000
```

## Column schema (legacy Lesson, preserved)

lesson_id, ted_slug, youtube_id, content_id, source_type, canonical_url,
provider, provider_content_id, title, collection, author, duration, views,
category, ted_url, youtube_url, description, tags, transcript,
transcript_status, scrape_status, last_enriched, error_message, extra_json

## Postgres tables (current source of truth)

See `scripts/init_supabase_schema.sql` for the full DDL.

- `source_content` — every raw/source row, dedup'd by
  `(source_type, source_url)`.
- `generated_lesson` — saved AI lesson, with `lesson_json` and
  `lesson_html`. FK → source_content (cascade delete).
- `lesson_artifact` — pointer to a downloadable file. FK →
  generated_lesson (cascade delete). `storage_backend = 'local'`
  means the file is on the running host's disk and may disappear.

## Claude Code

Always commit and push directly to the main branch. Never create pull requests unless I explicitly ask for one.
