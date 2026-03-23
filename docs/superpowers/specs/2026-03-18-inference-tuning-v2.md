# Inference Engine Tuning v2 — Parallel Fixture Refresh + HLL-targeted Sweep
**Date:** 2026-03-18
**Status:** Approved
**Branch:** `feature/inference-engine`

## Overview

A two-track improvement cycle for the inference engine targeting the remaining production errors (+2 ART, +2 CH_74, +9 HLL — total +13 docs overcounted vs. ground truth). Track A refreshes eval fixtures from current OCR output (stale since last OCR tuning). Track B designs HLL-targeted synthetic fixtures and two minor logic adjustments. Both converge into a 3-pass parameter sweep.

**Hard constraint:** No regression below current production readings. ART tolerance ±2 (ground truth uncertainty).

## Root Cause of Previous Failure

The eval sweep (6ph-t1) found params that scored well on stale fixtures but worsened production. The fixtures were extracted once from an older OCR state; after OCR tuning, fixture data no longer matched current engine input. The sweep optimized for a problem that no longer existed.

## Architecture

```
Track A (runs independently)               Track B (designed here)
────────────────────────────               ───────────────────────
Run extract_fixtures.py                    4 new HLL-targeted synthetic fixtures
  → fixtures/real/*.json (fresh)           2 minor logic adjustments in inference.py
  → synced with current OCR               Updated param space (+2 new params)
             ↓                                          ↓
        ──────────────────────────────────────────────────
                  3-pass sweep (LHS → fine grid → beam search)
                  Fresh real fixtures + all synthetic fixtures
                  Reformed composite scoring (real fixtures weighted higher)
                  ↓
             Ranked results report
             Apply winning params + logic fixes to eval/inference.py
             Validate → port to core/analyzer.py
```

**Key principle:** `eval/inference.py` remains the sandbox. `core/analyzer.py` is untouched until sweep results are validated.

## Track A — Fixture Refresh

Run `eval/extract_fixtures.py` on all 7 real PDFs (PDFs are available locally). Produces:

```
eval/fixtures/real/
  ART.json, CH_9.json, CH_39.json, CH_51.json, CH_74.json, HLL.json, INS_31.json
```

After extraction, update `eval/ground_truth.json` with validated doc counts from the current production run (logsmaster, 2026-03-18):

| Fixture | doc_count | Notes |
|---------|-----------|-------|
| ART | 674 | ±2 tolerance (human count uncertainty) |
| CH_9 | 9 | exact |
| CH_39 | 39 | exact |
| CH_51 | 51 | exact |
| CH_74 | 74 | exact |
| HLL | 363 | exact |
| INS_31 | 31 | exact |

**`complete_count` and `inferred_count` for real fixtures are reference-only.** The scoring function (`sweep.py:score_config`) only evaluates `doc_count` for real fixtures; `complete_count` and `inferred_count` are ignored in scoring. These fields are computed by running `run_pipeline` with PRODUCTION_PARAMS on the fresh fixtures and recorded in `ground_truth.json` for human inspection, not for automated scoring. Synthetic fixtures continue to use all three fields in scoring.

## Track B — HLL-targeted Synthetic Fixtures

HLL profile: 538 pages, 363 docs expected, +9 overcount, period=2 detected at ~43% confidence, 5.6% OCR failure. The engine creates false-positive document boundaries where it should see continuity.

Four new fixtures added to `eval/fixtures/synthetic/`. All use `method: "direct"` for non-failed reads unless otherwise noted.

### `period2_low_conf`

**Scenario:** 20 × 2-page documents (40 pages total). Period=2 is correct but autocorrelation confidence is degraded by misread totals.

**Page layout:**
- Pages 0,2,4,...,38 (even): `curr=1, total=2, confidence=0.90`
- Pages 1,3,5,...,39 (odd): `curr=2, total=2, confidence=0.90`
- Override pages 6,14,22,30 to: `curr=1, total=1, confidence=0.85` (4 pages misread as 1-page docs; these break the period-2 autocorrelation signal)

**Ground truth:** `doc_count=20, complete_count=16, inferred_count=0`

