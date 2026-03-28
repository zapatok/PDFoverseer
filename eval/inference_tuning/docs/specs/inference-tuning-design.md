# Inference Engine Tuning — Design Spec

**Date:** 2026-03-16
**Branch:** feature/inference-engine
**Goal:** Match or beat best historical result (≤2 errors across 7 real PDFs), then push lower.

---

## Problem

Motor `6ph-t1` undercounts in 5/7 real PDFs. Root cause: `ground_truth.json` was set from an old inference run (not from verified document counts), so the sweep optimized toward wrong targets. Additionally, the scoring metric treats real and synthetic fixtures equally and doesn't penalize doc count errors strongly enough.

**Known correct doc counts (from filenames):**

| PDF | Correct | Ground truth (current) | Error |
|-----|---------|----------------------|-------|
| ART | 674 | 668 | -6 |
| CH_9 | 9 | 9 | OK |
| CH_39 | 39 | 39 | OK |
| CH_51 | 51 | 50 | -1 |
| CH_74 | 74 | 73 | -1 |
| HLL | 363 | 294 | -69 |
| INS_31 | 31 | 30 | -1 |

**Best historical result (pre-t1):** CH_39 +1, INS_31 -1 (2 errors total)

---

## Approach: Metric → Fixtures → Iterative Sweep

### Phase 1: Fix Ground Truth and Scoring

**ground_truth.json:**
- Update `doc_count` for 5 PDFs to verified values (from filenames).
- `complete_count` and `inferred_count` for real fixtures have no verified ground truth, so they are removed as pass criteria for real fixtures. They remain in the file as reference but are not used in scoring.

**Fixture source field:** Each fixture JSON already has a `"source"` field (`"real"` or `"synthetic"`). The scoring function branches on this field to apply different weights.

**Scoring reform — `score_config` changes:**

For **real fixtures:**
- Pass criterion: `doc_count` exact match only (complete_count excluded from pass/fail)
- Doc count exact: **+5** per fixture
- Doc count delta: **-3 per doc** (sign-agnostic, undercount = overcount in penalty)
- `complete_exact` term: **not applied** to real fixtures
- `inf_delta` term: **not applied** to real fixtures

For **synthetic fixtures:** unchanged from current behavior (doc_exact +3, complete_exact +2, -doc_delta, -inf_delta).

Regressions penalty (-5): applies to both types.

**Note on HLL asymmetry:** HLL has a -69 gap which produces a 207-point swing in the score. This asymmetry is intentional — HLL is the most broken fixture and needs strong signal. A per-fixture delta cap is not applied; the sweep should heavily prioritize fixing HLL.

### Phase 2: Synthetic Fixture Expansion

**Current:** 8 synthetic fixtures.

**New failure-pattern fixtures (4):**

| Name | Description | Expected doc_count |
|------|-------------|-------------------|
| `many_1page_stream` | 50 pages 1/1, ~40% OCR failed | 50 |
| `period1_then_multipage` | 28 pages 1/1 + 3 pages 1/4,2/4,3/4 | 29 |
| `mixed_1_and_2page` | alternating 1p and 2p docs, OCR failures mid-stream | 15 |
| `high_failure_period2` | period=2, 60%+ failed, sparse reads | 10 |

**New positive anchor fixtures (3):**

| Name | Description | Expected doc_count |
|------|-------------|-------------------|
| `clean_period2` | period=2, all direct, all complete | 10 |
| `clean_period4` | period=4, perfect reads | 5 |
| `all_1page_clean` | 20 docs of 1 page each, no failures | 20 |

**New real-world pattern fixtures (4):**

| Name | Description | Expected doc_count |
|------|-------------|-------------------|
| `variable_doc_sizes` | mix of 1p, 2p, 3p docs | 10 |
| `single_long_doc` | one 40-page doc with some failures | 1 |
| `two_zones_diff_period` | first half period=2, second half period=4 | 15 |
| `sparse_reads` | ~80% OCR failed, only sparse successes | 8 |

All synthetic fixtures have ground truth set by construction (exact values known before running). Complete_count and inferred_count for new synthetics are defined during fixture creation.

**Total after expansion:** 19 synthetic + 7 real = **26 fixtures**

### Phase 3: Iterative Sweep Loop (autonomous)

Claude runs the full 3-pass sweep (500 LHS → fine grid → beam) and reads the JSON results each iteration.

**Per-iteration decision logic:**

```
Run sweep
    ↓
Count errors on real PDFs (doc_count exact match vs. filename)
    ↓
≤2 errors → save as candidate config; attempt further reduction
>2 errors → diagnose top-config failures:
    Which real fixtures fail? Direction of error?
    Is the failure pattern represented in synthetic fixtures?
        NO → add/fix fixture, re-sweep
        YES → modify eval/inference.py (new phase or param), re-sweep
```

**Phase 4 trigger:** If after 3 consecutive iterations the best config still has >2 errors on real PDFs AND no improvement over the prior iteration's best score, escalate to engine modifications.

### Phase 4: Engine Modifications (conditional)

Applied only to `eval/inference.py`. In priority order:

1. **Phase 5b** — correct direct OCR reads contradicting dominant period when confidence and agreement ratio exceed thresholds (targets INS_31)
2. **Contextual new_doc threshold** — lower new-doc threshold when neighbors suggest continuation
3. **Asymmetric D-S penalty** — heavier cost for undercount evidence vs. overcount

Nothing touches `core/analyzer.py` until a validated winning config exists.

---

## Success Criteria

- **Primary:** ≤2 errors on all 7 real PDFs (doc_count exact match)
- **Secondary:** push toward 0 errors if candidates exist
- **No regressions** on synthetic fixtures that currently pass
- **Max iterations:** 10 outer loops before escalating to human

## Constraints

- All engine changes in `eval/inference.py` only
- Sweep uses real fixtures as primary signal via weighted scoring
- ground_truth.json updated to verified values before first sweep
