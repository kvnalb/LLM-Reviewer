# Decision Metrics Comparison: 5-Paper Sample

Comprehensive comparison of NMAE, Spearman correlation, MAE, RMSE, and decision agreement across three test conditions.

---

## Summary Statistics Across All 5 Papers

### 1. Mixtral + Enhanced Prompt (Abstract-Only)
```
NMAE (Normalized Mean Absolute Error):
  Mean: 0.1164
  Median: 0.1069
  Std: 0.0447

Spearman Correlation:
  Mean: 0.8138
  Median: 0.8386
  P-value: avg 0.1717

MAE (Mean Absolute Error):
  Mean: 0.5034
  Median: 0.4500

RMSE (Root Mean Squared Error):
  Mean: 0.7497
  Median: 0.4743

Decision Agreement:
  Match: 4/5 (80%)
  Mismatch: 1/5 (20%)  ← Paper 1 only

Rating Abs Errors:
  Mean: 1.0 (all papers rated 7, average error across metrics)
```

---

### 2. Mixtral + Enhanced Prompt (With PDF Content)
```
NMAE (Normalized Mean Absolute Error):
  Mean: 0.1423
  Median: 0.1721
  Std: 0.0607

Spearman Correlation:
  Mean: 0.7558
  Median: 0.8944
  P-value: avg 0.1543

MAE (Mean Absolute Error):
  Mean: 0.5766
  Median: 0.5333

RMSE (Root Mean Squared Error):
  Mean: 0.7939
  Median: 0.6992

Decision Agreement:
  Match: 4/5 (80%)
  Mismatch: 1/5 (20%)  ← Paper 1 only

Rating Distribution: 3×7, 2×8
```

**PDF Effect:** NMAE increased (worse), Spearman decreased (worse), MAE increased (worse) overall.

---

### 3. Mock Generator (Abstract-Only, Baseline)
```
NMAE (Normalized Mean Absolute Error):
  Mean: 0.1400
  Median: 0.1458
  Std: 0.0432

Spearman Correlation:
  Mean: 0.6856
  Median: 0.7071
  P-value: avg 0.2638

MAE (Mean Absolute Error):
  Mean: 0.6246
  Median: 0.6500

RMSE (Root Mean Squared Error):
  Mean: 0.8241
  Median: 0.9083

Decision Agreement:
  Match: 4/5 (80%)
  Mismatch: 1/5 (20%)  ← Paper 1 only

Rating: All 6s
```

---

## Head-to-Head Comparison

| Metric | Mixtral Abstract | Mixtral PDF | Mock Baseline | Winner |
|--------|---|---|---|---|
| **NMAE** (lower=better) | **0.1164** | 0.1423 | 0.1400 | Mixtral Abstract ✓ |
| **Spearman** (higher=better) | 0.8138 | **0.7558** | 0.6856 | Mixtral Abstract ✓ |
| **MAE** (lower=better) | **0.5034** | 0.5766 | 0.6246 | Mixtral Abstract ✓ |
| **RMSE** (lower=better) | **0.7497** | 0.7939 | 0.8241 | Mixtral Abstract ✓ |
| **Decision Match** | 80% | 80% | 80% | Tie |
| **Mean Rating** | 7.0 | 7.4 | 6.0 | Mock (realistic) |

---

## Per-Paper Breakdown

### Paper 1 (wmMUAg_l4Qk) - GAN Pruning
Ground truth: Rating 4, Confidence 3.25, Correctness 3, Technical 3.75, Empirical 2
```
Model              | Rating | NMAE  | Spearman | Decision
-------------------|--------|-------|----------|----------
Mixtral Abstract   | 7      | 0.196 | 0.783    | ✗ Mismatch
Mixtral PDF        | 7      | 0.196 | 0.783    | ✗ Mismatch
Mock               | 6      | 0.224 | 0.354    | ✗ Mismatch

Issue: All models rated this paper too high (predicted 6-7, actual 4).
This paper is consistently underperforming across all models.
```

### Paper 2 (ueYYgo2pSSU) - Offline RL
Ground truth: Rating 8, Confidence 3.25, Correctness 3.33, Technical 3.33, Empirical 3.33
```
Model              | Rating | NMAE  | Spearman | Decision
-------------------|--------|-------|----------|----------
Mixtral Abstract   | 7      | 0.106 | 0.918 ★  | ✓ Match
Mixtral PDF        | 8      | 0.172 | 0.574    | ✓ Match
Mock               | 6      | 0.144 | 0.725    | ✓ Match

Best: Mixtral Abstract (NMAE 0.106, Spearman 0.918) ✓✓
PDF version: Correct rating (8) but worse correlation (0.574)
```

