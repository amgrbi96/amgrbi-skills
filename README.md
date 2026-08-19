# amgrbi-skills

A collection of [agent skills](https://skills.sh) for AI coding assistants — document parsing, PDF engineering, systematic-review research, and more. Each skill is self-contained and installable on its own.

Works with Claude Code, Cursor, Codex, ZCode, and any agent that reads `SKILL.md` files.

## Install

Install all skills, then pick what you need:

```bash
npx skills add amgrbi96/amgrbi-skills
```

Or install a single skill from this monorepo by subpath:

```bash
npx skills add amgrbi96/amgrbi-skills/skills/mineru
```

## Skills

### Document Parsing

A layered toolkit — `parse-docs` routes to the right tool for the job.

| Skill | What it does | Install |
|---|---|---|
| **[parse-docs](skills/parse-docs/)** | 🧭 **Router** — picks the right parser by intent (speed vs. accuracy vs. tables vs. formulas) | `amgrbi96/amgrbi-skills/skills/parse-docs` |
| **[pdf-to-markdown](skills/pdf-to-markdown/)** | ⚡ Fastest PDF → structured Markdown (~0.009s/page) | `…/skills/pdf-to-markdown` |
| **[pymupdf-pdf](skills/pymupdf-pdf/)** | 📄 Local PDF workbench on PyMuPDF — extract (md/json/tables/images), merge/split/rotate, render, meta/TOC, encrypt, annotations/forms/redaction recipes | `…/skills/pymupdf-pdf` |
| **[liteparse](skills/liteparse/)** | 📚 Multi-format (DOCX/PPTX/XLSX/img) + OCR + tables | `…/skills/liteparse` |
| **[mineru](skills/mineru/)** | ☁️ Cloud VLM — highest accuracy, formulas, batch | `…/skills/mineru` |

### PDF Engineering

| Skill | What it does | Install |
|---|---|---|
| **[pdf-tools](skills/pdf-tools/)** | 🔧 Generate, merge, split, fill forms, encrypt, sign, redact | `amgrbi96/amgrbi-skills/skills/pdf-tools` |

### Research Workflows

| Skill | What it does | Install |
|---|---|---|
| **[prospero-search](skills/prospero-search/)** | 🔍 Search PROSPERO for registered systematic reviews + duplicate check | `…/skills/prospero-search` |
| **[prisma-cli](skills/prisma-cli/)** | 📊 Run the PRISMA literature-review pipeline | `…/skills/prisma-cli` |

### Productivity

| Skill | What it does | Install |
|---|---|---|
| **[flashcards](skills/flashcards/)** | 🎴 High-yield flashcards from any source (book/lecture/notes) → `.md` / `.apkg` | `amgrbi96/amgrbi-skills/skills/flashcards` |

### Integrations

| Skill | What it does | Install |
|---|---|---|
| **[openwa](skills/openwa/)** | 💬 OpenWA self-hosted WhatsApp API Gateway — deploy, pair, drive via MCP/REST | `amgrbi96/amgrbi-skills/skills/openwa` |

## Repository Structure

```
skills/
├── parse-docs/         # Router for the parsing cluster
├── pdf-to-markdown/    # Fast PDF → Markdown (bin/)
├── pymupdf-pdf/        # Local PyMuPDF parsing (scripts/ references/)
├── liteparse/          # Multi-format + OCR
├── mineru/             # Cloud VLM parsing (scripts/ references/)
├── pdf-tools/          # PDF manipulation (references/)
├── prospero-search/    # PROSPERO search (scripts/ references/)
├── prisma-cli/         # PRISMA pipeline wrapper (scripts/ references/)
├── flashcards/         # Flashcard builder (scripts/ references/)
└── openwa/             # WhatsApp gateway guide (references/)
```

Each skill folder is self-contained: a `SKILL.md` with frontmatter (`name`, `description`) plus optional `scripts/`, `references/`, or `bin/`.

## Picking a Parser

Unsure which document parser to use? Load `parse-docs` and let it route, or use this shortcut:

| You need… | Use |
|---|---|
| Speed, just the text | `pdf-to-markdown` |
| Local layout boxes / table crops | `pymupdf-pdf` |
| DOCX / PPTX / XLSX / images + OCR | `liteparse` |
| Formulas, multi-column, highest accuracy | `mineru` |

## Development

This is a monorepo of skills — no build step, no test suite. Validation is live (API calls, script `--help`).

```bash
# PROSPERO — validate API connectivity
python3 skills/prospero-search/scripts/test_api.py

# MinerU — verify the parser CLI runs
python3 skills/mineru/scripts/mineru_v2.py --help
```

See [`CLAUDE.md`](CLAUDE.md) for repo-level development guidance and per-skill technical notes.

## Adding a Skill

1. Create `skills/<name>/SKILL.md` with `name` + `description` frontmatter.
2. Add `scripts/`, `references/`, or `bin/` as needed.
3. **YAML gotcha:** if the `description` contains a colon, wrap it in quotes — otherwise the skills.sh CLI silently skips it.

## License

[MIT](LICENSE) — applies to this repo and all skills unless a skill's `SKILL.md` states otherwise. Exception: `pdf-to-markdown` is proprietary (Nutrient) — see its SKILL.md for terms.
