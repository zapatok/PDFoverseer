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

## Conclusion

**PD_V2_RC remains the best generalized config.** The V3 post-processing tools (`_apply_floor`, `_suppress_consecutive`, `scorer_v3`) are implemented and tested but not promoted to production because they don't improve cross-validation metrics.

The tools remain available for:
- **Floor:** Safety mechanism for known-single-document PDFs
- **Consecutive suppression:** ART-specific optimization when cross-validation is not a concern
- **scorer_v3:** Composable scorer with configurable post-processing

## Files

| File | Purpose |
|------|---------|
| `eval/pixel_density/analyze_errors.py` | FP/FN diagnostic script |
| `eval/pixel_density/sweep_v3.py` | V3 parameter sweep |
| `eval/tests/test_pd_v3.py` | 11 tests for V3 functions |
| `data/pixel_density/sweep_v3.json` | Sweep results |
