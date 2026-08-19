# Source Code Verification Findings

Date: 2026-05-27 (final — all 6 verification agents + manual config.py review)

Source repo: `CarinaSchoppe/PISMA-Literature-Review-Pipeline-Automation-Tool`

Files verified: `pyproject.toml`, `pipeline_controller.py`, `ai_screener.py`, `deduplication.py`, `topic_prefilter.py`, `pubmed_client.py`, `report_generator.py`, `relevance_scoring.py`, `text_processing.py`, `citation_expander.py`, `openalex_client.py`, `semantic_scholar_client.py`, `crossref_client.py`, `arxiv_client.py`, `config.py`, `protocols.py`, `CLI_REFERENCE.md`

---

## CRITICAL DISCREPANCIES (Must Fix)

### C1. Default Topic Prefilter Model is WRONG

**Our docs say:** `sentence-transformers/all-MiniLM-L6-v2`
**Code says:** `BAAI/bge-small-en-v1.5`

Source: `config.py` → `ApiSettings.topic_prefilter_model` default = `os.getenv("HF_TOPIC_MODEL", "BAAI/bge-small-en-v1.5")`

**Files affected:** `references/flags.md`, `references/config-template.json`

### C2. Default OpenAI Model is gpt-5.4, Not gpt-4o

**Our providers.md says:** `"openai_model": "gpt-4o"` and `OPENAI_MODEL` default `gpt-4o`
**Code says:** `"gpt-5.4"` and `os.getenv("OPENAI_MODEL", "gpt-5.4")`

**File affected:** `references/providers.md`

### C3. Default HF Local Model is Qwen3-14B, Not Qwen3-8B

**Our providers.md says:** `"huggingface_model": "Qwen/Qwen3-8B"`
**Code says:** `"Qwen/Qwen3-14B"` and `os.getenv("HF_MODEL_ID", "Qwen/Qwen3-14B")`

**File affected:** `references/providers.md`

### C4. Many Config Defaults Differ from Our Template

| Field | Our template | Code default | 
|---|---|---|
| `relevance_threshold` | 50 | 70.0 |
| `max_papers_to_analyze` | 40 | 50 |
| `full_text_max_chars` | 8000 | 12000 |
| `results_per_page` | 20 | 25 |
| `llm_provider` | "heuristic" | "auto" |
| `maybe_threshold_margin` | 0 | 10.0 |
| `max_workers` | 2 | 4 |
| `year_range_start` | 2020 | 2018 |
| `arxiv_enabled` | true | false |
| `output_sqlite_exports` | false | true |
| `verbosity` | "verbose" | "ultra_verbose" |
| `http_cache_enabled` | false | true |
| `http_cache_ttl_seconds` | null | 86400 |
| `http_retry_max_attempts` | null | 4 |
| `http_retry_base_delay_seconds` | null | 1.0 |
| `http_retry_max_delay_seconds` | null | 30.0 |
| `log_http_requests` | false | true |
| `log_http_payloads` | false | true |
| `log_llm_prompts` | false | true |
| `log_llm_responses` | false | true |
| `log_screening_decisions` | false | true |
| `min_discovered_records` | null | 0 |
| `topic_prefilter_min_keyword_matches` | 0 | 1 |
| `title_similarity_threshold` | 0.9 | 0.92 |

**File affected:** `references/config-template.json`

### C5. flags.md Default Columns Are Wrong

| Flag | Our default | Code default |
|---|---|---|
| `--threshold` | 50 | 70 |
| `--results-per-page` | 10 | 25 |
| `--max-workers` | (blank) | 4 |
| `--full-text-max-chars` | 8000 | 12000 |
| `--maybe-threshold-margin` | 0 | 10 |

**File affected:** `references/flags.md`

---

## CONFIRMED Findings (No Changes Needed)

### 1. Install Command is Correct

`pip install -e ".[dev,local-llm]"` covers all dependencies. No missing packages. `coverage` is oddly in base deps (typically dev-only).

### 2. Topic Prefilter Uses `transformers` Directly

Lazy imports of `torch` and `transformers`. Manual mean-pooling + L2 normalization. The `sentence-transformers` package is NOT used — but the model name `sentence-transformers/all-MiniLM-L6-v2` is still a valid HuggingFace model ID loadable by raw `transformers`.

### 3. Deduplication Runs Twice

After discovery and after citation snowballing.

### 4. Heuristic Screening is Pure Rule-Based

