# Experiment: 8-Model Abstract-Only Baseline + GPT-OSS-20B Full-PDF Comparison

**Date:** 2026-02-16 / 2026-02-17
**Branch:** `exploratory`
**Dataset:** n=120 ICLR 2023 papers, stratified by decision and rating
**Input (baseline):** Title + abstract (up to 3 000 chars)
**Input (PDF run):** Full paper text via PyMuPDF, references stripped, ~10k tokens
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

## PDF Experiment: GPT-OSS-20B Full-Paper vs Abstract-Only

After confirming the baseline, GPT-OSS-20B was re-run on the same 120 papers using full PDF text (~10k tokens, references removed) to test whether information access explains the decision agreement failure.

### Aggregate results

| | Abstract-only | Full PDF | Δ |
|--|--|--|--|
| NMAE | 0.167 | **0.164** | −0.003 |
| Spearman | 0.770 | **0.787** | +0.017 |
| Decision agree | 42.5% (51/120) | 43.1% (50/116) | negligible |
| Lenient errors | 66 | 65 | −1 |
| Rating mean | 6.31 | 6.54 | **+0.23 ↑** |
| Rating std | 0.94 | **1.07** | +0.13 |

Decision agreement and NMAE are essentially unchanged. Notably, the mean rating went *up*, not down.

### What actually changes

Full paper content has two opposing effects that cancel at the aggregate level:

**Downward pressure on rejected papers:** The model now reads the experimental sections and correctly identifies thin evidence. On a targeted sample of 5 rejected papers (human mean 3.66):
- Abstract-only mean: 5.60 (+1.94 above human)
- Full PDF mean: 4.60 (+0.94 above human) — bias halved
- Rationales become specific: *"Experimental evidence is limited to CIFAR-10, with no comprehensive comparison"*, *"The paper does not present quantitative results"*

**Upward pressure on accepted papers:** The model also reads the strengths in good papers and rewards them. 7-ratings rose from 19→27, 8-ratings from 18→27.

These effects cancel: 65 rejected papers are still rated ≥6.

### Conclusion

Information access is a real factor for the reject class but is offset by symmetric inflation of accepted papers. The dominant problem remains calibration — the model has no learned prior toward assigning 3s and 4s regardless of what it reads.

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

### Why compression is the primary cause (with a secondary information component)

The PDF experiment confirms that information access is a real but secondary factor:

- **Full paper content helps with the reject class** — bias on rejected papers drops from +1.94 to +0.94 once the model can read thin experimental sections and missing baselines.
- **But it raises scores on accepted papers by a similar amount** — the model rewards genuine strengths when it can read methods and results in detail.
- **Net effect on decision agreement: zero.** The two effects cancel.

The core issue is a **calibration prior**: models have a strong learned tendency toward positive, constructive responses. This is visible in the baseline rationales — DeepSeek-V3.1 correctly notes *"comparisons to broader baselines would strengthen the claims"* for a paper rated 4.0 by humans, then gives it 7. The hedging language is present; the score is not adjusted. Llama-3.3-70B (std=0.43) assigns 8 to essentially everything regardless of content — this is purely a decoder behavior, not an evidence gap.

The information gap matters for the reject class, but fixing it requires calibration intervention regardless of input length.

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

### On full-paper PDF input

Full paper input is confirmed to reduce upward bias on the reject class (bias halved from +1.94 to +0.94 on rejected papers), but does not improve aggregate decision agreement because scores on accepted papers rise by a similar margin. **PDF input alone does not close the decision agreement gap.** Calibration intervention is required in addition.

### Recommended calibration interventions

1. **Calibration examples in system prompt.** Add 2–3 few-shot examples spanning the full rating range, including rejected papers (rating 3–4) with their rationales.

2. **Explicit base-rate instruction.** Tell the model: *"ICLR 2023 accepted approximately 30% of submissions. Apply the same stringency."*

3. **Threshold-aware prompting.** Ask for an explicit accept/reject decision first, then ask for a numerical score consistent with that decision.

4. **Score distribution anchoring.** Provide the rating scale with explicit calibration notes, e.g., *"A rating of 6 means borderline accept — most papers that feel reasonable should be 4–5."*

---

## Engineering Notes

- **Qwen3-235B bug:** model emitted `rationale` as an unquoted string, causing JSON parse failure and 118/120 null ratings. Fixed by adding a regex field-extraction fallback in `providers.py`; results reprocessed in-place.
- **DeepSeek-R1:** `<think>` block stripping added to parser; `max_tokens=4000` required. Run deferred pending cost approval.
- **Coverage:** All 7 evaluated models achieved ≥98% valid parse rate after fixes (GPT-OSS-20B PDF run: 116/120).
- **pdf_extractor.py dispatch bug:** `extract_paper()` only matched `extraction_mode == "sections"`, causing `sections_optimized` (the default) to silently fall through to `fulltext`. Fixed; the PDF run used `fulltext` mode intentionally.
- **Section detection limitation:** `_detect_sections` only matches 5 hardcoded headers. Real ML papers use non-standard section names ("Proposed Method", "Our Approach"), so `sections_optimized` mode in practice captures only intro/conclusion for most papers. `fulltext` mode is recommended until section detection is improved.
