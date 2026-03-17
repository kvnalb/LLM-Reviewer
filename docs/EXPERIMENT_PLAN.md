# Experiment Plan: Score-Based Review Simulation

## Objective

Compare LLM-generated review scores against human reviewer scores and GPT-4o baselines
for 2023 ICLR papers with known Accept/Reject outcomes.

## Data Flow

```
gen_review.db
    │
    ▼
export_2023_subset.py
    │
    ▼
review_subset_2023.jsonl
    │
    ├──► GPT-4o baseline (already embedded in JSONL, no API calls)
    │        │
    │        ▼
    │    gpt4o_baseline.rating vs human_review.rating
    │
    └──► TogetherGenerator / LlamaCppGenerator
             │
             ▼
         LLM-predicted scores
             │
             ▼
     evaluate/metrics.py
         │
         ├── Text-based   (TF-IDF cosine, Jaccard)
         ├── Score-based   (MAE, Spearman per dimension)
         └── Decision-based (Accuracy, F1, confusion matrix)
```

## Evaluation Modes

### Mode 1: Text Comparison (existing, backward-compatible)

- TF-IDF cosine similarity: LLM review text vs human review text
- Keyword Jaccard: token overlap
- Works for any provider that returns `{"text": "..."}`

### Mode 2: Score Comparison (new, primary focus)

**Input to LLM:** title + abstract

**Output from LLM:** JSON with numeric scores:

- rating (1-10)
- confidence (1-5)
- correctness (1-4)
- technical_novelty (1-4)
- empirical_novelty (1-4)

**Metrics:**

- MAE per dimension (LLM vs human)
- MAE per dimension (LLM vs GPT-4o baseline)
- Spearman rank correlation per dimension
- Score distribution comparison

**Advantages over text comparison:**

- ~50 output tokens vs ~500+ for full review text
- Deterministic evaluation (no TF-IDF noise)
- Directly comparable across models
- Can also compare GPT-4o baseline vs human as a reference point

### Mode 3: Decision Prediction (new)

**Input to LLM:** title + abstract

**Output from LLM:** "Accept" or "Reject" (+ optional confidence float)

**Metrics:**

- Accuracy, Precision, Recall, F1
- Confusion matrix
- ROC-AUC (if confidence provided)
- Compare to: GPT-4o rating threshold → Accept/Reject accuracy

**Advantages:**

- Minimal output tokens
- Binary ground truth available for every paper
- Most direct measure of "can an LLM replicate the review outcome?"

## Execution Order

1. Fix 2023 export (summary_of_the_review, correct JSONL schema, include GPT-4o data)
2. GPT-4o baseline analysis (no API calls — just analyze existing data)
3. Score prediction: TogetherGenerator with score-only prompt
4. Decision prediction: TogetherGenerator with accept/reject prompt
5. Cross-model comparison (vary TOGETHER_MODEL)
6. (Optional) TF-IDF comparison on 2023 slice for PI

## Models to Compare (Together AI)

- meta-llama/Llama-3-8b-chat-hf (fast, cheap)
- meta-llama/Llama-3-70b-chat-hf (stronger)
- mistralai/Mixtral-8x7B-Instruct-v0.1 (already used for enrichment)
- Others as needed