"""Flask web app — TranscriptLessonGenerator (lesson-generation CMS).

Permanent objects (Supabase Postgres is the durable source of truth):
  * SourceContent     — raw / source material (TED, YouTube, pasted, PDF)
  * GeneratedLesson   — saved AI-generated lessons (lesson_json + lesson_html)
  * LessonArtifact    — downloadable files (DOCX/PDF). DOCX on local disk is
                        TEMPORARY on Render free tier — see CLAUDE.md.

Routes:
  /                                     redirect → /sources
  /sources                              browse Source Library
  /sources/<id>                         source detail
  /sources/<id>/generate (POST)         kick off generation
  /sources/import-csv (GET/POST)        upload Apps Script CSV
  /lessons                              browse Generated Lessons
  /lessons/<id>                         in-browser preview (from lesson_html)
  /lessons/<id>/artifacts/<aid>         download DOCX (auto-regen if missing)
  /generate/status/<job_id>             progress polling JSON
  /submit (GET/POST)                    URL paste form (writes SourceContent)
  /lesson/<lesson_id>                   legacy → 301 to /sources/<id>
  /api/lessons, /api/sources, /api/generated-lessons   JSON API
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import threading
import time
import uuid
from pathlib import Path

from flask import (
    Flask, render_template, request, redirect, url_for, jsonify, abort, session,
    send_from_directory,
)

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ted_lessons.models import Lesson, SourceContent, GeneratedLesson  # noqa: E402
from ted_lessons.enricher import enrich  # noqa: E402
from ted_lessons.http_client import HttpClient  # noqa: E402
from ted_lessons.scraper import scrape_collection_page  # noqa: E402
from ted_lessons.store import (  # noqa: E402
    SQLiteStore, DEFAULT_SQLITE_PATH, get_store as ted_get_store,
)
from lesson_builder import THEMES  # noqa: E402

import activity_generator  # noqa: E402
from importers.csv_import import import_csv_text  # noqa: E402

log = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

PER_PAGE = 24

# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------
# Two stores live side-by-side during the migration:
#   _pg_store      — Supabase PostgresStore. Source of truth for everything.
#   _legacy_store  — local SQLiteStore. Read-only fallback when Postgres isn't
#                    configured, plus the place the legacy enrichment pipeline
#                    still expects to write through.

_pg_store = None
_pg_store_lock = threading.Lock()
_legacy_store: SQLiteStore | None = None


def get_pg_store():
    """Return the Postgres store, or None if SUPABASE_DB_URL isn't set."""
    global _pg_store
    if not os.environ.get("SUPABASE_DB_URL"):
        return None
    if _pg_store is None:
        with _pg_store_lock:
            if _pg_store is None:
                from ted_lessons.postgres_store import PostgresStore
                _pg_store = PostgresStore()
    return _pg_store


def get_legacy_store() -> SQLiteStore:
    global _legacy_store
    if _legacy_store is None:
        db_path = os.environ.get("TED_LESSONS_DB", str(DEFAULT_SQLITE_PATH))
        _legacy_store = SQLiteStore(db_path)
    return _legacy_store


def get_store():
    """Best store available: Postgres if configured, else legacy SQLite."""
    return get_pg_store() or get_legacy_store()


# Background generation jobs: job_id -> {state, ...}
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

# Downloads directory (local, NON-DURABLE on Render free tier).
DOWNLOADS_DIR = Path(
    os.environ.get(
        "WORKSHEET_DOWNLOADS_DIR",
        str(Path(__file__).resolve().parent / "static" / "downloads"),
    )
)
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
_DOWNLOAD_TTL_SECONDS = 24 * 60 * 60


# ═══════════════════════════════════════════════════════════════════════════
# CSRF protection
# ═══════════════════════════════════════════════════════════════════════════

def _generate_csrf_token() -> str:
    if "_csrf_secret" not in session:
        session["_csrf_secret"] = secrets.token_hex(16)
    return session["_csrf_secret"]


def _validate_csrf_token(token: str) -> bool:
    expected = session.get("_csrf_secret", "")
    if not expected or not token:
        return False
    return hmac.compare_digest(expected, token)