**What it tests:** Whether the engine correctly identifies 20 docs when the dominant period (2) has degraded autocorrelation due to ~10% total misreads. Phase 5b at `ph5b_conf_min=0.40` should be able to correct the 4 misread pages.

---

### `period2_noisy_splits`

**Scenario:** 15 × 2-page documents (30 pages total). Several pages have `total` misread as 1, causing the engine to potentially split docs incorrectly.

**Page layout:**
- Pages 0,2,4,...,28 (even): `curr=1, total=2, confidence=0.90`
- Pages 1,3,5,...,29 (odd): `curr=2, total=2, confidence=0.90`
- Override pages 4,12,20: `curr=1, total=1, confidence=0.88` (3 mid-sequence misreads — these pages read as if they start a new 1-page doc)

**Ground truth:** `doc_count=15, complete_count=12, inferred_count=0`

**What it tests:** Whether the engine resists splitting on misread `curr=1, total=1` pages when the surrounding period signal is strong. Tests Phase 5b + Phase 5 guard interaction.

---

### `mixed_1_2_dense`

**Scenario:** 30 documents alternating 1-page and 2-page (45 pages total). All reads are clean (no OCR failures). Period is genuinely ambiguous — mix of 1 and 2.

**Page layout (by document):**
- Docs 0,2,4,...,28 (15 even-indexed docs): 1-page docs → single page per doc, `curr=1, total=1, confidence=0.92`
- Docs 1,3,5,...,29 (15 odd-indexed docs): 2-page docs → two pages per doc, `curr=1/2, total=2, confidence=0.91`
- PDF pages: 0 (doc0), 1-2 (doc1), 3 (doc2), 4-5 (doc3), 6 (doc4), 7-8 (doc5), ... (30 docs, 45 pages)

**Ground truth:** `doc_count=30, complete_count=30, inferred_count=0`

**What it tests:** Boundary detection when no dominant period exists. The sweep should preserve this case (no correction should be applied). Phase 5b should NOT activate.

---

### `period2_boundary_fp`

**Scenario:** 10 × 2-page documents (20 pages total). Three pages have their `curr` value misread as 1 instead of 2 — they look like document starts but are actually mid-document pages.

**Page layout:**
- Pages 0,2,4,...,18 (even): `curr=1, total=2, confidence=0.90`
- Pages 1,3,5,...,19 (odd): `curr=2, total=2, confidence=0.90`
- Override pages 5,11,17 to: `curr=1, total=2, confidence=0.87` (these should be `curr=2` but OCR misread as `curr=1` — false-positive new-doc signals)

**Ground truth:** `doc_count=10, complete_count=7, inferred_count=0`

**What it tests:** Whether the Phase 5 guard (`ph5_guard_conf`) prevents the engine from treating misread `curr=1` pages as document starts when surrounding evidence strongly indicates period=2.

---

**Existing synthetic fixtures (19 files on disk):** All unchanged. Note: `orphan_after_complete.json` exists on disk but is NOT in `ground_truth.json` and is therefore skipped by the sweep (`score_config` has `if name not in gt: continue`). It remains inactive.

## Track B — Minor Logic Adjustments

Two targeted changes to `eval/inference.py` only (not `core/analyzer.py`):

### Adjustment 1 — Phase 5b coverage for low-confidence periods

**Problem:** HLL's period is detected at ~43% confidence. The `ph5b_conf_min` param space `[0.0, 0.50, 0.60, 0.69, 0.70]` has no value ≤0.43 except 0.0 (disabled). Phase 5b cannot activate for HLL-like cases in any sweep config.

**Change:** Add `0.40` to `ph5b_conf_min` param space:
```python
"ph5b_conf_min": [0.0, 0.40, 0.50, 0.60, 0.69, 0.70]
```

No change to inference logic — only the param space expands to let the sweep explore this range.

### Adjustment 2 — Phase 5 guard for over-merge of high-confidence inferred boundaries

**Problem:** Phase 5 (D-S post-validation) over-merges inferred reads with `curr==1` and high confidence — documented in memory as `project_art_guard_gap.md`. Likely contributes to ART's +2 overcount.

