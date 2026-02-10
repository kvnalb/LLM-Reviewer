PYTHONPATH := $(shell pwd)/src
INPUT_JSONL ?= outputs/review_subset.jsonl
OUTPUT_JSONL ?= outputs/results.jsonl

# Export clean subset from SQLite
export:
	PYTHONPATH=$(PYTHONPATH) python -m reviewer_sim.ingest.export_review_subset \
		--db-path data/gen_review.db \
		--out-path outputs/review_subset.jsonl \
		--n 200 --seed 42 --min-review-chars 50 \
		--year 2023 \
		--exclude-decisions "Withdrawn,Desk Reject,Invite to Workshop"

# Enrich with LLM-classified primary areas (requires TOGETHER_API_KEY)
enrich:
	PYTHONPATH=$(PYTHONPATH) python -m reviewer_sim.ingest.enrich_primary_area \
		--in-path outputs/review_subset.jsonl \
		--out-path outputs/review_subset_enriched.jsonl \
		--model "mistralai/Mixtral-8x7B-Instruct-v0.1"

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
# Override OUTPUT_JSONL to write to a different file per model, e.g.:
#   make run-together MODEL_PATH=meta-llama/Llama-3-8b-chat-hf OUTPUT_JSONL=outputs/results_llama3_8b.jsonl
TOGETHER_OUTPUT_JSONL ?= outputs/results_together.jsonl
run-together:
	@if [ -z "$(TOGETHER_API_KEY)" ]; then echo "ERROR: TOGETHER_API_KEY env var is required"; exit 1; fi
	@if [ -z "$(MODEL_PATH)" ]; then echo "ERROR: MODEL_PATH env var is required (e.g. meta-llama/Llama-3-8b-chat-hf)"; exit 1; fi
	PYTHONPATH=$(PYTHONPATH) \
	MODEL_PROVIDER=together \
	MODEL_PATH=$(MODEL_PATH) \
	TOGETHER_API_KEY=$(TOGETHER_API_KEY) \
	INPUT_JSONL=outputs/review_subset.jsonl \
	OUTPUT_JSONL=$(TOGETHER_OUTPUT_JSONL) \
	python -m reviewer_sim.run

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
