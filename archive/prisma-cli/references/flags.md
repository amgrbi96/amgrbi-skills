# PRISMA Pipeline — Complete Flag Reference

> **Defaults note:** Values in the "Default" column are the skill's recommended defaults for systematic reviews (high recall). The upstream pipeline's own defaults are more conservative (e.g., threshold 70, balanced strategy, strict mode). See `SKILL.md → Systematic Review Defaults` for the full comparison.

## Table of Contents
- [Review Brief](#review-brief)
- [Discovery Sources](#discovery-sources)
- [Manual Import Sources](#manual-import-sources)
- [Discovery Breadth](#discovery-breadth)
- [Run Mode](#run-mode)
- [Screening](#screening)
- [Topic Prefilter](#topic-prefilter)
- [Google Scholar](#google-scholar)
- [PDF Handling](#pdf-handling)
- [Output](#output)
- [Rate Limiting](#rate-limiting)
- [Rerun Modes](#rerun-modes)
- [Workers & Threading](#workers--threading)
- [Logging](#logging)
- [Advanced Runtime](#advanced-runtime)
- [Verbosity](#verbosity)
- [Environment Variables](#environment-variables)

## Review Brief

| Flag | Type | Default | Description |
|---|---|---|---|
| `--topic` | str | required | Research topic area |
| `--research-question` | str | | Explicit research question |
| `--review-objective` | str | | Intended review output |
| `--keywords` | str | | Search terms (comma/semicolon/newline separated) |
| `--boolean` | str | `AND` | Boolean operator for queries |
| `--inclusion-criteria` | str | | Positive screening rules |
| `--exclusion-criteria` | str | | Negative screening rules |
| `--banned-topics` | str | | Hard thematic bans |
| `--excluded-title-terms` | str | `correction;erratum;editorial;retraction` | Title markers to drop |

## Discovery Sources

All default to enabled unless toggled.

| Flag | Source | Default |
|---|---|---|
| `--openalex-enabled` / `--no-openalex-enabled` | OpenAlex | enabled |
| `--semantic-scholar-enabled` / `--no-semantic-scholar-enabled` | Semantic Scholar | enabled |
| `--crossref-enabled` / `--no-crossref-enabled` | Crossref | enabled |
| `--springer-enabled` / `--no-springer-enabled` | Springer | disabled |
| `--arxiv-enabled` / `--no-arxiv-enabled` | arXiv | disabled |
| `--include-pubmed` / `--no-include-pubmed` | PubMed | enabled |
| `--europe-pmc-enabled` / `--no-europe-pmc-enabled` | Europe PMC | enabled |
| `--core-enabled` / `--no-core-enabled` | CORE | disabled |
| `--google-scholar-enabled` / `--no-google-scholar-enabled` | Google Scholar | disabled |

Stage toggles:

| Flag | Description |
|---|---|
| `--discovery-stage-enabled` / `--no-discovery-stage-enabled` | Run discovery |
| `--ai-evaluation-enabled` / `--no-ai-evaluation-enabled` | Run screening |

## Manual Import Sources

Import existing paper collections instead of discovering from APIs.

| Flag | Description |
|---|---|
| `--fixture-data` | Bulk import from fixture JSON |
| `--manual-source-path` | Import from a CSV or JSON export |
| `--google-scholar-import-path` | Import previously scraped Google Scholar data |
| `--researchgate-import-path` | Import ResearchGate export files |

## Discovery Breadth

| Flag | Default | Description |
|---|---|---|
| `--pages` | | Pages per source (omit for no limit) |
| `--results-per-page` | | Results per page (omit for no limit) |
| `--max-discovered-records` | | Hard cap on deduplicated results (omit for no limit) |
| `--min-discovered-records` | 0 | Minimum results before screening |
| `--max-papers` | | Cap on papers sent to screening (omit for no limit) |
| `--year-start` | 2018 | Start year filter |
| `--year-end` | 2026 | End year filter |
| `--discovery-strategy` | `broad` | `precise`, `balanced`, or `broad` |
| `--citation-snowballing` | enabled | Enable citation expansion |
| `--snowballing-depth` | 2 | Iteration depth for citation snowballing |
| `--snowballing-per-direction-limit` | 15 | Max papers per direction (backward/forward) per seed |
| `--mesh-expansion-enabled` | on | Auto-expand PubMed queries with MeSH terms |
| `--skip-discovery` | off | Reuse stored papers |

## Run Mode

| Flag | Default | Description |
|---|---|---|
| `--run-mode` | `analyze` | `collect` (discovery only) or `analyze` (full pipeline) |

Legacy compatibility:
- `run_mode=collect` maps to discovery enabled, AI evaluation disabled
- `run_mode=analyze` maps to AI evaluation enabled
- `skip_discovery=true` maps to discovery disabled

Prefer the explicit stage toggles (`--discovery-stage-enabled`, `--ai-evaluation-enabled`) for new configurations. `--run-mode` remains supported as a compatibility flag.

## Screening

| Flag | Default | Description |
|---|---|---|
| `--llm-provider` | `auto` | `auto`, `heuristic`, `openai_compatible`, `gemini`, `ollama`, `huggingface_local` |
| `--threshold` | 55 | Relevance threshold (0-100) |
| `--decision-mode` | `triage` | `strict` or `triage` |
| `--maybe-threshold-margin` | 15 | Margin below threshold for `maybe` in triage mode |
| `--analyze-full-text` | off | Use extracted PDF text |
| `--full-text-max-chars` | 12000 | Max chars from PDF |
| `--llm-temperature` | 0.1 | Sampling temperature for LLM providers |
| `--screening-confidence-threshold` | 80 | Confidence threshold for screening decisions (0-100) |
| `--rob-confidence-threshold` | 80 | Confidence threshold for risk-of-bias judgments (0-100) |
| `--extraction-confidence-threshold` | 85 | Confidence threshold for data extraction (0-100) |
| `--grade-confidence-threshold` | 75 | Confidence threshold for GRADE ratings (0-100) |

Multi-pass supports two formats:

Colon format (simple): `name:provider:threshold[:decision_mode[:margin]]`
```bash
--analysis-pass "fast:heuristic:65:strict:10"
```

Pipe format (extended): `name|provider|threshold|decision_mode|margin[|model_name|min_input_score]`
```bash
--analysis-pass "fast|huggingface_local|65|strict|8|Qwen/Qwen3-14B|0"
--analysis-pass "final|openai_compatible|88|strict|5|gpt-5.4|80"
```

Note: `auto` is only valid for the global `--llm-provider` flag. Individual analysis passes must specify a concrete provider.

## Topic Prefilter

| Flag | Default | Description |
|---|---|---|
| `--topic-prefilter-enabled` | on | Enable semantic gate |
| `--topic-prefilter-filter-low-relevance` | off | Auto-exclude low relevance |
| `--topic-prefilter-high-threshold` | 0.75 | HIGH_RELEVANCE threshold |
| `--topic-prefilter-review-threshold` | 0.45 | REVIEW threshold |
| `--topic-prefilter-text-mode` | `title_abstract` | `title_only`, `title_abstract`, `title_abstract_full_text` |
| `--topic-prefilter-max-chars` | 4000 | Max text for embedding |
| `--topic-prefilter-model` | `BAAI/bge-small-en-v1.5` | Embedding model (loaded via `transformers`, not `sentence-transformers` package) |
| `--topic-prefilter-weighted-keywords` | | `"keyword|weight|threshold; ..."` |
| `--topic-prefilter-min-keyword-matches` | 1 | Min matches for STRONG_FIT |
| `--topic-prefilter-match-threshold` | 55 | STRONG_FIT score threshold |
| `--topic-prefilter-near-fit-threshold` | 35 | NEAR_FIT score threshold |

Weighted keyword syntax: `keyword`, `keyword|weight`, or `keyword|weight|threshold`.
Example: `"systematic review|1.8|70; large language models|1.4|60"`

## Google Scholar

| Flag | Default | Description |
|---|---|---|
| `--google-scholar-pages` | 1 | Number of result pages |
| `--google-scholar-page-min` | 1 | Lower bound for pages |
| `--google-scholar-page-max` | 100 | Upper bound for pages |
| `--google-scholar-results-per-page` | 10 | Expected page size |
| `--google-scholar-calls-per-second` | 0.2 | Throttle rate |

Behavior:
- Each configured page is fetched in order
- Partial page failures are logged and skipped
- The run stops early if the configured per-source limit is reached
- Metadata is deduplicated afterward through the normal DOI and title-based pipeline

## PDF Handling

| Flag | Default | Description |
|---|---|---|
| `--download-pdfs` | off | Enable PDF downloads |
| `--pdf-download-mode` | `all` | `all` or `relevant_only` |
| `--pdf-batch-size` | 10 | Batch size for downloads |
| `--papers-dir` | `papers/` | Download directory |
| `--relevant-pdfs-dir` | | Kept PDFs directory |

## Output

| Flag | Default | Description |
|---|---|---|
| `--output-csv` | on | Write CSV exports |
| `--output-json` | on | Write JSON exports |
| `--output-markdown` | on | Write Markdown exports |
| `--output-sqlite-exports` | on | Write SQLite exports |
| `--output-ris` | on | Write RIS export (importable by Zotero/Covidence/Rayyan) |
| `--output-bibtex` | on | Write BibTeX export (importable by LaTeX/BibDesk) |
| `--results-dir` | `results/` | Output directory |
| `--database-path` | `data/literature_review.db` | SQLite database path |
| `--log-file-path` | | Log file path |

## Rate Limiting

General HTTP controls:

| Flag | Default | Description |
|---|---|---|
| `--http-retry-max-attempts` | 4 | Max retry attempts |
| `--http-retry-base-delay-seconds` | 1.0 | Base delay for backoff |
| `--http-retry-max-delay-seconds` | 30.0 | Max delay cap |
| `--http-cache-enabled` | on | Enable disk cache |
| `--http-cache-dir` | `data/http_cache` | Cache directory |
| `--http-cache-ttl-seconds` | 86400 | Cache TTL (24 hours) |

Per-source rate limits:

| Flag | Default | Description |
|---|---|---|
| `--openalex-calls-per-second` | 5.0 | OpenAlex throttle rate |
| `--semantic-scholar-calls-per-second` | 3.0 | Semantic Scholar throttle rate |
| `--crossref-calls-per-second` | 2.5 | Crossref throttle rate |
| `--springer-calls-per-second` | 1.0 | Springer throttle rate |
| `--arxiv-calls-per-second` | 0.34 | arXiv throttle rate |
| `--pubmed-calls-per-second` | 3.0 | PubMed throttle rate |
| `--europe-pmc-calls-per-second` | 2.0 | Europe PMC throttle rate |
| `--core-calls-per-second` | 1.5 | CORE throttle rate |
| `--unpaywall-calls-per-second` | 2.0 | Unpaywall throttle rate |
| `--google-scholar-calls-per-second` | 0.2 | Google Scholar throttle rate |

Semantic Scholar controls:

| Flag | Default | Description |
|---|---|---|
| `--semantic-scholar-max-requests-per-minute` | 120 | Rate limit for S2 |
| `--semantic-scholar-request-delay-seconds` | 0.0 | Delay between S2 requests |
| `--semantic-scholar-retry-attempts` | 4 | S2 retry count |
| `--semantic-scholar-retry-backoff-strategy` | `exponential` | `exponential`, `fixed`, or `linear` |
| `--semantic-scholar-retry-backoff-base-seconds` | 2.0 | Base seconds for backoff |

Backoff behavior:
- Proactive throttling runs before requests are sent
- `Retry-After` is respected when present
- Bounded exponential backoff is the default fallback
- Exhausted retry paths fail cleanly and log the reason

## Rerun Modes

| Flag | Description |
|---|---|
| `--partial-rerun-mode` | `off`, `reporting_only`, `screening_and_reporting`, `pdfs_screening_reporting` |
| `--resume-mode` | Reuse cached screening |
| `--reset-query-records` | Delete stored papers for query |
| `--clear-screening-cache` | Delete cached screening results |

## Workers & Threading

| Flag | Default | Description |
|---|---|---|
| `--max-workers` | 4 | Global worker fallback |
| `--discovery-workers` | 0 | Discovery-stage override (0 = inherit `max_workers`) |
| `--io-workers` | 0 | PDF and full-text preparation override |
| `--screening-workers` | 0 | Screening worker override |

`max_workers` controls the global thread-pool fallback. `discovery_workers`, `io_workers`, and `screening_workers` can override that value per stage. A value of `0` means "inherit the global value".

## Logging

| Flag | Default | Description |
|---|---|---|
| `--log-http-requests` | on | Log all HTTP requests |
| `--log-http-payloads` | on | Log HTTP request/response payloads |
| `--log-llm-prompts` | on | Log prompts sent to LLM providers |
| `--log-llm-responses` | on | Log raw LLM responses |
| `--log-screening-decisions` | on | Log per-paper screening decisions |

Critical for debugging provider issues. Disable them with `--no-` prefix to reduce log volume.

## Advanced Runtime

| Flag | Description |
|---|---|
| `--incremental-report-regeneration` | Skip rewriting unchanged report artifacts |
| `--enable-async-network-stages` | Use async orchestration for network-heavy stages |
| `--request-timeout-seconds` | HTTP timeout (default: 30) |
| `--resume-mode` | Reuse cached screening and skip repeated work where valid |
| `--title-similarity-threshold` | Title-similarity fallback threshold for deduplication (default: 0.92) |
| `--data-dir` | Directory for pipeline state and SQLite artifacts (default: `data/`) |
| `--disable-progress-bars` | Disable tqdm progress bars |

## Verbosity

| Flag | Default | Description |
|---|---|---|
| `--verbosity` | `normal` | Logging mode: `normal`, `verbose`, `ultra_verbose`, `debug`, `quiet` |

| Level | Shows |
|---|---|
| `normal` | Stage boundaries, warnings |
| `verbose` | All steps, screening outcomes |
| `ultra_verbose` | Request traces, per-paper details |
| `debug` | Debug-level internals |
| `quiet` | Minimal output |

Shortcuts: `--verbose`, `--ultra-verbose`

## Interactive & UI Modes

| Flag | Default | Description |
|---|---|---|
| `--ui` | off | Launch the guided Tkinter desktop workbench |
| `--wizard` | off | Force the text-based interactive wizard |
| `--profile-name` | | Name for saving/loading UI profiles |
| `--ui-settings-mode` | `compact` | Settings density in desktop workbench (`compact` or `advanced`) |
| `--ui-show-advanced-settings` | off | Reveal advanced settings pages by default in workbench |

When no topic or keywords are provided and no config file is set, the pipeline enters interactive mode automatically.

## Provider Configuration Flags

These flags override environment variables and config file values.

| Flag | Description |
|---|---|
| `--openai-api-key` | OpenAI API key |
| `--openai-base-url` | OpenAI-compatible endpoint URL |
| `--openai-model` | OpenAI model name (default: `gpt-5.4`) |
| `--gemini-api-key` | Google Gemini API key |
| `--gemini-base-url` | Gemini endpoint URL |
| `--gemini-model` | Gemini model name (default: `gemini-2.5-flash`) |
| `--ollama-base-url` | Ollama endpoint URL |
| `--ollama-model` | Ollama model tag (default: `qwen3:8b`) |
| `--ollama-api-key` | Ollama API key |
| `--huggingface-model` | HF model id (default: `Qwen/Qwen3-14B`) |
| `--huggingface-task` | HF pipeline task (default: `text-generation`) |
| `--huggingface-device` | HF device (default: `auto`) |
| `--huggingface-dtype` | HF dtype (default: `auto`) |
| `--huggingface-max-new-tokens` | Max tokens for local generation (default: 700) |
| `--huggingface-cache-dir` | Model cache directory |
| `--huggingface-trust-remote-code` | Allow custom model code |
| `--semantic-scholar-api-key` | Semantic Scholar API key |
| `--springer-api-key` | Springer API key |
| `--core-api-key` | CORE API key |
| `--unpaywall-email` | Email for Unpaywall PDF lookups |
| `--crossref-mailto` | Email for Crossref polite pool |

## Environment Variables

### API Keys & Endpoints

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENAI_BASE_URL` | OpenAI-compatible endpoint URL |
| `OPENAI_MODEL` | Default OpenAI model |
| `GEMINI_API_KEY` | Google Gemini API key |
| `GOOGLE_API_KEY` | Alternative Gemini key |
| `GEMINI_BASE_URL` | Gemini endpoint URL |
| `GEMINI_MODEL` | Default Gemini model |
| `OLLAMA_BASE_URL` | Ollama endpoint URL |
| `OLLAMA_MODEL` | Default Ollama model |
| `OLLAMA_API_KEY` | Ollama API key |
| `SEMANTIC_SCHOLAR_API_KEY` | Semantic Scholar access |
| `SPRINGER_API_KEY` | Springer access |
| `CORE_API_KEY` | CORE access |
| `UNPAYWALL_EMAIL` | PDF metadata lookup |
| `CROSSREF_MAILTO` | Crossref polite pool |

### Hugging Face Local

| Variable | Purpose |
|---|---|
| `HF_MODEL_ID` | Default local model |
| `HF_TASK` | Pipeline task (e.g. `text-generation`) |
| `HF_DEVICE` | Device override (e.g. `cpu`, `cuda`) |
| `HF_DTYPE` | Data type override (e.g. `float32`, `auto`) |
| `HF_MAX_NEW_TOKENS` | Max new tokens for generation |
| `HF_HOME` / `TRANSFORMERS_CACHE` | Model cache directory |
| `HF_TRUST_REMOTE_CODE` | Allow remote code execution |

### Topic Prefilter Model

| Variable | Purpose |
|---|---|
| `HF_TOPIC_MODEL` | Override the default embedding model for topic prefilter (default: `BAAI/bge-small-en-v1.5`) |

### Per-Source Rate Limits

| Variable | Default | Purpose |
|---|---|---|
| `OPENALEX_CALLS_PER_SECOND` | 5.0 | OpenAlex throttle |
| `SEMANTIC_SCHOLAR_CALLS_PER_SECOND` | 3.0 | Semantic Scholar throttle |
| `CROSSREF_CALLS_PER_SECOND` | 2.5 | Crossref throttle |
| `SPRINGER_CALLS_PER_SECOND` | 1.0 | Springer throttle |
| `ARXIV_CALLS_PER_SECOND` | 0.34 | arXiv throttle |
| `PUBMED_CALLS_PER_SECOND` | 3.0 | PubMed throttle |
| `EUROPE_PMC_CALLS_PER_SECOND` | 2.0 | Europe PMC throttle |
| `CORE_CALLS_PER_SECOND` | 1.5 | CORE throttle |
| `UNPAYWALL_CALLS_PER_SECOND` | 2.0 | Unpaywall throttle |
| `GOOGLE_SCHOLAR_CALLS_PER_SECOND` | 0.2 | Google Scholar throttle |

### Semantic Scholar Rate Limits

| Variable | Default | Purpose |
|---|---|---|
| `SEMANTIC_SCHOLAR_MAX_REQUESTS_PER_MINUTE` | 120 | Proactive RPM ceiling |
| `SEMANTIC_SCHOLAR_REQUEST_DELAY_SECONDS` | 0.0 | Extra inter-request delay |
| `SEMANTIC_SCHOLAR_RETRY_ATTEMPTS` | 4 | 429 retry count |
| `SEMANTIC_SCHOLAR_RETRY_BACKOFF_STRATEGY` | `exponential` | Backoff type |
| `SEMANTIC_SCHOLAR_RETRY_BACKOFF_BASE_SECONDS` | 2.0 | Base delay for backoff |

### Shared

| Variable | Purpose |
|---|---|
| `LLM_TEMPERATURE` | Generation temperature (all providers) |
