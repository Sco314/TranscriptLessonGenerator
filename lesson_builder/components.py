"""
components.py — All worksheet components ported from the Node template.

Naming: snake_case Python equivalents of camelCase Node helpers.
    Node title()              → Python title()
    Node nameDateLine()       → Python name_date_line()
    Node numberedQuestion()   → Python numbered_question()
    Node scaffoldedPrompt()   → Python scaffolded_prompt()  (returns list)
    Node evaluationTable()    → Python evaluation_table()

Behavior parity is the goal: same colors, same spacing values, same hidden
white timestamps, same single-page-front-and-back layout discipline.

Functions that returned arrays in Node (e.g. scaffolded_prompt, candidates_list)
return lists here, so callers extend the document children list with them:

    body = []
    body.extend(scaffolded_prompt("Why this role?", "1–2 sentences"))
"""

from typing import Iterable, Optional, Sequence, Union

from docx.document import Document as _Document  # type: ignore
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Pt, Twips
from docx.table import Table, _Cell

from .constants import (
    CELL_MARGINS, COLOR, FONT, PAGE, SIZE, SPACING,
)
from .theme import primary, primary_light

# ═══════════════════════════════════════════════════════════════════════════
# Low-level XML helpers
#
# python-docx doesn't expose every Word feature we need (cell shading, paragraph
# borders, hidden runs, custom tab stops). We reach into the OXML directly via
# the same `qn()` namespace helper python-docx uses internally. This is the
# same approach python-docx's own examples use for advanced formatting.
# ═══════════════════════════════════════════════════════════════════════════

def _set_run_font(run, size_half_points: int, *, bold: bool = False,
                  italic: bool = False, color_hex: Optional[str] = None,
                  font_name: str = FONT):
    """Apply Arial-by-default font + size + color to a run."""
    run.font.name = font_name
    # ensure East Asian + Complex Script also use the font (Word quirk)
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rFonts.set(qn(attr), font_name)
    # Half-points: docx Pt() takes points, so divide
    run.font.size = Pt(size_half_points / 2.0)
    run.font.bold = bool(bold)
    run.font.italic = bool(italic)
    if color_hex:
        run.font.color.rgb = _RGB(color_hex)


def _RGB(hex_str: str):
    """Convert a 6-char hex string to a docx RGBColor."""
    from docx.shared import RGBColor
    return RGBColor.from_string(hex_str.upper().lstrip("#"))


def _set_paragraph_spacing(paragraph, *, before_twips: int = 0, after_twips: int = 0):
    pf = paragraph.paragraph_format
    if before_twips:
        pf.space_before = Twips(before_twips)
    else:
        pf.space_before = Twips(0)
    pf.space_after = Twips(after_twips)


def _set_paragraph_alignment(paragraph, align: str):
    """align: 'left' | 'center' | 'right' | 'justify'"""
    mapping = {
        "left": WD_ALIGN_PARAGRAPH.LEFT,
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
        "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
    }
    paragraph.alignment = mapping.get(align, WD_ALIGN_PARAGRAPH.LEFT)


def _shade_cell(cell: _Cell, hex_fill: str):
    """Add ShadingType.CLEAR background to a table cell."""
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill.upper())
    # remove any existing shd
    for existing in tcPr.findall(qn("w:shd")):
        tcPr.remove(existing)
    tcPr.append(shd)


def _set_cell_borders(cell: _Cell, color_hex: str = COLOR["table_border"], size: int = 8):
    """Single-line borders on all four sides of a cell."""
    tcPr = cell._tc.get_or_add_tcPr()
    # remove any existing
    existing = tcPr.find(qn("w:tcBorders"))
    if existing is not None:
        tcPr.remove(existing)
    tcBorders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        b = OxmlElement(f"w:{side}")
        b.set(qn("w:val"), "single")
        b.set(qn("w:sz"), str(size))
        b.set(qn("w:space"), "0")
        b.set(qn("w:color"), color_hex.upper())
        tcBorders.append(b)
    tcPr.append(tcBorders)


def _set_cell_margins(cell: _Cell):
    tcPr = cell._tc.get_or_add_tcPr()
    existing = tcPr.find(qn("w:tcMar"))
    if existing is not None:
        tcPr.remove(existing)
    tcMar = OxmlElement("w:tcMar")
    for side, val in (("top", CELL_MARGINS["top"]), ("left", CELL_MARGINS["left"]),
                      ("bottom", CELL_MARGINS["bottom"]), ("right", CELL_MARGINS["right"])):
        m = OxmlElement(f"w:{side}")
        m.set(qn("w:w"), str(val))
        m.set(qn("w:type"), "dxa")
        tcMar.append(m)
    tcPr.append(tcMar)


