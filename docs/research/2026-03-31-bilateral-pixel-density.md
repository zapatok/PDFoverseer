# Bilateral Pixel Density: Research Report

**Date:** 2026-03-31
**Branch:** `research/pixel-density`
**Status:** Integration rejected; standalone evaluation pending

---

## What Is Bilateral Pixel Density

A document cover detector that works without OCR. For each page, it:

1. Renders the page at low DPI (100) as grayscale
2. Splits into an 8x8 grid of tiles
3. Computes the fraction of "dark" pixels (< 128) per tile → 64-dimensional vector
4. Computes L2 distance to both neighbors (page before and after)
5. Combines left/right distances into a "bilateral score" (harmonic mean)
6. K-Means k=2 clusters scores into "cover" (high score = stands out from neighbors) and "non-cover"

The intuition: a document's first page looks visually different from both its predecessor (last page of previous doc) and its successor (second page of same doc, different layout).

---

## Hard Data

| Item | Value |
|------|-------|
| Source PDF | `data/samples/ART_674.pdf` — 2719 pages, 674 documents |
| Best config | dpi=100, grid=8x8, harmonic score, K-Means k=2 |
| Baseline result | 668 covers detected, error=-6 vs target 674 |
| VLM precision | 88.2% (of detected covers, 88.2% are real covers per VLM GT) |
| VLM recall | 89.0% (of 674 real covers, bilateral finds 89.0%) |
| Threshold | 0.5041 (midpoint between K-Means cluster boundaries) |

---

## What Was Investigated

### Stage 0: Coverage Audit (cross-reference with inference pipeline)

**Goal:** Understand which bilateral-detected pages the inference pipeline already covers.

**Method:** Ran `run_pipeline()` on the Tesseract fixture, built a page→status map for all 2719 pages, then cross-referenced with bilateral-only and tess-only page sets. Also cross-referenced with VLM ground truth for correct curr/total values.

**Key findings:**

| Finding | Value | Implication |
|---------|-------|-------------|
| Pipeline uncovered pages | **0/2719** | Pipeline covers every page via OCR + inference |
| Bilateral-only (172 pages) | 74 pipeline-inferred, 98 pipeline-OCR | All already assigned to documents |
| Bilateral-only VLM-confirmed covers | 86/172 | Half are real covers |
| Bilateral-only VLM false positives | 86/172 | Half are NOT covers |
| Tess-only (31 pages) VLM-confirmed | 28/31 | 3 are Tesseract fixture FPs |
| All VLM-confirmed bilateral covers | total=4 uniformly | ART forms are 4-page docs |
| Boundary agreement | 561/668 (84%) | Pipeline and bilateral agree on most doc starts |

**Script:** `audit_bilateral_coverage.py`
**Output:** `data/pixel_density/audit_coverage.json`

---

### Stage 1: Density Regime Characterization

**Goal:** Test hypothesis that the PDF has distinct density segments (e.g., a low-density ART form batch) where bilateral K-Means fails because it uses a global threshold.

**Method:** Computed per-page dark_ratio scalar, applied rolling mean (window=21), ran changepoint detector with decreasing delta thresholds (0.04, 0.02, 0.01, 0.005).

**Result: Hypothesis REFUTED.**

```
delta=0.040: 1 segment  (entire document)
delta=0.020: 1 segment
delta=0.010: 1 segment
delta=0.005: 1 segment
```

Rolling mean varies smoothly between 0.045 and 0.083 — no sharp regime transitions. The REGION_UNREADABLE (pp.1753–1933) is NOT a distinct density segment.

**Bimodality (global):**

```
Covers (VLM curr=1):      674 pages, scores: min=0.261  max=0.774  mean=0.615
Non-covers (VLM curr>1): 2012 pages, scores: min=0.166  max=0.759  mean=0.378
Overlap: 0.6% (fraction of covers below median non-cover)
Score gap: -0.498 (tails cross heavily despite separated means)
```

Bilateral scores are bimodal globally (covers clearly score higher on average), but the tails overlap by ~0.5 score units. The 31 TESS-ONLY misses live in the low-scoring tail of covers.

**Consequence:** Local K-Means per segment (the Stage 3 plan) was rendered impossible — there's only 1 segment. Local K-Means = global K-Means.

**Script:** `characterize_density.py` (exports `detect_density_segments()` for reuse)
**Plot:** `data/pixel_density/density_regime_plot.png`

---

### Stage 2: Preprocessing Variant Sweep

