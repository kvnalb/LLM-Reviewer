PYTHONPATH := $(shell pwd)/src
INPUT_JSONL ?= outputs/review_subset.jsonl
OUTPUT_JSONL ?= outputs/results.jsonl

# Export clean subset from SQLite (with pdf_url for PDF extraction)
export:
	PYTHONPATH=$(PYTHONPATH) python -m reviewer_sim.ingest.export_review_subset \
		--db-path data/gen_review.db \
		--out-path outputs/review_subset.jsonl \
		--n 120 --seed 42 --min-review-chars 50 \
		--year 2023 \
		--exclude-decisions "Withdrawn,Desk Reject,Invite to Workshop"

# Enrich with LLM-classified primary areas (requires TOGETHER_API_KEY)

# Extract PDF content with review-optimized strategy (10k tokens, methods>results priority)
extract-pdf:
	PYTHONPATH=$(PYTHONPATH) python -m reviewer_sim.ingest.extract_pdf_content \
		--input outputs/review_subset.jsonl \
		--output outputs/review_subset_with_pdf.jsonl \
		--mode sections_optimized \
		--max-tokens 10000 \
		--cache data/pdf_cache

# Extract PDF content with legacy mode (for backward compatibility)
extract-pdf-legacy:
	PYTHONPATH=$(PYTHONPATH) python -m reviewer_sim.ingest.extract_pdf_content \
		--input outputs/review_subset.jsonl \
		--output outputs/review_subset_with_pdf_legacy.jsonl \
		--mode sections \
		--max-tokens 6000 \
		--cache data/pdf_cache

# Extract PDF content with full-text mode (alternative: complete paper text)
extract-pdf-fulltext:
	PYTHONPATH=$(PYTHONPATH) python -m reviewer_sim.ingest.extract_pdf_content \
		--input outputs/review_subset.jsonl \
		--output outputs/review_subset_with_pdf_fulltext.jsonl \
		--mode fulltext \
		--max-tokens 10000 \
		--cache data/pdf_cache

# Run pipeline with PDF content (requires extract-pdf to be run first)
run-with-pdf:
	PYTHONPATH=$(PYTHONPATH) \
	INPUT_JSONL=outputs/review_subset_with_pdf.jsonl \
	OUTPUT_JSONL=outputs/results_with_pdf.jsonl \
	$(MAKE) run

# Full workflow: export → extract PDFs → run
full-pipeline: export extract-pdf run-with-pdf

# Run review simulation pipeline
run:
	PYTHONPATH=$(PYTHONPATH) INPUT_JSONL=$(INPUT_JSONL) OUTPUT_JSONL=$(OUTPUT_JSONL) python -m reviewer_sim.run

# Run with mock generator
run-mock:
	PYTHONPATH=$(PYTHONPATH) \
	MODEL_PROVIDER=mock \
	INPUT_JSONL=outputs/review_subset.jsonl \
	OUTPUT_JSONL=outputs/results_mock.jsonl \
	python -m reviewer_sim.run

# Run with llamacpp (requires MODEL_PATH)
run-llamacpp:
	@if [ -z "$(MODEL_PATH)" ]; then echo "ERROR: MODEL_PATH env var is required"; exit 1; fi
	PYTHONPATH=$(PYTHONPATH) \
	MODEL_PROVIDER=llamacpp \
	MODEL_PATH=$(MODEL_PATH) \
	INPUT_JSONL=outputs/review_subset.jsonl \
	OUTPUT_JSONL=outputs/results_llamacpp.jsonl \
	python -m reviewer_sim.run

# Run with Together AI (requires TOGETHER_API_KEY and MODEL_PATH)
# Default model is mistralai/Mixtral-8x7B-Instruct-v0.1. Override with:
#   make run-together MODEL_PATH=deepseek-ai/deepseek-v3.1 OUTPUT_JSONL=outputs/results_deepseek.jsonl
TOGETHER_OUTPUT_JSONL ?= outputs/results_together.jsonl
TOGETHER_MODEL_PATH ?= mistralai/Mixtral-8x7B-Instruct-v0.1
TOGETHER_INPUT_JSONL ?= outputs/review_subset.jsonl
run-together:
	@if [ -z "$(TOGETHER_API_KEY)" ]; then echo "ERROR: TOGETHER_API_KEY env var is required"; exit 1; fi
	PYTHONPATH=$(PYTHONPATH) \
	MODEL_PROVIDER=together \
	MODEL_PATH=$(if $(MODEL_PATH),$(MODEL_PATH),$(TOGETHER_MODEL_PATH)) \
	TOGETHER_API_KEY=$(TOGETHER_API_KEY) \
	INPUT_JSONL=$(if $(INPUT_JSONL),$(INPUT_JSONL),$(TOGETHER_INPUT_JSONL)) \
	OUTPUT_JSONL=$(if $(OUTPUT_JSONL),$(OUTPUT_JSONL),$(TOGETHER_OUTPUT_JSONL)) \
	python -m reviewer_sim.run

# Smoke test: run full pipeline on 5 papers
# mock mode (no API key):  make test-pipeline
# Together AI:             TOGETHER_API_KEY=xxx make test-pipeline
# skip PDF extraction:     SKIP_PDF=1 make test-pipeline
test-pipeline:
	bash scripts/test_pipeline.sh

# Run tests
test:
	PYTHONPATH=$(PYTHONPATH) pytest tests/ -v

# Check imports
test-imports:
	PYTHONPATH=$(PYTHONPATH) python -c "import reviewer_sim; import reviewer_sim.ingest; import reviewer_sim.generate; import reviewer_sim.evaluate; import reviewer_sim.utils"

# Summarize results (single model)
summarize:
	PYTHONPATH=$(PYTHONPATH) python scripts/summarize_results.py $(OUTPUT_JSONL)

# Run experiment across multiple models and produce comparison table
# Requires TOGETHER_API_KEY env var. Edit scripts/run_experiment.py to configure models.
experiment:
	@if [ -z "$(TOGETHER_API_KEY)" ]; then echo "ERROR: TOGETHER_API_KEY env var is required"; exit 1; fi
	PYTHONPATH=$(PYTHONPATH) TOGETHER_API_KEY=$(TOGETHER_API_KEY) python scripts/run_experiment.py

# Compare results from multiple model runs (reads all outputs/results_*.jsonl)
compare:
	PYTHONPATH=$(PYTHONPATH) python scripts/compare_models.py
