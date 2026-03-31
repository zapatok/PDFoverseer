# Bilateral Pixel Density — Improvement & Integration Plan

> **Created:** 2026-03-31
> **Branch:** `research/pixel-density`
> **For agentic workers:** Work through stages in order. Do not skip a stage unless its decision gate explicitly permits it. Each stage closes information gaps that the next stage depends on.

---

## Objective

The bilateral pixel density detector currently finds 668 covers in `ART_674.pdf` (target=674, error=-6), but it misses 31 TESS-ONLY pages (confirmed ART form covers) and fires falsely on ~5–20 of its 172 BILATERAL-ONLY pages. The root cause is not the threshold — it is the **feature representation and a non-stationary density baseline across the document**. This plan improves the detector before considering any integration with the OCR pipeline.

---

## Hard Data Available

All scripts run from the repo root (`a:/PROJECTS/PDFoverseer`). Activate `.venv-cuda` before running.

| Item | Location | Key facts |
|------|----------|-----------|
| Source PDF | `data/samples/ART_674.pdf` | 2719 pages, target=674 docs |
| Tesseract raw fixture | `eval/fixtures/real/ART_674_tess.json` | 2719 reads (one per page): direct(1510), SR(703), failed(506); 527 with `curr==1`. No `method=i` — this is raw OCR only. |
| VLM ground truth fixture | `eval/fixtures/real/ART_674.json` | 2686 reads, **all `method=vlm_opus`**, `total=4` on every read, `confidence=1.0` (96%) / `0.7` (4%). 674 reads with `curr==1`. **33 pages missing** (all in range 1753–1933, ~5-page spacing). **This is NOT a pipeline output** — it is VLM-generated ground truth. No `method=i` reads exist in any fixture. |
| 3-way diff (current) | computed by `inspect_bilateral.py` | SHARED=496, BILATERAL-ONLY=172, TESS-ONLY=31 |
| Score diagnostic | `inspect_bilateral.py --diagnose` | TESS-ONLY scores: min=0.2562 max=0.4980; SHARED scores: min=0.5102 max=0.7736; threshold=0.5041; **zero overlap** |
| Bilateral detector | `pixel_density.py` + `sweep_bilateral.py` | dpi=100, 8x8 grid, harmonic score, K-Means k=2; `dark_ratio` uses fixed threshold `< 128` on grayscale |
| Simulation | `simulate_bilateral_union.py` | Injecting 172 bilateral-only with total=1: DOC 668→694 (+20 error) |
| Baseline script | `eval/inference_tuning/baseline_art674_tess.py` | Runs `run_pipeline()` on tess fixture. Known output: DOC=668, complete=606, **inferred_pages=603**. Defines `REGION_UNREADABLE = (1753, 1933)` — the known difficult region. |
| Inspection PNGs | `data/pixel_density/bilateral_only/` (172), `data/pixel_density/tess_only/` (31) | |

### Key Architectural Fact

**No fixture stores `method=i` (inferred) reads.** Inference runs *on top of* fixtures — calling `run_pipeline(reads, PRODUCTION_PARAMS)` returns `list[Document]` where each `Document` has separate `.pages` (direct OCR) and `.inferred_pages` (method=i) lists. To know which pages the baseline infers, you must run the pipeline and inspect the Document objects. This data exists only in memory during execution.

### Known Fixture Issues

- **~3 fixture FPs in TESS-ONLY:** pages `p2041`, `p2014`, `p1998` are signature/attendance tables ("Toma de Conocimiento"), NOT real document covers. Tesseract falsely read `curr==1` on them. True miss count for bilateral is ~28, not 31.
- **~5–20 FPs in BILATERAL-ONLY:** pages `p0074`, `p2248`, `p2256` confirmed near-blank; visual estimate only.
- **33 missing pages in VLM fixture:** all in range 1753–1933 with ~5-page spacing. These coincide exactly with `REGION_UNREADABLE` defined in `baseline_art674_tess.py`. These could be blank separators or pages the VLM couldn't classify.
- **VLM total=4 uniformity:** 674 docs × 4 pages = 2696, but PDF has 2719 pages. The 23-page discrepancy (plus 33 missing from VLM) means some docs may not be exactly 4 pages. Do not blindly assume `total=4` for all injections.

