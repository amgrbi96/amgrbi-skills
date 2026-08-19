---
name: pdf-to-markdown
description: Extract text from PDFs as structured, semantic Markdown. Use when converting a PDF to Markdown, extracting text from a PDF, processing one or more PDFs into Markdown output, reading PDF contents for analysis, ingesting documents for RAG pipelines, preparing PDFs for LLM context, or any task where PDF text needs to be in a machine-readable format. ALWAYS use this skill when the user has a PDF and needs its content as text or Markdown — even if they don't explicitly say "convert to markdown". Fastest option for PDFs with a text layer; cannot OCR scanned PDFs on the free tier (route those to mineru/liteparse).
license: Proprietary
---

# PDF to Markdown

Fast, local PDF → structured Markdown via Nutrient's CLI. Preserves headings, tables, lists, and reading order — significantly better than reading a PDF as raw text. Best choice for speed on PDFs that have a real text layer. **No OCR on the free tier**: scanned/image-only PDFs produce empty output with exit code 0 (see [Failure modes](#failure-modes-verified-aug-2026)).

## What the binary is

`bin/pdf-to-markdown` is a POSIX-shell wrapper, not a bundled converter. On first run it downloads Nutrient's proprietary CLI (`nutrient-<platform>`, currently v1.4.1) from `agent-cdn.nutrient.io` into `~/.local/share/nutrient/cli/` and `exec`s it. It re-checks the CDN for updates every 6 hours; if the check fails but a binary is cached, the cached binary is used silently.

- Platforms: `linux-amd64`, `linux-arm64`, `macos-arm64`. Intel Macs (Darwin/x86_64) are **unsupported** — the wrapper exits 1.
- The underlying CLI is multi-command. The same wrapper also exposes `pdf-to-text` (layout-preserving plain text) and `query` (BM25 search over extracted `.md`/`.txt`). This skill only documents `pdf-to-markdown`.

## Install & prerequisites

Requirements: a supported platform (linux-amd64, linux-arm64, macos-arm64 — Intel Macs unsupported), `curl` **or** `wget`, `tar`, a writable `~/.local/share/nutrient/`, and network access to `agent-cdn.nutrient.io` on the first run (offline afterwards until the 6-hourly update check).

Verify everything in one command:

```bash
$SKILL_DIR/bin/check-env
```

Exit 0 means ready; a missing binary is fine — the wrapper self-installs on the first conversion. To pre-download the binary instead (so batch jobs never hit the network mid-run):

```bash
$SKILL_DIR/bin/check-env --install   # ~40 s measured
```

What gets installed: the binary at `~/.local/share/nutrient/cli/nutrient-<platform>` plus a state file tracking the release for the 6-hourly update check. Uninstall = `rm -rf ~/.local/share/nutrient`.

## Usage

Set `SKILL_DIR` to the absolute path of the directory containing this SKILL.md. Use `$SKILL_DIR/bin/pdf-to-markdown` in all commands below.

### Single file

```bash
$SKILL_DIR/bin/pdf-to-markdown INPUT.pdf OUTPUT.md
```

If `OUTPUT.md` is omitted, the Markdown goes to stdout.

### Batch directory (2+ files)

```bash
$SKILL_DIR/bin/pdf-to-markdown INPUT_DIR/ OUTPUT_DIR/
```

Converts every file in the input directory in parallel (it does **not** filter by extension — a stray `.txt` becomes a per-file error). Successes are still written when some files fail; exit code is 1 with an `N of M files failed` summary on stderr.

### Image export

```bash
$SKILL_DIR/bin/pdf-to-markdown --enable-image-export INPUT.pdf OUTPUT.md
```

Images are saved to `{output}_resources/` as `image_NNN.jpeg` and referenced with relative Markdown links. Two caveats: alt text is always the literal string `Description` (no real captions), and links are relative — move the `_resources` directory together with the `.md` or the links break.

## CLI flags (verified against nutrient 1.4.1, Aug 2026)

```
INPUT [OUTPUT]       Convert one PDF; stdout if OUTPUT omitted
INDIR OUTDIR         Batch-convert a directory in parallel
--enable-image-export  Export images to {output}_resources/ and reference them
--vision             Machine-vision ICR pipeline (layout, tables, formulas)
--provider P         Vision provider: auto (default) | gpu | cpu; only with --vision
--license-key KEY    Not listed in --help but accepted; activates a paid license
```

**`--vision` is license-gated.** On the free tier it exits 1 with `vision extraction failed (3017): ... 'vision_icr_api'`. Don't reach for it unless a license key is in hand — for scanned PDFs, route to mineru or liteparse instead (see below).

