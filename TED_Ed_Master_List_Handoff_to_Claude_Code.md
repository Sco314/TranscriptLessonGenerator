# TED-Ed Master List — Claude Code Handoff

## Project Overview

Scott (Process Technology instructor, Hallsville High School, Texas) is building a curated master list of TED-Ed lessons in Google Sheets. The goal is a single searchable database with lesson metadata, URLs, descriptions, and full transcripts — primarily for TED-Ed riddles and educational video collections used in classroom instruction.

The project includes a Google Apps Script (v4.1) that automates data import, web scraping, transcript fetching, and encoding cleanup — all running inside Google Sheets with no external tools required.

A retired Python script (`YouTubeTranscriptTEDEdDescriptionFetcher.py`) previously handled transcript fetching and description scraping via CLI/CSV workflow. The Apps Script replaced the Python for description scraping, but the Python script's transcript approach (`youtube-transcript-api` library) was more reliable than the Apps Script's current third-party API, which is now returning 404 errors.

---

## Google Sheet

**URL:** https://docs.google.com/spreadsheets/d/1E8DnEx0Sq42ixVZJz6r2syKDEl-_wbOyg9bd7eZJofo/edit

### Master List Tab: `TED-Ed Riddles Master List`

**Current header row (columns A-K):**

| Col | Header | Source | Notes |
|-----|--------|--------|-------|
| A | Title | Collection import or manual | Primary key for dedup (case-insensitive). Example: `"What happens when you share an idea?"` |
| B | TED-Ed Collection | Collection import | The TED-Ed collection name the lesson belongs to. Example: `"Public Speaking 101"`, `"Superhero Science"`. Blank for lessons not part of a collection. |
| C | Author | TED page scrape | Scraped from the TED-Ed lesson page: first tries `<meta name="author">` tag, falls back to parsing the `og:title` meta tag (splits on `" - "` and takes the last segment, filtering out strings containing "TED-Ed", "Lesson", or "Riddle"). Example: `"TED-Ed"` (many TED-Ed lessons list "TED-Ed" as author rather than the individual educator). |
| D | Duration | Collection import | Comes into Google Sheets as a Date/Time object when pasted from TED-Ed website. The script's `formatTime()` converts it to `"MM:SS"` or `"HH:MM"` string. Example: `"05:30"` |
| E | Views | Collection import | View count parsed from collection tab text like `"280,149 Views"`. The regex `/[\d,]+\s*Views/i` finds it, then strips the " Views" suffix. Stored as string with commas. Example: `"280149"` |
| F | TED-Ed Category | Collection import or TED page scrape | The topic category assigned by TED-Ed. Example: `"Thinking & Learning"`. When imported from collection tabs, this comes from the line immediately after the Duration in the repeating block pattern. When scraped from the TED page, it's extracted from a JSON `"category"` field in the page source. |
| G | TED Lesson URL | Manual entry (required for scraping) | The ed.ted.com lesson page URL. This is the primary input that enables scraping of YouTube URL, description, and author. Example: `"https://ed.ted.com/lessons/what-happens-when-you-share-an-idea?lesson_collection=public-speaking-101"`. The `?lesson_collection=` parameter is optional and does not affect scraping. |
| H | YouTube URL | TED page scrape or manual | The youtube.com watch URL. Scraped from the TED-Ed page by searching the HTML for YouTube embed patterns (see scrapeTedPage section below). If provided manually, enables transcript fetching even without a TED Lesson URL. Example: `"https://www.youtube.com/watch?v=Z7bfPaTfU0c"` |
| I | Video Description | TED page scrape | The lesson description scraped from the TED-Ed page's `<meta name="description">` tag, falling back to `<meta property="og:description">`, then reversed attribute order `<meta content="..." name="description">`. HTML entities are decoded and mojibake is fixed before writing. Example: `"This is episode 1 of the animated series, "Public Speaking 101." Ideas change everything — and since language lets us share our ideas, learning how to use it well gives speakers the power to inspire people and even change how they think."` |
| J | Tags and Notes | Collection import (fallback) | Currently auto-populated with the same value as Category during collection import. Intended for manual tagging and notes later. |
| K | Transcript | YouTube transcript API | Full transcript text joined with spaces, no timestamps. Subject to Google Sheets' ~49,000 character cell limit (the script truncates with `.substring(0, 49000)`). Currently broken — see Known Issues section. |

