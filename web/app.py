"""Flask web app for TED-Ed Lesson Database.

Routes:
  /                              Browse all lessons (card grid with thumbnails, search)
  /lesson/<lesson_id>            Lesson detail (metadata, embedded video, transcript)
  /lesson/<lesson_id>/document   Printable lesson document (HTML)
  /lesson/<lesson_id>/pdf        Download lesson document as PDF
  /submit                        Submit form (paste URLs)
  /submit/status/<job_id>        Poll enrichment job progress (JSON)
  /api/lessons                   JSON list (supports ?q= search, ?collection= filter)
  /api/lessons/<id>              Single lesson JSON
  /api/submit                    Submit URLs via API, returns JSON results
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
    make_response,
)

# Add parent to path for ted_lessons import
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ted_lessons.models import Lesson
from ted_lessons.enricher import enrich
from ted_lessons.http_client import HttpClient
from ted_lessons.scraper import scrape_collection_page
from ted_lessons.store import SQLiteStore, DEFAULT_SQLITE_PATH

log = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

# Pagination defaults
PER_PAGE = 24

# Store instance — SQLite for concurrent web access
_store: SQLiteStore | None = None

# Background enrichment jobs: job_id -> {status, results, total, completed}
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def get_store() -> SQLiteStore:
    global _store
    if _store is None:
        db_path = os.environ.get("TED_LESSONS_DB", str(DEFAULT_SQLITE_PATH))
        _store = SQLiteStore(db_path)
    return _store


# ═══════════════════════════════════════════════════════════════════════════
# CSRF protection
# ═══════════════════════════════════════════════════════════════════════════

def _generate_csrf_token() -> str:
    """Generate a CSRF token tied to the session."""
    if "_csrf_secret" not in session:
        session["_csrf_secret"] = secrets.token_hex(16)
    return session["_csrf_secret"]


def _validate_csrf_token(token: str) -> bool:
    """Validate a submitted CSRF token against the session."""
    expected = session.get("_csrf_secret", "")
    if not expected or not token:
        return False
    return hmac.compare_digest(expected, token)


@app.before_request
def _csrf_protect():
    """Check CSRF token on all POST requests with form data."""
    if request.method == "POST" and request.content_type != "application/json":
        token = request.form.get("_csrf_token", "")
        if not _validate_csrf_token(token):
            abort(403)


# Make csrf_token available in all templates
app.jinja_env.globals["csrf_token"] = _generate_csrf_token


# ═══════════════════════════════════════════════════════════════════════════
# URL validation
# ═══════════════════════════════════════════════════════════════════════════

_URL_RE = re.compile(
    r"^https?://"
    r"(ed\.ted\.com/lessons/[\w-]+"           # TED-Ed lesson
    r"|ed\.ted\.com/collections/[\w-]+"       # TED-Ed collection
    r"|(?:www\.)?youtube\.com/watch\?v=[\w-]+"  # YouTube watch
    r"|youtu\.be/[\w-]+"                      # YouTube short
    r")",
    re.IGNORECASE,
)


def _is_valid_url(url: str) -> bool:
    return bool(_URL_RE.match(url.strip()))


# ═══════════════════════════════════════════════════════════════════════════
# Web Routes
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    """Browse all lessons with optional search and collection filter."""
    store = get_store()
    q = request.args.get("q", "").strip()
    collection = request.args.get("collection", "").strip()
    page = max(1, request.args.get("page", 1, type=int))

    if q:
        lessons = store.search(q)
    else:
        lessons = store.all_lessons()

    if collection:
        lessons = [l for l in lessons if collection.lower() in l.collection.lower()]

    # Pagination
    total_results = len(lessons)
    total_pages = max(1, (total_results + PER_PAGE - 1) // PER_PAGE)
    page = min(page, total_pages)
    start = (page - 1) * PER_PAGE
    page_lessons = lessons[start:start + PER_PAGE]

    # Get unique collection names for filter dropdown
    all_lessons = store.all_lessons()
    collections = sorted({l.collection for l in all_lessons if l.collection})

    return render_template("index.html",
                           lessons=page_lessons, q=q, collection=collection,
                           collections=collections, total=len(all_lessons),
                           page=page, total_pages=total_pages,
                           total_results=total_results)


@app.route("/lesson/<lesson_id>")
def lesson_detail(lesson_id: str):
    """Show full details for a single lesson."""
    store = get_store()
    lesson = store.find_by_id(lesson_id)

    if not lesson:
        # Backwards compat: bare slug → try with ted_ prefix
        if not lesson_id.startswith(("ted_", "yt_")):
            prefixed = store.find_by_id(f"ted_{lesson_id}")
            if prefixed:
                return redirect(url_for("lesson_detail", lesson_id=prefixed.lesson_id))
        # Try substring match as last resort
        for l in store.all_lessons():
            if lesson_id in l.lesson_id:
                return redirect(url_for("lesson_detail", lesson_id=l.lesson_id))
        abort(404)

    return render_template("lesson.html", lesson=lesson)


@app.route("/lesson/<lesson_id>/document")
def lesson_document(lesson_id: str):
    """Printable lesson document (Phase 3)."""
    store = get_store()
    lesson = store.find_by_id(lesson_id)
    if not lesson and not lesson_id.startswith(("ted_", "yt_")):
        lesson = store.find_by_id(f"ted_{lesson_id}")
        if lesson:
            return redirect(url_for("lesson_document", lesson_id=lesson.lesson_id))
    if not lesson:
        abort(404)
    return render_template("document.html", lesson=lesson)


@app.route("/lesson/<lesson_id>/pdf")
def lesson_pdf(lesson_id: str):
    """Download lesson document as PDF."""
    store = get_store()
    lesson = store.find_by_id(lesson_id)
    if not lesson and not lesson_id.startswith(("ted_", "yt_")):
        lesson = store.find_by_id(f"ted_{lesson_id}")
        if lesson:
            return redirect(url_for("lesson_pdf", lesson_id=lesson.lesson_id))
    if not lesson:
        abort(404)

    try:
        from weasyprint import HTML
    except ImportError:
        abort(501)  # weasyprint not installed

    html_content = render_template("document.html", lesson=lesson)
    pdf_bytes = HTML(string=html_content, base_url=request.url_root).write_pdf()

    filename = f"{lesson.lesson_id}.pdf"
    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@app.route("/submit", methods=["GET"])
def submit_form():
    """Show the URL submission form."""
    return render_template("submit.html")


@app.route("/submit", methods=["POST"])
def submit_urls():
    """Process submitted URLs: validate, add to store, enrich in background."""
    store = get_store()
    raw_input = request.form.get("urls", "")
    is_collection = request.form.get("is_collection") == "on"

    # Parse URLs from input (one per line, strip whitespace)
    urls = [line.strip() for line in raw_input.splitlines()
            if line.strip() and not line.strip().startswith("#")]

    if not urls:
        return render_template("submit.html", error="Please enter at least one URL.")

    # Validate URLs
    invalid = [u for u in urls if not _is_valid_url(u)]
    if invalid:
        msg = f"Invalid URL(s): {', '.join(invalid[:3])}"
        if len(invalid) > 3:
            msg += f" and {len(invalid) - 3} more"
        return render_template("submit.html", error=msg)

    # Phase 1: add all URLs immediately (fast — no network)
    client = HttpClient()
    results = []

    if is_collection and len(urls) == 1:
        # Collection: scrape synchronously (fast), then enrich in background
        collection_data = scrape_collection_page(urls[0], client)
        if not collection_data:
            return render_template("submit.html",
                                   error="Could not find any lessons on that collection page.")
        for item in collection_data:
            lesson = Lesson.from_ted_url(item["ted_url"], collection=item.get("collection_name", ""))
            if item.get("title"):
                lesson.title = item["title"]
            lesson, was_new = store.add_or_update(lesson)
            results.append({"lesson": lesson, "was_new": was_new})
    else:
        for url in urls:
            try:
                lesson = Lesson.from_url(url)
            except ValueError as e:
                results.append({"error": str(e), "url": url})
                continue
            lesson, was_new = store.add_or_update(lesson)
            results.append({"lesson": lesson, "was_new": was_new})

    store.save()

    # Phase 2: kick off background enrichment for new lessons
    new_lessons = [r["lesson"] for r in results if r.get("was_new") and r.get("lesson")]
    job_id = None
    if new_lessons:
        job_id = str(uuid.uuid4())[:8]
        _start_enrichment_job(job_id, new_lessons)

    return render_template("results.html", results=results, job_id=job_id)


@app.route("/submit/status/<job_id>")
def submit_status(job_id: str):
    """Poll enrichment job progress."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "status": job["status"],
        "completed": job["completed"],
        "total": job["total"],
        "results": job["results"],
    })


