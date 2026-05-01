-- Schema for the lesson-generation web app on Supabase Postgres.
--
-- Idempotent: every CREATE uses IF NOT EXISTS so this can be re-applied to
-- an existing database without dropping data. Run once per Supabase project:
--
--     psql "$SUPABASE_DB_URL" -f scripts/init_supabase_schema.sql
--
-- Durable source of truth:
--   * source_content   - raw / source material (TED, YouTube, pasted, PDF)
--   * generated_lesson - saved AI-generated lessons, including lesson_json
--                        and lesson_html (the in-browser preview)
--   * lesson_artifact  - pointers to downloadable files (DOCX/PDF/etc).
--                        storage_backend='local' is NON-DURABLE on Render
--                        free tier; the app must regenerate from
--                        generated_lesson.lesson_json if the local file is
--                        missing.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- source_content
-- ---------------------------------------------------------------------------
create table if not exists source_content (
    id                  uuid primary key default gen_random_uuid(),
    source_type         text not null,
    title               text default '',
    author              text default '',
    description         text default '',
    category            text default '',
    collection          text default '',
    tags                text default '',
    source_url          text default '',
    ted_url             text default '',
    youtube_url         text default '',
    transcript_text     text default '',
    pdf_text            text default '',
    raw_text            text default '',
    duration            text default '',
    views               text default '',
    ted_slug            text default '',
    youtube_id          text default '',
    content_id          text default '',
    provider            text default '',
    provider_content_id text default '',
    source_status       text default '',
    scrape_status       text default '',
    transcript_status   text default '',
    last_enriched       timestamptz,
    error_message       text default '',
    extra_json          jsonb default '{}'::jsonb,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

-- Dedup key: same source_type + same canonical URL = same row.
create unique index if not exists source_content_type_url_key
    on source_content (source_type, source_url)
    where source_url <> '';

create index if not exists source_content_ted_slug_idx    on source_content (ted_slug);
create index if not exists source_content_youtube_id_idx  on source_content (youtube_id);
create index if not exists source_content_content_id_idx  on source_content (content_id);
create index if not exists source_content_collection_idx  on source_content (collection);
create index if not exists source_content_source_type_idx on source_content (source_type);

-- ---------------------------------------------------------------------------
-- generated_lesson
-- ---------------------------------------------------------------------------
create table if not exists generated_lesson (
    id                  uuid primary key default gen_random_uuid(),
    source_content_id   uuid not null references source_content(id) on delete cascade,
    lesson_type         text not null,
    title               text default '',
    grade_level         text default '',
    duration_minutes    integer default 0,
    lesson_json         jsonb,
    lesson_html         text default '',
    generation_status   text default 'pending',
    model_used          text default '',
    briefing_json       jsonb,
    notes               text default '',
    error_message       text default '',
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

create index if not exists generated_lesson_source_idx
    on generated_lesson (source_content_id);
create index if not exists generated_lesson_type_idx
    on generated_lesson (lesson_type);
create index if not exists generated_lesson_created_idx
    on generated_lesson (created_at desc);

-- ---------------------------------------------------------------------------
-- lesson_artifact
-- ---------------------------------------------------------------------------
create table if not exists lesson_artifact (
    id                  uuid primary key default gen_random_uuid(),
    generated_lesson_id uuid not null references generated_lesson(id) on delete cascade,
    artifact_type       text not null,
    storage_backend     text not null default 'local',
    file_path_or_url    text default '',
    file_size_bytes     integer default 0,
    created_at          timestamptz not null default now()
);

create index if not exists lesson_artifact_lesson_idx
    on lesson_artifact (generated_lesson_id);
create index if not exists lesson_artifact_type_idx
    on lesson_artifact (generated_lesson_id, artifact_type);
