# Critical Finding: New System Prompt Regression

**Summary:** The enhanced system prompt with distribution targets **made upward bias worse**, not better.

## Baseline Comparison

### Original Prompt (Feb 16-17, ~116 papers)
Generated with simple 500-token prompt, no distribution targets, no examples.

```
Rating 3: 1 paper (0.9%)
Rating 4: 4 papers (3.4%)
Rating 5: 7 papers (6.0%)
Rating 6: 50 papers (43.1%) ← Mode
Rating 7: 27 papers (23.3%)
Rating 8: 27 papers (23.3%)
Acceptance rate (6+): ~90%
Mean: ~6.5
```

**Assessment:** Mostly centered on 6 (weak accept), some 7-8. Upward biased but reasonable middle ground.

---

### Enhanced Prompt with Distribution Targets (Feb 23, 10 papers tested)
Generated with 1,600-token prompt including:
- Explicit distribution targets (20/40/35/5)
- 4 concrete examples (ratings 3, 5, 6, 8)
- ICLR 2023 statistics
- Detailed rating scales

**Abstract-only (5 papers):**
```
Rating 3: 0 papers (0%)
Rating 5: 0 papers (0%)
Rating 6: 0 papers (0%)
Rating 7: 5 papers (100%)
Acceptance rate (6+): 100%
Mean: 7.0
```

**With PDF content (5 papers):**
```
Rating 3: 0 papers (0%)
Rating 5: 0 papers (0%)
Rating 6: 0 papers (0%)
Rating 7: 3 papers (60%)
Rating 8: 2 papers (40%)
Acceptance rate (6+): 100%
Mean: 7.4
```

**Combined (10 papers):**
```
Rating 7: 8 papers (80%)
Rating 8: 2 papers (20%)
Acceptance rate (6+): 100%
Mean: 7.2
```

---

## The Regression

| Metric | Original Prompt | Enhanced Prompt | Change |
|--------|-----------------|-----------------|--------|
| Mean Rating | 6.5 | 7.2 | **+0.7 (worse)** |
| Acceptance Rate | ~90% | 100% | **+10% (worse)** |
| % at Rating 6 | 43% | 0% | **-43%** |
| % at Rating 7+ | 47% | 100% | **+53%** |
| Rating 5 (Borderline) | 6% | 0% | **-6%** |

---

## Why This Happened

### Hypothesis 1: Distribution Anchoring Backfired
The explicit "target ~40% in 5 range" instruction appears to have trained the model to **avoid** rating 5 entirely, because:
- The LLM sees "5 = borderline reject" framing
- Feels pressure to be helpful/encouraging
- Interprets target distribution as suggested minimums, not as guidance for producing rejects
- Result: Skips 5 and jumps to 6-7

### Hypothesis 2: Concrete Examples Raised the Bar
The examples used ratings 3, 5, 6, 8. If the model uses these as anchors:
- Rating 3 example: Too harsh (scattered, unrigorous)
- Rating 5 example: Still somewhat harsh (unclear, compressed writing)
- Rating 6 example: Clear accept (solid, well-executed)
- Rating 8 example: Strong accept (excellent, innovative)

**Problem:** All 5 real papers being reviewed probably seem "better written" or "more coherent" than the compressed paper in the rating 5 example. Model concludes: "This is at least a 6, probably a 7."

### Hypothesis 3: Primary Area Integration
Adding `{primary_area}` placeholder and requiring "expertise in X" may have changed the LLM's persona:
- Original: "You are an ICLR peer reviewer" → neutral, balanced persona
- Enhanced: "You are an expert in NLP/ML/CV" → expert persona → expert tends to see merit ("I recognize this technique...") → higher ratings

---

## What Should We Do?

### Option A: Revert to Original Prompt
- Use the original 500-token prompt that was producing 43% rating 6
- Accept the upward bias as baseline, not try to "fix" it in the prompt
- Pursue other solutions (post-generation calibration, different LLMs, fine-tuning)

### Option B: Simpler Adjustment
Remove the problematic elements:
- Keep the detailed rating definitions (1-10 scale clearly spelled out)
- **Remove** explicit distribution targets (they cause aversion to rating 5)
- **Remove or reframe** concrete examples (they set wrong anchors)
- Keep it to ~800 tokens

### Option C: Inverse Pressure
Instead of "target these distributions," say:
```
"You are currently too generous. Be more critical.
- Rating 3 should be ~20% of papers (papers with fundamental issues)
- Rating 5 should be ~40% (papers where you genuinely cannot decide)
- Only ~30% of submissions are acceptable (ratings 6+)"
```

### Option D: Structural Change
Change the task structure:
```
Step 1: "REJECT or ACCEPT?" — decide binary first
Step 2: "If REJECT, assign 1-5. If ACCEPT, assign 6-10."
```

This forces the model to commit to rejection before assigning scores, preventing the "charitable accept" default.

---

## Recommendation

**Immediate:** Revert to original prompt and establish it as baseline.

**Next:** Test Option D (binary decision first) on the same 5 papers to see if structural change helps.

The fundamental issue is that **LLM reviewers are inherently generous**, and no prompt engineering can fix that without changing the task structure or persona significantly.
