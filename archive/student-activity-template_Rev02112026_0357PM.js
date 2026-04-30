// ============================================================================
// STUDENT ACTIVITY SHEET TEMPLATE
// Version: 1.1
// Created: 2026-02-11
// Updated: 2026-02-11 3:57 PM CST
// Description: Master template for Indeed video student activity worksheets
// ============================================================================
// CHANGELOG:
//   v1.1 (02-11-2026 3:57 PM CST)
//     + Added numberedQuestion() helper function
//       - Bold + colored question numbers with tab indent
//       - Mixed-content runs: { text }, { blank }, { break }
//       - Hidden white timestamp text (invisible on paper, visible when selected)
//       - Configurable spaceAfter (default 180 twips) for student writing room
//       - Added TextRun "Break" import dependency
// ============================================================================

const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
        AlignmentType, BorderStyle, WidthType, ShadingType,
        PageBreak, Header, Footer, PageNumber } = require('docx');
const fs = require('fs');

// ============================================================================
// STYLE CONSTANTS
// ============================================================================

// Font (universal)
const FONT = "Arial";

// Page Setup (US Letter)
const PAGE = {
  width: 12240,           // 8.5 inches in DXA (twips)
  height: 15840,          // 11 inches in DXA
  margins: {
    top: 720,             // 0.5 inch (use 900 when header present)
    right: 720,           // 0.5 inch
    bottom: 720,          // 0.5 inch
    left: 720             // 0.5 inch
  },
  contentWidth: 10800     // Page width minus left/right margins
};

// Font Sizes (in half-points: value 22 = 11pt)
const SIZE = {
  title: 34,              // 17pt - Main document title
  subtitle: 20,           // 10pt - Italicized descriptor under title
  sectionHeader: 22,      // 11pt - Bold colored section headers
  body: 20,               // 10pt - Standard paragraph text
  tableHeader: 18,        // 9pt - Column headers (constrained by width)
  tableBody: 18,          // 9pt - Table cell content
  helper: 16,             // 8pt - Italicized tips, instructions
  link: 18,               // 9pt - URL display
  pageNumber: 18          // 9pt - Header/footer page numbers
};

// Spacing (in twips: 20 twips = 1pt, 1440 twips = 1 inch)
const SPACING = {
  afterTitle: 40,
  afterSubtitle: 60,
  afterVideoLink: 140,
  afterNameLine: 160,
  beforeSection: 160,
  afterSectionHeader: 60,
  afterParagraph: 120,
  afterFillLine: 60,
  afterTableRow: 0,
  betweenQuestions: 120,
  afterNumberedQuestion: 180  // v1.1: default space after numberedQuestion for writing room
};

// Colors - Functional (consistent across all documents)
const COLOR = {
  // Text colors
  headerText: "FFFFFF",       // White - text on dark backgrounds
  bodyText: "000000",         // Black - standard text
  helperText: "666666",       // Gray - instructions, tips
  lightHelper: "555555",      // Slightly darker gray
  link: "1565C0",             // Blue - URLs
  error: "C62828",            // Red - mistakes, warnings
  success: "2E7D32",          // Green - correct, tips
  hidden: "FFFFFF",           // White - hidden text (timestamps, invisible on paper)
  
  // Background colors
  altRow: "F5F5F5",           // Light gray - alternating table rows
  tableBorder: "AAAAAA",      // Medium gray - table borders
  fillLine: "CCCCCC",         // Light gray - fill-in underlines
  
  // Question section backgrounds
  question1Bg: "E3F2FD",      // Light blue
  question1Text: "1565C0",    // Blue
  question2Bg: "FFF3E0",      // Light orange
  question2Text: "E65100",    // Orange
  bonusBg: "E3F2FD",          // Light blue
  bonusText: "1565C0",        // Blue
  
  // Callout backgrounds
  tipBg: "E8F5E9",            // Light green
  warningBg: "FFEBEE",        // Light red
  connectionBg: "E8F5E9"      // Light green
};