def _set_cell_vertical_align(cell: _Cell, align: str = "center"):
    cell.vertical_alignment = {
        "top": WD_ALIGN_VERTICAL.TOP,
        "center": WD_ALIGN_VERTICAL.CENTER,
        "bottom": WD_ALIGN_VERTICAL.BOTTOM,
    }.get(align, WD_ALIGN_VERTICAL.CENTER)


def _add_paragraph_bottom_border(paragraph, color_hex: str, size: int = 6):
    """Adds a bottom border to a paragraph — used for fill_line()."""
    pPr = paragraph._p.get_or_add_pPr()
    existing = pPr.find(qn("w:pBdr"))
    if existing is not None:
        pPr.remove(existing)
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size))
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), color_hex.upper())
    pBdr.append(bottom)
    pPr.append(pBdr)


def _set_paragraph_indent(paragraph, *, left_twips: int = 0, hanging_twips: int = 0):
    pPr = paragraph._p.get_or_add_pPr()
    existing = pPr.find(qn("w:ind"))
    if existing is not None:
        pPr.remove(existing)
    ind = OxmlElement("w:ind")
    if left_twips:
        ind.set(qn("w:left"), str(left_twips))
    if hanging_twips:
        ind.set(qn("w:hanging"), str(hanging_twips))
    pPr.append(ind)


def _set_paragraph_tab_stop(paragraph, position_twips: int, val: str = "left"):
    pPr = paragraph._p.get_or_add_pPr()
    existing = pPr.find(qn("w:tabs"))
    if existing is None:
        existing = OxmlElement("w:tabs")
        pPr.append(existing)
    tab = OxmlElement("w:tab")
    tab.set(qn("w:val"), val)
    tab.set(qn("w:pos"), str(position_twips))
    existing.append(tab)


# ═══════════════════════════════════════════════════════════════════════════
# Append-mode pattern
#
# python-docx writes by appending to a Document object — there's no "build a
# Paragraph object then add it later" like the Node docx library. So every
# helper here takes the Document as its first arg and appends in place.
# This is a minor API difference from the Node template; callers compose by
# calling helpers in sequence rather than building an array.
#
# Where the Node API returned an array (scaffolded_prompt, candidates_list),
# we keep the same semantic: the helper appends multiple things.
# ═══════════════════════════════════════════════════════════════════════════

# ─── Core building blocks ────────────────────────────────────────────────────

def title(doc: _Document, text: str):
    """Centered, large, theme-colored title."""
    p = doc.add_paragraph()
    _set_paragraph_alignment(p, "center")
    _set_paragraph_spacing(p, after_twips=SPACING["after_title"])
    run = p.add_run(text)
    _set_run_font(run, SIZE["title"], bold=True, color_hex=primary())
    return p


def subtitle(doc: _Document, text: str):
    """Centered italicized descriptor under the title."""
    p = doc.add_paragraph()
    _set_paragraph_alignment(p, "center")
    _set_paragraph_spacing(p, after_twips=SPACING["after_subtitle"])
    run = p.add_run(text)
    _set_run_font(run, SIZE["subtitle"], italic=True, color_hex=COLOR["light_helper"])
    return p


def video_link(doc: _Document, url: str):
    """Centered 'Video: <url>' line."""
    p = doc.add_paragraph()
    _set_paragraph_alignment(p, "center")
    _set_paragraph_spacing(p, after_twips=SPACING["after_video_link"])
    label = p.add_run("Video: ")
    _set_run_font(label, SIZE["link"], color_hex=COLOR["helper_text"])
    link = p.add_run(url)
    _set_run_font(link, SIZE["link"], color_hex=COLOR["link"])
    return p


def name_date_line(doc: _Document):
    """`Name: ___________ Date: _____` line."""
    p = doc.add_paragraph()
    _set_paragraph_spacing(p, after_twips=SPACING["after_name_line"])
    name_label = p.add_run("Name: ")
    _set_run_font(name_label, SIZE["body"], bold=True)
    name_blank = p.add_run(inline_blank(30))
    _set_run_font(name_blank, SIZE["body"])
    date_label = p.add_run("     Date: ")
    _set_run_font(date_label, SIZE["body"], bold=True)
    date_blank = p.add_run(inline_blank(15))
    _set_run_font(date_blank, SIZE["body"])
    return p


