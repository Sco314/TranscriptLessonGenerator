#!/usr/bin/env python3
"""Seed the lesson DB with a small set of demo TED-Ed lessons.

Idempotent: skips any lesson that's already in the store. Safe to run on
every boot — see web/app.py for the auto-seed-if-empty hook.

Usage (standalone):
    python scripts/seed_demo_lessons.py
    python scripts/seed_demo_lessons.py --limit 3
    python scripts/seed_demo_lessons.py --no-enrich   # add only, skip transcripts

Usage (programmatic):
    from scripts.seed_demo_lessons import seed
    seed(store, enrich_new=True)
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ted_lessons.enricher import enrich
from ted_lessons.http_client import HttpClient
from ted_lessons.models import Lesson
from ted_lessons.store import SQLiteStore, get_store

log = logging.getLogger(__name__)

# Curated short list of TED-Ed lessons with reliable transcripts. These are
# popular riddles + a couple of explainer videos — chosen because they load
# fast, have YouTube captions, and exercise the worksheet generator's
# transcript path.
DEMO_LESSON_URLS: list[str] = [
    "https://ed.ted.com/lessons/can-you-solve-the-prisoner-hat-riddle-alex-gendler",
    "https://ed.ted.com/lessons/can-you-solve-the-bridge-riddle-alex-gendler",
    "https://ed.ted.com/lessons/can-you-solve-einstein-s-riddle-dan-van-der-vieren",
    "https://ed.ted.com/lessons/can-you-solve-the-pirate-riddle-alex-gendler",
    "https://ed.ted.com/lessons/how-to-spot-a-misleading-graph-lea-gaslowitz",
]


def seed(store: SQLiteStore, *, enrich_new: bool = True,
         limit: int | None = 3,
         pause_seconds: float = 5.0,
         http_client: HttpClient | None = None) -> dict:
    """Add the demo URLs to the store. Idempotent.

    Returns a summary dict: {added, skipped, enriched, failed}.

    Defaults aimed at low-memory free-tier hosts: 3 lessons, 5s pause
    between enrichments. Pass limit=None to use the full DEMO_LESSON_URLS list.
    """
    urls = DEMO_LESSON_URLS[:limit] if limit else DEMO_LESSON_URLS
    client = http_client or HttpClient()
    summary = {"added": 0, "skipped": 0, "enriched": 0, "failed": 0}

    for idx, url in enumerate(urls):
        try:
            candidate = Lesson.from_url(url)
        except ValueError as e:
            log.warning("Bad demo URL %s: %s", url, e)
            summary["failed"] += 1
            continue

        existing = store.find_by_id(candidate.lesson_id)
        if existing:
            summary["skipped"] += 1
            log.info("Skip %s (already in store)", candidate.lesson_id)
            continue

        lesson, _ = store.add_or_update(candidate)
        summary["added"] += 1
        log.info("Added %s", lesson.lesson_id)

        if enrich_new:
            try:
                enrich(lesson, client)
                store.add_or_update(lesson)
                summary["enriched"] += 1
                log.info(
                    "Enriched %s (scrape=%s, transcript=%s)",
                    lesson.lesson_id, lesson.scrape_status, lesson.transcript_status,
                )
            except Exception:
                log.exception("Enrichment failed for %s", lesson.lesson_id)
                summary["failed"] += 1

            if pause_seconds > 0 and idx < len(urls) - 1:
                time.sleep(pause_seconds)

    store.save()
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the lesson DB with demo TED-Ed lessons.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only seed the first N URLs.")
    parser.add_argument("--no-enrich", action="store_true",
                        help="Add lessons but skip transcript fetching.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    store = get_store()
    summary = seed(store, enrich_new=not args.no_enrich, limit=args.limit)
    print(
        f"✅ Seed complete: added={summary['added']}, skipped={summary['skipped']}, "
        f"enriched={summary['enriched']}, failed={summary['failed']}"
    )
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
