---
name: pymupdf-pdf
description: Local PDF workbench on PyMuPDF — extract text/tables/images to Markdown or JSON, merge/split/rotate/delete pages, render to PNG, read/write metadata and TOC, search, encrypt/decrypt, plus recipes for annotations, forms, redaction, and PDF creation. Use for any local, no-cloud PDF task; prefer mineru for VLM-grade accuracy and pdf-tools for JS/Puppeteer pipelines.
metadata:
  openclaw:
    emoji: "📄"
    requires:
      bins: ["python3"]
    install:
      - id: pip
        kind: pip
        packages: ["pymupdf>=1.23"]
        label: "Install PyMuPDF (pip)"
      - id: pip-optional
        kind: pip
        packages: ["pymupdf4llm"]
        label: "Optional: better Markdown engine + layout detection addon"
---

# PyMuPDF PDF Workbench

One dependency (`pip install pymupdf`), fully local, covering the whole PDF lifecycle: extraction, manipulation, creation, annotation, forms, and security. Two CLIs plus recipe references — load only the reference you need (progressive disclosure; don't read them all up front).

## Setup

Prerequisites: `python3` + `pymupdf` **1.23 or later** (native table extraction needs 1.23). No cloud, no token, no other binaries. Both scripts exit 1 with an install hint if PyMuPDF is missing (`--help` works without it).

1. Install PyMuPDF:

```bash
pip install "pymupdf>=1.23"
```

If pip refuses with "externally-managed-environment" (macOS/Linux system Python), either use a venv:

```bash
python3 -m venv ~/.venvs/pymupdf
~/.venvs/pymupdf/bin/pip install "pymupdf>=1.23"
# then invoke the scripts with that interpreter:
~/.venvs/pymupdf/bin/python3 scripts/pymupdf_parse.py /path/to/file.pdf
```

or force it: `pip install --break-system-packages "pymupdf>=1.23"`.

2. Verify the dependency:

```bash
python3 -c "import pymupdf; print(pymupdf.__version__)"   # expect: 1.23 or later
```

3. Smoke-test (validates dependency + a real PDF, writes nothing):

```bash
./scripts/pymupdf_parse.py /path/to/any.pdf --dry-run
# expect: "✅ Dry run OK — valid PDF, N pages. Ready to parse." (exit 0)
```

Optional but recommended — `pymupdf4llm` unlocks the higher-quality Markdown engine and layout detection:

```bash
pip install pymupdf4llm
```

Troubleshooting: NixOS `libstdc++` import failures and other notes live in `references/pymupdf-notes.md`.

## The two CLIs

```bash
# Extraction: single PDF or a whole directory (batch skips already-parsed docs)
./scripts/pymupdf_parse.py file.pdf --format both --tables --images --md-engine auto
./scripts/pymupdf_parse.py --dir ./pdfs/ --outroot ./pymupdf-output --tables

# Operations: merge, split, rotate, delete, render, info, meta, toc, search, encrypt, decrypt
./scripts/pdf_ops.py info file.pdf
./scripts/pdf_ops.py merge --inputs a.pdf b.pdf -o merged.pdf
./scripts/pdf_ops.py render file.pdf --pages 1-3 --dpi 150 --outroot pngs/
./scripts/pdf_ops.py encrypt file.pdf --user-pw secret -o enc.pdf
```

Subcommand flags (including `--dry-run` and `--password`) go **after** the subcommand name. Both scripts: pre-flight validation, `--dry-run`, exit code 0 only on success, JSON summary at the end.

## Parse options

- `pdf` positional for one file, or `--dir DIR` for batch (skips documents whose output folder already exists)
- `--pages 1-3,5` to parse a subset — real page numbers are preserved in outputs; applies to every file in batch mode
- `--format md|json|both` (default: `md`)
- `--md-engine auto|basic|pymupdf4llm` (default: `auto` — uses pymupdf4llm when installed, else basic)
- `--images` to extract embedded images
- `--tables` native table extraction via `page.find_tables()` — bbox + rows as lists (falls back to line-based on PyMuPDF < 1.23)
- `--outroot DIR` to change output root (default: `./pymupdf-output`)
- `--lang` language hint recorded in JSON output metadata (default: `en`)
- `--dry-run` to validate inputs (including which batch files would be skipped) and exit without writing anything

### Markdown engine guide

| Engine | Speed | Quality | Notes |
|---|---|---|---|
| `auto` | — | — | picks `pymupdf4llm` if installed, else `basic` (default) |
| `pymupdf4llm` | 🐢 Slower | High | Headers, real Markdown tables, preserves structure; needs `pip install pymupdf4llm` |
| `basic` | ⚡ Fastest | OK | `get_text("markdown")`, `<!-- page N -->` markers per page |

Requesting `pymupdf4llm` explicitly exits 1 with an install hint if the package is missing; `auto` silently falls back to `basic`. The chosen engine is recorded in the JSON summary (`md_engine`).

## Capability routing (progressive disclosure)

Load the matching reference file only when the task reaches that family:

| Task family | Load | CLI shortcut |
|---|---|---|
| Text extraction modes, words/spans, search, OCR | `references/extract.md` | `pymupdf_parse.py`, `pdf_ops.py search` |
| Tables (`find_tables`), embedded images, rendering/crops, `pymupdf.layout` bboxes | `references/tables-images-layout.md` | `--tables`, `--images`, `pdf_ops.py render` |
| Merge, split, reorder, rotate, crop, delete pages | `references/manipulate.md` | `pdf_ops.py merge/split/rotate/delete` |
| Create PDFs: text, fonts, images, drawing, HTML (Story) | `references/create.md` | — (recipes) |
| Annotations, form filling, redaction | `references/annotate-forms-redact.md` | — (recipes) |
| Encrypt/decrypt, metadata, TOC, embedded files, links | `references/security-metadata.md` | `pdf_ops.py encrypt/decrypt/meta/toc/info` |
| Install issues, NixOS libstdc++ | `references/pymupdf-notes.md` | — |

Development: after changing either script or any documented claim, run `python3 evals/smoke_test.py` (56 self-contained cases; exits nonzero on any failure).

## Error handling

- Pre-flight checks reject: missing file, non-PDF extension, empty file, corrupt PDF, password-protected PDF (supply `--password`) — one-line errors
- Missing PyMuPDF exits with a clear install hint; `--help` works without the dependency
- Exit code 0 only on success (or dry-run OK); 1 on invalid input, missing dependency, or failure — safe for scripting
- JSON summary block at the end of every run (op/file/pages/outputs/elapsed)
- `pdf_ops.py` never writes in place: output must differ from input; overwritten outputs are explicit (`-o`)

## Output conventions (parse)

- `./pymupdf-output/<pdf-stem>/` by default (filename without extension)
- `output.md` (with `<!-- page N -->` markers in basic engine), `output.json` (includes `lang`)
- `images/` subdir (`page-N-img-M.png`), `tables.json` (bbox + row lists)

## When to use vs. neighbors

| Need | Tool |
|---|---|
| Any local PDF task, one Python dependency | **this skill** |
| Fastest PDF → structured Markdown | `pdf-to-markdown` skill |
| DOCX/PPTX/XLSX/images + OCR + tables | `liteparse` skill |
| Highest accuracy, formulas, batch (cloud VLM) | `mineru` skill |
| JS-first pipelines: Puppeteer HTML→PDF, signing, BullMQ | `pdf-tools` skill |

For routing across parsers, start with the `parse-docs` skill.
