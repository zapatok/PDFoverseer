# Session Review: 2026-03-17 - Crash Investigation & Partial Fixes

## Executive Summary

Attempted to fix two identified runtime crashes from production test (7 real PDFs). Applied partial fixes and restarted servers, but discovered:
- **Fixes were incomplete** — missed third bug (`_issue` not defined)
- **Testing revealed new issue** — issues tray populating with high-confidence items that should be filtered
- **INS_31docs.pdf still crashes** — Phase 5b correction attempt fails
- **ART_HLL_674docsapp.pdf floods tray** — 500+ low-priority issues displayed

## Plan vs Reality

### What We Thought We'd Fixed

From the plan written before testing:

1. **Lambda arity error** (server.py:568) — Change `lambda p, k, d, i=None: None` to `lambda p, k, d, *a: None`
   - **Status:** ✅ Applied and verified in code
   - **Result:** Did NOT fix the 5 PDFs showing [UI:ERR]

2. **`on_log` not defined** (core/analyzer.py:653, 987, 1221) — Add `on_log` parameter and pass through call chain
   - **Status:** ✅ Applied
   - **Result:** Still crashes on INS_31 with DIFFERENT error

### What We Actually Found

**Three distinct bugs** (not two):

1. ❌ Lambda arity — Applied but ineffective
2. ❌ `on_log` undefined — Applied but insufficient
3. ❌ **`_issue` undefined** (NEW) — NOT IN PLAN, still present
   - Line 661 in `_infer_missing` calls `_issue(...)` but function not imported
   - Crashes INS_31 during Phase 5b activation
   - Causes "Aborted" status in sidebar

4. 🔴 **Issues tray filtering broken** (NEW, NOT ANTICIPATED)
   - Issues with 90-100% confidence appearing in tray
   - Should be filtered if confidence exceeds threshold
   - ART_HLL shows 500+ "FRONTERA" (boundary inference) entries
   - Example: "Pag 2458: frontera de documento inferida 1/4 (confianza: 90%)" — should not appear

## Root Causes of Failure

### 1. Incomplete Root Cause Analysis

**What we did:** Read error message, identified lambda/on_log issues from stack trace

**What we missed:**
- Did NOT search entire codebase for ALL uses of `_issue`
- Did NOT understand that Phase 5b activation is conditional (period_info + confidence threshold)
- Did NOT trace where issues are generated vs. filtered

**Lesson:** Stack traces show SYMPTOM not ROOT CAUSE. When one variable is undefined, search for ALL similar patterns in the file.

### 2. Assumptions About Hot-Reload

**What we assumed:**
- Hot-reload picks up all changes instantly
- Restarting frontend/backend guarantees code is current

**What actually happened:**
- Server showed WatchFiles messages → appeared to reload
- But some changes may not have been in the running server
- Never verified the actual code executing matched disk state

**Lesson:** For critical fixes, don't trust hot-reload. Either:
- Force a full process restart with explicit shutdown
- Verify the exact code running matches disk with breakpoints/logging

### 3. Incomplete Fix Verification

**What we did:**
- Applied changes to 4 files
- Ran analysis on 7 PDFs
- Checked logs for errors

**What we should have done:**
- Before testing: Verify ALL changes from plan were applied
- Grep search for each modified function/variable
- Check that each caller was updated
- Trace the complete data flow for each fix

**Example: on_log passing**
- Added parameter to `_infer_missing` ✓
- Updated analyze_pdf caller ✓
- Updated re_infer_documents caller ✓
- But did NOT check if ANY other functions call `_infer_missing` without passing `on_log`

### 4. No Boundary Specification for Issue Filtering

**Problem:** Issues appear in tray regardless of confidence. No logic to suppress low-priority inferences.

**What this suggests:**
- Issue emission logic doesn't have a confidence threshold
- Somewhere between "issue generated" and "issue displayed" should be a filter
- Currently either: (a) all issues emitted, or (b) filter removed, or (c) filter logic broken