@app.before_request
def _csrf_protect():
    if request.method == "POST" and request.content_type and \
       not request.content_type.startswith("application/json"):
        token = request.form.get("_csrf_token", "")
        if not _validate_csrf_token(token):
            abort(403)


_seed_started = False
_seed_lock = threading.Lock()


def _maybe_start_demo_seed() -> None:
    global _seed_started
    if os.environ.get("SEED_DEMO_LESSONS", "1") == "0":
        return
    if get_pg_store() is not None:
        # When Postgres is configured we don't seed local SQLite — the
        # source of truth lives elsewhere.
        return
    with _seed_lock:
        if _seed_started:
            return
        _seed_started = True
    try:
        if len(get_legacy_store()) > 0:
            return
    except Exception:
        log.exception("Could not check store size for demo seed")
        return

    log.info("Lesson DB is empty — starting demo seed in background.")

    def _run_seed():
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from scripts.seed_demo_lessons import seed
            db_path = os.environ.get("TED_LESSONS_DB", str(DEFAULT_SQLITE_PATH))
            local_store = SQLiteStore(db_path)
            try:
                summary = seed(local_store, enrich_new=True)
                log.info("Demo seed finished: %s", summary)
            finally:
                local_store.close()
        except Exception:
            log.exception("Demo seed failed")

    threading.Thread(target=_run_seed, daemon=True).start()


@app.before_request
def _bootstrap():
    _maybe_start_demo_seed()


app.jinja_env.globals["csrf_token"] = _generate_csrf_token
app.jinja_env.globals["pg_enabled"] = lambda: get_pg_store() is not None


# ═══════════════════════════════════════════════════════════════════════════
# URL validation
# ═══════════════════════════════════════════════════════════════════════════

_URL_RE = re.compile(
    r"^https?://"
    r"(ed\.ted\.com/lessons/[\w-]+"
    r"|ed\.ted\.com/collections/[\w-]+"
    r"|(?:www\.)?youtube\.com/watch\?v=[\w-]+"
    r"|youtu\.be/[\w-]+"
    r")",
    re.IGNORECASE,
)


def _is_valid_url(url: str) -> bool:
    return bool(_URL_RE.match(url.strip()))


def _require_pg(action: str = "this feature"):
    """Abort with a clear 503 when Postgres isn't configured."""
    if get_pg_store() is None:
        abort(
            503,
            f"{action} requires SUPABASE_DB_URL. Configure a Supabase Postgres "
            f"connection string in your environment, then run "
            f"`psql $SUPABASE_DB_URL -f scripts/init_supabase_schema.sql`.",
        )


# ═══════════════════════════════════════════════════════════════════════════
# Source Library (browse / detail / submit)
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return redirect(url_for("sources_index"))


