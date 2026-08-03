---
name: parse-docs
description: 'Routes document parsing to the right tool — pdf-to-markdown for fast Markdown, pymupdf-pdf for local layout/tables, liteparse for multi-format OCR/tables, or mineru for cloud VLM accuracy. CRITICAL: always use this skill before attempting to parse any document file (PDF, DOCX, PPTX, XLSX, images). Do not write ad-hoc Python parsing scripts — use one of the four approved tools below. Use when the user mentions parsing, extracting text, converting documents, reading PDFs, OCR, tables, drug dosing data, batch processing, or any file content extraction — even casually ("grab the text", "read this", "pull content from", "what does this file say").'
---

# Parse Docs — Smart Document Router

This skill routes document parsing jobs to one of four installed tools. Pick the first rule in the decision tree that matches — don't substitute a fifth option.

## The Four Tools

| | pdf-to-markdown | pymupdf-pdf | liteparse | mineru |
|---|---|---|---|---|
| **Binary** | `$SKILL_DIR/../pdf-to-markdown/bin/pdf-to-markdown` | `$SKILL_DIR/../pymupdf-pdf/scripts/pymupdf_parse.py` | `lit` (global CLI) | `$SKILL_DIR/../mineru/scripts/mineru_v2.py` |
| **Formats** | PDF only | PDF only | PDF, DOCX, PPTX, XLSX, images | PDF, DOCX, PPTX, images |
| **Output** | Structured Markdown | Markdown / JSON / images / tables | Text or JSON + bounding boxes | Markdown + images + metadata |
| **Speed** | ⚡ Fastest (~0.009s/pg) | ⚡ Fast (local) | 🐢 ~0.030s/pg | 🐢 Slowest (cloud round-trip) |
| **Tables** | Loses column relationships | Rough line-based JSON | Preserves cell-to-value mappings | Best (VLM) |
| **Formulas** | None | None | None | LaTeX recognition |
| **OCR** | None | None | Tesseract.js (built-in) | Cloud VLM (best) |
| **Cost** | Free ≤1000 docs/mo | Free (local) | Free (local) | Free 1000 pg/day priority |
| **Needs** | — | PyMuPDF installed | Node + `lit` + LibreOffice (Office) | Internet + `MINERU_TOKEN` |

Set `$SKILL_DIR` to the absolute path of **this** skill's directory (the one containing this SKILL.md). All four sibling skills resolve as `$SKILL_DIR/../<name>/`.

## Decision Tree

Walk top to bottom. First match wins.

### 1. Non-PDF files → liteparse or mineru

```
Extension is .docx, .pptx, .xlsx, .doc, .odt, .jpg, .png, .tiff, etc.
→ liteparse (local, fast enough)
→ mineru if formulas or highest accuracy matter (cloud)
```

### 2. Scanned PDF / image / OCR needed → mineru or liteparse

```
File is scanned, a photo, screenshot, or user says "OCR"
→ mineru for best accuracy (VLM OCR, cloud)
→ liteparse as local fallback (Tesseract.js)
```

### 3. Formulas / math / LaTeX → mineru only

```
Document has equations, chemical formulas, math notation
→ mineru (only tool with LaTeX formula recognition)
```

### 4. Complex layout / multi-column / mixed text+figures → mineru

```
Multi-column academic papers, posters, mixed content
→ mineru with --model vlm
```

### 5. Need local layout detection (tables/images/headers as boxes) → pymupdf-pdf

```
User wants bounding boxes, block-level layout, or to crop table/figure regions
→ pymupdf-pdf (uses pymupdf.layout addon — local, GNN-based)
```

### 6. Need accurate table data (drug doses, criteria, structured tables) → liteparse or mineru

```
Tables where cell-to-value mapping matters (clinical dosing, criteria lists)
→ liteparse (local, preserves mappings)
→ mineru if tables are complex/merged (cloud, VLM)
```

### 7. User explicitly wants JSON / bounding boxes → liteparse or pymupdf-pdf

```
"JSON output", "coordinates", "spatial extraction"
→ liteparse --format json (text + bboxes)
→ pymupdf-pdf --format json (layout boxes via pymupdf.layout)
```

### 8. User explicitly wants Markdown, fast → pdf-to-markdown

```
"Convert to markdown", "just need the text", large doc, speed matters
→ pdf-to-markdown (fastest)
```

### 9. Batch processing many PDFs → pdf-to-markdown or mineru

```
Folder of many PDFs, speed matters, no tables/formulas
→ pdf-to-markdown (150× faster in batch)

Folder with tables/dosing/formulas, accuracy matters
→ mineru with --workers 10 --resume (cloud, slower but accurate)
→ Warn: pdf-to-markdown on table-heavy batches will break cell relationships
```

