# Phase 2 (Investigation) — Gap Analysis Against Spec

Date: 2026-05-29

Scope: The pipeline's intended role is **Phase 2: Investigation** (search, dedup, screening, verification, supplementary search, RoB) per `systematic-review-pipeline.md`. All other phases (Scoping, Analysis, Composition, Review, Revision) are out of scope and handled by downstream tools via RIS/BibTeX/CSV export.

---

## Coverage Summary

| Spec Section | Pipeline Coverage | Gap Count |
|---|---|---|
| 3.1 Search Execution | Partial | 2 |
| 3.2 Data Persistence | Partial | 4 |
| 3.3 Metadata Quality Gate | Missing | 4 |
| 3.4 Deduplication | Partial | 4 |
| 3.5 Screening | Partial | 7 |
| 3.6 Full-Text Acquisition | Partial | 3 |
| 3.7 Source Verification | Missing | 3 |
| 3.8 Supplementary Search | Partial | 3 |
| 3.9 Risk of Bias | Missing | 5 |
| 3.10 Raw-to-Filtered Lineage | Partial | 3 |
| 3.11 Count Consistency | Missing | 2 |
| Gate 2→3 | Missing | 3 |
| Cross-Cutting 8.1–8.4 | Partial | 5 |
| Audit Artifacts (Phase 2 scope) | Partial | 6 |
| **Total** | | **54** (40 remaining after all resolved gaps) |

---

## 3.1 Search Execution

### What exists

- Multiple discovery clients (PubMed, OpenAlex, Semantic Scholar, Crossref, Europe PMC, CORE, arXiv, Google Scholar)
- Per-source query metadata recorded: source name, started_at, finished_at, duration, results_returned (G2: `SourceQueryRecord`)
- Search strategy docs generated: `search_strategy.md` and `search_strategy.json`
- MeSH term expansion for PubMed queries (G1)

### Gaps

**P2-01: Coverage anomaly detection**
Spec §3.1: "Compare per-database yields against expected ranges. If any database returns 0 results when the topic should yield results, flag as `POTENTIAL_SEARCH_ERROR`."

Current behavior: Zero-result sources are silently logged. No flag, no anomaly detection, no verification that the query was correctly adapted.

**P2-02: Raw results persistence before processing**
Spec §3.1: "Persist all raw results before any processing."

Current behavior: Results from individual sources are accumulated in memory and only written to SQLite after deduplication. If the pipeline crashes during dedup, raw per-source results are lost.

---

## 3.2 Data Persistence

### What exists

- SQLite database (`review.db`) stores all papers with metadata
- `resume_mode` skips already-screened papers on re-run
- Configuration snapshot saved as `run_config.json`

### Gaps

**P2-03: Staged checkpoint files**
Spec §3.2: "Incremental checkpoints — persist after each of: (1) each database search, (2) deduplication, (3) title/abstract screening, (4) full-text screening."

Current behavior: Single write after deduplication (`upsert_papers`). No intermediate checkpoints. A crash between discovery and dedup loses all raw data.

Each checkpoint must contain: database, search_timestamp, query_string, result_count, records array.

**P2-04: Checkpoint shape standardization**
Spec §3.2 defines a specific record shape: `id`, `title`, `authors` (as `{firstName, lastName}`), `year`, `doi`, `abstract`, `venue`, `source_db`, `source_id`, `search_timestamp`, `query_used`, `open_access_url`.

Current behavior: `PaperMetadata` has most fields but uses a flat `authors: list[str]` (not `{firstName, lastName}`), lacks `search_timestamp` and `query_used` per record.

**P2-05: Crash recovery with stage detection**
Spec §3.2: "On pipeline interruption, detect the latest checkpoint and offer the option to resume from that stage."

Current behavior: `resume_mode` skips already-screened papers but doesn't detect which stage failed or offer stage-level resume.

**P2-06: Pre-search raw persistence**
Spec §3.2: Raw results must be persisted before any transformation.

Current behavior: Results are transformed (normalized, merged) in memory before first write.

---

## 3.3 Metadata Quality Gate

### What exists

- `PaperMetadata` validation via Pydantic (title required, abstract optional)

### Gaps

**P2-07: Pre-screening metadata completeness check**
Spec §3.3: "Before screening begins, validate every record."

