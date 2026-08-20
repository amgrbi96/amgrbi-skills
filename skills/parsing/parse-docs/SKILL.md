---
name: parse-docs
description: 'Routes document parsing to the right tool — pdf-to-markdown for fast Markdown, pymupdf-pdf for local layout/tables, liteparse for multi-format OCR/tables, or mineru for cloud VLM accuracy. Three modes: single document (decision tree shortlist, then the user picks), folder batch (per-file routing + resume), or all-methods (every applicable tool per document). Use this skill before parsing any document (PDF, DOCX, PPTX, XLSX, images) — it checks which tools are installed, shortlists the fitting ones, and asks the user to choose, with a quick comparison in each option. Use when the user mentions parsing, extracting text, converting a document, OCR, tables, drug dosing data, or batch processing — even casually ("grab the text", "read this", "pull content from").'
---

# Parse Docs — Document Router

Routes parsing jobs to one of four installed tools. Pick a mode, then follow its section. In Single mode you never pick silently: shortlist the fitting tools, then **let the user decide** — see "Ask, don't assume".

| Mode | What it does | How |
|---|---|---|
| **Single** (default) | Shortlist via decision tree; the user picks the parser | documented commands below |
| **Folder** | Route each file in a directory independently; resume-safe batch | `scripts/parse_folder.py --mode folder` |
| **All-methods** | Run every applicable tool on each document | `scripts/parse_folder.py --mode all` |

Folder and all-methods use the orchestration script because the per-document output layout (`output/<doc>/<tool>/`) and per-file routing can't be expressed with the tools' native flags alone.

## The Four Tools

