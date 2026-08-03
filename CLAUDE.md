# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A monorepo of Claude Code skills. Each skill lives in its own directory under `skills/`.

## Repository Structure

```
skills/
  flashcards/            ← High-yield flashcards from any source (book/lecture/notes)
    SKILL.md             ← Skill definition (2 branches: batch + capture)
    references/          ← card-quality.md, hint-rules.md
    scripts/             ← build_cards.py (cards.json → .md / .apkg)
  pymupdf-pdf/           ← Fast local PDF parsing with PyMuPDF (md/json/images/tables)
    SKILL.md             ← Skill definition (frontmatter + usage)
    references/          ← pymupdf-notes.md (install + libstdc++ fixes)
    scripts/             ← pymupdf_parse.py
  prospero-search/       ← PROSPERO systematic review search & duplicate check
    SKILL.md             ← Skill definition (frontmatter + workflow)
    references/          ← API specs and supporting docs
    scripts/             ← Validation scripts
  prisma-cli/            ← PRISMA literature review pipeline wrapper
    SKILL.md             ← Skill definition (frontmatter + usage guide)
    references/          ← CLI flags, providers, config template, gap analysis
    scripts/             ← run-review (pipeline runner)
  liteparse/             ← LiteParse: local multi-format doc parsing (PDF/DOCX/img)
  mineru/                ← MinerU: cloud VLM PDF extraction with layout analysis
  parse-docs/            ← Gateway router for document-parsing skills
  pdf-to-markdown/       ← Fast PDF → Markdown extraction
  pdf-tools/             ← PDF engineering (generate/merge/encrypt/fill forms)
```

- **`CLAUDE.md`** (this file) — repo-level development guidance, not distributed with any skill.
- Each skill folder is self-contained and independently installable.

## Testing

```bash
# PROSPERO skill — validate API connectivity (hits a live server)
python3 skills/prospero-search/scripts/test_api.py

# PRISMA skill — verify runner works (requires pipeline installed at ~/.prisma-pipeline)
bash skills/prisma-cli/scripts/run-review --help
```

No unit test suite, no build step, no linting. The only validation is the live API test above.

## Key Technical Details

### prospero-search

- **Auth**: PROSPERO has no API key system. Instead, generate a per-request `prospero-auth-token` header by base64-encoding the current millisecond timestamp.
- **Filter format**: Filters use `{"name": "...", "value": [...]}` objects. The API converts them into query term modifications using hidden field codes (`rs` for reviewstatus, `rt` for recordtype, `yr` for year, `re` for region, `fi` for funders). Using the wrong key name or passing a string instead of array silently returns unfiltered results. The `dateinprospero` filter does not work at the API level.
- **Rate limiting**: The API rate-limits aggressively (HTTP 429). The skill must send one request at a time with retries.
- **`download: true`** mode only adds an `ris` (RIS citation format) field per record — not useful for PICOS extraction. Use the `/api/view/<CRD>` endpoint instead for full review content.

### prisma-cli

- **Pipeline location**: The skill wraps an external pipeline installed at `~/.prisma-pipeline/` (cloned from `amgrbi96/PISMA-Literature-Review-Pipeline-Automation-Tool`). The skill repo contains no application code.
- **Install source**: Always clone from the fork, not upstream. The fork's master includes 19 enhancement commits (MeSH expansion, two-pass screening, source verification, etc.) that the skill documents.
- **Path injection**: `scripts/run-review` auto-creates `prisma-results/` under the project root and injects paths + systematic review defaults. When `--config-file` is used, no defaults are injected.
- **Config keys**: snake_case in config files, kebab-case as CLI flags. The argparse layer maps between them.

## Modifying Skills

When editing any `SKILL.md`, note:
- The frontmatter `description` field controls when the skill triggers — keep it comprehensive with synonyms and use-case phrases.
- The workflow is linear (6 steps). Maintain this structure; agents follow it sequentially.
- References to `references/` files are intentional — detailed specs live there to keep `SKILL.md` focused on workflow logic.

## Adding a New Skill

1. Create `skills/<skill-name>/SKILL.md` with frontmatter (`name`, `description`) and workflow instructions.
2. Add supporting files (`references/`, `scripts/`) inside the skill directory.
3. Update this `CLAUDE.md` if the new skill has testing or setup requirements.
