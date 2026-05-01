"""Activity-sheet generation: briefing → Claude → JSON spec → .docx.

Pipeline:
  1. build_briefing(lesson, form_data) — assembles the briefing fields per
     skills/_briefings/video_briefing.md.
  2. call_claude(briefing) — sends the briefing + general-employability SKILL.md
     to Claude. Claude responds via a forced tool_use call carrying a JSON
     worksheet spec (validated against WORKSHEET_SCHEMA).
  3. render(spec, output_path) — walks the spec and dispatches to lesson_builder
     component methods to produce a .docx.

The JSON spec is the seam between LLM and rendering. A future no-LLM mode just
needs to populate the same spec from a form.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lesson_builder import (
    set_theme, create_document, save_document,
    title, subtitle, video_link, name_date_line, job_selection_line,
    section_header, para, fill_line, page_break,
    numbered_question, scaffolded_prompt,
    info_box, question_header, self_check_box, tip_box, warning_box,
    connection_box, candidates_list, evaluation_table,
    COLOR, THEMES,
)


# ═══════════════════════════════════════════════════════════════════════════
# JSON schema — the worksheet spec
# ═══════════════════════════════════════════════════════════════════════════

_RUN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "text": {"type": "string"},
        "bold": {"type": "boolean"},
        "italic": {"type": "boolean"},
        "color": {"type": "string", "description": "6-char hex without #"},
        "blank": {"type": "integer", "minimum": 1, "maximum": 60},
        "break": {"type": "boolean"},
    },
}

_COMPONENT_SCHEMA = {
    "type": "object",
    "required": ["type"],
    "properties": {
        "type": {
            "type": "string",
            "enum": [
                "title", "subtitle", "video_link", "name_date_line",
                "section_header", "para", "info_box", "numbered_question",
                "scaffolded_prompt", "tip_box", "warning_box", "connection_box",
                "question_header", "candidates_list", "evaluation_table",
                "job_selection_line", "self_check_box", "fill_line",
            ],
        },
        "text": {"type": "string"},
        "url": {"type": "string"},
        "title": {"type": "string"},
        "italic": {"type": "boolean"},
        "bold": {"type": "boolean"},
        "color": {"type": "string"},
        "align": {"type": "string", "enum": ["left", "center", "right", "justify"]},
        "paragraphs": {
            "type": "array",
            "items": {"type": "array", "items": _RUN_SCHEMA},
        },
        "number": {"type": "integer", "minimum": 1},
        "timestamp": {"type": "string"},
        "runs": {"type": "array", "items": _RUN_SCHEMA},
        "label": {"type": "string"},
        "hint": {"type": "string"},
        "candidates": {"type": "array", "items": {"type": "string"}},
        "role": {"type": "string"},
        "criteria": {"type": "array", "items": {"type": "string"}},
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["text"],
                "properties": {
                    "text": {"type": "string"},
                    "timestamp": {"type": "string"},
                },
            },
        },
        "default_job": {"type": "string"},
        "items": {"type": "array", "items": {"type": "string"}},
    },
}

WORKSHEET_SCHEMA = {
    "type": "object",
    "required": ["theme", "header_name", "page1", "page2"],
    "additionalProperties": False,
    "properties": {
        "theme": {"type": "string", "enum": list(THEMES.keys())},
        "header_name": {"type": "string", "minLength": 1, "maxLength": 80},
        "page1": {"type": "array", "items": _COMPONENT_SCHEMA, "minItems": 1},
        "page2": {"type": "array", "items": _COMPONENT_SCHEMA, "minItems": 1},
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# Briefing
# ═══════════════════════════════════════════════════════════════════════════

def _source_text(lesson) -> str:
    """Pull out the body text from either a Lesson or a SourceContent."""
    # Lesson has .transcript; SourceContent has .transcript_text plus
    # .pdf_text / .raw_text. Try them in order.
    for attr in ("transcript", "transcript_text", "pdf_text", "raw_text"):
        v = getattr(lesson, attr, "")
        if v:
            return v
    return ""


def build_briefing(lesson, form_data: dict) -> dict:
    """Assemble the briefing dict from a lesson + the submitted form fields.

    Accepts either a legacy Lesson or a SourceContent (duck-typed on
    .title, .youtube_url, .ted_url, .author, .collection, .duration plus a
    body-text attribute).
    """
    return {
        "VIDEO": lesson.title or getattr(lesson, "lesson_id", "") or getattr(lesson, "id", ""),
        "URL": getattr(lesson, "youtube_url", "") or getattr(lesson, "ted_url", "") or "",
        "TRANSCRIPT": _source_text(lesson),
        "FORMAT": form_data.get("format", "follow_along"),
        "FRAMEWORK": form_data.get("framework", "Auto"),
        "THEME_COLOR": form_data.get("theme", "teal"),
        "CANDIDATES": form_data.get("candidates", "").strip(),
        "CONNECTIONS": form_data.get("connections", "").strip(),
        "VOCAB_TO_DEFINE": form_data.get("vocab", "").strip(),
        "SPECIAL_NOTES": form_data.get("notes", "").strip(),
        "AUTHOR": getattr(lesson, "author", "") or "",
        "COLLECTION": getattr(lesson, "collection", "") or "",
        "DURATION": getattr(lesson, "duration", "") or "",
    }


# ═══════════════════════════════════════════════════════════════════════════
# Claude call (Anthropic API)
# ═══════════════════════════════════════════════════════════════════════════

_SKILL_PATH = REPO_ROOT / "skills" / "general-employability" / "SKILL.md"
_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
_MAX_TOKENS = 8000


def _load_skill_md() -> str:
    return _SKILL_PATH.read_text(encoding="utf-8")


def _system_prompt() -> str:
    """The system prompt: SKILL.md + a short instruction layer.

    Static — eligible for prompt caching."""
    skill = _load_skill_md()
    return (
        "You are an expert curriculum designer building a printable two-page "
        "student activity sheet. Follow the skill specification below "
        "exactly.\n\n"
        f"{skill}\n\n"
        "You will receive a briefing as a user message. Respond by calling the "
        "`build_worksheet` tool with a complete worksheet spec. Do not write "
        "any prose; the tool call is your entire response.\n\n"
        "Rules for the spec:\n"
        "- `theme` must be one of: " + ", ".join(THEMES.keys()) + ".\n"
        "- Page 1 always starts with title → subtitle → video_link → "
        "name_date_line, then a framework info_box, then a section_header, "
        "then numbered_question components.\n"
        "- Page 2 starts with a section_header, then either a candidates_list "
        "+ evaluation_table (Interview Game) or 2-3 scaffolded_prompt "
        "components (Follow-Along), then a job_selection_line, then a "
        "bonus numbered_question, then a self_check_box.\n"
        "- Numbered questions use `runs` arrays where each run is "
        '{"text": "..."} or {"blank": N} or {"break": true}.\n'
        "- Hex colors are 6 chars without `#`.\n"
        "- Name strategies, never number them.\n"
        "- Answers must come from the transcript; do not require outside "
        "knowledge."
    )


def _build_worksheet_tool() -> dict:
    return {
        "name": "build_worksheet",
        "description": (
            "Submit the final worksheet spec. Calling this tool is your only "
            "output."
        ),
        "input_schema": WORKSHEET_SCHEMA,
    }


def call_claude(briefing: dict) -> dict:
    """Call Claude and return a validated worksheet spec dict.

    Raises RuntimeError on missing API key or malformed response.
    Raises jsonschema.ValidationError if Claude's output doesn't match
    WORKSHEET_SCHEMA.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Export it before generating "
            "activity sheets."
        )

    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError(
            "anthropic package not installed. Run: pip install -r requirements.txt"
        ) from e

    client = anthropic.Anthropic(api_key=api_key)
    user_msg = (
        "Build a worksheet for the following briefing:\n\n"
        + json.dumps(briefing, indent=2)
    )

    response = client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=[{
            "type": "text",
            "text": _system_prompt(),
            "cache_control": {"type": "ephemeral"},
        }],
        tools=[_build_worksheet_tool()],
        tool_choice={"type": "tool", "name": "build_worksheet"},
        messages=[{"role": "user", "content": user_msg}],
    )

    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "build_worksheet":
            spec = block.input
            jsonschema.validate(spec, WORKSHEET_SCHEMA)
            return spec

    raise RuntimeError("Claude did not return a build_worksheet tool call.")


