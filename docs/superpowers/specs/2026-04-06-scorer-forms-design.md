# Scorer Forms — Page Classification for Form-Based PDFs

**Date:** 2026-04-06
**Branch:** `research/pixel-density`
**Status:** Design spec
**Constraint:** ART family results must not regress (6/6 exact, F1=0.996)

---

## Problem

The current pixel density scorers (`scorer_find_peaks`, `scorer_rescue_c`) detect document boundaries by finding pages that are visual outliers from their neighbors (bilateral scoring). This works for presentation-style PDFs (ART family) where covers have distinct visual signatures, but fails on form-based PDFs like HLL_363 where all pages share the same template.

### HLL_363 Characteristics

- **538 pages, 363 documents** (~1.48 pages/doc)
- **Document structure:** 188 single-page docs + 175 two-page docs (cover form + attendance sheet)
- **Visual uniformity:** All pages share the same official form template — same header, borders, logo
- **Cover ratio:** 67.5% of pages are covers (vs ~25% in ART)

### Current Performance on HLL_363

| Scorer | Detected | Target | Error |
|--------|----------|--------|-------|
| V2_RC (pct 75.2) | 135 | 363 | -228 |
| find_peaks (no rescue) | 84 | 363 | -279 |
| find_peaks (rescue 0.40) | 521 | 363 | +158 |

### Root Cause

Bilateral scoring fails because:
1. The score distribution is unimodal (no separation between covers and non-covers)
2. Page transitions within documents (cover -> attendance) have similar L2 distances to transitions between documents (attendance -> next cover)
3. The percentile threshold (75.2) assumes ~25% covers, but HLL has 67.5%

### Signal Found During Exploration

The **vertical ink distribution** shows a discriminating signal: attendance sheets have low dark_ratio in the bottom 35% of the page (empty table rows, ~0.03-0.04), while cover forms have moderate density throughout (~0.06-0.08). KMeans k=2 on this single feature gave 324 detections (error -39), a 6x improvement over bilateral.

---

## Design

### Architecture

A new scorer function `scorer_forms()` in `eval/pixel_density/sweep_rescue.py`, following the same interface as all existing scorers:

```python
def scorer_forms(pages: np.ndarray, ...) -> list[int]
```

- **Input:** Array of shape (N, H, W), uint8 grayscale pages (from `ensure_cache`)
- **Output:** List of 0-based page indices classified as document covers
- **Paradigm:** Page classification (not boundary detection)

The scorer is independent — it does not modify, import from, or share mutable state with any existing scorer.

### ART Safety Gate

Every sweep and test includes automatic verification:
1. Run `scorer_find_peaks` on all 6 ART PDFs — confirm 6/6 exact (MAE=0.0)
2. This verifies that the new code has not altered any shared module behavior
3. The gate is a test assertion, not a runtime check

### Scorer Selection

Manual selection by the user or calling script. No auto-detection of PDF type in this design.

---

## Implementation Phases

### Phase 1: Vertical Density Classifier

**New feature:** `feat_vertical_density` in `eval/pixel_density/features.py`

```python
def feat_vertical_density(
    img: np.ndarray,
    zones: tuple[float, float, float] = (0.30, 0.40, 0.30),
) -> np.ndarray:
    """Dark pixel fraction per vertical zone.

    Divides the page into vertical zones (top, mid, bottom) and computes
    dark_ratio for each zone independently.

    Args:
        img: Grayscale image (H, W), uint8.
        zones: Fraction of page height for (top, mid, bottom). Must sum to 1.0.

    Returns:
        1-D array of shape (3,), float64: [top_dark, mid_dark, bot_dark].
    """
```

Registered in `_FEATURE_REGISTRY` as `"vertical_density"`.

**Scorer logic:**

1. Extract `feat_vertical_density` for all N pages
2. Compute discriminant signal per page: `ratio = bot_dark / top_dark`
3. Separate with Otsu 1D threshold on the ratio array
4. Pages above threshold = covers (document starts)

**Why Otsu over KMeans k=2:** Otsu minimizes intra-class variance on a 1D histogram. It is deterministic (no random initialization), operates on the distribution shape directly, and is the standard approach for bimodal 1D separation. KMeans k=2 on 1D data is functionally equivalent but adds unnecessary complexity and non-determinism.

**Sweep parameters:**

| Parameter | Values | Purpose |
|-----------|--------|---------|
| bottom_cut | 0.25, 0.30, 0.35, 0.40 | Where "bottom zone" starts |
| signal | bot/top ratio, bot_dark absolute, bot/full ratio | Which discriminant to threshold |
| threshold_method | otsu, percentile(sweep 30-70), kmeans_k2 | Separation method |

**Sweep corpus:** HLL_363 + GENERAL_CORPUS + ART_CORPUS (same as sweep_rescue.py)

