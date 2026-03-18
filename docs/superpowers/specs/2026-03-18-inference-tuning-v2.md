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

`complete_count` and `inferred_count` for real fixtures are computed by running `run_pipeline` with PRODUCTION_PARAMS on the fresh fixtures — recorded in ground_truth once and used as baseline.

## Track B — HLL-targeted Synthetic Fixtures

HLL profile: 538 pages, 363 docs expected, +9 overcount, period=2 detected at ~43% confidence, 5.6% OCR failure. The engine creates false-positive document boundaries where it should see continuity — almost certainly a period detection confidence problem.

Four new fixtures added to `eval/fixtures/synthetic/`:

| Name | Scenario | What it tests |
|------|----------|---------------|
| `period2_low_conf` | 20 × 2-page docs; period autocorrelation yields ~45% confidence | Phase 5b threshold in the ambiguous-confidence zone |
| `period2_noisy_splits` | 15 × 2-page docs where some pages OCR as 1/1 (misread total) | Whether engine splits incorrectly on misread totals |
| `mixed_1_2_dense` | 30 docs alternating 1 and 2 pages, high OCR success rate | Boundary detection when period is genuinely ambiguous |
| `period2_boundary_fp` | 10 × 2-page docs with 3 injected false-positive boundaries | Phase 5 guard effectiveness against over-splitting |

Ground truth for each is defined at fixture creation time (exact doc counts known by construction).

Existing 19 synthetic fixtures are unchanged — they remain valid as they don't depend on OCR state.

## Track B — Minor Logic Adjustments

Two targeted changes to `eval/inference.py` (not `core/analyzer.py`):

### Adjustment 1 — Phase 5b coverage for low-confidence periods

**Problem:** HLL's period is detected at 43% confidence. Current `ph5b_conf_min` param space is `[0.0, 0.50, 0.60, 0.69, 0.70]` — no value ≤0.43 except 0.0 (disabled). Phase 5b cannot activate for HLL-like cases.

**Change:** Add `0.40` to `ph5b_conf_min` param space → `[0.0, 0.40, 0.50, 0.60, 0.69, 0.70]`.

This lets the sweep test whether activating Phase 5b at 43% period confidence helps correct HLL's false-positive boundaries without over-correcting cleaner PDFs.

### Adjustment 2 — Phase 5 guard for over-merge of high-confidence inferred boundaries

**Problem:** Memory `project_art_guard_gap.md` documents that Phase 5 (D-S post-validation) over-merges inferred reads with `curr==1` and high confidence. This likely contributes to ART's +2 overcount.

**Change:** Add configurable guard: if an inferred read has `curr==1` and `confidence >= ph5_guard_conf`, skip Phase 5 merge. New param: `ph5_guard_conf: [0.0, 0.70, 0.80, 0.90]` (0.0 = disabled = baseline behavior).

**Implementation:** ~5 lines in `eval/inference.py`'s D-S phase, guarded by the new param.

## Scoring Reform

Current composite score treats real and synthetic fixtures equally. Reformed formula weights real PDFs higher since they represent actual production behavior:

```python
composite_score = (
    doc_exact_real    * 5   # 7 real fixtures — primary target
  + doc_exact_syn     * 2   # 23 synthetic fixtures (19 existing + 4 new)
  + complete_exact    * 1
  - real_delta        * 3   # penalizes error in real PDFs
  - syn_delta         * 1
  - inf_delta         * 1
  - regressions       * 5   # regression = near-disqualifying
)
```

Weights may be adjusted after reviewing initial sweep results.

## Sweep Strategy

Unchanged 3-pass strategy from the original eval harness design:

- **Pass 1 — Latin Hypercube Sample:** 500 configs across full param space
- **Pass 2 — Fine grid:** Top-20 from Pass 1, adjacent-value perturbations (~2000 configs)
- **Pass 3 — Beam search:** Top-5 from Pass 2, single-param perturbations (~200 configs)

Baseline is PRODUCTION_PARAMS. Any config with `regression_count > 0` is excluded from top-10 report regardless of composite score.

## Updated Param Space

```python
PARAM_SPACE = {
    # ... existing params unchanged ...
    "ph5b_conf_min":   [0.0, 0.40, 0.50, 0.60, 0.69, 0.70],  # added 0.40
    "ph5b_ratio_min":  [0.90, 0.93, 0.95],
    "ph5_guard_conf":  [0.0, 0.70, 0.80, 0.90],               # new param
    "min_conf_for_new_doc": [0.0],                              # locked to 0.0 (binary tradeoff)
}
```

`min_conf_for_new_doc` is locked to 0.0 — memory `feedback_orphan_fixture_obsolete.md` documents that any value >0.0 causes real boundary misses with no compensating benefit.

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
2. Update `ground_truth.json` with current doc counts and computed complete/inferred counts
3. Add 4 new synthetic fixtures to `fixtures/synthetic/`; record ground truth
4. Add `ph5_guard_conf` param to `eval/params.py`; add `0.40` to `ph5b_conf_min`
5. Implement Phase 5b and Phase 5 guard adjustments in `eval/inference.py`
6. Update composite score formula in `eval/sweep.py`
7. Run sweep → review report
8. Apply winning params + validate no regressions
9. Port validated changes to `core/analyzer.py`

## Deferred (Phase C)

Structural redesign of period detection — explore if period confidence calculation itself can be improved for ambiguous cases (HLL: 43%, ART: mixed). Deferred until sweep results indicate parametric tuning is insufficient.