@app.route("/sources")
def sources_index():
    """Source Library — browse SourceContent (or fall back to legacy Lessons)."""
    q = request.args.get("q", "").strip()
    source_type = request.args.get("source_type", "").strip()
    collection = request.args.get("collection", "").strip()
    page = max(1, request.args.get("page", 1, type=int))

    pg = get_pg_store()
    if pg is not None:
        if q:
            sources = pg.search_sources(q)
        else:
            sources = pg.list_sources(
                source_type=source_type or None,
                collection=collection or None,
            )
    else:
        # Legacy fallback: build SourceContent views over the Lesson rows.
        legacy = get_legacy_store()
        lessons = legacy.search(q) if q else legacy.all_lessons()
        sources = [SourceContent.from_lesson(l) for l in lessons]
        if collection:
            sources = [
                s for s in sources
                if collection.lower() in (s.collection or "").lower()
            ]
        if source_type:
            sources = [s for s in sources if s.source_type == source_type]

    total_results = len(sources)
    total_pages = max(1, (total_results + PER_PAGE - 1) // PER_PAGE)
    page = min(page, total_pages)
    start = (page - 1) * PER_PAGE
    page_sources = sources[start:start + PER_PAGE]

    # Collections list for the filter dropdown.
    if pg is not None:
        all_for_filter = pg.list_sources(limit=2000)
    else:
        all_for_filter = sources
    collections = sorted({s.collection for s in all_for_filter if s.collection})

    return render_template(
        "sources.html",
        sources=page_sources,
        q=q,
        collection=collection,
        source_type=source_type,
        collections=collections,
        total=total_results,
        page=page,
        total_pages=total_pages,
        total_results=total_results,
    )


def _resolve_source(source_id: str) -> SourceContent | None:
    """Look up a source by UUID (Postgres) or by legacy ted_/yt_ id."""
    pg = get_pg_store()
    if pg is not None:
        s = pg.find_source_by_id(source_id)
        if s:
            return s
        if source_id.startswith("ted_"):
            return pg.find_source(ted_slug=source_id[4:])
        if source_id.startswith("yt_"):
            return pg.find_source(youtube_id=source_id[3:])
        return None

    legacy = get_legacy_store()
    lesson = legacy.find_by_id(source_id)
    if not lesson and not source_id.startswith(("ted_", "yt_")):
        lesson = legacy.find_by_id(f"ted_{source_id}")
    return SourceContent.from_lesson(lesson) if lesson else None


@app.route("/sources/<source_id>")
def source_detail(source_id: str):
    src = _resolve_source(source_id)
    if not src:
        abort(404)

    generated = []
    pg = get_pg_store()
    if pg is not None and src.id:
        generated = pg.list_generated_lessons(source_content_id=src.id)

    return render_template(
        "source_detail.html",
        source=src,
        generated=generated,
        themes=THEMES,
    )


@app.route("/lesson/<lesson_id>")
def legacy_lesson_detail(lesson_id: str):
    """301 redirect from the old /lesson/<id> URL to /sources/<id>."""
    src = _resolve_source(lesson_id)
    if src:
        return redirect(url_for("source_detail", source_id=src.id), code=301)
    abort(404)


@app.route("/lesson/<lesson_id>/document")
def legacy_lesson_document(lesson_id: str):
    src = _resolve_source(lesson_id)
    if src:
        return redirect(url_for("source_detail", source_id=src.id), code=301)
    abort(404)


# ═══════════════════════════════════════════════════════════════════════════
# CSV import
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/sources/import-csv", methods=["GET", "POST"])
def import_csv():
    if request.method == "GET":
        return render_template("import_csv.html")

    _require_pg("CSV import")

    upload = request.files.get("csv")
    if not upload or not upload.filename:
        return render_template("import_csv.html", error="Please choose a CSV file."), 400

    try:
        text = upload.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return render_template("import_csv.html",
                               error="CSV must be UTF-8 encoded."), 400

    report = import_csv_text(text, get_pg_store())
    return render_template("import_csv.html", report=report)


# ═══════════════════════════════════════════════════════════════════════════
# Generated lessons
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/lessons")
def lessons_index():
    """Library of saved GeneratedLessons."""
    _require_pg("the Generated Lessons library")
    pg = get_pg_store()
    rows = pg.list_generated_lessons(limit=500)
    # Annotate with the parent source title for the table.
    enriched = []
    for gl in rows:
        src = pg.find_source_by_id(gl.source_content_id) if gl.source_content_id else None
        enriched.append((gl, src))
    return render_template("lessons.html", entries=enriched)


@app.route("/lessons/<lesson_id>")
def lesson_view(lesson_id: str):
    _require_pg("viewing saved lessons")
    pg = get_pg_store()
    gl = pg.find_generated_lesson(lesson_id)
    if not gl:
        abort(404)
    artifacts = pg.list_artifacts(gl.id)
    source = pg.find_source_by_id(gl.source_content_id) if gl.source_content_id else None
    return render_template(
        "lesson_view.html",
        lesson=gl,
        source=source,
        artifacts=artifacts,
    )


@app.route("/lessons/<lesson_id>/artifacts/<artifact_id>")
def lesson_artifact_download(lesson_id: str, artifact_id: str):
    """Download a saved artifact, regenerating from lesson_json if missing."""
    _require_pg("downloading lesson artifacts")
    pg = get_pg_store()
    gl = pg.find_generated_lesson(lesson_id)
    art = pg.find_artifact(artifact_id)
    if not gl or not art or art.generated_lesson_id != gl.id:
        abort(404)

    file_path = Path(art.file_path_or_url) if art.file_path_or_url else None
    download_name = (gl.title or "activity_sheet").replace(" ", "_") + f".{art.artifact_type}"

    if art.storage_backend == "local":
        if not file_path or not file_path.exists():
            # NON-DURABLE local file is missing (likely a Render redeploy
            # wiped it). Regenerate from lesson_json — that's why we save it.
            if not gl.lesson_json:
                # Nothing to regenerate from.
                return render_template(
                    "lesson_view.html",
                    lesson=gl,
                    source=pg.find_source_by_id(gl.source_content_id),
                    artifacts=pg.list_artifacts(gl.id),
                    artifact_missing=True,
                ), 410

            new_path = DOWNLOADS_DIR / f"{gl.id}.docx"
            ok = activity_generator.regenerate_docx(gl, new_path)
            if not ok:
                return render_template(
                    "lesson_view.html",
                    lesson=gl,
                    source=pg.find_source_by_id(gl.source_content_id),
                    artifacts=pg.list_artifacts(gl.id),
                    artifact_missing=True,
                ), 410

            art.file_path_or_url = str(new_path)
            art.file_size_bytes = new_path.stat().st_size
            pg.save_artifact(art)
            file_path = new_path

        return send_from_directory(
            file_path.parent,
            file_path.name,
            as_attachment=True,
            download_name=download_name,
        )

    # storage_backend == 'supabase' (or other) — redirect to signed URL.
    if art.file_path_or_url:
        return redirect(art.file_path_or_url)
    abort(404)


@app.route("/sources/<source_id>/generate", methods=["GET", "POST"])
def generate_from_source(source_id: str):
    """Show the briefing form (GET) or kick off generation (POST)."""
    src = _resolve_source(source_id)
    if not src:
        abort(404)

    if request.method == "GET":
        return render_template(
            "activity_sheet_form.html",
            source=src,
            lesson=src,                      # legacy template variable
            themes=THEMES,
            has_transcript=src.has_usable_body,
        )

    if not src.has_usable_body:
        return render_template(
            "activity_sheet_form.html",
            source=src,
            lesson=src,
            themes=THEMES,
            has_transcript=False,
        )

    _require_pg("saving generated lessons")

    form_data = {
        "format": request.form.get("format", "follow_along"),
        "framework": request.form.get("framework", "Auto"),
        "theme": request.form.get("theme", "teal"),
        "candidates": request.form.get("candidates", ""),
        "connections": request.form.get("connections", ""),
        "vocab": request.form.get("vocab", ""),
        "notes": request.form.get("notes", ""),
    }
    if form_data["theme"] not in THEMES:
        form_data["theme"] = "teal"

    _cleanup_old_downloads()
    job_id = str(uuid.uuid4())[:8]
    _start_generation_job(job_id, src.id, form_data)

    return render_template(
        "activity_sheet_progress.html",
        lesson=src,
        source=src,
        job_id=job_id,
    )


@app.route("/lesson/<lesson_id>/activity-sheet", methods=["GET", "POST"])
def legacy_activity_sheet_form(lesson_id: str):
    """Legacy URL — redirect to /sources/<id>/generate."""
    src = _resolve_source(lesson_id)
    if not src:
        abort(404)
    return redirect(url_for("generate_from_source", source_id=src.id), code=301)


# ═══════════════════════════════════════════════════════════════════════════
# Background generation
# ═══════════════════════════════════════════════════════════════════════════

def _cleanup_old_downloads() -> None:
    try:
        cutoff = time.time() - _DOWNLOAD_TTL_SECONDS
        for f in DOWNLOADS_DIR.iterdir():
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
    except OSError:
        pass


def _start_generation_job(job_id: str, source_id: str, form_data: dict) -> None:
    with _jobs_lock:
        _jobs[job_id] = {"state": "running"}

    thread = threading.Thread(
        target=_run_generation_job,
        args=(job_id, source_id, form_data),
        daemon=True,
    )
    thread.start()


def _run_generation_job(job_id: str, source_id: str, form_data: dict) -> None:
    """Background worker. Re-resolves the source from a fresh store handle."""
    try:
        pg = get_pg_store()
        if pg is None:
            with _jobs_lock:
                _jobs[job_id] = {"state": "error",
                                 "error": "SUPABASE_DB_URL is not configured."}
            return

        src = pg.find_source_by_id(source_id)
        if src is None:
            with _jobs_lock:
                _jobs[job_id] = {"state": "error", "error": "Source not found."}
            return

        gl, err = activity_generator.generate(
            src, form_data, output_dir=DOWNLOADS_DIR, store=pg,
        )

        with _jobs_lock:
            if err:
                _jobs[job_id] = {
                    "state": "error",
                    "error": err,
                    "lesson_id": gl.id if gl else None,
                }
            else:
                _jobs[job_id] = {
                    "state": "done",
                    "lesson_id": gl.id,
                    "title": gl.title,
                }
    except Exception as e:
        log.exception("Generation failed for source %s", source_id)
        with _jobs_lock:
            _jobs[job_id] = {"state": "error",
                             "error": f"{type(e).__name__}: {e}"}


@app.route("/generate/status/<job_id>")
def generate_status(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"state": "error", "error": "Job not found."}), 404
    return jsonify(job)


