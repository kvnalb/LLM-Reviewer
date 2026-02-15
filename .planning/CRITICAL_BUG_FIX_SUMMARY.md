# Critical Bug Fix: Cherry-Picking Reviewer Scores

**Status:** ✅ FIXED
**Date:** 2026-02-15
**Impact:** HIGH - Invalidated all previous evaluation metrics

## The Bug

### What Happened
- Export pipeline selected **ONE random reviewer** per paper
- Papers typically have 3-5 reviewers with different scores
- Pipeline cherry-picked one reviewer instead of aggregating

### Example: Paper `dYQnWPqCCAs`
All 4 reviewers rated:
- Reviewer 1: 3 (Reject)
- Reviewer 2: 5 (Marginally below)
- Reviewer 3: 5 (Marginally below)
- Reviewer 4: 8 (Accept, **low confidence: 2/5**)

**Consensus:** Rejected (avg = 5.25)
**Old pipeline grabbed:** Reviewer 4's score (8)
**Result:** LLM compared against outlier (8) not consensus (5.25)

---

## Test Results: Before vs After

### Before Fix (5-paper test)
| Metric | Value |
|--------|-------|
| Human avg (cherry-picked) | 5.80/10 |
| Model avg | 6.80/10 |
| Model bias | +1.00 |
| Decision agreement | 20% (1/5) |
| Conclusion | "Model is too lenient" ❌ |

**Problem:** Comparing against random outlier, not consensus

### After Fix (Same 5 papers)
| Metric | Value |
|--------|-------|
| Human avg (consensus) | 6.52/10 |
| Model avg | 6.80/10 |
| Model bias | +0.28 |
| Decision agreement | **100% (5/5)** |
| Conclusion | "Model is slightly lenient but well-calibrated" ✅ |

**Result:** Fair comparison against reviewer consensus

---

## What Changed

### 1. Export Pipeline (`export_review_subset.py`)

**Before:**
```sql
-- Fetches one row per review (one reviewer per row)
SELECT s.id, ..., r.rating, r.confidence, ...
FROM REVIEW r
JOIN SUBMISSION s ON r.paper_id = s.id
```
→ Returns 1 row per reviewer per paper
→ Random selection picks ONE reviewer

**After:**
```sql
-- Fetches all reviews for all papers
SELECT s.id, ..., r.reviewer_id, r.rating, ...
FROM REVIEW r
JOIN SUBMISSION s ON r.paper_id = s.id
ORDER BY s.id, r.reviewer_id
```
→ Groups by paper
→ Aggregates all reviewers

### 2. New Output Schema

**Before:**
```json
{
  "paper_id": "...",
  "review": {
    "rating": {"value": 8.0},
    "confidence": {"value": 2.0},
    ...
  }
}
```
Single reviewer per paper

**After:**
```json
{
  "paper_id": "...",
  "reviews": {
    "count": 4,
    "rating": {
      "values": [3, 5, 5, 8],
      "mean": 5.25,
      "median": 5.0,
      "std": 1.95,
      "count": 4
    },
    "all_reviews": [
      {"reviewer_id": "...", "rating": 3, ...},
      {"reviewer_id": "...", "rating": 5, ...},
      ...
    ]
  }
}
```
All reviewers preserved with aggregation

### 3. Metrics Pipeline (`metrics.py`)

Updated `_extract_human_score()` to:
1. Check for `"mean"` (aggregated schema)
2. Fall back to `"value"` (old schema)
3. Maintain backward compatibility

Now compares LLM against reviewer **consensus**, not outliers

---

## Key Insights

### Decision Agreement Restored
- **Before:** 20% agreement (1/5 papers)
  - Disagreements were artifacts of comparing against random outliers
- **After:** 100% agreement (5/5 papers)
  - Model perfectly aligned with reviewer consensus

### Model Bias Recalibrated
- **Before:** +1.00 (model appeared 1 point too lenient)
- **After:** +0.28 (model slightly lenient, realistic)
- **Cause:** Old pipeline's outlier cherry-picking exaggerated leniency

### Model Quality Revalidated
- NMAE: 0.219 → 0.113 (BETTER)
- Model is well-calibrated when compared fairly
- All 5 papers: decision agreement maintained

---

## Affected Components

| Component | Change | Impact |
|-----------|--------|--------|
| `export_review_subset.py` | Aggregate reviews | ✅ Now correct |
| `metrics.py` | Handle new schema | ✅ Backward compatible |
| `providers.py` | None needed | ✅ Auto-compatible |
| Evaluation metrics | Now use consensus | ✅ Honest comparison |

---

## Backward Compatibility

✅ **Maintained:**
- Old export files still work (checks for `"review"` key)
- Metrics gracefully handle both schemas
- No breaking changes to API

---

## Next Steps for n=120 Production Run

1. **Export 120 papers** with new aggregated schema
2. **Extract PDFs** (10k tokens, optimized mode)
3. **Generate reviews** with corrected baseline
4. **Expect:**
   - Better decision agreement (not 20%)
   - Honest model bias assessment
   - Fair evaluation across models

---

## Technical Details

**Commits:**
- `c819185`: Fix export aggregation
- `899d7ea`: Update metrics for new schema

**Files Modified:**
- `src/reviewer_sim/ingest/export_review_subset.py`
- `src/reviewer_sim/evaluate/metrics.py`

**Testing:**
- ✅ Export: 5 papers with aggregated reviews
- ✅ PDF extraction: 100% success (10k tokens)
- ✅ Review generation: All scores valid
- ✅ Evaluation: 100% decision agreement
- ✅ Metrics: NMAE 0.113 (improvement)
