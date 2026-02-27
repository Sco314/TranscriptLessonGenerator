"""CLI entry point for ted_lessons — add, enrich, list, search, show, export, migrate."""

from __future__ import annotations

import argparse
import logging
import sys

from .enricher import enrich
from .http_client import HttpClient
from .models import Lesson
from .scraper import scrape_collection_page
from .store import CSVStore, SQLiteStore, get_store, DEFAULT_CSV_PATH, DEFAULT_SQLITE_PATH


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        prog="ted_lessons",
        description="TED-Ed Lesson Database — scrape, enrich, and manage TED-Ed lesson data.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--backend", choices=["auto", "csv", "sqlite"], default="auto",
        help="Storage backend (default: auto — uses sqlite if db exists, else csv)",
    )
    parser.add_argument("--data", default=None, help="Path to data file (csv or sqlite db)")

    sub = parser.add_subparsers(dest="command")

    # --- add ---
    p_add = sub.add_parser("add", help="Add lessons by URL")
    p_add.add_argument("urls", nargs="*", help="TED-Ed or YouTube URLs")
    p_add.add_argument("--file", "-f", help="File with one URL per line")
    p_add.add_argument("--collection", "-c", help="TED-Ed collection URL to import")
    p_add.add_argument("--no-enrich", action="store_true", help="Add without enriching (just store the URL)")

    # --- enrich ---
    p_enrich = sub.add_parser("enrich", help="Fill missing fields on existing lessons")
    p_enrich.add_argument("--retry-failed", action="store_true", help="Retry previously failed items")

    # --- list ---
    p_list = sub.add_parser("list", help="List all lessons")
    p_list.add_argument("--collection", help="Filter by collection name")

    # --- search ---
    p_search = sub.add_parser("search", help="Search lessons")
    p_search.add_argument("query", help="Search query")

    # --- show ---
    p_show = sub.add_parser("show", help="Show full details for a lesson")
    p_show.add_argument("lesson_id", help="Lesson ID (ted slug or yt_XXXXX)")

    # --- export ---
    p_export = sub.add_parser("export", help="Export to CSV")
    p_export.add_argument("--csv", default=str(DEFAULT_CSV_PATH), help="Output CSV path")

    # --- migrate ---
    p_migrate = sub.add_parser("migrate", help="Migrate CSV data to SQLite")
    p_migrate.add_argument("--csv", default=str(DEFAULT_CSV_PATH), help="Source CSV path")
    p_migrate.add_argument("--db", default=str(DEFAULT_SQLITE_PATH), help="Target SQLite path")
    p_migrate.add_argument("--dry-run", action="store_true", help="Preview without writing")

    args = parser.parse_args(argv)

    # Logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s" if not args.verbose else "%(levelname)s %(name)s: %(message)s",
    )

    if not args.command:
        parser.print_help()
        return

    # Migration doesn't need the normal store
    if args.command == "migrate":
        cmd_migrate(args)
        return

    store = get_store(backend=args.backend, path=args.data)

    if args.command == "add":
        cmd_add(args, store)
    elif args.command == "enrich":
        cmd_enrich(args, store)
    elif args.command == "list":
        cmd_list(args, store)
    elif args.command == "search":
        cmd_search(args, store)
    elif args.command == "show":
        cmd_show(args, store)
    elif args.command == "export":
        cmd_export(args, store)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_add(args, store):
    """Add lessons from URLs, file, or collection."""
    urls = list(args.urls) if args.urls else []

    # Read URLs from file
    if args.file:
        try:
            with open(args.file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        urls.append(line)
        except FileNotFoundError:
            print(f"Error: File not found: {args.file}")
            sys.exit(1)

    client = HttpClient()

    # Collection import
    if args.collection:
        print(f"Importing collection: {args.collection}")
        collection_lessons = scrape_collection_page(args.collection, client)
        if not collection_lessons:
            print("  No lessons found in collection page.")
        else:
            print(f"  Found {len(collection_lessons)} lessons")
            for item in collection_lessons:
                lesson = Lesson.from_ted_url(item["ted_url"], collection=item.get("collection_name", ""))
                if item.get("title"):
                    lesson.title = item["title"]
                lesson, was_new = store.add_or_update(lesson)
                status = "NEW" if was_new else "exists"
                print(f"  [{status}] {lesson.title or lesson.lesson_id}")
                if was_new and not args.no_enrich:
                    enrich(lesson, client)
                    print(f"         scrape: {lesson.scrape_status}, transcript: {lesson.transcript_status}")
            store.save()

    if not urls and not args.collection:
        print("Error: Provide URLs, --file, or --collection")
        sys.exit(1)

    if not urls:
        return

    # Process individual URLs
    added = 0
    existed = 0
    for url in urls:
        try:
            lesson = Lesson.from_url(url)
        except ValueError as e:
            print(f"  [SKIP] {url}: {e}")
            continue

        lesson, was_new = store.add_or_update(lesson)
        if was_new:
            added += 1
            print(f"  [NEW] {lesson.lesson_id}")
            if not args.no_enrich:
                enrich(lesson, client)
                print(f"        title: {lesson.title}")
                print(f"        scrape: {lesson.scrape_status}, transcript: {lesson.transcript_status}")
        else:
            existed += 1
            print(f"  [EXISTS] {lesson.title or lesson.lesson_id}")

    store.save()
    print(f"\nDone. Added: {added}, Already existed: {existed}, Total: {len(store)}")


def cmd_enrich(args, store):
    """Fill missing fields on existing lessons."""
    pending = store.needs_enrichment(retry_failed=args.retry_failed)
    if not pending:
        print("All lessons are fully enriched. Nothing to do.")
        return

    print(f"Enriching {len(pending)} lesson(s)...")
    client = HttpClient()

    for i, lesson in enumerate(pending, 1):
        print(f"  [{i}/{len(pending)}] {lesson.title or lesson.lesson_id}")
        enrich(lesson, client)
        print(f"           scrape: {lesson.scrape_status}, transcript: {lesson.transcript_status}")
        if lesson.error_message:
            print(f"           error: {lesson.error_message}")
        # Save after each lesson for SQLite (cheap), batch for CSV
        if isinstance(store, SQLiteStore):
            store.add_or_update(lesson)

    store.save()
    print(f"\nDone. Enriched {len(pending)} lesson(s).")


def cmd_list(args, store):
    """List all lessons."""
    lessons = store.all_lessons()
    if hasattr(args, "collection") and args.collection:
        q = args.collection.lower()
        lessons = [l for l in lessons if q in l.collection.lower()]

    if not lessons:
        print("No lessons found.")
        return

    print(f"{'ID':<45} {'Title':<40} {'S':>1} {'T':>1}")
    print("-" * 90)
    for lesson in lessons:
        lid = lesson.lesson_id[:44]
        title = lesson.title[:39] if lesson.title else "(untitled)"
        s = _status_char(lesson.scrape_status)
        t = _status_char(lesson.transcript_status)
        print(f"{lid:<45} {title:<40} {s:>1} {t:>1}")
    print(f"\n{len(lessons)} lesson(s). S=scrape status, T=transcript status (+ok, !fail, -unavail, ?pending)")


def cmd_search(args, store):
    """Search lessons."""
    results = store.search(args.query)
    if not results:
        print(f"No lessons matching '{args.query}'")
        return

    print(f"Found {len(results)} result(s) for '{args.query}':\n")
    for lesson in results:
        print(f"  {lesson.lesson_id}")
        print(f"    Title: {lesson.title}")
        if lesson.collection:
            print(f"    Collection: {lesson.collection}")
        if lesson.author:
            print(f"    Author: {lesson.author}")
        print()


def cmd_show(args, store):
    """Show full details for a lesson."""
    lesson = store.find_by_id(args.lesson_id)
    if not lesson:
        # Try substring match
        for l in store.all_lessons():
            if args.lesson_id in l.lesson_id:
                lesson = l
                break
    if not lesson:
        print(f"Lesson not found: {args.lesson_id}")
        sys.exit(1)

    print(f"Lesson: {lesson.lesson_id}")
    print(f"  Title:       {lesson.title}")
    print(f"  Author:      {lesson.author}")
    print(f"  Collection:  {lesson.collection}")
    print(f"  Category:    {lesson.category}")
    print(f"  Duration:    {lesson.duration}")
    print(f"  Views:       {lesson.views}")
    print(f"  TED URL:     {lesson.ted_url}")
    print(f"  YouTube URL: {lesson.youtube_url}")
    print(f"  Thumbnail:   {lesson.thumbnail_url}")
    desc = lesson.description
    print(f"  Description: {desc[:200]}{'...' if len(desc) > 200 else ''}")
    print(f"  Tags:        {lesson.tags}")
    print()
    print(f"  Scrape status:     {lesson.scrape_status}")
    print(f"  Transcript status: {lesson.transcript_status}")
    print(f"  Last enriched:     {lesson.last_enriched}")
    if lesson.error_message:
        print(f"  Error:             {lesson.error_message}")
    print()
    if lesson.transcript:
        preview = lesson.transcript[:500]
        print(f"  Transcript preview ({len(lesson.transcript)} chars total):")
        print(f"  {preview}{'...' if len(lesson.transcript) > 500 else ''}")


def cmd_export(args, store):
    """Export lessons to CSV."""
    csv_store = CSVStore(args.csv)
    csv_store._lessons = store.all_lessons()
    csv_store.save()
    print(f"Exported {len(store)} lessons to {args.csv}")


def cmd_migrate(args):
    """Migrate CSV data to SQLite."""
    csv_store = CSVStore(args.csv)
    lessons = csv_store.all_lessons()

    if not lessons:
        print(f"No lessons found in {args.csv}. Nothing to migrate.")
        return

    print(f"Loaded {len(lessons)} lesson(s) from {args.csv}")

    # Collapse duplicates by lesson_id
    deduped: dict[str, Lesson] = {}
    duplicates = 0
    for lesson in lessons:
        lid = lesson.lesson_id
        if not lid:
            lesson.ensure_ids()
            lid = lesson.lesson_id
            if not lid:
                print(f"  [SKIP] Row with no identifiable ID: title='{lesson.title}'")
                continue
        if lid in deduped:
            duplicates += 1
            existing = deduped[lid]
            if lesson.transcript_status == "ok" and existing.transcript_status != "ok":
                deduped[lid] = lesson
            elif lesson.last_enriched > existing.last_enriched:
                if existing.transcript_status == "ok" and lesson.transcript_status != "ok":
                    lesson.transcript = existing.transcript
                    lesson.transcript_status = existing.transcript_status
                deduped[lid] = lesson
        else:
            deduped[lid] = lesson

    print(f"After dedup: {len(deduped)} unique lesson(s) ({duplicates} duplicate(s) collapsed)")

    if args.dry_run:
        print("[DRY RUN] Would write to SQLite. Exiting.")
        for lid, lesson in deduped.items():
            print(f"  {lid}: {lesson.title or '(untitled)'} [S:{lesson.scrape_status} T:{lesson.transcript_status}]")
        return

    sqlite_store = SQLiteStore(args.db)
    for lesson in deduped.values():
        sqlite_store.add_or_update(lesson)
    sqlite_store.save()
    sqlite_store.close()
    print(f"Migrated {len(deduped)} lesson(s) to {args.db}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _status_char(status: str) -> str:
    return {"ok": "+", "failed": "!", "unavailable": "-"}.get(status, "?")