| | pdf-to-markdown | pymupdf-pdf | liteparse | mineru |
|---|---|---|---|---|
| **Binary** | `$SKILL_DIR/../pdf-to-markdown/bin/pdf-to-markdown` | `$SKILL_DIR/../pymupdf-pdf/scripts/pymupdf_parse.py` | `lit` (global CLI) | `$SKILL_DIR/../mineru/scripts/mineru_v2.py` |
| **Formats** | PDF only | PDF only | PDF, DOCX/ODT/RTF, PPTX/ODP, XLSX/ODS/CSV, jpg/png/gif/bmp/tiff/webp/svg | PDF, DOCX, PPTX, jpg/jpeg/png **only** |
| **Output** | Structured Markdown | Markdown / JSON / images / tables | Text/Markdown/JSON + bounding boxes | Markdown + images + metadata |
| **Speed** | ⚡ Fastest (~0.009s/pg) | ⚡ Fast basic engine; slower with `pymupdf4llm` (auto) | 🐢 ~0.03s/pg text-layer (`--no-ocr`); OCR adds ~0.3s/pg | 🐢 Slowest (cloud round-trip) |
| **Tables** | HTML tables, columns preserved | Native `find_tables()` — bbox + rows (**ruled tables only**) | Preserves cell-to-value mappings | Best (VLM) |
| **Formulas** | None | None | None | LaTeX recognition |
| **OCR** | None | None | Built-in Tesseract (opt-in — gate first) | Cloud VLM (best) |
| **Cost** | Free ≤1000 docs/mo | Free (local) | Free (local) | Free 1000 pages/day **per token** (poolable) |
| **Needs** | curl/wget + network (first run) | PyMuPDF ≥1.23 installed | Node + `lit` (+ LibreOffice for Office, opt-in ~800 MB) | Internet + token + Python 3.10+ + `requests` |

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
npx skills add amgrbi96/amgrbi-skills/skills/parsing/pdf-to-markdown
npx skills add amgrbi96/amgrbi-skills/skills/parsing/pymupdf-pdf
npx skills add amgrbi96/amgrbi-skills/skills/parsing/liteparse
npx skills add amgrbi96/amgrbi-skills/skills/parsing/mineru
```

Per-tool setup after install:

| Tool | Extra step |
|---|---|
| `pdf-to-markdown` | None usually — the wrapper self-installs on first run; `bin/check-env --install` pre-downloads (arm64 Linux/macOS only; Intel Macs unsupported) |
| `pymupdf-pdf` | `pip install "pymupdf>=1.23"` (`pymupdf4llm` recommended — better Markdown engine + layout addon; see its `references/pymupdf-notes.md`) |
| `liteparse` | `npm i -g @llamaindex/liteparse`; LibreOffice (~800 MB) is **opt-in with user approval** and only for Office formats; OCR is off by default (`--no-ocr`) — see the liteparse skill's OCR gate |
| `mineru` | Token from https://mineru.net/user-center/api-token into `MINERU_TOKEN`, `MINERU_TOKENS` (pool), or `mineru/tokens.txt`; `pip install requests`; Python 3.10+ — verify offline with `--dry-run`; `--check-token` validates the pool, `--probe` compares models on a sample |

## Mode 1 — Single document (default)

Use the decision tree to **shortlist** the installed tools that can handle the document and to form a recommendation. If the shortlist has more than one tool, ask the user to choose (next section) — don't decide for them. Then run the chosen tool with the commands under "Running the chosen tool".

### Ask, don't assume — the user picks the parser

When more than one installed, format-compatible tool fits, **ask the user which one to use**, and put a quick comparison inside each option of the question so the choice is self-explanatory. Mark your recommendation (first option, from the tree) but let the user override it. Only skip asking when exactly one tool fits (format lockout — e.g. `.xlsx` → liteparse, formulas → mineru) or the user already named the tool.

One-line comparisons to reuse in option descriptions — drop tools that are inapplicable or uninstalled, and lead with what matters for *this* document (tables, speed, privacy, formulas):

| Option | Description to show in the question |
|---|---|
| **pdf-to-markdown** | Fastest + local. PDF → Markdown with structure; tables as HTML. No OCR, no formulas — text layer only. |
| **pymupdf-pdf** | Local PDF workbench. Markdown/JSON, tables with cell coordinates, image export. Fast; no OCR. |
| **liteparse** | Local, widest formats (DOCX/PPTX/XLSX/images). Cell-accurate tables; OCR opt-in (~0.3s/pg). |
| **mineru** | Cloud VLM, highest accuracy: **best tables** (merged/complex too), formulas → LaTeX, scanned docs. Slowest; needs token + network, spends quota. |

Example question for a text-layer, table-heavy PDF:

> **"Which parser for report.pdf (217 pages, text layer, heavy tables)?"**
> - **mineru** *(Recommended)* — "Best table accuracy (VLM) + formula support; cloud, ~2-5 min, spends ~217 pages of quota."
> - **pdf-to-markdown** — "Fastest, local (~1-2s); tables come out as HTML, fine for reading not for exact cell data."
> - **liteparse** — "Local; cell-accurate tables, but slower than pdf-to-markdown on big PDFs."
> - **pymupdf-pdf** — "Local; tables with coordinates as JSON/MD — good for locating cells, weaker on complex merges."

Tailor the lead phrase to the document (scanned → lead with OCR quality; private data → lead with local vs cloud; huge PDF → lead with speed). If you can't tell what matters, this question is how you find out — the comparisons do the explaining.

### Decision tree (shortlist + recommendation)

Walk top to bottom; a matching rule adds its tools to the shortlist.

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
→ liteparse as local fallback — OCR is opt-in there: gate it first with
  `lit is-complex FILE` (needsOcr: true + textLength: 0), then ask the user
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

### 6. Need accurate table data (drug doses, criteria, structured tables) → mineru or liteparse

```
Tables where cell-to-value mapping matters (clinical dosing, criteria lists)
→ mineru — best table accuracy (VLM; handles merged/complex cells), cloud
→ liteparse — local/private fallback, preserves cell-to-value mappings
```

### 7. User explicitly wants JSON / bounding boxes → liteparse or pymupdf-pdf

```
"JSON output", "coordinates", "spatial extraction"
→ liteparse --format json (text + per-item bboxes + OCR confidence)
→ pymupdf-pdf --format json (plain per-page text JSON — NOT boxes)
→ pymupdf-pdf --tables (tables.json: bbox + rows per table, local — ruled tables only)
→ pymupdf-pdf layout addon (pymupdf.layout — full box classes, Python API)
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

