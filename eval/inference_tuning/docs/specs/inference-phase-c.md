# Inference Engine Phase C — Reconstruction Confidence + Dynamic Guard Scaling
**Date:** 2026-03-18
**Status:** Approved
**Branch:** `feature/inference-engine`

## Overview

Two orthogonal structural improvements to `eval/inference.py` targeting the remaining production errors after Tuning v2:

| PDF | GT | Post-v2 | Delta | Target |
|-----|----|---------|-------|--------|
| ART | 674 | 669 | **-5** (regression) | 0 (±2 tolerance) |
| HLL | 363 | 368 | **+5** | ≤ +3 |
| CH_74 | 74 | 75 | +1 | 0 |
| CH_39 | 39 | 40 | +1 | 0 |
| CH_9, CH_51, INS_31 | — | exact | 0 | 0 (must not regress) |

**Root causes:**

- **ART (-5):** `ph5_guard_conf=0.90` only protects inferred boundaries with confidence ≥ 0.90. In ART (42% OCR failures), inferred boundaries are capped to 0.35 by `xval_cap`, boosted to max 0.58 by D-S. All fall below the guard. Undercount recovery merges them → undercount.
- **HLL (+5):** Period=2 detected at ~43% confidence (autocorrelation degrades under OCR noise). `ph5b_conf_min=0.69` requires ≥69% → Phase 5b never fires for HLL → misread `curr=1` pages not corrected → overcount.

**Hard constraint:** No regression below post-v2 baseline on any PDF.

## Architecture

```
OCR reads
    │
    ▼
_detect_period (MODIFIED — Approach A)
    │  adds _recon_confidence() as 4th signal
    │  new param: recon_weight
    │
    ▼
_infer (Phases 1–6, unchanged)
    │
    ▼
_build_documents (unchanged)
    │
    ▼
_undercount_recovery (MODIFIED — Approach B)
       adds dynamic guard scaling
       new param: ph5_guard_slope
```

Both changes are **sweep-ready**: default value `0.0` = disabled = identical to current behavior. The sweep explores positive values independently and in combination.

**Key principle:** `eval/inference.py` is the sandbox. `core/analyzer.py` is untouched until sweep results are validated.

## Approach A — Reconstruction Confidence

### Problem

Autocorrelation of the `curr` sequence degrades when OCR noise introduces misread values. For HLL, ~10% of pages have `total=1` instead of `total=2`, breaking the periodic signal. Global autocorrelation confidence: ~43%.

The reconstruction confidence signal is more robust: given a candidate period P, anchor at the first observed `curr=1` position and check what fraction of actual `curr=1` reads land within ±1 of predicted positions. This is insensitive to misread `total` values.

### Implementation

**New function in `eval/inference.py`:**

```python
def _recon_confidence(reads: list[PageRead], period: int) -> float:
    """
    Reconstruction confidence: fraction of observed curr=1 positions
    that align within ±1 of positions predicted by repeating 'period'.
    Robust to misread total values since it only uses curr==1 positions.
    """
    if period < 2:
        return 0.0
    starts = [i for i, r in enumerate(reads)
              if r.curr == 1 and r.method not in ("failed", "excluded")]
    if len(starts) < 2:
        return 0.0
    anchor = starts[0]
    predicted = set(range(anchor, len(reads), period))
    hits = sum(
        1 for s in starts
        if (s in predicted) or ((s - 1) in predicted) or ((s + 1) in predicted)
    )
    return hits / len(starts)
```

**Integration in `_detect_period`:**

After computing the three existing candidates (gap, mode_total, acorr), add reconstruction as a fourth signal. The period evaluated is the current best candidate at that point (from gap or mode_total), falling back to 2.

```python
# After existing candidate computation (gap_period, mode_total, acorr_period are
# already defined; 'best' is NOT yet defined at this insertion point):
recon_weight = params.get("recon_weight", 0.0) if params else 0.0
if recon_weight > 0.0:
    recon_period = gap_period or mode_total or 2
    rc = _recon_confidence(reads, recon_period)
    if rc > 0.3:
        candidates[recon_period] = candidates.get(recon_period, 0) + rc * recon_weight
```

Because `_detect_period` currently takes only `reads` as argument, it must accept an optional `params` argument to read `recon_weight`:

