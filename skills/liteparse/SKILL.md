---
name: liteparse
description: Parse PDFs, Office documents (DOCX/PPTX/XLSX/ODT), and images locally into text, Markdown, or JSON with bounding boxes and OCR confidence — no cloud, no LLM, nothing leaves the machine. Use when the user wants local/offline/private document parsing or OCR (scanned PDFs, photos, screenshots), spatial text coordinates, page screenshots, or batch conversion of mixed-format folders — even casually ("grab the text from this", "read this image", "what does this scan say"). If the user needs highest accuracy (formulas, complex layouts, degraded scans) and cloud is acceptable, route to mineru instead.
compatibility: 'Node 18+; `npm i -g @llamaindex/liteparse` (bin: `lit`; verified against npm 2.13.1 — `lit --version` misleadingly prints a hardcoded 2.0.0, don't use it for install checks). LibreOffice required for Office formats.'
license: MIT
metadata:
  author: LlamaIndex
  version: "0.2.0"
---

# LiteParse (`lit` CLI)

Parse unstructured documents (PDF, DOCX, PPTX, XLSX, images) locally with LiteParse: fast, no cloud dependencies, no LLM. Output text, Markdown, or structured JSON with per-item bounding boxes and OCR confidence.

All commands and outputs below were **verified Aug 2026** against `@llamaindex/liteparse` 2.13.1 on macOS arm64.

## Defaults — OCR and LibreOffice are opt-in

Both cost the user something (network download, 800 MB install), so neither runs or installs silently:

1. **OCR is off by default.** The CLI enables OCR unless told otherwise — so always pass `--no-ocr` explicitly. Turn OCR on **only** when the gate below says so (`lit is-complex` → `needsOcr: true` with `textLength: 0`, or a parse came back empty) **and** the user approved. First run per language downloads ~15 MB over the network.
2. **LibreOffice is never auto-installed.** Offer it — stating the 800 MB size — only when the user actually needs an Office format parsed locally. Install only after explicit approval. If the user declines, route Office files to `mineru` (cloud converts them with zero local install) or a lighter skill.
3. **Try lighter skills first for text-layer PDFs** (`pdf-to-markdown`, `pymupdf-pdf`). Escalate to this skill's OCR only when those fail or return empty — that failure is the "needed" signal.

## Setup

Run the pre-flight first, then install only what is missing for the formats at hand — asking before every install beyond the CLI. Images and PDFs need nothing beyond the CLI; Office formats additionally need LibreOffice (opt-in, see Defaults).

### Pre-flight (run before parsing)

```bash
node --version                                 # must be v18+
command -v lit >/dev/null 2>&1 && echo "lit: ok" || echo "lit: MISSING"
command -v soffice >/dev/null 2>&1 && echo "libreoffice: ok" || echo "libreoffice: MISSING (only needed for Office formats)"
```

### Install

1. **CLI — always required:**

```bash
npm i -g @llamaindex/liteparse
lit parse --help >/dev/null && echo "install ok"
```

`lit parse --help` is the right verification: it loads the native platform binary at startup and fails loudly if the install is broken. Don't use `lit --version` — it prints a hardcoded `2.0.0` regardless of the installed package.

2. **LibreOffice — opt-in, user approval required (only for Office formats: DOCX/PPTX/XLSX/ODT/RTF/CSV):** ~800 MB. Offer it with the size stated; never install unprompted. If it's missing, Office files fail immediately with a clear exit-1 error listing these same commands; PDFs and images are unaffected.

```bash
brew install --cask libreoffice     # macOS
sudo apt-get install libreoffice    # Ubuntu/Debian
choco install libreoffice-fresh     # Windows
```

Verify with `command -v soffice`.

3. **OCR data — automatic, needs network once per language:** the first OCR run downloads Tesseract data (~45 s; cached at `~/Library/Application Support/tesseract-rs/tessdata/` on macOS). For offline machines, pre-seed a tessdata directory and point the config file's `tessdataPath` at it.

## When to Use This vs. Other Parsers

| Need | Tool |
|---|---|
| Local/private/offline multi-format parsing + OCR | **liteparse** (this skill) |
| Highest accuracy — formulas, multi-column academic, handwriting, degraded scans | `mineru` (cloud VLM, token required, 200 MB / 200 pages / 1000 pages/day per token) |
| Fast local PDF → Markdown (no OCR, no office formats) | `pdf-to-markdown` or `pymupdf-pdf` |

**Route to mineru when:** OCR output comes back empty or garbled (see Limits), the document has LaTeX formulas or complex multi-column layout, or the user explicitly wants maximum accuracy and accepts a cloud round-trip.

See the `parse-docs` router skill for full decision logic.

## Supported Input Formats

| Category | Formats | Requirement |
|----------|---------|-------------|
| PDF | `.pdf` (incl. password-protected via `--password`) | none |
| Word | `.docx`, `.docm`, `.odt`, `.rtf` | LibreOffice |
| PowerPoint | `.pptx`, `.pptm`, `.odp` | LibreOffice |
| Spreadsheets | `.xlsx`, `.xlsm`, `.ods`, `.csv`, `.tsv` | LibreOffice |
| Images | `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.tiff`, `.webp`, `.svg` | none |

Office documents are converted to PDF via LibreOffice first, then parsed. Anything else fails fast: `Error: conversion error: unsupported file format: .txt`, exit 1.

## Commands

### Single File → Text (default: no OCR)

```bash
lit parse document.pdf --no-ocr
```
```text
[liteparse] extract: 23.1ms (1 pages)
[liteparse] ocr: 0.0ms
...
LiteParse Audit Report

Section 1: Introduction
```

The CLI turns OCR **on** by default — always pass `--no-ocr` unless the OCR gate below passed and the user approved (see Defaults).