# Legacy aliases for the existing progress template.
@app.route("/activity-sheet/status/<job_id>")
def activity_sheet_status(job_id: str):
    return generate_status(job_id)


@app.route("/activity-sheet/download/<job_id>")
def activity_sheet_download(job_id: str):
    """Once a job is done, hand off to the artifact-download endpoint."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job or job.get("state") != "done":
        abort(404)
    pg = get_pg_store()
    if pg is None:
        abort(503)
    lesson_id = job.get("lesson_id")
    artifacts = pg.list_artifacts(lesson_id) if lesson_id else []
    docx = next((a for a in artifacts if a.artifact_type == "docx"), None)
    if not docx:
        abort(404)
    return redirect(
        url_for("lesson_artifact_download",
                lesson_id=lesson_id, artifact_id=docx.id)
    )


# ═══════════════════════════════════════════════════════════════════════════
# Submit (URL paste)
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/submit", methods=["GET"])
def submit_form():
    return render_template("submit.html")


@app.route("/submit", methods=["POST"])
def submit_urls():
    """Process submitted URLs: validate, add to source_content, enrich in background."""
    raw_input = request.form.get("urls", "")
    is_collection = request.form.get("is_collection") == "on"

    urls = [line.strip() for line in raw_input.splitlines()
            if line.strip() and not line.strip().startswith("#")]
    if not urls:
        return render_template("submit.html", error="Please enter at least one URL.")

    invalid = [u for u in urls if not _is_valid_url(u)]
    if invalid:
        msg = f"Invalid URL(s): {', '.join(invalid[:3])}"
        if len(invalid) > 3:
            msg += f" and {len(invalid) - 3} more"
        return render_template("submit.html", error=msg)

    pg = get_pg_store()
    client = HttpClient()
    results = []

    if is_collection and len(urls) == 1:
        collection_data = scrape_collection_page(urls[0], client)
        if not collection_data:
            return render_template(
                "submit.html",
                error="Could not find any lessons on that collection page.",
            )
        for item in collection_data:
            src = SourceContent.from_ted_url(
                item["ted_url"], collection=item.get("collection_name", "")
            )
            if item.get("title"):
                src.title = item["title"]
            stored, was_new = _store_source(pg, src)
            results.append({"source": stored, "was_new": was_new})
    else:
        for url in urls:
            try:
                if "ed.ted.com" in url:
                    src = SourceContent.from_ted_url(url)
                elif "youtube.com" in url or "youtu.be" in url:
                    src = SourceContent.from_youtube_url(url)
                else:
                    raise ValueError("Unrecognized URL format")
            except ValueError as e:
                results.append({"error": str(e), "url": url})
                continue
            stored, was_new = _store_source(pg, src)
            results.append({"source": stored, "was_new": was_new})

    new_sources = [r["source"] for r in results
                   if r.get("was_new") and r.get("source")]
    job_id = None
    if new_sources:
        job_id = str(uuid.uuid4())[:8]
        _start_enrichment_job(job_id, new_sources)

    return render_template("results.html", results=results, job_id=job_id)


def _store_source(pg, src: SourceContent) -> tuple[SourceContent, bool]:
    if pg is not None:
        return pg.add_or_update_source(src)
    # Legacy SQLite path — go through the Lesson API.
    legacy = get_legacy_store()
    lesson = _source_to_legacy_lesson(src)
    legacy_lesson, was_new = legacy.add_or_update(lesson)
    legacy.save()
    return SourceContent.from_lesson(legacy_lesson), was_new


def _source_to_legacy_lesson(src: SourceContent) -> Lesson:
    if src.ted_slug or src.ted_url:
        return Lesson.from_ted_url(src.ted_url or src.source_url, collection=src.collection)
    if src.youtube_id or src.youtube_url:
        return Lesson.from_youtube_url(src.youtube_url or src.source_url)
    return Lesson(canonical_url=src.source_url, source_type=src.source_type)


@app.route("/submit/status/<job_id>")
def submit_status(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if "results" in job:
        return jsonify({
            "status": job.get("status", "running"),
            "completed": job.get("completed", 0),
            "total": job.get("total", 0),
            "results": job.get("results", []),
        })
    return jsonify(job)


# ═══════════════════════════════════════════════════════════════════════════
# Background enrichment (TED/YouTube — keeps using the legacy Lesson pipeline)
# ═══════════════════════════════════════════════════════════════════════════

def _start_enrichment_job(job_id: str, sources: list[SourceContent]):
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "running",
            "total": len(sources),
            "completed": 0,
            "results": [],
        }
    ids = [s.id or s.ted_slug or s.youtube_id for s in sources]
    thread = threading.Thread(
        target=_run_enrichment, args=(job_id, ids), daemon=True,
    )
    thread.start()


def _run_enrichment(job_id: str, source_ids: list[str]):
    client = HttpClient()
    pg = get_pg_store()
    legacy = get_legacy_store() if pg is None else None

    for sid in source_ids:
        try:
            if pg is not None:
                src = pg.find_source_by_id(sid)
                if not src:
                    src = pg.find_source(ted_slug=sid) or pg.find_source(youtube_id=sid)
                if not src:
                    raise RuntimeError("source not found")
                lesson = _source_to_legacy_lesson(src)
                # Carry over any prior IDs/transcript so enrich can dedup.
                lesson.transcript = src.transcript_text
                lesson.transcript_status = src.transcript_status
                lesson.scrape_status = src.scrape_status
                enrich(lesson, client)
                pg.add_or_update(lesson)
                with _jobs_lock:
                    _jobs[job_id]["completed"] += 1
                    _jobs[job_id]["results"].append({
                        "lesson_id": src.id,
                        "title": lesson.title or src.title or sid,
                        "scrape_status": lesson.scrape_status,
                        "transcript_status": lesson.transcript_status,
                    })
            else:
                lesson = legacy.find_by_id(sid)
                if not lesson:
                    raise RuntimeError("not found")
                enrich(lesson, client)
                legacy.add_or_update(lesson)
                legacy.save()
                with _jobs_lock:
                    _jobs[job_id]["completed"] += 1
                    _jobs[job_id]["results"].append({
                        "lesson_id": lesson.lesson_id,
                        "title": lesson.title or sid,
                        "scrape_status": lesson.scrape_status,
                        "transcript_status": lesson.transcript_status,
                    })
        except Exception as e:
            log.exception("Enrichment failed for %s", sid)
            with _jobs_lock:
                _jobs[job_id]["completed"] += 1
                _jobs[job_id]["results"].append({
                    "lesson_id": sid, "status": "error", "message": str(e),
                })

    if legacy is not None:
        legacy.close()
    with _jobs_lock:
        _jobs[job_id]["status"] = "done"


# ═══════════════════════════════════════════════════════════════════════════
# JSON API
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/lessons")
def api_lessons():
    """Legacy: list of Lesson dicts (unchanged shape)."""
    store = get_store()
    q = request.args.get("q", "").strip()
    collection = request.args.get("collection", "").strip()
    page = max(1, request.args.get("page", 1, type=int))

    if hasattr(store, "all_lessons"):
        lessons = store.search(q) if q else store.all_lessons()
    else:
        lessons = []

    if collection:
        lessons = [l for l in lessons if collection.lower() in (l.collection or "").lower()]

    total_results = len(lessons)
    total_pages = max(1, (total_results + PER_PAGE - 1) // PER_PAGE)
    page = min(page, total_pages)
    start = (page - 1) * PER_PAGE
    page_lessons = lessons[start:start + PER_PAGE]

    return jsonify({
        "lessons": [l.to_dict() for l in page_lessons],
        "page": page,
        "total_pages": total_pages,
        "total_results": total_results,
    })


@app.route("/api/lessons/<lesson_id>")
def api_lesson_detail(lesson_id: str):
    store = get_store()
    if hasattr(store, "find_by_id"):
        lesson = store.find_by_id(lesson_id)
        if lesson:
            return jsonify(lesson.to_dict())
    return jsonify({"error": "Lesson not found"}), 404


@app.route("/api/sources")
def api_sources():
    pg = get_pg_store()
    if pg is None:
        return jsonify({"error": "SUPABASE_DB_URL not configured"}), 503
    q = request.args.get("q", "").strip()
    if q:
        sources = pg.search_sources(q)
    else:
        sources = pg.list_sources(
            source_type=request.args.get("source_type") or None,
            collection=request.args.get("collection") or None,
        )
    return jsonify({"sources": [s.to_dict() for s in sources]})


@app.route("/api/generated-lessons")
def api_generated_lessons():
    pg = get_pg_store()
    if pg is None:
        return jsonify({"error": "SUPABASE_DB_URL not configured"}), 503
    rows = pg.list_generated_lessons(
        source_content_id=request.args.get("source") or None,
        lesson_type=request.args.get("type") or None,
    )
    return jsonify({"lessons": [gl.to_dict() for gl in rows]})


@app.route("/api/submit", methods=["POST"])
def api_submit():
    """JSON submit endpoint — same shape as /submit, but returns JSON."""
    data = request.get_json(silent=True)
    if not data or "urls" not in data:
        return jsonify({"error": "JSON body with 'urls' array required"}), 400

    urls = data["urls"]
    if not isinstance(urls, list) or not urls:
        return jsonify({"error": "'urls' must be a non-empty array"}), 400

    invalid = [u for u in urls if not isinstance(u, str) or not _is_valid_url(u)]
    if invalid:
        return jsonify({"error": f"Invalid URL(s): {invalid[:3]}"}), 400

    pg = get_pg_store()
    client = HttpClient()
    is_collection = data.get("collection", False)
    results = []

    if is_collection and len(urls) == 1:
        collection_data = scrape_collection_page(urls[0], client)
        for item in (collection_data or []):
            src = SourceContent.from_ted_url(
                item["ted_url"], collection=item.get("collection_name", ""),
            )
            if item.get("title"):
                src.title = item["title"]
            stored, was_new = _store_source(pg, src)
            if was_new:
                _enrich_inline(stored, client, pg)
            results.append({
                "source_id": stored.id, "title": stored.title, "was_new": was_new,
            })
    else:
        for url in urls:
            try:
                if "ed.ted.com" in url:
                    src = SourceContent.from_ted_url(url)
                elif "youtube.com" in url or "youtu.be" in url:
                    src = SourceContent.from_youtube_url(url)
                else:
                    raise ValueError("Unrecognized URL format")
            except ValueError as e:
                results.append({"url": url, "error": str(e)})
                continue
            stored, was_new = _store_source(pg, src)
            if was_new:
                _enrich_inline(stored, client, pg)
            results.append({
                "source_id": stored.id, "title": stored.title, "was_new": was_new,
            })

    return jsonify({"results": results})


def _enrich_inline(src: SourceContent, client, pg):
    lesson = _source_to_legacy_lesson(src)
    enrich(lesson, client)
    if pg is not None:
        pg.add_or_update(lesson)
    else:
        legacy = get_legacy_store()
        legacy.add_or_update(lesson)
        legacy.save()


# ═══════════════════════════════════════════════════════════════════════════
# Error handlers
# ═══════════════════════════════════════════════════════════════════════════

@app.errorhandler(403)
def forbidden(e):
    return render_template("404.html",
                           message="Forbidden — invalid or missing CSRF token."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(503)
def service_unavailable(e):
    return render_template("404.html",
                           message=str(e.description or "Service unavailable.")), 503


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    app.run(debug=True, host="0.0.0.0", port=5000)