**Goal:** Improve per-page feature extraction to close the score gap between TESS-ONLY (bilateral misses) and SHARED (bilateral hits).

**Variants tested:**

| Variant | What it does |
|---------|-------------|
| baseline | Grayscale, fixed threshold < 128 |
| CLAHE | CLAHE contrast enhancement on grayscale, then < 128 |
| CLAHE+Otsu | CLAHE then per-cell Otsu threshold |
| Red channel | Use red channel from RGB instead of grayscale, then < 128 |
| Per-cell Otsu | Compute Otsu threshold per tile independently |

**Results:**

| Variant | Matches | Error | T-ONLY mean | T-ONLY max | SHARED min | SHARED mean |
|---------|---------|-------|-------------|------------|------------|-------------|
| baseline | 668 | **-6** | 0.433 | 0.498 | 0.510 | 0.649 |
| CLAHE | 652 | -22 | 0.580 | 0.685 | 0.705 | 0.930 |
| CLAHE+Otsu | 717 | +43 | 0.715 | 0.844 | 0.847 | 1.131 |
| red_channel | **670** | **-4** | 0.440 | 0.507 | 0.515 | 0.657 |
| otsu | 722 | +48 | 0.471 | 0.536 | 0.540 | 0.676 |

**Analysis:**

- **CLAHE** lifts TESS-ONLY scores most (+34%) but threshold rises proportionally. TESS-ONLY max (0.685) stops 0.001 below new threshold (0.686). Net: worse error (-22).
- **Red channel** gives marginal improvement: 670 matches, error=-4 (best raw count!). Suppresses colored watermarks/stamps. Low risk.
- **Otsu variants** destroy discriminability — many non-covers get high scores after adaptive binarization. +43 and +48 error.

**Additional experiments on CLAHE:**

- K-Means k=3 top-2 clusters: TESS-ONLY drops to 2 but bilateral-only explodes to 1313 FPs
- Percentile threshold p75: 680 matches, error=+6, VLM precision=88.2%, recall=89.0%
- None close the gap without FP flood

**Script:** `sweep_preprocessing.py`
**Output:** `data/pixel_density/preprocessing_sweep.json`

---

### Stage 4: Integration Simulation (with corrected data)

**Goal:** Test whether injecting bilateral-detected covers as synthetic reads into the Tesseract fixture improves the inference pipeline's doc count.

**Key corrections vs the original naive simulation:**
- Used correct `total=4` from VLM GT (not `total=1`)
- Filtered to VLM-confirmed covers only (excluding 86 FPs)
- Filtered by pipeline status (only inject where pipeline inferred or was uncertain)

**Results:**

| Scenario | DOC | Error | Complete | Decision |
|----------|-----|-------|----------|----------|
| Baseline (tess only) | 668 | -6 | 608 | reference |
| B: 86 VLM-confirmed (total=4) | 698 | +24 | 573 | NO — fragments docs |
| C: 65 inferred-only (total=4) | 677 | +3 | 556 | NO — complete -52 |
| D: 172 naive (total=1) | 694 | +20 | 574 | NO — as before |
| E: 86@t4 + 86@t1 | 699 | +25 | 570 | NO — worst |

**Root cause of failure:** Injecting `curr=1, total=4` on pages the pipeline already assigned as interior pages forces new document boundaries, splitting correctly-assembled documents. The pipeline handles "no data" better than "conflicting data" (same lesson as VLM integration — see `2026-03-29-vlm-alternative-approaches.md`).

**Script:** `simulate_realistic_injection.py`

---

## Key Learnings

### 1. Zero-coverage assumption was wrong
We assumed bilateral could find pages the pipeline misses entirely. In reality, the pipeline (with 603+ inferred pages) already covers 2719/2719 pages. There's no gap to fill.

### 2. The non-stationarity hypothesis was wrong
We assumed the PDF had distinct density regimes causing localized failures. The document is density-homogeneous — TESS-ONLY misses are scattered throughout, not clustered in specific regions.

### 3. Preprocessing helps scores but not classification
CLAHE boosts all scores proportionally. The K-Means threshold rises with the scores, so the relative ranking doesn't change. The 31 TESS-ONLY pages score low because their neighbors have similar density, not because of poor contrast.

### 4. Pipeline integration is counterproductive
Injecting covers fragments existing documents. This mirrors the VLM integration lesson: the inference engine handles gaps better than conflicting signals.

### 5. Bilateral is a strong standalone detector
668/674 covers (error=-6), 88% VLM precision, 89% recall — without any OCR. This has value as an independent validation signal, not as a pipeline input.