Add `-q`/`--quiet` to suppress the `[liteparse]` timing lines on stderr. Read from stdin with `lit parse -` (e.g. `curl -sL url/file.pdf | lit parse -`).

### Markdown (headings, lists, tables, links)

```bash
lit parse document.pdf --format markdown
```

### JSON with Bounding Boxes

```bash
lit parse document.pdf --format json -o output.json
```

Output structure (verified):

```json
{
  "pages": [
    {
      "page": 1,
      "width": 384,
      "height": 144,
      "text": "Invoice 2026-08-19  Total due: 142.50 USD",
      "text_items": [
        {
          "text": "Invoice 2026-08-19",
          "x": 20.6, "y": 32.2, "width": 145.4, "height": 12.5,
          "font_name": "OCR",
          "font_size": 12.5,
          "confidence": 0.962
        }
      ]
    }
  ]
}
```

Optional JSON extras (each adds fields): `--extract-images` (+`--image-output-dir <dir>` to write bytes), `--extract-annotations`, `--extract-form-fields`, `--extract-blocks`, `--extract-structure-tree`, `--extract-vector-graphics`, `--extract-text-metadata`, `--complexity`.

### The OCR Gate — run before ever dropping `--no-ocr`

`is-complex` is a cheap text-layer-only pass. It decides whether OCR is warranted at all; only a positive gate **plus user approval** turns OCR on:

```bash
lit is-complex scan.png
```
```json
[
  {
    "pageNumber": 1,
    "textLength": 0,
    "needsOcr": true,
    "reasons": ["scanned"],
    "layout": { "columnCount": 1, "isComplex": false, "reasons": [] }
  }
]
```

Reading the verdict: `needsOcr: true` **with `textLength: 0`** (reasons like `scanned`, `no-text`, `garbled`) → offer OCR to the user. Reasons: `scanned`, `no-text`, `sparse-text`, `embedded-images`, `garbled`, `vector-text`, `annotation-text`. Caveat (verified): it is conservative — a short text-layer memo flags `sparse-text`/`needsOcr: true` even when the text layer is fine. Check `textLength` before routing; don't blindly trust the flag.

### Page Ranges, DPI, and OCR (gated)

```bash
lit parse document.pdf --no-ocr                # DEFAULT — always start here
lit parse document.pdf --target-pages "1-5,10,15-20"
lit parse document.pdf --max-pages 50          # hard limit (default: 1000)
lit parse document.pdf --password secret       # encrypted documents

# OCR variants — only after the gate passed AND the user approved:
lit parse document.pdf --ocr-language fra      # Tesseract code; default eng
lit parse document.pdf --dpi 300               # default 150
```

### External OCR Server (higher accuracy than built-in Tesseract)

```bash
lit parse document.pdf --ocr-server-url http://localhost:8828/ocr \
  --ocr-server-header "Authorization: Bearer tkn"
```

The server implements `POST /ocr` taking `file` (multipart) + `language`, returning `{"results": [{"text": "Hello", "bbox": [x1, y1, x2, y2], "confidence": 0.98}]}`.

### Screenshots (for vision-capable agents)

```bash
lit screenshot document.pdf -o ./screenshots          # writes page_1.png, page_2.png, ...
lit screenshot document.pdf --target-pages "1,3,5" -o ./screenshots
```

### Batch Directory

```bash
lit batch-parse ./input ./output --recursive --no-ocr   # → "batch complete: 2 succeeded, 0 failed"
lit batch-parse ./input ./output --extension .pdf --format markdown --no-ocr
```

Writes one file per input named `<stem>.<txt|json|md>` directly in the output dir — **files with the same stem overwrite each other** (verified: `a.docx` and `a.png` both produce `a.txt`). Keep stems unique in batch inputs.

## Config File

For repeated use, pass a JSON config with Node-API camelCase keys (verified in CLI source — snake_case does **not** work here):

```bash
lit parse document.pdf --config liteparse.config.json
```

```json
{
  "ocrEnabled": true,
  "ocrLanguage": "eng",
  "maxPages": 1000,
  "dpi": 150,
  "outputFormat": "json",
  "numWorkers": 4,
  "preserveVerySmallText": false,
  "continueOnPageError": false
}
```

CLI flags override config-file values. Valid keys include everything above plus `ocrServerUrl`, `ocrServerHeaders`, `targetPages`, `password`, `quiet`, `skipDiagonalText` (config-only; no CLI flag).

## Limits (verified Aug 2026)

| Limit | Detail |
|---|---|
| **Silent empty OCR** | Degraded/rotated/blurred images can exit **0** with `Empty page!!` on stderr and empty `text_items` (verified with a blurred JPEG). Always check output is non-empty; if empty → re-try higher `--dpi`, another language, or route to `mineru`. |
| First OCR run per language | Downloads Tesseract data: ~45 s cold vs ~0.3 s warm per small page (verified). Not a hang — wait it out. |
| Office conversion overhead | LibreOffice adds ~4 s/file warm, ~15 s on first conversion after install. |
| Missing LibreOffice | Clear error + exit 1 (no silent fail): tells you the exact brew/apt/choco command. |
| OCR quality | Built-in Tesseract is fine for clean prints; weak on handwriting, dense low-DPI scans, heavy skew. Use an external OCR server or mineru for those. |
| Markdown fidelity | Reconstruction varies; office-converted docs can collapse paragraph breaks into one line (verified). Prefer `--format text` for fidelity, `markdown` for LLM ingestion of clean PDFs. |
| Max pages | Default 1000 (`--max-pages` to change). |
| Version reporting | `lit --version` prints hardcoded `2.0.0`; check `npm ls -g @llamaindex/liteparse` for the real package version. |
