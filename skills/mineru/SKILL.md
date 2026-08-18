---
name: mineru
description: "Parse PDFs, Word docs, PPTs, and images into clean Markdown using MinerU's cloud VLM engine. Use when: (1) Converting PDF/Word/PPT/image to Markdown, (2) Extracting text/tables/formulas from documents with highest accuracy, (3) Batch processing multiple files, (4) Saving parsed content to Obsidian or knowledge bases. Supports LaTeX formulas, tables, images, multilingual OCR, multi-token quota pooling, resume, and dry-run validation. Cloud-based — needs internet + API token."
homepage: https://mineru.net
metadata:
  openclaw:
    emoji: "📄"
    requires:
      bins: ["python3"]
      env:
        - name: MINERU_TOKEN
          description: "MinerU API token — create at https://mineru.net/user-center/api-token"
        - name: MINERU_TOKENS
          description: "Comma-separated MinerU API tokens for quota pooling (optional)"
    install:
      - id: pip
        kind: pip
        packages: ["requests"]
        label: "Install Python dependencies (pip)"
---

# MinerU Document Parser

Convert PDF, Word, PPT, and images to clean Markdown using MinerU's cloud VLM engine — LaTeX formulas, tables, and images all preserved. Highest accuracy of all the local parsers, at the cost of cloud round-trips.

This skill calls MinerU's **cloud web API** only (token-based). It never runs the local `mineru` CLI, which is a separate tool with different flags (`-p`, `-b/--backend`, `--effort`) and a heavy local install.

## Setup

1. Create one or more API tokens at https://mineru.net/user-center/api-token

2. Check prerequisites — Python **3.10+** (the script enforces this and exits with a clear error on older interpreters) and `requests`:

```bash
python3 --version                                                       # must be 3.10+
python3 -c "import requests" 2>/dev/null && echo "requests: ok" || pip install -r requirements.txt
```

3. Provide tokens any of these ways (combined if several are present):

```bash
export MINERU_TOKEN="single-token"            # one token
export MINERU_TOKENS="token1,token2,token3"   # quota pool
```

Or create `tokens.txt` in this skill's directory — one token per line, `#` comments allowed (gitignored, never committed).

4. Verify the whole setup offline (checks files, sizes, extensions, and tokens — no network, works even without `requests` installed):

```bash
python3 scripts/mineru_v2.py --dir ./docs/ --output ./output/ --dry-run
```

## Quota Pooling (multi-token)

Each token gets its own daily page quota. The script round-robins across all tokens and, at runtime:

- **Daily limit hit** (`-60018`) → token marked exhausted for today, file retried on the next token. Resets automatically tomorrow (state in `~/.mineru/state.json`).
- **Invalid/expired token** (`A0202`/`A0211`) → removed from the pool immediately, file retried on the next token.
- **All tokens exhausted** → run stops cleanly with instructions to add tokens; `--resume` continues where it left off.

To scale daily throughput, add tokens — 3 tokens ≈ 3000 pages/day.

## Limits (verified Aug 2026)

| Limit | Value | Handled by |
|---|---|---|
| File size | 200 MB | pre-flight check, rejected before upload |
| Pages per file | 200 | API error surfaced with `--pages` suggestion |
| Daily quota | 1000 pages/token | token rotation + state file |
| Batch size | 50 files | one file per batch request, never hit |

## When to Use This vs. Other Parsers

| Need | Tool |
|---|---|
| Highest accuracy (formulas, multi-column, scanned, complex layout) | **MinerU** (this skill) |
| Fast local PDF → Markdown (no cloud) | `pdf-to-markdown` or `pymupdf-pdf` |
| Local multi-format (DOCX/PPTX/XLSX/img) + tables/OCR | `liteparse` |

See the `parse-docs` router skill for full decision logic.

## Supported File Types

| Type | Formats |
|------|---------|
| 📕 PDF | `.pdf` — papers, textbooks, scanned docs |
| 📝 Word | `.docx` — reports, manuscripts |
| 📊 PPT | `.pptx` — slides, presentations |
| 🖼️ Image | `.jpg`, `.jpeg`, `.png` — OCR extraction |

## Commands

Always validate first — the dry run checks files, sizes, extensions, and tokens with no network and no dependencies:

