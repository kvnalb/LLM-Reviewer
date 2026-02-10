# Design Context

## Why numerical evaluation?

Early exploratory analysis (see `scripts/exploratory/`) revealed:

1. **Length mismatch**: Human reviews (`summary_of_the_review`) average ~550 chars, while
   GenAI neutral reviews (`generated`) average ~4 800 chars — a ~9× difference. Text-based
   similarity metrics (TF-IDF cosine, keyword Jaccard) are dominated by this length gap.
2. **Clean numerical scores**: The 5 score columns (`rating`, `confidence`, `correctness`,
   `technical_novelty_and_significance`, `empirical_novelty_and_significance`) parse cleanly
   into numeric values with well-defined ranges.
3. **Robustness**: Numeric comparison (absolute error, MAE, decision agreement) is immune to
   writing style, length, and tokenisation artifacts.

## Data slice

Default export targets:

- **Year**: 2023
- **Excluded decisions**: Withdrawn, Desk Reject, Invite to Workshop
- **Sample size**: 200 papers (top by `summary_of_the_review` length or random)

## Column semantics (ICLR OpenReview)

| Column                      | Meaning                                              |
| --------------------------- | ---------------------------------------------------- |
| `main_review`               | Full review text (populated for ≤2022 papers)        |
| `summary`                   | Reviewer's summary **of the paper** (not a review)   |
| `summary_of_the_review`     | Short review written by the human reviewer (2023+)   |

The export script uses `COALESCE(main_review, summary_of_the_review)` to unify
these across years. The `summary` column is exported as `paper_summary` — a
separate, non-review field.

## Evaluation metrics

| Metric                | Description                                        |
| --------------------- | -------------------------------------------------- |
| Per-dim absolute error| `|human_score − generated_score|` for each of 5 dims |
| MAE                   | Mean of per-dim abs errors                         |
| Decision agreement    | Whether both ratings fall on the same side of the accept threshold (default 6) |
