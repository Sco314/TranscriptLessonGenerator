# TED-Ed Master List — Transcript & Lesson Generator

A Google Sheets-powered database of TED-Ed lessons with automated metadata scraping, transcript fetching, and encoding cleanup. Built for classroom use by a Process Technology instructor at Hallsville High School, Texas.

## What This Project Does

- **Collects** TED-Ed lesson metadata (title, author, duration, views, category) from pasted collection pages
- **Scrapes** YouTube URLs, descriptions, authors, and categories from TED-Ed lesson pages
- **Fetches** full transcripts directly from YouTube (no third-party API dependency)
- **Fixes** UTF-8 encoding issues (mojibake) across all data
- **Exports** the database as CSV for version control and external tool access

The goal is a single searchable master list of TED-Ed lessons — a "mini database" that pulls from primary sources and can later support custom lesson documents, resource PDFs, and classroom materials.

## Quick Start

### 1. Install the Apps Script

1. Open your Google Sheet
2. Go to **Extensions > Apps Script**
3. Delete any existing code in `Code.gs`
4. Paste the entire contents of `TED_Ed_Master_List_Scripts_v4.gs`
5. Save (Ctrl+S)
6. The functions will appear in the Apps Script function dropdown

### 2. Import a TED-Ed Collection

1. Go to a TED-Ed collection page (e.g., "Public Speaking 101" on ed.ted.com)
2. Select all content on the page and copy it
3. Paste into a **new tab** in your Google Sheet
4. Run `importCollectionsToMaster()` from the Apps Script editor

### 3. Fill in Missing Data

1. Navigate to the master list tab (`TED-Ed Riddles Master List`)
2. Add TED Lesson URLs (ed.ted.com links) in the "TED Lesson URL" column for any rows you want to enrich
3. Run `fillMissingData()` — this will:
   - Scrape YouTube URLs, descriptions, authors, and categories from TED-Ed pages
   - Fetch full transcripts from YouTube for any row with a YouTube URL
4. Run `fixEncoding()` if you see garbled characters (curly quotes showing as `â€™`, etc.)

### 4. Optional: Timestamped Transcripts

Run `fillMissingDataWithTimestamps()` instead of `fillMissingData()` to get transcripts formatted as:
```
[0:00] Ideas change everything
[0:03] and since language lets us share our ideas
[0:06] learning how to use it well gives speakers the power
```

## Functions Reference

| Function | Purpose | Run From |
|----------|---------|----------|
| `fillMissingData()` | Fills YouTube URLs, descriptions, authors, categories, and transcripts from provided URLs | Master list tab |
| `fillMissingDataWithTimestamps()` | Same as above, but transcripts include `[M:SS]` timestamps | Master list tab |
| `importCollectionsToMaster()` | Parses collection tabs and appends new rows to master list | Any tab (targets master) |
| `fixEncoding()` | Fixes mojibake in all cells of the active sheet | Any tab |
| `exportMasterListToCSV()` | Exports master list as CSV to Google Drive | Any tab |

## Feature Status

| Feature | Status | Notes |
|---------|--------|-------|
| Collection import | Working | Parses pasted TED-Ed collection pages |
| TED-Ed page scraping (YouTube URL, description, author, category) | Working | Scrapes ed.ted.com pages |
| Transcript fetching | **Working (v5.0)** | Direct YouTube scraping, no third-party API |
| Timestamped transcripts | Working (v5.0) | `[M:SS]` format via `fillMissingDataWithTimestamps()` |
| Mojibake/encoding fix | Working | Handles 44+ character patterns |
| CSV export | Working (v5.0) | Exports to Google Drive for GitHub commits |
| Lesson resource PDF discovery | Planned | Some TED-Ed videos have downloadable PDFs |
| Dynamic column detection | Working | Headers matched by keyword, not position |

## Column Layout

| Col | Header | Source | Description |
|-----|--------|--------|-------------|
| A | Title | Collection import / manual | Primary key for dedup (case-insensitive) |
| B | TED-Ed Collection | Collection import | Which TED-Ed collection the lesson belongs to |
| C | Author | TED page scrape | Educator name (many say "TED-Ed") |
| D | Duration | Collection import | Format: `MM:SS` or `HH:MM` |
| E | Views | Collection import | View count as string |
| F | TED-Ed Category | Collection import / scrape | Topic category (e.g., "Thinking & Learning") |
| G | TED Lesson URL | Manual entry | The ed.ted.com lesson page URL (input for scraping) |
| H | YouTube URL | TED page scrape / manual | The youtube.com watch URL |
| I | Video Description | TED page scrape | Lesson description from meta tags |
| J | Tags and Notes | Auto / manual | Currently set to Category; intended for custom tags |
| K | Transcript | YouTube fetch | Full transcript text (49,000 char limit) |

## Architecture

### Dynamic Column Detection (`getColumnMap`)

All column references are resolved at runtime by scanning row 1 headers for keyword substrings. No hardcoded column letters anywhere. If columns are reordered, renamed, or new columns added, the script adapts automatically.

**Keywords:** `title`, `collection`, `author`, `duration`, `views`, `category`, `ted lesson`, `youtube`, `description`, `tags`, `transcript`

### Transcript Fetching (v5.0)

The v4.x approach used `subtitles-api.vercel.app`, a third-party free API that broke (returning HTTP 404). v5.0 replaces this with **direct YouTube page scraping** — the same approach used by the Python `youtube-transcript-api` library:

