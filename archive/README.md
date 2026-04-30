# archive/

Files preserved for reference but **no longer the active source of truth**.

| File | Replaced by | Why kept |
|---|---|---|
| `student-activity-template_Rev02112026_0357PM.js` (Node v1.1) | [`lesson_builder/`](../lesson_builder/) (Python port) | Standalone Node-based worksheet production still works; useful for one-off builds outside the web app |
| `student-activity-template.js` (Node v1.0) | `student-activity-template_Rev02112026_0357PM.js` | Original; pre-`numberedQuestion()` helper |
| `VIDEO_BRIEFING_TEMPLATE.md` | [`skills/_briefings/video_briefing.md`](../skills/_briefings/video_briefing.md) | Original location; preserved so any links still work |

## When to use the archived Node template instead of `lesson_builder/`

- You're building a worksheet **outside the Flask app** (e.g. a one-off
  classroom prep session in a shell)
- You're already in a Node environment for some other reason
- You're producing a worksheet style that hasn't been ported yet (none today,
  but if a Node-only helper is added in the future)

## Keeping the two runtimes in sync

The Python port and the Node template share the same constants, naming, and
visual output **by convention, not by enforcement**. If you change one, mirror
the change in the other:

- Constants (colors, sizes, spacing) → both `lesson_builder/constants.py` and
  the Node template's top constants block, plus `.claude/design/design-system.json`
- New helpers → add to both, with the same name (camelCase in JS, snake_case
  in Python) and same parameter ordering
- Bug fixes → fix in both, mention both in the changelog of whichever you
  edit first

If the runtimes drift, the `.claude/design/design-system.json` file is the
arbiter — both runtimes should match it.