def job_selection_line(doc: _Document, default_job: str):
    """Centered 'I am applying for: <default> (circle)  or  ____ (your choice)'."""
    p = doc.add_paragraph()
    _set_paragraph_alignment(p, "center")
    _set_paragraph_spacing(p, after_twips=180)

    parts = [
        ("I am applying for:     ", SIZE["body"], True, False, None),
        (default_job, SIZE["body"], True, False, None),
        ("  (circle)", SIZE["helper"], False, True, COLOR["helper_text"]),
        ("     or     ", SIZE["body"], False, False, None),
        (inline_blank(30), SIZE["body"], False, False, None),
        ("  (your choice)", SIZE["helper"], False, True, COLOR["helper_text"]),
    ]
    for text, size, bold, italic, color in parts:
        run = p.add_run(text)
        _set_run_font(run, size, bold=bold, italic=italic, color_hex=color)
    return p


def section_header(doc: _Document, text: str, *, color: Optional[str] = None):
    """Bold theme-colored section heading with proper before/after spacing."""
    p = doc.add_paragraph()
    _set_paragraph_spacing(
        p,
        before_twips=SPACING["before_section"],
        after_twips=SPACING["after_section_header"],
    )
    run = p.add_run(text)
    _set_run_font(run, SIZE["section_header"], bold=True,
                  color_hex=color or primary())
    return p


def para(doc: _Document, text: str, *, align: str = "left", size: int = SIZE["body"],
         bold: bool = False, italic: bool = False, color: Optional[str] = None,
         space_before: int = 0, space_after: Optional[int] = None):
    """Standard paragraph with formatting overrides."""
    p = doc.add_paragraph()
    _set_paragraph_alignment(p, align)
    _set_paragraph_spacing(
        p,
        before_twips=space_before,
        after_twips=SPACING["after_paragraph"] if space_after is None else space_after,
    )
    run = p.add_run(text)
    _set_run_font(run, size, bold=bold, italic=italic, color_hex=color)
    return p


def para_multi(doc: _Document, runs: Sequence[dict], *, align: str = "left",
               space_before: int = 0, space_after: Optional[int] = None):
    """Paragraph with multiple text runs of mixed formatting.

    Each run dict: {text, size?, bold?, italic?, color?}
    """
    p = doc.add_paragraph()
    _set_paragraph_alignment(p, align)
    _set_paragraph_spacing(
        p,
        before_twips=space_before,
        after_twips=SPACING["after_paragraph"] if space_after is None else space_after,
    )
    for run_spec in runs:
        run = p.add_run(run_spec.get("text", ""))
        _set_run_font(
            run,
            run_spec.get("size", SIZE["body"]),
            bold=run_spec.get("bold", False),
            italic=run_spec.get("italic", False),
            color_hex=run_spec.get("color"),
        )
    return p


def fill_line(doc: _Document, *, space_after: Optional[int] = None):
    """Underline-style fill-in-the-blank line (paragraph with bottom border)."""
    p = doc.add_paragraph()
    _set_paragraph_spacing(
        p,
        after_twips=SPACING["after_fill_line"] if space_after is None else space_after,
    )
    _add_paragraph_bottom_border(p, COLOR["fill_line"], size=6)
    run = p.add_run(" ")
    _set_run_font(run, SIZE["helper"])
    return p


def inline_blank(length: int = 20) -> str:
    """Inline underscore blank for use within a run of text."""
    return "_" * length


def page_break(doc: _Document):
    """Hard page break."""
    p = doc.add_paragraph()
    run = p.add_run()
    run.add_break(WD_BREAK.PAGE)
    return p


# ─── numbered_question — the workhorse ───────────────────────────────────────

