# LLM-Reviewer

Research prototype for benchmarking LLM-based peer review simulations. Compares AI-generated reviews against human reviewer consensus using multiple model providers (Mock, Local GGUF, Together AI).

---

## Key Capabilities

- **Data Ingestion**: Export clean subsets from SQLite with year filtering, min-length validation, deterministic sampling, and **aggregated reviewer consensus** (mean across all reviewers)
- **PDF Extraction**: Download and parse full-paper PDFs with review-optimized section extraction (Methods > Results priority)
- **Review Generation**: Generate synthetic reviews using mock, local Llama models (GGUF), or Together AI cloud APIs
- **Evaluation**: Compare generated vs human reviews using scale-aware NMAE (primary) and decision agreement metrics

---

## Project Structure

```
LLM-Reviewer/
├── data/
│   └── gen_review.db                    # Source database (~1.5GB, not committed)
├── outputs/                             # Generated results (not committed)
├── scripts/
│   ├── compare_models.py                # Multi-model comparison table generator
│   ├── run_experiment.py                # Batch experiment runner (Together AI)
│   └── summarize_results.py             # Single result summary tool
├── src/reviewer_sim/
│   ├── run.py                           # Pipeline entry point
│   ├── ingest/
│   │   ├── export_review_subset.py      # SQLite → JSONL exporter (aggregates reviewers)
│   │   ├── pdf_extractor.py             # PDF download + text extraction (PyMuPDF)
│   │   ├── extract_pdf_content.py       # Standalone PDF extraction script
│   │   └── load_jsonl.py                # JSONL loader utility
│   ├── generate/
│   │   └── providers.py                 # Mock + LlamaCpp + Together generators
│   ├── evaluate/
│   │   └── metrics.py                   # NMAE, RMSE, Spearman, decision agreement
│   └── utils/
│       └── config.py                    # ModelConfig + environment variable loading
├── tests/
│   └── test_export_review_subset.py     # Pytest tests for export pipeline
├── .dockerignore
├── .gitignore
├── Dockerfile
├── Makefile
├── README.md
└── requirements.txt
```

---

## Quick Start

### Install Dependencies
```bash
pip install -r requirements.txt
```

---

## Data Pipeline

### Step 1: Export from SQLite

Export a clean subset of papers with **aggregated reviewer consensus** (defaults to **n=120**, **2023** slice):

```bash
make export
```

Or with custom options:
```bash
PYTHONPATH=src python -m reviewer_sim.ingest.export_review_subset \
  --db-path data/gen_review.db \
  --out-path outputs/review_subset.jsonl \
  --n 120 --seed 42 --year 2023 --min-review-chars 50
```

**Output schema** (aggregates all reviewers per paper):
```json
{
  "paper_id": "abc123",
  "title": "Paper Title",
  "abstract": "...",
  "pdf_url": "https://openreview.net/pdf?id=...",
  "primary_area": "general",
  "decision": "Reject",
  "reviews": {
    "count": 4,
    "rating": {
      "values": [3, 5, 5, 8],
      "mean": 5.25,
      "median": 5.0,
      "std": 1.95,
      "count": 4
    },
    "all_reviews": [
      {"reviewer_id": "...", "rating": 3, "confidence": 4, ...},
      ...
    ]
  }
}
```

> **Note:** Evaluation uses the `mean` across all reviewers as the ground truth, not a single reviewer's score.

### Step 2: Extract PDF Content (optional, improves accuracy)

Download and parse full papers. This is a **separate, one-time step** that enriches the JSONL:

```bash
# Review-optimized extraction (Methods/Results priority, 10k tokens)
make extract-pdf

# Alternative: full-text extraction
make extract-pdf-fulltext
```

Adds a `pdf_content` field to each record. Review generators auto-detect this field and prefer it over the abstract.

### Step 3: Generate Reviews

```bash
# With abstract only (fast baseline)
make run-mock         # Mock generator (deterministic)
make run-together     # Together AI cloud API

# With full PDF content
make run-with-pdf
```

---

## Review Generation

### Run with Mock Generator (Fast Test)
```bash
make run-mock
```

### Run with Together AI
```bash
TOGETHER_API_KEY=your_key make run-together
```

Override model (default: `openai/gpt-oss-20b`):
```bash
TOGETHER_API_KEY=your_key MODEL_PATH=deepseek-ai/deepseek-v3.1 make run-together
```

