#!/usr/bin/env python3
"""Migrate lesson data from CSV to SQLite.

Reads the CSV, computes stable lesson_ids, collapses duplicates using shared
deterministic dedup rules, and writes to SQLite.

Usage:
    python scripts/migrate_csv_to_sqlite.py
    python scripts/migrate_csv_to_sqlite.py --csv data/ted_ed_master_list.csv --db data/lessons.db
"""

import argparse
import sys
from pathlib import Path

# Add parent dir to path so we can import ted_lessons
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ted_lessons.dedup import collapse_duplicates
from ted_lessons.store import CSVStore, SQLiteStore


def migrate(csv_path: str, db_path: str, dry_run: bool = False):
    """Migrate CSV data to SQLite, collapsing duplicates."""
    csv_store = CSVStore(csv_path)
    lessons = csv_store.all_lessons()

    if not lessons:
        print("No lessons found in CSV. Nothing to migrate.")
        return

    print(f"Loaded {len(lessons)} lesson(s) from {csv_path}")

    deduped, duplicates, skipped = collapse_duplicates(lessons)
    for msg in skipped:
        print(f"  [SKIP] {msg}")
    print(f"After dedup: {len(deduped)} unique lesson(s) ({duplicates} duplicate(s) collapsed)")

    if dry_run:
        print("[DRY RUN] Would write to SQLite. Exiting.")
        for lid, lesson in deduped.items():
            print(f"  {lid}: {lesson.title or '(untitled)'} [S:{lesson.scrape_status} T:{lesson.transcript_status}]")
        return

    # Write to SQLite
    sqlite_store = SQLiteStore(db_path)
    for lesson in deduped.values():
        sqlite_store.add_or_update(lesson)
    sqlite_store.save()
    sqlite_store.close()

    print(f"Migrated {len(deduped)} lesson(s) to {db_path}")


def main():
    parser = argparse.ArgumentParser(description="Migrate CSV lesson data to SQLite")
    parser.add_argument("--csv", default="data/ted_ed_master_list.csv", help="Input CSV path")
    parser.add_argument("--db", default="data/lessons.db", help="Output SQLite path")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without writing")
    args = parser.parse_args()
    migrate(args.csv, args.db, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
