---
name: general-employability
description: "Create student activity sheets for high school career and workforce readiness lessons based on short-form videos (Indeed Career Tips, TED-Ed lessons, employability YouTube content) or general employability textbook chapters. Triggers include: requests for activity sheets, worksheets, or follow-along handouts for videos about interviewing, resumes, customer service, conflict resolution, goal-setting, professionalism, meetings, communication, teamwork, or any soft-skills topic. Use when the user provides a video transcript, video URL, or textbook chapter and asks for a printable student worksheet. Also triggers for the Indeed Career Tips series specifically and for any worksheet that follows the established two-page front-and-back format. Do NOT use for technical/vocational instrumentation content (use instrumentation-activity-sheet skill instead) or for teacher lesson plans, quizzes, tests, or slide decks."
---

# General Employability Activity Sheet Creator

Create student-facing activity sheets for short-form career and workforce
readiness lessons. Optimized for the Indeed Career Tips video series, TED-Ed
employability lessons, and general soft-skills content used at the 9–12 grade
level.

## What this skill produces

A printable two-page front-and-back .docx student activity sheet that:

- Front page = follow-along during video viewing (or chapter reading)
- Back page = self-reflective and applied transfer
- Uses a named pedagogical framework where one fits (STAR, CARL, Four P's,
  GROW, custom)
- Names strategies, never numbers them ("Taking a Pause" not "Strategy #1")
- Includes a self-check box and an entry-level bonus question
- Built with [`lesson_builder/`](../../lesson_builder/) — same visual style
  as every prior worksheet in the library

## When to use this skill

| Situation | Use this skill? |
|---|---|
| Indeed Career Tips video → worksheet | Yes |
| TED-Ed lesson on a soft-skill topic → worksheet | Yes |
| General employability textbook chapter → worksheet | Yes |
| Soft Skills / Career Readiness chapter → worksheet | Yes |
| Instrumentation textbook chapter → worksheet | No — use `instrumentation-activity-sheet` |
| Teacher lesson plan or pacing guide | No |
| PowerPoint deck for teacher presentation | No |
| Quiz, test, or assessment | No |

## Required inputs

The user provides the source content. Either:

- A **video** — title, URL, transcript (preferred), or a description detailed
  enough to identify questions and timestamps
- A **textbook chapter** — PDF, or the relevant pages copy-pasted

Plus optional preferences (the briefing template at
[`skills/_briefings/video_briefing.md`](../_briefings/video_briefing.md)
covers the full set; minimum is video + URL + transcript):

- **Format**: Interview Game (candidates compete, students evaluate) |
  Follow-Along (instructional, timed fill-in then self-evaluation) | Hybrid
- **Framework**: STAR | CARL | Four P's | GROW | None | Auto
- **Theme color**: blue | purple | teal | brown | green | orange | navy
- **Connections**: previous lesson(s) to reference

If the user doesn't specify, pick sensible defaults based on the content and
proceed — don't ask three questions before starting.

## Two-page structure (always)

### Page 1 — Follow-along

The order on page 1 is consistent across every worksheet:

1. **Title** (centered, theme primary color)
2. **Subtitle** (centered, italic, gray) — series name + episode #
3. **Video link** (centered) — `https://youtu.be/...`
4. **Name + Date line**
5. **Framework intro box** (`info_box`) — one of the named frameworks, or a
   custom "watch for these strategies" preview
6. **Numbered questions** (`numbered_question`) with hidden timestamps
   - Use inline blanks (`{"blank": 18}`) sparingly — 1-2 per question max
   - Use line breaks (`{"break": True}`) before any blank that would land too
     close to the right margin
   - For a longer video, keep follow-along density manageable: short prompts,
     more of them
7. **Optional**: tip / connection / warning callout near the bottom

### Page 2 — Reflection + transfer

1. **Section header** for the back page (e.g. "Apply It Yourself" or
   "Score the Candidates")
2. **For Interview Game format**: candidates list + evaluation table + a
   reflection prompt
3. **For Follow-Along format**: 2-3 scaffolded prompts asking the student to
   apply the framework to their own life
4. **Job selection line** (`job_selection_line`) — defaults to the role from
   the video, with a write-in alternative
5. **Bonus question** — one entry-level-appropriate question that goes a
   little beyond the video. Same `numbered_question` style.