// Theme Colors (override per document)
// These get set by setTheme() function
let THEME = {
  primary: "1565C0",          // Default blue
  primaryLight: "E3F2FD",     // Light blue accent
  name: "Default Blue"
};

// Predefined themes
const THEMES = {
  blue:   { primary: "1565C0", primaryLight: "E3F2FD", name: "Blue" },
  purple: { primary: "6A1B9A", primaryLight: "F3E5F5", name: "Purple" },
  teal:   { primary: "00695C", primaryLight: "E0F2F1", name: "Teal" },
  brown:  { primary: "5D4037", primaryLight: "EFEBE9", name: "Brown" },
  green:  { primary: "2E7D32", primaryLight: "E8F5E9", name: "Green" },
  orange: { primary: "E65100", primaryLight: "FFF3E0", name: "Orange" }
};

// Framework Colors (for teaching acronyms)
const FRAMEWORK = {
  STAR: {
    S: { color: "C62828", bg: "FFEBEE", label: "Situation" },
    T: { color: "EF6C00", bg: "FFF3E0", label: "Task" },
    A: { color: "2E7D32", bg: "E8F5E9", label: "Action" },
    R: { color: "1565C0", bg: "E3F2FD", label: "Result" }
  },
  CARL: {
    C: { color: "6A1B9A", bg: "F3E5F5", label: "Context" },
    A: { color: "1565C0", bg: "E3F2FD", label: "Action" },
    R: { color: "2E7D32", bg: "E8F5E9", label: "Result" },
    L: { color: "E65100", bg: "FFF3E0", label: "Learned" }
  },
  FOURP: {
    P1: { color: "6A1B9A", bg: "F3E5F5", label: "Personal" },
    P2: { color: "6A1B9A", bg: "F3E5F5", label: "Professional" },
    P3: { color: "6A1B9A", bg: "F3E5F5", label: "Positive" },
    P4: { color: "6A1B9A", bg: "F3E5F5", label: "Pithy" }
  }
};

// Table styling
const TABLE = {
  border: { style: BorderStyle.SINGLE, size: 8, color: "AAAAAA" },
  cellMargins: { top: 60, bottom: 60, left: 100, right: 100 }
};

// Computed borders object (all sides same)
const borders = {
  top: TABLE.border,
  bottom: TABLE.border,
  left: TABLE.border,
  right: TABLE.border
};

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Set the document theme colors
 * @param {string} themeName - One of: blue, purple, teal, brown, green, orange
 */
function setTheme(themeName) {
  if (THEMES[themeName]) {
    THEME = { ...THEMES[themeName] };
  }
}

/**
 * Get borders object (optionally customize)
 * @param {object} opts - Optional overrides { color, size, style }
 */
function getBorders(opts = {}) {
  const b = {
    style: opts.style || TABLE.border.style,
    size: opts.size || TABLE.border.size,
    color: opts.color || TABLE.border.color
  };
  return { top: b, bottom: b, left: b, right: b };
}

// ============================================================================
// HELPER FUNCTIONS - Core Building Blocks
// ============================================================================

/**
 * Create a table cell with standard formatting
 * @param {string} content - Text content
 * @param {object} opts - Options: header, width, shade, align, bold, fontSize, color, vAlign
 */
function cell(content, opts = {}) {
  const isHeader = opts.header || false;
  const width = opts.width || 1560;
  const shade = opts.shade || (isHeader ? THEME.primary : null);
  const align = opts.align || AlignmentType.LEFT;
  const bold = opts.bold !== undefined ? opts.bold : isHeader;
  const fontSize = opts.fontSize || SIZE.tableBody;
  const textColor = opts.color || (isHeader ? COLOR.headerText : COLOR.bodyText);
  
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: shade ? { fill: shade, type: ShadingType.CLEAR } : undefined,
    margins: TABLE.cellMargins,
    verticalAlign: opts.vAlign || "center",
    columnSpan: opts.columnSpan || 1,
    children: [
      new Paragraph({
        alignment: align,
        children: [
          new TextRun({
            text: content,
            font: FONT,
            size: fontSize,
            bold: bold,
            italics: opts.italics || false,
            color: textColor
          })
        ]
      })
    ]
  });
}

