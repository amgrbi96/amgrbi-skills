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

### Token health check

```bash
python3 scripts/mineru_v2.py --check-token
```

One read-only API call per token (zero page spend): reports valid / invalid / inconclusive, marks invalid tokens dead in the state file, and revives stale dead/exhausted marks. Run it after adding tokens or when a run fails with auth errors. Needs no `--file`/`--dir`/`--output`.

## Limits (verified Aug 2026)

| Limit | Value | Handled by |
|---|---|---|
| File size | 200 MB | pre-flight check, rejected before upload |
| Pages per file | 200 | pre-flight warning prescribes a physical split |
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

## Clarify Intent Before Parsing

Defaults fit most runs — ask only what's ambiguous, one round, then parse:

1. **Accuracy or speed?** Default `vlm` (slowest, highest accuracy). For quick text extraction suggest `pipeline`. Undecided? Settle it empirically with `--probe` (sample-parse with both models — see Commands).
2. **Deliverables?** Markdown by default; `--extra-formats docx,html,latex` adds those files at no extra page cost.
3. **Output location?** Default `./output/` next to the input; confirm when the user names a vault or folder.
4. **Language?** `auto` handles most; `ch` improves Chinese-only documents.

Cost framing: every parsed page spends daily quota (1000 pages/token/day) — quote the estimated page count when the user asks whether to proceed.

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

**Preferred: physically split the PDF into ≤200-page parts and submit each whole** — parts are ordinary files, so this always works:

```bash
# pymupdf-pdf skill's splitter (or any splitter) → parts/big-1-200.pdf, parts/big-201-400.pdf, …
python3 pdf_ops.py split big.pdf --outroot ./parts/ --ranges 1-200,201-400
python3 scripts/mineru_v2.py --dir ./parts/ --output ./output/ --resume
```

`--pages` is the fallback, not the default. It sends the whole file with a server-side `page_ranges` request, and **on some PDFs the server rejects the parse (`-60010`, "replace the file") even for pages that parse fine as a standalone file** (seen on scanned Wiley textbooks, Aug 2026). The rejection is deterministic per file, each blind attempt burns ~6 minutes of retries, and the script fails fast on it — treat one `-60010` as file-level and switch to the physical split instead of retrying other ranges:

```bash
python3 scripts/mineru_v2.py --file ./big.pdf --output ./output/ --pages 1-200   # try once; on -60010 → split
```

Working ranges land in their own folders — `output/big-1-200/`, `output/big-201-400/` — and re-running a finished range is an idempotent no-op.

### Complex Layouts (slowest, most accurate)

```bash
python3 scripts/mineru_v2.py --file ./paper.pdf --output ./output/ --model vlm
```

### Sample Probe (pick a model empirically)

```bash
python3 scripts/mineru_v2.py --file ./book.pdf --output ./probe/ --probe                            # pages 1-3, pipeline + vlm
python3 scripts/mineru_v2.py --file ./book.pdf --output ./probe/ --probe --probe-pages "85-87,203"  # pages you know are hard
python3 scripts/mineru_v2.py --file ./book.pdf --output ./probe/ --probe --model MinerU-HTML        # one model only
```

- **Pages:** first N by default (`--probe 5`), or exact pages via `--probe-pages` — pick the hardest pages (formulas, dense tables, multi-column), not the title page. PDFs only.
- **Models:** no `--model` → `pipeline` + `vlm` side by side (comparison mode); `--model X` → probe just X. Each model writes its own folder, so probing different models across runs coexists.
- **Output:** `output/<name>-probe/<model>/<name>/<name>.md` — compare with `code -d fileA fileB`, then run the full parse with `--model <winner>`.
- **Cost:** pages × models (~6 pages of quota for the default probe). PDFs and images only — Office files aren't page-addressable.

## CLI Options

