# Primary Area Integration Guide

This document describes the integration of the `primary_area_llm` field into the reviewer simulation workflow, enabling domain-specific LLM reviewer personas.

## Overview

The primary_area field allows the LLM reviewer to adopt a domain-specific expertise persona based on the paper's research area. This personalizes the review generation and system prompt.

**Supported research areas** (11 categories):
- `computer_vision` - image/video processing, object detection, segmentation, 3D vision
- `nlp` - natural language processing, text understanding, language models
- `ml` - general machine learning, optimization, learning theory, neural architectures
- `robotics` - robot control, planning, manipulation, autonomous systems
- `graphics` - rendering, animation, 3D modeling, visual synthesis
- `systems` - distributed systems, databases, networks, hardware/software systems
- `theory` - theoretical CS, algorithms, complexity, formal methods
- `hci` - human-computer interaction, user interfaces, accessibility
- `bio_medical` - bioinformatics, medical imaging, drug discovery, health AI
- `multi_modal` - combining vision+language, audio+text, cross-modal learning
- `other` - fallback for ambiguous or novel areas

## Complete Workflow

### Step 1: Export Review Subset
Create a base JSONL file from the SQLite database:

```bash
python -m reviewer_sim.ingest.export_review_subset \
  --db-path /path/to/database.db \
  --out-path outputs/review_subset.jsonl \
  --n 1000 \
  --seed 42 \
  --year 2023 \
  --min-review-chars 100
```

**Output**: `review_subset.jsonl` with fields: `paper_id`, `title`, `abstract`, `decision`, `review` (with nested `main_review`, `paper_summary`, score breakdowns)

### Step 2: Enrich with Primary Area Classification
Use an LLM to classify each paper into a primary research area:

```bash
export TOGETHER_API_KEY="your-api-key-here"

python -m reviewer_sim.ingest.enrich_primary_area \
  --in-path outputs/review_subset.jsonl \
  --out-path outputs/review_subset_enriched.jsonl \
  --model "meta-llama/Llama-3-8b-chat-hf" \
  --max-concurrency 8
```

**Adds to each record**:
- `primary_area_llm`: string (one of 11 allowed labels or "other")
- `primary_area_llm_confidence`: float (0.0-1.0)
- `meta.llm_labeling`: provenance info (provider, model, prompt version, temperature, timestamp)

**Resume interrupted runs**:
```bash
python -m reviewer_sim.ingest.enrich_primary_area \
  --in-path outputs/review_subset.jsonl \
  --out-path outputs/review_subset_enriched.jsonl \
  --resume
```

### Step 3: Run Simulation with Enriched Data
Use the enriched JSONL to generate reviews with domain-specific personas:

```bash
export MODEL_PROVIDER=together
export MODEL_PATH="meta-llama/Llama-3-8b-chat-hf"
export TOGETHER_API_KEY="your-api-key-here"
export INPUT_JSONL=outputs/review_subset_enriched.jsonl
export OUTPUT_JSONL=outputs/results.jsonl

python -m reviewer_sim.run
```

**Key behavior**:
- The system prompt is formatted with the paper's `primary_area_llm` field
- Each paper gets a reviewer with matching domain expertise
- Fallback to "general" expertise if `primary_area_llm` is missing

## Changes Made to Support Integration

### 1. `config.py`
**Changed**: `DEFAULT_SYSTEM_PROMPT` now includes `{primary_area}` placeholder

```python
DEFAULT_SYSTEM_PROMPT = (
    "You are an ICLR 2023 peer reviewer with expertise in the following area: {primary_area}.\n"
    # ... rest of prompt
)
```

### 2. `providers.py`
**Changed**: All generator classes now format the system prompt with `primary_area_llm`

**LlamaCppGenerator._build_prompt()**:
```python
primary_area = example.get("primary_area_llm", "general")
system_prompt = self.config.system_prompt.format(primary_area=primary_area)
```

**TogetherGenerator._build_messages()**:
```python
primary_area = example.get("primary_area_llm", "general")
system_prompt = self.config.system_prompt.format(primary_area=primary_area)
```

**MockGenerator.generate()**:
```python
# Uses primary_area_llm if available, otherwise falls back to reviewer_profile.expertise
expertise = example.get("primary_area_llm") or profile.get("expertise", "general")
```

### 3. `run.py`
**Changed**: Added comprehensive documentation in module docstring explaining:
- The 3-step workflow
- Why enrichment is recommended
- How to structure the pipeline

### 4. `tests/test_enrich_primary_area.py`
**Added**: 22 unit tests covering:
- Response parsing and validation (13 tests)
- Resume functionality (6 tests)
- Allowed labels (3 tests)

All tests pass: `pytest tests/test_enrich_primary_area.py -v`

## Data Flow

```
SQLite Database
    ↓
export_review_subset (ingest)
    ↓
review_subset.jsonl (base records: title, abstract, decision, review, scores)
    ↓
enrich_primary_area (Together AI API)
    ↓
review_subset_enriched.jsonl (added: primary_area_llm, confidence, meta.llm_labeling)
    ↓
run.py (generate reviews)
    ↓
results.jsonl (generated_review, metrics)
```

## Backward Compatibility

- If `primary_area_llm` is missing from input records, defaults to `"general"` expertise
- Existing non-enriched JSONL files continue to work
- No breaking changes to the core pipeline

## Testing

Run all tests:
```bash
PYTHONPATH=src pytest tests/test_enrich_primary_area.py -v
```

Expected output:
```
22 passed in 0.15s
```

## Example Prompts

When `primary_area_llm="nlp"`:
```
You are an ICLR 2023 peer reviewer with expertise in the following area: nlp.
Your task is to simulate how human reviewers on OpenReview would score this ICLR submission.
...
```

When `primary_area_llm="computer_vision"`:
```
You are an ICLR 2023 peer reviewer with expertise in the following area: computer_vision.
Your task is to simulate how human reviewers on OpenReview would score this ICLR submission.
...
```

## Troubleshooting

### "TOGETHER_API_KEY environment variable is required"
Set the API key before running enrich_primary_area:
```bash
export TOGETHER_API_KEY="your-actual-key"
```

### "confidence" field not a number
The enrich_primary_area script validates and clamps confidence to [0.0, 1.0]. Invalid values are set to 0.3.

### Primary area not appearing in system prompt
Ensure your INPUT_JSONL has the `primary_area_llm` field. Check with:
```bash
jq '.primary_area_llm' outputs/review_subset_enriched.jsonl | head -5
```

## Performance Notes

- **enrich_primary_area**: ~10-30 records/second with `--max-concurrency 8` (depends on Together API)
- **run.py**: ~1-5 records/second depending on model size and provider
- Use `--limit N` flag on enrich_primary_area for testing on small subsets

## Future Enhancements

- Add support for multiple primary areas (multi-label classification)
- Cache enrichment results to avoid re-classifying papers
- Fine-tune area classification model on ICLR acceptance patterns
- Add paper-to-reviewer matching based on primary_area alignment
