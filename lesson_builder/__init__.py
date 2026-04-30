"""
lesson_builder — student activity sheet builder for TranscriptLessonGenerator.

Python port of student-activity-template_Rev02112026_0357PM.js (v1.1).
Same theme system, same component vocabulary, same single-page-front-and-back
layout discipline. Everything an existing Node.js worksheet relies on has a
direct counterpart here.

Top-level exports mirror the Node module so a JS-fluent reader can find their
way around quickly:

    from lesson_builder import (
        # constants
        FONT, PAGE, SIZE, SPACING, COLOR, THEMES, FRAMEWORK,
        # state
        set_theme, get_theme,
        # building blocks
        title, subtitle, video_link, name_date_line, job_selection_line,
        section_header, para, para_multi, fill_line, inline_blank, page_break,
        numbered_question, scaffolded_prompt,
        # complex components
        info_box, question_header, self_check_box, tip_box, warning_box,
        connection_box, candidates_list, evaluation_table,
        # document
        create_document, save_document,
    )

Version mapping:
    Node v1.1 (2026-02-11) → Python v1.0 (2026-04-30)

If you add a helper to the Node template, mirror it here with the same name
in snake_case. If you add one only here, document it in CHANGELOG below so
the Node side can catch up.

CHANGELOG:
    v1.0 (2026-04-30) — Initial Python port of Node v1.1
        + All core building blocks (title, subtitle, para, para_multi, etc.)
        + numbered_question with hidden white timestamps and inline blanks
        + All complex components (info_box, question_header, self_check_box,
          tip_box, warning_box, connection_box, candidates_list, evaluation_table)
        + scaffolded_prompt returns a list of paragraphs (Node returns array)
        + Document factory with optional running header (doc name + page numbers)
        + save_document uses ✅/❌ console prefixes per project convention
"""

from .constants import (
    FONT, PAGE, SIZE, SPACING, COLOR, THEMES, FRAMEWORK, TABLE_BORDER_COLOR,
)
from .theme import set_theme, get_theme
from .components import (
    # core building blocks
    title, subtitle, video_link, name_date_line, job_selection_line,
    section_header, para, para_multi, fill_line, inline_blank, page_break,
    numbered_question, scaffolded_prompt,
    # complex components
    info_box, question_header, self_check_box, tip_box, warning_box,
    connection_box, candidates_list, evaluation_table,
)
from .document import create_document, save_document

__version__ = "1.0.0"
__all__ = [
    # constants
    "FONT", "PAGE", "SIZE", "SPACING", "COLOR", "THEMES", "FRAMEWORK",
    "TABLE_BORDER_COLOR",
    # theme
    "set_theme", "get_theme",
    # building blocks
    "title", "subtitle", "video_link", "name_date_line", "job_selection_line",
    "section_header", "para", "para_multi", "fill_line", "inline_blank",
    "page_break", "numbered_question", "scaffolded_prompt",
    # complex components
    "info_box", "question_header", "self_check_box", "tip_box", "warning_box",
    "connection_box", "candidates_list", "evaluation_table",
    # document
    "create_document", "save_document",
]
