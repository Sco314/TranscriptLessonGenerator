#!/usr/bin/env python3
# ============================================================================
# YouTube Transcript + TED-Ed Description Fetcher
# ============================================================================
# Reads a CSV (exported from Google Sheets), does two things:
#   1. Fetches YouTube transcripts from URLs in column G → writes to column J
#   2. Scrapes TED-Ed lesson descriptions from URLs in column F → writes to column H
#
# Column layout (0-indexed):
#   A=0 Title | B=1 Author | C=2 Duration | D=3 Views | E=4 TED-Ed Category
#   F=5 TED Lesson URL | G=6 YouTube URL | H=7 Video Description
#   I=8 Notes | J=9 Transcript
#
# Requirements:
#   python -m pip install youtube-transcript-api beautifulsoup4
#
# Usage:
#   python youtube_transcript_fetcher.py input.csv
#   python youtube_transcript_fetcher.py input.csv --output updated.csv
#   python youtube_transcript_fetcher.py input.csv --timestamps
#   python youtube_transcript_fetcher.py input.csv --only transcripts
#   python youtube_transcript_fetcher.py input.csv --only descriptions
# ============================================================================

import csv
import re
import sys
import argparse
import time

# --- YouTube transcript API ---
try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    print("❌ Missing dependency: youtube-transcript-api")
    print("   Install with: python -m pip install youtube-transcript-api")
    sys.exit(1)

# --- Web scraping for TED-Ed ---
try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("❌ Missing dependency: beautifulsoup4")
    print("   Install with: python -m pip install beautifulsoup4")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Column Configuration
# ---------------------------------------------------------------------------
COL_TED_URL = 5        # Column F: TED Lesson URL
COL_YOUTUBE_URL = 6    # Column G: YouTube URL
COL_DESCRIPTION = 7    # Column H: Video Description
COL_TRANSCRIPT = 9     # Column J: Transcript


# ---------------------------------------------------------------------------
# YouTube Transcript Helpers
# ---------------------------------------------------------------------------