**Success criteria:** HLL_363 error ≤ ±30 (from -228 baseline). If met, refine. If not, proceed to Phase 2.

### Phase 2: Add Table Structure Detection

If Phase 1 is insufficient (error > ±30), add a second discriminating feature.

**New feature:** `feat_table_regularity` in `eval/pixel_density/features.py`

```python
def feat_table_regularity(img: np.ndarray, min_line_width_frac: float = 0.3) -> np.ndarray:
    """Detect regular horizontal line patterns (table rows).

    Uses horizontal projection profile (sum of dark pixels per row) to find
    evenly-spaced horizontal lines characteristic of attendance/sign-in sheets.

    Args:
        img: Grayscale image (H, W), uint8.
        min_line_width_frac: Minimum fraction of page width a dark row must
            span to count as a table line.

    Returns:
        1-D array of shape (2,): [n_regular_lines, spacing_std_normalized].
        n_regular_lines: Count of detected horizontal lines with regular spacing.
        spacing_std_normalized: Std of inter-line spacing / mean spacing (0 = perfectly regular).
    """
```

**Detection logic:**

1. Compute horizontal projection: `row_sums = (img < 128).sum(axis=1)`
2. Threshold: rows where `row_sums / width > min_line_width_frac` = candidate table lines
3. Find peaks in the projection (scipy.signal.find_peaks)
4. Compute spacing between consecutive peaks
5. Measure regularity: `std(spacings) / mean(spacings)` — low = regular table

**Combined scorer:**

```python
score = w1 * vertical_signal + w2 * (1.0 - regularity_signal)
```

Attendance sheets: low vertical_signal + high regularity (regular table) → low score.
Cover forms: high vertical_signal + low regularity (no table or irregular) → high score.

**Sweep:** w1/w2 weights × threshold methods over the combined corpus.

**Success criteria:** HLL_363 error ≤ ±15.

### Phase 3: Feature Combination Sweep (Fallback)

Only if Phases 1+2 fail to reach ±15. Exploratory sweep over combinations of:

- `feat_vertical_density` (Phase 1)
- `feat_table_regularity` (Phase 2)
- `feat_projection_stats` (already in features.py — h_std, h_skew capture vertical distribution)
- `feat_dark_ratio_grid` with asymmetric grid (e.g., 4 rows × 2 cols instead of 8×8)

Method: same classification paradigm, with robust-z normalization + Otsu or percentile on the combined score.

This phase is exploratory and does not have a pre-defined pipeline.

---

## Files

### New Files

| File | Purpose |
|------|---------|
| `eval/pixel_density/sweep_forms.py` | Sweep script for scorer_forms variants |

### Modified Files

| File | Change |
|------|--------|
| `eval/pixel_density/features.py` | Add `feat_vertical_density`, possibly `feat_table_regularity` (Phase 2) |
| `eval/pixel_density/sweep_rescue.py` | Add `scorer_forms()` function |
| `eval/pixel_density/params.py` | Add `BEST_FORMS_CONFIG` after sweep identifies best params |
| `eval/pixel_density/README.md` | Document new scorer and results |

### Test Files

| File | Tests |
|------|-------|
| `eval/tests/test_scorer_forms.py` | Feature shape/range tests, scorer smoke test, ART safety gate |

---

## Evaluation Protocol

### Per-Sweep Run

1. Run scorer_forms with current params on HLL_363 → report count error
2. Run scorer_forms on GENERAL_CORPUS → report MAE (context only, not optimization target)
3. Run scorer_find_peaks on ART_CORPUS → confirm 6/6 exact (**hard gate**)

### Final Validation

Once a configuration is selected:

1. Tag the commit (e.g., `PD_FORMS_V1`)
2. Document results in `docs/research/2026-04-06-scorer-forms-results.md`
3. If HLL error ≤ ±10, consider building page-level GT for F1 measurement

---

## Out of Scope

- Auto-detection of PDF type (form vs presentation) — manual scorer selection for now
- Integration into the main PDFoverseer pipeline (`core/`) — this is eval-only research
- Modification of any existing scorer behavior
- Page-level ground truth for HLL_363 (deferred unless results warrant it)

---

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Vertical density overlap zone (0.04-0.06) | Phase 1 under-detects by ~40 | Phase 2 adds table detection to resolve ambiguous pages |
| Otsu fails on non-bimodal distributions | Scorer gives bad results on some PDFs | Sweep includes percentile and kmeans alternatives |
| Table detection too slow | Sweep takes hours | Only activate Phase 2 if Phase 1 insufficient |
| New features accidentally imported by existing code | ART regression | Scorer is a standalone function; ART gate test catches any interference |
| HLL_363 is not representative of other form PDFs | Scorer overfits to one PDF | Cross-validate on GENERAL_CORPUS (some may also be form-based) |