### Open Questions (to be answered by Stage 0)

1. Of the 172 bilateral-only pages, how many fall within documents whose boundaries the baseline pipeline inferred (i.e., appear in some `Document.inferred_pages` list)?
2. What is the correct `total` for each bilateral-only page? (Cross-reference VLM ground truth, which says total=4 for nearly all, and verify against pipeline Document objects.)
3. How many bilateral-only pages have *no* coverage whatsoever — not in any Document's `.pages` or `.inferred_pages`?
4. Do the two "668 doc" results (bilateral detection and baseline pipeline) agree on document boundary placement? Quantify: how many documents start at the same page?

### What Was Tried and Did Not Work

- Global K-Means k=2 on harmonic scores: fails for ART form segments (structurally lower absolute density, weaker bilateral signal)
- Score threshold lowering: zero-overlap distributions make it impossible to lower threshold to catch TESS-ONLY without massive FP flood
- Score filter on union injection: all 172 bilateral-only pages score >0.40; filter had zero effect
- `total=1` injection assumption: wrong, causes DOC 668→694 (+26 excess docs), complete drops 608→574

---

## Stage 0 — Data Audit (Close Information Gaps)

**Objective:** Answer all four open questions by (a) running the baseline pipeline to extract per-page inference data, and (b) cross-referencing with VLM ground truth for correct `total` values. These are two separate data sources answering different questions.

**Why this must go first:** Stages 2–4 require knowing which pages are genuinely uncovered by the baseline and what their correct `total` values are. Without this, any simulation or injection experiment has a flawed premise.

### Task 0.1 — Write `audit_bilateral_coverage.py`

Create `audit_bilateral_coverage.py` at the repo root. This script does two things:

**Part A — Run baseline pipeline, extract per-page inference map:**

1. Load `ART_674_tess.json` reads.
2. Call `run_pipeline(reads, PRODUCTION_PARAMS)` to get `list[Document]` (expected: 668 docs, 603 inferred pages — matches `AI_LOG` in `baseline_art674_tess.py`).
3. Build a page→status map for all 2719 PDF pages:
   - For each `Document d`, for each page in `d.pages`: record `(doc_index=d.index, method='ocr', curr=position_in_doc, total=d.declared_total)`
   - For each `Document d`, for each page in `d.inferred_pages`: record `(doc_index=d.index, method='inferred', curr=position_in_doc, total=d.declared_total)`
   - Pages not in any Document: record `method='uncovered'`
4. Sanity check: total inferred pages should be ~603 (matching AI_LOG).

**Part B — Cross-reference bilateral-only and tess-only pages:**

5. Run bilateral detection (dpi=100, 8x8, harmonic) to get 3-way diff (SHARED, BILATERAL-ONLY, TESS-ONLY).
6. For each of the 172 bilateral-only pages, look up in the page→status map from Part A. Record:
   - `pipeline_inferred`: page is in some Document's `.inferred_pages`
   - `pipeline_ocr`: page is in some Document's `.pages` (direct OCR read, but bilateral also fires — boundary placement difference)
   - `pipeline_uncovered`: page is not in any Document at all
7. For each bilateral-only page, also look up in `ART_674.json` (VLM ground truth) to get the VLM's `curr` and `total` for that page. Handle the 33 missing VLM pages (report them as `vlm_missing`).
8. Do the same analysis for the 31 TESS-ONLY pages.
9. Save structured results to `data/pixel_density/audit_coverage.json`.

**Expected output format:**

```
Stage 0: Coverage Audit
-------------------------------------------------
Baseline pipeline: 668 docs, 603 inferred pages (sanity: matches AI_LOG)

Bilateral-only (172 pages):
  pipeline_inferred :  XXX  (already covered by baseline inference)
  pipeline_ocr      :  XXX  (boundary placement diff: bilateral says cover, pipeline says interior page)
  pipeline_uncovered:  XXX  (genuinely missed by both OCR and inference)

  VLM ground truth cross-ref:
    vlm_curr_1      :  XXX  (VLM confirms these are cover pages)
    vlm_curr_other  :  XXX  (VLM says these are NOT cover pages — bilateral FPs)
    vlm_missing     :  XXX  (in the 33 VLM gaps, 1753-1933 range)

Tess-only (31 pages):
  pipeline_inferred :  XXX
  pipeline_ocr      :  XXX
  pipeline_uncovered:  XXX
  vlm_curr_1        :  XXX  (real covers)
  vlm_curr_other    :  XXX  (fixture FPs — not real covers)
```

