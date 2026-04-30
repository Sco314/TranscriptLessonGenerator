# Foundation v1 — Integration Note

**Date:** 2026-04-30
**Scope:** Foundation only. No Flask integration yet (deliberate — see "Next" below).

## What changed

This PR adds the foundation for combining the **lesson library** (already in
this repo) with the **activity-sheet production system** (previously living
only in chat conversations and a Node.js template) into one workflow.

### New top-level folders

```
lesson_builder/          # Python port of student-activity-template.js
skills/                  # Per-content-type skill files
  general-employability/
  instrumentation-activity-sheet/
  _briefings/
.claude/design/          # Claude Design integration files
archive/                 # Node template + original briefing, kept for reference
examples/                # Rendered worksheet samples
tests/                   # Smoke test for lesson_builder
```

### Changed files

- `requirements.txt` — added `python-docx>=1.0.0`
- `README.md` — replaced with new top-level README describing the combined
  architecture
- `README.legacy.md` — *(create from old `README.md` if you want to preserve
  the Apps Script docs; not done in this PR to keep the diff small)*

### Files preserved unchanged

- `ted_lessons/` — entire package untouched
- `web/` — entire app untouched
- `data/` — untouched
- `scripts/` — untouched
- `PLAN.md`, `CLAUDE.md` — untouched (update in a future PR with the new
  scope)

## Why nothing in `web/` changed

You picked option 2 (foundation only) so I deliberately stopped before
wiring the Python builder into Flask. The next PR adds:

1. A `/activities` route with skill picker + briefing form
2. A "Generate Activity Sheet" button on the existing `/lesson/<id>` page
3. PDF chapter upload + parsing
4. A per-skill prompt or simple form that turns briefing input into builder
   calls

The reason for the split: the Flask integration has design decisions in it
(how to handle long-running .docx generation, where to put the file output,
whether to render previews) that benefit from looking at the foundation
first.

## How to verify the port works

```bash
cd /path/to/repo
pip install -r requirements.txt
python tests/smoke_test.py
# expect: ✅ Document saved: tests/smoke_test.docx
```

Open `tests/smoke_test.docx` in Word or Google Docs. It should be 2 pages
with:

- Teal title "Customer Service Excellence"
- Running header "Smoke Test Worksheet | Page X of Y"
- STAR framework intro box (light teal background, colored letter labels)
- Two numbered questions with hidden timestamps (select page text to see them)
- A scaffolded prompt with a write-on line
- Tip + connection callout boxes
- Page 2: candidates list, evaluation table with alternating Q1/Q2 banners,
  question header banner, warning box, job selection line, scaffolded prompt,
  self-check box

A pre-rendered version of this exact worksheet is in
[`examples/sample-follow-along.docx`](examples/sample-follow-along.docx)
with PDF page rasters alongside it.

## Backward compatibility

- The Node template at `archive/student-activity-template_Rev02112026_0357PM.js`
  still works. Any existing scripts that `require()` it are unaffected.
- The old `VIDEO_BRIEFING_TEMPLATE.md` is preserved in `archive/` (the new
  canonical version is in `skills/_briefings/video_briefing.md`).
- `ted_lessons/` and `web/` are unchanged — the lesson library still works
  exactly as before.

## Conventions used in new code

Per the user's coding preferences:

- 2-space indent (Python uses 4 by language convention; JSON/YAML uses 2)
- ✅/❌ prefixes in console output (`save_document`, `set_theme`)
- Version headers and CHANGELOG comments at the top of `lesson_builder/__init__.py`
- Diagnostic visibility — no silent failures in `save_document` (file lock,
  filesystem, and unknown errors all reported with next-step hints)
- Backward-compatible — existing repo functionality unchanged

## Files you should review first

1. [`lesson_builder/README.md`](lesson_builder/README.md) — API surface and
   port-vs-Node naming map
2. [`skills/general-employability/SKILL.md`](skills/general-employability/SKILL.md) —
   captures the worksheet patterns from project memory
3. [`.claude/design/BRAND.md`](.claude/design/BRAND.md) — what Claude Design
   will read about the visual identity
4. [`README.md`](README.md) — top-level orientation for any new contributor
   (or for Claude Code when you ask it to do something here)

## Next iteration (when you're ready)

Pick any or all:

- **Flask integration** — `/activities` route + lesson-page button +
  `lesson_builder` ↔ Flask wiring
- **PDF chapter parsing** — for the instrumentation skill path; uses pdf-reading
- **Brief-to-build agent** — a function that takes a filled-out briefing and
  produces the full worksheet builder script
- **More themes / a navy-gold soft-skills variant** — minor; just add to
  `THEMES` in `constants.py` and mirror in `design-system.json`
- **CI smoke test** — GitHub Actions runs `tests/smoke_test.py` on every push
- **Auto-sync `design-system.json` from `constants.py`** — so the design
  tokens can never drift from the Python source of truth

## How to commit this

You have two paths:

**Manual:**
1. Download the files from this conversation
2. `cd /path/to/TranscriptLessonGenerator`
3. Move/extract the new files into place (folder structure matches exactly)
4. `git add lesson_builder/ skills/ .claude/ archive/ examples/ tests/ README.md requirements.txt INTEGRATION_NOTE_v1.md`
5. `git commit -m "Add lesson_builder Python port, skills foundation, and Claude Design files"`
6. `git push origin main` (per `CLAUDE.md` — always push to main)

**Automated with Claude Code:**
1. In the repo terminal: `claude`
2. Tell it: "Implement what's described in INTEGRATION_NOTE_v1.md from chat
   [paste this conversation or reference the file structure]. Commit and
   push to main per CLAUDE.md."
3. Claude Code creates the files and pushes directly.