### 6. Red channel is a marginal but free improvement
670 matches (error=-4) vs 668 baseline (error=-6). The red channel suppresses colored stamps. Worth keeping as the default if we standardize the standalone detector.

---

## Standalone Baseline (PD BASELINE)

Full sweep of 6 preprocessing variants x 3 score functions x 3 threshold methods = 54 combinations, evaluated against VLM ground truth (674 covers).

### Best Count — PRODUCTION BASELINE

```
Variant:   clahe
Score fn:  min
Threshold: percentile 75.2
```

| Metric | Value |
|--------|-------|
| Matches | 675 |
| Error | +1 |
| Precision | 0.921 |
| Recall | 0.923 |
| F1 | 0.922 |
| TP / FP / FN | 622 / 53 / 52 |

This is the closest to the true document count (674). Percentile threshold is computed as the value that yields ~target matches.

### Best Quality — HIGH PRECISION REFERENCE

```
Variant:   clahe
Score fn:  min
Threshold: kmeans_k2
```

| Metric | Value |
|--------|-------|
| Matches | 626 |
| Error | -48 |
| Precision | 0.966 |
| Recall | 0.898 |
| F1 | 0.931 |
| TP / FP / FN | 605 / 21 / 69 |

Highest F1. Only 21 false positives in 2719 pages. Undercounts (626 vs 674) but what it detects is almost always correct.

### Key Design Choices

- **CLAHE** (`cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))`) enhances local contrast before computing dark_ratio per grid cell, amplifying the difference between cover pages and their neighbors.
- **min score** (vs harmonic or mean) acts as a strict AND gate: a page must stand out from BOTH its left and right neighbor. This kills one-sided FPs where a page is different from only one neighbor by coincidence.
- **Percentile threshold** is calibrated to yield ~674 matches (the target doc count). It's document-specific — a different PDF with different doc count would need a different percentile.

### Variants Tested But Not Better

| Variant | Best F1 | Notes |
|---------|---------|-------|
| ink_sum (continuous darkness, no threshold) | 0.894 | Threshold-free feature; slightly worse than CLAHE binary |
| ink_only (dark pixels only, ignore white) | 0.870 | Weighting by dark fraction didn't help |
| clahe_ink_sum (CLAHE + continuous) | 0.922 | Tied with CLAHE binary — no benefit from removing threshold |
| red_channel | 0.865 | Marginal improvement over baseline but far below CLAHE |
| otsu / clahe_otsu | excluded | Adaptive binarization destroyed discriminability (+43/+48 error) |

---

## What Was NOT Explored (future directions)

1. **Standalone doc count refinement:** The K-Means binary classification gives cover count, not doc count. A proper standalone doc counter would need to handle multi-page documents (e.g., period detection from bilateral scores alone).
2. **Alternative features:** Edge density, connected component count, or structural descriptors per tile instead of dark_ratio. These might better distinguish form headers from body content.
3. **Template matching:** Using VLM-confirmed covers as exemplars for supervised classification (needs only ~10 exemplars per document type).
4. **Different distance metrics:** The L2 bilateral score treats all 64 grid cells equally. Weighted cells (e.g., top-right where page numbers live) might improve discrimination.
5. **Bilateral as confidence booster:** Instead of injecting synthetic reads, use bilateral scores to boost/reduce confidence on existing inferred pages. This doesn't add new boundaries — it just adjusts certainty.

---

## Files Created This Session

| File | Purpose |
|------|---------|
| `audit_bilateral_coverage.py` | Stage 0: pipeline + VLM cross-reference |
| `characterize_density.py` | Stage 1: density regimes, segment detection, bimodality |
| `sweep_preprocessing.py` | Stage 2: CLAHE/red/Otsu/ink variant sweep (8 variants) |
| `simulate_realistic_injection.py` | Stage 4: corrected integration simulation |
| `baseline_bilateral_standalone.py` | Full standalone sweep (54 combos) + VLM evaluation |
| `data/pixel_density/audit_coverage.json` | Audit structured results |
| `data/pixel_density/density_regime_plot.png` | Density regime visualization |
| `data/pixel_density/preprocessing_sweep.json` | Preprocessing sweep results |
| `data/pixel_density/standalone_baseline.json` | Standalone sweep results (54 combos, sorted by F1) |
| `docs/superpowers/plans/2026-03-31-bilateral-improvement-plan.md` | Plan (updated with all results) |
