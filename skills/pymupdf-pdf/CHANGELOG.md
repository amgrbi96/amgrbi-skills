# Changelog

## v1.0.0 (2026-08-19)

Full PyMuPDF workbench: restructured for progressive disclosure (lean SKILL.md
routing to per-family references). Covers all PyMuPDF capability families.

### Added
- `scripts/pdf_ops.py`: operations CLI with 11 subcommands — info, merge,
  split (per-page or grouped ranges), rotate, delete, render (PNG at DPI),
  meta read/set, toc read/set, search, encrypt (AES-256), decrypt — each with
  pre-flight checks, --dry-run, exit codes, JSON summary
- `--tables` upgraded from line-based placeholder to native
  `page.find_tables()`: bbox, row/col counts, rows as lists (line-based
  fallback kept for PyMuPDF < 1.23)
- Six per-family reference files: extract, tables-images-layout, manipulate,
  create, annotate-forms-redact, security-metadata — every snippet verified
  against PyMuPDF 1.28
- SKILL.md rewritten as a capability router (progressive disclosure)

### Fixed
- Removed incorrect `pymupdf.open(path, password=...)` claim (password kwarg
  does not exist; authenticate() after open is the only path)

## v0.3.0 (2026-08-19)

### Added
- `--md-engine auto|basic|pymupdf4llm` (default `auto`): high-quality Markdown via
  pymupdf4llm (headers, real tables) when installed, automatic fallback to basic;
  explicit request without the package exits 1 with an install hint
- Chosen engine recorded in the JSON summary (`md_engine`) and dry-run output
- SKILL.md: engine guide, manipulation routing pointer (merge/split/forms → pdf
  document-production skill, not this one)

## v0.2.0 (2026-08-19)

### Added
- Setup section with install/verify/dry-run flow; `openclaw` install metadata (`pip install pymupdf`)
- `--dry-run`: validate the input PDF (opens it, reports page count) without writing anything
- Pre-flight checks: missing file, non-PDF extension, empty file, corrupt PDF, password-protected PDF
- Clear error + install hint when PyMuPDF is missing (`--help` works without the dependency)
- Exit codes: 0 = success/dry-run OK, 1 = invalid input, missing dep, or parse failure
- JSON summary block (file, pages, outputs, elapsed) at the end

### Fixed
- Use canonical `import pymupdf` (silences the `fitz` deprecation warning on PyMuPDF 1.24+)
- CMYK images now convert to RGB before saving (previously crashed in image extraction)

## v1.0.0 (2026-01-23)

### Added
- Initial release
- PyMuPDF PDF parsing skill for Clawdbot
- Support for Markdown and JSON output
- Image and basic table extraction
- NixOS compatibility notes for libstdc++
- Falls back from markdown to text if unsupported