def numbered_question(
    doc: _Document,
    num: int,
    runs: Sequence[dict],
    *,
    timestamp: Optional[str] = None,
    space_after: Optional[int] = None,
    space_before: int = 0,
    num_color: Optional[str] = None,
    num_size: Optional[int] = None,
    text_size: Optional[int] = None,
):
    """Numbered question with mixed content runs and optional hidden timestamp.

    runs: list of dicts. Each one is ONE of:
        {"text": "string", "bold": bool?, "italic": bool?, "color": "hex"?}
        {"blank": int}     — inline underscore blank
        {"break": True}    — line break (prevents orphaned blanks)

    timestamp: e.g. "1:04" — rendered as white text, invisible on paper but
    visible when text is selected. Same trick as the Node template.

    Mirrors Node numberedQuestion(num, runs, opts).
    """
    n_color = num_color or primary()
    n_size = num_size or SIZE["body"]
    t_size = text_size or SIZE["body"]
    after = SPACING["after_numbered_question"] if space_after is None else space_after

    p = doc.add_paragraph()
    _set_paragraph_spacing(p, before_twips=space_before, after_twips=after)
    _set_paragraph_indent(p, left_twips=360, hanging_twips=360)
    _set_paragraph_tab_stop(p, position_twips=360, val="left")

    # Number + tab
    num_run = p.add_run(f"{num}.\t")
    _set_run_font(num_run, n_size, bold=True, color_hex=n_color)

    # Hidden timestamp — white text, invisible on paper
    if timestamp:
        ts_run = p.add_run(f"({timestamp}) ")
        _set_run_font(ts_run, SIZE["helper"], color_hex=COLOR["hidden"])

    # Process runs in order
    for spec in runs:
        if spec.get("break"):
            run = p.add_run()
            run.add_break(WD_BREAK.LINE)
        elif "blank" in spec:
            blank = p.add_run("_" * spec["blank"])
            _set_run_font(blank, t_size, color_hex=COLOR["body_text"])
        elif "text" in spec:
            run = p.add_run(spec["text"])
            _set_run_font(
                run,
                spec.get("size", t_size),
                bold=spec.get("bold", False),
                italic=spec.get("italic", False),
                color_hex=spec.get("color", COLOR["body_text"]),
            )
    return p


def scaffolded_prompt(doc: _Document, label: str, hint: str = "",
                      *, label_color: Optional[str] = None):
    """Bold prompt + optional gray hint + fill-in line.

    Returns nothing (mutates doc); Node version returned [paragraph, fillLine].
    """
    color = label_color or primary()
    p = doc.add_paragraph()
    _set_paragraph_spacing(p, before_twips=80, after_twips=40)
    label_run = p.add_run(label)
    _set_run_font(label_run, SIZE["body"], bold=True, color_hex=color)
    if hint:
        hint_run = p.add_run(f" {hint}")
        _set_run_font(hint_run, SIZE["helper"], italic=True, color_hex=COLOR["helper_text"])
    fill_line(doc)


# ═══════════════════════════════════════════════════════════════════════════
# Complex components — single-cell tables with shaded backgrounds
# ═══════════════════════════════════════════════════════════════════════════

def _full_width_shaded_box(doc: _Document, bg_color: str,
                           build_content) -> Table:
    """Single-cell, full-content-width table with shaded background.

    build_content is a callable that takes a `cell` and adds paragraphs to it.
    Used as the foundation for info_box, question_header, tip_box, etc.
    """
    table = doc.add_table(rows=1, cols=1)
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    # Set table width and column width
    _set_table_width(table, PAGE["content_width"])

    cell = table.rows[0].cells[0]
    _set_cell_width(cell, PAGE["content_width"])
    _set_cell_borders(cell)
    _shade_cell(cell, bg_color)
    _set_cell_margins(cell)

    # Remove the auto-added empty paragraph python-docx puts in the cell
    if cell.paragraphs and not cell.paragraphs[0].runs:
        cell._tc.remove(cell.paragraphs[0]._p)

    build_content(cell)
    return table


def _set_table_width(table: Table, width_twips: int):
    tblPr = table._element.tblPr
    tblW = tblPr.find(qn("w:tblW"))
    if tblW is None:
        tblW = OxmlElement("w:tblW")
        tblPr.append(tblW)
    tblW.set(qn("w:w"), str(width_twips))
    tblW.set(qn("w:type"), "dxa")


def _set_cell_width(cell: _Cell, width_twips: int):
    tcPr = cell._tc.get_or_add_tcPr()
    tcW = tcPr.find(qn("w:tcW"))
    if tcW is None:
        tcW = OxmlElement("w:tcW")
        tcPr.append(tcW)
    tcW.set(qn("w:w"), str(width_twips))
    tcW.set(qn("w:type"), "dxa")


def _add_para_to_cell(cell: _Cell, *, align: str = "left",
                       space_before: int = 0, space_after: int = 0):
    """Add a fresh paragraph to a cell with spacing/alignment baked in."""
    p = cell.add_paragraph()
    _set_paragraph_alignment(p, align)
    _set_paragraph_spacing(p, before_twips=space_before, after_twips=space_after)
    return p


