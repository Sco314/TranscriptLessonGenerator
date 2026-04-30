# VIDEO BRIEFING TEMPLATE
### Copy, fill in, paste into chat with transcript attached

---

```
VIDEO: [title] | [series, e.g. Indeed Career Tips, TED-Ed]
URL: [youtube link]
TRANSCRIPT: [attached / pasted below]

FORMAT: [pick one]
  - Interview Game    (candidates compete, students evaluate then answer)
  - Follow-Along      (instructional, timed fill-in then self-evaluation)
  - Hybrid            (let Claude decide based on transcript)

FRAMEWORK: [pick one or leave blank for Claude to decide]
  - STAR    (Situation, Task, Action, Result)
  - CARL    (Context, Action, Result, Learned)
  - 4Ps     (Personal, Professional, Positive, Pithy)
  - GROW    (Goal, Reality, Options, Will)
  - Custom  (describe below)
  - None    (no acronym framework)
  - Auto    (Claude picks based on content)

THEME COLOR: [pick one]
  - blue | purple | teal | brown | green | orange | navy

CANDIDATES: [if Interview Game — names from video, or "see transcript"]

CONNECTIONS: [previous lesson to reference, or "none"]
  Example: "Students already completed Conflict Resolution 3 Steps activity"

VOCAB TO DEFINE: [any terms to explain on the sheet, or "Claude decides"]
  Example: "pithy, contentious"

SPECIAL NOTES: [anything unusual — extra questions, specific focus, etc.]
  Example: "Don't use the REPS acronym, just list what to look for"
  Example: "Add a bonus question about teamwork"
  Example: "This is a shorter video, one page might be enough"
```

---

## WHAT YOU DON'T NEED TO SPECIFY (defaults handled by the skill):

- **Grade level:** 9-12th
- **Page structure:** Front = video follow-along/evaluation, Back = student practice
- **Layout:** 2 pages, front-and-back printable
- **Builder:** Uses `lesson_builder/` (Python) or `student-activity-template.js` (Node) — same visual output
- **Page headers:** Doc name + page numbers
- **Name/date line:** Always included
- **Self-check box:** Always on back page
- **Job selection line:** Always on back page (default job from video + write-in)
- **Tip/warning/connection boxes:** Added where pedagogically appropriate
- **Scaffolded prompts:** Student answers are chunked, not open-ended
- **Evaluation criteria:** Pulled from the framework (checkmarks or ratings)
- **Bonus question:** 1 added on back page appropriate for entry-level
- **Editable in Google Docs:** Always

## PROCESS (what happens after you submit):

1. **Analyze transcript** — identify questions, candidates, key moments, timestamps
2. **Propose outline** — quick summary of what will be built (you approve or tweak)
3. **Build .docx** — using `lesson_builder/` and the `general-employability` skill
4. **Deliver file** — ready to download, upload to Drive, and print

## QUICK-START EXAMPLES

### Minimal (when the video is straightforward):

```
VIDEO: Resume Writing Tips | Indeed
URL: https://youtu.be/xxxxx
TRANSCRIPT: [attached]
FORMAT: Follow-Along
THEME: orange
CONNECTIONS: none
```

### Detailed (when you have specific preferences):

```
VIDEO: First Job Interview Mistakes to AVOID | Indeed
URL: https://youtu.be/vnuefk2djjk
TRANSCRIPT: [attached]
FORMAT: Interview Game
FRAMEWORK: None (don't use REPS acronym — list criteria instead)
THEME: teal
CANDIDATES: see transcript
CONNECTIONS: Students completed Introduce Yourself (4Ps) and Customer Service (STAR)
VOCAB TO DEFINE: Claude decides
SPECIAL NOTES: Focus on mistakes — have students spot what went wrong, not just what went right. Include a "common mistakes" reference box.
```

---

## LESSON SERIES INVENTORY

This list is maintained in [`skills/_briefings/lesson_inventory.md`](lesson_inventory.md)
to keep this template short. Update the inventory file whenever a new
worksheet is added to the library.