# ═══════════════════════════════════════════════════════════════════════════
# Background enrichment
# ═══════════════════════════════════════════════════════════════════════════

def _start_enrichment_job(job_id: str, lessons: list[Lesson]):
    """Start enrichment of lessons in a background thread."""
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "running",
            "total": len(lessons),
            "completed": 0,
            "results": [],
        }

    thread = threading.Thread(
        target=_run_enrichment,
        args=(job_id, [l.lesson_id for l in lessons]),
        daemon=True,
    )
    thread.start()


def _run_enrichment(job_id: str, lesson_ids: list[str]):
    """Background thread: enrich each lesson and update job status."""
    client = HttpClient()
    # Create a separate SQLiteStore for this thread (SQLite connections are thread-local)
    db_path = os.environ.get("TED_LESSONS_DB", str(DEFAULT_SQLITE_PATH))
    store = SQLiteStore(db_path)

    for lid in lesson_ids:
        lesson = store.find_by_id(lid)
        if not lesson:
            with _jobs_lock:
                _jobs[job_id]["completed"] += 1
                _jobs[job_id]["results"].append({
                    "lesson_id": lid, "status": "error", "message": "Not found"
                })
            continue

        try:
            enrich(lesson, client)
            store.add_or_update(lesson)
            store.save()
        except Exception as e:
            log.exception("Enrichment failed for %s", lid)

        with _jobs_lock:
            _jobs[job_id]["completed"] += 1
            _jobs[job_id]["results"].append({
                "lesson_id": lid,
                "title": lesson.title or lid,
                "scrape_status": lesson.scrape_status,
                "transcript_status": lesson.transcript_status,
            })

    store.close()

    with _jobs_lock:
        _jobs[job_id]["status"] = "done"


