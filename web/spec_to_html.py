"""Render a WORKSHEET_SCHEMA spec to in-browser HTML.

The DOCX render in `lesson_builder` is the canonical print output. This
module mirrors the same component dispatch but emits semantic HTML so a
saved generated lesson can be displayed in-app without re-running Claude
or even the DOCX engine. The lesson_json spec is the source of truth;
DOCX and HTML are both derived views.

Output is a self-contained string of HTML you can drop inside a Jinja
template (no <html>/<head> wrapper). Theme colors are emitted as inline
CSS variables on a wrapping <article>.
"""

from __future__ import annotations

import html
import re
from typing import Any, Iterable

from lesson_builder import COLOR, THEMES


def _resolve_color(value: str | None) -> str:
    if not value:
        return ""
    return COLOR.get(value, value)


def _esc(text: str) -> str:
    return html.escape(text or "")


def _render_runs(runs: Iterable[dict]) -> str:
    """Convert a list of run dicts to inline HTML."""
    out = []
    for r in runs:
        if r.get("break"):
            out.append("<br>")
            continue
        if "blank" in r:
            n = max(1, min(60, int(r["blank"])))
            # Underline of N en-spaces; printable + visually a fill-line.
            out.append(
                f'<span class="ws-blank" style="display:inline-block;'
                f'border-bottom:1px solid #888;min-width:{n*0.5:.1f}ch;">'
                f'&nbsp;</span>'
            )
            continue
        text = _esc(r.get("text", ""))
        styles = []
        if r.get("bold"):
            styles.append("font-weight:600")
        if r.get("italic"):
            styles.append("font-style:italic")
        color = _resolve_color(r.get("color"))
        if color:
            styles.append(f"color:#{color}")
        if styles:
            out.append(f'<span style="{";".join(styles)}">{text}</span>')
        else:
            out.append(text)
    return "".join(out)


