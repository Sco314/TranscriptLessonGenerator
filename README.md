# TranscriptLessonGenerator

A teacher's toolkit that turns video transcripts and PDF chapters into printable
student activity sheets, lesson docs, and a searchable lesson library.

Two content paths feed one library:

| Source | Path | Output |
|---|---|---|
| TED-Ed lesson, YouTube video | scrape → enrich → store | searchable lesson + transcript |
| PDF textbook chapter, custom briefing | parse → skill-driven build | printable .docx activity sheet |

The Flask web app at [`web/`](web/) is the front door. The Python package at
[`ted_lessons/`](ted_lessons/) handles scraping and storage. The Python package
at [`lesson_builder/`](lesson_builder/) handles document generation. Skills at
[`skills/`](skills/) tell the builder *what kind* of worksheet to make for a
given source.

## Repo layout

```
TranscriptLessonGenerator/
├── ted_lessons/            # Scrape, enrich, store TED-Ed + YouTube lessons
├── lesson_builder/         # Generate .docx activity sheets (Python port of
│                           # student-activity-template.js)
├── skills/                 # Per-content-type skill files. Each skill encodes
│   ├── general-employability/   # the rules for a worksheet "shape".
│   ├── instrumentation-activity-sheet/
│   └── _briefings/         # Reusable briefing templates (video, chapter, etc.)
├── web/                    # Flask app — browse, submit, generate
├── data/                   # CSV + SQLite lesson database (gitignored .db)
├── scripts/                # Maintenance scripts (CSV→SQLite migration, etc.)
├── examples/               # Rendered worksheet samples for Claude Design
├── .claude/                # Claude Design integration
│   └── design/             # Brand, design system, component vocabulary
└── archive/                # Retired tools kept for reference (Apps Script, etc.)
```

## Two installation paths

**Just running the lesson library:**

```bash
pip install -r requirements.txt
python -m ted_lessons add https://ed.ted.com/lessons/the-prison-break-riddle
python web/app.py
```

**Building activity sheets locally:**

```bash
pip install -r requirements.txt
python -c "
from lesson_builder import set_theme, create_document, save_document, title, name_date_line
set_theme('teal')
doc = create_document(use_header=True, header_name='Quick Test')
title(doc, 'Hello, Worksheet')
name_date_line(doc)
save_document(doc, 'test.docx')
"
```

## Foundation status

| Piece | Status |
|---|---|
| `ted_lessons/` — scrape + store | Working |
| `web/` — browse + submit | Working |
| `lesson_builder/` — Python port of Node template | **New (this PR)** — passing smoke test, not yet wired into Flask |
| `skills/` — content-type rules | **New (this PR)** — instrumentation + employability |
| `.claude/design/` — Claude Design hooks | **New (this PR)** — brand + design system |
| Flask `/activities` builder | Planned (next iteration) |
| Lesson-page "Generate Worksheet" button | Planned (next iteration) |

## Working with Claude Design

This repo is set up so [Claude Design](https://www.anthropic.com) can read your
visual conventions when you connect it. See [`.claude/design/README.md`](.claude/design/README.md)
for what Claude Design will look at and how to keep the design system in sync
with the actual generated documents.

## See also

- [`PLAN.md`](PLAN.md) — phased implementation plan
- [`CLAUDE.md`](CLAUDE.md) — repo-specific notes for Claude Code
- [`lesson_builder/README.md`](lesson_builder/README.md) — full builder API
- [`skills/README.md`](skills/README.md) — how skills work and how to add one
- [`README.legacy.md`](README.legacy.md) — original Apps Script README, retained
  for the Google Sheets workflow
