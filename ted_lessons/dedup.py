"""Shared deduplication logic for migration and data consolidation.

Used by both cli.py (migrate command) and scripts/migrate_csv_to_sqlite.py
to ensure identical, deterministic dedup behavior.
"""

from __future__ import annotations

from .models import Lesson

_CONTENT_FIELDS = [
    "title", "collection", "author", "duration", "views", "category",
    "ted_url", "youtube_url", "description", "tags", "transcript",
]


def content_field_count(lesson: Lesson) -> int:
    """Count non-empty content fields for migration tie-breaking."""
    return sum(1 for f in _CONTENT_FIELDS if getattr(lesson, f, ""))


def pick_best_row(a: Lesson, b: Lesson) -> Lesson:
    """Deterministic best-row selection for migration dedup.

    Priority (first match wins):
      1. Prefer transcript_status == "ok"
      2. Prefer scrape_status == "ok"
      3. Prefer more non-empty content fields
      4. Prefer newer last_enriched timestamp
      5. Tie: keep first (stable)
    """
    # 1. Prefer transcript_status == "ok"
    a_tok = a.transcript_status == "ok"
    b_tok = b.transcript_status == "ok"
    if a_tok and not b_tok:
        return a
    if b_tok and not a_tok:
        return b

    # 2. Prefer scrape_status == "ok"
    a_sok = a.scrape_status == "ok"
    b_sok = b.scrape_status == "ok"
    if a_sok and not b_sok:
        return a
    if b_sok and not a_sok:
        return b

    # 3. Prefer more non-empty content fields
    a_count = content_field_count(a)
    b_count = content_field_count(b)
    if a_count != b_count:
        return a if a_count > b_count else b

    # 4. Prefer newer last_enriched
    if a.last_enriched > b.last_enriched:
        return a
    if b.last_enriched > a.last_enriched:
        return b

    # Tie: keep first (stable)
    return a


def collapse_duplicates(lessons: list[Lesson]) -> tuple[dict[str, Lesson], int, list[str]]:
    """Collapse a list of lessons by lesson_id using deterministic best-row rules.

    Returns:
        (deduped_dict, duplicate_count, skip_messages)
    """
    deduped: dict[str, Lesson] = {}
    duplicates = 0
    skipped: list[str] = []

    for lesson in lessons:
        lid = lesson.lesson_id
        if not lid:
            lesson.ensure_ids()
            lid = lesson.lesson_id
            if not lid:
                skipped.append(f"Row with no identifiable ID: title='{lesson.title}'")
                continue

        if lid in deduped:
            duplicates += 1
            existing = deduped[lid]
            winner = pick_best_row(existing, lesson)
            loser = lesson if winner is existing else existing
            # Preserve successful transcript from loser
            if loser.transcript_status == "ok" and winner.transcript_status != "ok":
                winner.transcript = loser.transcript
                winner.transcript_status = loser.transcript_status
            deduped[lid] = winner
        else:
            deduped[lid] = lesson

    return deduped, duplicates, skipped