def _component(comp: dict) -> str:
    t = comp.get("type")

    if t == "title":
        return f'<h1 class="ws-title">{_esc(comp["text"])}</h1>'

    if t == "subtitle":
        return f'<p class="ws-subtitle"><em>{_esc(comp["text"])}</em></p>'

    if t == "video_link":
        url = _esc(comp["url"])
        return (
            f'<p class="ws-video-link">'
            f'<strong>Video:</strong> <a href="{url}" target="_blank" '
            f'rel="noopener noreferrer">{url}</a></p>'
        )

    if t == "name_date_line":
        return (
            '<p class="ws-name-date">'
            'Name: <span class="ws-fill">&nbsp;</span> &nbsp; '
            'Date: <span class="ws-fill">&nbsp;</span></p>'
        )

    if t == "section_header":
        color = _resolve_color(comp.get("color")) or "var(--theme-primary, 00695C)"
        style = f"color:#{color};" if not color.startswith("var") else f"color:{color};"
        return f'<h2 class="ws-section-header" style="{style}">{_esc(comp["text"])}</h2>'

    if t == "para":
        align = comp.get("align", "left")
        styles = [f"text-align:{align}"]
        if comp.get("bold"):
            styles.append("font-weight:600")
        if comp.get("italic"):
            styles.append("font-style:italic")
        color = _resolve_color(comp.get("color"))
        if color:
            styles.append(f"color:#{color}")
        return f'<p class="ws-para" style="{";".join(styles)}">{_esc(comp["text"])}</p>'

    if t == "fill_line":
        return '<p class="ws-fill-line"><span class="ws-fill">&nbsp;</span></p>'

    if t == "info_box":
        title = _esc(comp.get("title", ""))
        paras = []
        for p in comp.get("paragraphs", []):
            paras.append(f"<p>{_render_runs(p)}</p>")
        return (
            f'<aside class="ws-info-box">'
            f'<h3>{title}</h3>{"".join(paras)}</aside>'
        )

    if t == "numbered_question":
        n = int(comp.get("number", 1))
        timestamp = comp.get("timestamp")
        ts_html = (
            f' <span class="ws-timestamp">[{_esc(timestamp)}]</span>'
            if timestamp else ""
        )
        body = _render_runs(comp.get("runs", []))
        return (
            f'<div class="ws-numbered-q">'
            f'<span class="ws-q-number">{n}.</span>{ts_html} '
            f'<span class="ws-q-body">{body}</span></div>'
        )

    if t == "scaffolded_prompt":
        label = _esc(comp.get("label", ""))
        hint = _esc(comp.get("hint", ""))
        hint_html = f' <em class="ws-hint">{hint}</em>' if hint else ""
        return (
            f'<div class="ws-scaffold">'
            f'<p class="ws-scaffold-label">{label}{hint_html}</p>'
            f'<div class="ws-scaffold-lines">'
            f'<div class="ws-fill-line"></div>'
            f'<div class="ws-fill-line"></div>'
            f'<div class="ws-fill-line"></div>'
            f'</div></div>'
        )

    if t == "tip_box":
        return f'<aside class="ws-tip-box">💡 {_esc(comp["text"])}</aside>'

    if t == "warning_box":
        return f'<aside class="ws-warning-box">⚠️ {_esc(comp["text"])}</aside>'

    if t == "connection_box":
        return f'<aside class="ws-connection-box">🔗 {_esc(comp["text"])}</aside>'

    if t == "question_header":
        ts = comp.get("timestamp")
        ts_html = f' <span class="ws-timestamp">[{_esc(ts)}]</span>' if ts else ""
        return (
            f'<h3 class="ws-question-header">{_esc(comp["text"])}{ts_html}</h3>'
        )

    if t == "candidates_list":
        role = _esc(comp.get("role", ""))
        items = "".join(f"<li>{_esc(c)}</li>" for c in comp.get("candidates", []))
        return (
            f'<div class="ws-candidates">'
            f'<p><strong>Role:</strong> {role}</p>'
            f'<ol>{items}</ol></div>'
        )

    if t == "evaluation_table":
        candidates = comp.get("candidates", [])
        criteria = comp.get("criteria", [])
        questions = comp.get("questions", [])
        # Header row: blank corner, then candidate names.
        head_cells = "".join(f"<th>{_esc(c)}</th>" for c in candidates)
        head = f"<tr><th></th>{head_cells}</tr>"
        # One row per question (with optional timestamp), then one row per criterion.
        body_rows = []
        for q in questions:
            ts = q.get("timestamp")
            ts_html = f' <span class="ws-timestamp">[{_esc(ts)}]</span>' if ts else ""
            cells = "".join("<td>&nbsp;</td>" for _ in candidates)
            body_rows.append(
                f'<tr><th class="ws-q-cell">{_esc(q.get("text", ""))}{ts_html}</th>{cells}</tr>'
            )
        for crit in criteria:
            cells = "".join("<td>&nbsp;</td>" for _ in candidates)
            body_rows.append(f"<tr><th>{_esc(crit)}</th>{cells}</tr>")
        return (
            '<table class="ws-eval-table"><thead>'
            f"{head}</thead><tbody>{''.join(body_rows)}</tbody></table>"
        )

    if t == "job_selection_line":
        return (
            f'<p class="ws-job-line">'
            f'<strong>Job:</strong> {_esc(comp.get("default_job", ""))} '
            f'<span class="ws-fill">&nbsp;</span></p>'
        )

    if t == "self_check_box":
        items = "".join(
            f'<li><label><input type="checkbox" disabled> {_esc(item)}</label></li>'
            for item in comp.get("items", [])
        )
        return (
            f'<aside class="ws-self-check">'
            f'<h4>Self-check</h4><ul>{items}</ul></aside>'
        )

    # Unknown component: surface it instead of failing the whole render.
    return f'<div class="ws-unknown" data-type="{_esc(t or "")}"></div>'