**We didn't investigate this at all** — assumed plan fixes were sufficient

## What We Got Right

✅ **Systematic logging review** — Read error timestamps to determine if logs were pre/post fix

✅ **Identified restart procedure as critical** — Documented it for future use

✅ **Frontend+backend coordination** — Verified both servers running and responsive

✅ **Port availability verification** — Checked 8000/5173 before restart

## What We Got Wrong

❌ **Plan completeness** — Plan was incomplete (missed `_issue` bug entirely)

❌ **Verification discipline** — Applied fixes without checking if they actually worked

❌ **Testing before committing** — Never made formal commits of changes

❌ **Scope understanding** — Didn't understand issue emission vs filtering problem

❌ **Search exhaustiveness** — Grep search for undefined names was incomplete

❌ **Assumption validation** — Trusted hot-reload without verification

## Key Findings

### Bug #1: Lambda Arity (APPLIED, STATUS UNCLEAR)
```python
# server.py:568
_ud = _build_documents(
    reads,
    lambda m, l: None,
    lambda p, k, d, *a: None  # Changed from: lambda p, k, d, i=None: None
)
```
- _build_documents calls on_issue with 6 positional args
- Old lambda only accepted 4
- Fix applied BUT 5 PDFs still showing [UI:ERR] in logs
- **Action needed:** Verify this lambda is actually being called, verify parameter signature matches

### Bug #2: on_log Undefined (APPLIED, STATUS UNCLEAR)
```python
# core/analyzer.py:449
def _infer_missing(
    reads: list[_PageRead],
    period_info: dict | None = None,
    on_log: callable = None,  # ADDED
) -> list[_PageRead]:
    ...
    if on_log:  # GUARDED
        on_log(...)

# core/analyzer.py:987
reads_clean = _infer_missing(reads_clean, period_info, on_log)  # PASSED

# core/analyzer.py:1221
reads = _infer_missing(reads, period_info, on_log)  # PASSED
```
- Fix applied but INS_31 still crashes with `_issue` error
- **This suggests Bug #2 fix worked but Bug #3 exists**

### Bug #3: _issue Undefined (NOT FIXED, CRITICAL)
```python
# core/analyzer.py:661 (inside _infer_missing)
_issue(r.pdf_page, "ph5b-corregida", ...)  # NameError: name '_issue' is not defined
```
- `_issue` is referenced but never imported or defined locally
- Only triggers when Phase 5b activates (period confidence ≥ 70%)
- **Status:** Completely missed in plan
- **Fix:** Find where `_issue` is defined, import it at module level OR pass it as parameter

### Bug #4: Issues Tray Overpopulation (NOT INVESTIGATED)
- ART_HLL shows 500+ "FRONTERA" issues despite high confidence
- Issues with 90-100% confidence appearing when they shouldn't
- Examples:
  - "Pag 2458: frontera de documento inferida 1/4 (confianza: 90%)"
  - "Pag 2490: frontera de documento inferida 1/4 (confianza: 100%)"
- **Status:** Unknown root cause — could be:
  - Issue emission threshold not applied
  - Filter logic broken in UI
  - Incorrect confidence calculation
  - All inferred issues being emitted without filtering

## Lessons for Future Work

### Process Lessons

1. **Three-Phase Debugging Before Fixes**
   - Phase 1: Root cause investigation (complete, not partial)
   - Phase 2: Verify ALL affected locations in codebase
   - Phase 3: Only then write fixes

2. **Complete Issue Search**
   - When variable X is undefined: `grep -r "name 'X'" codebase`
   - Then: `grep -rn "def.*X\|import.*X" codebase`
   - Don't assume stack trace shows all occurrences

