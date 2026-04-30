# skills/

Skills tell the lesson builder *what kind* of worksheet to make for a given
source. Each skill is a folder with a `SKILL.md` file containing a YAML
frontmatter block (`name`, `description`) and human-readable instructions.

This is the same skill format Anthropic uses for Claude's built-in skills, so
when you connect this repo to Claude Design or use it from a Claude conversation,
the skills here become discoverable and usable directly.

## Current skills

| Skill | When it triggers | What it produces |
|---|---|---|
| `general-employability` | Indeed videos, TED-Ed soft skills, employability chapters | Two-page front-and-back student activity sheet |
| `instrumentation-activity-sheet` | NAPTA / process control textbook chapters and slides | Multi-section student activity packet |

## Briefing templates

The `_briefings/` folder holds reusable input templates. When you ask Claude
(or a human) to build a worksheet, you fill out the relevant briefing template
first. This eliminates the need to re-explain context every time.

- [`_briefings/video_briefing.md`](_briefings/video_briefing.md) — for any
  video-based worksheet (Indeed Career Tips, TED-Ed, YouTube)
- `_briefings/chapter_briefing.md` — *planned, for textbook chapter input*

## Choosing the right skill

Use the decision flow:

```
Source type?
├── Video (Indeed, TED-Ed, YouTube)            → general-employability
├── Soft-skills textbook chapter                → general-employability
├── Instrumentation textbook chapter (NAPTA)   → instrumentation-activity-sheet
└── Other technical/vocational chapter         → instrumentation-activity-sheet
```

If a source could fit either skill (e.g., a TED-Ed video on industrial
safety), prefer `general-employability` — its two-page constraint forces
tighter content selection, which is usually what students need.

## Adding a new skill

1. Create a folder: `skills/<skill-name>/`
2. Add `SKILL.md` with the standard frontmatter:
   ```markdown
   ---
   name: skill-name
   description: "When to use this skill, what triggers it, what it does."
   ---
   ```
3. Document inputs, outputs, layout rules, and pedagogical principles
4. If a new briefing template is needed, add it under `_briefings/`
5. Update the table in this README

The skill should be self-contained — anyone reading just the `SKILL.md` file
should be able to produce a worksheet matching the established style.

## Why incompatible skills stay separate

Instrumentation worksheets and employability worksheets have different
formatting philosophies:

- Instrumentation: multi-section packets, segmented for ~30-min independent
  work, learning-objective alignment, varied Bloom's levels
- Employability: strict two-page front-and-back, named (not numbered)
  strategies, single pedagogical framework per worksheet

Merging them into one skill would require so many conditional branches that
the skill stops being useful. They share the same `lesson_builder/` engine
underneath; that's the right level of abstraction.
