# LLM-Reviewer

Research prototype for benchmarking LLM-based peer review simulations. Enables automated comparison between human reviews and AI-generated reviews using disparate model providers (Mock, Local GGUF, Together AI).

---

## Key Capabilities

- **Data Ingestion**: Export clean subsets from SQLite with year filtering, min-length validation, deterministic sampling
- **Review Generation**: Generate synthetic reviews using mock, local Llama models (GGUF), or cloud APIs
- **Automated Benchmarking**: Run large-scale experiments comparing multiple models (Llama 3, Mistral, Qwen)
- **Evaluation**: Compare generated vs human reviews using score difference MAE (primary) and text similarity metrics (secondary)

---

## Project Structure

```
LLM-Reviewer/
├── data/
│   ├── gen_review.db                    # Source database (~1.5GB)
│   └── processed/
│       ├── review_subset.jsonl          # Clean export (200 papers, 2023)
├── outputs/                             # Generated results (not committed)
├── scripts/
│   ├── compare_models.py                # Multi-model comparison table generator
│   ├── run_experiment.py                # Batch experiment runner (Together AI)
│   └── summarize_results.py             # Single result summary tool
├── src/reviewer_sim/
│   ├── __init__.py
│   ├── run.py                           # Pipeline entry point
│   ├── ingest/
│   │   ├── export_review_subset.py      # SQLite → JSONL exporter
│   │   └── load_jsonl.py                # JSONL loader utility
│   ├── generate/
│   │   └── providers.py                 # Mock + LlamaCpp + Together generators
│   ├── evaluate/
│   │   └── metrics.py                   # Evaluation metrics
│   └── utils/
│       └── config.py                    # ModelConfig + validation
├── tests/
│   └── test_export_review_subset.py     # Pytest tests
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

### For Apple Silicon (M1/M2/M3) with Metal GPU
```bash
CMAKE_ARGS="-DLLAMA_METAL=on" FORCE_CMAKE=1 pip install llama-cpp-python
```

---

## Data Pipeline

### 1. Export from SQLite
Export a clean subset of papers with reviews (defaults to **2023** slice):

```bash
make export
```

Or with custom options:
```bash
PYTHONPATH=src python -m reviewer_sim.ingest.export_review_subset \
  --db-path data/gen_review.db \
  --out-path data/processed/review_subset.jsonl \
  --n 200 --seed 42 --year 2023 --min-review-chars 50
```

**Output schema:**
```json
{
  "paper_id": "abc123",
  "title": "Paper Title",
  "abstract": "...",
  "primary_area": "general",
  "year": 2023,
  "review": {"main_review": "..."},
  "meta": {
    "source": "gen_review_sqlite",
    "filters": {"year": 2023, "min_review_chars": 50},
    "exported_at": "2024-01-01T00:00:00+00:00"
  }
}
```



---

## Review Generation & Experimentation

### Run with Mock Generator (Fast Test)
```bash
make run-mock
```

### Run with Local LLM (GGUF)
```bash
MODEL_PATH=models/llama-3-8b-instruct-q4_k_m.gguf make run-llamacpp
```

### Full Custom Run
```bash
PYTHONPATH=src \
MODEL_PROVIDER=llamacpp \
MODEL_PATH=models/your-model.gguf \
INPUT_JSONL=data/processed/review_subset.jsonl \
OUTPUT_JSONL=outputs/results.jsonl \
python -m reviewer_sim.run
```

---

## Provider Interface

### MockGenerator
- Deterministic output based on `reviewer_profile`
- Score adjustment: `critical` (-2), `neutral` (0), `positive` (+2) from base 6
- Fast iteration and testing

### LlamaCppGenerator
- Local GGUF model inference via llama-cpp-python
- Metal GPU acceleration on Apple Silicon
- Model loaded once, reused for all examples
- Robust JSON parsing with fallback

---

## Configuration (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_PROVIDER` | `mock` | `mock` or `llamacpp` |
| `MODEL_PATH` | None | Path to GGUF file (required for llamacpp) |
| `TEMPERATURE` | `0.2` | Sampling temperature |
| `TOP_P` | `0.95` | Nucleus sampling threshold |
| `MAX_TOKENS` | `600` | Maximum generation length |
| `N_CTX` | `4096` | Context window size |
| `N_GPU_LAYERS` | `-1` | GPU layers (-1 = all) |
| `INPUT_JSONL` | `data/processed/review_subset.jsonl` | Input file |
| `OUTPUT_JSONL` | `outputs/results.jsonl` | Output file |
| `TOGETHER_API_KEY` | None | API key for enrichment |

---

## Evaluation Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `mae` | Primary | Mean Absolute Error across 5 scoring dimensions (lower is better) |
| `coverage_pct` | Primary | Percentage of examples successfully evaluated |
| `decision_agree` | Primary | Agreement on Accept/Reject decision |
| `tfidf_cosine` | Secondary | Cosine similarity of TF-IDF vectors (higher = more similar) |
| `keyword_jaccard` | Secondary | Jaccard index of token sets (higher = more overlap) |

### Summarize Results
```bash
make summarize OUTPUT_JSONL=outputs/results.jsonl
```

---

## Makefile Targets

| Target | Description |
|--------|-------------|
| `make export` | Export 200 papers from SQLite (2023 slice) |
| `make run` | Run review simulation pipeline |
| `make run-mock` | Run with mock generator |
| `make run-llamacpp` | Run with GGUF model (requires `MODEL_PATH`) |
| `make test` | Run pytest tests |
| `make test-imports` | Verify all modules import |
| `make summarize` | Summarize results JSONL |

---

## Database Statistics

| Table | Count |
|-------|-------|
| Papers (SUBMISSION) | 32,652 |
| Human Reviews (REVIEW) | 124,615 |
| Papers with non-empty reviews | 9,766 |
| GenAI Reviews | 81,850 |

**Processed subset:** 200 papers from **2023** with reviews ≥50 chars

---

## Tests

```bash
make test
```

5 tests covering:
- Year filtering
- Deterministic sampling
- Empty review filtering
- Short review filtering
- Output schema validation

---

## Docker

```bash
docker build -t reviewer_sim .
docker run -v $(pwd)/outputs:/app/outputs reviewer_sim
```

For llamacpp:
```bash
docker run -v $(pwd)/models:/app/models \
           -v $(pwd)/outputs:/app/outputs \
           -e MODEL_PROVIDER=llamacpp \
           -e MODEL_PATH=/app/models/your-model.gguf \
           reviewer_sim
```

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Provider pattern | Swap mock↔LLM with one env var |
| Model loaded once | Avoid 30+ second reload per example |
| Deterministic export | Same seed = identical output |
| LLM enrichment separate | Original data unchanged, derived datasets |
| Per-example error handling | Pipeline continues on failures |
| Config via env vars | Easy Docker/CI integration |
| models/ in .gitignore | Don't commit multi-GB model files |

---

## Benchmarks (2023 Subset)

| Model | MAE (lower is better) | Coverage | Decision Agreement |
|-------|-----------------------|----------|--------------------|
| **Mock** | 0.709 | 100% | 61.0% |
| *Llama-3-8B (TBD)* | ... | ... | ... |

*Note: Benchmarks now prioritize Mean Absolute Error (MAE) and Decision Agreement over text similarity.*

---

## Future Work

1. Prompt engineering for review quality
2. Model comparison (Mistral, Phi, etc.)
3. Additional metrics (BLEU, ROUGE, BERTScore)
4. Reviewer profile impact analysis
5. Human evaluation study
6. Domain-specific fine-tuning
