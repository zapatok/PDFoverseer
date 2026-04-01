# PD V3 Error Analysis — Floor + Consecutive Suppression

**Date:** 2026-04-01
**Branch:** `research/pixel-density`
**Baseline:** PD_V2_RC (F1=0.956, 30 FP, 29 FN on ART_674)

## Objective

Reduce the 30 false positives and 29 false negatives in PD_V2_RC on ART_674.pdf, and fix the fundamental flaw where single-document PDFs always produce ~25% false covers due to the relative percentile threshold.

## FP/FN Diagnosis

### Score Distribution

| Category | Count | Score Min | Score Max | Score Mean |
|----------|-------|-----------|-----------|------------|
| True Positive | 645 | 13.69 | 25.81 | 18.54 |
| False Positive | 30 | 13.63 | 19.27 | 14.65 |
| False Negative | 29 | 7.98 | 13.63 | 12.53 |
| Non-cover | ~1944 | 3.96 | 13.61 | 8.81 |

**Threshold (percentile 75.2):** 13.63

The gap between the lowest TP (13.69) and the highest FN (13.63) is only **0.06** — the threshold sits right at the boundary.

### FP Root Cause: Document Boundary Pairs

20/30 FPs are at position 4 or 5 within their document — the **last page of one document and the first page of the next**. When two documents have different visual styles, the transition creates high bilateral scores on BOTH sides of the boundary. Only the first page of the new document is a real cover, but both pages score high.

8/30 FPs come in consecutive pairs with identical bilateral scores:
- Pages 1840-1841 (score=13.77)
- Pages 1845-1846 (score=14.10)
- Pages 1860-1861 (score=13.89)
- Pages 1870-1871 (score=13.69)
- Pages 1885-1886 (score=13.79)
- Pages 2049-2050 (score=14.14)
- Pages 2279-2280 (score=15.28)

### FN Root Cause: Homogeneous Zone

18/29 FNs are in pages 2055-2128 — a zone of consecutive 4-page documents with visually similar covers. These are all part of the same series (same template, same layout), so bilateral scores between adjacent documents are low.

23/29 FNs are within 10% of threshold. Most are barely below the cut.

### Document Size Distribution

93.6% of ART_674 documents are exactly 4 pages (631/674). This uniformity is what makes the percentile 75.2 work: the real cover ratio is 674/2648 = 25.5%, close to the 25% that pct 75.2 selects.

## Interventions Tested

### 1. Absolute Score Floor

**Hypothesis:** A minimum absolute score would prevent spurious detections on single-document PDFs where no real transitions exist.

**Result: No effect on ART_674.** All 30 FP pages have bilateral scores ≥ 13.63 — above every floor value tested (0, 5, 7, 8, 9, 10, 11, 12, 13). The FPs are real visual transitions, just not at cover pages.

**Why:** The floor was designed for a different problem (single-doc PDFs). On a multi-document PDF like ART_674, the FPs have genuinely high bilateral scores because they ARE at visual transitions — just the wrong ones (document boundaries seen from the wrong side).

### 2. Consecutive Detection Suppression

**Hypothesis:** When two adjacent pages are both detected, the "wrong side" FP can be eliminated by keeping only the higher-scoring page.

**Result on ART_674: Dramatically effective.** FPs dropped from 30 to 3 (90% reduction). F1 improved from 0.956 to 0.971.

| Metric | V2_RC | V3 (suppress) |
|--------|-------|---------------|
| F1 | 0.956 | **0.971** |
| Precision | 0.956 | **0.995** |
| Recall | 0.957 | 0.948 |
| TP | 645 | 639 |
| FP | 30 | **3** |
| FN | 29 | 35 |

**However, fails cross-validation.** gen_MAE went from 20.1 to 29.7 (+48% regression). On smaller PDFs with short documents (1-2 pages), legitimate consecutive covers exist, and suppressing them removes real detections.

### Sweep Results Table

| Floor | Suppress | F1 | TP | FP | FN | gen_MAE | art_MAE |
|-------|----------|------|-----|----|----|---------|---------|
| 0.0 | No | 0.9563 | 645 | 30 | 29 | 20.1 | 0.0 |
| 0-13 | No | 0.9563 | 645 | 30 | 29 | 20.1-20.4 | 0.0 |
| 0.0 | Yes | **0.9711** | 639 | **3** | 35 | **29.7** | 0.0 |
| 0-13 | Yes | **0.9711** | 639 | **3** | 35 | **29.7-29.8** | 0.0 |