Current behavior: No validation gate. Papers with empty titles are filtered in individual clients (e.g., `pubmed_client.py` skips articles with no title), but there's no unified pre-screening quality check.

Required validation:
| Field | Action if Missing |
|---|---|
| Title | HALT |
| Authors ≥1 | WARN |
| Year | WARN |
| Abstract | Track rate; >20% → HALT |
| Source database | WARN |

**P2-08: Per-database metadata quality report**
Spec §3.3: "Produce a per-database metadata quality report showing field completeness percentages."

Current behavior: No quality report generated.

**P2-09: Abstract coverage gate**
Spec §3.3: "If overall abstract coverage is below 90%, recommend backfilling from alternative databases. If >20% missing, HALT."

Current behavior: No abstract coverage tracking or gate.

**P2-10: Cross-source metadata reconciliation with logging**
Spec §3.3: "Prefer the metadata from the source with the most complete record. Log which version was kept and why."

Current behavior: `merge_with()` in `PaperMetadata` merges fields but doesn't log which source's version was kept or why.

---

## 3.4 Deduplication

### What exists

- 3-tier dedup: identity_key (hash of DOI + title + source) → DOI match → title similarity (fuzzy, threshold 0.92)
- `merge_with()` combines metadata from duplicates
- Configurable title similarity threshold

### Gaps

**P2-11: 4-tier dedup priority**
Spec §3.4: Priority 1 (unique identifier) → 2 (DOI) → 3 (title fuzzy ≥0.85) → 4 (author+year+venue heuristic).

Current behavior: Uses identity_key (which incorporates DOI), then title similarity. No author+year+venue fallback. Threshold is 0.92 (spec recommends 0.85 for dedup — the pipeline is stricter, which is acceptable).

**P2-12: Duplicate separation (not deletion)**
Spec §3.4: "Duplicates must be separated from the active corpus (not deleted) so dedup decisions are auditable and reversible."

Current behavior: Duplicates are merged via `merge_with()` — the original records are replaced, not preserved separately. No audit trail of what was merged.

**P2-13: Deduplication audit trail**
Spec §3.4: "Produce a structured log: total before/after, every duplicate pair with method, similarity score, which was kept, reason."

Current behavior: No audit trail. Logging mentions dedup counts but not individual pairs.

**P2-14: Fallback method warning**
Spec §3.4: "WARN if >5% of decisions relied on priority 3 or 4 methods."

Current behavior: No tracking of which method resolved each duplicate.

---

## 3.5 Screening

### What exists

- LLM-based screening with relevance scores (0–100)
- `inclusion_decision` field (include/exclude/maybe in triage mode)
- `exclusion_reason` and `retain_reason` text fields
- `matched_inclusion_criteria`, `matched_exclusion_criteria` lists
- Multi-pass screening (`analysis_passes`)
- Topic prefilter (embedding-based pre-screening)
- Heuristic fallback when no LLM configured

### Gaps

**P2-15: Two-pass screening protocol (T/A → FT as separate stages)**
Spec §3.5: "Two-pass screening: Pass 1 (Title + Abstract) → Pass 2 (Full Text)."

Current behavior: The pipeline has multi-pass screening but passes are configured generically. There's no explicit T/A pass vs. full-text pass distinction. The `analyze_full_text` flag adds full-text context but doesn't create a separate FT screening stage with its own decisions and exclusion reasons.

**P2-16: UNCERTAIN classification**
Spec §3.5: "Records scored below threshold → UNCERTAIN. T/A: default INCLUDE. FT: default EXCLUDE."

Current behavior: Triage mode has `maybe` classification, which partially maps to UNCERTAIN. But there's no explicit "default include at T/A, default exclude at FT" logic.

**P2-17: Exclusion reason taxonomy**
Spec §3.5 requires codes: `POP_MISMATCH`, `INT_MISMATCH`, `OUT_MISMATCH`, `DESIGN_MISMATCH`, `LANGUAGE`, `DUPLICATE`, `FULL_TEXT_UNAVAILABLE`, `OTHER`.

Current behavior: `exclusion_reason` is free-text. No structured taxonomy or codes.

**P2-18: Confidence score per screening decision**
Spec §3.5: "Every screening decision must include a confidence score. Below threshold → surfaced for human review."