### Full Workflow (Export → PDF → Generate)
```bash
TOGETHER_API_KEY=your_key make full-pipeline
```

### Run with Local LLM (GGUF)
```bash
MODEL_PATH=models/llama-3-8b-instruct-q4_k_m.gguf make run-llamacpp
```

For Apple Silicon (M1/M2/M3) with Metal GPU:
```bash
CMAKE_ARGS="-DLLAMA_METAL=on" FORCE_CMAKE=1 pip install llama-cpp-python
```

---

## Configuration (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_PROVIDER` | `mock` | `mock`, `llamacpp`, or `together` |
| `MODEL_PATH` | None | GGUF file path or Together AI model ID |
| `TOGETHER_API_KEY` | None | Together AI API key |
| `TEMPERATURE` | `0.2` | Sampling temperature |
| `TOP_P` | `0.95` | Nucleus sampling threshold |
| `MAX_TOKENS` | `800` | Maximum generation length |
| `N_CTX` | `16384` | Context window size |
| `N_GPU_LAYERS` | `-1` | GPU layers for llamacpp (-1 = all) |
| `INPUT_JSONL` | `outputs/review_subset.jsonl` | Input file |
| `OUTPUT_JSONL` | `outputs/results.jsonl` | Output file |

---

## Evaluation Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `nmae` | **Primary** | Normalized MAE — error divided by each dimension's range (lower is better) |
| `decision_agree` | **Primary** | Agreement on Accept/Reject at threshold ≥6 |
| `rmse` | Secondary | Root mean squared error (penalizes large errors) |
| `spearman_corr` | Secondary | Rank correlation across 5 score dimensions |
| `mae` | Legacy | Raw mean absolute error (kept for backward compatibility) |

Evaluation compares generated scores against **reviewer consensus** (mean across all human reviewers), not a single reviewer's score.

### Summarize Results
```bash
make summarize OUTPUT_JSONL=outputs/results.jsonl
```

---

## Makefile Targets

| Target | Description |
|--------|-------------|
| `make export` | Export 120 papers from SQLite (2023, aggregated reviews) |
| `make extract-pdf` | Extract PDF content (sections_optimized, 10k tokens) |
| `make extract-pdf-fulltext` | Extract PDF full text (10k tokens) |
| `make extract-pdf-legacy` | Extract PDF sections (legacy mode, 6k tokens) |
| `make run` | Run review simulation pipeline |
| `make run-mock` | Run with mock generator |
| `make run-llamacpp` | Run with GGUF model (requires `MODEL_PATH`) |
| `make run-together` | Run with Together AI (requires `TOGETHER_API_KEY`) |
| `make run-with-pdf` | Run with PDF-enriched input |
| `make full-pipeline` | Export → extract PDFs → run |
| `make experiment` | Batch run across multiple models (requires `TOGETHER_API_KEY`) |
| `make compare` | Compare all `outputs/results_*.jsonl` files |
| `make summarize` | Summarize a single results file |
| `make test-pipeline` | Smoke test: full pipeline on 5 papers (mock or Together AI) |
| `make test` | Run pytest tests |
| `make test-imports` | Verify all modules import correctly |

---

## Database Statistics

| Table | Count |
|-------|-------|
| Papers (SUBMISSION) | 32,652 |
| Human Reviews (REVIEW) | 124,615 |
| Papers with non-empty reviews | 9,766 |

**Processed subset:** 120 papers from **2023** with reviews ≥50 chars

---

## Tests

```bash
make test
```

Tests cover: year filtering, deterministic sampling, empty review filtering, short review filtering, output schema validation.

---

## Docker

```bash
docker build -t reviewer_sim .

# Mount database at runtime
docker run \
  -v /path/to/gen_review.db:/app/data/gen_review.db \
  -v $(pwd)/outputs:/app/outputs \
  -e TOGETHER_API_KEY=your_key \
  reviewer_sim
```

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Reviewer consensus as ground truth | Single reviewers are noisy; mean across all reviewers is a fairer comparison target |
| NMAE as primary metric | Scale-aware: rating (1-10) and confidence (1-5) errors are not directly comparable |
| PDF extraction as separate step | Run once, manually fix failures, then reuse enriched JSONL for all experiments |
| Methods/Results priority in PDF extraction | Reduces systematic upward bias from intro/conclusion marketing language |
| Provider pattern | Swap mock↔LLM with one env var; no code changes |
| Config via env vars | Easy Docker/CI integration |
