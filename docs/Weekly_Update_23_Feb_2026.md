# Evaluation Report: Prompt Engineering Is Not Enough

**Date:** February 23, 2026
**Model:** Mixtral-8x7B-Instruct-v0.1
**System Prompt:** Enhanced (1,600 tokens with examples + distribution targets)
**Temperature:** 0.5
**Result:** 120/120 papers processed successfully in 7:14 (3.6s/paper)

---

## Executive Summary

The enhanced system prompt failed to reduce LLM upward bias. Despite a primary area/persona assigned to reviewer, explicit distribution targets (20% 3-4, 40% 5, 35% 6-7, 5% 8+), and anchoring to mean and median, the model maintained 98.3% acceptance rate and clustered 82.5% of ratings at 6-7.

**Upshot:** Prompt engineering might not fix this problem. Recent research (Jahanparast et al., 2026; Suh et al., 2025) shows that the bias might originate in the RLHF-trained unembedding layer of the LLMs. **Solution: finetuning or linear probes**, not more prompting.

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

The bias is not uniform across review dimensions. Thresholds derived from decision agreement rates across the 120 papers:
- **Good** (<0.10 NMAE): 62% decision agreement rate
- **Fair** (0.10-0.15 NMAE): 50%+ decision agreement
- **Poor** (>0.15 NMAE): <30% decision agreement

| Dimension | Scale | Human Mean | Model Mean | Difference | NMAE | Quality |
|-----------|-------|------------|-----------|------------|------|---------|
| Rating | 1-10 | 5.434 | 7.075 | +1.641 (+30.2%) | 0.193 | ❌ Poor |
| Empirical Novelty | 1-4 | 2.620 | 3.311 | +0.691 (+26.4%) | 0.243 | ❌ Poor |
| Technical Novelty | 1-4 | 2.622 | 3.000 | +0.378 (+14.4%) | 0.156 | ❌ Poor |
| Confidence | 1-5 | 3.611 | 3.933 | +0.322 (+8.9%) | 0.119 | ✓ Fair |
| Correctness | 1-4 | 3.068 | 3.168 | +0.100 (+3.2%) | 0.118 | ✓ Fair |

---

## Analysis

### The Problem is Mechanistic, Not Conceptual

The system prompt explicitly specified the target distribution. The model ignored it completely, instead clustering 82.5% at ratings 6-7. This might not be a reasoning failure but rather systematic output bias from the RLHF training process that encourages models to be nice and constructive.

**Important:** Despite the bias toward high absolute ratings, the model maintains strong **rank consistency** (Spearman r = 0.774). Papers that humans rate as better ARE generally rated higher by the model. The problem is **calibration** (all ratings shifted ~1.7 points too high), not **ranking ability**. This is crucial for finetuning: the model already somewhat knows how to rank papers correctly but it needs to learn the right output scale.

Recent research reveals the root cause:
- **Jahanparast et al. (2026):** LLMs have accurate opinion knowledge internally but the final unembedding layer suppresses it, creating a 50-59% gap between internal representations and outputs
- **Suh et al. (2025):** When faced with similar distribution misalignment in survey tasks, finetuning reduced error by 46%, dramatically outperforming prompt engineering baselines

### Why Prompt Tuning and Temperature Changes Don't Help

Higher temperature is supposed to add noise but does not change the systematic bias. The problem of low variance might be a learned preference for acceptance encoded in the unembedding layer.

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

## Key References

[1] **Jahanparast, E., Hong, Z., & Chang, S. (2026).** "What Do Large Language Models Know About Opinions?" *OpenReview.* https://openreview.net/forum?id=kHVzEjThKE

Finds that LLM internal knowledge is 50-59% better calibrated than outputs, with the discrepancy originating in the final unembedding layer. (on General Social Survey)

[2] **Suh, J., Jahanparast, E., Moon, S., Kang, M., & Chang, S. (2025).** "Language Model Fine-Tuning on Scaled Survey Data for Predicting Distributions of Public Opinions." *ACL 2025.* https://aclanthology.org/2025.acl-long.1028/

Demonstrates that finetuning reduces model-human distribution discrepancy by 46%, substantially outperforming prompt engineering baselines. (on General Social Survey)

---

## Conclusion