/**
 * Create a multi-content table cell (for mixed formatting within one cell)
 * @param {array} runs - Array of TextRun objects or config objects
 * @param {object} opts - Cell options: width, shade, align, vAlign
 */
function cellMulti(runs, opts = {}) {
  const children = runs.map(run => {
    if (run instanceof TextRun) return run;
    return new TextRun({
      text: run.text || "",
      font: FONT,
      size: run.size || SIZE.tableBody,
      bold: run.bold || false,
      italics: run.italics || false,
      color: run.color || COLOR.bodyText
    });
  });
  
  return new TableCell({
    borders,
    width: { size: opts.width || 1560, type: WidthType.DXA },
    shading: opts.shade ? { fill: opts.shade, type: ShadingType.CLEAR } : undefined,
    margins: TABLE.cellMargins,
    verticalAlign: opts.vAlign || "center",
    columnSpan: opts.columnSpan || 1,
    children: [
      new Paragraph({
        alignment: opts.align || AlignmentType.LEFT,
        children: children
      })
    ]
  });
}

/**
 * Create a paragraph with standard formatting
 * @param {string} text - Text content
 * @param {object} opts - Options: align, size, bold, italic, color, spaceBefore, spaceAfter
 */
function para(text, opts = {}) {
  return new Paragraph({
    alignment: opts.align || AlignmentType.LEFT,
    spacing: {
      before: opts.spaceBefore || 0,
      after: opts.spaceAfter !== undefined ? opts.spaceAfter : SPACING.afterParagraph
    },
    children: [
      new TextRun({
        text: text,
        font: FONT,
        size: opts.size || SIZE.body,
        bold: opts.bold || false,
        italics: opts.italic || false,
        color: opts.color || COLOR.bodyText
      })
    ]
  });
}

/**
 * Create a paragraph with multiple text runs (mixed formatting)
 * @param {array} runs - Array of { text, size, bold, italic, color } objects
 * @param {object} opts - Paragraph options: align, spaceBefore, spaceAfter
 */
function paraMulti(runs, opts = {}) {
  const children = runs.map(run => new TextRun({
    text: run.text || "",
    font: FONT,
    size: run.size || SIZE.body,
    bold: run.bold || false,
    italics: run.italic || false,
    color: run.color || COLOR.bodyText
  }));
  
  return new Paragraph({
    alignment: opts.align || AlignmentType.LEFT,
    spacing: {
      before: opts.spaceBefore || 0,
      after: opts.spaceAfter !== undefined ? opts.spaceAfter : SPACING.afterParagraph
    },
    children: children
  });
}

/**
 * Create a fill-in-the-blank line (underline style)
 * @param {object} opts - Options: spaceAfter
 */
function fillLine(opts = {}) {
  return new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: COLOR.fillLine } },
    spacing: { after: opts.spaceAfter || SPACING.afterFillLine },
    children: [new TextRun({ text: " ", size: SIZE.helper })]
  });
}

/**
 * Create inline blank (underscores for fill-in within text)
 * @param {number} length - Approximate character length
 */
function inlineBlank(length = 20) {
  return "_".repeat(length);
}

/**
 * Create a section header
 * @param {string} text - Header text
 * @param {object} opts - Options: color (defaults to theme primary)
 */
function sectionHeader(text, opts = {}) {
  return new Paragraph({
    spacing: { before: SPACING.beforeSection, after: SPACING.afterSectionHeader },
    children: [
      new TextRun({
        text: text,
        font: FONT,
        size: SIZE.sectionHeader,
        bold: true,
        color: opts.color || THEME.primary
      })
    ]
  });
}

