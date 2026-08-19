# PRISMA Pipeline — Gap Analysis

Date: 2026-05-29 (updated after upstream gap fixes)

Based on full source code verification of `CarinaSchoppe/PISMA-Literature-Review-Pipeline-Automation-Tool` and review of the skill documentation. Gaps are split into upstream pipeline gaps (require changes to the pipeline repo) and skill gaps (fixable in this repo).

---

## Upstream Pipeline Gaps

These require changes to the PRISMA pipeline itself. The skill can only document them and suggest workarounds.

### G1. No MeSH Term Support — RESOLVED

**Severity:** Critical for medical systematic reviews
**Status:** Resolved (commit 0ac8f72 on `feature/gaps-g1-g2-g3-g4-g9` branch)

**Original behavior:** PubMed queries used plain keywords with no MeSH term mapping.

**Fix applied:**
- Created `utils/mesh_lookup.py` with `MeshTerm` dataclass and `lookup_mesh_terms()` function using NLM E-utilities API
- Added `mesh_expansion_enabled` config flag (defaults to true when PubMed is enabled)
- Modified `pubmed_client.py` to call `lookup_mesh_terms()` and expand queries with `OR "DescriptorName"[MeSH Terms]`
- MeSH terms are appended with OR — original free-text query is never replaced

**Files changed:** `config.py`, `utils/mesh_lookup.py` (new), `discovery/pubmed_client.py`

---

### G2. No Search Strategy Documentation Output — RESOLVED

**Severity:** Critical for PRISMA reproducibility
**Status:** Resolved (commit 82ca42d on `feature/gaps-g1-g2-g3-g4-g9` branch)

**Original behavior:** Search queries were only logged at verbose level, not persisted to output files.

**Fix applied:**
- Added `SourceQueryRecord` dataclass tracking per-source discovery metadata (source, timestamps, duration, result count, query variants)
- Modified `_discover_from_source()` in `pipeline_controller.py` to capture and record per-source metadata
- Added `_write_search_strategy_md()` and `_write_search_strategy_json()` to `report_generator.py`
- Always generates both files (no toggle — core PRISMA requirement)
- Output includes: search parameters, query variants, per-source results table, deduplication statistics, MeSH and snowballing config

**Files changed:** `pipeline/pipeline_controller.py`, `reporting/report_generator.py`, `main.py`

---

### G3. Citation Snowballing is Depth-1 Only — RESOLVED

**Severity:** Moderate
**Status:** Resolved (commit 2bc1962 on `feature/gaps-g1-g2-g3-g4-g9` branch)

**Original behavior:** Snowballing was hardcoded to depth-1 with a limit of 10 papers per direction.

**Fix applied:**
- Added `snowballing_depth: int = 1` and `snowballing_per_direction_limit: int = 10` to config
- Replaced single-pass `expand()` with iterative depth loop in `citation_expander.py`
- Each iteration uses the previous iteration's discoveries as new seeds
- Track `seen_identity_keys` across iterations to avoid re-processing
- Defaults (depth=1, limit=10) produce identical behavior to original code
- Skill defaults: depth=2, limit=15 for comprehensive reviews

**Files changed:** `config.py`, `citation/citation_expander.py`

---

### G4. No PRISMA Flow Diagram Image — RESOLVED

**Severity:** Moderate (visual reporting)
**Status:** Resolved (commit 31d1791 on `feature/gaps-g1-g2-g3-g4-g9` branch)

**Original behavior:** Pipeline produced `prisma_flow.json` and `prisma_flow.md` with only flat bullet lists. No visual flowchart.

**Fix applied:**
- Added `_write_prisma_flow_mermaid()` to `report_generator.py`
- Generates a `prisma_flow.mermaid` file with `flowchart TD` syntax
- Nodes: identification → deduplication → snowballing → screening → excluded/maybe/included
- All counts come from the same `stats` dict used by `prisma_flow.json` (consistent numbers)
- Renderable on GitHub, Mermaid Live Editor, or via `mmdc` CLI
- Always generated alongside existing `prisma_flow.md`

**Files changed:** `reporting/report_generator.py`, `main.py`

---

### G5. No Risk of Bias / Quality Assessment — DEFERRED

