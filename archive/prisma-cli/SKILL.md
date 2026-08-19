---
name: prisma-cli
description: "Use when running or configuring the PRISMA Literature Review Pipeline, constructing CLI commands, setting up literature review runs, choosing screening providers, configuring discovery sources, interpreting output artifacts, or creating per-project config files. Also use when the user mentions systematic reviews, literature screening, paper discovery, PRISMA flow, citation snowballing, or anything related to academic paper search and analysis — even if they don't explicitly name the tool."
---

# PRISMA Pipeline CLI

Systematic literature review tool: discovers papers from scholarly APIs, deduplicates, screens with heuristic or LLM-based scoring, and generates PRISMA flow outputs. The pipeline includes enhancements for systematic review rigor: two-pass screening (title/abstract → full text), MeSH term expansion, source verification, search reproducibility checks, structured exclusion codes, and staged crash-recovery checkpoints.

## Quick Start

```bash
bash scripts/run-review --topic "AI in healthcare" --keywords "LLM,clinical,evaluation"
```

The script handles everything: finding the pipeline, setting up output directories, and running the review.

**Before the first run**, add `prisma-results/` to your project's `.gitignore`.

## How It Works

When you run `scripts/run-review`, it automatically:

1. **Locates the pipeline** — checks `$PRISMA_ROOT`, then `~/.prisma-pipeline/`
2. **Creates output directories** under `<project-root>/prisma-results/`
3. **Injects path defaults** for results, database, papers, and logs
4. **Injects systematic review defaults** — threshold, triage mode, broad strategy, PubMed, Europe PMC (see table below)
5. **Runs the pipeline** with your flags plus the resolved paths

Override any auto-set flag explicitly — the script only injects defaults for flags you don't provide.

## Pipeline Capabilities

The pipeline covers the full Phase 2 (Investigation) lifecycle:

### Discovery
- **9 scholarly sources**: OpenAlex, Semantic Scholar, Crossref, PubMed, Europe PMC, Springer, arXiv, CORE, Google Scholar
- **MeSH term expansion** — PubMed queries auto-expanded with Medical Subject Headings for broader medical coverage (`--mesh-expansion-enabled`)
- **Configurable citation snowballing** — iteratively fetches references and citations from seed papers (depth and per-direction limit configurable)
- **Multiple import paths** — fixture JSON, CSV/JSON exports, Google Scholar scrapes, ResearchGate exports

### Deduplication
- **DOI-based + title-similarity dedup** with configurable threshold (`--title-similarity-threshold 0.92`)
- **Full audit trail** — every dedup decision logged with method, similarity score, and reason (`dedup_audit_trail.json`)

### Screening
- **Two-pass screening** — Pass 1: title/abstract (T/A) → Pass 2: full text (FT), each with independent decisions and confidence scores
- **6 screening providers**: heuristic, OpenAI-compatible, Gemini, Ollama, HuggingFace local, or auto
- **Structured exclusion codes** — 8 standardized reasons (POP_MISMATCH, INT_MISMATCH, OUT_MISMATCH, DESIGN_MISMATCH, LANGUAGE, DUPLICATE, FULL_TEXT_UNAVAILABLE, OTHER)
- **Per-decision confidence scores** — multi-factor (relevance + criteria match + LLM signal), with configurable thresholds per decision type

### Verification & Quality
- **Metadata quality gate** — pre-screening check validates titles, abstracts, authors, year across all sources (`metadata_quality.json`)
- **Source verification** — Tier 0 (Semantic Scholar/PubMed identifier lookup) + Tier 1 (Crossref DOI resolution). Papers rated VERIFIED/PLAUSIBLE/UNVERIFIABLE/FABRICATED. Fabricated papers removed automatically.
- **Search reproducibility** — re-executes PubMed queries and compares counts (≤5% VERIFIED, 5-20% APPROXIMATE, >20% UNVERIFIED)
- **Count consistency checks** — cross-component verification (discovery → dedup → screening counts)

### Crash Recovery
- **Staged checkpoints** — persisted after discovery, deduplication, and screening stages (`checkpoint_post_discovery.json`, `checkpoint_post_dedup.json`, `checkpoint_post_screening.json`)
- **Gate mechanism** — composable preconditions evaluated before each phase transition

### Outputs
- **PRISMA 2020 flow diagram** — JSON, Markdown, and Mermaid formats
- **Search strategy documentation** — reproducible markdown + JSON with per-source queries, timestamps, and counts
- **RIS/BibTeX export** — importable by Zotero, Covidence, Rayyan, LaTeX, BibDesk
- **SQLite databases** — included and excluded papers in queryable format
- **Full lineage tracking** — source_database, screening_pass, ta/ft decisions, confidence scores, exclusion_stage on every paper

