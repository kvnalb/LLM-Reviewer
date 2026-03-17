# Codebase Review: Issue Analysis & To-Do List

**Reviewer:** Staff Engineer Code Audit
**Date:** 2026-02-23
**Severity Levels:** 🔴 Critical | 🟠 High | 🟡 Medium | 🟢 Low

---

## 1. CRITICAL ISSUES

### 🔴 Issue #1: Environment Variable Validation Happens Too Late
**Location:** `src/reviewer_sim/utils/config.py` + `src/reviewer_sim/generate/providers.py`

**Problem:**
- `config.py` loads `TOGETHER_API_KEY` but doesn't validate it
- `TogetherGenerator.__init__()` (line 274-279) checks API key **after** instantiation
- If `MODEL_PROVIDER=together` but `TOGETHER_API_KEY` is missing, error only appears at runtime during first paper
- Wastes API credits/time before failing

**Current Code:**
```python
# config.py - no validation
system_prompt = os.environ.get("SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)

# providers.py - validation in generator
self.api_key = os.environ.get("TOGETHER_API_KEY", "")
if not self.api_key:
    raise ValueError("TOGETHER_API_KEY environment variable is required...")
```

**Impact:** Loses time/credits before catching config errors

**Fix:** Add validation to `load_model_config()` before returning config object

---

### 🔴 Issue #2: Makefile `run-together` Target Doesn't Override Variables Correctly
**Location:** `Makefile` line 80-88

**Problem:**
- Makefile uses `$(MODEL_PATH}` with `make` variable syntax
- But calling `make run-together MODEL_PATH=...` doesn't work reliably
- The `${MODEL_PATH:-${TOGETHER_MODEL_PATH}}` shell substitution in make context is fragile
- Result: User can't easily override model (stuck with default gpt-oss-20b)

**Current Code:**
```makefile
TOGETHER_MODEL_PATH ?= openai/gpt-oss-20b
run-together:
    ...
    MODEL_PATH=${MODEL_PATH:-${TOGETHER_MODEL_PATH}} \
```

**Impact:** Makes it impossible to run different models via make without editing Makefile

**Fix:** Use make `-e` flag or rewrite target to accept make variables properly

---

### 🔴 Issue #3: System Prompt Format String Not Escaped
**Location:** `src/reviewer_sim/utils/config.py` line 114 + `src/reviewer_sim/generate/providers.py` line 142, 302

**Problem:**
- System prompt has `{primary_area}` placeholder
- If `primary_area_llm` field contains malicious braces like `{__import__('os').system('...')}`... actually wait, this is just string formatting, not code injection. But it could still cause `.format()` failures if braces aren't balanced
- No validation of `primary_area_llm` before formatting

**Current Code:**
```python
primary_area = example.get("primary_area_llm", "general")
system_prompt = self.config.system_prompt.format(primary_area=primary_area)
```

**Impact:** Could cause `.format()` to fail if `primary_area_llm` contains special characters like `{`, `}`, or `:`

**Fix:** Validate `primary_area_llm` is alphanumeric or use `.format_map()` with escaping

---

## 2. HIGH SEVERITY ISSUES

### 🟠 Issue #4: Overly Broad Exception Handling in `run.py`
**Location:** `src/reviewer_sim/run.py` line 62-74

**Problem:**
- Catches all exceptions during review generation
- Just prints error and continues silently
- No distinction between transient errors (retry) vs permanent errors (skip)
- No way to know how many papers failed

**Current Code:**
```python
try:
    generated = generator.generate(ex)
    metrics = evaluate(ex, generated)
    row = {...}
    f.write(json.dumps(row) + "\n")
except Exception as exc:
    paper_id = ex.get("paper_id")
    print(f"Error processing paper_id={paper_id}: ...")
```

**Impact:** Silent failures, no summary of what went wrong, no way to retry failed papers

**Fix:**
- Track failed papers in a list
- Distinguish retry-able vs permanent errors
- Print summary at end with failure count

---