**Severity:** Important for review rigor
**Status:** Deferred. Would require significant prompt engineering for each assessment framework (RoB2, ROBINS-I, QUADAS-2, NOS, JBI). Could be implemented as a custom `--analysis-pass` with provider-specific prompts in a future iteration.

**Current behavior:** The pipeline screens papers for relevance only. There is no framework for assessing methodological quality, risk of bias, or study validity. No support for common assessment tools:
- RoB2 (Cochrane Risk of Bias 2 for RCTs)
- ROBINS-I (Risk of Bias in Non-randomised Studies)
- QUADAS-2 (Quality Assessment of Diagnostic Accuracy Studies)
- Newcastle-Ottawa Scale (NOS)
- JBI Critical Appraisal Checklists

**Impact:** Systematic reviews require quality assessment as a core methodological step. Without it, the review cannot weight or qualify the evidence. Most journals and PRISMA guidelines expect this assessment to be reported.

**Workaround:** Export the included papers via `included_papers.csv` or `included_papers.db` and perform quality assessment manually in a spreadsheet or dedicated tool (e.g., Covidence, Rayyan).

**Recommendation:** Add an optional quality assessment stage that uses LLM-based evaluation against established frameworks. Could be implemented as a custom `--analysis-pass` with provider-specific prompts.

---

### G6. No Data Extraction Templates — DEFERRED

**Severity:** Important for review completeness
**Status:** Deferred. Requires configurable extraction forms, LLM-based structured data extraction, and template definitions for common review types (PICO, diagnostic, intervention). Medium-high effort, best addressed after the core gaps are resolved.

**Current behavior:** The pipeline extracts basic metadata (title, authors, abstract, year, venue, DOI, citations, methodology category, domain category) but does not support structured data extraction forms common in systematic reviews:
- Study characteristics (design, sample size, population, intervention, comparator)
- Outcome measures (primary/secondary outcomes, effect sizes, confidence intervals)
- Population details (age, sex, condition, severity)
- Intervention details (dosage, duration, delivery method)

**Impact:** Systematic reviews require structured data extraction to synthesize findings. Without templates, researchers must manually extract data from included papers.

**Workaround:** Use `included_papers.csv` as a starting point and add extraction columns manually. Or use `--analyze-full-text` to capture full text and extract data with a separate LLM-based tool.

---

### G7. No Meta-Analysis Support — DEFERRED

**Severity:** Moderate (depends on review type)
**Status:** Deferred. Statistical synthesis is a specialized domain best handled by dedicated tools (R `meta` package, RevMan). The pipeline should focus on discovery and screening. G9 (RIS/BibTeX export) provides the bridge to these tools.

**Current behavior:** No statistical synthesis capabilities. No pooled effect estimates, forest plots, heterogeneity statistics (I², Q-test), subgroup analyses, or sensitivity analyses.

**Impact:** Many systematic reviews include meta-analysis as the quantitative synthesis step. The pipeline stops at screening and ranking.

