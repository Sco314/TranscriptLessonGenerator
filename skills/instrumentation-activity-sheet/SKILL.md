---
name: instrumentation-activity-sheet
description: "Create student activity sheets for high school technical/vocational courses (Introduction to Instrumentation, process control, NAPTA curriculum). Triggers include: requests for student worksheets, activity packets, evidence-of-learning handouts, or any printable classwork materials based on textbook chapters or slide decks. Use when the user uploads a textbook PDF and/or PowerPoint slides and wants structured student-facing materials. Also triggers for requests to make educational content accessible to students with ADHD/learning disabilities, or to align activities to specific learning objectives or Bloom's Taxonomy levels. Do NOT use for quizzes, tests, teacher lesson plans, or non-educational documents."
---

# Instrumentation Activity Sheet Creator

Create accessible, pedagogically-sound student activity sheets for technical courses.

## Overview

This skill produces printable .docx activity packets that:
- Align to chapter learning objectives (NAPTA curriculum standards)
- Support students with ADHD and learning disabilities
- Use varied task types across Bloom's Taxonomy levels
- Segment into ~30-minute independent work sections
- Are highly editable for teacher customization

---

## Workflow

### Step 0: File Verification

Before reading any source materials, verify file sizes:

```bash
ls -la /mnt/user-data/uploads/
```

- PDF textbook: typically 500KB–2MB for a chapter
- PPTX slides: typically 2–5MB (prefer .pptx over .pdf for slides—better image/text extraction)

### Step 1: Content Extraction

**Textbook (PDF):** Usually provided as sanitized document in context. If not, extract with OCR tools.

**Slides (PPTX):** Extract text per slide:

```python
from pptx import Presentation
prs = Presentation("slides.pptx")
for i, slide in enumerate(prs.slides, 1):
    print(f"SLIDE {i}")
    for shape in slide.shapes:
        if hasattr(shape, "text") and shape.text.strip():
            print(shape.text.strip())
```

### Step 2: Identify Learning Objectives

Look for objectives at the beginning of the chapter/slides. Typical format:
- "1.1 Describe..." / "1.2 Explain..." / "1.3 Categorize..."
- Map each objective to source pages/slides for reference hints

### Step 3: Content Mapping

Before writing activities, create a mental map of:
- Which objectives each activity addresses
- Bloom's level for each task (Remember → Analyze)
- Source locations for student hints
- Task type variety within each section

### Step 4: Document Generation

Use docx-js to create the document. Follow the formatting rules below exactly.

---

## Formatting Rules (CRITICAL)

### Typography

| Element | Size | Style | Color |
|---------|------|-------|-------|
| Document title | 14pt | Bold | Black |
| Section H1 | 14pt | Bold | Black |
| Body text / questions | 12pt | Normal | Black |
| Vocabulary terms | 12pt | **Bold** | Black |
| Unit labels in answers (PSI, °F, etc.) | 12pt | Normal | Black |
| Scaffold text / hints | 9pt | *Italic* | #AAAAAA |
| Blanks, dividers, "Show the formula..." | — | — | #AAAAAA |

**Font:** Arial (universally supported)

### What Goes Gray (#AAAAAA)

All guide/scaffold elements:
- Blanks (horizontal rules)
- Slash dividers in tables ( / )
- "Show the formula & your work:"
- "Answer:"
- Hint text (when small italic font alone signals it)

**Student cognitive content stays black 12pt.**

### Blanks and Writing Lines

**Use horizontal rules, NOT underscores:**

```javascript
// ✅ CORRECT - horizontal rule for writing line
new Paragraph({
  border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "AAAAAA" } },
  spacing: { after: 200 }
})

// ❌ WRONG - underscores
new TextRun({ text: "__________" })
```

**Size blanks to expected answer:**
- 5 underscores for numbers
- Longer for terms/phrases
- NOT excessive (10+ underscores for a 2-digit number)

**No underscores inside bordered table cells** (the cell border already defines the space).

### Hints

**Hints go BEFORE the blank** (with the question text or activity header), never after.

```
✅ "The standard pneumatic signal range is [Hint: Slide 23] _________ to _________ PSI."

❌ "The standard pneumatic signal range is _________ to _________ PSI. [Hint: Slide 23]"
```

**Drop the 📖 emoji and "Hint:" label** when smaller italic font alone signals it:

```
✅ Activity 1.3: Operator Safety Role  See Slide 12, p. 8
                                       ↑ 9pt italic gray

❌ Activity 1.3: Operator Safety Role  📖 Hint: See Slide 12, p. 8
```

### Titles and Headers

- **No em dashes in titles** (use colon or remove)
- **Title + hint on same line** when possible
- **Sections use actual H1 heading style** (not just bold text)
- **Every task numbered with actual numbered lists** (not manual "1." text)