**Important: Additional columns may be added over time** (e.g., "Resources/Lesson PDF" is planned — see below). The script's `getColumnMap()` system and `fixEncoding()` both handle new columns automatically. Any new column just needs a recognizable header keyword. When adding features that introduce new columns, follow the existing pattern: add the keyword to the `getColumnMap()` call's keyword array, and populate the column using `cols["keyword"]` indexing.

### Collection Tabs (Source Data)

These are created by copying content from the TED-Ed website's collection pages and pasting into a new Google Sheets tab. The paste brings in a specific structure in column A that the script parses.

**How the script identifies a collection tab** (all three must match):
- Cell A1 exactly equals `"TED-Ed Collections"` (this is the page header from TED-Ed's website)
- Cell A3 exactly equals `"Collection"` (this is a label)
- Cell A4 contains the collection name (e.g., `"Public Speaking 101"`)

**Data pattern in column A (repeating blocks starting at approximately row 7):**
```
Row N:   [Date/Time value] → Duration (e.g., 05:30 — Sheets interprets this as a time)
Row N+1: [String]          → Category (e.g., "Thinking & Learning")
Row N+2: [String]          → Lesson Title (e.g., "What happens when you share an idea?")
Row N+3: [blank or "Lesson duration"] → skipped
Row N+4: [String matching /\d+,?\d* Views/] → Views count (e.g., "280,149 Views")
```

The parser starts at index 6 (row 7) and advances in blocks of 5 when it finds a Date object, or by 1 otherwise. The Views field is found by scanning forward up to 5 rows from the Duration looking for the Views regex pattern.

**Existing collection tabs:** "Public Speaking 101", "Superhero Science" (more will be added over time).

**Non-collection tabs are safe:** The script skips any tab named "Summary", the master list tab itself, tabs with fewer than 7 rows, and any tab that doesn't match all three signature cells above. Scott uses other tabs for notes and placeholders — these are ignored.

### Example Row (Copy-Pasted from Sheet)

Here is actual data from one row in the master list (fields separated by tab):
```
Title: What happens when you share an idea?
TED-Ed Collection: Public Speaking 101
Author: TED-Ed
Duration: 05:30
Views: 280149
TED-Ed Category: Thinking & Learning
TED Lesson URL: https://ed.ted.com/lessons/what-happens-when-you-share-an-idea?lesson_collection=public-speaking-101
YouTube URL: https://www.youtube.com/watch?v=Z7bfPaTfU0c
Video Description: This is episode 1 of the animated series, "Public Speaking 101." Ideas change everything...
Tags and Notes: Thinking & Learning
Transcript: Error: HTTP 404
```

Note the transcript cell shows `Error: HTTP 404` — this is the primary bug (see Known Issues).

---

## Google Apps Script (v4.1)

**File:** `TED_Ed_Master_List_Scripts_v4.gs` (provided separately)

**Deployment location:** Google Sheets > Extensions > Apps Script. The entire file replaces the contents of `Code.gs`. Functions appear in the Apps Script editor's function dropdown and in Sheets' macro menu.

**Critical constraint:** Google Apps Script runs server-side JavaScript (V8 runtime) with no access to npm, pip, or external package managers. Only `UrlFetchApp` is available for HTTP requests. This is why the script uses a third-party transcript API rather than a library like `youtube-transcript-api`.

### Architecture

All column references are **dynamic** — `getColumnMap(sheet, keywords)` reads row 1 headers and matches keywords case-insensitively using `String.indexOf()`. No hardcoded column letters anywhere. If columns are reordered, added, or renamed, the script adapts automatically as long as the header text contains the expected keyword substring.

**Keywords currently used:** `title`, `collection`, `author`, `duration`, `views`, `category`, `ted lesson`, `youtube`, `description`, `tags`, `transcript`

**To add a new column:** Add its keyword to the keyword array in the relevant function's `getColumnMap()` call, then reference it as `cols["newkeyword"]`. The pattern is consistent across all functions.

### Functions

#### `fillMissingData()`
The primary data-population function. Operates on the **currently active sheet tab** — user must navigate to the master list tab before running. For each row starting at row 2:

1. Reads the Title cell. Skips the row if Title is empty.
2. Reads all other cells for the row (TED URL, YouTube URL, Description, Author, Category, Transcript).
3. **If a TED Lesson URL exists** (matches `^https?://`) **and any of YouTube URL, Description, Author, or Category are empty** → calls `scrapeTedPage(tedUrl)` which:
   - Fetches the HTML of the TED-Ed page using `UrlFetchApp.fetch()` with `followRedirects: true`
   - Searches for YouTube video ID using 4 regex patterns in order:
     1. `youtube.com/embed/{11-char-id}` (iframe embed)
     2. `youtube.com/watch?v={11-char-id}` (standard link)
     3. `youtu.be/{11-char-id}` (short link)
     4. `"video_id": "{11-char-id}"` (JSON data in page source)
   - Extracts description from `<meta name="description">`, then `og:description`, then reversed attribute order
   - Extracts author from `<meta name="author">`, then falls back to parsing `og:title` on `" - "` delimiter
   - Extracts category from JSON `"category": "..."` pattern in page source
   - All extracted text is run through `decodeHtmlEntities()` and `fixMojibake()` before returning
   - Waits 1 second after each page fetch (`Utilities.sleep(1000)`) to avoid overwhelming TED-Ed servers
4. **If a YouTube URL exists and Transcript is empty** → extracts video ID using `extractVideoId()`, then fetches from `https://subtitles-api.vercel.app/{videoId}`. The API returns JSON with a `transcript` array of objects, each having `.text` and `.start` fields. Currently only `.text` is used — all segments are joined with spaces into a single string. The string is run through `fixMojibake()` and truncated to 49,000 characters (Google Sheets cell limit).
5. **Never guesses or fabricates URLs.** An earlier version (v4.0) attempted to construct TED-Ed URLs from lesson titles by building URL slugs — this was removed because TED-Ed URLs are unpredictable (they often include author suffixes or variant spellings) and wrong guesses would silently write bad data.
6. Logs a summary at the end with counts of YouTube URLs found, descriptions scraped, authors found, categories found, transcripts fetched, rows skipped, and errors.

#### `importCollectionsToMaster()`
- **Hardcoded master tab name:** `"TED-Ed Riddles Master List"` — looks it up by name using `ss.getSheetByName()`. If the tab is renamed, this string must be updated.
- Scans all tabs in the spreadsheet looking for the collection signature (A1/A3/A4 pattern described above)
- Parses the repeating block pattern in column A starting at index 6
- Appends new rows to the master list tab using `masterSheet.appendRow(row)`
- **Deduplicates** by comparing lowercase trimmed Title against all existing titles in the master list. Builds a `{}` hash map on first pass, adds to it as rows are appended.
- Skips tabs named "Summary" or the master list tab itself
- **Populates these columns:** Title, Collection (from A4 of the source tab), Duration, Views, Category, Tags (set to same value as Category)
- **Leaves blank:** Author, TED Lesson URL, YouTube URL, Description, Transcript — these are filled later by `fillMissingData()` once URLs are provided

#### `fixEncoding()`
- Scans **every cell** in the active sheet (row 2 through last row, column A through last column — determined dynamically by `sheet.getLastRow()` and `sheet.getLastColumn()`)
- Does NOT use `getColumnMap()` — it's completely column-agnostic. Works on any column including future columns.
- Calls `fixMojibake()` on every string cell >= 3 characters
- `fixMojibake()` runs 3 passes:
  - **Pass 1 (3-byte mojibake):** Fixes curly quotes, em/en dashes, ellipsis, bullets. These occur when UTF-8 3-byte sequences (like `E2 80 99` for right single quote) are decoded as Windows-1252, producing `â€™`. The map has 10 patterns covering: `'` `'` `"` `"` `—` `–` `…` `•` non-breaking space, middle dot.
  - **Pass 2 (2-byte mojibake):** Fixes accented Latin characters. These occur when UTF-8 2-byte sequences (like `C3 B6` for `ö`) are decoded as Latin-1, producing `Ã¶`. The map has 34 patterns covering the full Latin-1 accented range: `á à â ã ä å æ ç è é ê ë ì í î ï ð ñ ò ó ô õ ö ø ù ú û ü ý ÿ Ö Ü Ä ß`.
  - **Pass 3:** Removes stray `Â` (U+00C2) characters that appear before non-whitespace, which are leftover prefix bytes from mojibake.
- All mojibake search patterns are stored as `\u00XX` escape sequences in the source code, making the .gs file 100% ASCII. Previous versions had raw multi-byte characters in the source which caused syntax errors in Apps Script's parser.
- **Performance:** Reads the entire data range into memory with one `getValues()` call, processes in-memory, then writes back with one `setValues()` call. Only writes if something actually changed.
- **Real-world examples of mojibake this fixes:**
  - `"thatâ€™s"` → `"that's"` (from transcript and description columns)
  - `"Dr. SchrÃ¶dinger"` → `"Dr. Schrödinger"` (from description column)
  - `"theyâ€™ve"` → `"they've"` (from transcript column)
  - `"â€"the"` → `"—the"` (em dash in descriptions)

### Shared Helpers

- **`getColumnMap(sheet, keywords)`** — Defensive: returns `{}` if `sheet` is null, or if `sheet.getLastColumn()` returns 0 (empty sheet). This was a bug fix in v4.1 — earlier versions crashed with `TypeError: Cannot read properties of undefined (reading 'getRange')` when run on an empty tab.
- **`extractVideoId(url)`** — Regex-based extraction of 11-character YouTube video IDs. Handles: `youtube.com/watch?v=`, `youtu.be/`, `youtube.com/embed/`, `youtube.com/v/`, `youtube.com/u/*/` formats, and bare 11-char IDs. Returns null if no valid ID found.
- **`fixMojibake(text)`** — 3-pass replacement engine described above. Returns original string if no mojibake found.
- **`fetchPage(url)`** — Thin wrapper around `UrlFetchApp.fetch()` with `muteHttpExceptions: true` and `followRedirects: true`. Returns UTF-8 string on HTTP 200, null on any error. Logs the error message on failure.
- **`decodeHtmlEntities(str)`** — Handles: `&amp;` `&lt;` `&gt;` `&quot;` `&#39;` `&#x27;` `&apos;` `&#8217;` `&#8216;` `&#8220;` `&#8221;` `&#8212;` `&#8211;` `&#8230;`
- **`scrapeTedPage(tedUrl)`** — Orchestrator that calls `fetchPage()`, runs 4 YouTube URL regex patterns, 3 description meta tag patterns, author extraction, and category extraction. Returns `{ youtubeUrl: string|null, description: string|null, author: string|null, category: string|null }`.
- **`formatTime(dateVal)`** — Converts Date objects (from Sheets' time interpretation) to `"HH:MM"` or `"MM:SS"` strings. Uses `pad()` for zero-padding.
- **`getString(arr, idx)`** — Safe array access that returns `""` for out-of-bounds, null, undefined, or Date values (Date values in the middle of text blocks are Duration fields from the next lesson, not string data).

---

## Known Issues & Current Bugs

### 1. PRIORITY: Transcript HTTP 404 Error
**Symptom:** Transcript column shows `Error: HTTP 404` for rows that have valid YouTube URLs. Confirmed on the "Public Speaking 101" collection — every row has a valid YouTube URL (e.g., `https://www.youtube.com/watch?v=Z7bfPaTfU0c`) but the transcript cell says `Error: HTTP 404`.

**Root cause:** The Apps Script fetches transcripts from `https://subtitles-api.vercel.app/{videoId}` — a **third-party free API** hosted on Vercel. This API is returning HTTP 404 for requests that previously worked. The API may be down, rate-limiting, or may have changed its endpoint structure. This is an external dependency with no SLA or guarantee.

**What the API returns when working:** JSON object with a `transcript` array:
```json
{
  "transcript": [
    { "text": "Ideas change everything", "start": 0.5 },
    { "text": "and since language lets us share our ideas", "start": 3.2 },
    ...
  ]
}
```
The script currently joins all `.text` values with spaces, discarding the `.start` timing data.

**What the retired Python script used instead:** The `youtube-transcript-api` Python library (pip package), which calls YouTube's internal timedtext API directly. This worked reliably. The relevant Python code:
```python
from youtube_transcript_api import YouTubeTranscriptApi
ytt = YouTubeTranscriptApi()
transcript = ytt.fetch(video_id)
# Each snippet has: snippet.text, snippet.start (seconds)
```

**Options to investigate for a fix:**
1. **Alternative free transcript APIs** — search for services similar to subtitles-api.vercel.app that expose YouTube transcripts via HTTP GET
2. **YouTube Data API v3** — official API, requires an API key (free tier: 10,000 quota units/day). The `captions` endpoint can retrieve transcripts but requires OAuth for most videos. May be too restrictive.
3. **Google Cloud Function / Apps Script Web App hybrid** — deploy a small Python Cloud Function that uses `youtube-transcript-api`, call it from Apps Script via `UrlFetchApp.fetch()`. More infrastructure but most reliable.
4. **YouTube's internal timedtext endpoint** — `https://www.youtube.com/api/timedtext?v={videoId}&lang=en` — this is what `youtube-transcript-api` uses under the hood. It may be callable directly from Apps Script, but the URL structure requires parameters extracted from the video page's player config.
5. **Scrape the YouTube watch page directly** — the transcript data is embedded in the page's initial JSON data (`ytInitialPlayerResponse`). Could be parsed with regex from Apps Script, but YouTube's page structure changes frequently.

**The Google Apps Script constraint:** Apps Script has no `pip` or `npm`. Only `UrlFetchApp` for HTTP. Any solution must ultimately be an HTTP endpoint that Apps Script can call, or must parse data from a fetchable URL.

### 2. LOW PRIORITY / OPTIONAL: Timestamp Support in Transcripts
**This is a nice-to-have, not a priority.** The primary issue (404 errors) must be fixed first.

**Context:** The transcript API response includes a `start` field (seconds from video start) for each text segment. The retired Python script supported a `--timestamps` flag that formatted transcripts as:
```
[0:00] Ideas change everything
[0:03] and since language lets us share our ideas
[0:06] learning how to use it well gives speakers the power
```
The Apps Script currently discards this timing data and joins all `.text` fields with spaces into continuous prose.

**If implemented:** Consider making it togglable — perhaps a separate function `fillMissingDataWithTimestamps()`, or a cell/named range that acts as a config flag the script checks. Timestamped transcripts are useful for finding specific moments but harder to read as continuous text. Both formats have value.

### 3. Lesson Resource PDFs (New Feature Request)
**Discovery context:** While examining the YouTube page for TED-Ed lesson `"What happens when you share an idea?"` (`https://www.youtube.com/watch?v=Z7bfPaTfU0c`), Scott found a downloadable PDF resource linked from the video. The full URL found on YouTube:

```
https://www.youtube.com/file_download?expire=19000000000&ei=b72gafrZD4ukib4P0ezP-A4&ip=0.0.0.0&v=Z7bfPaTfU0c&file_id=1KWt9g6PsVNkIJHefc5fH4cMuuNk_uLei/Public_Speaking_101_Lesson_1.pdf&fd=1&susc=yrw&xpc=EgVo2aDSNQ==&sparams=expire,ei,ip,susc,xpc&sig=AJEij0EwRAIgCy-lw7lUvKwAsXVh20Fj7N4A53i0YJXju0XfkErAUIoCIBfqKblhz-biO-oiGAyOqPBTwAEQiJ3QPpe9zqJx7hDK
```

Key observations about this URL:
- It's a `youtube.com/file_download` endpoint (YouTube's file attachment system)
- It contains the video ID: `v=Z7bfPaTfU0c`
- It contains a Google Drive file ID: `file_id=1KWt9g6PsVNkIJHefc5fH4cMuuNk_uLei`
- The filename is in the path: `Public_Speaking_101_Lesson_1.pdf`
- It has expiration/signature parameters, so the URL itself is temporary — but the file_id may be stable

**Open questions to investigate:**
1. Do most or all TED-Ed lessons have associated PDF resources? Or is this specific to certain collections?
2. Where does this link appear on the YouTube page? (Video description? A "resources" section below the video? The "more" dropdown?)
3. Is the same PDF linked from the TED-Ed lesson page (ed.ted.com)?
4. Can the Google Drive `file_id` be extracted and used to construct a permanent link like `https://drive.google.com/file/d/{file_id}/view`?
5. Is there a pattern in the YouTube video description text that contains the PDF URL or a link to it?

**Suggested investigation approach:**
1. Fetch the YouTube watch page HTML for `Z7bfPaTfU0c` and search for "pdf", "file_download", "drive.google.com", or "resource"
2. Fetch the TED-Ed lesson page HTML for the same lesson and search for similar patterns
3. Check 3-5 different TED-Ed lessons across different collections to see if the pattern is consistent
4. If PDFs are common, add a new column (e.g., "Lesson PDF" or "Resources") to the master sheet. Add `"lesson pdf"` or `"resources"` to the `getColumnMap()` keyword list and populate it during `fillMissingData()`.

---

## Retired Python Script

**File:** `YouTubeTranscriptTEDEdDescriptionFetcher.py` (provided separately)

**What it did:** A standalone CLI tool that read a CSV export of the Google Sheet, fetched data, and wrote a new CSV for re-import to Sheets.

**Two main operations:**
1. **Transcript fetching** — Used `youtube-transcript-api` library (pip package). Called `YouTubeTranscriptApi().fetch(video_id)` which returns transcript segments with `.text` and `.start` attributes. Supported `--timestamps` flag for `[M:SS] text` formatting. This approach was **more reliable** than the Apps Script's current API.
2. **Description scraping** — Used `requests` + `BeautifulSoup` to fetch TED-Ed lesson pages. Tried 3 strategies: `<meta name="description">`, `<meta property="og:description">`, and CSS selector search (`.lesson-description`, `.talk-description`, `[data-testid='description']`). Used a reusable `requests.Session` with browser-like User-Agent headers.

**Status:** The description scraping is fully replaced by the Apps Script's `scrapeTedPage()`. The transcript fetching was replaced but the replacement (`subtitles-api.vercel.app`) is now broken. The Python script's `youtube-transcript-api` approach may need to be brought back via a different mechanism (see Known Issues #1).

**CLI usage (for reference):**
```bash
python YouTubeTranscriptTEDEdDescriptionFetcher.py input.csv
python YouTubeTranscriptTEDEdDescriptionFetcher.py input.csv --timestamps
python YouTubeTranscriptTEDEdDescriptionFetcher.py input.csv --only transcripts
python YouTubeTranscriptTEDEdDescriptionFetcher.py input.csv --only descriptions
python YouTubeTranscriptTEDEdDescriptionFetcher.py input.csv --skip-existing --delay 2.0
```

**Column layout the Python script used (0-indexed, OUTDATED — sheet has been reorganized since):**
```
A=0 Title | B=1 Author | C=2 Duration | D=3 Views | E=4 TED-Ed Category
F=5 TED Lesson URL | G=6 YouTube URL | H=7 Video Description
I=8 Notes | J=9 Transcript
```
The current master sheet has "TED-Ed Collection" in column B, pushing everything else over. The Python script's hardcoded column indices would need updating if reused directly.

---

## Design Principles & Conventions

These patterns have been established through the development of v1-v4.1 and should be maintained:

1. **Dynamic column detection** — Never hardcode column letters or indices. Always use `getColumnMap()` with keyword matching. This allows Scott to reorder or insert columns without breaking the script.
2. **No URL guessing** — Only use URLs that are explicitly provided in the sheet. Constructing URLs from titles was tried (v4.0) and removed because TED-Ed URL slugs are unpredictable and wrong guesses produce bad data silently.
3. **Defensive entry points** — Every public function validates its sheet has data before proceeding. `getColumnMap()` returns `{}` on null/empty sheets rather than crashing. Error messages should name the sheet and suggest what to do.
4. **Encoding safety** — All fetched text passes through `fixMojibake()`. The .gs source file itself must be 100% ASCII — use `\u00XX` escape sequences for any non-ASCII patterns in lookup tables. Previous versions had raw multi-byte characters that caused syntax errors.
5. **Mojibake patterns in source code** — The `fixMojibake()` function's lookup arrays use Unicode escapes because the literal mojibake characters (like `â€™`) cause syntax errors in Google Apps Script when they appear in the .gs source file. The escaped versions (`\u00E2\u0080\u0099`) are byte-equivalent at runtime.
6. **Batch read/write** — Use `getValues()`/`setValues()` for bulk operations rather than cell-by-cell access. Cell-by-cell is extremely slow in Apps Script.
7. **Rate limiting** — 1-second delay between external page fetches. Google Apps Script has a 6-minute execution timeout, so be mindful of row count vs. delay.
8. **Dedup by title** — Case-insensitive trimmed comparison. The title is the only reliable unique identifier since URLs may be missing.
9. **Logger output** — Use `Logger.log()` for all diagnostic output. Keep messages plain ASCII. Include row numbers, character counts, and actionable error messages.
10. **Column flexibility** — The sheet will grow over time. New columns may be added for things like resource PDFs, lesson difficulty, or custom tags. The `getColumnMap()` + keyword system handles this — just add the keyword and reference it.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.0 | 2026-02-26 | Initial transcript fetcher with hardcoded columns G (YouTube URL) and J (Transcript). Used `response.getContentText()` which caused UTF-8 mojibake. Had duplicate `const data` declaration bug. |
| v2.0 | 2026-02-26 | Introduced `getColumnMap()` for dynamic column detection. Added `importCollectionsToMaster()` to parse collection tabs. Added `fixEncodingInTranscripts()` (transcript column only). Fixed UTF-8 encoding by switching to `response.getBlob().getDataAsString("UTF-8")`. |
| v3.0 | 2026-02-26 | Added `fetchTedEdDescriptions()` to scrape descriptions from TED-Ed pages, replacing the Python script for that function. Expanded encoding fix to scan all columns, renamed to `fixEncoding()`. |
| v4.0 | 2026-02-26 | Unified `fetchYouTubeTranscripts()` and `fetchTedEdDescriptions()` into single `fillMissingData()` function. Added `scrapeTedPage()` to extract YouTube URLs, descriptions, authors, and categories from TED-Ed pages. Initially included URL guessing from titles — removed same day due to unreliability. |
| v4.1 | 2026-02-26 | Clean rebuild. All mojibake patterns converted to `\u00XX` escape sequences (100% ASCII source file). Fixed `getColumnMap()` crash on null/empty sheets. Added sheet validation with clear error messages to all entry points. Removed all emoji from Logger output. Fixed syntax error caused by raw multi-byte characters in the .gs source. |

---

## README Development Requirement

**Action item:** Create a `README.md` file for this project that serves as living documentation. It should include:

1. **Project description** — What this project is, who it's for, what problem it solves
2. **Setup instructions** — How to install the Apps Script in Google Sheets (Extensions > Apps Script > paste Code.gs)
3. **Usage guide** — Step-by-step workflow for each function, with expected inputs and outputs
4. **Feature list** — Current capabilities with status indicators (working, broken, planned)
5. **Known issues** — Current bugs with severity/priority
6. **Changelog** — Detailed version history (can be pulled from the Version History section above)
7. **Architecture notes** — How `getColumnMap()` works, how `fixMojibake()` works, the scraping strategies
8. **Column reference** — Current sheet layout with descriptions

**The README must include a maintenance instruction block** — a visible section (e.g., `## Maintaining This README`) that states:
- This README must be updated whenever a function is added, modified, or removed
- New columns added to the sheet must be documented in the column reference
- Bug fixes and new features must be added to the changelog with date and version
- Any new design decisions or conventions should be added to the Design Principles section
- If a new external API or dependency is introduced, document it with the URL, what it returns, and what happens if it goes down

---

## Open Work / Next Steps (Priority Order)

1. **FIX: Transcript fetching** — `subtitles-api.vercel.app` returning 404. This is the highest priority because it blocks the core use case. Need a reliable alternative that works from Google Apps Script's `UrlFetchApp` (no npm/pip). See Known Issues #1 for detailed options.

2. **NEW FEATURE: Lesson resource PDF discovery** — Investigate whether TED-Ed lessons commonly have downloadable PDF resources. Use the example URL from YouTube video `Z7bfPaTfU0c` as a starting point (full URL in Known Issues #3). If common, add a column and populate it in `fillMissingData()`.

3. **OPTIONAL: Timestamp support in transcripts** — Low priority. Add ability to include `[M:SS]` timestamps in transcript text. See Known Issues #2. Only relevant once transcript fetching is fixed.

4. **ONGOING: Collection imports** — Scott will continue pasting new TED-Ed collections into new tabs. `importCollectionsToMaster()` handles this — no code changes needed unless the TED-Ed website changes its collection page format.

5. **ONGOING: Data population** — After each import, `fillMissingData()` + `fixEncoding()` complete the rows. Currently blocked on transcript fetching (item 1).

6. **DOCUMENTATION: Create README.md** — See README Development Requirement section above.

---

## Workflow Summary

```
+----------------------------------+
|  Paste TED-Ed collection         |
|  into new Google Sheet tab       |
+----------------+-----------------+
                 |
                 v
+----------------------------------+
|  importCollectionsToMaster()     |
|  Parses tab -> appends to master |
|  Fills: Title, Collection,       |
|  Duration, Views, Category, Tags |
+----------------+-----------------+
                 |
                 v
+----------------------------------+
|  Manually add TED Lesson URLs    |
|  and/or YouTube URLs             |
|  (script fills the other from    |
|  whichever you provide)          |
+----------------+-----------------+
                 |
                 v
+----------------------------------+
|  fillMissingData()               |
|  TED URL -> YouTube URL,         |
|  Description, Author, Category   |
|  YouTube URL -> Transcript       |
+----------------+-----------------+
                 |
                 v
+----------------------------------+
|  fixEncoding()                   |
|  Cleans mojibake in ALL cells    |
|  (any column, auto-expands)      |
+----------------------------------+
```

---

## Files Included in Handoff

| File | Purpose |
|------|---------|
| `TED_Ed_Master_List_Handoff_to_Claude_Code.md` | This document |
| `TED_Ed_Master_List_Scripts_v4.gs` | Current Google Apps Script (v4.1) — paste into Extensions > Apps Script > Code.gs |
| `YouTubeTranscriptTEDEdDescriptionFetcher.py` | Retired Python script — reference only, for understanding the `youtube-transcript-api` approach |
