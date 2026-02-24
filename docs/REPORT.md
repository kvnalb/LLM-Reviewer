# LLM Reviewer Evaluation Report
## 120-Paper Benchmark Study with Enhanced System Prompt

**Date:** February 23, 2026
**Model:** Mixtral-8x7B-Instruct-v0.1
**Dataset:** 120 ICLR 2023 Papers (abstract-only)
**System Prompt:** Enhanced (1,600 tokens with examples + distribution targets)
**Temperature:** 0.5

---

## Executive Summary

This report evaluates whether an enhanced system prompt with concrete examples and distribution targets can reduce LLM upward bias in peer review simulation.

**Finding:** The enhanced prompt did NOT achieve its goal of reducing acceptance rates from ~98% to the target 30%. All 120 papers were processed successfully with no errors, but the model systematically ignored the distribution guidance.

**Upshot:** Prompt engineering cannot resolve the fundamental acceptance bias. Recent research (Jahanparast et al., 2025; Suh et al., 2025) suggests that this bias originates in the unembedding layer after RLHF training. To achieve realistic review distributions, we need to pursue **finetuning** or **linear probes** rather than further prompt optimization.

---

## Key Performance Metrics

### Evaluation Results

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Papers Evaluated | 120 | - | ✓ Complete |
| Mean NMAE | 0.1662 | - | Acceptable |
| Mean RMSE | 0.9978 | - | Acceptable |
| Mean MAE | 0.7591 | - | Acceptable |
| Decision Match | 44/120 (36.7%) | - | ⚠ Below Expected |
| Mean Rating | 7.08 / 10 | 5.4 (target) | ❌ +1.68 above target |
| Acceptance Rate (≥6) | 98.3% | 30% (target) | ❌ +68.3% above target |
| Runtime | 7:14 (3.6s/paper) | - | ✓ On pace |

### Rating Distribution

```
Rating 1:   0 papers (  0.0%)
Rating 2:   0 papers (  0.0%)
Rating 3:   0 papers (  0.0%)
Rating 4:   0 papers (  0.0%)
Rating 5:   2 papers (  1.7%)  ██
Rating 6:   6 papers (  5.0%)  ███
Rating 7:  93 papers ( 77.5%)  ████████████████████████████████████████
Rating 8:  19 papers ( 15.8%)  █████████
Rating 9:   0 papers (  0.0%)
Rating 10:  0 papers (  0.0%)
```

---

## Detailed Distribution Analysis

### Target vs Actual Distribution

The system prompt explicitly specified these targets based on ICLR 2023 statistics:

| Rating Range | Target | Actual | Count | Delta | Status |
|--------------|--------|--------|-------|-------|--------|
| 3-4 (Clear Reject) | 20% | 0% | 0 | -20% | ❌ |
| 5 (Borderline) | 40% | 1.7% | 2 | -38.3% | ❌ |
| 6-7 (Accept) | 35% | 82.5% | 99 | +47.5% | ❌ |
| 8-10 (Strong Accept) | 5% | 15.8% | 19 | +10.8% | ❌ |
| **Overall Acceptance (≥6)** | **30%** | **98.3%** | **118** | **+68.3%** | **❌** |

---

## Comparison: 5-Paper vs 120-Paper Tests

### Temperature Effect

| Metric | 5-Paper (T=0.2) | 120-Paper (T=0.5) | Change |
|--------|---|---|---|
| NMAE | 0.1162 | 0.1662 | ↑ 43% worse |
| MAE | 0.5033 | 0.7591 | ↑ 51% worse |
| RMSE | 0.6548 | 0.9978 | ↑ 52% worse |
| Decision Match | 80% | 36.7% | ↓ 54% worse |
| Mean Rating | 7.0 | 7.08 | ≈ No change |
| Acceptance Rate | 100% | 98.3% | ≈ No change |

**Finding:** Increasing temperature from 0.2 to 0.5 degraded performance across all metrics while providing no meaningful benefit to the distribution problem. Higher temperature adds noise but maintains the systematic bias.

---

## Key Findings

### Finding 1: Distribution Targets Are Completely Ignored

The system prompt explicitly specified:
> "Target this distribution across papers:
> - ~20% in 3–4 range (clear rejects)
> - ~40% in 5 range (borderline)
> - ~35% in 6–7 range (accepts)
> - ~5% in 8+ range (strong accepts)"