**Change:** In the D-S merge loop of `eval/inference.py`, add:

```python
# Guard: skip Phase 5 merge for high-confidence inferred new-doc starts
if (r.curr == 1 and r.curr is not None
        and r.confidence >= params["ph5_guard_conf"] > 0.0):
    continue
```

This guard fires only when `ph5_guard_conf > 0.0`. When `ph5_guard_conf = 0.0` (baseline), the guard is disabled and behavior is identical to current production.

New param added to `eval/params.py`:
```python
"ph5_guard_conf": [0.0, 0.70, 0.80, 0.90]
```
Default in `PRODUCTION_PARAMS`: `"ph5_guard_conf": 0.0` (disabled — matches current behavior).

## Param Space Changes (Summary)

Changes to `eval/params.py` relative to current state:

```python
# Modified:
"ph5b_conf_min": [0.0, 0.40, 0.50, 0.60, 0.69, 0.70],  # added 0.40

# New:
"ph5_guard_conf": [0.0, 0.70, 0.80, 0.90],

# Locked (replace existing list with single value):
"min_conf_for_new_doc": [0.0],  # was [0.0, 0.45, 0.55, 0.65]
```

`min_conf_for_new_doc` is locked to `[0.0]` — memory `feedback_orphan_fixture_obsolete.md` documents that any value >0.0 causes real boundary misses with no compensating benefit. Removing it from the sweep eliminates ~4× dead search space.

`PRODUCTION_PARAMS` additions:
```python
"ph5_guard_conf": 0.0,   # new param, disabled by default
```

## Scoring

The existing `score_config` formula in `eval/sweep.py` is **unchanged**:

```python
# Per fixture (accumulated):
doc_exact += 5          # real fixture passes doc count
doc_exact += 3          # synthetic fixture passes doc count
complete_exact += 2     # synthetic fixture passes complete count

# Composite:
composite = (doc_exact + complete_exact
             - real_doc_delta * 3
             - syn_doc_delta
             - inf_delta
             - regressions * 5)
```

The formula already weights real fixtures (×5) higher than synthetic (×3). No code changes to scoring — the reformed formula proposed during design was already implemented in the current `sweep.py`. Weights may be tuned after reviewing initial sweep results if real PDFs are still not resolving.

## Success Criteria

| PDF | Current | Target |
|-----|---------|--------|
| ART | +2 | ≤ +2 (no regression; improvement to 0 desirable) |
| CH_9 | 0 | 0 (must not regress) |
| CH_39 | 0 | 0 (must not regress) |
| CH_51 | 0 | 0 (must not regress) |
| CH_74 | +2 | ≤ +2 (improvement to 0 desirable) |
| HLL | +9 | ≤ +3 (significant reduction required) |
| INS_31 | 0 | 0 (must not regress) |

## Implementation Sequence

1. Run `extract_fixtures.py` → fresh `fixtures/real/*.json`
2. Run `run_pipeline` with PRODUCTION_PARAMS on fresh fixtures → record `complete_count` and `inferred_count` per real fixture in `ground_truth.json` (reference only, not scored)
3. Update `doc_count` in `ground_truth.json` for all 7 real fixtures (use table above)
4. Add 4 new synthetic fixtures to `fixtures/synthetic/`; add their ground truth entries to `ground_truth.json`
5. In `eval/params.py`:
   - Add `0.40` to `ph5b_conf_min` list
   - Add `"ph5_guard_conf": [0.0, 0.70, 0.80, 0.90]`
   - Replace `min_conf_for_new_doc` list with `[0.0]`
   - Add `"ph5_guard_conf": 0.0` to `PRODUCTION_PARAMS`
6. Implement Phase 5 guard in `eval/inference.py` (see Adjustment 2 above)
7. Run sweep → review report
8. Apply winning params + validate no regressions against current production
9. Port validated changes to `core/analyzer.py`

## Deferred (Phase C)

Structural redesign of period detection — explore if period confidence calculation itself can be improved for ambiguous cases (HLL: ~43%, ART: mixed). Deferred until sweep results indicate parametric tuning is insufficient.