MinerU's dedicated `hybrid` backend (v2.6+) is **self-hosted only** — the cloud API exposes `pipeline | vlm | MinerU-HTML`, so "hybrid" through these skills always means the manual graft above. When step 2 sends mineru part of a large PDF, physically split and submit parts whole: the cloud `--pages`/`page_ranges` path is rejected server-side on some PDFs (see the mineru skill's Long Documents section).

### 11. Large PDF, user needs only the gist → pdf-to-markdown

```
Summary, overview, quick extraction from a large PDF
→ pdf-to-markdown (fast), then summarize from the Markdown
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

OCR is **off by default in this router** — pass `--no-ocr` on text-layer documents (the CLI would otherwise OCR silently and download Tesseract data on first run). Turn OCR on only for images or after the gate (`lit is-complex` → `needsOcr: true` + `textLength: 0`) **and** user approval.

```bash
# Single file → text (text-layer docs — always --no-ocr)
lit parse INPUT.pdf --no-ocr -o OUTPUT.txt

# Markdown / JSON with bounding boxes
lit parse INPUT.pdf --no-ocr --format markdown -o OUTPUT.md
lit parse INPUT.pdf --no-ocr --format json -o OUTPUT.json

# Specific pages
lit parse INPUT.pdf --no-ocr --target-pages "1-5,10,15-20" -o OUTPUT.txt

# Image OCR (no text layer — OCR is the point; first run downloads ~15 MB/language)
lit parse INPUT.jpg -o OUTPUT.txt

# Batch (native — ⚠ same-stem files overwrite each other)
lit batch-parse INPUT_DIR/ OUTPUT_DIR/ --extension .pdf --no-ocr
```

#### mineru

```bash
# 1. ALWAYS validate first — offline, no deps, checks files + token pool
python3 "$SKILL_DIR/../mineru/scripts/mineru_v2.py" --file INPUT.pdf --output ./output/ --dry-run

# 2. Single file (default model is vlm — slowest, most accurate)
python3 "$SKILL_DIR/../mineru/scripts/mineru_v2.py" --file INPUT.pdf --output ./output/

# Long documents (>200 pages) — physically split first (pymupdf pdf_ops.py or any
# splitter), then parse the parts dir. Cloud --pages ranges are rejected server-side
# on some PDFs (-60010), ~6 min burned per failed range:
python3 "$SKILL_DIR/../pymupdf-pdf/scripts/pdf_ops.py" split BIG.pdf --outroot ./parts/ --ranges 1-200,201-400
python3 "$SKILL_DIR/../mineru/scripts/mineru_v2.py" --dir ./parts/ --output ./output/ --resume

# Faster model for standard docs
python3 "$SKILL_DIR/../mineru/scripts/mineru_v2.py" --file INPUT.pdf --output ./output/ --model pipeline

# Batch with resume (native)
python3 "$SKILL_DIR/../mineru/scripts/mineru_v2.py" --dir INPUT_DIR/ --output ./output/ --workers 10 --resume

# Token health (read-only API check, zero page spend — no --file/--output needed)
python3 "$SKILL_DIR/../mineru/scripts/mineru_v2.py" --check-token