Current behavior: `relevance_score` exists (0–100) and could serve as a confidence proxy, but there's no separate "confidence" concept. No configurable threshold for surfacing decisions. No structured human review protocol.

**P2-19: Screening consistency audit**
Spec §3.5: "Randomly sample 10% of borderline decisions, re-screen with fresh context, compare. Flip rate >10% → WARN."

Current behavior: No self-audit of screening consistency.

**P2-20: Large-set sample calibration**
Spec §3.5: "For sets >1000 records, screen a random 20% sample first to calibrate criteria, then review with human."

Current behavior: No sample calibration step.

**P2-21: Low-confidence surfacing protocol**
Spec §3.5: "Decisions below threshold are presented to the human with: decision, confidence score, reasoning, evidence, prompt to confirm/modify/overturn."

Current behavior: No structured surfacing. Low-scoring papers in triage mode get `maybe` but there's no human review interface or protocol beyond the desktop app's manual review.

---

## 3.6 Full-Text Acquisition

### What exists

- PDF fetcher resolves open-access URLs and downloads PDFs
- `pdf_download_mode`: "all" or "relevant_only"
- `full_text_extractor` extracts excerpts from PDFs
- `open_access` field tracked per paper

### Gaps

**P2-22: Retrieval method documentation**
Spec §3.6: "Record outcome per study: RETRIEVED / PREPRINT_ONLY / UNRETRIEVED / LIMITED_ACCESS. Document method used."

Current behavior: `pdf_path` and `pdf_link` indicate success/failure but no structured retrieval outcome or method tracking.

**P2-23: Retrieval rate gate**
Spec §3.6: "≥95% proceed, 90–95% WARN, <90% HALT."

Current behavior: No retrieval rate gate or warning.

**P2-24: Multi-tier retrieval attempts**
Spec §3.6: Priority order: open access → institutional → preprint → author correspondence → interlibrary loan.

Current behavior: Only open-access resolution is attempted. No fallback tiers.

---

## 3.7 Source Verification

### What exists

- DOI field on papers (could be resolved)
- External IDs (PMID, S2 ID, etc.) stored

### Gaps

**P2-25: Multi-tier source verification**
Spec §3.7: Tier 0 (identifier lookup via Semantic Scholar) → Tier 1 (DOI resolution via Crossref) → Tier 2 (web search spot-check 50%) → Tier 3 (human).

Current behavior: No source verification. Papers are assumed to exist.

**P2-26: Verification verdicts**
Spec §3.7: VERIFIED / PLAUSIBLE / UNVERIFIABLE / FABRICATED with specific actions per verdict.

Current behavior: No verification verdicts.

**P2-27: FABRICATED source removal**
Spec §3.7: "Strong indicators the source does not exist → Remove from corpus immediately."

Current behavior: No fabrication detection.

---

## 3.8 Supplementary Search

### What exists

- Citation snowballing via OpenAlex (configurable depth, G3)
- Forward and backward citation chaining
- Per-direction limit configurable

### Gaps

**P2-28: Supplementary record tracking in PRISMA flow**
Spec §3.8: "Supplementary search results are tracked separately in the PRISMA flow diagram under 'records identified from other sources'."

Current behavior: Snowballing results are merged into the main corpus. PRISMA flow shows `snowballing_added_count` as a single number but doesn't track supplementary records as a separate category through the screening pipeline.

**P2-29: Supplementary record provenance**
Spec §3.8: "Document: source of each supplementary record (which included study's reference list, which citation database), date of discovery, screening outcome."

Current behavior: Snowballed papers have `source` field set to the citation provider (e.g., "openalex") but don't record which seed paper led to their discovery.

**P2-30: Related review reference list screening**
Spec §3.8: "Screen reference lists of related systematic reviews identified during scoping."

Current behavior: No mechanism for this. Out of scope for the pipeline itself (requires scoping phase output), but the citation expander could accept a list of "related review" papers to use as additional seeds.

---

## 3.9 Risk of Bias Assessment

### What exists

- Nothing. This was G5 (deferred).

### Gaps

**P2-31: RoB tool selection per study design**
Spec §3.9: RoB 2 (RCTs), ROBINS-I (non-randomized), QUADAS-2 (diagnostic), QUIPS (prognostic), PROBAST (prediction models), NOS (cohort/case-control).

