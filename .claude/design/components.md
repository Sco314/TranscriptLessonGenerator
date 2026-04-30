# Component Vocabulary

These are the named components in the worksheet design system. When Claude
Design (or anyone else) builds a new artifact for this project, these are
the building blocks to reach for first. New compositions are fine; new
components should be rare.

Each component below maps to a function in
[`lesson_builder/components.py`](../../lesson_builder/components.py) and to
a corresponding helper in
[`archive/student-activity-template_Rev02112026_0357PM.js`](../../archive/student-activity-template_Rev02112026_0357PM.js).

---

## Header components

### `title`
Centered, large (17pt), bold, theme-primary color. Always at the top of
page 1. One per worksheet.

### `subtitle`
Centered, italic, gray (10pt). Sits directly under the title. Names the
series and episode. Optional but standard.

### `video_link`
Centered, gray "Video:" label + blue URL (9pt). One per worksheet, only
when the source is a video.

### `name_date_line`
Left-aligned: `Name: ____________  Date: _______`. Always present, just
under the video link.

---

## Section dividers

### `section_header`
Bold, theme-primary color (11pt). Name the section in 2-4 words. Examples:
"Watch For These Strategies", "Apply It Yourself", "Score the Candidates".

### `page_break`
Hard break between page 1 and page 2. Exactly one per worksheet.

---

## Question components

### `numbered_question`
Tab-indented question with: bold theme-colored number, question text with
optional inline blanks (`{"blank": 18}`), optional line breaks
(`{"break": True}`), optional hidden white-text timestamp. The workhorse —
most worksheets have 6-12 of these.

Hidden timestamps appear as `(M:SS)` in white text — invisible on paper but
selectable in Word, used for answer-key alignment.

### `scaffolded_prompt`
Bold theme-colored prompt + small italic gray hint + horizontal write-on
line. For open-ended student responses.

### `fill_line`
Single horizontal underline. Where students write longer responses. Multiple
in a row create lined writing space.

### `question_header`
Full-width colored banner with bold question text. For "big" prompts that
deserve visual weight — typically once on page 2.

---

## Container components

### `info_box`
Shaded box with a centered bold title and one or more content paragraphs
underneath. Used for framework intros (STAR, CARL, Four P's). Background is
the theme's `primary-light`. Title is the theme `primary`.

### `tip_box`
Light-green inset with 💡 icon + bold "Tip:" label + italic text. Inline
helper. Use sparingly — 0-2 per worksheet.

### `warning_box`
Light-red variant of `tip_box` with ⚠️ icon. Use for clear "don't do this"
moments. Use sparingly — 0-1 per worksheet.

### `connection_box`
Light-green variant with 🔗 icon. Use to tie this lesson to a previous one
the student already completed.

### `self_check_box`
Shaded box with a centered "✓ Self-Check" title and a list of ☐ checkbox
items. Always at the bottom of page 2. 4-6 items, each naming something
specific the student should have done.

---

## Specialty components (Interview Game format)

### `candidates_list`
Header line "The Candidates (All applying for [role])" + bulleted name line.
Used on page 2 of Interview Game format worksheets.

### `evaluation_table`
Multi-row evaluation table. Columns: Candidate | Criteria... | Notes. Rows
are grouped by question, with a colored banner row between question groups.
Banners alternate light-blue and light-orange.

### `job_selection_line`
Centered: `I am applying for: [default] (circle)  or  ____________
(your choice)`. Always at the top of the back-page application section.

---

## Composition rules

A standard worksheet composes these in this order:

```
Page 1:
  title
  subtitle
  video_link               (if video source)
  name_date_line
  info_box                 (framework intro, optional)
  section_header           ("Watch For These Strategies" or similar)
  numbered_question × N    (4-8 typical; with hidden timestamps)
  tip_box | connection_box (optional, near bottom)

page_break

Page 2:
  section_header           ("Apply It Yourself" or "Score the Candidates")

  [Interview Game]                  | [Follow-Along]
    candidates_list                 |   scaffolded_prompt × 2-3
    evaluation_table                |
    question_header                 |
                                    |
  job_selection_line
  numbered_question                 (bonus question, entry-level)
  self_check_box
```

## Why these specific components

Every component in this list earned its place by recurring across multiple
worksheets in the production library. Components that didn't recur (e.g., a
"matching" exercise from one early sheet) were deliberately not added to the
permanent vocabulary — the constraint forces a more cohesive student
experience across the series.

When a new pattern is needed, the rule is: build it ad-hoc twice, then
promote to a named component if it shows up a third time.
