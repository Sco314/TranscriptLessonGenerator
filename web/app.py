"""Flask web app for TED-Ed Lesson Database.

Routes:
  /                       Browse all lessons (card grid with thumbnails, search)
  /lesson/<lesson_id>     Lesson detail (metadata, embedded video, transcript)
  /submit                 Submit form (paste URLs)
  /api/lessons            JSON list (supports ?q= search, ?collection= filter)
  /api/lessons/<id>       Single lesson JSON
  /api/submit             Submit URLs via API, returns JSON results
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, jsonify, abort

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

# Store instance — SQLite for concurrent web access
_store: SQLiteStore | None = None


def get_store() -> SQLiteStore:
    global _store
    if _store is None:
        db_path = os.environ.get("TED_LESSONS_DB", str(DEFAULT_SQLITE_PATH))
        _store = SQLiteStore(db_path)
    return _store


# ═══════════════════════════════════════════════════════════════════════════
# Web Routes
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    """Browse all lessons with optional search and collection filter."""
    store = get_store()
    q = request.args.get("q", "").strip()
    collection = request.args.get("collection", "").strip()

    if q:
        lessons = store.search(q)
    else:
        lessons = store.all_lessons()

    if collection:
        lessons = [l for l in lessons if collection.lower() in l.collection.lower()]

    # Get unique collection names for filter dropdown
    all_lessons = store.all_lessons()
    collections = sorted({l.collection for l in all_lessons if l.collection})

    return render_template("index.html",
                           lessons=lessons, q=q, collection=collection,
                           collections=collections, total=len(all_lessons))


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


@app.route("/submit", methods=["GET"])
def submit_form():
    """Show the URL submission form."""
    return render_template("submit.html")


@app.route("/submit", methods=["POST"])
def submit_urls():
    """Process submitted URLs and show results."""
    store = get_store()
    raw_input = request.form.get("urls", "")
    is_collection = request.form.get("is_collection") == "on"

    # Parse URLs from input (one per line, strip whitespace)
    urls = [line.strip() for line in raw_input.splitlines() if line.strip() and not line.strip().startswith("#")]

    if not urls:
        return render_template("submit.html", error="Please enter at least one URL.")

    client = HttpClient()
    results = []

    if is_collection and len(urls) == 1:
        # Treat single URL as a collection page
        collection_data = scrape_collection_page(urls[0], client)
        if collection_data:
            for item in collection_data:
                lesson = Lesson.from_ted_url(item["ted_url"], collection=item.get("collection_name", ""))
                if item.get("title"):
                    lesson.title = item["title"]
                lesson, was_new = store.add_or_update(lesson)
                if was_new:
                    enrich(lesson, client)
                    store.add_or_update(lesson)
                results.append({"lesson": lesson, "was_new": was_new})
        else:
            return render_template("submit.html",
                                   error="Could not find any lessons on that collection page.")
    else:
        # Process individual URLs
        for url in urls:
            try:
                lesson = Lesson.from_url(url)
            except ValueError as e:
                results.append({"error": str(e), "url": url})
                continue

            lesson, was_new = store.add_or_update(lesson)
            if was_new:
                enrich(lesson, client)
                store.add_or_update(lesson)
            results.append({"lesson": lesson, "was_new": was_new})

    store.save()
    return render_template("results.html", results=results)


# ═══════════════════════════════════════════════════════════════════════════
# API Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/lessons")
def api_lessons():
    """JSON list of lessons with optional search and collection filter."""
    store = get_store()
    q = request.args.get("q", "").strip()
    collection = request.args.get("collection", "").strip()

    if q:
        lessons = store.search(q)
    else:
        lessons = store.all_lessons()

    if collection:
        lessons = [l for l in lessons if collection.lower() in l.collection.lower()]

    return jsonify([l.to_dict() for l in lessons])


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

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


# ═══════════════════════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app.run(debug=True, host="0.0.0.0", port=5000)
