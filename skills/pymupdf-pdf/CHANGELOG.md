# Changelog

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
