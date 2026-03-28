# OCR Preprocessing v2 Investigation

**Date:** 2026-03-28
**Branch:** `cuda-gpu`
**Status:** CLAHE reverted from production; eval tooling retained for future use

## Objective

Evaluate 3 new image preprocessing techniques for Tier 1 Tesseract OCR to rescue pages that fail with the current production pipeline (blue inpaint + grayscale + unsharp mask + skip_binarization).

## Baseline (Production v6)

```python
# core/ocr.py _tess_ocr() — production pipeline before this investigation
blue_inpaint = True          # HSV mask + Navier-Stokes inpainting
grayscale_method = "luminance"
skip_binarization = True     # let Tesseract handle thresholding
tess_threshold = 0           # Tesseract internal threshold method
unsharp_sigma = 1.0
unsharp_strength = 0.3
psm = 6, oem = 1
```

Sweep dataset: 1967 failed + 1498 success pages (from eval fixtures).

## Techniques Evaluated

### 1. Red Channel Extraction

**Idea:** Extract BGR red channel (`bgr[:,:,2]`) instead of HSV inpainting. Blue pen ink has low R values (~30-80), black text has R~0-40 — the red channel naturally attenuates blue ink while preserving text.

**Results:**
- rescued=863, regressed=38, net_gain=749
- Compared to HSV inpaint: rescued=919, regressed=22, net_gain=853

**Verdict: DISCARDED.** HSV inpainting outperforms red channel on both rescue count and regression rate. Red channel loses ~56 rescues and adds 16 regressions vs baseline inpainting.

**Why it underperforms:** The red channel attenuates blue ink but doesn't remove it completely — residual ink noise at R~30-80 overlaps with faint text strokes. HSV inpainting surgically removes blue pixels and reconstructs the background, producing cleaner input for Tesseract.

### 2. CLAHE (Contrast Limited Adaptive Histogram Equalization)

**Idea:** Apply `cv2.createCLAHE(clipLimit, tileGridSize=(4,4))` after grayscale conversion to boost local contrast, making faint text more readable for Tesseract.

**Results (clipLimit sweep):**
| clipLimit | rescued | regressed | net_gain |
|-----------|---------|-----------|----------|
| 0.0 (off) | 919     | 22        | 853      |
| **2.0**   | **1017**| **20**    | **957**  |
| 3.0       | 917     | 29        | 830      |

**CLAHE 2.0 was the clear winner:** +98 additional rescues vs baseline, with 2 fewer regressions. Net gain +104 vs no-CLAHE.

**Ported to production as `[MOD:v7-tess-sr-clahe]`** — then reverted (see below).

### 3. Morphological Dilation

**Idea:** Invert → dilate (thicken strokes) → re-invert to make thin/broken character strokes more solid for Tesseract recognition.

**Results:**
| kernel_size | rescued | regressed | net_gain |
|-------------|---------|-----------|----------|
| 0 (off)     | 919     | 22        | 853      |
| 2           | 685     | 47        | 544      |
| 3           | 34      | 105       | -281     |

**Verdict: DISCARDED.** Catastrophic at kernel=3 (net -281). Even kernel=2 loses 234 rescues and adds 25 regressions. Dilation merges adjacent characters and destroys digit recognition.

### 4. Combo Phase

No combo was tested because only CLAHE 2.0 showed positive signal. Red channel and dilation were both worse than baseline individually — combining losers doesn't produce winners.

## Production Test: CLAHE 2.0 Regression

### What happened

CLAHE 2.0 was ported to `core/ocr.py` and tested manually on all 21 source PDFs as `[MOD:v7-tess-sr-clahe]` with inference engine `s2t5-vlm`.

**ART_670 regression (the largest/hardest PDF, 1854 pages):**
- OCR failures: 588 → 688 (+100)
- super_resolution reads: 494 → 287 (-207)
- Documents detected: 668 → 644 (-24)
- Abnormal document sizes appeared: 8p×1, 10p×1 (merging)
- LOW confidence pages: 0 → 3
- Inferred pages: 120 → 46 (-74)

All other 20 PDFs showed similar or identical results to baseline.

### Confounding variable

The production test ran with **two simultaneous changes**:
1. CLAHE 2.0 (OCR preprocessing)
2. `s2t5-vlm` inference engine (vs `s2t-helena` in baseline)

This made it impossible to attribute the ART_670 regression to either change alone.

### Why sweep results didn't predict the regression

The eval sweep tests preprocessing on **isolated page-number strips** extracted as fixtures. Production runs on **full PDF pages** rendered at 150 DPI, cropped to the rightmost 30% × top 22%.

