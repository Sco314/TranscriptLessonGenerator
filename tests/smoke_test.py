"""Quick smoke test for the Python port. Builds a worksheet that exercises
every helper, then we'll convert to PDF and visually inspect."""

import sys
sys.path.insert(0, ".")

from lesson_builder import (
    set_theme, create_document, save_document,
    title, subtitle, video_link, name_date_line, job_selection_line,
    section_header, para, para_multi, fill_line, page_break,
    numbered_question, scaffolded_prompt,
    info_box, question_header, self_check_box, tip_box, warning_box,
    connection_box, candidates_list, evaluation_table,
    COLOR, SIZE,
)

# ─── PAGE 1: follow-along ────────────────────────────────────────────────────
set_theme("teal")
doc = create_document(use_header=True, header_name="Smoke Test Worksheet")

title(doc, "Customer Service Excellence")
subtitle(doc, "Indeed Career Tips Series — Smoke Test")
video_link(doc, "https://youtu.be/EXAMPLE")
name_date_line(doc)

# Framework intro
info_box(doc, "The STAR Framework", [
    [
        {"text": "Situation  ", "bold": True, "color": "C62828"},
        {"text": "— set the scene"},
    ],
    [
        {"text": "Task  ", "bold": True, "color": "EF6C00"},
        {"text": "— what you needed to do"},
    ],
    [
        {"text": "Action  ", "bold": True, "color": "2E7D32"},
        {"text": "— the steps you actually took"},
    ],
    [
        {"text": "Result  ", "bold": True, "color": "1565C0"},
        {"text": "— what happened"},
    ],
])

section_header(doc, "Watch For These Strategies")
para(doc, "Fill in the blanks as you watch the video.", italic=True, color=COLOR["helper_text"])

# Numbered questions with the full mixed-content vocabulary
numbered_question(doc, 1, [
    {"text": "The video says to start by listening for the "},
    {"text": "real problem", "bold": True, "color": "C62828"},
    {"text": ", not just the "},
    {"blank": 18},
    {"text": "."},
], timestamp="0:42")

numbered_question(doc, 2, [
    {"text": "Complete the strategy: \"Acknowledge first, then "},
    {"blank": 18},
    {"break": True},
    {"text": "before you propose a "},
    {"blank": 12},
    {"text": ".\""},
], timestamp="1:17")

# Scaffolded prompt
scaffolded_prompt(doc, "In your own words, what does 'service recovery' mean?",
                  "(1–2 sentences)")

# Tip + connection callouts
tip_box(doc, "Empathy doesn't mean agreement — it means you heard them.")
connection_box(doc, "This connects to the conflict resolution lesson — same listen-first rhythm.")

# ─── PAGE 2: evaluation ─────────────────────────────────────────────────────
page_break(doc)

section_header(doc, "Score the Candidates")
candidates_list(doc, ["Trevor", "Kimberly", "Wayne"], "Customer Service Rep")

evaluation_table(doc,
    candidates=["Trevor", "Kimberly", "Wayne"],
    criteria=["Listened?", "Acknowledged?", "Solution?"],
    questions=[
        {"text": "Tell me about a time you handled an angry customer.", "timestamp": "2:30"},
        {"text": "What does great service mean to you?", "timestamp": "4:15"},
    ],
)

# Question header + warning
question_header(doc, "Reflection: Which candidate would you hire?", timestamp="end")
warning_box(doc, "Be honest in your scoring — this isn't about who you'd be friends with.")

# Job selection + self check + bonus
section_header(doc, "Apply It Yourself")
job_selection_line(doc, "Customer Service Rep")

scaffolded_prompt(doc, "Describe a time YOU handled a frustrated person:",
                  "(STAR format — Situation, Task, Action, Result)")

self_check_box(doc, [
    "I named the strategies (not just numbered them)",
    "I scored every candidate on every criterion",
    "I wrote my own STAR example on the back",
    "My Notes column says WHY, not just a score",
])

# ─── Save ────────────────────────────────────────────────────────────────────
ok = save_document(doc, "tests/smoke_test.docx")
sys.exit(0 if ok else 1)