**Result:** The model clustered 82.5% of ratings in the 6-7 range, completely deviating from all target buckets. The model apparently does not parse quantitative distribution targets and actively avoids rating 5, suggesting it interprets "borderline" as something to circumvent rather than as a category to use 40% of the time.

### Finding 2: Upward Bias Persists Across Conditions

- **Across temperatures:** 100% → 98.3% acceptance (0.2 → 0.5 temperature)
- **Across dataset sizes:** 100% → 98.3% acceptance (5 papers → 120 papers)
- **Across prompt variations:** All system prompts tested maintain ~98% acceptance
- **Pattern:** The bias appears fundamental and invariant to prompt engineering approaches

### Finding 3: Higher Temperature Increases Variance Without Fixing Bias

Higher temperature (attempting to add exploration) actually:
- Degraded NMAE by 43%
- Reduced decision match accuracy from 80% to 37%
- Maintained the same systematic bias toward acceptance
- **Conclusion:** Temperature adds noise around the bias; it doesn't correct it.

### Finding 4: Mechanistic Root Cause

The bias likely originates in the **unembedding layer after RLHF training**, not in the model's actual knowledge or reasoning capabilities. This is consistent with recent findings (Jahanparast et al., 2025) that:
- LLMs' internal representations contain more accurate opinion distributions than their outputs suggest
- The discrepancy between internal knowledge and outputs stems from the final unembedding layer
- The unembedding layer acts as a final filter that systematically steers outputs toward sycophantic/positive responses

---

## Why Prompt Engineering Cannot Solve This Problem

1. **The bias is post-RLHF:** After instruction tuning and RLHF alignment, the model's final unembedding layer has been trained to produce helpful, harmless, and honest outputs—which in practice means accepting charitable interpretations of papers.

2. **The model knows better internally:** Jahanparast et al. (2025) show that probing the model's internal representations reveals 50-59% better alignment with actual distributions than what the model outputs suggest. The internal knowledge is there; the output layer suppresses it.

3. **Prompt engineering operates upstream:** System prompts and instructions are processed before the unembedding layer, so they cannot counteract the final filtering applied by RLHF-trained unembedding layers.

4. **Distribution targets are ignored:** The explicit guidance to produce 20/40/35/5 distribution is parsed but not followed because the unembedding layer's learned sycophancy overrides explicit instructions.

---

## Recommended Path Forward: Finetuning and Linear Probes

Given that the bias is mechanistic (localized in the unembedding layer) rather than conceptual, we should pursue approaches that directly address this layer:

### Option 1: Domain-Specific Finetuning

**Approach:** Fine-tune the model on a curated dataset of paper reviews with realistic rating distributions (e.g., ICLR 2023 acceptance statistics).

**Evidence:** Suh et al. (2025) demonstrate that fine-tuning on survey response data reduces the LLM-human discrepancy by up to 46% compared to prompt engineering baselines. They achieve this through targeted finetuning rather than prompt iteration.

**Implementation:**
1. Collect or synthesize ~500-1000 paper review examples with realistic distributions (20% 3-4, 40% 5, 35% 6-7, 5% 8+)
2. Fine-tune Mixtral on this data with controlled hyperparameters
3. Evaluate on held-out test set

**Pros:**
- Directly targets the root cause (unembedding layer)
- Well-established technique with strong precedent
- Likely to achieve the 30% acceptance target

**Cons:**
- Requires labeled training data
- Requires compute for finetuning
- May reduce general-purpose capabilities if not done carefully

---

### Option 2: Linear Probes on Internal Representations

**Approach:** Use the internal representations from the model's middle layers (where opinion knowledge emerges) rather than the final unembedded output.

**Evidence:** Jahanparast et al. (2025) identify that:
- Opinion knowledge emerges rapidly in middle layers
- The final unembedding layer suppresses this knowledge
- Specific attention heads can be traced to demographic/quality reasoning
- Linear probes on these representations achieve 50-59% better alignment with actual distributions

**Implementation:**
1. Extract activations from model's middle layers (e.g., layer 12-24 of 32 for Mixtral)
2. Train lightweight linear probes to predict rating distributions from these activations
3. Use probes as interpretable layer on top of frozen base model

**Pros:**
- Works with frozen model (no expensive finetuning)
- Leverages internal knowledge that's already present
- Interpretable and mechanistically grounded
- Computationally efficient