def info_box(doc: _Document, title_text: str,
             content_paragraphs: Iterable[Sequence[dict]],
             *, bg_color: Optional[str] = None,
             title_color: Optional[str] = None) -> Table:
    """Framework/info box with shaded background and bold title.

    content_paragraphs: an iterable where each item is a list of run-spec dicts
    (same shape as para_multi runs). Each item becomes one paragraph in the box.
    """
    bg = bg_color or primary_light()
    tc = title_color or primary()

    def build(cell: _Cell):
        # Title paragraph
        tp = _add_para_to_cell(cell, align="center", space_after=80)
        run = tp.add_run(title_text)
        _set_run_font(run, SIZE["section_header"] + 2, bold=True, color_hex=tc)

        # Content paragraphs
        for runs in content_paragraphs:
            cp = _add_para_to_cell(cell, align="left", space_after=40)
            for spec in runs:
                r = cp.add_run(spec.get("text", ""))
                _set_run_font(
                    r,
                    spec.get("size", SIZE["body"]),
                    bold=spec.get("bold", False),
                    italic=spec.get("italic", False),
                    color_hex=spec.get("color"),
                )

    return _full_width_shaded_box(doc, bg, build)


def question_header(doc: _Document, question_text: str,
                    *, bg_color: Optional[str] = None,
                    text_color: Optional[str] = None,
                    timestamp: Optional[str] = None) -> Table:
    """Colored banner with the question text inside."""
    bg = bg_color or COLOR["question_1_bg"]
    tx = text_color or COLOR["question_1_text"]
    display = f"{question_text} ({timestamp})" if timestamp else question_text

    def build(cell: _Cell):
        p = _add_para_to_cell(cell)
        run = p.add_run(display)
        _set_run_font(run, SIZE["body"], bold=True, color_hex=tx)

    return _full_width_shaded_box(doc, bg, build)


def self_check_box(doc: _Document, items: Sequence[str],
                   *, title: str = "✓ Self-Check: Review Your Answers",
                   bg_color: Optional[str] = None) -> Table:
    """Box with a title and a list of checkbox items."""
    bg = bg_color or primary_light()

    def build(cell: _Cell):
        tp = _add_para_to_cell(cell, align="center", space_after=60)
        run = tp.add_run(title)
        _set_run_font(run, SIZE["section_header"], bold=True, color_hex=primary())

        for i, item in enumerate(items):
            ip = _add_para_to_cell(cell, align="center",
                                   space_before=0 if i == 0 else 40)
            box = ip.add_run("☐ ")
            _set_run_font(box, SIZE["table_body"])
            txt = ip.add_run(item)
            _set_run_font(txt, SIZE["table_body"])

    return _full_width_shaded_box(doc, bg, build)


def tip_box(doc: _Document, tip_text: str, *,
            icon: str = "💡", label: str = "Tip:",
            bg_color: Optional[str] = None,
            text_color: Optional[str] = None) -> Table:
    """Generic callout box. Use warning_box / connection_box for preset variants."""
    bg = bg_color or COLOR["tip_bg"]
    tx = text_color or COLOR["success"]

    def build(cell: _Cell):
        p = _add_para_to_cell(cell)
        head = p.add_run(f"{icon} {label} ")
        _set_run_font(head, SIZE["table_body"], bold=True, color_hex=tx)
        body = p.add_run(tip_text)
        _set_run_font(body, SIZE["table_body"], italic=True, color_hex=COLOR["light_helper"])

    return _full_width_shaded_box(doc, bg, build)


def warning_box(doc: _Document, warning_text: str) -> Table:
    return tip_box(
        doc, warning_text,
        icon="⚠️", label="Warning:",
        bg_color=COLOR["warning_bg"], text_color=COLOR["error"],
    )


def connection_box(doc: _Document, connection_text: str) -> Table:
    return tip_box(
        doc, connection_text,
        icon="🔗", label="Connection:",
        bg_color=COLOR["connection_bg"], text_color=COLOR["success"],
    )


def candidates_list(doc: _Document, candidates: Sequence[str], role: str):
    """'The Candidates (All applying for X)' header + bulleted name line."""
    header = doc.add_paragraph()
    _set_paragraph_spacing(header, after_twips=40)
    h_run = header.add_run("The Candidates ")
    _set_run_font(h_run, SIZE["body"], bold=True, color_hex=primary())
    sub_run = header.add_run(f"(All applying for {role})")
    _set_run_font(sub_run, SIZE["table_body"], italic=True, color_hex=COLOR["helper_text"])

    names = doc.add_paragraph()
    _set_paragraph_spacing(names, after_twips=SPACING["after_name_line"])
    name_run = names.add_run("• " + "     • ".join(candidates))
    _set_run_font(name_run, SIZE["body"], bold=True)