```javascript
// Section header with shading
new Paragraph({
  heading: HeadingLevel.HEADING_1,
  shading: { fill: "1E4D6B", type: ShadingType.CLEAR },
  children: [new TextRun({ text: "Section 1: What Is Instrumentation?", color: "FFFFFF" })]
})
```

### Page Layout

- **US Letter:** 12240 × 15840 DXA
- **Margins:** 0.7" all sides (1008 DXA)
- **Content width:** 12240 - 2016 = 10224 DXA

### Page Breaks

**Critical rules:**
- No question splits across pages
- No activity splits across pages
- Use `keepNext` and `keepLines` paragraph properties

```javascript
new Paragraph({
  keepNext: true,
  keepLines: true,
  children: [...]
})
```

### Tables

**Always use DXA widths, not percentages** (percentages break in Google Docs):

```javascript
new Table({
  width: { size: 10224, type: WidthType.DXA },
  columnWidths: [5112, 5112], // Must sum to table width
  rows: [...]
})
```

**Cell setup:**
```javascript
new TableCell({
  width: { size: 5112, type: WidthType.DXA },
  borders: { top: border, bottom: border, left: border, right: border },
  margins: { top: 80, bottom: 80, left: 120, right: 120 },
  shading: { fill: "D5E8F0", type: ShadingType.CLEAR }, // CLEAR not SOLID
  children: [...]
})
```

### Scaffold Indentation

"Show the formula & your work:" should be tabbed to align with question text above:

```
3. Calculate the head pressure at the bottom of a 20-foot tank filled with water.
      Show the formula & your work:      ← indented to align
      _________________________________
      Answer: _________ PSI
```

---

## Content Rules

### Prohibited Elements

| Don't Include | Why |
|---------------|-----|
| Self-check sections | Teacher won't respond to that format |
| "Questions I still have" boxes | Same—no feedback loop |
| True/False questions | False statements encode misinformation |
| Meta-instruction boxes | Adds clutter without value |
| Motivational asides | Keep it clean and direct |
| Redundant activity titles | Merge sub-activities when logical |
| Obvious instructions | "Write your answer on the line" is unnecessary |

### Use Instead

| Instead of T/F | Use |
|----------------|-----|
| "True or False: Flow rate measures total volume." | "Flow rate measures _________ (volume per unit time / total volume)." |

Fill-in-the-blank and sentence completion don't risk encoding wrong information.

### Activity Type Variety

Mix task types within each section to maintain engagement:

- **Definitions:** Fill-in-the-blank with word bank or no bank
- **Matching:** Timeline events, terms to definitions, functions to descriptions
- **Tables:** Compare/contrast (local vs. remote, analog vs. digital)
- **Labeling:** Diagram annotation (with placeholder if image needed)
- **Short answer:** "List 3 reasons why..." / "Explain in your own words..."
- **Scenario-based:** "A blocked-in tank overnight experiences a cold front. What happens to..."
- **Calculation:** With scaffold ("Show the formula & your work:")

**Avoid** long sequences of the same task type (e.g., 10 definitions in a row).

### Bloom's Taxonomy Coverage

Each section should include tasks at multiple levels:

| Level | Example Task |
|-------|--------------|
| Remember | "List the 5 major process variables." |
| Understand | "In your own words, explain why monitoring is important." |
| Apply | "Given this scenario, calculate the head pressure." |
| Analyze | "Compare pneumatic and electronic signals. Why might a plant use both?" |

### Section Structure (~30 min each)

Typical section contains 4–6 activities:
1. Recall/define key terms
2. Matching or categorization
3. Table completion or comparison
4. Short answer or explanation
5. Application or scenario (if appropriate)

---

## Document Structure

### Front Matter

1. **Title page** with student info box:
   ```
   Name: _______________________
   Period: _____  Date: _________
   ```

2. **Learning Objectives** list (numbered, from chapter)

3. **"How to Use This Packet"** brief instructions (optional)

### Sections

Each section:
- H1 header with shading (1E4D6B blue, white text)
- Activities numbered within section (1.1, 1.2... or just 1, 2, 3...)
- Hint references in brackets: `[Slide 12, p. 8]`
- Visual spacing between activities

### Back Matter

- **Answer Key** on final page (removable for teacher reference)
- Page numbers in footer

---

## Images

### Option A: Extract and Insert (Preferred)

Extract images from PPTX:
```python
from pptx import Presentation
from pptx.util import Inches
import os

prs = Presentation("slides.pptx")
for i, slide in enumerate(prs.slides):
    for shape in slide.shapes:
        if shape.shape_type == 13:  # Picture
            image = shape.image
            with open(f"image_{i}.{image.ext}", "wb") as f:
                f.write(image.blob)
```

