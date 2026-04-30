"""Tests for ted_lessons.store.merge_lesson and SQLiteStore thread safety.

merge_lesson must propagate enrichment outcomes (status, last_enriched,
error_message) without clobbering successful prior data.

SQLiteStore must be safe to use from multiple threads — the bug that took
down the Render deploy was a single connection shared across gthread workers.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ted_lessons.models import Lesson
from ted_lessons.store import SQLiteStore, merge_lesson


def _make(scrape_status="", transcript_status="", transcript="",
          last_enriched="", error_message="", **fields):
    base = dict(
        lesson_id="ted_t", ted_slug="t", youtube_id="abc",
        ted_url="https://ed.ted.com/lessons/t",
        scrape_status=scrape_status,
        transcript_status=transcript_status,
        transcript=transcript,
        last_enriched=last_enriched,
        error_message=error_message,
    )
    base.update(fields)
    return Lesson(**base)


# ─── merge_lesson ────────────────────────────────────────────────────────────

def test_merge_propagates_scrape_ok():
    existing = _make()
    incoming = _make(scrape_status="ok", title="Hello")
    merge_lesson(existing, incoming)
    assert existing.scrape_status == "ok"
    assert existing.title == "Hello"


def test_merge_propagates_scrape_failed():
    existing = _make()
    incoming = _make(scrape_status="failed", error_message="boom")
    merge_lesson(existing, incoming)
    assert existing.scrape_status == "failed"
    assert existing.error_message == "boom"


def test_merge_propagates_transcript_ok():
    existing = _make()
    incoming = _make(transcript_status="ok", transcript="Hello world")
    merge_lesson(existing, incoming)
    assert existing.transcript_status == "ok"
    assert existing.transcript == "Hello world"


def test_merge_propagates_transcript_failed_when_existing_empty():
    existing = _make()
    incoming = _make(transcript_status="failed")
    merge_lesson(existing, incoming)
    assert existing.transcript_status == "failed"


def test_merge_does_not_overwrite_good_transcript_with_failure():
    existing = _make(transcript_status="ok", transcript="GOOD")
    incoming = _make(transcript_status="failed")
    merge_lesson(existing, incoming)
    assert existing.transcript_status == "ok"
    assert existing.transcript == "GOOD"


def test_merge_does_not_overwrite_good_transcript_with_unavailable():
    existing = _make(transcript_status="ok", transcript="GOOD")
    incoming = _make(transcript_status="unavailable")
    merge_lesson(existing, incoming)
    assert existing.transcript_status == "ok"
    assert existing.transcript == "GOOD"


def test_merge_propagates_last_enriched_and_error():
    existing = _make()
    incoming = _make(scrape_status="ok",
                     last_enriched="2026-04-30T17:00:00+00:00",
                     error_message="warn")
    merge_lesson(existing, incoming)
    assert existing.last_enriched == "2026-04-30T17:00:00+00:00"
    assert existing.error_message == "warn"


def test_merge_empty_status_does_not_clobber_existing_ok():
    existing = _make(scrape_status="ok")
    incoming = _make()  # blank
    merge_lesson(existing, incoming)
    assert existing.scrape_status == "ok"


# ─── SQLiteStore thread safety ───────────────────────────────────────────────

def test_store_usable_from_multiple_threads(tmp_path):
    db = tmp_path / "t.db"
    store = SQLiteStore(db)

    seed = _make(lesson_id="ted_t1", ted_slug="t1", youtube_id="A1")
    store.add_or_update(seed)
    store.save()

    errors: list[Exception] = []
    results: list[int] = []

    def worker():
        try:
            n = len(store)
            results.append(n)
            found = store.find_by_id("ted_t1")
            assert found is not None
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"Thread errors: {errors}"
    assert results == [1] * 8