### 10. Hybrid: full text + accurate tables → pdf-to-markdown + liteparse/mineru

```
User needs the whole document AND accurate tables
→ Step 1: pdf-to-markdown for full document (fast, Markdown structure)
→ Step 2: liteparse or mineru on just the table-heavy pages
→ Step 3: replace broken table sections in the Markdown with accurate output
```

### 11. Large PDF, user needs only the gist → pdf-to-markdown

```
Summary, overview, quick extraction from a large PDF
→ pdf-to-markdown (fast), then summarize from the Markdown
```

### 12. Ambiguous → ask one question

```
Can't determine intent from context
→ "Do you need exact tables/formulas (mineru/liteparse), or is fast text enough (pdf-to-markdown)?"
```

## Running the Chosen Tool

Once decided, run directly. Do NOT delegate back to the individual skill — the routing above replaces loading them.

### pdf-to-markdown

```bash
# Single file
"$SKILL_DIR/../pdf-to-markdown/bin/pdf-to-markdown" INPUT.pdf OUTPUT.md

# Batch
"$SKILL_DIR/../pdf-to-markdown/bin/pdf-to-markdown" INPUT_DIR/ OUTPUT_DIR/

# With images
"$SKILL_DIR/../pdf-to-markdown/bin/pdf-to-markdown" --enable-image-export INPUT.pdf OUTPUT.md
```

### pymupdf-pdf

```bash
# Single PDF → Markdown (default)
python3 "$SKILL_DIR/../pymupdf-pdf/scripts/pymupdf_parse.py" INPUT.pdf --format md --outroot ./output

# JSON output
python3 "$SKILL_DIR/../pymupdf-pdf/scripts/pymupdf_parse.py" INPUT.pdf --format json --outroot ./output

# With images + tables
python3 "$SKILL_DIR/../pymupdf-pdf/scripts/pymupdf_parse.py" INPUT.pdf --images --tables --outroot ./output
```

For layout detection (`pymupdf.layout` addon — block-level boxes), see the pymupdf-pdf SKILL.md.

### liteparse

```bash
# Single file → text
lit parse INPUT.pdf -o OUTPUT.txt

# JSON with bounding boxes
lit parse INPUT.pdf --format json -o OUTPUT.json

# Specific pages
lit parse INPUT.pdf --target-pages "1-5,10,15-20" -o OUTPUT.txt

# Image OCR
lit parse INPUT.jpg -o OUTPUT.txt

# Batch
lit batch-parse INPUT_DIR/ OUTPUT_DIR/ --extension .pdf
```

### mineru

```bash
# Single file
python3 "$SKILL_DIR/../mineru/scripts/mineru_v2.py" --file INPUT.pdf --output ./output/

# Batch with resume
python3 "$SKILL_DIR/../mineru/scripts/mineru_v2.py" --dir INPUT_DIR/ --output ./output/ --workers 10 --resume

# Complex layout (VLM, slowest/most accurate)
python3 "$SKILL_DIR/../mineru/scripts/mineru_v2.py" --file INPUT.pdf --output ./output/ --model vlm
```

Requires `MINERU_TOKEN` env var. Limits: 200 MB / 200 pages per file, 1000 pages/day priority.

## Out of Scope

This skill handles **content extraction** only. For PDF manipulation, use the appropriate skill:

- **Generate PDFs from HTML** → `pdf-tools` skill (Puppeteer/Playwright)
- **Modify, merge, split PDFs** → `pdf-tools` skill (pdf-lib)
- **Fill PDF forms** → `pdf-tools` skill
- **Encrypt/sign PDFs** → `pdf-tools` skill (qpdf, @signpdf)

## Workflow

1. **Identify the file(s)** — check extension, size, page count
2. **Determine intent** — what does the user need? (speed vs. accuracy vs. tables vs. formulas)
3. **Apply the decision tree** — pick the tool
4. **Run the tool** — execute the appropriate command
5. **Verify** — check exit code and output size (tiny output may mean extraction failure)
6. **Report** — tell the user where the output is and which tool was used

## Speed Reference

Benchmarked on a psychiatry document collection:

| Document type | pdf-to-markdown | pymupdf-pdf | liteparse | mineru |
|---|---|---|---|---|
| Small PDF (<50p) | 1-2s | 1-2s | 5-15s | 10-30s |
| Medium PDF (~200p) | 1-2s | 2-4s | 7-20s | 30-90s |
| Large PDF (~1000p) | 10-12s | 8-15s | 13-30s | 2-5 min |
| Image (OCR) | N/A | N/A | 15-40s | 15-40s |
| Batch (13 files) | 5s | 8-15s | 830s | 3-8 min |
