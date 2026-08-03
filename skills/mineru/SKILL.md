---
name: mineru
description: "Parse PDFs, Word docs, PPTs, and images into clean Markdown using MinerU's cloud VLM engine. Use when: (1) Converting PDF/Word/PPT/image to Markdown, (2) Extracting text/tables/formulas from documents with highest accuracy, (3) Batch processing multiple files, (4) Saving parsed content to Obsidian or knowledge bases. Supports LaTeX formulas, tables, images, multilingual OCR, and async parallel processing. Cloud-based — needs internet + API token."
homepage: https://mineru.net
metadata:
  openclaw:
    emoji: "📄"
    requires:
      bins: ["python3"]
      env:
        - name: MINERU_TOKEN
          description: "MinerU API token — create at https://mineru.net/user-center/api-token"
    install:
      - id: pip
        kind: pip
        packages: ["requests", "aiohttp"]
        label: "Install Python dependencies (pip)"
---

# MinerU Document Parser

Convert PDF, Word, PPT, and images to clean Markdown using MinerU's cloud VLM engine — LaTeX formulas, tables, and images all preserved. Highest accuracy of all the local parsers, at the cost of cloud round-trips.

## Setup

1. Create an API token at https://mineru.net/user-center/api-token

```bash
export MINERU_TOKEN="your-token-here"
```

**Limits (verified Aug 2026):**
- **200 MB** per file
- **200 pages** per file
- **1000 pages/day** at highest priority (extra pages process at lower priority)
- **50 files** per batch request

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

Run from the skill directory (the `.venv` has `requests` + `aiohttp` installed):

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
  --output "~/Library/Mobile Documents/com~apple~CloudDocs/Obsidian/VaultName/" \
  --resume
```

### Chinese Documents

```bash
python3 scripts/mineru_v2.py --dir ./papers/ --output ./output/ --language ch
```

### Complex Layouts (slowest, most accurate)

```bash
python3 scripts/mineru_v2.py --file ./paper.pdf --output ./output/ --model vlm
```

## CLI Options

```
--dir PATH          Input directory (PDF/Word/PPT/images)
--file PATH         Single file
--output PATH       Output directory (default: ./output/)
--workers N         Concurrent workers (default: 5, max: 15)
--resume            Skip already processed files
--model MODEL       pipeline | vlm | MinerU-HTML (default: vlm)
--language LANG     auto | en | ch (default: auto)
--no-formula        Disable formula recognition
--no-table          Disable table extraction
--token TOKEN       API token (overrides MINERU_TOKEN env var)
```

## Model Version Guide

| Model | Speed | Accuracy | Best For |
|-------|-------|----------|----------|
| `pipeline` | ⚡ Fast | High | Standard docs, most use cases (default per API) |
| `vlm` | 🐢 Slow | Highest | Complex layouts, multi-column, mixed text+figures (script default) |
| `MinerU-HTML` | ⚡ Fast | High | Web-style output, HTML-ready content |

## Script Selection

| Script | Use When |
|--------|----------|
| `mineru_v2.py` | Default — async parallel (up to 15 workers) |
| `mineru_async.py` | Fast network, need maximum throughput |
| `mineru_stable.py` | Unstable network — sequential, max retry |

Other scripts (`mineru_api.py`, `mineru_batch.py`, `mineru_parallel.py`, `mineru_obsidian.py`) are legacy variants — prefer `mineru_v2.py` unless you have a specific reason.

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

## Error Handling

- 5× auto-retry with exponential backoff
- Use `--resume` to continue interrupted batches
- Failed files listed at end of run
- Common failures: token invalid (`A0202`), file >200 MB (`-60005`), >200 pages (`-60006`), daily limit (`-60018`)

## Agent Lightweight API (no token)

MinerU also offers `/api/v1/agent/parse/*` — tokenless, IP-rate-limited, Markdown-only, ≤50 pages. Not wired into the scripts (they use the token-based v4 API). See [references/api_reference.md](references/api_reference.md) if you need to call it directly.

## API Reference

Full endpoint + parameter + error-code details: [references/api_reference.md](references/api_reference.md)