# Undecided on model? Sample-parse pages with BOTH models (~6 pages), or point
# it at known-hard pages, or probe a single model:
python3 "$SKILL_DIR/../mineru/scripts/mineru_v2.py" --file INPUT.pdf --output ./probe/ --probe
python3 "$SKILL_DIR/../mineru/scripts/mineru_v2.py" --file INPUT.pdf --output ./probe/ --probe --probe-pages "85-87,203"
python3 "$SKILL_DIR/../mineru/scripts/mineru_v2.py" --file INPUT.pdf --output ./probe/ --probe --model MinerU-HTML
```

Tokens: `--token`, `MINERU_TOKENS` (comma pool), `MINERU_TOKEN`, or `mineru/tokens.txt` — all sources combine. Limits: 200 MB / 200 pages per file, 1000 pages/day per token (3 tokens ≈ 3000 pages/day). The script warns before wasting quota (text-layer PDFs, >200-page files, over-budget batches) and never re-parses an existing output dir. Output: `output/<stem>/<stem>.md` + `images/` (+ `.docx/.html/.latex` with `--extra-formats`); with `--pages` (fallback — rejected by some PDFs server-side), one folder per range (`output/<stem>-1-200/`). Probe output: `output/<stem>-probe/<model>/<stem>/<stem>.md`. Exit 1 on any failure.

## Mode 2 — Folder (batch with per-file routing)

One run over a directory: each file is typed and routed independently (a `.docx` and a `.pdf` in the same folder go to different tools), outputs land per document, and re-runs skip finished work.

Two routing preferences exist — **ask the user which one** before running: *speed* (local tools only, free, fastest) vs *accuracy* (mineru-first for its formats; needs `--mineru` + tokens and spends quota — relay the printed cost).

```bash
# Plan first — no files touched
python3 "$SKILL_DIR/scripts/parse_folder.py" INPUT_DIR --output ./output --mode folder --dry-run

# Run (speed: PDFs → pdf-to-markdown, everything else → liteparse)
python3 "$SKILL_DIR/scripts/parse_folder.py" INPUT_DIR --output ./output --mode folder
# add --format txt for liteparse plain-text output, --no-ocr to forbid OCR everywhere

# Run (accuracy: mineru-first for its formats — requires --mineru + tokens)
python3 "$SKILL_DIR/scripts/parse_folder.py" INPUT_DIR --output ./output --mode folder --prefer accuracy --mineru
```

Behavior:

- **Routing**: `.pdf` → pdf-to-markdown (speed) or mineru (accuracy); `.docx/.pptx/.jpg/.jpeg/.png` → liteparse (speed) or mineru (accuracy); liteparse-only formats (`.xlsx/.odt/.tiff/…`) → liteparse; anything else is listed as unroutable.
- **Missing tools** are skipped with a note; files route to what's installed.
- **OCR policy** (mirrors liteparse): text-layer documents run with `--no-ocr`; OCR fires only for image files and the scanned-PDF fallback below. `--no-ocr` disables both everywhere.
- **Scanned-PDF fallback**: if pdf-to-markdown produces empty output (scanned PDF, exit 0 + ~2 bytes), the file is automatically re-run through liteparse **with OCR** — that empty result is the liteparse skill's OCR-gate "needed" signal. First OCR run per language downloads ~15 MB of Tesseract data.
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

This skill handles **content extraction** only. For everything else:

- **Merge, split, rotate, crop, delete pages · render to PNG · metadata/TOC · encrypt/decrypt · search** → `pymupdf-pdf` skill (`pdf_ops.py` — local, one dependency)
- **Annotations, form filling, redaction** → `pymupdf-pdf` skill (recipe references)
- **Generate PDFs from HTML (Puppeteer/Playwright) · PDF/A archival (ghostscript/verapdf) · digital signing (@signpdf) · qpdf repair/linearize/encrypt** → `pdf-tools` skill

## Workflow

1. **Pick the mode** — one document → Single; a folder to parse once → Folder; compare/extract with every tool → All-methods
2. **Identify the input** — check extension, size, page count; for folders, run the orchestrator's `--dry-run`
3. **Shortlist, then ask** — decision tree shortlists (Single); ask the user to pick with quick comparisons in the options; Folder/All use the script's type table (ask speed vs accuracy for `--prefer`)
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