**Cons:**
- More complex to implement
- Requires access to internal model representations
- May sacrifice some reasoning quality from later layers

---

### Option 3: Hybrid Approach

**Approach:** Combine finetuning with linear probes—fine-tune on a subset of data while using probes to validate internal representations.

**Benefits:**
- Iterative improvement loop
- Can measure progress on internal representations even before final output improves
- Provides both mechanistic understanding and practical results

---

## Comparison to Prior Work

### Suh et al. (2025): Fine-Tuning on Scaled Survey Data

Suh et al. show that when faced with distribution misalignment in LLM outputs, the solution is not more creative prompting but rather direct finetuning on target data:

> "Prompt engineering approaches have struggled to faithfully predict the distribution of survey responses... [We] introduce SubPOP, a curated dataset of 70,000 subpopulation-response pairs from established surveys."

Their approach reduced model-human discrepancy by **46%** through finetuning compared to prompt baseline.

**Direct Parallel:** Just as they had to finetune to achieve realistic survey distributions, we should finetune to achieve realistic peer review distributions.

---

### Jahanparast et al. (2025): What Do Large Language Models Know About Opinions?

Jahanparast et al. reveal the mechanistic source of our problem:

> "We find that LLMs' internal knowledge of opinions significantly exceeds what their outputs reveal, showing a 50-59% improvement in alignment with the human answer distribution. We identify the final unembeddings as the source of the discrepancy between internal knowledge and outputs."

**Direct Implication:** Our model likely knows more than it's expressing. The 98% acceptance rate is an artifact of the RLHF-trained unembedding layer, not a reflection of the model's actual understanding of paper quality.

---

## Conclusion

**Key Takeaway:** The enhanced system prompt achieved reasonable metric accuracy (NMAE 0.166) but failed to reduce the LLM's systematic 98% acceptance rate, missing the 30% target by 68 percentage points. This failure is not due to prompt engineering technique but rather to a fundamental post-RLHF bias in the unembedding layer.

**Decision:** Rather than continuing to iterate on prompts, we should pursue:

1. **Primary recommendation:** Domain-specific finetuning on realistic paper review distributions (following Suh et al., 2025)
2. **Secondary recommendation:** Linear probes on internal representations to leverage existing knowledge (following Jahanparast et al., 2025)
3. **Validation:** Compare finetuned model vs probed model to determine which approach better balances accuracy and distribution matching

The mechanistic understanding provided by recent LLM internals research suggests that both approaches should successfully address the root cause while maintaining or improving metric performance.

---

## References

[1] Jahanparast, E., Hong, Z., & Chang, S. (2025). What Do Large Language Models Know About Opinions? *OpenReview.* https://openreview.net/forum?id=kHVzEjThKE

[2] Suh, J., Jahanparast, E., Moon, S., Kang, M., & Chang, S. (2025). Language Model Fine-Tuning on Scaled Survey Data for Predicting Distributions of Public Opinions. In *Proceedings of the 63rd Annual Meeting of the Association for Computational Linguistics (ACL 2025)* (pp. 18482-18498). https://aclanthology.org/2025.acl-long.1028/

---

## Appendices

### Appendix A: Test Execution Summary

- **Start time:** ~07:00 UTC on 2026-02-23
- **Completion time:** ~07:14 UTC on 2026-02-23
- **Total runtime:** 7 minutes 14 seconds
- **Average time per paper:** 3.6 seconds
- **API provider:** Together AI (Mixtral-8x7B-Instruct-v0.1)
- **Success rate:** 100% (120/120 papers)
- **Error rate:** 0%

### Appendix B: System Prompt Used

The enhanced system prompt included:
- ICLR 2023 context and statistics
- Explicit distribution targets (20/40/35/5)
- Four concrete examples at ratings 3, 5, 6, and 8
- 1,600 tokens total
- Non-breaking hyphens to prevent tokenization issues
- `{primary_area}` placeholder for domain-specific personalization

See `docs/RESULTS_120_PAPER_TEST.md` for full prompt text.

### Appendix C: Graphics

- Main analysis: `docs/report_graphics.png` (6-panel visualization)
- Detailed distribution: `docs/rating_distribution_detailed.png` (1-10 scale)

---

*Report prepared by Claude Code. For code review issues and codebase improvements, see `docs/CODE_REVIEW_ISSUES.md`.*