1. Fetch the YouTube watch page HTML
2. Extract `captionTracks` from the embedded `ytInitialPlayerResponse` JSON
3. Find the English caption track (prefers manual captions over auto-generated)
4. Fetch the timedtext XML from the track's `baseUrl`
5. Parse `<text>` elements to extract transcript segments with timing data

This eliminates the third-party dependency entirely. The only external calls are to `youtube.com` itself.

### Encoding Fix (`fixMojibake`)

Three-pass replacement engine handling:
- **3-byte mojibake:** Curly quotes, em/en dashes, ellipsis, bullets (UTF-8 → Windows-1252 corruption)
- **2-byte mojibake:** 34 accented Latin characters (UTF-8 → Latin-1 corruption)
- **Stray prefix bytes:** Removes leftover `\u00C2` artifacts

All patterns stored as `\u00XX` escape sequences to keep the `.gs` file 100% ASCII.

## CSV in GitHub

### Why Have a CSV?

A CSV snapshot in the repository serves as:
- **Version-controlled data** — track changes to the lesson database over time via git history
- **Machine-readable export** — other tools (Python, web apps, AI) can read it without Google Sheets API auth
- **Backup** — if the Google Sheet is accidentally modified, the CSV preserves a known-good state
- **IMPORTDATA source** — Google Sheets can import a CSV from a raw GitHub URL using `=IMPORTDATA("https://raw.githubusercontent.com/.../data/ted_ed_master_list.csv")`

### Workflow: Google Sheets → GitHub CSV

1. Run `exportMasterListToCSV()` in the Apps Script — saves CSV to Google Drive
2. Download the CSV from Drive
3. Replace `data/ted_ed_master_list.csv` in this repository
4. Commit and push

### Workflow: GitHub CSV → Google Sheets (read-only)

In any Google Sheet cell, use:
```
=IMPORTDATA("https://raw.githubusercontent.com/YOUR_USER/TranscriptLessonGenerator/main/data/ted_ed_master_list.csv")
```
This creates a live read-only view that updates when the GitHub CSV changes. Useful for sharing the data without giving edit access to the master sheet.

## Known Issues

### YouTube Consent/Cookie Walls
Some regions or IP addresses may receive a consent page instead of the actual YouTube watch page. The script sends `Accept-Language: en-US` headers to minimize this. If transcripts consistently fail, Google Apps Script may be hitting a rate limit — reduce batch sizes or add longer delays.

### Google Sheets Cell Limit
Transcripts are truncated to 49,000 characters (Google Sheets' cell limit is ~50,000). Very long videos may have truncated transcripts. Timestamped format uses more characters due to `[M:SS]` prefixes on each line.

### 6-Minute Execution Timeout
Google Apps Script has a hard 6-minute execution limit per run. With 1-second delays between fetches, `fillMissingData()` can process roughly 150-180 rows per run. For larger datasets, run multiple times — it skips rows that already have data.

## Design Principles

1. **Dynamic column detection** — Never hardcode column positions. Use `getColumnMap()` keyword matching.
2. **No URL guessing** — Only use URLs explicitly provided in the sheet.
3. **Defensive entry points** — Every function validates its sheet before proceeding.
4. **Encoding safety** — All fetched text runs through `fixMojibake()`. Source file stays 100% ASCII.
5. **Batch read/write** — Use `getValues()`/`setValues()` for bulk operations.
6. **Rate limiting** — 1-second delay between external fetches.
7. **Dedup by title** — Case-insensitive trimmed comparison.
8. **No third-party API dependencies** — v5.0 fetches transcripts directly from YouTube.

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.0 | 2026-02-26 | Initial transcript fetcher with hardcoded columns. UTF-8 mojibake issues. |
| v2.0 | 2026-02-26 | Dynamic column detection via `getColumnMap()`. Collection import. Encoding fix for transcripts. |
| v3.0 | 2026-02-26 | TED-Ed page scraping for descriptions. Encoding fix expanded to all columns. |
| v4.0 | 2026-02-26 | Unified `fillMissingData()`. Added `scrapeTedPage()` for YouTube URLs, authors, categories. Removed URL guessing. |
| v4.1 | 2026-02-26 | ASCII-safe mojibake patterns. `getColumnMap()` null safety. Sheet validation on all entry points. |
| v5.0 | 2026-02-26 | **Replaced broken `subtitles-api.vercel.app`** with direct YouTube page scraping (same approach as `youtube-transcript-api` Python library). Added `fillMissingDataWithTimestamps()` for `[M:SS]` formatted transcripts. Added `exportMasterListToCSV()` for GitHub-hosted data snapshots. |

## Files

| File | Purpose |
|------|---------|
| `TED_Ed_Master_List_Scripts_v4.gs` | Google Apps Script (v5.0) — paste into Extensions > Apps Script > Code.gs |
| `YouTubeTranscriptTEDEdDescriptionFetcher.py` | Retired Python script — reference for `youtube-transcript-api` approach |
| `TED_Ed_Master_List_Handoff_to_Claude_Code.md` | Project handoff document with full context |
| `data/ted_ed_master_list.csv` | CSV export of the master list (update via `exportMasterListToCSV()`) |

## Maintaining This README

This README must be updated whenever:
- A function is added, modified, or removed from the Apps Script
- New columns are added to the Google Sheet
- Bug fixes or new features are implemented (add to Version History with date)
- New design decisions or conventions are established
- Any new external API or dependency is introduced (document URL, response format, and failure behavior)

---

*Built for classroom use. TED-Ed content belongs to TED Conferences, LLC. This tool automates data collection for educational purposes only.*