Requires: study design classification (partially exists — `methodology_category` field) mapped to appropriate RoB tool.

**P2-32: LLM-based RoB domain assessment**
Spec §3.9: Per-domain judgments (e.g., RoB 2 has 5 domains) with confidence scores.

Requires: prompt engineering per tool, structured output parsing, domain-level confidence tracking.

**P2-33: Blocking rule**
Spec §3.9: "IF count(studies_with_completed_RoB) < count(included), HALT."

Requires: gate mechanism that checks RoB completion before allowing synthesis to proceed.

**P2-34: RoB confidence tracking with human surfacing**
Spec §3.9: "Domain judgments below threshold → surfaced for human review with signaling question responses."

Requires: confidence scoring per domain judgment, human review protocol.

**P2-35: "No Information" handling and GRADE flagging**
Spec §3.9: "If >20% of studies receive 'No Information' across multiple domains, flag for GRADE downgrade."

Requires: tracking of "No Information" judgments, aggregate statistics.

---

## 3.10 Raw-to-Filtered Lineage

### What exists

- `screening_details` dict with pass-level metadata
- `inclusion_decision`, `exclusion_reason`, `relevance_score` per paper
- `source` field tracks origin database

### Gaps

**P2-36: Structured lineage fields**
Spec §3.10 requires: `source_database`, `ta_decision`, `ta_criteria_matched`, `ta_confidence`, `ta_exclusion_code`, `ft_decision`, `ft_retrieval_method`, `ft_exclusion_code`, `final_status`, `exclusion_stage`.

Current behavior: Information is spread across `screening_details`, `inclusion_decision`, `exclusion_reason`. Not in the spec's canonical shape.

**P2-37: Exclusion stage tracking**
Spec §3.10: Track whether exclusion happened at T/A or FT stage.

Current behavior: No explicit stage tracking for exclusions.

**P2-38: PRISMA flow count verification against lineage**
Spec §3.10: "PRISMA flow counts must be verifiable against lineage data. If inconsistent, WARN."

Current behavior: PRISMA flow counts come from `stats` dict built at report time. No cross-check against individual paper lineage.

---

## 3.11 Count Consistency

### What exists

- PRISMA flow JSON tracks aggregate counts

### Gaps

**P2-39: Cross-component count verification**
Spec §3.11: "At every phase transition, verify study counts are consistent. HALT if counts diverge."

Current behavior: No count verification between components (screening count vs. RoB count vs. verification count).

**P2-40: Study-level tracking table**
Spec §3.11: Per-study table showing ✓/?/— across Screening, Verification, RoB, Synthesis, Extraction.

Current behavior: No such tracking table.

---

## Gate 2→3

### Gaps

**P2-41: Gate mechanism**
Spec Gate 2→3: 17 preconditions that must all be checked before proceeding to Analysis.

Current behavior: No gate mechanism. Pipeline flows linearly from screening to reporting.

**P2-42: Minimum source count gate**
Spec: "Minimum source count met (full mode: 15+ | systematic-review: all eligible | quick: 5–8)."

Current behavior: `min_discovered_records` exists but only checks total count, not per-source adequacy.

**P2-43: PRISMA flow number consistency check**
Spec: "identified = duplicates_removed + records_screened; records_screened = excluded_TA + assessed_FT; assessed_FT = excluded_FT + included."

Current behavior: Flow numbers are computed independently. No algebraic consistency check.

---

## Cross-Cutting Requirements (Phase 2 relevant)

### Gaps

**P2-44: Configurable confidence thresholds per decision type**
Spec §8.1: Different thresholds for screening (80%), RoB (80%), extraction (85%), GRADE (75%).

Current behavior: Single `relevance_threshold` for screening. No separate thresholds.

**P2-45: Structured human surfacing protocol**
Spec §8.1: "Decisions below threshold presented with: decision, confidence, reasoning, evidence, prompt to confirm/modify/overturn. All human decisions logged."

Current behavior: No structured protocol. Desktop app allows manual review but doesn't follow this workflow.

**P2-46: Staged checkpoint writes**
Spec §8.3: "Incremental checkpoints at every major stage."

Current behavior: Checkpoints only at deduplication write and screening completion. Missing: post-search, post-T/A.