/**
 * Create document title (centered, large)
 * @param {string} text - Title text
 */
function title(text) {
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: SPACING.afterTitle },
    children: [
      new TextRun({
        text: text,
        font: FONT,
        size: SIZE.title,
        bold: true,
        color: THEME.primary
      })
    ]
  });
}

/**
 * Create document subtitle (centered, italic)
 * @param {string} text - Subtitle text
 */
function subtitle(text) {
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: SPACING.afterSubtitle },
    children: [
      new TextRun({
        text: text,
        font: FONT,
        size: SIZE.subtitle,
        italics: true,
        color: COLOR.lightHelper
      })
    ]
  });
}

/**
 * Create video link line (centered)
 * @param {string} url - Video URL
 */
function videoLink(url) {
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: SPACING.afterVideoLink },
    children: [
      new TextRun({ text: "Video: ", font: FONT, size: SIZE.link, color: COLOR.helperText }),
      new TextRun({ text: url, font: FONT, size: SIZE.link, color: COLOR.link })
    ]
  });
}

/**
 * Create name/date line
 */
function nameDateLine() {
  return new Paragraph({
    spacing: { after: SPACING.afterNameLine },
    children: [
      new TextRun({ text: "Name: ", font: FONT, size: SIZE.body, bold: true }),
      new TextRun({ text: inlineBlank(30), font: FONT, size: SIZE.body }),
      new TextRun({ text: "     Date: ", font: FONT, size: SIZE.body, bold: true }),
      new TextRun({ text: inlineBlank(15), font: FONT, size: SIZE.body })
    ]
  });
}

/**
 * Create job selection line (centered, with circle option)
 * @param {string} defaultJob - The default job to circle
 */
function jobSelectionLine(defaultJob) {
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 180 },
    children: [
      new TextRun({ text: "I am applying for:     ", font: FONT, size: SIZE.body, bold: true }),
      new TextRun({ text: defaultJob, font: FONT, size: SIZE.body, bold: true }),
      new TextRun({ text: "  (circle)", font: FONT, size: SIZE.helper, italics: true, color: COLOR.helperText }),
      new TextRun({ text: "     or     ", font: FONT, size: SIZE.body }),
      new TextRun({ text: inlineBlank(30), font: FONT, size: SIZE.body }),
      new TextRun({ text: "  (your choice)", font: FONT, size: SIZE.helper, italics: true, color: COLOR.helperText })
    ]
  });
}

/**
 * Create a page break
 */
function pageBreak() {
  return new Paragraph({ children: [new PageBreak()] });
}

// ============================================================================
// HELPER FUNCTIONS - Numbered Questions (v1.1)
// ============================================================================

/**
 * Create a numbered question with mixed content (text, blanks, line breaks)
 * and an optional hidden timestamp in white text.
 * 
 * The number is bold + theme-colored, question text is normal body text,
 * tab-indented for clean alignment. Blanks render as underscores inline.
 * Line breaks ({ break: true }) prevent orphaned blanks at line ends.
 * Hidden timestamps are white text â€” invisible on paper but visible when
 * text is selected in a word processor (useful for answer key alignment).
 * 
 * @param {number} num - Question number (displayed as "1.", "2.", etc.)
 * @param {array} runs - Array of content objects:
 *   { text: "string" }          - Normal body text
 *   { text: "string", bold: true, color: "#hex" } - Styled text
 *   { blank: 18 }               - Inline blank (number = underscore count)
 *   { break: true }             - Line break (prevents orphaned blanks)
 * @param {object} opts - Options:
 *   timestamp {string}          - Video timestamp, rendered as hidden white text e.g. "1:04"
 *   spaceAfter {number}         - Twips after paragraph (default: SPACING.afterNumberedQuestion = 180)
 *   spaceBefore {number}        - Twips before paragraph (default: 0)
 *   numColor {string}           - Override color for the number (default: THEME.primary)
 *   numSize {number}            - Override size for the number (default: SIZE.body)
 *   textSize {number}           - Override size for text runs (default: SIZE.body)
 * 
 * @returns {Paragraph} A single Paragraph element
 * 
 * @example
 * // Simple question
 * numberedQuestion(1, [
 *   { text: "What is the first step in resolving a conflict?" }
 * ])
 * 
 * @example
 * // Question with blanks and line break
 * numberedQuestion(2, [
 *   { text: "Complete the quote: \"You're either going to be " },
 *   { blank: 18 },
 *   { break: true },
 *   { text: "or you'll be " },
 *   { blank: 12 },
 *   { text: ".\"" }
 * ], { timestamp: "1:04" })
 * 
 * @example
 * // Question with styled text
 * numberedQuestion(3, [
 *   { text: "The video says to use " },
 *   { text: "\"I\" statements", bold: true, color: "C62828" },
 *   { text: " instead of " },
 *   { blank: 15 },
 *   { text: " statements." }
 * ], { timestamp: "2:30" })
 */