# ═══════════════════════════════════════════════════════════════════════════
# Render: spec → lesson_builder calls → .docx
# ═══════════════════════════════════════════════════════════════════════════

def _resolve_color(value: str | None) -> str | None:
    if not value:
        return None
    return COLOR.get(value, value)


def _render_runs(runs: list[dict]) -> list[dict]:
    """Pass runs through, resolving named colors to hex."""
    out = []
    for r in runs:
        if "color" in r:
            r = {**r, "color": _resolve_color(r["color"])}
        out.append(r)
    return out


def _render_component(doc, comp: dict) -> None:
    t = comp["type"]

    if t == "title":
        title(doc, comp["text"])
    elif t == "subtitle":
        subtitle(doc, comp["text"])
    elif t == "video_link":
        video_link(doc, comp["url"])
    elif t == "name_date_line":
        name_date_line(doc)
    elif t == "section_header":
        section_header(doc, comp["text"], color=_resolve_color(comp.get("color")))
    elif t == "para":
        para(
            doc, comp["text"],
            align=comp.get("align", "left"),
            bold=comp.get("bold", False),
            italic=comp.get("italic", False),
            color=_resolve_color(comp.get("color")),
        )
    elif t == "fill_line":
        fill_line(doc)
    elif t == "info_box":
        paragraphs = [_render_runs(p) for p in comp.get("paragraphs", [])]
        info_box(doc, comp["title"], paragraphs)
    elif t == "numbered_question":
        numbered_question(
            doc, comp["number"], _render_runs(comp.get("runs", [])),
            timestamp=comp.get("timestamp"),
        )
    elif t == "scaffolded_prompt":
        scaffolded_prompt(doc, comp["label"], comp.get("hint", ""))
    elif t == "tip_box":
        tip_box(doc, comp["text"])
    elif t == "warning_box":
        warning_box(doc, comp["text"])
    elif t == "connection_box":
        connection_box(doc, comp["text"])
    elif t == "question_header":
        question_header(doc, comp["text"], timestamp=comp.get("timestamp"))
    elif t == "candidates_list":
        candidates_list(doc, comp["candidates"], comp["role"])
    elif t == "evaluation_table":
        evaluation_table(
            doc,
            candidates=comp["candidates"],
            criteria=comp["criteria"],
            questions=comp["questions"],
        )
    elif t == "job_selection_line":
        job_selection_line(doc, comp["default_job"])
    elif t == "self_check_box":
        self_check_box(doc, comp["items"])
    else:
        raise ValueError(f"Unknown component type: {t}")