def extract_video_id(url):
    """Extract YouTube video ID from various URL formats."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def fetch_transcript(video_id, include_timestamps=False):
    """Fetch transcript using youtube-transcript-api v1.2+."""
    try:
        ytt = YouTubeTranscriptApi()
        transcript = ytt.fetch(video_id)

        lines = []
        for snippet in transcript:
            text = snippet.text.strip()
            if not text:
                continue
            if include_timestamps:
                start = snippet.start
                minutes = int(start // 60)
                seconds = int(start % 60)
                lines.append(f"[{minutes}:{seconds:02d}] {text}")
            else:
                lines.append(text)

        return " ".join(lines) if not include_timestamps else "\n".join(lines)

    except Exception as e:
        error_msg = str(e)
        if "disabled" in error_msg.lower():
            return "[ERROR: Transcripts disabled for this video]"
        elif "no transcript" in error_msg.lower() or "not found" in error_msg.lower():
            return "[ERROR: No transcript available for this video]"
        else:
            return f"[ERROR: {error_msg}]"


# ---------------------------------------------------------------------------
# TED-Ed Description Helpers
# ---------------------------------------------------------------------------

# Reusable session for TED-Ed requests (faster for multiple pages)
_ted_session = None

def get_ted_session():
    """Create a reusable requests session with browser-like headers."""
    global _ted_session
    if _ted_session is None:
        _ted_session = requests.Session()
        _ted_session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })
    return _ted_session


def fetch_ted_description(url):
    """
    Scrape the lesson description from a TED-Ed lesson page.
    
    Tries multiple strategies:
      1. <meta name="description"> tag
      2. <meta property="og:description"> tag
      3. Look for lesson description in page body divs
    """
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url.startswith("http"):
        return None

    try:
        session = get_ted_session()
        response = session.get(url, timeout=15)
        response.raise_for_status()
        # Force UTF-8 encoding to prevent curly quote mangling (â€™ etc.)
        response.encoding = "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")

        description = None

        # Strategy 1: meta description tag
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            description = meta_desc["content"].strip()

        # Strategy 2: OpenGraph description
        if not description:
            og_desc = soup.find("meta", attrs={"property": "og:description"})
            if og_desc and og_desc.get("content"):
                description = og_desc["content"].strip()

        # Strategy 3: Look for lesson description in page body
        if not description:
            for selector in [".lesson-description", ".talk-description", "[data-testid='description']"]:
                elem = soup.select_one(selector)
                if elem:
                    description = elem.get_text(strip=True)
                    break

        # Clean up the description
        if description:
            # Collapse multiple spaces/newlines
            description = re.sub(r"\s+", " ", description).strip()
            # Fix any remaining encoding artifacts
            replacements = {
                "\u2018": "'", "\u2019": "'",   # curly single quotes → straight
                "\u201c": '"', "\u201d": '"',   # curly double quotes → straight
                "\u2013": "-", "\u2014": "-",   # en/em dashes → hyphen
                "\u2026": "...",                 # ellipsis character → three dots
                "\u00a0": " ",                   # non-breaking space → space
                "\u200b": "",                    # zero-width space → remove
            }
            for old, new in replacements.items():
                description = description.replace(old, new)

        return description if description else "[ERROR: No description found on page]"

    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return "[ERROR: TED-Ed page not found (404)]"
        return f"[ERROR: HTTP {e.response.status_code if e.response else 'unknown'}]"
    except requests.exceptions.ConnectionError:
        return "[ERROR: Could not connect to TED-Ed]"
    except requests.exceptions.Timeout:
        return "[ERROR: TED-Ed page timed out]"
    except Exception as e:
        return f"[ERROR: {str(e)}]"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fetch YouTube transcripts and TED-Ed descriptions into a CSV spreadsheet."
    )
    parser.add_argument("input_csv", help="Path to the input CSV file (Google Sheets export)")
    parser.add_argument("--output", "-o", default=None,
                        help="Output CSV path (default: input_with_data.csv)")
    parser.add_argument("--timestamps", "-t", action="store_true",
                        help="Include timestamps in transcript text")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Seconds to wait between API calls (default: 1.0)")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip rows that already have data in the target column")
    parser.add_argument("--only", choices=["transcripts", "descriptions"],
                        default=None,
                        help="Only fetch transcripts OR descriptions (default: both)")
    args = parser.parse_args()

    do_transcripts = args.only in (None, "transcripts")
    do_descriptions = args.only in (None, "descriptions")

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        base = args.input_csv.rsplit(".", 1)[0]
        output_path = f"{base}_with_data.csv"

    # Read input CSV
    try:
        with open(args.input_csv, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)
    except FileNotFoundError:
        print(f"❌ File not found: {args.input_csv}")
        sys.exit(1)

    if len(rows) < 2:
        print("❌ CSV has no data rows (only header or empty)")
        sys.exit(1)

    # Ensure all rows have enough columns
    min_cols = COL_TRANSCRIPT + 1  # need at least through column J
    for row in rows:
        while len(row) < min_cols:
            row.append("")

    print(f"✅ Loaded {len(rows) - 1} data rows from {args.input_csv}")
    if do_transcripts:
        print(f"   YouTube URLs:     Column G (index {COL_YOUTUBE_URL}) → Transcript: Column J (index {COL_TRANSCRIPT})")
    if do_descriptions:
        print(f"   TED-Ed URLs:      Column F (index {COL_TED_URL}) → Description: Column H (index {COL_DESCRIPTION})")
    print()

    # Counters
    transcript_ok = 0
    transcript_err = 0
    transcript_skip = 0
    desc_ok = 0
    desc_err = 0
    desc_skip = 0

    for i, row in enumerate(rows[1:], start=2):

        # --- YouTube Transcript ---
        if do_transcripts:
            yt_url = row[COL_YOUTUBE_URL].strip()
            existing_transcript = row[COL_TRANSCRIPT].strip()

            if not yt_url:
                transcript_skip += 1
            elif args.skip_existing and existing_transcript and not existing_transcript.startswith("[ERROR"):
                print(f"  ⏩ Row {i}: Transcript already exists, skipping")
                transcript_skip += 1
            else:
                video_id = extract_video_id(yt_url)
                if not video_id:
                    print(f"  ⚠️  Row {i}: Could not parse video ID from: {yt_url}")
                    row[COL_TRANSCRIPT] = "[ERROR: Invalid YouTube URL]"
                    transcript_err += 1
                else:
                    print(f"  📥 Row {i}: Fetching transcript for {video_id}...", end=" ", flush=True)
                    text = fetch_transcript(video_id, include_timestamps=args.timestamps)
                    if text.startswith("[ERROR"):
                        print(f"❌ {text}")
                        transcript_err += 1
                    else:
                        print(f"✅ ({len(text)} chars)")
                        transcript_ok += 1
                    row[COL_TRANSCRIPT] = text
                    time.sleep(args.delay)

        # --- TED-Ed Description ---
        if do_descriptions:
            ted_url = row[COL_TED_URL].strip()
            existing_desc = row[COL_DESCRIPTION].strip()

            if not ted_url:
                desc_skip += 1
            elif args.skip_existing and existing_desc and not existing_desc.startswith("[ERROR"):
                print(f"  ⏩ Row {i}: Description already exists, skipping")
                desc_skip += 1
            else:
                print(f"  🌐 Row {i}: Fetching TED-Ed description...", end=" ", flush=True)
                desc = fetch_ted_description(ted_url)
                if desc and desc.startswith("[ERROR"):
                    print(f"❌ {desc}")
                    desc_err += 1
                elif desc:
                    print(f"✅ ({len(desc)} chars)")
                    desc_ok += 1
                else:
                    print("❌ No description returned")
                    desc = "[ERROR: No description found]"
                    desc_err += 1
                row[COL_DESCRIPTION] = desc
                time.sleep(args.delay)

    # Write output CSV
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)

    print()
    print(f"{'=' * 55}")
    print(f"✅ Done! Results saved to: {output_path}")
    if do_transcripts:
        print(f"   Transcripts fetched:  {transcript_ok}")
        print(f"   Transcripts skipped:  {transcript_skip}")
        print(f"   Transcript errors:    {transcript_err}")
    if do_descriptions:
        print(f"   Descriptions fetched: {desc_ok}")
        print(f"   Descriptions skipped: {desc_skip}")
        print(f"   Description errors:   {desc_err}")
    print()
    print("Next steps:")
    print("  1. Open Google Sheets → File → Import → Upload the output CSV")
    print("  2. Choose 'Replace spreadsheet' or 'Insert new sheet'")
    if do_transcripts:
        print("  3. Transcripts will be in column J")
    if do_descriptions:
        print(f"  {'3' if not do_transcripts else '4'}. Descriptions will be in column H")


if __name__ == "__main__":
    main()