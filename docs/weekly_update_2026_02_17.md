# Weekly Update — LLM Reviewer Simulation
**Week of 2026-02-17**

Since last week: scaled from single-model smoke test (Mistral-7B) to a 7-model comparative experiment, caught and fixed a critical evaluation bug, and ran a controlled ablation on full-paper PDF input vs. abstract-only.

---

## 1. Critical Bug Fix: Ground Truth Was Wrong

Discovered that the original pipeline was selecting **one random reviewer per paper** as ground truth, rather than aggregating consensus across all reviewers. Individual reviewer scores vary substantially (std ~1.5–2.0 within paper), so comparisons against a single reviewer were unreliable.

**Fix:** Export now fetches all reviews per paper and computes mean/median/std. The LLM is evaluated against reviewer consensus.

**Impact on metrics:** Decision agreement 20% → 100% on the small test set (the signal was noise); model leniency bias dropped from +1.00 to +0.28 once consensus was used as ground truth. All subsequent results use the corrected pipeline.

---

## 2. Metric Overhaul

Switched primary metric from plain MAE to **Normalized MAE (NMAE)** — each dimension's error is divided by its scale range, making the five score dimensions (rating 1–10, confidence 1–5, correctness 1–4, novelty 1–4, empirical novelty 1–4) directly comparable. Also added Spearman rank correlation and accept/reject decision agreement as secondary metrics.

---

## 3. 7-Model Comparative Experiment (n=120, abstract-only)

Ran seven serverless Together AI models on 120 ICLR 2023 papers (abstract + title, ≤3k chars). Models span 8B–671B parameters across dense and MoE architectures.

| Rank | Model | NMAE | Spearman | DecAgr |
|------|-------|------|----------|--------|
| 1 | DeepSeek-V3.1 | **0.154** | 0.757 | 38.3% |
| 2 | GPT-OSS-20B | 0.167 | 0.770 | **42.5%** |
| 3 | Mistral-Small-24B | 0.178 | 0.710 | 36.4% |
| 4 | Qwen3-235B | 0.195 | 0.839 | 36.7% |
| 5 | Llama4-Maverick | 0.207 | 0.828 | 37.3% |
| 6 | Llama-3.3-70B | 0.218 | 0.841 | 35.0% |
| 7 | Llama-3.1-8B | 0.331 | 0.833 | 36.1% |

DeepSeek-R1 (reasoning model) was deferred — requires ~4k tokens for its reasoning chain, raising API cost ~5× per paper; pending approval.

**Key finding — score compression:** Decision agreement is uniformly low (35–43%) across all models. The cause is a systematic upward calibration bias: human reviewers rejected 65% of papers (mean rating 5.43), but every model assigns accept-range scores (≥6) to 92–100% of papers. Llama-3.3-70B has rating std=0.43 and essentially assigns 8 to everything. Even when models identify specific weaknesses in their rationales, they do not convert that into a low score — suggesting a learned prior toward positive language rather than an information gap.

Spearman correlations are moderate-high (0.75–0.84), indicating models preserve **relative rankings** reasonably well even when absolute calibration is off.

---

## 4. Full-Paper PDF Ablation (GPT-OSS-20B, n=120)

Downloaded and extracted full-text PDFs for all 120 papers (~10k tokens each, references removed). Re-ran GPT-OSS-20B to isolate the effect of input content.

| | Abstract-only | Full PDF |
|--|--|--|
| NMAE | 0.167 | 0.164 |
| Decision agree | 42.5% | 43.1% |
| Rating mean | 6.31 | 6.54 |

Aggregate improvement is negligible. However, decomposing by outcome reveals an asymmetry:

- **On rejected papers** (human mean 3.66): abstract-only bias = +1.94; full PDF bias = **+0.94** — halved, because the model can now read thin experimental sections and call out missing baselines/ablations.
- **On accepted papers**: scores rose by a similar amount as the model rewards genuine strengths it can now read in detail.

The two effects cancel at the aggregate level. The fundamental problem is not information access but calibration — the model needs a prior that ~65% of submitted papers should be rejected. Next step is prompt-level calibration intervention (explicit base-rate instruction, few-shot rejected examples).

---

## 5. Engineering

- Full PDF extraction pipeline implemented (PyMuPDF, caching, failure logging)
- Automated comparison reports: markdown, CSV, HTML, charts
- Fixed two parser bugs: DeepSeek-R1 `<think>` block stripping; Qwen3-235B unquoted JSON string extraction
- All code and results on the `exploratory` branch

**Detailed experiment writeup:** [`docs/experiment_8model_baseline.md`](experiment_8model_baseline.md)
