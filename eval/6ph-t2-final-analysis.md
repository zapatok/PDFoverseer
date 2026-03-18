# Inference Engine v6ph-t2: Final Analysis

**Build:** 6-phase, tier-2 tuned parameters
**Status:** BROKEN — Multiple critical bugs prevent production use
**Last tested:** 2026-03-17 (7 real PDFs, all crashed or corrupted output)
**Tag:** `6ph-t2-almost-there`

---

## What Works

### Period Detection (✅ Reliable)
- **Method:** Autocorrelation on OCR reads with Dempster-Shafer confidence calibration
- **Performance:** 65-96% confidence across test set
- **Result:** Correct period identified for 6/7 PDFs (86-96% confidence)
- **Strength:** Robust to OCR errors via statistical aggregation
- **Use case:** Foundation for all downstream inference

### Tesseract + Super-Resolution Pipeline (✅ Mostly Works)
- **Architecture:** 6 parallel workers (Tesseract), SR fallback, EasyOCR GPU consumer
- **OCR Success:** 95%+ direct read rate on good quality pages
- **SR Coverage:** Handles 1000+ pages/PDF efficiently
- **GPU fallback:** Recovers 60-80% of failed Tesseract reads
- **Bottleneck:** OCR digit normalization incomplete (see Bug #3)

### Phase 1-4: Read Collection & Aggregation (✅ Works)
- Tesseract extraction, confidence scoring, SR application
- Dempster-Shafer evidence pooling across OCR methods
- No known crashes or logic errors in these phases

### Three-Tier Document Classification (✅ Works)
- **Direct:** High-confidence OCR reads (>threshold)
- **Inferred_HI:** Inferred from period + neighbor evidence (≥95% confidence)
- **Inferred_LO:** Inferred but lower confidence (50-95%)
- **Metric broadcasting:** Works to UI sidebar correctly
- **Strength:** Enables confidence-aware human review

---

## What Doesn't Work

### Phase 5 Document Merging (❌ Over-aggressive)

**Bug:** Over-merges boundary-adjacent inferred documents
- **Symptom:** ART_HLL shows 500+ spurious "FRONTERA" (boundary) issues
- **Root cause:** Phase 5 guards allow merging of consecutive inferred docs without confirmation
- **Impact:** Inflates issue count by 10x, drowns out real problems
- **Data:** ART_HLL 2719 pages → 681 docs detected, 78 documented as "sequence broken" merges
- **Example:** Page boundaries at 1/4, 2/4 inferred as same document instead of separate

**Fix needed:**
- Strengthen guard condition: require direct (OCR) confirmation for merge
- Or: disable merging of inferred-only sequences
- Or: require higher confidence threshold (>90%) for merges

### Phase 5b Period Corrections (❌ Crashes)

**Bug:** `_issue` function undefined at line 661
```python
_issue(r.pdf_page, "ph5b-corregida", ...)  # NameError
```

**Symptom:** INS_31docs.pdf aborts during analysis
- Triggered when: period_info exists AND confidence ≥ 70%
- Happens ONLY in Phase 5b (period correction phase)
- Affects 2/7 PDFs in test (CH_39, INS_31)

**Why not caught earlier:**
- Only executes when period detection succeeds AND has high confidence
- 5/7 PDFs with lower period confidence skip Phase 5b entirely
- INS_31: period=1/page, confidence=70% → triggers Phase 5b → crashes

**Fix needed:**
- Find `_issue` definition (possibly needs import)
- OR: Add `_issue` as parameter to `_infer_missing()` like `on_log`
- OR: Replace `_issue` call with appropriate logging/recording method

### Issue Tray Overpopulation (❌ Broken Filtering)

**Symptom:** Issues with 90-100% confidence appearing in tray
```
Error: Pag 2458: frontera de documento inferida 1/4 (confianza: 90%)
Error: Pag 2490: frontera de documento inferida 1/4 (confianza: 100%)
```

**Expected behavior:** High-confidence inferences should be filtered or auto-accepted

**Actual behavior:** All boundary inferences emitted regardless of confidence

**Questions unanswered:**
- Where is issue filtering supposed to happen? (server vs. UI)
- What's the confidence threshold for "too confident to show"?
- Is filtering logic broken or never implemented?
- Commit `b3eebb3` claims "smart tray filtering by impact" but not observed

**Impact:** Users see 500+ low-priority alerts instead of 10-20 actionable issues

**Investigation needed:**
- Trace issue emission path: `_emit_issue()` → server broadcast → UI tray
- Understand impact filtering logic (code mentions impact=FRONTERA, impact=etc)
- Determine if threshold logic exists but disabled

### Lambda Arity Mismatch (❌ Partially Fixed)

**Symptom:** 5/7 PDFs show [UI:ERR] in sidebar instead of metrics

**Code location:** server.py:568 in `_process_pdfs`
```python
_ud = _build_documents(
    reads,
    lambda m, l: None,
    lambda p, k, d, i=None: None  # OLD: 4 args
)
# Should be:
    lambda p, k, d, *a: None  # NEW: variadic
```

**Status:** Fix applied but effectiveness unverified
- Lambda changed to accept `*a` (variadic args)
- But 5 PDFs still show [UI:ERR]
- **Unknown:** Is lambda being called? Is new signature actually loaded?

**Root cause:** `_build_documents` calls `on_issue` with 6 positional args:
```python
on_issue(page, kind, detail, None, impact, doc_index)
```
But old lambda only accepted `p, k, d, i=None` (4 parameters).

**Fix verification needed:**
- Add logging to lambda to confirm it's called
- Check if on_issue callback actually invokes the lambda
- Verify parameter count at runtime

### on_log Parameter Missing (❌ Partially Fixed)

**Symptom:** Code references `on_log` but parameter not received
- Location: core/analyzer.py line 653-654 in `_infer_missing()`
- Caller chain: `analyze_pdf()` → `_infer_missing()` (missing on_log)

**Status:** Fix applied
- Added `on_log: callable = None` to signature
- Guarded calls with `if on_log:`
- Updated callers at lines 987 and 1221

**Effectiveness:** Unknown
- INS_31 still crashes with DIFFERENT error (`_issue` undefined)
- Suggests this fix may have worked, but unmasked third bug
- No verification that on_log parameter is actually being passed

---

## Architecture Issues

### 1. Callback Hell (Design Smell)

Multiple callback parameters passed through 3+ levels:
- `analyze_pdf()` receives `on_log`, `on_issue`, `on_metrics`
- Passes `on_log` to `_infer_missing()`
- Passes `on_issue` to `_build_documents()`
- No clear pattern → easy to miss a level

**Better design:** Dependency injection or context object
```python
class AnalysisContext:
    on_log: callable
    on_issue: callable
    on_metrics: callable
    # Pass as single param
```

### 2. Undefined Functions in Global Scope

Functions like `_issue()` referenced but not defined/imported at module level.
- Makes refactoring dangerous
- Static analysis won't catch undefined names
- Runtime-only detection

**Better practice:** All dependencies at top of file
```python
from .emitters import emit_issue as _issue
```

### 3. Phase 5b Conditional Execution (Hidden Complexity)

Phase 5b only runs when `period_info is not None AND confidence >= 0.69`.
- This condition is fragile
- Easy to add code that expects on_log but only some code paths provide it
- Conditional phases mean conditional bugs

**Better approach:** Explicit phase router
```python
if should_run_phase_5b(period_info):
    reads = phase_5b(reads, period_info, on_log)
```

### 4. Issue Filtering Architecture Undefined

Questions that code doesn't answer:
- Where should filtering happen? (analysis vs. broadcast vs. UI)
- What's the confidence threshold for filtering?
- Should high-confidence inferences auto-accept or hide?
- Is impact categorization working? (FRONTERA, etc.)

This needs explicit specification before Phase 6.

---

## Data Quality Issues

### OCR Digit Normalization (⚠️ Incomplete)

**Bug:** GPU consumer crashes on lowercase 'i' in page numbers

**Code:** core/analyzer.py line 90
```python
_OCR_DIGIT = str.maketrans("OoIlzZ|", "0011220")  # Missing 'i'
```

**With regex `re.IGNORECASE`:** Character class `[I]` matches both 'I' and 'i'
But translation only maps uppercase 'I' → '1', not lowercase 'i' → '1'

**Fix applied:** Add 'i' to translation
```python
_OCR_DIGIT = str.maketrans("OoIilzZ|", "00111220")
```

**Impact:** Rare but causes GPU thread crash on certain PDFs

### Confidence Score Semantics (? Unclear)

Issues appear with:
- 90% confidence: "Pag 2458: frontera ... (confianza: 90%)"
- 100% confidence: "Pag 2490: frontera ... (confianza: 100%)"

**Question:** If 100% confident it's an inferred boundary, why needs human review?
- Suggests confidence metric may not represent what we think
- Or filtering logic is inverted (show high-confidence, hide low-confidence?)
- Or "confidence" means something different in Phase 5b context

Needs clarification in code comments and issue specification.

---

## Test Results Summary

### Dataset: 7 Real PDFs

| File | Pages | Status | Issues |
|------|-------|--------|--------|
| ART_HLL_674docsapp | 2719 | ✅ Completes | ❌ 500+ spurious FRONTERA |
| CH_9docs | 17 | ✅ Completes | ✅ 0 issues |
| CH_39docs | 78 | ✅ Completes | ⚠️ Normal |
| CH_51docs | 102 | ✅ Completes | ⚠️ Normal |
| CH_74docs | 150 | ✅ Completes | ⚠️ Normal |
| HLL_363docs | 538 | ✅ Completes | ⚠️ Normal |
| INS_31docs | 31 | ❌ Aborted | ❌ Phase 5b crash (`_issue` undefined) |

**Success rate:** 6/7 (86%)
**Output quality:** 5/7 acceptable, 1/7 unusable (ART_HLL), 1/7 aborted
**Effective rate:** 5/7 (71%)

---

## Known Bugs Summary

| # | Name | Location | Severity | Status |
|---|------|----------|----------|--------|
| 1 | Lambda arity mismatch | server.py:568 | HIGH | Partially fixed, unverified |
| 2 | on_log undefined | analyzer.py:653 | HIGH | Fixed, unverified |
| 3 | _issue undefined | analyzer.py:661 | CRITICAL | Not fixed, blocks INS_31 |
| 4 | Issue tray overpopulation | Unknown | HIGH | Not investigated |
| 5 | OCR digit 'i' not normalized | analyzer.py:90 | MEDIUM | Fixed |
| 6 | Phase 5 over-merging | analyzer.py:~1800 | HIGH | Not fixed |

---

## Proposed Fixes (Priority Order)

### P0: Critical Blockers

1. **Fix `_issue` undefined** (enables INS_31 completion)
   - Search: `grep -rn "_issue" core/`
   - Import or define at module level
   - Or add as parameter to `_infer_missing()`
   - Time estimate: 15 min
   - Test with: `python eval/inference.py` on INS_31

2. **Verify lambda arity fix** (enables metrics for all PDFs)
   - Add logging to lambda: `print(f"on_issue called with {len(args)} args")`
   - Run 7 PDFs, check that lambda is invoked
   - If not invoked, trace why `_build_documents` callback isn't called
   - Time estimate: 30 min
   - Test with: Full 7-PDF run

### P1: High Priority

3. **Investigate issue filtering logic** (reduces false positives)
   - Understand: Where are high-confidence issues filtered?
   - Find: Confidence threshold values
   - Trace: Issue emission → broadcast → UI population
   - Fix: Disable filtering or adjust threshold
   - Time estimate: 1-2 hours
   - Test with: ART_HLL (review issue count before/after)

4. **Strengthen Phase 5 merge guards** (reduces spurious merges)
   - Current: Merge inferred docs if adjacent + same period
   - Proposed: Require direct OCR confirmation for merge
   - Or: Require both boundaries ≥95% confidence
   - Time estimate: 1 hour
   - Test with: ART_HLL (verify issue count drops to <50)

### P2: Medium Priority

5. **Refactor callback architecture** (reduces future bugs)
   - Replace multiple callback params with AnalysisContext
   - Ensures all phases have access to all callbacks
   - Time estimate: 3-4 hours
   - Risk: High (touches many files)

6. **Document Phase 5b conditional logic** (improves maintainability)
   - Explain when Phase 5b runs
   - Document required parameters for each phase
   - Add assertions: `assert on_log is not None if period_info else True`

---

## Recommendations

### Do Not Push to Production
Current state has 3 critical bugs + 1 architectural issue preventing reliable operation.

### Merge Path
1. Fix bugs P0 items (#1, #2) → Re-test 7 PDFs → Commit formally
2. Fix bugs P1 items (#3, #4) → Benchmark → Commit separately
3. Consider refactor P2 items after P0+P1 working

### Testing Strategy
- **Unit tests:** Add tests for `_infer_missing(on_log=None)` parameter handling
- **Integration tests:** INS_31 (triggers Phase 5b), ART_HLL (triggers Phase 5 merges)
- **Regression tests:** Ensure previous known-good results still work
- **Before each commit:** Verify with at least 3-PDF subset

### Documentation Gaps
- Phase 5/5b activation conditions
- Confidence score interpretation
- Issue filtering specification
- Callback parameter contract

---

## Lessons for Next Iteration

1. **Incomplete fixes are worse than no fixes**
   - Applied 3 fixes, none verified before testing
   - Wasted effort discovering bugs during production test instead of unit test
   - Better: Fix one bug, test thoroughly, commit, repeat

2. **Stack traces show symptoms, not root causes**
   - Lambda arity error masked by on_log missing error
   - on_log missing masked by _issue missing
   - Need exhaustive grep for all undefined symbols before declaring bug fixed

3. **Conditional code paths hide bugs**
   - Phase 5b only triggers on 2/7 PDFs
   - Bugs in conditional logic found late in testing cycle
   - Better: Create minimal test case for each phase before full pipeline test

4. **Hot-reload not reliable for critical fixes**
   - Changed code but uncertainty about what actually running
   - Better: Force process restart, verify with logging

---

## Conclusion

**Status:** 6ph-t2 is functionally incomplete. Core OCR pipeline works well (Phase 1-4), but downstream phases have critical bugs:
- Phase 5b crashes (blocks 1 PDF)
- Phase 5 over-merges (ruins 1 PDF output)
- Issue filtering broken (drowns users in false positives)

**Recommendation:** Address P0 bugs before next test cycle. Don't merge to master until all P0+P1 items resolved and 7 PDF test passes with <100 spurious issues total.

**Next steps:** See "Proposed Fixes" section for detailed plan.
