# examples/

Rendered worksheet samples for Claude Design and visual reference.

This folder is empty in v1. To populate it:

1. Build a representative sample worksheet with `lesson_builder/`
2. Convert to PDF: `python /path/to/soffice.py --headless --convert-to pdf sample.docx`
3. Rasterize: `pdftoppm -jpeg -r 110 sample.pdf sample`
4. Commit `sample-1.jpg` and `sample-2.jpg` here

Suggested initial samples:

| File | What it should show |
|---|---|
| `interview-game.docx` + `.jpg` pages | Two-page Interview Game format with evaluation table |
| `follow-along.docx` + `.jpg` pages | Two-page Follow-Along format with framework intro |
| `instrumentation-packet.docx` + `.jpg` pages | Multi-section instrumentation activity packet |

Why this matters for Claude Design: per the product description, *"You can
also use the web capture tool to grab elements directly from your website
so prototypes look like the real product."* For this project, the equivalent
is making sure Claude Design can see what a real worksheet actually looks
like, not just read the design tokens.