```python
def _detect_period(reads: list[PageRead], params: dict | None = None) -> dict:
```

And `run_pipeline` passes `params` to `_detect_period`:

```python
period_info = _detect_period(reads, params)
```

### Expected effect

For HLL: reconstruction confidence ~0.75–0.85 (period=2 is structurally strong). Combined period confidence rises above 0.69 → Phase 5b activates → corrects misread `curr=1` pages → overcount reduced.

For ART: period is genuinely mixed (docs range 1–N pages). Reconstruction confidence low. Period confidence stays low. No Phase 5b activation. No unintended correction.

### New param

```python
# PARAM_SPACE addition:
"recon_weight": [0.0, 0.15, 0.20, 0.25, 0.30],

# PRODUCTION_PARAMS addition:
"recon_weight": 0.0,   # disabled until sweep validates
```

`recon_weight=0.0` reproduces current behavior exactly.

## Approach B — Dynamic Guard Scaling

### Problem

`ph5_guard_conf=0.90` was designed for PDFs with mostly direct OCR reads. In ART (42% failure rate), all inferred boundaries are capped to ≤0.58 by xval_cap + D-S. None pass the guard. Undercount recovery merges them freely → undercount.

The guard threshold should loosen proportionally when many pages are inferred: with 42% OCR failures, the inferred boundaries represent the best available evidence and should be protected at a lower confidence threshold.

### Implementation

**In `_undercount_recovery`, before the merge loop:**

```python
inferred_ratio = sum(
    1 for r in reads if r.method == "inferred"
) / max(len(reads), 1)
ph5_guard_slope = params.get("ph5_guard_slope", 0.0)
effective_guard = ph5_guard_conf * max(1.0 - ph5_guard_slope * inferred_ratio, 0.0)
```

Replace `ph5_guard_conf` with `effective_guard` in the `has_confirmed_start` check:

```python
or (effective_guard > 0.0
    and reads_by_page[pp].method == "inferred"
    and reads_by_page[pp].confidence >= effective_guard)
```

### Effective guard values at key slope settings

With `ph5_guard_conf=0.90`:

| slope | ART (ratio≈0.42) | HLL (ratio≈0.056) |
|-------|------------------|-------------------|
| 0.0 | 0.90 (unchanged) | 0.90 (unchanged) |
| 0.5 | 0.71 | 0.875 |
| 1.0 | **0.52** | 0.850 |
| 1.5 | 0.33 | 0.824 |
| 2.0 | 0.00 (disabled) | 0.799 |

At `slope=1.0`, ART's effective guard is 0.52. Boundaries at confidence ≥0.52 are protected. With xval_cap=0.35 + D-S boost of 0.17+, some boundaries cross 0.52 → protected from recovery → count increases toward 674.

HLL effect is minimal (effective guard 0.85 vs 0.90) — no meaningful change.

### New param

```python
# PARAM_SPACE addition:
"ph5_guard_slope": [0.0, 0.5, 1.0, 1.5, 2.0],

# PRODUCTION_PARAMS addition:
"ph5_guard_slope": 0.0,   # disabled until sweep validates
```

## New Synthetic Fixtures

Two fixtures added to `eval/fixtures/synthetic/`:

### `art_like_high_failure`

**Scenario:** 15 documents of mixed sizes (1–3 pages, 30 pages total), ~33% OCR failure rate.

**Page layout (by document, in PDF order):**

Each group of 3 consecutive docs follows the pattern [1-page, 2-page, 3-page] × 5:

| Doc | Type | PDF pages | Direct reads | Failed |
|-----|------|-----------|--------------|--------|
| 0 | 1p | 0 | 0 | — |
| 1 | 2p | 1–2 | 1 | 2 |
| 2 | 3p | 3–5 | 3,4 | 5 |
| 3 | 1p | 6 | 6 | — |
| 4 | 2p | 7–8 | 7 | 8 |
| 5 | 3p | 9–11 | 9,10 | 11 |
| 6 | 1p | 12 | 12 | — |
| 7 | 2p | 13–14 | 13 | 14 |
| 8 | 3p | 15–17 | 15,16 | 17 |
| 9 | 1p | 18 | 18 | — |
| 10 | 2p | 19–20 | 19 | 20 |
| 11 | 3p | 21–23 | 21,22 | 23 |
| 12 | 1p | 24 | 24 | — |
| 13 | 2p | 25–26 | 25 | 26 |
| 14 | 3p | 27–29 | 27,28 | 29 |