### Paper 3 (6qcYDVlVLnK) - Noisy Labels
Ground truth: Rating 7.4, Confidence 4, Correctness 3, Technical 3.2, Empirical 3.6
```
Model              | Rating | NMAE  | Spearman | Decision
-------------------|--------|-------|----------|----------
Mixtral Abstract   | 7      | 0.049 | 0.894 ✓  | ✓ Match
Mixtral PDF        | 7      | 0.049 | 0.894 ✓  | ✓ Match
Mock               | 6      | 0.103 | 0.707    | ✓ Match

Best: Both Mixtral versions (NMAE 0.049, Spearman 0.894) ✓✓
Most accurate paper for all models
```

### Paper 4 (HPdxC1THU8T) - Adversarial Training
Ground truth: Rating 6.5, Confidence 3.75, Correctness 3.25, Technical 3.25, Empirical 3
```
Model              | Rating | NMAE  | Spearman | Decision
-------------------|--------|-------|----------|----------
Mixtral Abstract   | 7      | 0.124 | 0.738    | ✓ Match
Mixtral PDF        | 8      | 0.179 | 0.894 ✓  | ✓ Match
Mock               | 6      | 0.082 | 0.707    | ✓ Match

Best: Mock (lowest NMAE 0.082), but Mixtral PDF has better Spearman
PDF upgrade (7→8) hurt NMAE but improved Spearman
```

### Paper 5 (fxjzKOdw9wb) - Video Augmentation
Ground truth: Rating 7.5, Confidence 3.75, Correctness 2.5, Technical 3, Empirical 3.25
```
Model              | Rating | NMAE  | Spearman | Decision
-------------------|--------|-------|----------|----------
Mixtral Abstract   | 7      | 0.107 | 0.738    | ✓ Match
Mixtral PDF        | 7      | 0.107 | 0.738    | ✓ Match
Mock               | 6      | 0.146 | 0.707    | ✓ Match

All models close to ground truth, Mixtral best
```

---

## Statistical Summary

### Strengths of Mixtral Abstract (Enhanced Prompt)
- **Lowest NMAE** across samples (0.1164 vs 0.1400 mock)
- **Highest Spearman correlation** (0.8138 vs 0.6856 mock)
- **Lowest MAE** (0.5034 vs 0.6246 mock)
- **Best on paper 2 & 3:** Exceptional performance with Spearman 0.918 and 0.894

### Weaknesses of Mixtral Abstract
- **Same 80% decision match** as mock baseline (not an improvement)
- **Paper 1 consistently fails** across all models (systematic bias on this paper)
- **All papers rated 7** → no differentiation despite good correlation

### PDF Content Effect
- **Worse overall NMAE** (0.1423 vs 0.1164 abstract)
- **Lower Spearman** (0.7558 vs 0.8138 abstract)
- **Higher MAE** (0.5766 vs 0.5034 abstract)
- **Rating inflation:** Paper 2 & 4 upgraded (7→8), but correlation suffered

---

## Interpretation

**The enhanced system prompt improves metric accuracy but fails on real-world distribution:**

1. **Good news:** Abstract-only Mixtral has better calibration metrics (NMAE, Spearman, MAE) than mock baseline
2. **Bad news:** Still maintains 100% acceptance rate and loses decision differentiation
3. **Confusing:** PDF content hurts metrics despite providing more information
4. **Consistent problem:** Paper 1 (GAN pruning) systematically misjudged by all models

---

## Recommendation

**Decision: Enhanced Mixtral (Abstract-Only) is marginally better on metrics, but the distribution problem remains fundamental.**

If we're optimizing for:
- **Metric accuracy (NMAE, Spearman):** Use Mixtral Abstract ✓
- **Realistic acceptance rates (30%):** Switch strategy entirely ✗
- **Reproducibility & consistency:** Mock baseline is more predictable (all 6s)

The real issue is not the system prompt quality—it's that LLMs are inherently biased toward acceptance. Mixtral Abstract happens to be slightly better at minimizing error while maintaining that bias.

**Next step:** Don't revert yet. The metrics show improvement. But commit to addressing the fundamental bias issue with a different approach (structural change to task, not prompt refinement).
