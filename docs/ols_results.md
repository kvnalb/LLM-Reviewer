# OLS Regression: Human Scores ~ LLM Scores

**Dataset:** 7 models, 120 papers, 5 fields → 4160 observations

> **Note:** The pooled-across-fields R² is a methodological artifact — it captures
> cross-field scale differences (rating 1–10 vs correctness 1–4), not predictive power.
> All interpretation should use the per-field numbers.

## Spec 1: `human ~ llm` (no fixed effects)

| Field | β | Intercept | R² | N |
|-------|---|-----------|-----|---|
| rating | 0.333 | 2.956 | 0.052 | 832 |
| confidence | -0.021 | 3.693 | 0.001 | 832 |
| correctness | 0.086 | 2.758 | 0.010 | 832 |
| technical_novelty_and_significance | 0.177 | 2.077 | 0.042 | 832 |
| empirical_novelty_and_significance | 0.153 | 2.163 | 0.039 | 832 |

*Pooled (misleading — do not use): β=0.554, R²=0.614*

## Spec 2: `human ~ llm + C(model)` (model fixed effects)

| Field | β | R² | ΔR² vs no-FE | N |
|-------|---|-----|--------------|---|
| rating | 0.525 | 0.082 | +0.030 | 832 |
| confidence | -0.110 | 0.006 | +0.005 | 832 |
| correctness | 0.218 | 0.026 | +0.016 | 832 |
| technical_novelty_and_significance | 0.341 | 0.080 | +0.038 | 832 |
| empirical_novelty_and_significance | 0.264 | 0.068 | +0.028 | 832 |

*Pooled (misleading — do not use): β=0.587, R²=0.651*

## Interpretation

LLM scores explain **1–8% of variance** in human scores on any individual field.
Model fixed effects add ≤0.04 ΔR², meaning per-model intercept shifts explain
almost none of the residual. The β for confidence is slightly negative (−0.021),
indicating no meaningful signal.

This confirms the score compression finding: models output scores in a narrow
band that does not track paper-level variation in human assessments.