function numberedQuestion(num, runs, opts = {}) {
  const numColor = opts.numColor || THEME.primary;
  const numSize = opts.numSize || SIZE.body;
  const textSize = opts.textSize || SIZE.body;
  const spaceAfter = opts.spaceAfter !== undefined ? opts.spaceAfter : SPACING.afterNumberedQuestion;
  const spaceBefore = opts.spaceBefore || 0;
  
  // Build the TextRun children array
  const children = [];
  
  // Question number: bold, colored, with tab
  children.push(new TextRun({
    text: `${num}.\t`,
    font: FONT,
    size: numSize,
    bold: true,
    color: numColor
  }));
  
  // Hidden timestamp (white text â€” invisible on paper, visible when selected)
  if (opts.timestamp) {
    children.push(new TextRun({
      text: `(${opts.timestamp}) `,
      font: FONT,
      size: SIZE.helper,
      color: COLOR.hidden
    }));
  }
  
  // Process each run in the content array
  runs.forEach(run => {
    if (run.break) {
      // Line break â€” prevents orphaned blanks
      children.push(new TextRun({ break: 1 }));
    } else if (run.blank !== undefined) {
      // Inline blank â€” underscores
      children.push(new TextRun({
        text: "_".repeat(run.blank),
        font: FONT,
        size: textSize,
        color: COLOR.bodyText
      }));
    } else if (run.text !== undefined) {
      // Text run â€” supports optional bold, italic, color overrides
      children.push(new TextRun({
        text: run.text,
        font: FONT,
        size: run.size || textSize,
        bold: run.bold || false,
        italics: run.italic || run.italics || false,
        color: run.color || COLOR.bodyText
      }));
    }
  });
  
  return new Paragraph({
    spacing: { before: spaceBefore, after: spaceAfter },
    tabStops: [{ type: "left", position: 360 }],
    indent: { left: 360, hanging: 360 },
    children: children
  });
}

// ============================================================================
// HELPER FUNCTIONS - Complex Components
// ============================================================================

/**
 * Create an info/framework box (single-cell table with background)
 * @param {string} titleText - Box title
 * @param {array} contentParagraphs - Array of Paragraph objects for content
 * @param {object} opts - Options: bgColor (defaults to theme primaryLight)
 */
function infoBox(titleText, contentParagraphs, opts = {}) {
  const bgColor = opts.bgColor || THEME.primaryLight;
  const titleColor = opts.titleColor || THEME.primary;
  
  const children = [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 80 },
      children: [
        new TextRun({
          text: titleText,
          font: FONT,
          size: SIZE.sectionHeader + 2,
          bold: true,
          color: titleColor
        })
      ]
    }),
    ...contentParagraphs
  ];
  
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    columnWidths: [PAGE.contentWidth],
    rows: [
      new TableRow({
        children: [
          new TableCell({
            borders,
            width: { size: PAGE.contentWidth, type: WidthType.DXA },
            shading: { fill: bgColor, type: ShadingType.CLEAR },
            margins: { top: 80, bottom: 80, left: 150, right: 150 },
            children: children
          })
        ]
      })
    ]
  });
}