Key differences:
- **Strip quality:** Eval strips are pre-extracted at consistent quality. Production strips come from real-time rendering with variable scan quality, compression artifacts, and page geometry.
- **Tier 2 interaction:** CLAHE modifies the base image that Tier 2 (4x GPU bicubic upscale) receives. The sweep only tested Tier 1. CLAHE + 4x upscale may amplify noise differently than CLAHE alone.
- **SR read collapse:** The -207 super_resolution reads suggest CLAHE is changing Tier 1 pass/fail boundaries — pages that previously failed Tier 1 (triggering Tier 2 rescue) now "pass" Tier 1 with wrong text, or pages that previously passed Tier 1 now fail both tiers.

### Decision

**Reverted CLAHE from production** (`[MOD:v6-tess-sr]`). The +98 rescue gain on isolated strips doesn't justify +100 failures on the hardest real PDF. The eval harness needs to better simulate production conditions before preprocessing changes can be trusted.

## Eval Tooling Produced

All eval code was committed and retained for future sweeps:

- **`eval/ocr_sweep.py`** — `--preprocess` mode with 4-phase sweep logic (red channel, CLAHE, dilation, combo)
- **`eval/ocr_preprocess.py`** — Parameterized preprocessing pipeline with color_separation, CLAHE, morph_dilate steps
- **`eval/ocr_params.py`** — `OCR_PRODUCTION_PARAMS` (corrected) + `OCR_PREPROCESS_V2_SPACE`
- **Results:** `eval/results/ocr_preprocess_v2_20260327_195643.json`
- **Spec:** `docs/superpowers/specs/2026-03-27-ocr-preprocess-v2-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-27-ocr-preprocess-v2.md`

Note: `eval/ocr_sweep.py` success_sample_size was reduced from 200 to 50 for speed during this investigation. Consider restoring to 200 for future sweeps that need higher statistical confidence.

## Future Directions

### High priority

1. **Isolate VLM regression:** Run manual test with `s2t5-vlm` alone (no CLAHE) to determine if the ART_670 regression comes from VLM inference changes, not preprocessing.

2. **End-to-end eval harness:** The current OCR sweep tests isolated strips. A more reliable eval would:
   - Render pages from actual PDFs at production DPI (150)
   - Apply the full crop pipeline (rightmost 30% × top 22%)
   - Run both Tier 1 and Tier 2
   - Compare against ground truth at the document-count level, not just page-read level

3. **Per-PDF sweep:** Run CLAHE sweep on ART_670 specifically to understand why it regresses on that PDF. Hypothesis: ART_670 has different scan characteristics (compression, ink color, paper tone) that CLAHE handles poorly.

### Medium priority

4. **Adaptive CLAHE:** Instead of fixed clipLimit=2.0, compute per-strip contrast metrics and apply CLAHE only when contrast is below a threshold. This could capture the +98 rescues without the ART_670 regression.

5. **CLAHE on Tier 2 only:** Apply CLAHE only to the 4x-upscaled image (after SR), not to the Tier 1 path. This preserves the proven Tier 1 pipeline while potentially helping the harder Tier 2 cases.

6. **Otsu comparison study:** Save raw + Otsu-binarized versions of failure strips to detect if binarization (or its absence with skip_binarization=True) destroys text when ink/pen overlaps page numbers. (Previously noted in memory as `project_otsu_comparison_idea`.)

### Low priority / exploratory

7. **Bilateral filter:** Edge-preserving denoising that smooths flat regions while keeping text edges sharp. Could replace or complement unsharp mask.

8. **Morphological opening** (erosion then dilation): Unlike pure dilation (which failed), opening can remove small noise dots without merging characters. Needs careful kernel sizing.

9. **Document-specific preprocessing profiles:** If different PDFs have fundamentally different scan characteristics, a classifier could select the optimal preprocessing chain per document. Overkill for now, but worth noting if more PDFs show divergent behavior.

## Lessons Learned

1. **Eval-production gap is real.** Isolated strip sweeps can show +98 rescue gains that don't survive full-pipeline testing. Always validate preprocessing changes with end-to-end manual tests on the hardest PDFs (especially ART_670).

2. **One variable at a time.** Testing CLAHE + VLM simultaneously wasted a manual test cycle. Each change must be tested in isolation before combining.

3. **Tier 2 interaction matters.** Preprocessing changes affect the base image for both tiers. Tier 2 (4x upscale) can amplify artifacts that are invisible at Tier 1 resolution.

4. **Dilation is catastrophic for digit OCR.** Even small kernels (2×2) merge adjacent digits. Never revisit pure dilation for page-number recognition.

5. **Red channel is strictly inferior to HSV inpainting** for blue ink removal in this domain. The precision of HSV masking + inpainting outweighs the simplicity of channel extraction.