**Winner selection:** No config improves ART_674 F1 without regressing gen_MAE beyond the 0.5 tolerance. The control (V2_RC) remains the best generalized config.

## Key Findings

1. **The 30 FPs are structurally unfixable by post-processing.** They're genuine visual transitions with high bilateral scores. Only a feature that distinguishes "cover page" from "last page before a cover" could fix them — not a score filter.

2. **Consecutive suppression is the most promising direction** but needs a way to avoid hurting short-document PDFs. Possible approaches:
   - Only suppress when the PDF has >100 pages (ART-scale PDFs don't have 1-page documents)
   - Only suppress when both pages in a pair have very similar scores (true boundary pairs have near-identical scores)
   - Combine with a minimum document size heuristic

3. **The floor is valuable as a safety mechanism** for single-document PDFs (prevents ~25% false detection) even though it doesn't improve ART_674 accuracy. It should be available as a configurable option.

4. **The 29 FNs require a fundamentally different approach** — either adaptive local thresholds or additional features that capture template similarity across the homogeneous zone.

## Document Count Impact (ART Family)

The metric that matters most to the user is **how many documents** the algorithm counts, not page-level F1.

| PDF | Target | V2_RC | err | V3 suppress | err |
|-----|--------|-------|-----|-------------|-----|
| ART_674 | 674 | **675** | +1 | 642 | -32 |
| ART_CH_13 | 13 | **13** | 0 | **13** | 0 |
| ART_CON_13 | 13 | **13** | 0 | **13** | 0 |
| ART_EX_13 | 13 | **13** | 0 | **13** | 0 |
| ART_GR_8 | 8 | **8** | 0 | **8** | 0 |
| ART_ROC_10 | 10 | **10** | 0 | **10** | 0 |

V2_RC: total error = +1 across 6 ART PDFs.
V3 suppress: loses 32 documents on ART_674 — suppression kills real covers at document boundaries.

## The Percentile Problem (Unresolved)

The percentile 75.2 threshold always selects the top ~25% of pages as covers, regardless of whether the scores represent genuine transitions. This is equivalent to saying "25% of pages are covers" without analyzing content. It works on ART_674 because the real cover ratio happens to be ~25.5% (674/2648), but fails structurally on:

- Single-document PDFs (would mark ~25% as covers when only page 0 is correct)
- PDFs with different document-to-page ratios

The floor was designed to address this but has no effect on ART_674 because all FP scores are genuinely high (≥13.63). The floor only helps on single-document PDFs where all bilateral scores are low.

**Solving this properly requires replacing the percentile with an adaptive cut that finds the natural boundary between "cover scores" and "content scores" without assuming a fixed ratio.**

## Investigation Results (Phase 2)

### find_peaks (scipy.signal) — Breakthrough for ART

Instead of percentile threshold, treat bilateral scores as a 1D signal and detect **peaks** (local maxima that stand out from surroundings). Uses `scipy.signal.find_peaks` with `prominence` parameter — prominence measures how much a peak rises above its lowest surrounding contour, independent of absolute height.

```
scipy.signal.find_peaks(scores, prominence=0.5, distance=2)
```

- `prominence=0.5`: minimum rise from surrounding signal to count as a peak
- `distance=2`: minimum 2 pages between peaks (ART docs are always ≥2 pages)

**ART_674 results (prominence sweep):**

| Prominence | Detected | TP | FP | FN | F1 | Doc count error |
|------------|----------|-----|----|----|------|----------------|
| 0.5 | 670 | 666 | 4 | 8 | **0.9911** | -4 |
| 1.0 | 668 | 664 | 4 | 10 | 0.9896 | -6 |
| 1.3 | 667 | 664 | 3 | 10 | 0.9903 | -7 |

**Best: prominence=0.5, distance=2 → F1=0.9911** (vs V2_RC F1=0.956). Only 4 FP and 8 FN.

**ART family doc count cross-validation:**

| PDF | Target | V2_RC | err | find_peaks p=0.5 | err |
|-----|--------|-------|-----|------------------|-----|
| ART_674 | 674 | 675 | +1 | 670 | **-4** |
| ART_CH_13 | 13 | 13 | 0 | 13 | 0 |
| ART_CON_13 | 13 | 13 | 0 | 13 | 0 |
| ART_EX_13 | 13 | 13 | 0 | 13 | 0 |
| ART_GR_8 | 8 | 8 | 0 | 8 | 0 |
| ART_ROC_10 | 10 | 10 | 0 | 10 | 0 |
| **Total MAE** | | | **0.2** | | **0.7** |

find_peaks preserves perfect accuracy on the 5 small ART PDFs while dramatically improving F1 on ART_674. Doc count error goes from +1 to -4 (slightly worse in absolute terms but the quality of detections is vastly superior: 4 FP vs 30 FP).

**General corpus:** find_peaks is WORSE than percentile on non-ART PDFs (MAE 25.7 vs 20.1). This is expected — non-ART PDFs don't have the same peak-structured signal. find_peaks is an ART-specific optimization.

**Why it works:** find_peaks doesn't assume "25% are covers" — it finds pages that genuinely stand out from their neighbors. No ratio assumption. A single-document ART PDF would correctly detect only page 0 (no other peaks exist).

### find_peaks + Cover Shift — F1=0.9926

**Key discovery:** 3 of the 4 FPs are **displacement errors** — the bilateral peak is 1 page off from the real cover. The peak lands on page N+1 (last page of current doc) instead of page N (first page of next doc), because both sides of the document boundary have similar scores.

Example: page 541 is a real cover (curr=1), page 542 is the last page of a 1-page document (curr=4/total=4), page 543 is another real cover. The bilateral scores are 19.22, 19.27, 19.27 — find_peaks picks 542 as the peak because it's the local maximum, but 541 is the real cover.

**Fix: shift_to_cover.** For each detected peak, check if the page before it has a score within 1% (sim=0.99). If so, shift the detection left by 1. This corrects the displacement without affecting peaks that are clearly positioned.

| Config | Detected | TP | FP | FN | F1 | Doc err |
|--------|----------|-----|----|----|------|---------|
| V2_RC (pct 75.2) | 675 | 645 | 30 | 29 | 0.956 | +1 |
| find_peaks p=0.5 d=2 | 670 | 666 | 4 | 8 | 0.991 | -4 |
| **fp + shift (sim=0.99)** | **670** | **667** | **3** | **7** | **0.9926** | **-4** |

The remaining 3 FP and 7 FN are **irreducible with bilateral scores alone**:

**3 FP (content pages that are genuine visual outliers):**
- p1762: score=15.03 — content page with unusual layout
- p1795: score=15.08 — content page with unusual layout
- p2061: score=13.32 — content page in homogeneous zone

**7 FN (covers that are NOT local maxima):**
- All 7 have `is_local_max=False` — their right neighbor has a higher score
- p1745 (score=7.98) and p2128 (score=10.23) have genuinely low bilateral scores — visually similar to neighbors
- p543 (score=19.27) is a special case: two consecutive covers (1-page doc between them) create equal scores, and find_peaks picks one, shift corrects the other, but the third (p543) remains undetected

**ART family cross-validation (find_peaks + shift):** 5/5 small ARTs remain exact. ART_674 doc count = 670 (err=-4).

### Suppress Near-Identical Scores

Testing on V2_RC (percentile 75.2) with various epsilon values:

| Epsilon | Detected | TP | FP | FN | F1 | Error |
|---------|----------|-----|----|----|------|-------|
| 0 (V2_RC) | 675 | 645 | 30 | 29 | 0.956 | +1 |
| 0.001 | 665 | 643 | 22 | 31 | 0.960 | -9 |
| 0.01 | 665 | 643 | 22 | 31 | 0.960 | -9 |
| 0.5 | 661 | 642 | 19 | 32 | 0.962 | -13 |
| 1.0 | 657 | 641 | 16 | 33 | 0.963 | -17 |

Reduces FPs but also loses some TPs (those at boundaries where both pages are real covers from adjacent documents). Net F1 improvement is modest (+0.004 to +0.007). Doc count error worsens from +1 to -9 through -17.

**Verdict:** Not worth pursuing as standalone intervention. find_peaks already eliminates the boundary pair problem more elegantly.

### Otsu Threshold

Tested `skimage.filters.threshold_otsu` on bilateral scores:

| PDF | Target | Otsu detected | Error |
|-----|--------|---------------|-------|
| ART_674 | 674 | 682 | +8 |
| ART_CH_13 | 13 | 25 | +12 |
| ART_GR_8 | 8 | 16 | +8 |

**Verdict:** Otsu severely over-detects on small PDFs. Same problem as KMeans k=2 — adapts to each PDF's score distribution, not to document structure. Rejected.

## Future Investigation Lines

### 1. Suppress with Near-Identical Scores (Low Risk, High Confidence)

The 8 FP consecutive pairs all have **identical** bilateral scores (difference = 0.0000). Real consecutive covers have different scores because they have different neighbors. Rule: if two adjacent detected pages have scores within ε (e.g., 0.01), keep only the higher-scoring one.

**Expected impact:** -8 FP on ART_674, no regression on other PDFs.
**Risk:** Very low — identical scores at boundaries is a structural artifact, not a pattern seen in real consecutive covers.

### 2. Periodicity Detection via Autocorrelation (Medium Complexity)

ART documents are 93.6% 4-page. The bilateral score signal should show periodicity at lag=4. Autocorrelation (already used in `core/inference.py`) could detect this period and place covers at period boundaries instead of using a threshold.

**Advantage:** No threshold needed — detects structure directly.
**Risk:** Not all documents are the same length (33 are 5-page, 4 are 3-page). Mixed periods would weaken the autocorrelation peak. Would need to handle variable-period documents.

### 3. Two-Pass Feature Enrichment (Medium Complexity)

First pass: V2_RC as-is. Second pass: for pages with scores in the "gray zone" (e.g., 11.0-14.0), extract additional features (`projection_stats`, `cc_stats`) and re-evaluate.

**Advantage:** Doesn't affect clear detections (scores >15 or <10). Only refines borderline cases. Would not cause regressions on pages far from threshold.
**Risk:** Defining the gray zone boundaries. The additional features might not separate covers from content in the homogeneous zone if the visual difference is too subtle.

### 4. Calibrated Absolute Threshold for ART Family (Low Complexity)

Instead of percentile, use a fixed absolute threshold calibrated on the ART corpus. We know: TP min = 13.69, non-cover max = 13.61, gap = 0.06. If this range is consistent across the 5 smaller ART PDFs, a threshold of ~13.65 would work for all ART-type PDFs.

**Advantage:** Simple, no percentile assumption.
**Risk:** Only works for PDFs with similar visual characteristics to ART. Not generalizable. Would need a way to detect "is this an ART-like PDF" to apply the right threshold.

### 5. Repeating Pattern Detection (Speculative)

Detect that a sequence of 3-4 pages with consistent feature vectors repeats throughout the PDF. If pages [A, B, C, D] have a similar pattern to [E, F, G, H], they likely represent two instances of the same document template. The first page of each group is the cover.

**Advantage:** Doesn't need a threshold — detects document structure directly.
**Risk:** Assumes documents follow a consistent template. Fails for heterogeneous collections. High implementation complexity.

## Conclusion

**PD_V2_RC remains the best generalized config.** The V3 post-processing tools (`_apply_floor`, `_suppress_consecutive`, `scorer_v3`) are implemented and tested but not promoted to production because they don't improve cross-validation metrics.

The tools remain available for:
- **Floor:** Safety mechanism for known-single-document PDFs
- **Consecutive suppression:** ART-specific optimization when cross-validation is not a concern
- **scorer_v3:** Composable scorer with configurable post-processing

The most promising next step is **near-identical suppress** (line 1): low risk, targets 8/30 FPs specifically, unlikely to regress. After that, **two-pass enrichment** (line 3) or **periodicity** (line 2) for the 29 FN pages.

## Files

| File | Purpose |
|------|---------|
| `eval/pixel_density/analyze_errors.py` | FP/FN diagnostic script |
| `eval/pixel_density/sweep_v3.py` | V3 parameter sweep |
| `eval/tests/test_pd_v3.py` | 11 tests for V3 functions |
| `data/pixel_density/sweep_v3.json` | Sweep results |