## First-Time Setup

### Step 1 — Install the pipeline (one-time, requires Python >= 3.11)

```bash
git clone https://github.com/amgrbi96/PISMA-Literature-Review-Pipeline-Automation-Tool.git ~/.prisma-pipeline
cd ~/.prisma-pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev,local-llm]"
```

### Step 2 — Verify

```bash
~/.prisma-pipeline/.venv/bin/python3 ~/.prisma-pipeline/main.py --help
```

### Step 3 — Add to .gitignore

Add this to your project's `.gitignore`:

```
prisma-results/
```

## Output Structure

All outputs land in `<project-root>/prisma-results/`:

```
prisma-results/
  results/                     # --results-dir
    papers.csv                 # All discovered papers
    included_papers.csv        # Papers that passed screening
    excluded_papers.csv        # Papers that failed screening
    top_papers.json            # Ranked results
    citation_graph.json        # Citation network
    prisma_flow.json / .md     # PRISMA flow diagram data
    prisma_flow.mermaid        # Mermaid flowchart (renderable on GitHub)
    search_strategy.md         # Reproducible search strategy documentation
    search_strategy.json       # Search strategy in structured JSON
    papers.ris                 # RIS export for Zotero/Covidence/Rayyan
    papers.bib                 # BibTeX export for LaTeX/BibDesk
    metadata_quality.json      # Per-source metadata completeness report
    retrieval_log.json         # PDF retrieval status per paper
    source_verification.json   # Source verification verdicts (S2/PubMed/Crossref)
    search_reproducibility.json # Search re-execution comparison results
    dedup_audit_trail.json     # Deduplication decisions (kept vs removed)
    checkpoint_*.json          # Staged checkpoints (post_discovery, post_dedup, post_screening)
    review_summary.md          # Human-readable summary
    included_papers.db         # SQLite export of included
    excluded_papers.db         # SQLite export of excluded
    run_config.json            # Run config snapshot (redacted API keys)
  data/
    review.db                  # --database-path
  papers/                      # --papers-dir (downloaded PDFs)
  logs/
    pipeline.log               # --log-file-path
```

## Using a Config File

For repeatable or complex reviews, use a config file:

```bash
bash scripts/run-review --config-file path/to/config.json
```

**Important:** when using `--config-file`, the script does NOT auto-set paths. Your config must include absolute paths for `results_dir`, `database_path`, etc. See `references/config-template.json` for all available settings.

## Run Modes

| Mode | Behavior |
|---|---|
| `--run-mode collect` | Discovery only — collect metadata and stop |
| `--run-mode analyze` | Full pipeline — discover, screen, generate reports |

Prefer explicit stage toggles for new configurations:

| What you want | Flags |
|---|---|
| Full pipeline (discover + screen) | `--discovery-stage-enabled --ai-evaluation-enabled` |
| Search only, no screening | `--discovery-stage-enabled --no-ai-evaluation-enabled` |
| Screen stored papers, no new search | `--no-discovery-stage-enabled --ai-evaluation-enabled` |
| Re-generate reports only | `--skip-discovery --partial-rerun-mode reporting_only` |
| Broad search for comprehensive reviews | Add `--discovery-strategy broad` |
| Narrow, precise search | Add `--discovery-strategy precise` |

## Screening Providers

| Provider | When to use | Key flags |
|---|---|---|
| `auto` | Auto-select best available (falls back to heuristic) | `--llm-provider auto` |
| `heuristic` | Rule-based scoring, no API keys needed | `--llm-provider heuristic` |
| `openai_compatible` | OpenAI or compatible endpoint | `--llm-provider openai_compatible` + env `OPENAI_API_KEY` |
| `gemini` | Google Gemini | `--llm-provider gemini` + env `GEMINI_API_KEY` |
| `ollama` | Local model via Ollama | `--llm-provider ollama` |
| `huggingface_local` | Local HF model, fully offline | `--llm-provider huggingface_local` |

For provider-specific config examples, read `references/providers.md`.

## Importing Existing Papers

Instead of discovering from APIs, import existing collections:

- `--fixture-data-path` — bulk import from fixture JSON
- `--manual-source-path` — import from a directory of PDFs or metadata files
- `--google-scholar-import-path` — import previously scraped Google Scholar data
- `--researchgate-import-path` — import ResearchGate export files

## Common Patterns

