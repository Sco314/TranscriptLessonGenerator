"""Unit tests for SourceContent, the CSV importer, and spec_to_html."""

from __future__ import annotations

import io
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "web"))

from ted_lessons.models import Lesson, SourceContent  # noqa: E402
from web.importers.csv_import import import_csv_text  # noqa: E402
from spec_to_html import render_html  # noqa: E402


# ---------------------------------------------------------------------------
# SourceContent.from_lesson
# ---------------------------------------------------------------------------

def test_from_lesson_ted_url_keeps_provenance():
    lesson = Lesson.from_ted_url(
        "https://ed.ted.com/lessons/the-prison-break-riddle"
    )
    lesson.title = "The prison break riddle"
    lesson.transcript = "Once upon a time..."
    lesson.transcript_status = "ok"
    lesson.scrape_status = "ok"
    lesson.collection = "Riddles"

    src = SourceContent.from_lesson(lesson)

    assert src.source_type == "ted_ed"
    assert src.ted_slug == "the-prison-break-riddle"
    assert src.title == "The prison break riddle"
    assert src.collection == "Riddles"
    assert src.transcript_text == "Once upon a time..."
    assert src.transcript_status == "ok"
    assert src.source_url.startswith("https://ed.ted.com/lessons/")
    # New SourceContent gets a fresh UUID id, not the legacy lesson_id.
    assert src.id and src.id != lesson.lesson_id


def test_from_lesson_youtube_url():
    lesson = Lesson.from_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    src = SourceContent.from_lesson(lesson)
    assert src.source_type == "youtube"
    assert src.youtube_id == "dQw4w9WgXcQ"
    assert src.source_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_has_usable_body_for_ted_requires_ok_transcript():
    src = SourceContent.from_ted_url("https://ed.ted.com/lessons/example")
    assert not src.has_usable_body
    src.transcript_text = "abc"
    src.transcript_status = "ok"
    assert src.has_usable_body


def test_has_usable_body_for_pasted_text():
    src = SourceContent.from_pasted_text("Some pasted notes.")
    assert src.source_type == "pasted_text"
    assert src.has_usable_body


def test_has_usable_body_for_pdf():
    src = SourceContent.from_pdf("Extracted from PDF.")
    assert src.source_type == "pdf"
    assert src.has_usable_body


# ---------------------------------------------------------------------------
# CSV importer
# ---------------------------------------------------------------------------

class _FakeStore:
    def __init__(self):
        self.calls = []

    def add_or_update_source(self, src):
        # Dedup by source_url to mimic Postgres behavior.
        for existing in self.calls:
            if existing.source_url and existing.source_url == src.source_url:
                return existing, False
        self.calls.append(src)
        return src, True


def test_import_csv_text_modern_columns():
    csv_text = (
        "title,collection,author,duration,ted_url,youtube_url,transcript\n"
        "Riddle 1,Riddles,Alex,5:01,"
        "https://ed.ted.com/lessons/r1,https://youtu.be/aaaaaaaaaaa,Hello\n"
        "Riddle 2,Riddles,Sam,4:00,"
        "https://ed.ted.com/lessons/r2,https://youtu.be/bbbbbbbbbbb,World\n"
    )
    store = _FakeStore()
    report = import_csv_text(csv_text, store)
    assert report.inserted == 2
    assert report.failed == 0
    assert all(s.source_type == "ted_ed" for s in store.calls)
    assert {s.title for s in store.calls} == {"Riddle 1", "Riddle 2"}
    # Transcript inferred status.
    assert all(s.transcript_status == "ok" for s in store.calls)


def test_import_csv_text_legacy_apps_script_columns():
    csv_text = (
        "Title,Collection,Author,Duration,TED Lesson URL,YouTube URL,Description,Transcript\n"
        "Lesson A,Coll A,Person A,3:00,"
        "https://ed.ted.com/lessons/a,https://youtu.be/cccccccccccc,desc,t1\n"
    )
    store = _FakeStore()
    report = import_csv_text(csv_text, store)
    assert report.inserted == 1
    s = store.calls[0]
    assert s.title == "Lesson A"
    assert s.collection == "Coll A"
    assert s.author == "Person A"
    assert s.duration == "3:00"
    assert s.transcript_text == "t1"


def test_import_csv_text_dedups_on_repeat():
    csv_text = (
        "title,ted_url\n"
        "Lesson,https://ed.ted.com/lessons/dup\n"
        "Lesson,https://ed.ted.com/lessons/dup\n"
    )
    store = _FakeStore()
    report = import_csv_text(csv_text, store)
    assert report.inserted == 1
    assert report.updated == 1


def test_import_csv_text_skips_rows_without_url():
    csv_text = "title,description\nNo URL,nothing here\n"
    store = _FakeStore()
    report = import_csv_text(csv_text, store)
    assert report.errors  # importer reports the missing URL column
    assert report.inserted == 0


# ---------------------------------------------------------------------------
# spec_to_html
# ---------------------------------------------------------------------------

_MINI_SPEC = {
    "theme": "teal",
    "header_name": "Test",
    "page1": [
        {"type": "title", "text": "Hello"},
        {"type": "subtitle", "text": "World"},
        {"type": "section_header", "text": "Watch"},
        {
            "type": "numbered_question",
            "number": 1,
            "runs": [{"text": "Fill in: "}, {"blank": 6}, {"text": "."}],
        },
    ],
    "page2": [
        {"type": "section_header", "text": "Score"},
        {
            "type": "self_check_box",
            "items": ["Did the thing", "Named names"],
        },
    ],
}


def test_render_html_contains_text_and_structure():
    html = render_html(_MINI_SPEC)
    assert "<h1" in html and "Hello" in html
    assert "World" in html
    assert "Watch" in html
    # Numbered question runs include the blank.
    assert "ws-blank" in html
    # Self-check box renders the list items.
    assert "Did the thing" in html
    assert "Named names" in html
    # Theme primary color shows up as inline CSS.
    assert "--theme-primary:#00695C" in html


def test_render_html_html_escapes_user_text():
    spec = {
        "theme": "teal",
        "header_name": "Test",
        "page1": [{"type": "title", "text": "<script>alert(1)</script>"}],
        "page2": [{"type": "title", "text": "ok"}],
    }
    html = render_html(spec)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
