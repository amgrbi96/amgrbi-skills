# Eval Suite

Self-contained smoke suite for the pymupdf-pdf skill. Run before publishing
changes to either script or to SKILL.md claims:

```bash
python3 evals/smoke_test.py
```

- Builds all fixtures in a temp directory (nothing installed, nothing touched outside `tmp`)
- **CLI matrix**: every `pymupdf_parse.py` mode (single, `--dir` batch, skip-if-exists,
  `--pages`, `--md-engine`, `--dry-run`, error paths) and every `pdf_ops.py` subcommand
  (info, merge, split, rotate, delete, render, meta, toc, search, encrypt, decrypt)
  with expected exit codes
- **Output integrity**: merged page counts, rotation, decryption round-trip, TOC
  round-trip, native table cells from a ruled-grid fixture
- **Reference snippets**: executes the load-bearing API calls documented in
  `references/*.md` (annotations, widgets, redaction, Story, embedded files, links)
  so the docs can't silently rot

Requires `pymupdf` (>= 1.23). `pymupdf4llm` is optional — the engine-fallback
path is tested either way.
