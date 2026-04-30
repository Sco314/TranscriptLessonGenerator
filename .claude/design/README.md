# Claude Design integration

This folder contains the design system Claude Design reads when it connects
to this repo. Per Anthropic's [Claude Design](https://www.anthropic.com)
docs: *"During onboarding, Claude builds a design system for your team by
reading your codebase and design files. Every project after that uses your
colors, typography, and components automatically."*

Files here are deliberately structured to make that build step accurate.

## What's here

| File | Purpose |
|---|---|
| `BRAND.md` | Plain-language description of the visual identity, tone, and audience |
| `design-system.json` | Machine-readable design tokens (colors, type, spacing, themes) |
| `components.md` | Component vocabulary — what each named component looks like and when it's used |
| `examples/` | *(planned)* Rendered worksheet samples so Claude Design has visual reference |

## How to keep this in sync

The Python builder at [`lesson_builder/constants.py`](../../lesson_builder/constants.py)
is the source of truth for design tokens. If you change a color or theme there,
mirror it in `design-system.json` here. A future maintenance script can
auto-generate the JSON from the constants module — for now it's by hand.

If the Node template ([`archive/student-activity-template_Rev02112026_0357PM.js`](../../archive/student-activity-template_Rev02112026_0357PM.js))
also has the same constant, update there too. The two runtimes share the
same visual output by convention, not by enforcement.

## What Claude Design will (probably) be able to do here

Based on the product description, once connected:

- **Build new designs that match the worksheet style** — landing pages,
  printable handouts, slide layouts that share the brand's color and type
- **Refine an existing worksheet's layout interactively** — drag adjustment
  knobs to tweak spacing, then ask Claude to apply across the worksheet library
- **Hand off to Claude Code** — when a design is ready, package it for
  Claude Code to implement against `lesson_builder/` directly
- **Export as DOCX/PPTX/PDF** — useful for one-off marketing or admin handouts
  that don't need to live in the worksheet pipeline

## What's still uncertain

Claude Design is new and the integration surface may evolve. The files here
are a reasonable first cut — the `design-system.json` token format follows
common design-token conventions (Style Dictionary / W3C Design Tokens
Community Group spec), and `BRAND.md` + `components.md` are plain markdown
that any LLM can consume.

If Claude Design eventually expects a different folder layout or file format,
moving these files is straightforward. The design tokens themselves don't
change.

## See also

- [`../../lesson_builder/`](../../lesson_builder/) — the Python builder these
  tokens describe
- [`../../skills/`](../../skills/) — content-type rules that constrain how
  the design tokens get used