/**
 * Create a question header box (colored banner)
 * @param {string} questionText - The question
 * @param {object} opts - Options: bgColor, textColor, timestamp
 */
function questionHeader(questionText, opts = {}) {
  const bgColor = opts.bgColor || COLOR.question1Bg;
  const textColor = opts.textColor || COLOR.question1Text;
  const displayText = opts.timestamp 
    ? `${questionText} (${opts.timestamp})`
    : questionText;
  
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    columnWidths: [PAGE.contentWidth],
    rows: [
      new TableRow({
        children: [
          new TableCell({
            borders,
            width: { size: PAGE.contentWidth, type: WidthType.DXA },
            shading: { fill: bgColor, type: ShadingType.CLEAR },
            margins: { top: 80, bottom: 80, left: 150, right: 150 },
            children: [
              new Paragraph({
                children: [
                  new TextRun({
                    text: displayText,
                    font: FONT,
                    size: SIZE.body,
                    bold: true,
                    color: textColor
                  })
                ]
              })
            ]
          })
        ]
      })
    ]
  });
}

/**
 * Create a self-check box with checkboxes
 * @param {array} items - Array of strings for checkbox items
 * @param {object} opts - Options: title, bgColor
 */
function selfCheckBox(items, opts = {}) {
  const boxTitle = opts.title || "âœ“ Self-Check: Review Your Answers";
  const bgColor = opts.bgColor || THEME.primaryLight;
  
  const checkboxParagraphs = items.map((item, index) => 
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: index === 0 ? 0 : 40 },
      children: [
        new TextRun({ text: "â˜ ", font: FONT, size: SIZE.tableBody }),
        new TextRun({ text: item, font: FONT, size: SIZE.tableBody })
      ]
    })
  );
  
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    columnWidths: [PAGE.contentWidth],
    rows: [
      new TableRow({
        children: [
          new TableCell({
            borders,
            width: { size: PAGE.contentWidth, type: WidthType.DXA },
            shading: { fill: bgColor, type: ShadingType.CLEAR },
            margins: { top: 80, bottom: 80, left: 150, right: 150 },
            children: [
              new Paragraph({
                alignment: AlignmentType.CENTER,
                spacing: { after: 60 },
                children: [
                  new TextRun({
                    text: boxTitle,
                    font: FONT,
                    size: SIZE.sectionHeader,
                    bold: true,
                    color: THEME.primary
                  })
                ]
              }),
              ...checkboxParagraphs
            ]
          })
        ]
      })
    ]
  });
}

/**
 * Create a tip/callout box
 * @param {string} tipText - The tip content
 * @param {object} opts - Options: icon, label, bgColor, textColor
 */
function tipBox(tipText, opts = {}) {
  const icon = opts.icon || "ðŸ’¡";
  const label = opts.label || "Tip:";
  const bgColor = opts.bgColor || COLOR.tipBg;
  const textColor = opts.textColor || COLOR.success;
  
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    columnWidths: [PAGE.contentWidth],
    rows: [
      new TableRow({
        children: [
          new TableCell({
            borders,
            width: { size: PAGE.contentWidth, type: WidthType.DXA },
            shading: { fill: bgColor, type: ShadingType.CLEAR },
            margins: { top: 60, bottom: 60, left: 150, right: 150 },
            children: [
              new Paragraph({
                children: [
                  new TextRun({ text: `${icon} ${label} `, font: FONT, size: SIZE.tableBody, bold: true, color: textColor }),
                  new TextRun({ text: tipText, font: FONT, size: SIZE.tableBody, italics: true, color: COLOR.lightHelper })
                ]
              })
            ]
          })
        ]
      })
    ]
  });
}

