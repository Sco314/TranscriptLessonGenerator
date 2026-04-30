# lesson_builder

Python port of [`student-activity-template_Rev02112026_0357PM.js`](../archive/student-activity-template_Rev02112026_0357PM.js)
(Node v1.1) — generates printable student activity sheets as `.docx` files.

This is the document-generation engine. It does not know about TED-Ed, YouTube,
PDFs, or skills. Higher-level code (a Flask route, a CLI, a skill) decides
*what* worksheet to build and calls these helpers in sequence.

## Why a port instead of shelling out to Node

The Flask app is Python. Shelling out to Node from a Flask route adds a
runtime dependency, two serialization boundaries (Python → JSON → JS → Word),
and an error surface that's painful to debug. A native Python builder is
boring infrastructure that just works.

The trade: the Node template still exists for any standalone document-
production work outside the web app. Both runtimes share the same constants,
naming, and visual output, so a worksheet built by either looks identical.

## API overview

```python
from lesson_builder import (
    set_theme, create_document, save_document,
    title, subtitle, video_link, name_date_line, job_selection_line,
    section_header, para, para_multi, fill_line, page_break,
    numbered_question, scaffolded_prompt,
    info_box, question_header, self_check_box, tip_box, warning_box,
    connection_box, candidates_list, evaluation_table,
)

set_theme("teal")
doc = create_document(use_header=True, header_name="Customer Service")

title(doc, "Customer Service Excellence")
subtitle(doc, "Indeed Career Tips Series")
video_link(doc, "https://youtu.be/EXAMPLE")
name_date_line(doc)

numbered_question(doc, 1, [
    {"text": "The video says to listen for the "},
    {"text": "real problem", "bold": True, "color": "C62828"},
    {"text": ", not just the "},
    {"blank": 18},
    {"text": "."},
], timestamp="0:42")

save_document(doc, "customer_service.docx")
```

## Naming map: Node → Python

| Node helper | Python helper | Notes |
|---|---|---|
| `setTheme(name)` | `set_theme(name)` | Same preset names + `navy` added |
| `title(text)` | `title(doc, text)` | All builders take `doc` first |
| `nameDateLine()` | `name_date_line(doc)` | |
| `numberedQuestion(num, runs, opts)` | `numbered_question(doc, num, runs, **opts)` | Same run vocabulary: `{text, bold, italic, color}`, `{blank: int}`, `{break: True}` |
| `scaffoldedPrompt(label, hint, opts)` | `scaffolded_prompt(doc, label, hint, **opts)` | Returned array in Node; appends in Python |
| `evaluationTable({candidates, criteria, questions})` | `evaluation_table(doc, candidates=..., criteria=..., questions=...)` | |
| `createDocument(content, opts)` | `create_document(**opts)` | Append-mode — no content arg |
| `saveDocument(doc, path)` | `save_document(doc, path)` | Same `✅`/`❌` prefixes |

## API differences worth knowing

1. **Append-mode.** Node returns `Paragraph` and `Table` objects you collect
   into an array. Python helpers append to the `Document` directly. Cleaner
   for Python; minor port friction.
2. **`scaffolded_prompt` returns nothing** in Python (it appends both the
   prompt and the fill line). Node returned `[paragraph, fillLine]`.
3. **`info_box` content is a list of run-spec lists**, not a list of pre-built
   paragraphs. One nested list per paragraph. Same expressive power, simpler
   call site.

## Component visual vocabulary

| Component | What it does | When to use |
|---|---|---|
| `title` / `subtitle` | Centered headers at the top of page 1 | Always |
| `video_link` | Centered "Video: <url>" line | Video-based lessons |
| `name_date_line` | "Name: ____ Date: ____" | Always — top of page 1 |
| `section_header` | Bold colored heading | Sectioning a page |
| `para` / `para_multi` | Body text, optional mixed formatting | Instructions, narration |
| `numbered_question` | Tab-indented question with optional inline blanks, line breaks, hidden timestamp | Follow-along questions during video |
| `scaffolded_prompt` | Bold prompt + gray hint + write-on line | Open-ended student response |
| `fill_line` | Single horizontal write-on line | Where students write |
| `info_box` | Shaded box with title + content paragraphs | Framework intros (STAR, CARL, etc.) |
| `question_header` | Colored full-width banner | Big question prompts |
| `tip_box` / `warning_box` / `connection_box` | Small icon callouts | Heads-ups, ties to prior lessons |
| `self_check_box` | Title + checkbox list | End of back page — student verifies they did the work |
| `candidates_list` | "The Candidates: • A • B • C" | Interview Game format |
| `evaluation_table` | Multi-row scorecard with question banners | Interview Game format |
| `job_selection_line` | "I am applying for: <default> (circle) or _____" | Back page of Indeed worksheets |

## Themes

`set_theme(name)` accepts: `blue`, `purple`, `teal`, `brown`, `green`, `orange`,
`navy`. All themes use the same secondary palette (gray helpers, alternating
row gray, light-blue/light-orange question banners) — only `primary` and
`primary_light` change.

## Hidden timestamps

`numbered_question(..., timestamp="1:04")` adds white text that's invisible on
paper but visible when text is selected in Word/Google Docs. Used so an answer
key built from the same source can quickly align video moments to questions.
Same trick as the Node template.

## What's *not* ported

- The Node template's `cellMulti()` helper isn't here yet — the cases that
  used it in past worksheets all worked fine with `_add_para_to_cell` plus
  inline run building. If a worksheet pattern needs it, add it then.
- Page footers — not in the Node template either. Headers cover the page
  numbering need.

## Adding a helper

1. Add it to `components.py` (or `document.py` for page-level concerns).
2. Re-export from `__init__.py`.
3. Document it in this README's component table.
4. Add it to the Node template too if it should be available there.
5. Bump `__version__` in `__init__.py` and add a CHANGELOG line.

## Validation

The smoke test at `tests/smoke_test.py` exercises every helper. Run it after
any port change:

```bash
python tests/smoke_test.py
# verify the resulting smoke_test.docx renders correctly
```
