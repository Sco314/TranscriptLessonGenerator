"""Postgres-backed storage for SourceContent / GeneratedLesson / LessonArtifact.

Uses psycopg v3 directly — no ORM, matching the thin-data-layer style of
CSVStore / SQLiteStore. Backwards-compatible with Lesson via the
SourceContent.from_lesson adapter, so the legacy enrichment pipeline
(ted_lessons.enricher) keeps working: it sees SourceContent rows
through the same `find` / `find_by_id` / `add_or_update` interface.

Connection target: env var SUPABASE_DB_URL (a standard postgres:// URL).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from contextlib import contextmanager
from dataclasses import fields as dc_fields
from typing import Any, Iterable, Iterator

from .models import (
    GeneratedLesson, Lesson, LessonArtifact, SourceContent,
    derive_content_id,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

class PostgresStore:
    """Postgres store backed by a single long-lived psycopg connection.

    Thread-safety: psycopg connections are not thread-safe, so we wrap each
    write/read in a lock. For the scale of this app (single Flask process,
    a handful of background threads) that's plenty. If we ever need real
    concurrency, swap in psycopg_pool.ConnectionPool with no public API
    change.
    """

    def __init__(self, db_url: str | None = None):
        self.db_url = db_url or os.environ.get("SUPABASE_DB_URL", "")
        if not self.db_url:
            raise RuntimeError(
                "PostgresStore requires SUPABASE_DB_URL (Supabase connection string)."
            )
        try:
            import psycopg  # noqa: F401  -- imported for early failure
        except ImportError as e:
            raise RuntimeError(
                "psycopg is not installed. Run: pip install -r requirements.txt"
            ) from e

        self._lock = threading.Lock()
        self._conn = None
        self._connect()

    def _connect(self):
        import psycopg
        self._conn = psycopg.connect(self.db_url, autocommit=True)

    @contextmanager
    def _cursor(self) -> Iterator[Any]:
        import psycopg
        with self._lock:
            try:
                with self._conn.cursor() as cur:
                    yield cur
            except psycopg.OperationalError:
                # Stale connection — reconnect once and retry.
                log.warning("Postgres connection dropped; reconnecting.")
                self._connect()
                with self._conn.cursor() as cur:
                    yield cur

    def close(self):
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def save(self):
        # autocommit=True; nothing to flush.
        return None

    # ---------------------------------------------------------------------
    # Lesson <-> SourceContent adapter
    # ---------------------------------------------------------------------
    # The legacy enricher and CLI drive everything in terms of `Lesson`. To
    # keep that pipeline working we accept Lessons at this boundary, store
    # them as SourceContent rows, and reconstitute Lessons on read.

    def all_lessons(self) -> list[Lesson]:
        return [_source_to_lesson(s) for s in self.list_sources()]

    def find(self, ted_slug: str = "", youtube_id: str = "",
             content_id: str = "") -> Lesson | None:
        s = self.find_source(
            ted_slug=ted_slug, youtube_id=youtube_id, content_id=content_id,
        )
        return _source_to_lesson(s) if s else None

    def find_by_id(self, lesson_id: str) -> Lesson | None:
        # lesson_id may be a UUID (new) or a ted_/yt_ slug-id (legacy).
        s = self.find_source_by_id(lesson_id)
        if s:
            return _source_to_lesson(s)
        if lesson_id.startswith("ted_"):
            slug = lesson_id[4:]
            s = self.find_source(ted_slug=slug)
        elif lesson_id.startswith("yt_"):
            vid = lesson_id[3:]
            s = self.find_source(youtube_id=vid)
        return _source_to_lesson(s) if s else None

    def add_or_update(self, lesson: Lesson) -> tuple[Lesson, bool]:
        existing = self.find_source(
            ted_slug=lesson.ted_slug,
            youtube_id=lesson.youtube_id,
            content_id=lesson.content_id,
        )
        if existing:
            _merge_into_source(existing, lesson)
            self.upsert_source(existing)
            return _source_to_lesson(existing), False
        new = SourceContent.from_lesson(lesson)
        self.upsert_source(new)
        return _source_to_lesson(new), True

    def search(self, query: str) -> list[Lesson]:
        return [_source_to_lesson(s) for s in self.search_sources(query)]

    def needs_enrichment(self, retry_failed: bool = False) -> list[Lesson]:
        if retry_failed:
            sql = """
                select * from source_content
                where (ted_url <> '' and (scrape_status is null or scrape_status <> 'ok'))
                   or (youtube_id <> '' and (transcript_status is null
                       or transcript_status not in ('ok','unavailable')))
                order by created_at
            """
        else:
            sql = """
                select * from source_content
                where (ted_url <> '' and (scrape_status is null
                       or scrape_status not in ('ok','failed')))
                   or (youtube_id <> '' and (transcript_status is null
                       or transcript_status not in ('ok','unavailable','failed')))
                order by created_at
            """
        with self._cursor() as cur:
            cur.execute(sql)
            rows = _rows_with_columns(cur)
        return [_source_to_lesson(_row_to_source(r)) for r in rows]

    def __len__(self) -> int:
        with self._cursor() as cur:
            cur.execute("select count(*) from source_content")
            return cur.fetchone()[0]

    # ---------------------------------------------------------------------
    # Native SourceContent API
    # ---------------------------------------------------------------------

    def list_sources(self,
                     source_type: str | None = None,
                     collection: str | None = None,
                     limit: int | None = None) -> list[SourceContent]:
        sql = "select * from source_content"
        clauses = []
        params: list[Any] = []
        if source_type:
            clauses.append("source_type = %s")
            params.append(source_type)
        if collection:
            clauses.append("collection ilike %s")
            params.append(f"%{collection}%")
        if clauses:
            sql += " where " + " and ".join(clauses)
        sql += " order by updated_at desc"
        if limit:
            sql += " limit %s"
            params.append(limit)
        with self._cursor() as cur:
            cur.execute(sql, params)
            rows = _rows_with_columns(cur)
        return [_row_to_source(r) for r in rows]

    def find_source(self, *, ted_slug: str = "", youtube_id: str = "",
                    content_id: str = "",
                    source_url: str = "") -> SourceContent | None:
        with self._cursor() as cur:
            if ted_slug:
                cur.execute(
                    "select * from source_content where ted_slug = %s limit 1",
                    (ted_slug,),
                )
                row = _one_with_columns(cur)
                if row:
                    return _row_to_source(row)
            if youtube_id:
                cur.execute(
                    "select * from source_content where youtube_id = %s limit 1",
                    (youtube_id,),
                )
                row = _one_with_columns(cur)
                if row:
                    return _row_to_source(row)
            if content_id:
                cur.execute(
                    "select * from source_content where content_id = %s limit 1",
                    (content_id,),
                )
                row = _one_with_columns(cur)
                if row:
                    return _row_to_source(row)
            if source_url:
                cur.execute(
                    "select * from source_content where source_url = %s limit 1",
                    (source_url,),
                )
                row = _one_with_columns(cur)
                if row:
                    return _row_to_source(row)
        return None

    def find_source_by_id(self, source_id: str) -> SourceContent | None:
        with self._cursor() as cur:
            try:
                cur.execute(
                    "select * from source_content where id = %s limit 1",
                    (source_id,),
                )
            except Exception:
                # Not a valid uuid — caller may have passed a legacy slug-id.
                return None
            row = _one_with_columns(cur)
        return _row_to_source(row) if row else None

    def search_sources(self, query: str) -> list[SourceContent]:
        q = f"%{query}%"
        with self._cursor() as cur:
            cur.execute(
                """
                select * from source_content
                where title ilike %s
                   or description ilike %s
                   or category ilike %s
                   or collection ilike %s
                   or tags ilike %s
                   or transcript_text ilike %s
                   or pdf_text ilike %s
                   or raw_text ilike %s
                order by updated_at desc
                """,
                (q, q, q, q, q, q, q, q),
            )
            rows = _rows_with_columns(cur)
        return [_row_to_source(r) for r in rows]

    def upsert_source(self, src: SourceContent) -> SourceContent:
        """Insert or update by id (primary key)."""
        src.touch()
        d = src.to_row()
        cols = list(d.keys())
        placeholders = ", ".join(["%s"] * len(cols))
        col_names = ", ".join(cols)
        # Only update on conflict — keep the existing id, refresh data.
        update_assignments = ", ".join(
            f"{c} = excluded.{c}" for c in cols if c != "id"
        )
        sql = (
            f"insert into source_content ({col_names}) values ({placeholders}) "
            f"on conflict (id) do update set {update_assignments}"
        )
        values = [_to_db(c, d[c]) for c in cols]
        with self._cursor() as cur:
            cur.execute(sql, values)
        return src

    def add_or_update_source(self, src: SourceContent) -> tuple[SourceContent, bool]:
        existing = self.find_source(
            ted_slug=src.ted_slug,
            youtube_id=src.youtube_id,
            content_id=src.content_id,
            source_url=src.source_url,
        )
        if existing:
            _merge_into_source(existing, src)
            self.upsert_source(existing)
            return existing, False
        self.upsert_source(src)
        return src, True

    # ---------------------------------------------------------------------
    # GeneratedLesson API
    # ---------------------------------------------------------------------

    def save_generated_lesson(self, gl: GeneratedLesson) -> GeneratedLesson:
        gl.touch()
        sql = """
            insert into generated_lesson (
                id, source_content_id, lesson_type, title, grade_level,
                duration_minutes, lesson_json, lesson_html, generation_status,
                model_used, briefing_json, notes, error_message,
                created_at, updated_at
            ) values (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s
            )
            on conflict (id) do update set
                source_content_id = excluded.source_content_id,
                lesson_type       = excluded.lesson_type,
                title             = excluded.title,
                grade_level       = excluded.grade_level,
                duration_minutes  = excluded.duration_minutes,
                lesson_json       = excluded.lesson_json,
                lesson_html       = excluded.lesson_html,
                generation_status = excluded.generation_status,
                model_used        = excluded.model_used,
                briefing_json     = excluded.briefing_json,
                notes             = excluded.notes,
                error_message    = excluded.error_message,
                updated_at        = excluded.updated_at
        """
        params = (
            gl.id, gl.source_content_id, gl.lesson_type, gl.title, gl.grade_level,
            gl.duration_minutes,
            _json_or_null(gl.lesson_json), gl.lesson_html, gl.generation_status,
            gl.model_used, _json_or_null(gl.briefing_json), gl.notes, gl.error_message,
            gl.created_at, gl.updated_at,
        )
        with self._cursor() as cur:
            cur.execute(sql, params)
        return gl

    def find_generated_lesson(self, lesson_id: str) -> GeneratedLesson | None:
        with self._cursor() as cur:
            try:
                cur.execute(
                    "select * from generated_lesson where id = %s limit 1",
                    (lesson_id,),
                )
            except Exception:
                return None
            row = _one_with_columns(cur)
        return _row_to_generated(row) if row else None

    def list_generated_lessons(self,
                               source_content_id: str | None = None,
                               lesson_type: str | None = None,
                               limit: int | None = None) -> list[GeneratedLesson]:
        sql = "select * from generated_lesson"
        clauses = []
        params: list[Any] = []
        if source_content_id:
            clauses.append("source_content_id = %s")
            params.append(source_content_id)
        if lesson_type:
            clauses.append("lesson_type = %s")
            params.append(lesson_type)
        if clauses:
            sql += " where " + " and ".join(clauses)
        sql += " order by created_at desc"
        if limit:
            sql += " limit %s"
            params.append(limit)
        with self._cursor() as cur:
            cur.execute(sql, params)
            rows = _rows_with_columns(cur)
        return [_row_to_generated(r) for r in rows]

    def update_generation_status(self, lesson_id: str, status: str,
                                 error_message: str = "") -> None:
        with self._cursor() as cur:
            cur.execute(
                """update generated_lesson
                   set generation_status = %s,
                       error_message = %s,
                       updated_at = now()
                   where id = %s""",
                (status, error_message, lesson_id),
            )

    # ---------------------------------------------------------------------
    # LessonArtifact API
    # ---------------------------------------------------------------------

    def save_artifact(self, art: LessonArtifact) -> LessonArtifact:
        sql = """
            insert into lesson_artifact (
                id, generated_lesson_id, artifact_type, storage_backend,
                file_path_or_url, file_size_bytes, created_at
            ) values (%s, %s, %s, %s, %s, %s, %s)
            on conflict (id) do update set
                artifact_type    = excluded.artifact_type,
                storage_backend  = excluded.storage_backend,
                file_path_or_url = excluded.file_path_or_url,
                file_size_bytes  = excluded.file_size_bytes
        """
        params = (
            art.id, art.generated_lesson_id, art.artifact_type, art.storage_backend,
            art.file_path_or_url, art.file_size_bytes, art.created_at,
        )
        with self._cursor() as cur:
            cur.execute(sql, params)
        return art

    def find_artifact(self, artifact_id: str) -> LessonArtifact | None:
        with self._cursor() as cur:
            try:
                cur.execute(
                    "select * from lesson_artifact where id = %s limit 1",
                    (artifact_id,),
                )
            except Exception:
                return None
            row = _one_with_columns(cur)
        return _row_to_artifact(row) if row else None

    def list_artifacts(self, generated_lesson_id: str) -> list[LessonArtifact]:
        with self._cursor() as cur:
            cur.execute(
                """select * from lesson_artifact
                   where generated_lesson_id = %s
                   order by created_at""",
                (generated_lesson_id,),
            )
            rows = _rows_with_columns(cur)
        return [_row_to_artifact(r) for r in rows]


# ---------------------------------------------------------------------------
# Row -> dataclass
# ---------------------------------------------------------------------------

def _rows_with_columns(cur) -> list[dict]:
    cols = [d.name for d in cur.description] if cur.description else []
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _one_with_columns(cur) -> dict | None:
    cols = [d.name for d in cur.description] if cur.description else []
    row = cur.fetchone()
    if row is None:
        return None
    return dict(zip(cols, row))


def _row_to_source(row: dict) -> SourceContent:
    valid = {f.name for f in dc_fields(SourceContent)}
    kwargs = {}
    for k, v in row.items():
        if k not in valid:
            continue
        if k in ("created_at", "updated_at", "last_enriched"):
            kwargs[k] = v.isoformat() if v else ""
        elif k == "extra_json":
            kwargs[k] = json.dumps(v) if isinstance(v, (dict, list)) else (v or "")
        else:
            kwargs[k] = v if v is not None else ""
    return SourceContent(**kwargs)


def _row_to_generated(row: dict) -> GeneratedLesson:
    return GeneratedLesson(
        id=str(row["id"]),
        source_content_id=str(row["source_content_id"]),
        lesson_type=row.get("lesson_type") or "",
        title=row.get("title") or "",
        grade_level=row.get("grade_level") or "",
        duration_minutes=row.get("duration_minutes") or 0,
        lesson_json=row.get("lesson_json"),
        lesson_html=row.get("lesson_html") or "",
        generation_status=row.get("generation_status") or "",
        model_used=row.get("model_used") or "",
        briefing_json=row.get("briefing_json"),
        notes=row.get("notes") or "",
        error_message=row.get("error_message") or "",
        created_at=_iso(row.get("created_at")),
        updated_at=_iso(row.get("updated_at")),
    )


def _row_to_artifact(row: dict) -> LessonArtifact:
    return LessonArtifact(
        id=str(row["id"]),
        generated_lesson_id=str(row["generated_lesson_id"]),
        artifact_type=row.get("artifact_type") or "",
        storage_backend=row.get("storage_backend") or "local",
        file_path_or_url=row.get("file_path_or_url") or "",
        file_size_bytes=row.get("file_size_bytes") or 0,
        created_at=_iso(row.get("created_at")),
    )


def _iso(value) -> str:
    if not value:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _json_or_null(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


def _to_db(col: str, value):
    if col in ("created_at", "updated_at", "last_enriched"):
        return value or None
    if col == "extra_json":
        if not value:
            return "{}"
        if isinstance(value, str):
            try:
                json.loads(value)
                return value
            except Exception:
                return "{}"
        return json.dumps(value)
    return value


# ---------------------------------------------------------------------------
# Lesson <-> SourceContent
# ---------------------------------------------------------------------------

def _source_to_lesson(src: SourceContent) -> Lesson:
    """Reconstitute a Lesson view of a SourceContent row.

    Used so the legacy enricher / CLI / web routes that still take a Lesson
    keep working while we migrate.
    """
    if not src:
        return None  # type: ignore[return-value]
    legacy_lesson_id = src.id
    if src.ted_slug:
        legacy_lesson_id = f"ted_{src.ted_slug}"
    elif src.youtube_id:
        legacy_lesson_id = f"yt_{src.youtube_id}"
    return Lesson(
        lesson_id=legacy_lesson_id,
        ted_slug=src.ted_slug,
        youtube_id=src.youtube_id,
        content_id=src.content_id or derive_content_id(src.source_type, src.source_url),
        source_type="ted" if src.source_type == "ted_ed" else src.source_type,
        canonical_url=src.source_url,
        provider=src.provider,
        provider_content_id=src.provider_content_id,
        title=src.title,
        collection=src.collection,
        author=src.author,
        duration=src.duration,
        views=src.views,
        category=src.category,
        ted_url=src.ted_url,
        youtube_url=src.youtube_url,
        description=src.description,
        tags=src.tags,
        transcript=src.transcript_text,
        transcript_status=src.transcript_status,
        scrape_status=src.scrape_status,
        last_enriched=src.last_enriched,
        error_message=src.error_message,
        extra_json=src.extra_json,
    )


def _merge_into_source(existing: SourceContent, incoming: Any) -> None:
    """Merge an incoming Lesson or SourceContent into an existing SourceContent.

    Same rules as ted_lessons.store.merge_lesson:
      - never overwrite a populated content field with empty/missing data;
      - never overwrite a successful transcript with a failed attempt.
    """
    # Accept either a Lesson or a SourceContent.
    if isinstance(incoming, Lesson):
        incoming = SourceContent.from_lesson(incoming)

    for field_name in [
        "title", "author", "description", "category", "collection",
        "tags", "duration", "views", "ted_url", "youtube_url", "source_url",
        "ted_slug", "youtube_id", "provider", "provider_content_id",
        "pdf_text", "raw_text",
    ]:
        cur = getattr(existing, field_name, "")
        new = getattr(incoming, field_name, "")
        if not cur and new:
            setattr(existing, field_name, new)

    # Transcript: only overwrite when we'd be improving status.
    if incoming.transcript_text and incoming.transcript_status == "ok":
        if existing.transcript_status != "ok":
            existing.transcript_text = incoming.transcript_text
            existing.transcript_status = "ok"

    if incoming.scrape_status and not existing.scrape_status:
        existing.scrape_status = incoming.scrape_status
    if incoming.last_enriched:
        existing.last_enriched = incoming.last_enriched
    if incoming.error_message and not existing.error_message:
        existing.error_message = incoming.error_message

    existing.touch()
