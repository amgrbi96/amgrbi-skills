# PRISMA Pipeline — Provider Setup Guides

## Auto (default)

Automatically selects the best available provider. Falls back to `heuristic` when no API keys or local models are found.

```bash
--llm-provider auto
```

The pipeline checks for available API keys and local models and selects the first viable provider. `auto` is only valid for the global `--llm-provider` flag — individual analysis passes must specify a concrete provider.

## Heuristic (no API needed)

No configuration required. Uses built-in keyword matching and weighted scoring.

```bash
--llm-provider heuristic --threshold 70
```

The heuristic scorer uses a weighted formula: 40% topic overlap + 20% methodology + 15% theoretical + 10% recency + 15% citations, minus penalties for exclusion criteria and banned topics. No ML model involved.

## OpenAI Compatible

Supports OpenAI and any OpenAI-compatible endpoint (e.g., Azure, local servers).

Required environment variables:
```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_BASE_URL="https://api.openai.com/v1"  # optional
export OPENAI_MODEL="gpt-5.4"                        # optional
```

Config example:
```json
{
  "llm_provider": "openai_compatible",
  "relevance_threshold": 72,
  "decision_mode": "strict",
  "api_settings": {
    "openai_model": "gpt-5.4",
    "llm_temperature": 0.1
  }
}
```

## Google Gemini

Required environment variables:
```bash
export GEMINI_API_KEY="AIza..."
```

Also accepts `GOOGLE_API_KEY` as an alternative.

Config example:
```json
{
  "llm_provider": "gemini",
  "relevance_threshold": 75,
  "api_settings": {
    "gemini_model": "gemini-2.5-flash",
    "llm_temperature": 0.1
  }
}
```

## Ollama (local)

Prerequisites:
```bash
# Install Ollama, then pull a model
ollama pull qwen3:8b
```

Config example:
```json
{
  "llm_provider": "ollama",
  "relevance_threshold": 70,
  "api_settings": {
    "ollama_base_url": "http://localhost:11434/v1",
    "ollama_model": "qwen3:8b",
    "ollama_api_key": "ollama",
    "llm_temperature": 0.1
  }
}
```

## Hugging Face Local (fully offline)

No API keys needed. Downloads model on first run, caches locally.

Config example:
```json
{
  "llm_provider": "huggingface_local",
  "relevance_threshold": 70,
  "api_settings": {
    "huggingface_model": "Qwen/Qwen3-14B",
    "huggingface_task": "text-generation",
    "huggingface_device": "auto",
    "huggingface_dtype": "auto",
    "huggingface_max_new_tokens": 700,
    "huggingface_trust_remote_code": false,
    "llm_temperature": 0.1
  }
}
```

Environment variables for fine-tuning:
- `HF_MODEL_ID` — default local model
- `HF_TASK` — pipeline task (e.g. `text-generation`)
- `HF_DEVICE` — device override (e.g. `cpu`, `cuda`)
- `HF_DTYPE` — data type override (e.g. `float32`, `auto`)
- `HF_MAX_NEW_TOKENS` — max new tokens for generation
- `HF_HOME` / `TRANSFORMERS_CACHE` — model cache directory
- `HF_TRUST_REMOTE_CODE` — allow remote code execution

Note: Local inference runs single-threaded regardless of `--screening-workers` setting.

## Multi-Pass Screening

Chain multiple providers in sequence. Papers below `min_previous_score` skip subsequent passes.

Two formats supported:

**Colon format** (simple): `name:provider:threshold[:decision_mode[:margin]]`
```bash
--analysis-pass "fast:heuristic:65:strict:10"
```

**Pipe format** (extended): `name|provider|threshold|decision_mode|margin[|model_name|min_previous_score]`
```bash
--analysis-pass "fast|huggingface_local|65|strict|8|Qwen/Qwen3-14B|0" \
--analysis-pass "review|gemini|80|triage|10|gemini-2.5-flash|65" \
--analysis-pass "final|openai_compatible|88|strict|5|gpt-5.4|80"
```

Pipe format fields:

| Field | Description |
|---|---|
| name | Label for this pass |
| provider | Screening provider (must be concrete — `auto` not allowed) |
| threshold | Relevance threshold (0-100) |
| decision_mode | `strict` or `triage` |
| maybe_margin | Margin below threshold for maybe |
| model | Model override (pipe format only) |
| min_previous_score | Minimum score from previous pass to continue (pipe format only) |

## Provider Guidance for Medical Reviews

### Single-provider strategies

| Provider | Best for | Trade-offs |
|---|---|---|
| `heuristic` | Quick triage, no cost | No clinical reasoning — scores on keyword overlap, methodology patterns, citation count, and recency. May miss contextually relevant papers that use different medical terminology. |
| `openai_compatible` | Clinical evaluation | Can assess study design, population, intervention relevance. Higher quality screening but costs money and needs API key. |
| `gemini` | Clinical evaluation | Similar clinical reasoning capability to OpenAI. Good cost/quality ratio with `gemini-2.5-flash`. |
| `ollama` / `huggingface_local` | Offline, private runs | Quality depends on the model. Larger models (Qwen3-14B+) perform better on clinical text but require significant RAM/VRAM. |

### Recommended multi-pass for medical reviews

```bash
--analysis-pass "triage:heuristic:55:triage:15" \
--analysis-pass "clinical:gemini:65:triage:10:gemini-2.5-flash:50"
```

This runs a fast heuristic pass first to weed out clearly irrelevant papers, then a Gemini clinical pass that evaluates the remaining papers with medical understanding. The `min_previous_score` of 50 means only papers scoring 50+ on the heuristic pass reach the clinical evaluator.

### Tips for medical screening

- Use `--inclusion-criteria` and `--exclusion-criteria` explicitly — LLM providers use these in their evaluation prompts
- Include PICO elements in your criteria: Population, Intervention, Comparator, Outcome
- Example: `--inclusion-criteria "human subjects;randomized controlled trial;adults 18+"`
- Example: `--exclusion-criteria "animal study;case report;review article;editorial;non-English"`

## Topic Prefilter Model Selection

The default embedding model (`BAAI/bge-small-en-v1.5`) is a general-purpose sentence embedding model. For medical reviews, a biomedical-specific model may improve prefilter accuracy.

### Recommended models

| Model | Size | Best for | Override |
|---|---|---|---|
| `BAAI/bge-small-en-v1.5` | 134MB | General reviews (default) | (used automatically) |
| `NeuML/pubmedbert-base-embeddings` | 520MB | Medical/biomedical reviews | `--topic-prefilter-model NeuML/pubmedbert-base-embeddings` |
| `FremyCompany/BioLORD-2023-M` | 480MB | Biomedical sentence similarity | `--topic-prefilter-model FremyCompany/BioLORD-2023-M` |

Or set the environment variable: `export HF_TOPIC_MODEL="NeuML/pubmedbert-base-embeddings"`

The model downloads on first use and is cached locally. Switching models requires `--clear-screening-cache` to re-evaluate previously screened papers.

