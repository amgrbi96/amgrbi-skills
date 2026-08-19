---
name: parse-docs
description: 'Routes document parsing to the right tool — pdf-to-markdown for fast Markdown, pymupdf-pdf for local layout/tables, liteparse for multi-format OCR/tables, or mineru for cloud VLM accuracy. Three modes: single document (decision tree), folder batch (per-file routing + resume), or all-methods (every applicable tool per document). Use this skill before parsing any document (PDF, DOCX, PPTX, XLSX, images) — it checks which tools are installed and routes to the best fit. Use when the user mentions parsing, extracting text, converting a document, OCR, tables, drug dosing data, or batch processing — even casually ("grab the text", "read this", "pull content from").'
---

# Parse Docs — Document Router

Routes parsing jobs to one of four installed tools. Pick a mode, then follow its section.

| Mode | What it does | How |
|---|---|---|
| **Single** (default) | Route one document via the decision tree | documented commands below |
| **Folder** | Route each file in a directory independently; resume-safe batch | `scripts/parse_folder.py --mode folder` |
| **All-methods** | Run every applicable tool on each document | `scripts/parse_folder.py --mode all` |

Folder and all-methods use the orchestration script because the per-document output layout (`output/<doc>/<tool>/`) and per-file routing can't be expressed with the tools' native flags alone.

## The Four Tools

| | pdf-to-markdown | pymupdf-pdf | liteparse | mineru |
|---|---|---|---|---|
| **Binary** | `$SKILL_DIR/../pdf-to-markdown/bin/pdf-to-markdown` | `$SKILL_DIR/../pymupdf-pdf/scripts/pymupdf_parse.py` | `lit` (global CLI) | `$SKILL_DIR/../mineru/scripts/mineru_v2.py` |
| **Formats** | PDF only | PDF only | PDF, DOCX/ODT/RTF, PPTX/ODP, XLSX/ODS/CSV, jpg/png/gif/bmp/tiff/webp/svg | PDF, DOCX, PPTX, jpg/jpeg/png **only** |
| **Output** | Structured Markdown | Markdown / JSON / images / tables | Text/Markdown/JSON + bounding boxes | Markdown + images + metadata |
| **Speed** | ⚡ Fastest (~0.009s/pg) | ⚡ Fast (local) | 🐢 ~0.03s/pg text-layer; OCR adds ~0.3s/pg | 🐢 Slowest (cloud round-trip) |
| **Tables** | HTML tables, columns preserved | Native `find_tables()` — bbox + rows | Preserves cell-to-value mappings | Best (VLM) |
| **Formulas** | None | None | None | LaTeX recognition |
| **OCR** | None | None | Tesseract.js (built-in) | Cloud VLM (best) |
| **Cost** | Free ≤1000 docs/mo | Free (local) | Free (local) | Free 1000 pages/day **per token** (poolable) |
| **Needs** | curl/wget + network (first run) | PyMuPDF installed | Node + `lit` + LibreOffice (Office) | Internet + token + Python 3.10+ + `requests` |

Set `$SKILL_DIR` to the absolute path of **this** skill's directory (the one containing this SKILL.md). All four sibling skills resolve as `$SKILL_DIR/../<name>/`.

## Prerequisites — install check

Before routing, confirm each tool the job might reach is present. Run these checks; install whatever is missing. A missing tool is **not** an error — route to an installed alternative, and tell the user what was skipped and why.

```bash
# pdf-to-markdown — full pre-flight (platform, curl/wget, tar, install state)
"$SKILL_DIR/../pdf-to-markdown/bin/check-env" >/dev/null 2>&1 \
  && echo "pdf-to-markdown: ok" \
  || echo "pdf-to-markdown: MISSING (run ../pdf-to-markdown/bin/check-env for details)"

# pymupdf-pdf — script present + PyMuPDF importable
test -f "$SKILL_DIR/../pymupdf-pdf/scripts/pymupdf_parse.py" \
  && python3 -c "import pymupdf" 2>/dev/null \
  && echo "pymupdf-pdf: ok" \
  || echo "pymupdf-pdf: MISSING (script or PyMuPDF)"

# liteparse — the `lit` CLI on PATH (`lit --version` is unreliable; this is the right check)
command -v lit >/dev/null 2>&1 \
  && echo "liteparse: ok" \
  || echo "liteparse: MISSING"

# mineru — script + Python 3.10+ + a token from ANY source (env pool, single env, or tokens.txt)
test -f "$SKILL_DIR/../mineru/scripts/mineru_v2.py" \
  && python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" \
  && { test -n "$MINERU_TOKEN$MINERU_TOKENS" || test -f "$SKILL_DIR/../mineru/tokens.txt"; } \
  && echo "mineru: ok" \
  || echo "mineru: MISSING (script, Python 3.10+, or no token in MINERU_TOKEN/MINERU_TOKENS/tokens.txt)"
```