**Workaround:** Export included papers and use dedicated meta-analysis tools (R's `meta` package, RevMan, Comprehensive Meta-Analysis).

---

### G8. No Inter-Rater Reliability / Dual Screening — DEFERRED

**Severity:** Important for review credibility
**Status:** Deferred. Would require a dual-screening mode with agreement metrics (Cohen's kappa), conflict resolution, and per-paper dual decision tracking. Medium effort, builds on existing multi-pass infrastructure.

**Current behavior:** Screening is performed by a single automated screener (heuristic or LLM). There is no dual-screening mode, no conflict resolution between independent screeners, and no calculation of inter-rater reliability metrics (Cohen's kappa, percentage agreement).

**Impact:** PRISMA guidelines recommend dual independent screening with conflict resolution. Single-screener automated reviews may be questioned by journal reviewers.

**Workaround:** Run the pipeline twice with different providers (e.g., `heuristic` then `gemini`) and manually compare results. The `--analysis-pass` multi-pass feature partially addresses this but does not calculate agreement metrics.

---

### G9. No Export to Systematic Review Tools — RESOLVED

**Severity:** Moderate (workflow integration)
**Status:** Resolved (commit 2685f0a on `feature/gaps-g1-g2-g3-g4-g9` branch)

**Original behavior:** Outputs were CSV, JSON, Markdown, and SQLite only. No RIS or BibTeX export.

**Fix applied:**
- Added `output_ris: bool = True` and `output_bibtex: bool = True` to config
- Added `_write_ris_export()` using standard RIS tags (TY, TI, AU, PY, JO, DO, AB, ER)
- Added `_write_bibtex_export()` using `@article{}` with cite keys as `firstauthor_year_firstword`
- Both gated by config flags, enabled by default
- Generated files import cleanly into Zotero, Covidence, Rayyan, and other review tools

**Files changed:** `config.py`, `reporting/report_generator.py`, `main.py`

---

## Skill Gaps (Fixable in This Repo)

### G10. run-review Does Not Inject Skill Defaults — RESOLVED

**Severity:** High

**Problem:** `scripts/run-review` only injected path defaults (`--results-dir`, `--database-path`, etc.) but not the skill's recommended screening and discovery settings. A bare command like `bash scripts/run-review --topic "X" --keywords "Y"` would use the pipeline's own conservative defaults (threshold 70, strict mode, balanced strategy) instead of the skill's systematic-review-tuned values.

**Fix applied:** Added a "Systematic review defaults" section to `scripts/run-review` that injects the following flags when they are not explicitly provided by the user AND `--config-file` is not used:

| Flag injected | Value | Pipeline default it overrides |
|---|---|---|
| `--threshold` | 55 | 70 |
| `--decision-mode` | triage | strict |
| `--maybe-threshold-margin` | 15 | 10 |
| `--discovery-strategy` | broad | balanced |
| `--include-pubmed` | (enabled) | auto |
| `--europe-pmc-enabled` | (enabled) | disabled |
| `--no-arxiv-enabled` | (disabled) | disabled |
| `--topic-prefilter-review-threshold` | 0.45 | 0.55 |

Each injection uses the existing `has_flag()` helper to check if the user already provided the flag, so explicit user choices always take priority. The injection only runs when `--config-file` is not used (matching the existing path-injection behavior).

**Files changed:** `scripts/run-review`

**Verification:** A bare run `bash scripts/run-review --topic "X" --keywords "Y"` will now receive all 8 flags automatically. Any explicit flag override (e.g. `--threshold 70`) is respected.

---

### G11. Europe PMC Disabled — RESOLVED

**Severity:** Low-moderate

**Problem:** `europe_pmc_enabled` was set to `false` across all skill files. Europe PMC indexes PubMed Central, PubMed, and other biomedical repositories — a relevant source for medical systematic reviews that was being missed.

**Fix applied:**
- `references/config-template.json`: changed `"europe_pmc_enabled": false` → `"europe_pmc_enabled": true`
- `references/flags.md`: changed Europe PMC default from "disabled" to "enabled"
- `scripts/run-review`: added `--europe-pmc-enabled` to the defaults injection section

**Files changed:** `references/config-template.json`, `references/flags.md`, `scripts/run-review`

---

### G12. Google Scholar Disabled — DEFERRED

**Severity:** Low

**Problem:** Google Scholar has broader coverage than most academic APIs but uses HTML scraping and is marked experimental in the pipeline.

**Decision:** Left disabled by default. Google Scholar scraping carries risk of rate limiting, CAPTCHAs, and IP blocks that could halt a review run. Users who need broader coverage can enable it explicitly:
```bash
--google-scholar-enabled --google-scholar-pages 2
```

**No files changed.**

---

### G13. No Provider Choice Guidance for Medical Screening — RESOLVED

**Severity:** Low-moderate

**Problem:** `providers.md` documented each provider's technical setup but gave no guidance on which provider produces better screening decisions for medical/clinical papers. Users had no basis for choosing between heuristic, Gemini, OpenAI, or local models.

**Fix applied:** Added "Provider Guidance for Medical Reviews" section to `references/providers.md` containing:

1. **Single-provider comparison table** — rates each provider on clinical reasoning capability, cost, and trade-offs:
   - Heuristic: fastest, no cost, no clinical reasoning
   - OpenAI/Gemini: clinical evaluation of study design and relevance
   - Ollama/HuggingFace: quality depends on model size, requires RAM/VRAM

2. **Recommended multi-pass strategy** for medical reviews:
   ```bash
   --analysis-pass "triage:heuristic:55:triage:15" \
   --analysis-pass "clinical:gemini:65:triage:10:gemini-2.5-flash:50"
   ```
   Heuristic weeds out clearly irrelevant papers cheaply, then Gemini evaluates the remaining papers with clinical understanding.

3. **PICO-based tips** for writing effective inclusion/exclusion criteria:
   - Include Population, Intervention, Comparator, Outcome elements
   - Examples: `--inclusion-criteria "human subjects;randomized controlled trial;adults 18+"`

**Files changed:** `references/providers.md`

---

### G14. No Example Inclusion/Exclusion Criteria for Medical Reviews — RESOLVED

**Severity:** Low

**Problem:** SKILL.md showed only generic patterns (`--topic "X" --keywords "Y"`). No medical-specific examples demonstrating proper use of inclusion criteria, exclusion criteria, or MeSH terms in keywords.

**Fix applied:** Added "Medical systematic review" pattern to SKILL.md's Common Patterns section:
```bash
bash scripts/run-review \
  --topic "AI-assisted diagnosis in radiology" \
  --keywords '"artificial intelligence"[MeSH Terms],deep learning,CT,MRI,diagnostic accuracy' \
  --inclusion-criteria "human subjects;English language;prospective study;diagnostic accuracy" \
  --exclusion-criteria "animal study;case report;review article;editorial;opinion" \
  --llm-provider gemini
```

This demonstrates:
- MeSH terms in the `--keywords` field (manual workaround for G1)
- PICO-structured inclusion/exclusion criteria
- LLM provider choice for clinical screening

**Files changed:** `SKILL.md`

---

### G15. Topic Prefilter Model is General-Purpose — RESOLVED

**Severity:** Low-moderate

**Problem:** The default embedding model (`BAAI/bge-small-en-v1.5`) is a general-purpose English sentence model not trained on biomedical text. The topic prefilter's semantic similarity scoring may be less accurate for medical terminology, clinical jargon, and biomedical concepts.

**Fix applied:** Added "Topic Prefilter Model Selection" section to `references/providers.md` documenting three models:

| Model | Size | Best for | How to use |
|---|---|---|---|
| `BAAI/bge-small-en-v1.5` | 134MB | General reviews (default) | (used automatically) |
| `NeuML/pubmedbert-base-embeddings` | 520MB | Medical/biomedical reviews | `--topic-prefilter-model NeuML/pubmedbert-base-embeddings` |
| `FremyCompany/BioLORD-2023-M` | 480MB | Biomedical sentence similarity | `--topic-prefilter-model FremyCompany/BioLORD-2023-M` |

Also documented:
- Environment variable override: `export HF_TOPIC_MODEL="NeuML/pubmedbert-base-embeddings"`
- Models download and cache on first use
- Switching models requires `--clear-screening-cache` to re-evaluate previously screened papers

The default is kept as `BAAI/bge-small-en-v1.5` to avoid surprising users with a 520MB download on first run. Medical users can opt in to a biomedical model.

**Files changed:** `references/providers.md`

---

## Summary Table

| # | Gap | Severity | Status |
|---|---|---|---|
| G1 | No MeSH term support | Critical | **Resolved** (commit 0ac8f72) |
| G2 | No search strategy documentation | Critical | **Resolved** (commit 82ca42d) |
| G3 | Snowballing depth-1 only | Moderate | **Resolved** (commit 2bc1962) |
| G4 | No PRISMA flow diagram image | Moderate | **Resolved** (commit 31d1791) |
| G5 | No risk of bias assessment | Important | **Deferred** |
| G6 | No data extraction templates | Important | **Deferred** |
| G7 | No meta-analysis support | Moderate | **Deferred** |
| G8 | No inter-rater reliability | Important | **Deferred** |
| G9 | No export to review tools | Moderate | **Resolved** (commit 2685f0a) |
| G10 | run-review doesn't inject skill defaults | High | **Resolved** (commit f1228d2) |
| G11 | Europe PMC disabled | Low-moderate | **Resolved** (commit f1228d2) |
| G12 | Google Scholar disabled | Low | **Deferred** (experimental) |
| G13 | No provider guidance for medical screening | Low-moderate | **Resolved** (commit f1228d2) |
| G14 | No medical example criteria | Low | **Resolved** (commit f1228d2) |
| G15 | General-purpose embedding model | Low-moderate | **Resolved** (commit f1228d2) |

**Score: 10 of 15 gaps resolved, 1 skill gap deferred, 4 upstream gaps deferred.**
