# Experiment: 8-Model Abstract-Only Baseline

**Date:** 2026-02-16
**Branch:** `exploratory`
**Dataset:** n=120 ICLR 2023 papers, stratified by decision and rating
**Input:** Title + abstract (up to 3 000 chars)
**Ground truth:** Mean score across all human reviewers per paper

---

## Setup

Eight serverless Together AI models were evaluated spanning a range of architectures and scales:

| Model | Type | Active params |
|-------|------|---------------|
| `meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo` | Dense | 8B |
| `openai/gpt-oss-20b` | Dense | 20B |
| `mistralai/Mistral-Small-24B-Instruct-2501` | Dense | 24B |
| `meta-llama/Llama-3.3-70B-Instruct-Turbo` | Dense | 70B |
| `meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8` | MoE | 17B/128E |
| `Qwen/Qwen3-235B-A22B-Instruct-2507-tput` | MoE | 22B/235B |
| `deepseek-ai/DeepSeek-V3.1` | MoE | ~37B/671B |
| `deepseek-ai/DeepSeek-R1` | Reasoning | ~37B/671B |

DeepSeek-R1 was deferred (pending cost approval; requires `max_tokens=4000` for reasoning chains).

---

## Results

Sorted by NMAE (Normalized MAE, lower is better). NMAE normalises each score dimension's error by its scale range, making errors comparable across the five dimensions.

| Rank | Model | NMAE | Spearman | DecAgr | Rating | Conf | Corr | TechNov | EmpNov | N |
|------|-------|------|----------|--------|--------|------|------|---------|--------|---|
| 1 | DeepSeek-V3.1 | **0.154** | 0.757 | 38.3% | 0.201 | 0.157 | 0.114 | 0.152 | 0.147 | 120 |
| 2 | GPT-OSS-20B | 0.167 | 0.770 | **42.5%** | 0.145 | 0.180 | 0.152 | 0.163 | 0.194 | 120 |
| 3 | Mistral-Small-24B | 0.178 | 0.710 | 36.4% | 0.259 | 0.164 | 0.154 | 0.153 | 0.161 | 120 |
| 4 | Qwen3-235B | 0.195 | **0.839** | 36.7% | 0.210 | 0.151 | 0.289 | 0.174 | 0.151 | 120 |
| 5 | Llama4-Maverick | 0.207 | 0.828 | 37.3% | 0.269 | 0.134 | 0.291 | 0.162 | 0.178 | 120 |
| 6 | Llama-3.3-70B | 0.218 | 0.841 | 35.0% | 0.292 | 0.140 | 0.308 | 0.177 | 0.172 | 120 |
| 7 | Llama-3.1-8B | 0.331 | 0.833 | 36.1% | 0.276 | 0.337 | 0.302 | 0.396 | 0.343 | 120 |

*NMAE per dimension: lower = closer to human. DecAgr = fraction of papers where model and human agree on accept/reject.*

---

## Key Finding: Score Compression Bias

Decision agreement is uniformly low (35–43%) across all models, including the largest and most capable ones. The primary cause is **score compression** — models systematically output ratings in a narrow band well above the human distribution.

### Rating distributions

| Source | Mean | Std | Range | % Accept (≥6) |
|--------|------|-----|-------|----------------|
| Human reviewers | 5.43 | 1.36 | [2, 8] | **35%** |
| DeepSeek-V3.1 | 7.14 | 0.86 | [3, 8] | 97% |
| GPT-OSS-20B | 6.31 | 0.94 | [3, 8] | 92% |
| Qwen3-235B | 7.28 | 0.83 | [5, 9] | 100% |
| Llama-3.3-70B | 8.07 | **0.43** | [6, 10] | 100% |
| Llama-3.1-8B | 7.89 | 0.58 | [3, 8] | 100% |

65% of papers in the dataset were rejected by human reviewers (mean rating 4.7). Every model assigns accept-range scores to 92–100% of papers.