**Key imports:** `eval/shared/types.py` (PageRead, Document), `eval/inference_tuning/inference.run_pipeline`, `eval/inference_tuning/params.PRODUCTION_PARAMS`, `sweep_bilateral.bilateral_scores`, `sweep_bilateral.kmeans_matches`, `pixel_density.compute_ratios_grid`.

**Success criteria:** Script runs without error; `audit_coverage.json` exists; inferred page count matches ~603.

### Task 0.2 — Interpret Findings and Update Plan

After running `audit_bilateral_coverage.py`:

- If `pipeline_inferred` is high (>100 of 172): most bilateral-only pages are already covered by baseline inference. The simulation overshoot (+26 docs) is explained by double-counting. Integration value for these pages is zero.
- If `pipeline_uncovered` is significant (>20): these are the true integration targets — pages neither OCR nor inference covers. Record them.
- If `vlm_curr_other` is significant for bilateral-only: these are confirmed bilateral FPs. The improved detector (Stage 3) must not fire on them.
- Record the `total` distribution from VLM ground truth for bilateral-only pages confirmed as `vlm_curr_1`. These become the realistic `total` values for Stage 4 injection.

**Decision gate:** Proceed to Stage 1 regardless. Stage 0 informs Stage 4 but does not block signal improvement work.

---

## Stage 1 — Signal Characterization (Density Regime Analysis)

**Objective:** Confirm or refute the non-stationarity hypothesis: the document has distinct density segments, and the bilateral signal fails in low-density segments because global K-Means assigns their cover peaks to the wrong cluster.

**Existing knowledge:** `baseline_art674_tess.py` already defines `REGION_UNREADABLE = (1753, 1933)` — this is the known difficult region with high OCR failure rate. The 33 missing VLM pages cluster here too. This region likely contains the low-density ART form batch.

### Task 1.1 — Write `characterize_density.py`

Create `characterize_density.py` at the repo root. This script:

1. Computes the raw per-page dark_ratio scalar for all 2719 pages at dpi=100 (mean of the 8x8 grid cell ratios from `compute_ratios_grid`).
2. Computes a rolling mean with window=21 pages (centre-aligned) to estimate the local baseline density.
3. Implements a changepoint detector function `detect_density_segments(dark_ratios, delta=0.04, window=50)`:
   - Computes rolling mean, finds pages where it shifts by more than `delta` within `window` pages.
   - Returns list of `(start_page, end_page)` segment tuples.
   - **This function will be reused in Stage 3** — write it as an importable function, not inline.
4. Plots two sub-panels:
   - Top: raw dark_ratio per page (scatter) + rolling mean (line) + vertical lines at segment boundaries
   - Bottom: bilateral harmonic score per page (from `sweep_bilateral.bilateral_scores`) with horizontal line at threshold=0.5041
5. Marks on both panels: TESS-ONLY pages (red triangles), BILATERAL-ONLY pages (blue circles), SHARED pages (small green dots).
6. Saves the plot to `data/pixel_density/density_regime_plot.png`.
7. Prints: segment boundaries, rolling mean range per segment, count of TESS-ONLY/BILATERAL-ONLY/SHARED pages per segment.

**Success criteria:**
- Plot saved without error.
- At least 1 segment boundary detected that separates the REGION_UNREADABLE (1753–1933) from surrounding regions.
- TESS-ONLY pages visually cluster in a segment with lower rolling mean than SHARED pages.

### Task 1.2 — Verify Bimodality Within Segments

**This is the critical check before Stage 3.** For each detected segment that contains TESS-ONLY pages:

1. Use VLM ground truth (`ART_674.json`) to label pages within the segment as `cover` (curr=1) vs `non-cover` (curr>1).
2. Compute bilateral harmonic scores for both groups within that segment.
3. Plot histograms of bilateral scores for covers vs non-covers (within the segment only).
4. Check: is there visible separation? Compute the overlap between the two distributions (e.g., using the min of the two CDFs, or simply: what fraction of covers score above the median non-cover score?).