6. **Self-check box** (`self_check_box`) — 4-6 specific items. Each item
   names something concrete the student should have done, not vague effort.

## Format-specific guidance

### Interview Game format

Used when the video shows candidates answering interview questions and
students are evaluating performance.

- Page 1 framework intro previews what students should listen for
- Page 1 questions are about the *interview questions* themselves, not the
  candidates' answers
- Page 2 has the `evaluation_table` with all candidates × all criteria
- Page 2 reflection prompt: "Who would you hire and why?" (1-2 sentences)
- Bonus question on page 2: an entry-level question the student answers themselves

### Follow-Along format

Used when the video is instructional (one presenter, multiple tips/strategies).

- Page 1 framework intro = the named strategies being taught
- Page 1 questions are about each strategy in turn — name the strategy in the
  question or in a `section_header` between question groups
- Page 2 prompts ask the student to apply each strategy to their own situation
- Bonus question on page 2: an entry-level transfer question

## Pedagogical principles (non-negotiable)

These come from many iterations and student feedback. Don't drop them.

1. **Name strategies, don't number them.** "Taking a Pause" — not "Strategy #1"
   or "Tip 3". Numbers don't transfer; names do.
2. **Single-page front-and-back when content allows.** Density should never
   sacrifice formatting quality. If you can't fit cleanly on two pages,
   prune content rather than letting layout suffer.
3. **Fill-in-the-blank is compact and purposeful.** Not every question needs
   a blank. Use inline blanks for vocabulary or completion; use full
   `fill_line()` for open responses.
4. **Document flow matters.** Analysis sections follow data-gathering
   sections. Hint placement is adjacent to where students need them — never
   on a different page from the prompt.
5. **Classroom rhythm: partner-share-rotate.** When the lesson plan involves
   peer interaction, the worksheet should reflect it: include partner notes
   lines and explicit rotate banners.
6. **Activity format mirrors the skill being taught.** Pedagogical structure
   isn't just organizational — the format itself is part of the lesson.

## Quality gates (run before delivering)

1. **Page count check.** Open the produced .docx (or convert to PDF). Confirm
   it's 2 pages exactly. If 3, prune. If 1, the back page is missing content.
2. **Visual layout check.** Convert to PDF and rasterize page-by-page.
   Confirm: no orphaned blanks at line ends, banners on page 2 are colored,
   numbered questions have proper hanging indent.
3. **Content fidelity check.** Every numbered question is answerable from the
   transcript or chapter. No question requires outside knowledge.
4. **Framework consistency.** If you named a framework in the intro box,
   every section header on page 1 references it.

## Build pattern

```python
from lesson_builder import (
    set_theme, create_document, save_document,
    title, subtitle, video_link, name_date_line, job_selection_line,
    section_header, para, info_box, numbered_question, scaffolded_prompt,
    self_check_box, page_break, COLOR,
)

set_theme("teal")  # match the briefing's theme choice
doc = create_document(use_header=True, header_name="<Doc Name>")

# ── Page 1 ──
title(doc, "<Lesson Title>")
subtitle(doc, "<Series — Episode #>")
video_link(doc, "<URL>")
name_date_line(doc)
info_box(doc, "<Framework Title>", [...])
section_header(doc, "<Page 1 section>")
numbered_question(doc, 1, [...], timestamp="<M:SS>")
# ... more numbered questions ...

page_break(doc)

# ── Page 2 ──
section_header(doc, "Apply It Yourself")
# ... scaffolded prompts or evaluation_table ...
job_selection_line(doc, "<default role>")
numbered_question(doc, N, [...])  # bonus
self_check_box(doc, ["...", "...", "...", "..."])

save_document(doc, "<output path>.docx")
```

## Briefing template

When the user gives you a video without filling out the briefing template,
infer the missing fields from the transcript and proceed. Don't pause to ask
unless the source itself is ambiguous.

The briefing template is at [`skills/_briefings/video_briefing.md`](../_briefings/video_briefing.md).
The full project context (existing series, completed lessons, naming
conventions) is also documented there.

## Output location

Save to `/mnt/user-data/outputs/<Lesson_Title>_Activity_Sheet.docx` so the
user can download it. Use Title_Case_With_Underscores in filenames — this
matches the rest of the worksheet library.