**Every single disagreement is in the lenient direction**: models say "accept" when humans say "reject". No model erred in the strict direction.

### Why compression, not information access

A natural hypothesis is that models fail because they only see the abstract (not the full paper). However, this does not explain the pattern:

1. **Rationales are accurate about weaknesses.** Sample from DeepSeek-V3.1 (human: 4.0, model: 7): *"comparisons to broader baselines and deeper analysis of limitations would strengthen the claims"* — yet still gives 7. The model understands the paper is weak but doesn't convert that understanding into a low score.

2. **The failure is symmetric.** A model with full-paper access would also need to be calibrated to assign 4s and 5s — a reluctance that is independent of information. Models trained on internet text have a strong prior toward positive, constructive language.

3. **Scale compression is consistent regardless of content.** Llama-3.3-70B (std=0.43) essentially assigns 8 to everything regardless of what it reads. This is a decoder behavior, not an evidence gap.

The **information gap does matter at the margin** — full paper content gives access to experimental sections, ablation studies, and related work that can reveal fatal flaws — but the compression bias will persist independently and needs its own fix.

### Why Spearman is high but DecAgr is low

Spearman (0.75–0.84) measures rank correlation, not absolute accuracy. Models do partially preserve relative ordering — papers that humans rated 7 tend to get higher model scores than those humans rated 4. But all scores are shifted upward by ~1.5–2 points and compressed into a narrow range, so virtually every paper crosses the accept threshold even when the relative ranking is intact.

Concretely: a model that gives every paper exactly 7 would have perfect Spearman if the human ratings happen to be monotone, but 65% decision disagreement.

---

## Observations by Model Type

**Dense models scale reasonably:** DeepSeek-V3.1 > GPT-OSS-20B > Mistral-24B > Llama-3.1-8B — NMAE improves roughly with capability. The exception is Llama-3.3-70B (worse than Mistral-24B), likely due to its extreme score compression (std=0.43).

**MoE models do not uniformly outperform dense:** Qwen3-235B (22B active) is 4th; Llama4-Maverick (17B active) is 5th. Both rank below DeepSeek-V3.1 and GPT-OSS-20B despite far more total parameters.

**GPT-OSS-20B has the best decision agreement (42.5%)** despite not having the best NMAE. Its mean rating (6.31) is the closest to the human mean (5.43), suggesting better base-rate calibration than the other models.

**Correctness is the hardest dimension** for all models above 20B — every model above that threshold has correctness NMAE > 0.28, likely because verifying mathematical or algorithmic correctness requires reading proofs, not just abstracts.

---

## Implications

### For full-paper PDF experiment

Full paper access will help with:
- Identifying unsupported or cherry-picked empirical claims
- Evaluating ablations and comparison to baselines
- Assessing correctness of proofs and derivations

But **PDF access alone will not close the decision agreement gap** unless score calibration is also addressed.

### Recommended calibration interventions

1. **Calibration examples in system prompt.** Add 2–3 few-shot examples spanning the full rating range, including rejected papers (rating 3–4) with their rationales.

2. **Explicit base-rate instruction.** Tell the model: *"ICLR 2023 accepted approximately 30% of submissions. Apply the same stringency."*

3. **Threshold-aware prompting.** Ask for an explicit accept/reject decision first, then ask for a numerical score consistent with that decision.

4. **Score distribution anchoring.** Provide the rating scale with explicit calibration notes, e.g., *"A rating of 6 means borderline accept — most papers that feel reasonable should be 4–5."*

---

## Engineering Notes

- **Qwen3-235B bug:** model emitted `rationale` as an unquoted string, causing JSON parse failure and 118/120 null ratings. Fixed by adding a regex field-extraction fallback in `providers.py`; results reprocessed in-place.
- **DeepSeek-R1:** `<think>` block stripping added to parser; `max_tokens=4000` required. Run deferred pending cost approval.
- **Coverage:** All 7 evaluated models achieved ≥98% valid parse rate after fixes.