### Quick one-liner (no config file)
```bash
bash scripts/run-review \
  --topic "AI in healthcare" \
  --keywords "LLM,clinical,evaluation"
```

### With a specific provider
```bash
bash scripts/run-review \
  --topic "Machine learning in drug discovery" \
  --keywords "ML,pharmaceutical,compound screening" \
  --llm-provider openai_compatible
```

### Medical systematic review
```bash
bash scripts/run-review \
  --topic "AI-assisted diagnosis in radiology" \
  --keywords '"artificial intelligence"[MeSH Terms],deep learning,CT,MRI,diagnostic accuracy' \
  --inclusion-criteria "human subjects;English language;prospective study;diagnostic accuracy" \
  --exclusion-criteria "animal study;case report;review article;editorial;opinion" \
  --llm-provider gemini
```

### Advanced run with config file
```bash
bash scripts/run-review --config-file ~/my-research/config.json
```

### Quick exploration (fewer papers, faster)
```bash
bash scripts/run-review \
  --topic "AI in healthcare" \
  --keywords "LLM,clinical,evaluation" \
  --max-papers 30 \
  --pages 2 \
  --discovery-strategy balanced \
  --threshold 70
```

## Systematic Review Defaults

The skill's `config-template.json` is tuned for systematic reviews with high recall. Key differences from the pipeline's built-in defaults:

| Setting | Pipeline default | Skill default | Why |
|---|---|---|---|
| `relevance_threshold` | 70 | 55 | Include more papers — let human review decide |
| `decision_mode` | strict | triage | "Maybe" papers flagged for manual review instead of excluded |
| `maybe_threshold_margin` | 10 | 15 | Wider maybe band captures borderline papers |
| `discovery_strategy` | balanced | broad | More query variants per source = better coverage |
| `pages_to_retrieve` | 2 | unlimited | No cap — retrieve everything available |
| `max_papers_to_analyze` | 50 | unlimited | Screen all discovered papers |
| `max_discovered_records` | null | null | No cap on total unique records |
| `include_pubmed` | auto | enabled | Always search PubMed (medical focus) |
| `europe_pmc_enabled` | false | enabled | Biomedical source with PubMed Central coverage |
| `arxiv_enabled` | false | false | Not a medical source |
| `topic_prefilter_review_threshold` | 0.55 | 0.45 | More papers pass prefilter to screening stage |

Confidence thresholds (pipeline defaults, no override needed): screening 80, RoB 80, extraction 85, GRADE 75. Adjust with `--screening-confidence-threshold`, `--rob-confidence-threshold`, etc.

Use explicit limits (`--max-papers`, `--pages`) only for quick exploratory runs where speed matters more than completeness.

## Known Limitations

| Limitation | Impact | Workaround |
|---|---|---|
| Default provider is `auto` | Falls back to heuristic when no API keys set | Use `--llm-provider` explicitly for consistent behavior |
| No risk of bias assessment | No structured quality appraisal of included studies | Export via RIS/BibTeX to Covidence or similar tools |
| No data extraction templates | No structured PICO extraction | Use `included_papers.csv` and extract manually |
| No meta-analysis support | No statistical synthesis | Export to R/RevMan for quantitative analysis |
| No dual screening / kappa | No inter-rater reliability metrics | Run twice with different providers and compare |
| Google Scholar is experimental | Scraping may hit rate limits or CAPTCHAs | Enable with `--google-scholar-enabled` if needed |
| Search reproducibility only covers PubMed | Other sources not re-verified | PubMed is the primary medical database; other sources documented as NOT_VERIFIED |

## When Things Go Wrong

| Problem | Fix |
|---|---|
| `429 Too Many Requests` from Semantic Scholar | Lower `--semantic-scholar-max-requests-per-minute 15` and increase `--semantic-scholar-request-delay-seconds 2.0` |
| Topic prefilter warnings | Read `references/flags.md` → "Topic Prefilter" section |
| GUI won't open | Use `--wizard` instead, or check `python3 -c "import _tkinter"` |
| Python version error | Must be Python >= 3.11 |
| Pipeline not found | Install to `~/.prisma-pipeline/` or set `PRISMA_ROOT` |
| Outputs in wrong directory | Auto-paths only apply when NOT using `--config-file`. With a config, you control all paths. |

## Deeper Reference

- **`references/flags.md`** — Complete flag reference. Read when constructing complex CLI commands.
- **`references/providers.md`** — Provider setup guides with config examples.
- **`references/config-template.json`** — All available config fields.
- **`scripts/run-review`** — The runner script. Read when debugging path or installation issues.