Then embed in document:
```javascript
new ImageRun({
  data: fs.readFileSync("image.png"),
  transformation: { width: 300, height: 200 },
  type: "png"
})
```

### Option B: Placeholder (Fallback)

If image quality is poor or extraction fails:
```
[IMAGE PLACEHOLDER: Control loop diagram showing sensor → transmitter → controller → final element]
```

---

## Post-Production

### Content-Mapping CSV

After producing the activity sheet, output a CSV for alignment verification:

```csv
Activity,Learning_Objective,Source_Page,Source_Slide,Blooms_Level,Task_Type
1.1,1.1,4,3,Remember,Fill-in-blank
1.2,1.1,5-6,5-7,Understand,Timeline matching
2.1,1.3,8,12,Remember,List
2.2,1.3,9,14,Understand,Table completion
```

This helps the instructor verify coverage.

---

## Example Activity Formats

### Fill-in Definition
```
Activity 1.1: Define Instrumentation
Instrumentation is the _________________ and _________________ used to
_________________, _________________, _________________, and _________________
process variables in industrial settings.
```

### Timeline Matching
```
Activity 1.2: Evolution of Instrumentation  [Slides 5–7, pp. 5–6]
Match each development to its approximate date.

____ Flyball governor invented          A. 1920s
____ Pneumatic controls introduced      B. 1932
____ Nyquist stability theory           C. 1775
____ First process control computer     D. 1940s
____ PID control becomes standard       E. 1958
____ Microprocessor invented            F. 1971
```

### Comparison Table
```
Activity 3.1: Local vs. Remote Instruments  [Slide 18, p. 12]

| Feature          | Local (Field)           | Remote                   |
|------------------|-------------------------|--------------------------|
| Location         | _____________________   | _____________________    |
| Who reads it     | _____________________   | _____________________    |
| Example          | _____________________   | _____________________    |
```

### Calculation with Scaffold
```
3. Calculate the head pressure at the bottom of a 15-foot tank filled with water
   (density = 62.4 lb/ft³).   [p. 14]

      Show the formula & your work:
      _________________________________
      _________________________________

      Answer: _________ PSI
```

### Scenario-Based Application
```
Activity 4.6: Impact on Measurements  [Slides 32–35]

A tank is blocked in overnight. The temperature drops from 80°F to 40°F.

a) What happens to the pressure inside the tank?
   _________________________________________________________________

b) Why does this occur?
   _________________________________________________________________

c) What safety concern might this create?
   _________________________________________________________________
```

---

## Technical Implementation Notes

### docx-js Setup

```javascript
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
        Header, Footer, PageNumber, PageBreak, HeadingLevel, BorderStyle,
        WidthType, ShadingType, AlignmentType, LevelFormat } = require('docx');
```

### Numbering Config

```javascript
numbering: {
  config: [
    {
      reference: "activity-numbers",
      levels: [{
        level: 0,
        format: LevelFormat.DECIMAL,
        text: "%1.",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } }
      }]
    },
    {
      reference: "letters",
      levels: [{
        level: 0,
        format: LevelFormat.LOWER_LETTER,
        text: "%1)",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } }
      }]
    }
  ]
}
```

### Document Styles

```javascript
styles: {
  default: {
    document: { run: { font: "Arial", size: 24 } } // 12pt
  },
  paragraphStyles: [
    {
      id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal",
      quickFormat: true,
      run: { size: 28, bold: true, font: "Arial" }, // 14pt
      paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 0 }
    }
  ]
}
```

### Section Header Pattern

```javascript
function createSectionHeader(title) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    shading: { fill: "1E4D6B", type: ShadingType.CLEAR },
    spacing: { before: 400, after: 200 },
    children: [
      new TextRun({ text: title, bold: true, color: "FFFFFF", size: 28 })
    ]
  });
}
```

### Gray Scaffold Text

```javascript
function grayText(text) {
  return new TextRun({ text, italics: true, size: 18, color: "AAAAAA" }); // 9pt
}
```

### Writing Line (Horizontal Rule)

```javascript
function writingLine() {
  return new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "AAAAAA" } },
    spacing: { before: 100, after: 200 }
  });
}
```

---

## Checklist Before Delivery

- [ ] All learning objectives have at least one activity
- [ ] No section has only one task type
- [ ] Hints reference actual slide/page numbers
- [ ] No T/F questions
- [ ] No self-check or "questions I have" sections
- [ ] Blanks sized appropriately
- [ ] Hints before blanks, not after
- [ ] No em dashes in titles
- [ ] Tables use DXA widths (not percentages)
- [ ] Page breaks don't split activities
- [ ] Answer key on final page
- [ ] Content-mapping CSV generated