```
--dir PATH          Input directory (PDF/Word/PPT/images); hidden dotfiles ignored
--file PATH         Single file (mutually exclusive with --dir)
--output PATH       Output directory (required unless --check-token)
--token TOKEN       Token placed first in the pool (env/file tokens still used)
--tokens-file PATH  Read tokens from file, one per line (default: <skill>/tokens.txt)
--workers N         Concurrent workers, >= 1 (default: 5)
--resume            Report already-processed files up front and drop them from the run
--model MODEL       pipeline | vlm | MinerU-HTML (default: vlm; with --probe: probe only this model)
--language LANG     auto | en | ch (default: auto)
--pages RANGES      Server-side page ranges, e.g. "1-10,15,20-30" — rejected on some PDFs (-60010); prefer a physical split (applies to every file with --dir)
--extra-formats F   Extra deliverables: comma list from docx,html,latex (default: none)
--probe [N]         Sample-parse first N pages to pick a model, then stop (default: 3)
--probe-pages RANGES Probe specific pages instead of the first N, e.g. "85-87,203" (PDFs only)
--check-token       Verify pool tokens against the API (read-only), then exit
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
- Non-retryable errors fail fast, one attempt: bad params (`-500`), too large (`-60005`), too many pages (`-60006` — the error prescribes a physical split), region-blocked URL (`-60023`). Server-side `page_ranges` rejection (`-60010` with `--pages`) also fails fast — it is deterministic per file, and blind retries burn ~6 min each
- Token errors rotate the pool (see Quota Pooling above)
- Failed files listed in a JSON summary block at the end (machine-readable)
- Ctrl-C saves token state and exits 130 — re-run with `--resume` to continue
- Exit codes: 0 success, 1 runtime failure (failed files / no token / bad input file / no network), 2 usage error (bad flag values) — safe for scripting

## Waste Guards

The script refuses to spend quota silently:

- **Duplicate runs** — existing output directories are always skipped (⏭️), so re-runs never re-parse
- **OCR overkill** — warns when a PDF already has a text layer (a local parser likely suffices — see comparison table above)
- **Over-limit files** — warns when a PDF is estimated >200 pages, prescribing a physical split into ≤200-page parts (`--pages` ranges are rejected server-side on some PDFs)
- **Over-budget batches** — warns when estimated total pages exceed the pool's daily capacity (~1000/token)
- **Token health** — `--check-token` catches dead tokens before a run instead of mid-batch

Estimates come from raw PDF bytes (best-effort — compressed PDFs may hide page counts); warnings are advisory, nothing is blocked.

## Output Structure

```
output/
├── document-name/
│   ├── document-name.md    # Main Markdown
│   ├── images/             # Extracted images
│   ├── content.json        # Metadata
│   └── document-name.docx  # Only with --extra-formats docx
├── document-name-201-400/  # With --pages: one folder per range (md named to match)
└── document-name-probe/    # Only with --probe
    ├── pipeline/document-name/document-name.md
    └── vlm/document-name/document-name.md
```

## Performance

| Workers | Speed |
|---------|-------|
| 1 (sequential) | 1.2 files/min |
| 5 | 3.1 files/min |
| 15 | 5.6 files/min |

## Keeping This Skill Current

- **Verified stamps**: the Limits table above and `references/api_reference.md` carry "verified <date>" stamps. Re-check against https://mineru.net/apiManage/docs quarterly — file/page limits, error codes, parameter defaults.
- **Self-test**: after changing the script or any documented claim, run the offline self-test (checks every documented flag/default against `--help`, exercises all offline paths, no network):

```bash
python3 evals/selftest.py
```

- **Live smoke test**: `--check-token` doubles as one — if known-good tokens start reporting "inconclusive", the API's error codes changed; update `references/api_reference.md` and the code's `FATAL_TOKEN_CODES` / `-60012` handling.

## Agent Lightweight API (no token)

MinerU also offers `/api/v1/agent/parse/*` — tokenless, IP-rate-limited, Markdown-only, ≤50 pages. Not wired into the script (it uses the token-based v4 API). See [references/api_reference.md](references/api_reference.md) if you need to call it directly.

## API Reference

Full endpoint + parameter + error-code details: [references/api_reference.md](references/api_reference.md)