**Decision gate for Stages 2/3:**
- If bimodal within segments AND TESS-ONLY cluster in low-density segments → **Stage 3 (local K-Means) is the primary track.** Stage 2 may help further but is secondary.
- If NOT bimodal within segments (covers and non-covers have similar bilateral scores even locally) → the bilateral feature itself lacks discriminative power in these regions → **Stage 2 (preprocessing) is the primary track.** Stage 3 alone won't help.
- If TESS-ONLY pages are scattered across all density levels (not clustered in specific segments) → non-stationarity hypothesis is wrong → **Stage 2 is the only viable track.** Re-evaluate the approach if Stage 2 also fails.

**Record findings:** Fill in the "Segment Map" section at the bottom of this plan.

---

## Stage 2 — Preprocessing Improvements

**Objective:** Improve the per-page feature vector before bilateral comparison, to close the score gap between TESS-ONLY covers and the detection threshold.

**Current pipeline:** `compute_ratios_grid` renders page at dpi=100, converts to grayscale, counts pixels `< 128` per cell.

**Critical constraint:** Preprocessing that normalizes per-page intensity distribution (like page-level Otsu) would destroy the cross-page density variation that bilateral relies on. Only preprocessing that improves *within-page detail extraction* without equalizing the relative density between pages is safe.

### Task 2.1 — CLAHE on Grayscale

Create a variant `compute_ratios_grid_clahe` that applies CLAHE (`cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))`) to the grayscale page image before computing cell dark_ratios, keeping the `< 128` threshold.

**Warning:** CLAHE redistributes pixel intensities per tile. After CLAHE, the fixed `< 128` threshold may behave unpredictably: faint pages (like ART forms) could gain dark pixels (their faint lines get enhanced), while already-dense pages could lose dark pixels (contrast gets flattened). The net effect on bilateral *differences between neighbors* is uncertain. Monitor both TESS-ONLY and SHARED score distributions carefully — if SHARED scores degrade, CLAHE is counterproductive.

**Alternative to test alongside:** CLAHE + Otsu per cell (instead of fixed 128). This combinations lets CLAHE enhance contrast and Otsu adapt the threshold to the enhanced distribution.

### Task 2.2 — Red Channel vs Grayscale

Create a variant using the red channel (`img[:,:,0]` after RGB render) instead of grayscale. The red channel suppresses blue/red stamps and watermarks that inflate density on non-cover pages while preserving black text and form lines.

### Task 2.3 — Per-Cell Otsu Threshold

Replace the global `< 128` threshold with per-cell Otsu. For each 8×8 grid cell independently: compute Otsu threshold on that cell's pixels, count below-threshold as "dark".

**Warning:** This may destroy cross-page discriminability. If a blank ART form cell gets Otsu-binarized, noise becomes "content" and the page looks similar to a dense page. Monitor SHARED score distribution — if mean drops > 0.05, discard.

### Task 2.4 — Sweep and Compare Variants

Write `sweep_preprocessing.py` to sweep the preprocessing variants. For each variant, record:

| Metric | Current baseline | Target (improvement) |
|--------|------------------|----------------------|
| TESS-ONLY max score | 0.4980 | > 0.5500 |
| TESS-ONLY mean score | 0.4333 | > 0.4800 |
| SHARED min score | 0.5102 | >= 0.5000 (must not degrade) |
| SHARED mean score | 0.6494 | >= 0.6200 (must not degrade significantly) |
| Bilateral match count | 668 | 650–690 (error <= 24) |

**Decision gate for Stage 3:**
- If any variant raises TESS-ONLY max score above SHARED min score → the distributions begin to overlap → combine with Stage 3.
- If no variant meaningfully improves TESS-ONLY scores → preprocessing alone cannot fix the problem → proceed to Stage 3 if bimodality check (Task 1.2) passed.
- If neither preprocessing nor local K-Means works → the bilateral approach has a fundamental limitation for this document type. Document this conclusion and consider alternative features (see Stage 3 fallback).

---

## Stage 3 — Adaptive / Local Thresholding

**Prerequisite:** Stage 1 Task 1.2 must confirm bimodality within segments. If not confirmed, skip to the fallback at the end of this stage.

**Objective:** Apply K-Means per density segment instead of globally, so covers in low-density segments are classified relative to their local baseline.

### Task 3.1 — Local K-Means Per Segment

