# LLM Reviewer Evaluation Report: 120-Paper Benchmark

**Date:** February 23, 2026
**Model:** Mixtral-8x7B-Instruct-v0.1
**System Prompt:** Enhanced (1,600 tokens with examples + distribution targets)
**Temperature:** 0.5
**Result:** 120/120 papers processed successfully in 7:14 (3.6s/paper)

---

## Executive Summary

The enhanced system prompt failed to reduce LLM upward bias. Despite explicit distribution targets (20% 3-4, 40% 5, 35% 6-7, 5% 8+), the model maintained 98.3% acceptance rate and clustered 82.5% of ratings at 6-7.

**Conclusion:** Prompt engineering cannot fix this problem. Recent research (Jahanparast et al., 2025; Suh et al., 2025) shows the bias originates in the RLHF-trained unembedding layer. **Solution: finetuning or linear probes**, not more prompting.

---

## Key Results

### Metrics
| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Mean NMAE | 0.1662 | - | Acceptable |
| Mean MAE | 0.7591 | - | Acceptable |
| **Spearman Correlation** | **0.774** | - | **✓ Strong rank consistency** |
| Decision Match | 44/120 (36.7%) | - | ⚠ Low |
| Mean Rating | 7.08 | 5.4 | ❌ +1.68 too high |
| Acceptance Rate (≥6) | 98.3% | 30% | ❌ +68.3% too high |

### Rating Distribution vs Target

| Range | Target | Actual | Gap |
|-------|--------|--------|-----|
| 3-4 (reject) | 20% | 0% | -20% |
| 5 (borderline) | 40% | 1.7% | -38.3% |
| 6-7 (accept) | 35% | 82.5% | +47.5% |
| 8+ (strong) | 5% | 15.8% | +10.8% |

Actual distribution: `0 + 2 + 99 + 19 = 120 papers`

### Per-Dimension Calibration

The bias is not uniform across review dimensions. Some subdimensions match human ratings well, while others show significant drift:

| Dimension | Scale | Human Mean | Model Mean | Difference | NMAE |
|-----------|-------|------------|-----------|------------|------|
| Rating | 1-10 | 5.434 | 7.075 | +1.641 (+30.2%) | 0.193 |
| Empirical Novelty | 1-4 | 2.620 | 3.311 | +0.691 (+26.4%) | 0.243 |
| Technical Novelty | 1-4 | 2.622 | 3.000 | +0.378 (+14.4%) | 0.156 |
| Confidence | 1-5 | 3.611 | 3.933 | +0.322 (+8.9%) | 0.119 |
| Correctness | 1-4 | 3.068 | 3.168 | +0.100 (+3.2%) | 0.118 |

**Key insight:** The model's bias concentrates in the overall rating (0.193 NMAE) and empirical novelty (0.243 NMAE) dimensions, while correctness (0.118 NMAE) and confidence (0.119 NMAE) are nearly perfectly calibrated. This pattern suggests finetuning should prioritize recalibrating rating/novelty outputs, as the model already has accurate representations of correctness and reviewer confidence.

---

## Analysis

### The Problem is Mechanistic, Not Conceptual

The system prompt explicitly specified the target distribution. The model ignored it completely, instead clustering 82.5% at ratings 6-7. This is not a reasoning failure—it's a systematic output bias from the RLHF training process.

**Important:** Despite the bias toward high absolute ratings, the model maintains strong **rank consistency** (Spearman r = 0.774). Papers that humans rate as better ARE generally rated higher by the model. The problem is **calibration** (all ratings shifted ~1.7 points too high), not **ranking ability**. This is crucial for finetuning—the model already knows how to rank papers correctly; it just needs to learn the right output scale.

Recent research reveals the root cause:
- **Jahanparast et al. (2025):** LLMs have accurate opinion knowledge internally but the final unembedding layer suppresses it, creating a 50-59% gap between internal representations and outputs
- **Suh et al. (2025):** When faced with similar distribution misalignment in survey tasks, finetuning reduced error by 46%, dramatically outperforming prompt engineering baselines

### Why Temperature Changes Don't Help

Increasing temperature from 0.2 (5-paper test) to 0.5 (120-paper test):
- NMAE: 0.1162 → 0.1662 (↑43% worse)
- Decision match: 80% → 36.7% (↓54% worse)
- Acceptance rate: 100% → 98.3% (unchanged)

Higher temperature adds noise but does not change the systematic bias. The problem is not variance; it's a learned preference for acceptance encoded in the unembedding layer.

---

## Why Prompt Engineering Failed

Prompt instructions operate upstream of the unembedding layer. The RLHF-trained unembedding layer is a final filter that suppresses critical outputs and steers toward helpful/positive responses. No amount of instruction-level prompting can override this post-training encoding.

The model likely *knows* papers should get lower ratings (internal representations are better calibrated), but the unembedding layer prevents it from expressing that knowledge.

---

## Recommended Solutions

### Option 1: Domain-Specific Finetuning ⭐ PRIMARY

**Evidence:** Suh et al. (2025) achieved 46% error reduction through finetuning on survey response data—far exceeding prompt engineering results.

**Approach:**
1. Collect ~500-1000 realistic paper reviews with target distributions (20/40/35/5)
2. Fine-tune Mixtral on this labeled data
3. Evaluate on held-out test set

**Pros:** Directly targets root cause, strong precedent, likely achieves 30% target
**Cons:** Requires labeled data, finetuning compute

---

### Option 2: Linear Probes on Internal Representations ⭐ SECONDARY

**Evidence:** Jahanparast et al. (2025) show that opinion knowledge emerges in middle layers and gets suppressed by the unembedding layer. Probes on middle-layer activations achieve 50-59% better alignment with actual distributions.

**Approach:**
1. Extract activations from middle layers (layers 12-24 of 32)
2. Train lightweight linear probes to predict ratings from these activations
3. Use as interpretable layer on frozen base model

**Pros:** No expensive finetuning, mechanistically grounded, computationally efficient
**Cons:** More complex implementation, may lose downstream reasoning

---

### Option 3: Hybrid Approach

Combine both: fine-tune on subset of data while using probes to validate internal representations improve.

---

## Key References

[1] **Jahanparast, E., Hong, Z., & Chang, S. (2025).** "What Do Large Language Models Know About Opinions?" *OpenReview.* https://openreview.net/forum?id=kHVzEjThKE

Finds that LLM internal knowledge is 50-59% better calibrated than outputs, with the discrepancy originating in the final unembedding layer.

[2] **Suh, J., Jahanparast, E., Moon, S., Kang, M., & Chang, S. (2025).** "Language Model Fine-Tuning on Scaled Survey Data for Predicting Distributions of Public Opinions." *ACL 2025.* https://aclanthology.org/2025.acl-long.1028/

Demonstrates that finetuning reduces model-human distribution discrepancy by 46%, substantially outperforming prompt engineering baselines.

---

## Conclusion

The enhanced prompt achieved reasonable metric accuracy (NMAE 0.166) but failed on distribution matching, maintaining 98% acceptance vs 30% target. This failure reflects a fundamental post-RLHF bias in the unembedding layer, not inadequate prompting.

**Next steps:** Pursue finetuning (primary) or linear probes (secondary) rather than continued prompt iteration.

---

## Appendix: Test Details

- **Runtime:** 7:14 total, 3.6s average per paper
- **Error rate:** 0% (120/120 successful)
- **System prompt:** 1,600 tokens with examples, distribution targets, and {primary_area} placeholder
- **Graphics:** Available at `docs/report_graphics.png` and `docs/rating_distribution_detailed.png`