**P2-47: Search reproducibility verification** *(Resolved — 7a06e54)*
Spec §2.6 / §8.4: "Re-execute the documented search and compare result counts. 0–5%: SEARCH_VERIFIED. 5–20%: SEARCH_APPROXIMATE. >20%: SEARCH_UNVERIFIED."

Implemented: `utils/search_reproducibility.py` re-executes PubMed queries and compares counts. Output in `search_reproducibility.json`.

**P2-48: Reference manager integration**
Spec §8.2: "Use persistent reference management system (Zotero, Mendeley) for storage, organization by stage, tagging."

Current behavior: RIS/BibTeX export (G9) enables import into reference managers, but no direct API integration or automated collection organization.

---

## Audit Artifacts (Phase 2 Scope)

| # | Artifact | Status | Gap |
|---|---|---|---|
| 1 | PRISMA 2020 flow diagram | **Partial** | Has counts but missing T/A vs FT breakdown, supplementary source tracking, exclusion reason categories |
| 2 | Screening decision log | **Partial** | Has decisions in CSV/SQLite but missing exclusion codes, confidence scores, structured lineage |
| 3 | Deduplication audit trail | **Missing** | **P2-49**: No duplicate pair log, method tracking, or merge decisions |
| 4 | Metadata quality report | **Missing** | **P2-50**: No per-database field completeness report |
| 5 | Risk of bias summary | **Missing** | Covered by P2-31–P2-35 |
| 10 | Full-text retrieval log | **Missing** | **P2-51**: No per-study retrieval outcome/method tracking |
| 11 | Supplementary search log | **Missing** | **P2-52**: No provenance tracking for snowballed records |
| 9 | Configuration snapshot | **Exists** | `run_config.json` — adequate |
| — | Search strategy documentation | **Exists** | `search_strategy.md`/`.json` — adequate |

---

## Priority Assessment

### Resolved (high priority)

| ID | Gap | Commit | Summary |
|---|---|---|---|
| P2-17 | Exclusion reason taxonomy | 619f794 | 8 structured exclusion codes in ExclusionCode type |
| P2-07 | Metadata quality gate | 782f0de | Pre-screening validation with per-source quality report |
| P2-03 | Staged checkpoint files | 49ca860 | 3 checkpoint stages (post_discovery, post_dedup, post_screening) |
| P2-12 | Duplicate separation | 2bc1962 | Audit trail + separated duplicate records |
| P2-41 | Gate mechanism | d6e1911 | GateChecker with composable precondition evaluation |

### High priority (foundational — unblocks other gaps)

### Medium priority (completeness and auditability)

| ID | Gap | Commit | Summary |
|---|---|---|---|
| P2-15 | Two-pass screening (T/A → FT) | 6f4799d | Explicit T/A and FT pass decisions with separate tracking |
| P2-18 | Confidence score per decision | 1d28085 | Multi-factor confidence (score + criteria + LLM) on ScreeningResult |
| P2-22 | Retrieval method documentation | 1d565cc | retrieval_status/method fields + retrieval_log.json |
| P2-25 | Source verification (Tier 0-1) | 1ac37dd | S2/PubMed/Crossref verification with verdicts |
| P2-28 | Supplementary record PRISMA tracking | aac052a | supplementary_origin + seed_paper provenance on snowballed papers |
| P2-36 | Structured lineage fields | e82cdcf | source_database, final_status, exclusion_stage, ta/ft fields |
| P2-39 | Count consistency verification | bd54812 | Cross-component count checks with WARN on inconsistency |
| P2-44 | Per-decision-type confidence thresholds | 9712082 | 4 configurable thresholds (screening/rob/extraction/grade) |
| P2-47 | Search reproducibility verification | 7a06e54 | Re-executes PubMed queries, compares counts (≤5% SEARCH_VERIFIED) |

### Lower priority (important but less blocking)

| ID | Gap | Effort |
|---|---|---|
| P2-01 | Coverage anomaly detection | Low |
| P2-08 | Per-database metadata quality report | Low |
| P2-13 | Deduplication audit trail | Medium |
| P2-19 | Screening consistency audit | Medium |
| P2-23 | Retrieval rate gate | Low |
| P2-29 | Supplementary provenance | Low |
| P2-31–35 | Risk of bias assessment | Very high |
| P2-45 | Structured human surfacing protocol | Medium |
