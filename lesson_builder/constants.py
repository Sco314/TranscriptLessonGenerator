"""
constants.py — Style constants ported from student-activity-template_Rev02112026_0357PM.js (v1.1).

Naming maps directly: Node `SIZE.title` → Python `SIZE["title"]`. Values identical.
Half-points for font sizes (22 = 11pt). Twips for spacing (20 twips = 1pt, 1440 twips = 1in).
DXA for page dimensions (12240 = 8.5in).

If you change a value here, change it in the Node template too. Drift breaks
the visual consistency of mixed-runtime worksheets.
"""

# ─── Font (universal) ────────────────────────────────────────────────────────
FONT = "Arial"

# ─── Page Setup (US Letter) ──────────────────────────────────────────────────
# DXA = 1/1440 inch. 8.5" × 11" with 0.5" margins.
PAGE = {
    "width": 12240,           # 8.5 inches
    "height": 15840,          # 11 inches
    "margins": {
        "top": 720,           # 0.5 inch (use 900 when header present)
        "right": 720,
        "bottom": 720,
        "left": 720,
    },
    "content_width": 10800,   # page width minus left+right margins
    "header_top_margin": 900, # used when running header is enabled
}

# ─── Font Sizes (half-points: 22 = 11pt) ─────────────────────────────────────
SIZE = {
    "title": 34,              # 17pt — main document title
    "subtitle": 20,           # 10pt — italicized descriptor under title
    "section_header": 22,     # 11pt — bold colored section headers
    "body": 20,               # 10pt — standard paragraph text
    "table_header": 18,       # 9pt — column headers (constrained by width)
    "table_body": 18,         # 9pt — table cell content
    "helper": 16,             # 8pt — italicized tips, instructions
    "link": 18,               # 9pt — URL display
    "page_number": 18,        # 9pt — header/footer page numbers
}

# ─── Spacing (twips: 20 twips = 1pt, 1440 twips = 1in) ───────────────────────
SPACING = {
    "after_title": 40,
    "after_subtitle": 60,
    "after_video_link": 140,
    "after_name_line": 160,
    "before_section": 160,
    "after_section_header": 60,
    "after_paragraph": 120,
    "after_fill_line": 60,
    "after_table_row": 0,
    "between_questions": 120,
    "after_numbered_question": 180,
}

# ─── Colors ──────────────────────────────────────────────────────────────────
# All hex strings WITHOUT leading #. python-docx wants 6-char uppercase hex.
COLOR = {
    # Text
    "header_text":   "FFFFFF",   # white — text on dark backgrounds
    "body_text":     "000000",   # black — standard text
    "helper_text":   "666666",   # gray — instructions, tips
    "light_helper":  "555555",   # slightly darker gray
    "link":          "1565C0",   # blue — URLs
    "error":         "C62828",   # red — mistakes, warnings
    "success":       "2E7D32",   # green — correct, tips
    "hidden":        "FFFFFF",   # white text — invisible on paper, visible when selected

    # Backgrounds
    "alt_row":       "F5F5F5",   # light gray — alternating table rows
    "table_border":  "AAAAAA",   # medium gray — table borders
    "fill_line":     "CCCCCC",   # light gray — fill-in underlines

    # Question section banners
    "question_1_bg":   "E3F2FD",   # light blue
    "question_1_text": "1565C0",   # blue
    "question_2_bg":   "FFF3E0",   # light orange
    "question_2_text": "E65100",   # orange
    "bonus_bg":        "E3F2FD",
    "bonus_text":      "1565C0",

    # Callout backgrounds
    "tip_bg":          "E8F5E9",   # light green
    "warning_bg":      "FFEBEE",   # light red
    "connection_bg":   "E8F5E9",   # light green
}

# Convenience alias used by table-building code
TABLE_BORDER_COLOR = COLOR["table_border"]

# ─── Themes ──────────────────────────────────────────────────────────────────
# Mutable theme is held in theme.py. These are the immutable presets.
THEMES = {
    "blue":   {"primary": "1565C0", "primary_light": "E3F2FD", "name": "Blue"},
    "purple": {"primary": "6A1B9A", "primary_light": "F3E5F5", "name": "Purple"},
    "teal":   {"primary": "00695C", "primary_light": "E0F2F1", "name": "Teal"},
    "brown":  {"primary": "5D4037", "primary_light": "EFEBE9", "name": "Brown"},
    "green":  {"primary": "2E7D32", "primary_light": "E8F5E9", "name": "Green"},
    "orange": {"primary": "E65100", "primary_light": "FFF3E0", "name": "Orange"},
    # Navy + gold extension used in Soft Skills Chapter 14 (added in port)
    "navy":   {"primary": "1A237E", "primary_light": "E8EAF6", "name": "Navy"},
}

# ─── Framework Colors (for teaching acronyms) ────────────────────────────────
FRAMEWORK = {
    "STAR": {
        "S": {"color": "C62828", "bg": "FFEBEE", "label": "Situation"},
        "T": {"color": "EF6C00", "bg": "FFF3E0", "label": "Task"},
        "A": {"color": "2E7D32", "bg": "E8F5E9", "label": "Action"},
        "R": {"color": "1565C0", "bg": "E3F2FD", "label": "Result"},
    },
    "CARL": {
        "C": {"color": "6A1B9A", "bg": "F3E5F5", "label": "Context"},
        "A": {"color": "1565C0", "bg": "E3F2FD", "label": "Action"},
        "R": {"color": "2E7D32", "bg": "E8F5E9", "label": "Result"},
        "L": {"color": "E65100", "bg": "FFF3E0", "label": "Learned"},
    },
    "FOURP": {
        "P1": {"color": "6A1B9A", "bg": "F3E5F5", "label": "Personal"},
        "P2": {"color": "6A1B9A", "bg": "F3E5F5", "label": "Professional"},
        "P3": {"color": "6A1B9A", "bg": "F3E5F5", "label": "Positive"},
        "P4": {"color": "6A1B9A", "bg": "F3E5F5", "label": "Pithy"},
    },
}

# ─── Table cell padding (twips) ──────────────────────────────────────────────
CELL_MARGINS = {"top": 60, "bottom": 60, "left": 100, "right": 100}
