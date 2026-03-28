# OCR Preprocessing Sweep — Postmortem

**Date:** 2026-03-28
**Status:** Production pipeline unchanged; eval tooling retained
**Branch:** `cuda-gpu`

---

## Purpose

Parameterized OCR image preprocessing pipeline for sweeping transforms before Tesseract.
Goal: rescue pages where `_parse()` fails to extract "Pagina N de M" from Tesseract output,
without regressing pages that already parse correctly.

## Production Pipeline (current)

```
HSV blue inpaint -> luminance grayscale -> unsharp mask (sigma=1.0, strength=0.3)
  -> skip_binarization (Tesseract handles thresholding) -> Tesseract PSM6 OEM1
```

This configuration was the v1 sweep winner and remains in `core/ocr.py` as `[MOD:v6-tess-sr]`.

## v1 Sweep (1024 configs)

**Parameter space:** blue_inpaint, grayscale_method (luminance/min_channel),
skip_binarization, tess_threshold (Otsu/Sauvola), white_border (0-15px),
unsharp_sigma (0-2.0), unsharp_strength (0-0.8), deskew. 2048 combinations,
~1024 effective after constraint pruning.

**Two-phase evaluation:**
- Phase A: all configs against 697 failed pages (rescue count)
- Phase B: top-10 configs against 200 success pages (regression check)

**Key finding:** `skip_binarization=True` + `unsharp_mask(1.0, 0.3)` was the clear winner.
External Otsu binarization hurts Tesseract LSTM (destroys gradient info at character edges).
Letting Tesseract handle thresholding internally, with mild sharpening, gave the best rescue/regression tradeoff.

## v2 Techniques (2026-03-27)

### CLAHE 2.0 (clipLimit=2.0, tileGrid=4x4)

- **Strip sweep:** +98 rescued pages vs baseline, 2 fewer regressions. Net gain +104.
- **Production (ART_670):** +100 OCR failures, -207 SR reads, -24 documents detected.
  Abnormal 8-page and 10-page documents appeared (merging). 3 new LOW-confidence pages.
- **Verdict:** REVERTED. Strip-level gains did not survive full-pipeline testing.
  CLAHE shifted Tier 1 pass/fail boundaries, causing pages that SR handled correctly
  to either produce wrong Tier 1 reads or fail both tiers entirely.

### Red Channel Extraction

- **Idea:** Extract BGR red channel instead of HSV inpaint. Blue ink has low R (~30-80).
- **Result:** rescued=863 vs HSV inpaint rescued=919. 16 more regressions.
- **Verdict:** DISCARDED. Strictly inferior to HSV inpainting. Residual ink at R~30-80
  overlaps faint text; HSV mask + Navier-Stokes inpainting is surgically cleaner.

### Morphological Dilation

- **Idea:** Thicken thin character strokes (~1px at 150 DPI) via invert-dilate-reinvert.
- **Result:** kernel=2: -234 rescues, +25 regressions. kernel=3: net -281 (catastrophic).
- **Verdict:** DISCARDED. Merges adjacent digits, destroys page-number recognition.
  Never revisit pure dilation for this domain.

## DPI 300 Experiment (2026-03-25)

Tested higher render DPI as an additional Tesseract tier. Offline sweep on 50 failed pages
showed 23/50 recovered, 0 wrong. In production on ART_670 (2719 pages):

- **Tier 1b (before SR):** COM dropped 90% -> 88%. DPI 300 intercepted 542 SR-readable
  pages; some reads were wrong but returned confidence 1.0, poisoning inference.
- **Tier 2b (after SR):** COM dropped 90% -> 87%. 199 exclusive DPI 300 reads still
  contained enough errors to break document boundaries (undercount 14 -> 21).

**Abandoned.** The sweep's 0% error on 50 pages did not generalize. Wrong reads at
confidence 1.0 are worse than failed reads (inference handles gaps; it trusts "reads").

## Confidence Gating (design only)

Designed but not shipped: replace `image_to_string()` with `image_to_data()` to get
per-word confidence scores. Reject parses where digit-word confidence < threshold (60).
Pages with low-confidence reads would fall to the next tier instead of poisoning inference.

This addresses the root cause of both the CLAHE and DPI 300 regressions: Tesseract reads
that match the regex but contain wrong digits, accepted at hardcoded confidence 1.0.

## Central Lessons

### 1. Eval-production gap is real

Strip-level sweep results do not predict full-pipeline behavior. CLAHE showed +98 rescue
on isolated strips but caused +100 failures end-to-end on ART_670. The eval harness tests
pre-extracted strips at consistent quality; production renders full pages at 150 DPI with
variable scan quality, then runs both Tier 1 and Tier 2. CLAHE + 4x SR upscale amplifies
noise differently than CLAHE alone.

### 2. One variable at a time

The CLAHE production test ran simultaneously with `s2t5-vlm` inference (vs `s2t-helena`
baseline). This made it impossible to attribute the ART_670 regression to either change.
A manual test cycle was wasted. Each change must be validated in isolation.

### 3. Wrong reads are worse than no reads

The inference engine handles failed pages gracefully via Dempster-Shafer propagation.
A single wrong read (e.g., "3/4" instead of "2/4") at confidence 1.0 cascades through
document boundary detection, breaking sequence validation for surrounding pages.

### 4. Small-sample 0% error does not generalize

DPI 300 sweep: 0/50 wrong. Production: enough wrong reads in 741 intercepted pages to
break dozens of doc boundaries. Even 1% error on intercepted pages is catastrophic.

## Future Directions

| Priority | Technique | Rationale |
|----------|-----------|-----------|
| High | End-to-end eval harness | Render from PDFs at production DPI, run both tiers, validate at document-count level |
| High | Adaptive CLAHE | Per-strip contrast metric; apply CLAHE only when contrast is low |
| Medium | CLAHE on Tier 2 only | Preserve proven Tier 1 pipeline; help harder SR cases |
| Medium | Bilateral filter | Edge-preserving denoising as alternative to unsharp mask |
| Medium | Otsu comparison study | Save raw + Otsu strips to detect binarization damage on ink-overlap pages |
| Low | Confidence gating | Route low-confidence Tier 1 reads to Tier 2 instead of accepting them |
| Low | Per-PDF preprocessing profiles | Classifier selects optimal chain per document scan characteristics |

## Files

```
eval/ocr_preprocessing/
  preprocess.py       # Parameterized pipeline (blue inpaint, CLAHE, dilate, red channel)
  sweep.py            # Two-phase sweep runner (--full, --tier1, --mini, --preprocess)
  params.py           # Parameter spaces + production baseline
  report.py           # Ranked results printer
  docs/specs/         # Design specs (v1 sweep, v2 design, DPI 300, confidence gating)
  docs/reports/       # v2 investigation report
  results/            # Sweep output JSON (gitignored)
```