## Companion subcommands

The same wrapper passes through to two more Nutrient subcommands (both verified working, free tier):

**`pdf-to-text`** — layout-preserving plain text instead of Markdown. Tables come out column-aligned with whitespace, not HTML. Good for diffing or consumers that choke on Markdown.

```bash
$SKILL_DIR/bin/pdf-to-markdown pdf-to-text INPUT.pdf [OUTPUT.txt]   # also supports INDIR OUTDIR
```

**`query text`** — BM25 ranked passage search over converted `.md`/`.txt` files. Searches a file, a directory (hits attributed per file), or a pre-built index. Use it after batch conversion to answer "where does this corpus say X" without loading everything into context.

```bash
$SKILL_DIR/bin/pdf-to-markdown query text OUTPUT_DIR/ "search terms" -k 5
$SKILL_DIR/bin/pdf-to-markdown query text OUTPUT_DIR/ "search terms" --emit-index corpus.idx  # build once
$SKILL_DIR/bin/pdf-to-markdown query text corpus.idx "search terms"                          # reuse, faster
```

Useful options: `-k N` results (default 8), `-e N` context lines (default 5), `--display json` for machine-readable hits (`line`, `score`, `text`, plus `document` when the corpus has multiple files — index queries omit it), `--mode strict|balanced|lenient`.

Notes: both subcommands' `--vision` variants hit the same 3017 license gate. `self-update` also exists but is redundant — the wrapper already auto-updates every 6 hours.

## Output characteristics (verified)

- Headings become ATX (`#`/`##`), mapped from font size/weight.
- **Heading detection is inconsistent**: headings immediately followed by a list or a table are sometimes emitted as plain text. Spot-check heading counts against the PDF.
- Tables become HTML `<table>` blocks, not GFM pipe tables. Column structure is preserved; fine for rendering and LLMs, awkward for grep/diff. Detection needs roughly 3+ data rows — smaller grids degrade to aligned plain-text lines.
- Two-column pages keep correct column reading order on simple layouts. Complex layouts are untested here — prefer mineru.
- Multi-page documents concatenate with **no page-break markers**, and repeated headers/footers are kept verbatim on every page.
- Whitespace is loose: runs of blank lines between blocks.

## Failure modes (verified Aug 2026)

| Situation | Behavior |
|---|---|
| Scanned / image-only PDF | **Exit 0 with ~2 bytes of output.** Silent success — always check output size after converting. |
| `--vision` without paid license | Exit 1, error 3017 `vision_icr_api` |
| Encrypted PDF | Exit 1, error 3026 `PdfDocumentMustBeUnencrypted` — and a **0-byte OUTPUT file is left behind**, so "file exists" ≠ success |
| Nonexistent / corrupt / non-PDF input | Exit 1, `failed to open document` on stderr |
| Output directory missing | Exit 1, clear stderr message |
| Extra positional arg (3+ args) | **Exit 0** — arg 2 is silently used as OUTPUT, arg 3 ignored. Double-check command shape. |
| No network and no cached binary | Exit 1 at wrapper stage; first run needs the CDN |

After every run, validate: `test -s OUTPUT.md || echo "empty — likely scanned; reroute to mineru/liteparse"`.

## When to route to another parser

| Situation | Use instead |
|---|---|
| Scanned / OCR needed | **mineru** (cloud VLM, best accuracy) or **liteparse** (local Tesseract) |
| LaTeX formulas | **mineru** |
| Complex multi-column or mixed layouts | **mineru** |
| DOCX / PPTX / XLSX / images | **liteparse** or **mineru** |
| PDF tables as machine-readable data | **pymupdf-pdf** (JSON) |
| Fast local conversion of a text-layer PDF | this skill |

See the `parse-docs` router skill for the full decision tree.

## Performance

Single small PDF: ~0.1–0.4 s. Batch mode converts in parallel. First run downloads the binary (~40 s measured); subsequent runs use the cache and only hit the CDN every 6 hours.

## License

Free tier: up to **1,000 documents per calendar month**, where each processing event counts as one document — converting the same file twice counts twice. Within the free tier, internal use, SaaS/OEM/embedded/white-label use, and serving third parties are all permitted. A commercial license (sales@nutrient.io) is required only above 1,000 documents/month; using the software to compete with Nutrient's offerings is prohibited. The binary collects and transmits usage telemetry (performance, feature usage, volume — not document contents). Full terms: `--license`.