_DEFAULT_STYLES = """
<style>
.ws-document { font-family: Arial, sans-serif; max-width: 8.5in;
  margin: 1rem auto; padding: 1.5rem; background: #fff; color: #111;
  line-height: 1.5; box-shadow: 0 0 0 1px #e2e2e2; }
.ws-document h1.ws-title { font-size: 1.7rem; margin: 0 0 .3rem; color: var(--theme-primary, #00695C); }
.ws-document p.ws-subtitle { margin: 0 0 1rem; color: #555; }
.ws-document h2.ws-section-header { margin-top: 1.4rem; font-size: 1.15rem; }
.ws-document h3 { margin: 1rem 0 .4rem; }
.ws-document p { margin: .4rem 0; }
.ws-document .ws-page-break { border: 0; border-top: 2px dashed #ccc;
  margin: 2rem 0; }
.ws-document .ws-fill { display: inline-block; min-width: 8ch;
  border-bottom: 1px solid #888; }
.ws-document .ws-fill-line { display: block; border-bottom: 1px solid #aaa;
  height: 1.4em; margin: .3em 0; }
.ws-document .ws-info-box, .ws-document .ws-tip-box,
.ws-document .ws-warning-box, .ws-document .ws-connection-box,
.ws-document .ws-self-check {
  border-radius: 6px; padding: .75rem 1rem; margin: .8rem 0; }
.ws-document .ws-info-box { background: var(--theme-light, #E0F2F1); }
.ws-document .ws-tip-box { background: #E8F5E9; }
.ws-document .ws-warning-box { background: #FFEBEE; }
.ws-document .ws-connection-box { background: #E8F5E9; }
.ws-document .ws-self-check { background: #F5F5F5; border: 1px solid #ddd; }
.ws-document .ws-numbered-q { margin: .6rem 0; }
.ws-document .ws-q-number { font-weight: 700; }
.ws-document .ws-timestamp { color: #888; font-size: .85em; }
.ws-document .ws-eval-table { border-collapse: collapse; width: 100%;
  margin: 1rem 0; font-size: .9em; }
.ws-document .ws-eval-table th, .ws-document .ws-eval-table td {
  border: 1px solid #aaa; padding: .35rem .5rem; vertical-align: top; }
.ws-document .ws-eval-table th { background: #F5F5F5; text-align: left; }
.ws-document .ws-q-cell { font-weight: 600; }
.ws-document .ws-scaffold { margin: .8rem 0; }
.ws-document .ws-scaffold-lines .ws-fill-line { margin: .4em 0; }
@media print {
  .ws-document { box-shadow: none; max-width: none; padding: 0; }
}
</style>
""".strip()


def render_html(spec: dict, include_styles: bool = True) -> str:
    """Render a worksheet spec to a self-contained HTML fragment.

    Arguments:
        spec: a validated WORKSHEET_SCHEMA dict.
        include_styles: prepend a <style> block with the default print-friendly
            stylesheet. Set False if the host page already provides one.
    """
    theme_key = spec.get("theme", "teal")
    theme = THEMES.get(theme_key, THEMES["teal"])
    primary = theme.get("primary", "00695C")
    light = theme.get("primary_light", "E0F2F1")

    page1_html = "".join(_component(c) for c in spec.get("page1", []))
    page2_html = "".join(_component(c) for c in spec.get("page2", []))

    body = (
        f'<article class="ws-document" style="--theme-primary:#{primary};'
        f'--theme-light:#{light};">'
        f'<header class="ws-header">{_esc(spec.get("header_name", ""))}</header>'
        f'<section class="ws-page ws-page-1">{page1_html}</section>'
        f'<hr class="ws-page-break">'
        f'<section class="ws-page ws-page-2">{page2_html}</section>'
        f'</article>'
    )

    if include_styles:
        return _DEFAULT_STYLES + "\n" + body
    return body
