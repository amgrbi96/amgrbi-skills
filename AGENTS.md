# AGENTS.md

Repo-level guidance for AI coding agents (ZCode, Codex, Cursor, …). `CLAUDE.md` carries the same content for Claude Code — keep both in sync when editing.

## Project Overview

A monorepo of [agent skills](https://skills.sh), each self-contained and installable on its own via subpath (`npx skills add amgrbi96/amgrbi-skills/skills/parsing/<name>`). Deferred skills live in `archive/` — kept in git but not discoverable by skills.sh.

## Repository Structure

```
skills/
  parsing/               ← Document-parsing cluster; parse-docs routes to the others
    parse-docs/          ← Router skill + scripts/parse_folder.py batch orchestrator
    pdf-to-markdown/     ← Fast PDF → Markdown (bin/ wrapper + bin/check-env; arm64 only)
    pymupdf-pdf/         ← Local PyMuPDF workbench (scripts/ references/ evals/)
    liteparse/           ← Local multi-format + OCR (Node 18+, `lit` CLI, LibreOffice for Office)
    mineru/              ← Cloud VLM parser (scripts/ references/ evals/; Python 3.10+ + requests + token)
  pdf-tools/             ← Puppeteer HTML→PDF, PDF/A, signing, qpdf
  openwa/                ← OpenWA WhatsApp gateway guide
archive/                 ← Deferred: prospero-search, prisma-cli, flashcards
```

## Testing

No build step, no linting. Two skills ship offline self-test suites — **run them after changing that skill's script or any documented claim** (they catch doc drift, and they make zero network calls; never validate by spending live API quota):

```bash
python3 skills/parsing/mineru/evals/selftest.py         # 90 checks: CLI, token pool, probe, --pages chunks, SKILL.md drift
python3 skills/parsing/pymupdf-pdf/evals/smoke_test.py  # 58 cases over scripts + documented API calls
```

The mineru suite diffs SKILL.md's CLI table against the script's `--help` (flags, defaults, verified stamps) — if you add or change a flag, update SKILL.md in the same commit or the suite fails.

Skills without a suite are checked with their script's `--help`.

## Skill Conventions

- `SKILL.md` frontmatter: `name` (matches directory) + `description` — the description is the trigger; keep it comprehensive with synonyms and use-case phrases. YAML gotcha: a colon inside `description` must be quoted or skills.sh silently skips the skill.
- Progressive disclosure: body under 500 lines; deep detail goes in `references/`, executable helpers in `scripts/`, self-tests in `evals/`.
- Documented claims carry "verified <date>" stamps; re-verify against live docs when touching a skill (mineru: quarterly, per its Keeping This Skill Current section).

## Per-Skill Notes

- **mineru** — cloud-only (never the local `mineru` CLI). Python 3.10+ enforced at runtime; `requests` required for parsing but not `--help`/`--dry-run`. Tokens: `MINERU_TOKEN(S)` env or `skills/parsing/mineru/tokens.txt` (gitignored — never commit). Quota model: 1000 pages/token/day, 200 MB / 200 pages per file; `--pages` chunks write per-range folders. Its selftest is hermetic (real env tokens/tokens.txt are stripped).
- **liteparse** — global `lit` CLI; `lit --version` is misleading (hardcoded), verify with `lit parse --help`. OCR and LibreOffice are opt-in.
- **pdf-to-markdown** — arm64 Linux/macOS only (Intel Macs unsupported); `bin/check-env` pre-flight, binary self-installs on first run.
- **parse-docs** — the router; Single mode shortlists then asks the user to pick the parser (quick comparison per option); keep its command blocks and limits table in sync when sibling parsers change.

## Modifying Skills

- Keep docs and code in one commit: CLI flags, defaults, output paths, and behavior claims in `SKILL.md` must match the script (the eval suites enforce this where they exist).
- The frontmatter `description` controls triggering — update it when adding major features.

## Adding a New Skill

1. Create `skills/<name>/SKILL.md` with frontmatter (`name`, `description`).
2. Add `scripts/`, `references/`, `bin/`, or `evals/` as needed.
3. Update the structure trees in `README.md` and this file, and `README.md`'s skills table.
