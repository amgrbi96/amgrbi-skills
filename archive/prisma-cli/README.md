# PRISMA-cli Skill

[![skills.sh](https://skills.sh/b/amgrbi96/PRISMA-cli-skill)](https://skills.sh/amgrbi96/PRISMA-cli-skill)

An agent skill that guides AI coding assistants through the [PRISMA Literature Review Pipeline](https://github.com/amgrbi96/PISMA-Literature-Review-Pipeline-Automation-Tool) — from installation to running systematic literature reviews.

## What it does

The skill enables your AI agent to:

- **Install** the PRISMA pipeline (clone from the enhanced fork, venv, dependencies) if not already present
- **Configure** literature reviews with proper screening providers, discovery sources, and thresholds
- **Run** the pipeline from any directory with correct CLI flags
- **Troubleshoot** common issues (rate limits, missing deps, config errors)

The PRISMA pipeline discovers papers from scholarly APIs (OpenAlex, Semantic Scholar, Crossref, PubMed, Europe PMC, etc.), deduplicates with full audit trails, screens with two-pass (title/abstract → full text) heuristic or LLM-based scoring, verifies sources against known databases, and generates PRISMA 2020 flow outputs.

## Install

```bash
npx skills add amgrbi96/PRISMA-cli-skill
```

Works with Claude Code, Cursor, Codex, and 50+ other AI coding agents.

## Requirements

- **Python >= 3.11** — for the PRISMA pipeline itself
- **Git** — to clone the pipeline repo
- API keys only needed for non-heuristic screening (OpenAI, Gemini, etc.)

## Quick start

After installing the skill, just tell your agent:

> "I want to do a systematic literature review on machine learning in drug discovery"

The skill will guide the agent through installation (if needed), configuration, and running the review.

## Skill structure

```
├── SKILL.md                    # Main instructions loaded on skill activation
├── references/
│   ├── flags.md                # Complete CLI flag reference
│   ├── providers.md            # Screening provider setup guides
│   └── config-template.json    # Copy-pasteable config template
└── scripts/
    └── run-review              # Auto-locates pipeline, runs with any flags
```

## License

MIT
