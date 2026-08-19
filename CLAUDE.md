# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A monorepo of Claude Code skills. Each skill lives in its own directory under `skills/`. Deferred skills live in `archive/` — kept in git but not discoverable/installable via skills.sh.

## Repository Structure

```
skills/
  parsing/               ← Document-parsing cluster
    pymupdf-pdf/         ← Fast local PDF parsing with PyMuPDF (md/json/images/tables)
      SKILL.md           ← Skill definition (frontmatter + usage)
      references/        ← pymupdf-notes.md (install + libstdc++ fixes)
      scripts/           ← pymupdf_parse.py
    liteparse/           ← LiteParse: local multi-format doc parsing (PDF/DOCX/img)
    mineru/              ← MinerU: cloud VLM PDF extraction with layout analysis
    parse-docs/          ← Gateway router for document-parsing skills
    pdf-to-markdown/     ← Fast PDF → Markdown extraction
  pdf-tools/             ← Puppeteer HTML→PDF, PDF/A, signing, qpdf (page edits → pymupdf-pdf)
  openwa/                ← OpenWA WhatsApp API Gateway guide

archive/                 ← Deferred: prospero-search, prisma-cli, flashcards
```

- **`CLAUDE.md`** (this file) — repo-level development guidance, not distributed with any skill.
- Each skill folder is self-contained and independently installable.

## Testing

No unit test suite, no build step, no linting. Validation is live (API calls, script `--help`).

## Modifying Skills

When editing any `SKILL.md`, note:
- The frontmatter `description` field controls when the skill triggers — keep it comprehensive with synonyms and use-case phrases.
- The workflow is linear (6 steps). Maintain this structure; agents follow it sequentially.
- References to `references/` files are intentional — detailed specs live there to keep `SKILL.md` focused on workflow logic.

## Adding a New Skill

1. Create `skills/<skill-name>/SKILL.md` with frontmatter (`name`, `description`) and workflow instructions.
2. Add supporting files (`references/`, `scripts/`) inside the skill directory.
3. Update this `CLAUDE.md` if the new skill has testing or setup requirements.