Weighted formula: 40% topic + 20% methodology + 15% theoretical + 10% recency + 15% citation, minus penalties. Keyword matching is exact substring after normalization. No ML model.

### 5. Citation Snowballing is Depth-1

Both backward (references) and forward (citations). Single pass, no recursion. Per-paper limit: 10 per direction (hardcoded). OpenAlex is the sole citation backend. Seed count: `max(5, max_papers_to_analyze // 2)`.

### 6. LOW_RELEVANCE Papers Are Saved

All papers in `papers.csv` with prefilter fields. Also in `excluded_papers.csv` when `filter_low_relevance` is enabled.

### 7. LLM Screening Has Two Stages

Triage (include/maybe/exclude) then detailed scoring.

### 8. No MeSH Term Support

PubMed client sends plain queries with `[pdat]` date filter. No controlled vocabulary.

### 9. No Search Strategy Documentation Output

Queries not saved to output artifacts. PRISMA flow has counts only.

### 10. run_config.json IS Generated

Via `ResearchConfig.save_snapshot()` — writes to `results_dir / "run_config.json"` with redacted API keys. Our SKILL.md listing is correct.

### 11. All 11 Output Artifacts Verified

papers.csv, included_papers.csv, excluded_papers.csv, top_papers.json (up to 25), citation_graph.json, prisma_flow.json, prisma_flow.md, review_summary.md, included_papers.db, excluded_papers.db, run_config.json.

---

## ADDITIONAL FINDINGS

### A1. Analysis Pass Supports Two Separator Formats

- **Colon** (simpler): `name:provider:threshold[:decision_mode[:margin]]`
- **Pipe** (extended): `name|provider|threshold|decision_mode|margin[|model_name|min_input_score]`

Our providers.md only documents the pipe format.

### A2. "auto" Provider Falls Back to "heuristic"

When `llm_provider="auto"`, `resolved_analysis_passes` creates a default pass with provider "heuristic". "auto" means "auto-detect", not a separate provider.

### A3. AnalysisPassConfig Does NOT Support "auto"

The `AnalysisPassConfig.llm_provider` literal only allows: `heuristic`, `openai_compatible`, `gemini`, `ollama`, `huggingface_local`. "auto" is only valid for the global `llm_provider` field.

### A4. Many CLI Flags Not in Our flags.md

Missing from our documentation: `--ui`, `--wizard`, `--profile-name`, `--relevant-pdfs-dir`, `--fixture-data`, `--topic-prefilter-model`, `--decision-mode`, `--maybe-threshold-margin`, `--full-text-max-chars`, `--llm-temperature`, `--huggingface-cache-dir`, `--huggingface-trust-remote-code`, `--openai-api-key` (and all other direct API key flags), per-source `--*-calls-per-second` for ALL sources, `--openai-base-url`, `--openai-model`, `--gemini-api-key`, `--gemini-base-url`, `--gemini-model`, `--ollama-base-url`, `--ollama-model`, `--ollama-api-key`, `--huggingface-model`, `--huggingface-task`, `--huggingface-device`, `--huggingface-dtype`, `--huggingface-max-new-tokens`, `--unpaywall-email`.

### A5. Per-Source Rate Limit Defaults

| Source | Calls/second |
|---|---|
| OpenAlex | 5.0 |
| Semantic Scholar | 3.0 |
| Crossref | 2.5 |
| Springer | 1.0 |
| arXiv | 0.34 |
| PubMed | 3.0 |
| Europe PMC | 2.0 |
| CORE | 1.5 |
| Unpaywall | 2.0 |
| Google Scholar | 0.2 |

### A6. SKILL.md References "MiniLM" but Code Uses "bge-small"

SKILL.md and flags.md describe the prefilter as using "MiniLM" or "all-MiniLM-L6-v2", but the actual default is `BAAI/bge-small-en-v1.5`. Help text in argparse still says "MiniLM-style topic gate" — this appears to be legacy text in the upstream code.

---

## ACTIONS

- [ ] **Fix config-template.json** — align ALL defaults with code (C4 table)
- [ ] **Fix flags.md** — update default model, update all "Default" columns, add missing flags
- [ ] **Fix providers.md** — update OpenAI default model (gpt-5.4), HF default model (Qwen3-14B)
- [ ] **Fix flags.md** — add note about two analysis-pass formats (colon and pipe)
- [ ] **Consider SKILL.md notes** about: MeSH gap, search strategy gap, snowballing depth-1