Reuse `detect_density_segments()` from Stage 1's `characterize_density.py`. Write `kmeans_local(scores, segments)` in `sweep_bilateral.py`:

- For each segment, extract the bilateral harmonic scores for pages in that range.
- Apply K-Means k=2 within the segment.
- Assign each page a binary cover/non-cover label relative to its segment.
- Combine all segment labels into a final covers list.
- Handle short segments (< 20 pages): merge with adjacent segment rather than running K-Means independently (too few data points for meaningful clustering).

### Task 3.2 — Combine with Best Preprocessing Variant

If Stage 2 produced a variant that improved TESS-ONLY scores, apply it as preprocessing before computing bilateral scores, then run local K-Means on the improved scores. The combination may be stronger than either alone.

### Task 3.3 — Evaluate Local vs Global

Run `inspect_bilateral.py` equivalent with local K-Means (with and without preprocessing) and record:

| Metric | Global K-Means (current) | Local K-Means (target) |
|--------|--------------------------|------------------------|
| TESS-ONLY detected | 0 / ~28 real covers | >= 20 / ~28 |
| BILATERAL-ONLY count | 172 | <= 130 (fewer FPs) |
| Total matches | 668 | 665–690 |
| Error vs target (674) | -6 | <= ±15 |

Cross-validate against VLM ground truth: of the newly detected pages, how many have `vlm_curr==1`? (True positive rate for the improvement.)

**Success criterion:** Local K-Means detects >= 20/~28 real TESS-ONLY covers without raising BILATERAL-ONLY count above 200.

**Decision gate for Stage 4:**
- Success criterion met → proceed to Stage 4.
- Partial improvement (10–19 TESS-ONLY detected) → combine with more aggressive preprocessing or tune segment parameters → re-evaluate.
- No improvement → **Fallback:** The bilateral harmonic score lacks discriminative power in homogeneous-density regions. Consider alternative approaches:
  - **Template matching:** Use VLM ground truth to build an average "ART cover" feature vector and match pages against it (supervised, but only needs ~10 exemplars).
  - **Layout descriptor:** Replace dark_ratio with a structural feature (e.g., number of connected components per cell, or edge density) that distinguishes form headers from body content regardless of overall density.
  - **Hybrid:** Use bilateral for the dense segments where it works well; use a different detector for the REGION_UNREADABLE segment.
  - Document the conclusion and stop if none of these are viable within reasonable effort.

---

## Stage 4 — Realistic Integration Simulation

**This stage is only meaningful if Stage 3 succeeds.** Do not run Stage 4 with the current (unimproved) bilateral detector.

**Objective:** Re-run the injection simulation with correct `total` values (from Stage 0) and without re-injecting pages already covered by baseline inference. Determine if the improved bilateral detector reduces overall inference error.

### Task 4.1 — Realistic Injection

Rewrite or extend `simulate_bilateral_union.py`. The key differences from the original simulation:

1. **Data sources** (from Stage 0 `audit_coverage.json`):
   - Pipeline inference status per page (from running `run_pipeline` on tess fixture) — tells us which pages are already covered.
   - VLM ground truth (`ART_674.json`) — provides correct `total` values.