# ═══════════════════════════════════════════════════════════════════════════
# API Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/lessons")
def api_lessons():
    """JSON list of lessons with optional search and collection filter."""
    store = get_store()
    q = request.args.get("q", "").strip()
    collection = request.args.get("collection", "").strip()
    page = max(1, request.args.get("page", 1, type=int))

    if q:
        lessons = store.search(q)
    else:
        lessons = store.all_lessons()

    if collection:
        lessons = [l for l in lessons if collection.lower() in l.collection.lower()]

    # Pagination
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
    """Single lesson JSON by lesson_id."""
    store = get_store()
    lesson = store.find_by_id(lesson_id)
    if not lesson:
        return jsonify({"error": "Lesson not found"}), 404
    return jsonify(lesson.to_dict())


@app.route("/api/submit", methods=["POST"])
def api_submit():
    """Submit URLs via API. Accepts JSON body: {"urls": [...], "collection": bool}."""
    store = get_store()
    data = request.get_json(silent=True)
    if not data or "urls" not in data:
        return jsonify({"error": "JSON body with 'urls' array required"}), 400

    urls = data["urls"]
    if not isinstance(urls, list) or not urls:
        return jsonify({"error": "'urls' must be a non-empty array"}), 400

    # Validate URLs
    invalid = [u for u in urls if not isinstance(u, str) or not _is_valid_url(u)]
    if invalid:
        return jsonify({"error": f"Invalid URL(s): {invalid[:3]}"}), 400

    is_collection = data.get("collection", False)
    client = HttpClient()
    results = []

    if is_collection and len(urls) == 1:
        collection_data = scrape_collection_page(urls[0], client)
        for item in (collection_data or []):
            lesson = Lesson.from_ted_url(item["ted_url"], collection=item.get("collection_name", ""))
            if item.get("title"):
                lesson.title = item["title"]
            lesson, was_new = store.add_or_update(lesson)
            if was_new:
                enrich(lesson, client)
                store.add_or_update(lesson)
            results.append({"lesson_id": lesson.lesson_id, "title": lesson.title, "was_new": was_new})
    else:
        for url in urls:
            try:
                lesson = Lesson.from_url(url)
            except ValueError as e:
                results.append({"url": url, "error": str(e)})
                continue
            lesson, was_new = store.add_or_update(lesson)
            if was_new:
                enrich(lesson, client)
                store.add_or_update(lesson)
            results.append({"lesson_id": lesson.lesson_id, "title": lesson.title, "was_new": was_new})

    store.save()
    return jsonify({"results": results, "total": len(store)})


# ═══════════════════════════════════════════════════════════════════════════
# Error Handlers
# ═══════════════════════════════════════════════════════════════════════════

@app.errorhandler(403)
def forbidden(e):
    return render_template("404.html", message="Forbidden — invalid or missing CSRF token."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


# ═══════════════════════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app.run(debug=True, host="0.0.0.0", port=5000)