/**
 * Create a warning box
 * @param {string} warningText - The warning content
 */
function warningBox(warningText) {
  return tipBox(warningText, {
    icon: "âš ï¸",
    label: "Warning:",
    bgColor: COLOR.warningBg,
    textColor: COLOR.error
  });
}

/**
 * Create a connection box (ties to previous lesson)
 * @param {string} connectionText - The connection content
 */
function connectionBox(connectionText) {
  return tipBox(connectionText, {
    icon: "ðŸ”—",
    label: "Connection:",
    bgColor: COLOR.connectionBg,
    textColor: COLOR.success
  });
}

/**
 * Create candidates list line
 * @param {array} candidates - Array of candidate names
 * @param {string} role - The job role
 */
function candidatesList(candidates, role) {
  return [
    new Paragraph({
      spacing: { after: 40 },
      children: [
        new TextRun({ text: "The Candidates ", font: FONT, size: SIZE.body, bold: true, color: THEME.primary }),
        new TextRun({ text: `(All applying for ${role})`, font: FONT, size: SIZE.tableBody, italics: true, color: COLOR.helperText })
      ]
    }),
    new Paragraph({
      spacing: { after: SPACING.afterNameLine },
      children: [
        new TextRun({ text: "â€¢ " + candidates.join("     â€¢ "), font: FONT, size: SIZE.body, bold: true })
      ]
    })
  ];
}

/**
 * Create a standard evaluation table
 * @param {object} config - { candidates, criteria, questions }
 */
function evaluationTable(config) {
  const { candidates, criteria, questions } = config;
  
  // Calculate column widths
  const nameWidth = 1400;
  const criteriaWidth = Math.floor((PAGE.contentWidth - nameWidth - 2700) / criteria.length);
  const notesWidth = 2700;
  
  // Header row
  const headerCells = [
    cell("Candidate", { header: true, width: nameWidth, align: AlignmentType.CENTER, fontSize: SIZE.tableHeader }),
    ...criteria.map(c => cell(c, { header: true, width: criteriaWidth, align: AlignmentType.CENTER, fontSize: SIZE.tableHeader })),
    cell("Notes", { header: true, width: notesWidth, align: AlignmentType.CENTER, fontSize: SIZE.tableHeader })
  ];
  
  const rows = [new TableRow({ children: headerCells })];
  
  // Question sections with candidate rows
  questions.forEach((question, qIndex) => {
    // Question section header
    const qBg = qIndex % 2 === 0 ? COLOR.question1Bg : COLOR.question2Bg;
    const qColor = qIndex % 2 === 0 ? COLOR.question1Text : COLOR.question2Text;
    
    rows.push(new TableRow({
      children: [
        new TableCell({
          borders,
          columnSpan: criteria.length + 2,
          width: { size: PAGE.contentWidth, type: WidthType.DXA },
          shading: { fill: qBg, type: ShadingType.CLEAR },
          margins: TABLE.cellMargins,
          children: [
            new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [
                new TextRun({
                  text: `Q${qIndex + 1}: "${question.text}"${question.timestamp ? ` (${question.timestamp})` : ""}`,
                  font: FONT,
                  size: SIZE.tableBody,
                  bold: true,
                  color: qColor
                })
              ]
            })
          ]
        })
      ]
    }));
    
    // Candidate rows
    candidates.forEach((candidate, cIndex) => {
      const rowShade = cIndex % 2 === 1 ? COLOR.altRow : null;
      rows.push(new TableRow({
        children: [
          cell(candidate, { width: nameWidth, bold: true, shade: rowShade }),
          ...criteria.map(() => cell("", { width: criteriaWidth, align: AlignmentType.CENTER, shade: rowShade })),
          cell("", { width: notesWidth, shade: rowShade })
        ]
      }));
    });
  });
  
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    columnWidths: [nameWidth, ...criteria.map(() => criteriaWidth), notesWidth],
    rows: rows
  });
}