3. **Separation of Concerns**
   - One error per analysis round (don't fix 3 bugs in same push)
   - Test each fix independently if possible
   - Don't apply multiple fixes then test — can't isolate what worked

4. **Commit Before Testing**
   - Make changes, commit with clear message
   - Test known-good state
   - If test fails, at least you have git history to diff against
   - This session had no commits for the changes made

5. **Verification Protocol**
   - Before: `git status`, `git diff` (what changed?)
   - After applying code: Grep for exact function signatures
   - Before testing: Verify hot-reload or restart actually loaded new code
   - Log verification: Check timestamps and full stack traces

### Technical Lessons

1. **on_log as Optional Parameter**
   - Some callers of `_infer_missing` may pass on_log, others may not
   - Guarding with `if on_log:` is correct but incomplete
   - Need to verify ALL callers either pass it OR it's not needed

2. **Phase 5b Conditional Logic**
   - Phase 5b only runs when `period_info` exists AND confidence threshold met
   - This is why only some PDFs triggered the `_issue` bug
   - Period detection: 65-96% confidence in test run
   - **Insight:** More likely to trigger on higher-confidence PDFs

3. **Issue Filtering Architecture**
   - Somewhere between generation and display, issues should be filtered
   - Currently unclear if filter is:
     - Missing entirely
     - Disabled
     - Broken logic
   - Need to trace: `emit_issue()` → UI tray population

4. **Hot-Reload Limitations**
   - Tesseract + EasyOCR threads may cache module state
   - GPU consumer thread might not pick up reloaded code
   - Solution: Kill processes explicitly, verify process IDs match expectations

### Testing Insights

1. **7 PDF test is too coarse**
   - 6 PDFs complete, 1 crashes
   - Need smaller reproduction case for Phase 5b (INS_31 is 31 pages, good for this)
   - Need ART_HLL breakdown (separate out the tray filtering issue)

2. **Metrics Don't Guarantee Correctness**
   - 6 of 7 PDFs showing metrics in sidebar
   - But INS_31 "Aborted" + ART_HLL flooded with false positives
   - Metrics ≠ correctness; need issue count + quality inspection

3. **Confidence Score Validation**
   - Issues appearing with 100% confidence in tray = serious UX problem
   - If 100% confident, why not auto-accept in one of the passes?
   - Or if auto-accept shouldn't happen, why emit to tray at all?
   - Suggests confidence metric may be uninformative

## Action Items (Not in Current Session Scope)

- [ ] Search codebase for `_issue` definition and imports
- [ ] Verify lambda arity fix is actually in memory at runtime
- [ ] Investigate issue filtering logic (where are high-confidence issues filtered?)
- [ ] Create smaller test case for Phase 5b (use INS_31 as baseline)
- [ ] Document confidence score semantics (what does 90% mean? why show in tray if high?)
- [ ] Add unit tests for `_infer_missing` parameter passing
- [ ] Consider whether Phase 5b should even emit issues vs. just logging corrections

## Commits from This Session

No commits made. Changes applied but not formalized in git history.

**Files modified (uncommitted):**
- `server.py` — lambda arity fix (line 568)
- `core/analyzer.py` — on_log parameter chain (lines 449, 654, 987, 1221)

**Relevant recent commits in main branch:**
- `93defdc` — chore(settings): allow pytest and venv activation
- `1e177f7` — fix(server+ui): merge metrics loops, F5 recovery, session save
- `b3eebb3` — feat(ui): smart tray filtering by impact + post-cascade toast
- `cf90bc4` — feat(core): relocate issue emission after Phase 5/5b; add impact category

**Tags available:**
- `6ph-t2-almost-there` (current working baseline)
- `archive/core-fixes`
- `v3-baseline`
- `v4-sweep-tuned`

## Recommendation

This session revealed that:
1. Initial plan was incomplete (3 bugs, not 2)
2. Fixes applied were partial and unverified
3. New category of bug discovered (tray filtering)

**Do not push these changes to master without:**
1. Finding and fixing `_issue` undefined bug
2. Creating failing test case for Phase 5b
3. Investigating tray filtering (separate PR)
4. Running all 7 PDFs again with all fixes
5. Committing formally with clear messages

Current state is worse than before (more errors discovered) — rollback, plan systematically, implement with verification.
