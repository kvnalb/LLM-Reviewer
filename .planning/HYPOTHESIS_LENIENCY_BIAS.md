# Hypothesis: LLM Review Model Shows +1.0 Rating Leniency Bias

**Date:** 2026-02-14
**Status:** Observed in 5-paper test run
**Evidence:** Preliminary (n=5, too small for statistical significance)

## Summary

The LLM model (`openai/gpt-oss-20b` on Together AI) shows systematic leniency when scoring papers:

- **Human average rating:** 5.80/10
- **Model average rating:** 6.80/10
- **Mean bias:** +1.0 points (model rates higher)
- **Mean absolute error:** 2.2 points per paper
- **Decision agreement:** 20% (1/5 papers, accept/reject threshold at ≥6)

## Detailed Results

| Paper ID | Human | Model | Diff | Human Decision | Model Decision | Status |
|----------|-------|-------|------|---|---|---|
| dYQnWPqCCA | 8 | 5 | -3.0 | Accept | Reject | ✗ Disagreement |
| gwTP_sA-aj | 6 | 6 | +0.0 | Accept | Accept | ✓ Agreement |
| i0lHs3ji9x | 5 | 7 | +2.0 | Reject | Accept | ✗ Disagreement |
| xKYlWJaLFi | 5 | 8 | +3.0 | Reject | Accept | ✗ Disagreement |
| bPiHuNUNv_ | 5 | 8 | +3.0 | Reject | Accept | ✗ Disagreement |

## Pattern Observed

**Leniency on lower-rated papers:**
- 3 of 4 disagreements: model accepts what humans rejected (5 → 7-8)
- Model consistently bumps papers rated 5 up to 7-8

**One harsh outlier:**
- 1 paper human accepted (8) → model rejected (5)
- This is the only human-to-model disagreement where model is harsh

## Possible Explanations

### 1. Model Is Better (Optimistic)
- Full PDF content (methods, results sections) provides evidence humans missed
- Model's 7-8 ratings on low-rated papers might be *correct*
- Human reviewers were too harsh on implementation details
- Evidence: model can read full experimental setup, results tables, validation details

### 2. Model Is Miscalibrated (Likely)
- Model trained on different distribution than OpenReview reviewers
- Model not learning to match human harshness level
- Prompt doesn't adequately communicate scoring distribution expectations
- Evidence: systematic +1.0 bias suggests calibration issue, not noise

### 3. Extraction Bias (Possible)
- Review-optimized extraction prioritizes Methods > Results > Appendix
- De-prioritizes marketing language (Intro/Conclusion)
- Might reveal stronger technical content than abstract-only reviews
- Evidence: consistent upward bias on "Reject" papers, which need more scrutiny to accept

## Why Accept/Reject Binary Is Failing

The threshold (rating ≥ 6) is at the **boundary** of the leniency:
- With +1.0 bias, most papers rated 5 cross into acceptance
- Decision agreement collapsed to 20% not because of random error, but systematic shift
- This is a calibration problem, not an accuracy problem

## Diagnosis Required

To determine which explanation is correct, we need:

### Option 1: Manual Inspection (Immediate)
1. Pick one 5→8 disagreement
2. Read the full paper (PDF content)
3. Read both the human review and model's generated rationale
4. Judge: "Is the model's assessment reasonable?"
5. Repeat for 2-3 papers

### Option 2: Scale Experiment (n=120)
1. Run full pipeline with 120 papers
2. Calculate mean bias across full distribution
3. Check if +1.0 bias is consistent or was noise
4. Statistical significance testing

### Option 3: Model Comparison (n=5 each)
1. Test multiple models on same 5 papers:
   - DeepSeek-V3.1
   - Llama-3-70b
   - Mixtral-8x7B
2. Do they all show +1.0 bias? Or is it model-specific?
3. If all models biased → likely extraction or prompt issue
4. If model-specific → calibration issue for this model

## Recommended Next Action

**Run Option 2 (n=120)** because:
- Gives statistical significance
- Required for comparing models anyway
- Will show if bias persists at scale
- Only ~1.7x cost vs current test

**Then run Option 1 (manual inspection)** on:
- Biggest disagreements (5→8 and 8→5)
- Papers with high NMAE
- To understand why specific disagreements occurred

## Implementation Notes

- Test run: `exploratory` branch, commit e544a7c
- Extraction: sections_optimized (methods > results > appendix)
- Token budget: 10,000 tokens per paper
- Context window: 16k tokens
- Model: openai/gpt-oss-20b (serverless)
- Max tokens: 800 (for complete JSON)
- Sample size: 5 papers (NOT statistically significant)

## Metrics Affected

**By this bias:**
- ✗ Decision agreement: inflated by leniency (many false accepts)
- ✓ NMAE: unaffected (scale-aware, bias cancels out partially)
- ✗ Accept/reject accuracy: will be poor if bias persists at scale

**Not affected:**
- NMAE calculations (already scale-normalized)
- Spearman correlation (rank metric, less sensitive to constant bias)
- Individual score dimensions might show different biases

## Questions to Resolve

1. Is this real systematic bias or random noise from n=5?
2. Is the model's leniency justified by fuller paper content?
3. Are other models also lenient?
4. Can prompt engineering reduce the bias?
5. Should we accept this bias as "model just weights evidence differently" or treat it as miscalibration?