/**
 * Create a scaffolded prompt with label and fill line
 * @param {string} label - The prompt label (bold)
 * @param {string} hint - Optional hint text (italic, gray)
 * @param {object} opts - Options: labelColor
 */
function scaffoldedPrompt(label, hint = "", opts = {}) {
  const labelColor = opts.labelColor || THEME.primary;
  
  const children = [
    new TextRun({ text: label, font: FONT, size: SIZE.body, bold: true, color: labelColor })
  ];
  
  if (hint) {
    children.push(new TextRun({ text: ` ${hint}`, font: FONT, size: SIZE.helper, italics: true, color: COLOR.helperText }));
  }
  
  return [
    new Paragraph({ spacing: { before: 80, after: 40 }, children }),
    fillLine()
  ];
}

// ============================================================================
// HEADER/FOOTER FUNCTIONS
// ============================================================================

/**
 * Create a standard page header with document name and page numbers
 * @param {string} docName - Document name to display
 */
function createHeader(docName) {
  return new Header({
    children: [
      new Paragraph({
        alignment: AlignmentType.RIGHT,
        children: [
          new TextRun({ text: `${docName}  |  Page `, font: FONT, size: SIZE.pageNumber, color: COLOR.helperText }),
          new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: SIZE.pageNumber, color: COLOR.helperText }),
          new TextRun({ text: " of ", font: FONT, size: SIZE.pageNumber, color: COLOR.helperText }),
          new TextRun({ children: [PageNumber.TOTAL_PAGES], font: FONT, size: SIZE.pageNumber, color: COLOR.helperText })
        ]
      })
    ]
  });
}

// ============================================================================
// DOCUMENT GENERATOR
// ============================================================================

/**
 * Create a complete document
 * @param {array} content - Array of document elements (paragraphs, tables, etc.)
 * @param {object} opts - Options: headerName, useHeader
 */
function createDocument(content, opts = {}) {
  const sectionOpts = {
    page: {
      size: { width: PAGE.width, height: PAGE.height },
      margin: opts.useHeader 
        ? { ...PAGE.margins, top: 900 }
        : PAGE.margins
    }
  };
  
  if (opts.useHeader && opts.headerName) {
    sectionOpts.headers = { default: createHeader(opts.headerName) };
  }
  
  return new Document({
    styles: {
      default: {
        document: {
          run: { font: FONT, size: SIZE.body }
        }
      }
    },
    sections: [{
      properties: sectionOpts,
      children: content
    }]
  });
}

/**
 * Save document to file
 * @param {Document} doc - The document object
 * @param {string} filepath - Output file path
 */
async function saveDocument(doc, filepath) {
  try {
    const buffer = await Packer.toBuffer(doc);
    fs.writeFileSync(filepath, buffer);
    console.log(`âœ… Document saved: ${filepath}`);
    return true;
  } catch (err) {
    console.error(`âŒ Error saving document: ${err.message}`);
    return false;
  }
}

// ============================================================================
// EXPORTS
// ============================================================================

module.exports = {
  // Constants
  FONT,
  PAGE,
  SIZE,
  SPACING,
  COLOR,
  THEME,
  THEMES,
  FRAMEWORK,
  TABLE,
  borders,
  
  // Utility functions
  setTheme,
  getBorders,
  inlineBlank,
  
  // Core helper functions
  cell,
  cellMulti,
  para,
  paraMulti,
  fillLine,
  sectionHeader,
  title,
  subtitle,
  videoLink,
  nameDateLine,
  jobSelectionLine,
  pageBreak,
  numberedQuestion,
  
  // Complex components
  infoBox,
  questionHeader,
  selfCheckBox,
  tipBox,
  warningBox,
  connectionBox,
  candidatesList,
  evaluationTable,
  scaffoldedPrompt,
  
  // Document functions
  createHeader,
  createDocument,
  saveDocument
};