def evaluation_table(doc: _Document, *, candidates: Sequence[str],
                     criteria: Sequence[str],
                     questions: Sequence[dict]) -> Table:
    """Multi-row evaluation table with question section headers between candidate blocks.

    questions: list of {"text": str, "timestamp": str?}
    """
    name_w = 1400
    notes_w = 2700
    # Distribute remainder among criteria columns
    crit_w = (PAGE["content_width"] - name_w - notes_w) // len(criteria)

    n_cols = 2 + len(criteria)  # candidate + criteria + notes
    table = doc.add_table(rows=0, cols=n_cols)
    table.autofit = False
    _set_table_width(table, PAGE["content_width"])

    # ── Header row ──
    header_row = table.add_row()
    _fill_header_cell(header_row.cells[0], "Candidate", name_w)
    for i, crit in enumerate(criteria):
        _fill_header_cell(header_row.cells[1 + i], crit, crit_w)
    _fill_header_cell(header_row.cells[-1], "Notes", notes_w)

    # ── Question sections ──
    for q_idx, q in enumerate(questions):
        # Section banner row (merged)
        banner_row = table.add_row()
        merged = banner_row.cells[0]
        for c in banner_row.cells[1:]:
            merged = merged.merge(c)
        bg = COLOR["question_1_bg"] if q_idx % 2 == 0 else COLOR["question_2_bg"]
        fg = COLOR["question_1_text"] if q_idx % 2 == 0 else COLOR["question_2_text"]
        _set_cell_borders(merged)
        _shade_cell(merged, bg)
        _set_cell_margins(merged)
        if merged.paragraphs and not merged.paragraphs[0].runs:
            merged._tc.remove(merged.paragraphs[0]._p)
        bp = _add_para_to_cell(merged, align="center")
        ts = f" ({q['timestamp']})" if q.get("timestamp") else ""
        run = bp.add_run(f"Q{q_idx + 1}: \"{q['text']}\"{ts}")
        _set_run_font(run, SIZE["table_body"], bold=True, color_hex=fg)

        # Candidate rows
        for c_idx, name in enumerate(candidates):
            row = table.add_row()
            shade = COLOR["alt_row"] if c_idx % 2 == 1 else None

            name_cell = row.cells[0]
            _set_cell_width(name_cell, name_w)
            _set_cell_borders(name_cell)
            _set_cell_margins(name_cell)
            _set_cell_vertical_align(name_cell)
            if shade:
                _shade_cell(name_cell, shade)
            _clear_cell(name_cell)
            np = _add_para_to_cell(name_cell)
            np_run = np.add_run(name)
            _set_run_font(np_run, SIZE["table_body"], bold=True)

            for ci in range(len(criteria)):
                cell = row.cells[1 + ci]
                _set_cell_width(cell, crit_w)
                _set_cell_borders(cell)
                _set_cell_margins(cell)
                _set_cell_vertical_align(cell)
                if shade:
                    _shade_cell(cell, shade)
                _clear_cell(cell)
                _add_para_to_cell(cell, align="center")

            notes_cell = row.cells[-1]
            _set_cell_width(notes_cell, notes_w)
            _set_cell_borders(notes_cell)
            _set_cell_margins(notes_cell)
            _set_cell_vertical_align(notes_cell)
            if shade:
                _shade_cell(notes_cell, shade)
            _clear_cell(notes_cell)
            _add_para_to_cell(notes_cell)

    return table


def _fill_header_cell(cell: _Cell, label: str, width_twips: int):
    _set_cell_width(cell, width_twips)
    _set_cell_borders(cell)
    _set_cell_margins(cell)
    _set_cell_vertical_align(cell)
    _shade_cell(cell, primary())
    _clear_cell(cell)
    p = _add_para_to_cell(cell, align="center")
    run = p.add_run(label)
    _set_run_font(run, SIZE["table_header"], bold=True, color_hex=COLOR["header_text"])


def _clear_cell(cell: _Cell):
    """Remove the default empty paragraph python-docx adds to a new cell."""
    if cell.paragraphs and not cell.paragraphs[0].runs:
        cell._tc.remove(cell.paragraphs[0]._p)