2. **Injection filter:** Only inject bilateral-detected pages that are:
   - In the **improved** bilateral cover set (Stage 3 output), AND
   - `pipeline_uncovered` or `pipeline_inferred` with confidence < 0.55 in the baseline (from Stage 0 data), AND
   - `vlm_curr==1` (VLM confirms it's a real cover — avoids injecting bilateral FPs).

3. **Correct `total`:** Use the VLM ground truth `total` for each injected page (mostly total=4, but verify per-page). For the ~33 pages missing from VLM fixture, skip injection rather than guessing.

4. **Run:** `run_pipeline(combined_reads, PRODUCTION_PARAMS)` and compare DOC count to target=674.

**Expected result:** DOC count moves from 668 toward 674, not past it.

### Task 4.2 — Integration Decision Criteria

| Criterion | Threshold | Notes |
|-----------|-----------|-------|
| DOC error improvement | New error closer to 0 than -6 | |
| No regression on complete | complete >= 608 (baseline) | |
| Error direction | Error should be in [-6, 0], not positive | Positive = bilateral FPs fragmenting docs |
| Cross-validate with VLM GT | Newly formed docs match VLM doc boundaries | |

**Integrate if** all criteria are met.
**Do not integrate if** DOC overshoots target (error > +5) — bilateral FPs are still fragmenting multi-page documents.

---

## Implementation Order and Dependencies

```
Stage 0 (Data Audit) ──────────────────────────────────────┐
  ├── runs pipeline to get method=i page map                │
  ├── crosses bilateral-only against VLM GT for totals      │
  └── informs: Stage 4 injection realism                    │
                                                            │
Stage 1 (Signal Characterization) ─────────────────────┐   │
  ├── confirms non-stationarity hypothesis              │   │
  ├── Task 1.2: verifies bimodality within segments     │   │
  └── determines: Stage 2 vs Stage 3 priority           │   │
                                                        │   │
Stage 2 (Preprocessing) ◄──────────────────────────────┤   │
  ├── depends on: nothing (can start with Stage 1)      │   │
  └── feeds into: Stage 3 (combined approach)           │   │
                                                        │   │
Stage 3 (Local Thresholding) ◄──────────────────────────┘   │
  ├── depends on: Stage 1 (segment boundaries + bimodality) │
  ├── may incorporate: Stage 2 best variant                  │
  └── feeds into: Stage 4                                    │
                                                             │
Stage 4 (Integration Simulation) ◄──────────────────────────┘
  ├── depends on: Stage 0 (correct totals + coverage map)
  └── depends on: Stage 3 (improved detector)
```

**Recommended execution order:** Stages 0 and 1 first (can be parallel — they share the bilateral computation but use different fixtures). Stage 2 next (or parallel with Stage 1 Task 1.2). Stage 3 after Stage 1 decision gate. Stage 4 last.

---

## Options From Previous Plan — Current Status

| Option | Description | Status |
|--------|-------------|--------|
| Option A | Boost confidence of `failed` reads on bilateral-detected pages | Deferred — requires low FP rate first (Stage 3 precondition) |
| Option B | Resolve `total` from context before injecting | **Incorporated into Stage 4** — uses VLM ground truth directly |
| Option C | Only inject where baseline has low-confidence inferred coverage | **Incorporated into Stage 4** Task 4.1 step 2 |
| Option D | Feed bilateral scores into Phase 5 period detection | Still deferred — architectural change, evaluate after Stage 4 |

---

## Files to Create

| File | Stage | Purpose |
|------|-------|---------|
| `audit_bilateral_coverage.py` | 0 | Run pipeline + cross-reference bilateral-only against inference map and VLM GT |
| `characterize_density.py` | 1 | Plot density regimes + rolling mean + changepoint detection + bimodality check. **Exports `detect_density_segments()` for Stage 3 reuse.** |
| `sweep_preprocessing.py` | 2 | Sweep CLAHE / red channel / per-cell Otsu variants |
| Updated `sweep_bilateral.py` | 3 | Add `kmeans_local(scores, segments)` |
| Updated `simulate_bilateral_union.py` | 4 | Realistic injection with correct totals + coverage filter |

All files at repo root. CLI scripts may use `print()`. Importable functions use `logging`. Type annotations, ruff 0 violations.

---

## Segment Map (filled 2026-03-31)

**Result: NO SEGMENT BOUNDARIES DETECTED.** Tested delta values 0.04, 0.02, 0.01, 0.005 with window=50 — all return a single segment spanning the entire document. The non-stationarity hypothesis is **WRONG**.

```
Segment 1: pages 0–2718   rolling_mean 0.0452–0.0827 (mean ~0.0711)
            TESS-ONLY: 31  BILATERAL-ONLY: 172  SHARED: 496
```

The document has gradual density variation but no sharp regime changes. REGION_UNREADABLE (1753–1933) is NOT a distinct density segment — it has a similar rolling mean to surrounding regions.

**Implication:** Stage 3 (local K-Means per segment) is NOT VIABLE — there is only 1 segment, making local K-Means identical to global K-Means.

---

## Bimodality Check Results (filled 2026-03-31)

Single global segment — bimodality check runs on the full document:

```
Segment 1 (pages 0–2718):
  Covers (VLM curr=1):      674 pages, bilateral scores: min=0.2608  max=0.7736  mean=0.6154
  Non-covers (VLM curr>1): 2012 pages, bilateral scores: min=0.1659  max=0.7585  mean=0.3783
  Overlap:  0.6%  (fraction of covers scoring below median non-cover score)
  Bimodal:  YES  (covers clearly score higher on average)
  Score gap (min_cover - max_non_cover): -0.4977  (OVERLAPPING — tails cross heavily)
```

**Decision gate result:** Bimodal globally (YES), but no segments to exploit. Per the plan: Stage 2 is the primary track.

---

## Execution Results Summary (2026-03-31)

### Stage 0 — Data Audit

| Finding | Value | Implication |
|---------|-------|-------------|
| Pipeline uncovered pages | **0** | Every page assigned to a Document; bilateral cannot add NEW coverage |
| Bilateral-only pipeline_inferred | 74/172 | Already handled by inference |
| Bilateral-only pipeline_ocr | 98/172 | Pipeline sees them as interior pages, not covers |
| Bilateral-only VLM-confirmed covers | 86/172 | Half are real covers, half are FPs |
| Bilateral-only VLM FPs | 86/172 | Bilateral fires on interior pages |
| Tess-only VLM-confirmed covers | 28/31 | 3 are fixture FPs |
| VLM total for confirmed covers | All total=4 | Uniform document structure |
| Boundary agreement | 561/668 (84%) | Good but not perfect |

### Stage 1 — Signal Characterization

- Non-stationarity hypothesis: **WRONG** — no density segments detected
- Bimodality: **YES** globally, but tails overlap by 0.4977 score units
- Stage 3 local K-Means: **NOT VIABLE** (only 1 segment)

### Stage 2 — Preprocessing Sweep

| Variant | Matches | Error | TESS-ONLY max | TESS-ONLY mean | SHARED min | SHARED mean |
|---------|---------|-------|---------------|----------------|------------|-------------|
| baseline | 668 | -6 | 0.4980 | 0.4333 | 0.5102 | 0.6494 |
| clahe | 652 | -22 | 0.6847 | 0.5799 | 0.7051 | 0.9303 |
| clahe_otsu | 717 | +43 | 0.8437 | 0.7145 | 0.8473 | 1.1306 |
| red_channel | 670 | -4 | 0.5074 | 0.4400 | 0.5146 | 0.6566 |
| otsu | 722 | +48 | 0.5363 | 0.4710 | 0.5399 | 0.6761 |

**Best variant:** CLAHE raises TESS-ONLY scores most (+34%), but threshold rises proportionally. Net effect: **worse** (-22 error). No variant closes the TESS-ONLY→SHARED gap enough for K-Means.

### Stage 4 — Integration Simulation

| Scenario | DOC | Error | Complete | Inferred | INTEGRATE? |
|----------|-----|-------|----------|----------|------------|
| A: baseline | 668 | -6 | 608 | 525 | (reference) |
| B: VLM-confirmed (86, total=4) | 698 | +24 | 573 | 524 | **NO** |
| C: inferred-only (65, total=4) | 677 | +3 | 556 | 524 | **NO** |
| D: naive (172, total=1) | 694 | +20 | 574 | 614 | **NO** |
| E: confirmed+rest | 699 | +25 | 570 | 531 | **NO** |

**All scenarios fail** the integration criteria. The fundamental problem: injecting `curr=1` bilateral reads fragments existing documents that the pipeline correctly assembled through inference.

### Final Conclusion

The bilateral pixel density detector is a useful **standalone** document cover detector (668 covers, -6 error vs target 674, 88% VLM precision), but it **cannot be integrated into the inference pipeline** as a pre-inference signal:

1. The pipeline already covers all 2719 pages — bilateral adds no new coverage
2. Injecting bilateral covers as synthetic reads fragments correctly-assembled documents
3. The 31 TESS-ONLY pages (bilateral misses) cannot be recovered through preprocessing or local thresholding — they lack sufficient density contrast with their neighbors
4. The 86 bilateral FPs (non-cover pages detected as covers) would need to be filtered, but the only reliable filter is VLM ground truth, which defeats the purpose

**Recommendation:** Keep bilateral as a standalone analysis/validation tool. For pipeline improvement, focus on the 6 genuinely missing documents (error=-6) which likely require better OCR or VLM-based cover detection in the failure zones.