**Failed pages (10 of 30 = 33%):** 2, 5, 8, 11, 14, 17, 20, 23, 26, 29

- All 1-page docs (pages 0, 6, 12, 18, 24) are always direct reads — `_local_total` cannot correctly infer `total=1` for isolated 1-page docs surrounded by multi-page docs, so they must not fail
- All failed pages are the last page of a multi-page doc; the preceding page is a direct read with `curr < total`, so Phase 1 forward propagation reliably assigns `curr=prev.curr+1, total=prev.total`

**Ground truth:** `doc_count=15, complete_count=15, inferred_count=10`

With correct inference: all 10 failed pages are assigned by forward propagation. All 15 docs end up complete.

**What it tests:** That Approach B (slope > 0) protects inferred boundaries in high-failure scenarios without undercounting. Ensures slope values >1.5 don't over-protect (create false splits).

### `hll_recon_period2`

**Scenario:** 20 × 2-page documents (40 pages total), 5% of pages with `total` misread as 1.

**Page layout:**
- Pages 0,2,4,...,38 (even): `curr=1, total=2, conf=0.90`
- Pages 1,3,5,...,39 (odd): `curr=2, total=2, conf=0.90`
- Override pages 4, 8 to: `curr=1, total=1, conf=0.88` (misread total; ~5% noise)

**Ground truth:** `doc_count=20, complete_count=20, inferred_count=2`

With Phase 5b correcting the 2 misread pages (`total=1→2, method="inferred"`), all 20 docs are complete. Agreeing ratio: 38/40=0.95 ≥ `ph5b_ratio_min=0.93` (PROD_PARAMS) — Phase 5b fires once period confidence clears `ph5b_conf_min=0.69`.

**What it tests:** That Approach A (`recon_weight > 0`) raises period confidence above 0.69, enabling Phase 5b to correct the 2 misread pages. Global autocorrelation with 5% noise should be ~0.60; reconstruction confidence should be ~0.90+.

## Param Space Changes (Summary)

Changes to `eval/params.py`:

```python
# New:
"recon_weight":    [0.0, 0.15, 0.20, 0.25, 0.30],
"ph5_guard_slope": [0.0, 0.5, 1.0, 1.5, 2.0],

# PRODUCTION_PARAMS additions:
"recon_weight":    0.0,
"ph5_guard_slope": 0.0,
```

All other params unchanged. The sweep now covers 2 additional dimensions.

## Implementation Sequence

1. Add `recon_weight` and `ph5_guard_slope` to `eval/params.py` (PARAM_SPACE + PRODUCTION_PARAMS)
2. Implement `_recon_confidence()` in `eval/inference.py`
3. Modify `_detect_period()` to accept optional `params` and integrate `recon_weight`
4. Update `run_pipeline()` to pass `params` to `_detect_period()`
5. Implement dynamic guard scaling in `_undercount_recovery()` using `ph5_guard_slope`
6. Add `art_like_high_failure` fixture to `eval/fixtures/synthetic/` and ground truth entry
7. Add `hll_recon_period2` fixture to `eval/fixtures/synthetic/` and ground truth entry
8. Run sweep → review report
9. Apply winning params + validate no regressions vs post-v2 baseline
10. Port validated changes to `core/analyzer.py`

## Success Criteria

| PDF | Post-v2 | Target |
|-----|---------|--------|
| ART | 669 (-5) | ≥ 672 (within ±2 of GT=674) |
| HLL | 368 (+5) | ≤ 366 (within ±3 of GT=363) |
| CH_74 | 75 (+1) | ≤ 75 (no regression) |
| CH_39 | 40 (+1) | ≤ 40 (no regression) |
| CH_9, CH_51, INS_31 | exact | exact (must not regress) |

## Deferred

**Local Period Windows:** Segmented period detection per rolling window (~50 pages). Would help HLL even further by using local period confidence (strong locally even if global is noisy). Deferred until Phase C (A+B) sweep results are reviewed.

**Bayesian Anchor Constraint:** Use high-confidence reads (>90%) as HMM anchors; Viterbi decoding for global sequence optimization. Most powerful approach for high-failure PDFs like ART. Deferred as Phase D after Phase C results.