### 🟠 Issue #5: Imports Inside Functions
**Location:** `src/reviewer_sim/generate/providers.py` line 336, 361

**Problem:**
- `import time` appears inside the `generate()` method, in retry loops
- This is inefficient (import happens repeatedly) and confusing
- Top-level imports are clearer and better practice

**Current Code:**
```python
for attempt in range(max_retries):
    try:
        ...
    except:
        import time  # ← Inside retry loop
        time.sleep(2 ** attempt)
```

**Impact:** Minor performance cost, code clarity issue

**Fix:** Move `import time` to top of file

---

### 🟠 Issue #6: Temperature Not Validated for Valid Range
**Location:** `src/reviewer_sim/utils/config.py` line 109

**Problem:**
- Temperature loaded as float from env var with no bounds checking
- Can be set to negative or > 1, which most APIs reject
- No error until API call fails

**Current Code:**
```python
temperature = float(os.environ.get("TEMPERATURE", "0.2"))
```

**Impact:** Silent failures when temperature is invalid

**Fix:** Validate 0 <= temperature <= 2 (or API-specific bounds)

---

## 3. MEDIUM SEVERITY ISSUES

### 🟡 Issue #7: No Input Data Validation Before Generation
**Location:** `src/reviewer_sim/run.py` line 55-61

**Problem:**
- Loads input JSONL but doesn't validate required fields exist
- If `title` or `abstract` missing, only discovered during generation
- No upfront schema validation

**Current Code:**
```python
examples = load_jsonl(input_path)
print(f"Number of examples: {len(examples)}")
# Loop immediately tries to generate without checking fields
for ex in tqdm(examples, ...):
```

**Impact:** Wasted processing on invalid data before discovering schema issues

**Fix:** Add validation function that checks required fields before starting generation

---

### 🟡 Issue #8: JSON Parsing Has Multiple Fragile Fallbacks
**Location:** `src/reviewer_sim/generate/providers.py` line 173-240

**Problem:**
- Multiple regex patterns to extract JSON from response text
- Fallback strategies include finding outermost braces, fixing quotes, etc.
- Unclear which strategy should be used when
- Can succeed with wrong/incomplete JSON

**Current Code:**
```python
# Try full parse
parsed = json.loads(content)

# Fallback 1: Regex for "rating"
json_match = re.search(r'\{[^{}]*"rating"[^{}]*\}', content, re.DOTALL)

# Fallback 2+: Try to find outermost braces, fix quotes, etc.
```

**Impact:** May accept malformed reviews that happen to parse

**Fix:**
- Document fallback strategy clearly
- Add logging for which fallback was used
- Add validation that all required fields are present after parsing

---

### 🟡 Issue #9: Generator Protocol vs Implementation Mismatch
**Location:** `src/reviewer_sim/generate/providers.py` line 17-20

**Problem:**
- `BaseGenerator` protocol says it returns dict with SCORE_DIMENSIONS keys
- But implementations return dict with optional `'text'`, `'rationale'` keys
- Inconsistent return structure

**Current Code:**
```python
class BaseGenerator(Protocol):
    def generate(self, example: Dict) -> Dict:
        """Return a dict with the five SCORE_DIMENSIONS keys and optional 'rationale'."""
        ...
```

But actual returns include `'text'` key from all generators

**Impact:** Protocol documentation is wrong, makes it hard to understand contract

**Fix:** Update protocol to match actual implementation

---

### 🟡 Issue #10: No Logging Infrastructure
**Location:** Throughout codebase

**Problem:**
- All communication via `print()` statements
- No structured logging levels (DEBUG, INFO, WARN, ERROR)
- Difficult to capture logs, filter by severity, or redirect output
- No timestamps on log messages

**Current Code:**
```python
print(f"Provider: {config.provider}")
print(f"Error processing paper_id={paper_id}: {type(exc).__name__}: {exc}")
```

**Impact:** Difficult to debug, monitor, or parse logs programmatically