For a definitive mineru check on real inputs, use its offline dry run (no network, no `requests` needed):

```bash
python3 "$SKILL_DIR/../mineru/scripts/mineru_v2.py" --file INPUT.pdf --output ./output/ --dry-run
```

### Installing a missing tool

Every tool below is an agent skill published on [skills.sh](https://skills.sh). Install the whole set, or any one, with `npx skills add`:

```bash
# All four parsers + this router at once
npx skills add amgrbi96/amgrbi-skills

# Or install one at a time by subpath
npx skills add amgrbi96/amgrbi-skills/skills/pdf-to-markdown
npx skills add amgrbi96/amgrbi-skills/skills/pymupdf-pdf
npx skills add amgrbi96/amgrbi-skills/skills/liteparse
npx skills add amgrbi96/amgrbi-skills/skills/mineru
```

Per-tool setup after install:

| Tool | Extra step |
|---|---|
| `pdf-to-markdown` | None usually — the wrapper self-installs on first run; `bin/check-env --install` pre-downloads (arm64 Linux/macOS only; Intel Macs unsupported) |
| `pymupdf-pdf` | `pip install "pymupdf>=1.23"` (`pymupdf4llm` recommended — better Markdown engine + layout addon; see its `references/pymupdf-notes.md`) |
| `liteparse` | `npm i -g @llamaindex/liteparse`; `brew install --cask libreoffice` (Office docs) |
| `mineru` | Token from https://mineru.net/user-center/api-token into `MINERU_TOKEN`, `MINERU_TOKENS` (pool), or `mineru/tokens.txt`; `pip install requests`; Python 3.10+ — verify offline with `--dry-run`; `--check-token` validates the pool, `--probe` compares models on a sample |

## Mode 1 — Single document (default)

Walk the decision tree top to bottom; first match wins. Then run the tool directly with the commands under "Running the chosen tool".

### 1. Non-PDF files → liteparse or mineru

```
Extension is .docx, .pptx, .jpg, .jpeg, .png
→ liteparse (local, fast enough) — mineru if formulas or highest accuracy matter

Extension is .xlsx, .odt, .rtf, .csv, .tiff, .gif, .webp, …
→ liteparse ONLY (mineru rejects these extensions in pre-flight)
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
→ mineru (its default model is already vlm — no flag needed)
```

### 5. Need local layout detection (tables/images/headers as boxes) → pymupdf-pdf

```
User wants bounding boxes, block-level layout, or to crop table/figure regions
→ pymupdf-pdf layout addon (pymupdf.layout — local, GNN-based, Python API;
  the parse script itself does not emit boxes — see the pymupdf-pdf SKILL.md)
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
→ liteparse --format json (text + per-item bboxes + OCR confidence)
→ pymupdf-pdf --format json (plain per-page text JSON — NOT boxes;
  for layout boxes use the pymupdf.layout addon API)
```

### 8. User explicitly wants Markdown, fast → pdf-to-markdown

```
"Convert to markdown", "just need the text", large doc, speed matters
→ pdf-to-markdown (fastest)
```

### 9. Batch processing many files → Folder mode (below)

```
Folder of documents to parse
→ Mode 2 (one tool per file) or Mode 3 (every tool per file)
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

### Running the chosen tool

#### pdf-to-markdown

```bash
# Single file
"$SKILL_DIR/../pdf-to-markdown/bin/pdf-to-markdown" INPUT.pdf OUTPUT.md

# With images
"$SKILL_DIR/../pdf-to-markdown/bin/pdf-to-markdown" --enable-image-export INPUT.pdf OUTPUT.md

# Batch (native — converts every file in the dir in parallel, no extension filter)
"$SKILL_DIR/../pdf-to-markdown/bin/pdf-to-markdown" INPUT_DIR/ OUTPUT_DIR/
```

Always verify: `test -s OUTPUT.md || echo "empty — likely scanned; reroute to mineru/liteparse"`.

#### pymupdf-pdf

```bash
# Validate first (no output written)
python3 "$SKILL_DIR/../pymupdf-pdf/scripts/pymupdf_parse.py" INPUT.pdf --dry-run

# Single PDF → Markdown (default)
python3 "$SKILL_DIR/../pymupdf-pdf/scripts/pymupdf_parse.py" INPUT.pdf --format md --outroot ./output

# JSON / images + tables
python3 "$SKILL_DIR/../pymupdf-pdf/scripts/pymupdf_parse.py" INPUT.pdf --format json --outroot ./output
python3 "$SKILL_DIR/../pymupdf-pdf/scripts/pymupdf_parse.py" INPUT.pdf --images --tables --outroot ./output

# Batch (native — skips docs whose output folder already exists)
python3 "$SKILL_DIR/../pymupdf-pdf/scripts/pymupdf_parse.py" --dir INPUT_DIR/ --outroot ./output --tables
```

Output lands in `./output/<pdf-stem>/` (`output.md`, `output.json`, `images/`, `tables.json`). Layout boxes are a separate Python API — see the pymupdf-pdf SKILL.md.

#### liteparse

```bash
# Single file → text
lit parse INPUT.pdf -o OUTPUT.txt

# Markdown / JSON with bounding boxes
lit parse INPUT.pdf --format markdown -o OUTPUT.md
lit parse INPUT.pdf --format json -o OUTPUT.json

# Specific pages / image OCR
lit parse INPUT.pdf --target-pages "1-5,10,15-20" -o OUTPUT.txt
lit parse INPUT.jpg -o OUTPUT.txt

# Batch (native — ⚠ same-stem files overwrite each other)
lit batch-parse INPUT_DIR/ OUTPUT_DIR/ --extension .pdf
```

#### mineru

```bash
# 1. ALWAYS validate first — offline, no deps, checks files + token pool
python3 "$SKILL_DIR/../mineru/scripts/mineru_v2.py" --file INPUT.pdf --output ./output/ --dry-run

# 2. Single file (default model is vlm — slowest, most accurate)
python3 "$SKILL_DIR/../mineru/scripts/mineru_v2.py" --file INPUT.pdf --output ./output/

# Long documents (>200 pages) — page ranges
python3 "$SKILL_DIR/../mineru/scripts/mineru_v2.py" --file BIG.pdf --output ./output/ --pages 1-200

# Faster model for standard docs
python3 "$SKILL_DIR/../mineru/scripts/mineru_v2.py" --file INPUT.pdf --output ./output/ --model pipeline

# Batch with resume (native)
python3 "$SKILL_DIR/../mineru/scripts/mineru_v2.py" --dir INPUT_DIR/ --output ./output/ --workers 10 --resume
```

Tokens: `--token`, `MINERU_TOKENS` (comma pool), `MINERU_TOKEN`, or `mineru/tokens.txt` — all sources combine. Limits: 200 MB / 200 pages per file, 1000 pages/day per token (3 tokens ≈ 3000 pages/day). Output: `output/<stem>/<stem>.md` + `images/`. Exit 1 on any failure.

## Mode 2 — Folder (batch with per-file routing)

One run over a directory: each file is typed and routed independently (a `.docx` and a `.pdf` in the same folder go to different tools), outputs land per document, and re-runs skip finished work.

```bash
# Plan first — no files touched
python3 "$SKILL_DIR/scripts/parse_folder.py" INPUT_DIR --output ./output --mode folder --dry-run

# Run (speed: PDFs → pdf-to-markdown, everything else → liteparse)
python3 "$SKILL_DIR/scripts/parse_folder.py" INPUT_DIR --output ./output --mode folder

# Run (accuracy: mineru-first for its formats — requires --mineru + tokens)
python3 "$SKILL_DIR/scripts/parse_folder.py" INPUT_DIR --output ./output --mode folder --prefer accuracy --mineru
```

Behavior:

- **Routing**: `.pdf` → pdf-to-markdown (speed) or mineru (accuracy); `.docx/.pptx/.jpg/.jpeg/.png` → liteparse (speed) or mineru (accuracy); liteparse-only formats (`.xlsx/.odt/.tiff/…`) → liteparse; anything else is listed as unroutable.
- **Missing tools** are skipped with a note; files route to what's installed.
- **Scanned-PDF fallback**: if pdf-to-markdown produces empty output (scanned PDF, exit 0 + ~2 bytes), the file is automatically re-run through liteparse OCR.
- **Resume**: re-running skips any doc+tool whose output already exists (see table below). mineru quota is never re-spent.
- **mineru**: only runs with `--mineru` AND tokens configured; the script prints the quota cost (file count, counted PDF pages, tokens × 1000 pages/day) before parsing.

Output layout — one dir per document, one subdir per tool:

```
output/
├── report.pdf/pdf-to-markdown/report.md
├── scan.pdf/liteparse/scan.md          # fell back from pdf-to-markdown
└── notes.docx/liteparse/notes.md
```

## Mode 3 — All-methods (every applicable tool per document)

Runs **all** installed, format-compatible tools on each document — for comparing parsers or when you want the best of each.

```bash
# Plan + quota cost first (offline; tells you what mineru would spend)
python3 "$SKILL_DIR/scripts/parse_folder.py" INPUT_DIR --output ./output --mode all --mineru --dry-run

# Run — local tools always; mineru included only with --mineru + tokens
python3 "$SKILL_DIR/scripts/parse_folder.py" INPUT_DIR --output ./output --mode all --mineru
```

Output layout — each tool's FULL native output under the document name:

```
output/
├── report.pdf/
│   ├── pdf-to-markdown/report.md
│   ├── pymupdf/report/output.md
│   ├── liteparse/report.md
│   └── mineru/report/           # <stem>.md + images/ (cloud)
├── notes.docx/
│   ├── liteparse/notes.md
│   └── mineru/notes/            # only with --mineru
└── data.xlsx/liteparse/data.md  # tools that can't handle the format are skipped + noted
```

Rules:

- **Format gating**: PDFs get all four tools; `.docx/.pptx/.jpg/.jpeg/.png` get liteparse + mineru; liteparse-only formats get liteparse. Inapplicable tools are skipped and listed — never errors.
- **Cost gating**: local tools always run; mineru requires `--mineru` AND tokens, validated offline via `mineru --dry-run` first. Tell the user the printed quota cost before running in bulk; for >500 counted pages, confirm first.
- **Empty outputs are diagnosed, not hidden**: pdf-to-markdown returning ~2 bytes (scanned PDF) is recorded in a `.scanned-skip` marker so re-runs skip it instead of failing forever.
- **Resume**: identical to folder mode — existing outputs are skipped.

For very large mineru-heavy batches (>20 cloud files), prefer running the mineru skill directly with `--dir --workers 10 --resume` (parallel workers, flat `output/<stem>/` layout instead of per-doc).

## Resume reference (what "already done" means per tool)

| Tool | Native flag | Orchestrator skip condition |
|---|---|---|
| pdf-to-markdown | none (batch redoes everything) | `<doc>/pdf-to-markdown/<stem>.md` exists and >10 bytes, or `.scanned-skip` marker |
| pymupdf-pdf | native batch skip (`--dir` skips existing output folders) | `<doc>/pymupdf/<stem>/output.md` exists |
| liteparse | none (⚠ `batch-parse` overwrites same stems) | `<doc>/liteparse/<stem>.md` exists and non-empty |
| mineru | `--resume` + always idempotent (existing `<stem>/` dir is skipped, quota-safe) | `<doc>/mineru/<stem>/` dir exists |

## Out of Scope

This skill handles **content extraction** only. For PDF manipulation, use the appropriate skill:

- **Generate PDFs from HTML** → `pdf-tools` skill (Puppeteer/Playwright)
- **Modify, merge, split PDFs** → `pdf-tools` skill (pdf-lib)
- **Fill PDF forms** → `pdf-tools` skill
- **Encrypt/sign PDFs** → `pdf-tools` skill (qpdf, @signpdf)

## Workflow

1. **Pick the mode** — one document → Single; a folder to parse once → Folder; compare/extract with every tool → All-methods
2. **Identify the input** — check extension, size, page count; for folders, run the orchestrator's `--dry-run`
3. **Apply routing** — decision tree (Single) or the script's type table (Folder/All)
4. **Run** — execute the command; for mineru in bulk, relay the quota cost first
5. **Verify** — check exit code and output size (tiny output = scanned/failure; the orchestrator flags these)
6. **Report** — where the output is, which tool(s) ran, what was skipped and why

## Speed Reference

Benchmarked on a psychiatry document collection:

| Document type | pdf-to-markdown | pymupdf-pdf | liteparse | mineru |
|---|---|---|---|---|
| Small PDF (<50p) | 1-2s | 1-2s | 5-15s | 10-30s |
| Medium PDF (~200p) | 1-2s | 2-4s | 7-20s | 30-90s |
| Large PDF (~1000p) | 10-12s | 8-15s | 13-30s | 2-5 min |
| Image (OCR) | N/A | N/A | 15-40s | 15-40s |
| Batch (13 files) | 5s | 8-15s | 830s | 3-8 min |

liteparse timings assume OCR; text-layer extraction alone is far faster (`--no-ocr`).