```bash
python3 scripts/mineru_v2.py --dir ./docs/ --output ./output/ --dry-run
```

### Single File

```bash
python3 scripts/mineru_v2.py --file ./document.pdf --output ./output/
```

### Batch Directory with Resume

```bash
python3 scripts/mineru_v2.py \
  --dir ./docs/ \
  --output ./output/ \
  --workers 10 \
  --resume
```

### Direct to Obsidian

```bash
python3 scripts/mineru_v2.py \
  --dir ./pdfs/ \
  --output "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Obsidian/VaultName/" \
  --resume
```

(`~` in `--output`/`--file`/`--dir` is expanded by the script itself, but quote it as `"$HOME/..."` in shells where tilde inside quotes stays literal.)

### Chinese Documents

```bash
python3 scripts/mineru_v2.py --dir ./papers/ --output ./output/ --language ch
```

### Long Documents (>200 pages)

```bash
python3 scripts/mineru_v2.py --file ./big.pdf --output ./output/ --pages 1-200
python3 scripts/mineru_v2.py --file ./big.pdf --output ./output/ --pages 201-400
```

### Complex Layouts (slowest, most accurate)

```bash
python3 scripts/mineru_v2.py --file ./paper.pdf --output ./output/ --model vlm
```

## CLI Options

```
--dir PATH          Input directory (PDF/Word/PPT/images); hidden dotfiles ignored
--file PATH         Single file (mutually exclusive with --dir)
--output PATH       Output directory (required)
--token TOKEN       Token placed first in the pool (env/file tokens still used)
--tokens-file PATH  Read tokens from file, one per line (default: <skill>/tokens.txt)
--workers N         Concurrent workers, >= 1 (default: 5)
--resume            Report already-processed files up front and drop them from the run
--model MODEL       pipeline | vlm | MinerU-HTML (default: vlm)
--language LANG     auto | en | ch (default: auto)
--pages RANGES      Page ranges, e.g. "1-10,15,20-30" (validated; applies to every file with --dir)
--no-formula        Disable formula recognition
--no-table          Disable table extraction
--dry-run           Validate files and tokens, no network, no dependencies
```

**Idempotent by default:** a file whose output directory already exists is always skipped (⏭️, counted as success) so a re-run never re-spends quota. `--resume` additionally filters those files before the run starts and prints the skip count — use it after interruptions for accurate summaries.

## Model Version Guide

| Model | Speed | Accuracy | Best For |
|-------|-------|----------|----------|
| `pipeline` | ⚡ Fast | High | Standard docs, most use cases (default per API) |
| `vlm` | 🐢 Slow | Highest | Complex layouts, multi-column, mixed text+figures (script default) |
| `MinerU-HTML` | ⚡ Fast | High | Web-style output, HTML-ready content |

## Error Handling

- Up to 5 attempts per file with exponential backoff (1+2+4+8 s) for network errors, timeouts, and unrecognized API errors; token rotations (quota/invalid-token) never consume an attempt
- Non-retryable errors fail fast, one attempt: bad params (`-500`), too large (`-60005`), too many pages (`-60006` — the error message includes a `--pages` suggestion), region-blocked URL (`-60023`)
- Token errors rotate the pool (see Quota Pooling above)
- Failed files listed in a JSON summary block at the end (machine-readable)
- Ctrl-C saves token state and exits 130 — re-run with `--resume` to continue
- Exit codes: 0 success, 1 runtime failure (failed files / no token / bad input file / no network), 2 usage error (bad flag values) — safe for scripting

## Output Structure

```
output/
├── document-name/
│   ├── document-name.md    # Main Markdown
│   ├── images/             # Extracted images
│   └── content.json        # Metadata
```

## Performance

| Workers | Speed |
|---------|-------|
| 1 (sequential) | 1.2 files/min |
| 5 | 3.1 files/min |
| 15 | 5.6 files/min |

## Agent Lightweight API (no token)

MinerU also offers `/api/v1/agent/parse/*` — tokenless, IP-rate-limited, Markdown-only, ≤50 pages. Not wired into the script (it uses the token-based v4 API). See [references/api_reference.md](references/api_reference.md) if you need to call it directly.

## API Reference

Full endpoint + parameter + error-code details: [references/api_reference.md](references/api_reference.md)