**Fix:** Use `logging` module instead of print()

---

## 4. LOW SEVERITY ISSUES

### 🟢 Issue #11: Makefile Has Hardcoded Default Paths
**Location:** `Makefile` line 3, 86, 87

**Problem:**
- Default `INPUT_JSONL ?= outputs/review_subset.jsonl`
- Default `OUTPUT_JSONL ?= outputs/results.jsonl`
- But during our testing, we're using enriched versions (`review_subset_enriched.jsonl`)
- Makefile doesn't know about enriched datasets by default

**Impact:** Users must remember to override paths each time

**Fix:** Add new targets for enriched versions or make enriched the default

---

### 🟢 Issue #12: Inconsistent Type Hints
**Location:** Various files

**Problem:**
- Some functions use full type hints: `def evaluate(example: Dict, ...) -> Dict:`
- Others use none: `def generate(self, example):`
- Inconsistent use of `Optional[X]` vs `X | None`

**Impact:** Reduces code clarity and IDE support

**Fix:** Add consistent type hints throughout (Python 3.9+ supports `X | None`)

---

### 🟢 Issue #13: No Validation of PDF Extraction Success
**Location:** `src/reviewer_sim/generate/providers.py` line 132-138

**Problem:**
- Code checks `extraction_metadata.get("success")` but no fallback if that field is missing
- Silent fallback to abstract if PDF extraction field is malformed

**Current Code:**
```python
if pdf_content and pdf_content.get("extraction_metadata", {}).get("success"):
    content = pdf_content.get("full_text", "")
else:
    content = example.get("abstract", "") or ""
```

**Impact:** Could silently use wrong data if extraction metadata is malformed

**Fix:** Add explicit validation and logging

---

### 🟢 Issue #14: System Prompt Too Long for Some Use Cases
**Location:** `src/reviewer_sim/utils/config.py` line 8-91

**Problem:**
- Default system prompt is ~1,600 tokens (with examples)
- For large batches, this multiplies token cost significantly
- No way to use a shorter baseline prompt without editing code

**Current Code:** Single fixed DEFAULT_SYSTEM_PROMPT

**Impact:** Wastes tokens on every API call

**Fix:** Add `SYSTEM_PROMPT_VARIANT` env var to choose between baseline/enhanced prompts

---

### 🟢 Issue #15: No Async Support for API Calls
**Location:** `src/reviewer_sim/generate/providers.py` line 286, 332

**Problem:**
- `TogetherGenerator` uses `httpx.Client` (sync) not `httpx.AsyncClient`
- Each API call blocks, can't parallelize
- Limits throughput for large batches

**Impact:** Slower processing for batch runs

**Fix:** Consider async implementation (non-trivial refactor)

---

## SUMMARY

| Severity | Count | Blocking? |
|----------|-------|-----------|
| 🔴 Critical | 3 | YES - Fix before running 120-paper test |
| 🟠 High | 3 | NO - Should fix |
| 🟡 Medium | 5 | NO - Nice to have |
| 🟢 Low | 4 | NO - Enhancements |
| **Total** | **15** | |

---

## RECOMMENDED FIX ORDER

1. **Fix #1 (Critical):** Add config validation for TOGETHER_API_KEY
2. **Fix #2 (Critical):** Fix Makefile variable passing
3. **Fix #3 (Critical):** Add primary_area_llm validation
4. **Fix #4 (High):** Improve exception handling in run.py
5. **Fix #5 (High):** Move imports to top
6. **Fix #6 (High):** Validate temperature range

After these 6, the 120-paper test should run safely and reliably.

---

## TESTING RECOMMENDATIONS

After fixes:
- [ ] Test with missing TOGETHER_API_KEY (should fail at config load, not runtime)
- [ ] Test with invalid temperature (should fail at config load)
- [ ] Test with missing input file fields (should validate before generation)
- [ ] Test Makefile variable overrides: `make run-together MODEL_PATH=...`
- [ ] Run small test (5-10 papers) to verify error handling works

---