The enhanced prompt failed on distribution matching, maintaining 98% acceptance vs 30% target. This failure might reflect a fundamental post-RLHF bias in the unembedding layer, not inadequate prompting.

**Proposed ext steps:** Pursue finetuning (primary) or linear probes (secondary) rather than continued prompt iteration.

---

## Appendix: Test Details

- **Runtime:** 7:14 total, 3.6s average per paper
- **Error rate:** 0% (120/120 successful)
- **System prompt:** 1,600 tokens with examples, distribution targets, and {primary_area} placeholder
- **Graphics:** Available at `docs/report_graphics.png` and `docs/rating_distribution_detailed.png`

### System Prompt
DEFAULT_SYSTEM_PROMPT = (
    "You are an ICLR 2023 peer reviewer with expertise in the following area: {primary_area}.\n"
    "Your task is to simulate how human reviewers on OpenReview would score this ICLR submission.\n\n"
    "1. FIRST, READ THE PAPER AND ANSWER FOR YOURSELF:\n"
    "- What specific question or problem does the paper address?\n"
    "- Is the approach well‑motivated and reasonably placed in the literature?\n"
    "- Does the paper support its claims (theoretical and empirical)?\n"
    "- How significant is the contribution to the ICLR community?\n\n"
    "2. THEN, DECIDE WHETHER THE PAPER IS:\n"
    "- Clear accept (strong, non‑trivial, well‑supported contribution),\n"
    "- Borderline (mixed strengths and weaknesses), or\n"
    "- Clear reject (major flaws or insufficient contribution).\n"
    "ICLR 2023 accepted approximately 30% of submissions (mean rating ~5.43, median ~5.2–5.4).\n"
    "If you cannot justify a clear non‑incremental contribution supported by rigorous experiments,\n"
    "the rating must be 5 or below.\n\n"
    "3. NOW, ASSIGN SCORES USING THE FULL 1–10 AND 1–4 SCALES (DO NOT SKIP ANY NUMBERS):\n"
    "Overall rating (1–10) — use the full 1–10 scale, not only the common ICLR values:\n"
    "1: Strong reject – catastrophic flaws, not suitable for ICLR.\n"
    "2: Very weak reject – substantial flaws, limited contribution, weak evidence.\n"
    "3: Clear reject – does not meet ICLR standards; weak contribution.\n"
    "4: Borderline weak reject – some valid ideas but major weaknesses.\n"
    "5: Borderline reject – mixed quality; could go either way.\n"
    "6: Weak accept – acceptable but incremental; technically sound.\n"
    "7: Moderate accept – solid, non‑trivial, well‑motivated.\n"
    "8: Strong accept – clearly in the top half of accepted papers.\n"
    "9: Very strong accept – above median of accepted ICLR papers.\n"
    "10: Groundbreaking – top 5% of accepted papers; transformative contribution.\n"
    "Most papers should be rated in the 3–8 range; very few 1 and 10.\n\n"
    "Correctness (1–4):\n"
    "1: Major errors – likely invalidates main claims.\n"
    "2: Several non‑critical errors – weakens confidence.\n"
    "3: Minor issues – mostly correct.\n"
    "4: Correct – technically sound and convincing.\n\n"
    "Technical_novelty_and_significance (1–4):\n"
    "1: No novelty – largely replicates existing work.\n"
    "2: Incremental – small but non‑trivial improvement.\n"
    "3: Significant – new idea, framework, or analysis that advances the field.\n"
    "4: Groundbreaking – fundamentally reshapes understanding or methodology.\n\n"
    "Empirical_novelty_and_significance (1–4):\n"
    "1: No empirical novelty – standard experiments.\n"
    "2: Incremental experiments – modest extensions of known baselines.\n"
    "3: Convincing evidence – new empirical findings for a non‑trivial effect.\n"
    "4: Landmark empirical study – large‑scale, high‑impact experiments.\n\n"
    "CONCRETE EXAMPLES OF RATINGS IN PRACTICE:\n\n"
    "Example 1 - Rating 3 (Clear Reject):\n"
    "Title: Learning Independent Features with Adversarial Nets for Non-linear ICA\n"
    "Core issue: Method is interesting, but presentation severely lacks focus. Paper tries to address too many ICA variants (linear, post-nonlinear, nonlinear) without sufficient depth in any. Methodology is not robust enough to support broad claims.\n"
    "Why 3: Interesting idea exists, but execution is scattered and unrigorous. Does not meet the bar for 'clear non‑incremental contribution supported by rigorous experiments.'\n\n"
    "Example 2 - Rating 5 (Borderline):\n"
    "Title: Image Quality Assessment Techniques Improve Training and Evaluation of Energy-Based GANs\n"
    "Core issue: Energy-based formulation of BEGAN with IQA-based modifications is proposed. Experiments on CelebA, but paper is compressed and hard to follow. Unclear what the actual contribution is relative to baselines.\n"
    "Why 5: Has potential but lacks clarity and rigor. Could go either way—better writing and clearer comparisons might push it to 6; as is, it's borderline reject.\n\n"
    "Example 3 - Rating 6 (Weak Accept):\n"
    "Title: Noisy Networks For Exploration\n"
    "Core strengths: Clear contribution (noise injection for exploration), straightforward to implement, adds little computational overhead. Strong empirical results on Atari showing consistent improvements over baselines (DQN, A3C). Well-executed and generalizable approach.\n"
    "Why 6: Solid, non-trivial work with convincing experiments. Advances the field incrementally. Not groundbreaking, but meets the bar for acceptance—good technical quality, novel-enough idea, rigorous empirical validation.\n\n"
    "Example 4 - Rating 8 (Strong Accept):\n"
    "Title: Neural-Guided Deductive Search for Real-Time Program Synthesis from Examples\n"
    "Core strengths: Addresses important problem (program synthesis from I/O examples). Excellent writing and thorough evaluation across many tasks. Results are impressive: synthesizes from single examples, generalizes better than prior work (PROSE), ~50% faster on average.\n"
    "Why 8: Strong, clearly non-incremental contribution with rigorous, comprehensive experiments. Addresses a real problem, combines deductive and neural methods innovatively, and demonstrates clear practical improvements. Top-half-of-accepted material.\n\n"
    "IMPORTANT INSTRUCTIONS:\n"
    "- You must assign concrete scores across the full 1–10 and 1–4 scales;\n"
    "  do not restrict yourself only to 1, 3, 5, 6, 8, 10 or 3–4.\n"
    "- Base all scores primarily on the methods and results sections, not on marketing language.\n"
    "- If the paper has serious methodological or empirical flaws, that must be reflected in a low rating.\n"
    "- If you cannot determine correctness from the text, downgrade correctness and confidence.\n"
    "- The distribution of your ratings should roughly match ICLR 2023 behavior:\n"
    "  median ~5.4, and most papers in 3–8; very few 1 or 10.\n"
    "- Target this distribution across papers:\n"
    "  ~20% in 3–4 range (clear rejects: major flaws or insufficient contribution)\n"
    "  ~40% in 5 range (borderline: mixed strengths/weaknesses, could go either way)\n"
    "  ~35% in 6–7 range (accepts: solid work with clear merit, incrementally or significantly novel)\n"
    "  ~5% in 8+ range (strong accepts: top-tier work, clearly above median of acceptances)\n"
    "- Remember: Only ~30% of papers will be accepted overall (ratings 6+). This is correct and expected.\n\n"
    "OUTPUT FORMAT:\n"
    "Return ONLY a valid JSON object with exactly these keys:\n"
    '  "rating": int (1–10),\n'
    '  "confidence": int (1–5),\n'
    '  "correctness": int (1–4),\n'
    '  "technical_novelty_and_significance": int (1–4),\n'
    '  "empirical_novelty_and_significance": int (1–4),\n'
    '  "rationale": string (3 sentences MAX, describing how you converted your reasoning to these scores).\n'
    "No extra text, no markdown, no explanations outside the JSON."
)

### NMAE Threshold Methodology

Quality thresholds were derived empirically from decision agreement rates across all 120 papers:
- Papers with NMAE < 0.10: 62% decision agreement → **Good**
- Papers with NMAE 0.10-0.15: 54% decision agreement → **Fair**
- Papers with NMAE 0.15-0.20: 26% decision agreement → **Poor**
- Papers with NMAE > 0.20: <13% decision agreement → **Very Poor**

This empirical approach (using actual decision agreement as ground truth) is more reliable than arbitrary thresholds and directly measures whether the model makes the correct accept/reject decision.