def render(spec: dict, output_path: str | Path) -> bool:
    """Render a validated worksheet spec to .docx at output_path."""
    jsonschema.validate(spec, WORKSHEET_SCHEMA)
    set_theme(spec["theme"])
    doc = create_document(use_header=True, header_name=spec["header_name"])

    for comp in spec["page1"]:
        _render_component(doc, comp)

    page_break(doc)

    for comp in spec["page2"]:
        _render_component(doc, comp)

    return save_document(doc, output_path)


# ═══════════════════════════════════════════════════════════════════════════
# Top-level orchestration: source → Claude → save → DOCX → return record
# ═══════════════════════════════════════════════════════════════════════════

LESSON_TYPE = "general_employability_activity_sheet"


def _has_usable_body(source) -> bool:
    """Whether this source has enough text to feed the model."""
    if hasattr(source, "has_usable_body"):
        return bool(source.has_usable_body)
    # Legacy Lesson: require a successful transcript.
    return bool(getattr(source, "transcript", "")) and \
        getattr(source, "transcript_status", "") == "ok"


def generate(source, form_data: dict, output_dir: str | Path, store=None):
    """Run the full activity-sheet generation pipeline.

    Steps:
      1. Insert/refresh a GeneratedLesson row with status='running'.
      2. Build briefing → call Claude → validate spec.
      3. Render HTML view of the spec (durable, in-DB).
      4. Render DOCX to local disk (TEMPORARY artifact — see CLAUDE.md
         durability boundary).
      5. Persist lesson_json + lesson_html on the GeneratedLesson row,
         status='done'. Persist a LessonArtifact pointing at the DOCX.

    Returns: (generated_lesson, error_message). On failure
    `generated_lesson.generation_status == 'failed'`. The caller can use
    `generated_lesson.id` to look the row up later regardless.

    `store` is the Postgres store. If None, the function still runs the
    pipeline and returns an in-memory GeneratedLesson + DOCX, but no row
    is persisted (useful for tests).
    """
    from ted_lessons.models import GeneratedLesson, LessonArtifact

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_id = getattr(source, "id", "") or getattr(source, "lesson_id", "")
    title = getattr(source, "title", "") or "Activity Sheet"

    gl = GeneratedLesson(
        source_content_id=source_id,
        lesson_type=LESSON_TYPE,
        title=title,
        generation_status="running",
        briefing_json=dict(form_data) if form_data else {},
    )
    if store is not None:
        store.save_generated_lesson(gl)

    if not _has_usable_body(source):
        gl.generation_status = "failed"
        gl.error_message = "Source has no usable transcript or body text."
        if store is not None:
            store.save_generated_lesson(gl)
        return gl, gl.error_message

    try:
        briefing = build_briefing(source, form_data)
        spec = call_claude(briefing)

        # In-DB durable views.
        from spec_to_html import render_html  # local import: web/ is on sys.path
        html_view = render_html(spec)

        # Local-disk artifact (NON-DURABLE on Render).
        output_path = output_dir / f"{gl.id}.docx"
        ok = render(spec, output_path)
        if not ok:
            raise RuntimeError("Failed to save DOCX document.")

        gl.lesson_json = spec
        gl.lesson_html = html_view
        gl.model_used = _MODEL
        gl.generation_status = "done"
        gl.error_message = ""
        if store is not None:
            store.save_generated_lesson(gl)

            artifact = LessonArtifact(
                generated_lesson_id=gl.id,
                artifact_type="docx",
                storage_backend="local",
                file_path_or_url=str(output_path),
                file_size_bytes=output_path.stat().st_size,
            )
            store.save_artifact(artifact)

        return gl, None

    except jsonschema.ValidationError as e:
        msg = f"Claude returned an invalid worksheet spec: {e.message}"
    except RuntimeError as e:
        msg = str(e)
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"

    gl.generation_status = "failed"
    gl.error_message = msg
    if store is not None:
        store.save_generated_lesson(gl)
    return gl, msg


def regenerate_docx(generated_lesson, output_path: str | Path) -> bool:
    """Re-render the DOCX for a saved GeneratedLesson from its lesson_json.

    Used by the artifact-download endpoint to recover when a local DOCX
    file has been wiped (e.g. after a Render redeploy). Cheap — just walks
    the saved spec; no LLM call.
    """
    if not generated_lesson.lesson_json:
        return False
    return render(generated_lesson.lesson_json, output_path)
