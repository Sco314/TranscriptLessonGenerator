"""Migrate existing local SQLite Lesson rows -> Supabase source_content.

Idempotent: dedup happens on (source_type, source_url) — running this twice
inserts each row exactly once.

Usage:
    # Inspect what would happen:
    python scripts/migrate_to_supabase.py --dry-run

    # Actually migrate:
    SUPABASE_DB_URL=postgres://... python scripts/migrate_to_supabase.py

    # Or specify the source SQLite file explicitly:
    python scripts/migrate_to_supabase.py --sqlite data/lessons.db
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ted_lessons.models import SourceContent  # noqa: E402
from ted_lessons.store import SQLiteStore, DEFAULT_SQLITE_PATH  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't write anything, just print what would happen.")
    parser.add_argument("--sqlite", default=str(DEFAULT_SQLITE_PATH),
                        help="Path to source SQLite database.")
    parser.add_argument("--db-url", default=os.environ.get("SUPABASE_DB_URL", ""),
                        help="Supabase Postgres connection URL "
                             "(falls back to $SUPABASE_DB_URL).")
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite)
    if not sqlite_path.exists():
        print(f"[migrate] no source SQLite at {sqlite_path}; nothing to do.")
        return 0

    sqlite_store = SQLiteStore(sqlite_path)
    lessons = sqlite_store.all_lessons()
    print(f"[migrate] found {len(lessons)} Lesson rows in {sqlite_path}.")

    if args.dry_run:
        for ls in lessons[:10]:
            src = SourceContent.from_lesson(ls)
            print(f"  - {src.source_type:11s} {src.source_url or '(no url)':70s} "
                  f"transcript={src.transcript_status or '-'}")
        if len(lessons) > 10:
            print(f"  ... and {len(lessons) - 10} more")
        print("[migrate] dry-run complete; no rows written.")
        sqlite_store.close()
        return 0

    if not args.db_url:
        print("[migrate] error: SUPABASE_DB_URL not set and --db-url not given.",
              file=sys.stderr)
        sqlite_store.close()
        return 2

    from ted_lessons.postgres_store import PostgresStore
    pg = PostgresStore(args.db_url)

    inserted = 0
    updated = 0
    skipped = 0
    failed = 0
    for ls in lessons:
        try:
            src = SourceContent.from_lesson(ls)
            if not src.source_url:
                # Without a URL we can't dedup safely. Insert as-is using id.
                pg.upsert_source(src)
                inserted += 1
                continue
            _, was_new = pg.add_or_update_source(src)
            if was_new:
                inserted += 1
            else:
                updated += 1
        except Exception as e:
            failed += 1
            print(f"  ! failed: {ls.lesson_id}: {type(e).__name__}: {e}",
                  file=sys.stderr)

    print(f"[migrate] inserted={inserted} updated={updated} "
          f"skipped={skipped} failed={failed}")
    sqlite_store.close()
    pg.close()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
