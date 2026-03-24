# Deskew — Design Spec

**Date:** 2026-03-23
**Branch:** cuda-gpu
**Status:** Draft

## Problem

Scanned PDFs with physically tilted pages cause Tesseract to misread or miss the "Página N de M" pattern. Correcting the skew before OCR improves read rates on imperfect scans.

## Scope

Add a `_deskew` function to `core/image.py` that detects and corrects small rotation angles (physical scan skew) using OpenCV's projection profile method. Plug it into `_process_page` in `core/ocr.py` between the render and the first Tesseract pass.

Out of scope: orientation detection (90°/180°/270° flips), full-page re-render for angle detection, telemetry changes, EasyOCR deskew (see Known Limitations).

## Algorithm

**Function:** `_deskew(bgr: np.ndarray) -> np.ndarray`

1. Convert BGR to grayscale.
2. Apply Otsu binarization (invert so text pixels are white on black background).
3. Sweep candidate angles in `[-10°, +10°]` with step `0.5°` (~40 iterations).
4. For each angle: rotate the binary image around its center → compute per-row pixel sums → compute variance of that distribution.
5. Select the angle with maximum variance (highest horizontal alignment of text lines).
6. **Guard — too small:** if `|angle| < 0.5°`, return the original image unchanged. This threshold is an independent constant (not derived from the sweep step); it represents the minimum correction worth applying given the resolution of the crop.
7. **Guard — too large:** if `|angle| > 10°`, return the original image unchanged (likely a detection error on the small crop).
8. Apply `cv2.warpAffine` to the **BGR original** using the selected angle, with white background fill (`borderValue=(255, 255, 255)`). White is correct because the crop background is white paper and `_tess_ocr` applies Otsu binarization downstream, so the fill color does not affect OCR quality.
9. Return the corrected BGR image.

**Why projection profile:** maximizes row-sum variance when text lines are perfectly horizontal. More robust than Hough on sparse content (a single page-number line is enough).

**Angular range rationale:** physical scan skew rarely exceeds ±10°. Steps of 0.5° balance precision and speed (~5–15ms total on CPU).

## Integration

**File:** `core/ocr.py`, function `_process_page`

Insert one call after `_render_clip` and before `_tess_ocr`. Overwrite `bgr` in place so that Tier 2 also receives the corrected image — `bgr_sr = _upsample_4x(bgr)` derives from the same variable, so the deskewed crop flows to Tier 2 implicitly without any additional changes:

```python
bgr = _render_clip(doc[page_idx])
bgr = _deskew(bgr)          # correct scan skew; Tier 1 and Tier 2 both see corrected image
text = _tess_ocr(bgr)
...
bgr_sr = _upsample_4x(bgr)  # inherits deskewed bgr automatically
```

The deskewed image flows to:
- **Tier 1:** Tesseract direct on corrected crop.
- **Tier 2:** 4x upscale (`_upsample_4x`) + Tesseract on corrected crop (implicit — `bgr_sr` derives from `bgr`).
- **Tier 3 (EasyOCR):** not deskewed — see Known Limitations.

## Files Changed

| File | Change |
|------|--------|
| `core/image.py` | Add `import warnings`; add `_deskew(bgr) -> np.ndarray` |
| `core/ocr.py` | Call `bgr = _deskew(bgr)` in `_process_page` after `_render_clip` |
| `tests/test_image.py` | Create file; add unit test for `_deskew` |

## Error Handling

Any exception inside `_deskew` (e.g., empty image, OpenCV error) → catch, issue `warnings.warn`, return the original BGR unchanged. OCR proceeds as before. `core/image.py` must add `import warnings` for this.

## Testing

Create `tests/test_image.py` (new file). Add one unit test:

- Generate a synthetic grayscale image with a horizontal text-like pattern (e.g., horizontal stripes), rotate it by a known angle (e.g., 3°) using `cv2.warpAffine`, pass the result to `_deskew`.
- Verify the corrected image: re-run the same projection-profile sweep on the output and confirm the detected angle is within ±0.5° of 0°. Running the same algorithm on the output is acceptable because the goal is that the sweep returns near-zero — a circular dependency that proves the correction converges, not that the image is pixel-perfect.
- Also verify existing tests still pass (no regressions).

## Known Limitations

**EasyOCR (Tier 3) does not receive the deskewed image.** EasyOCR re-renders the page at 300 DPI via a separate code path in the GPU consumer. If Tesseract fails on a skewed page, EasyOCR will receive the original skewed render. Since EasyOCR operates at higher resolution and uses a deep learning model, it may tolerate moderate skew better than Tesseract, but this is not guaranteed. Extending deskew to the EasyOCR path is a candidate follow-up task.

## Dependencies

No new pip dependencies. Uses `cv2` and `numpy` (already present). Adds `import warnings` to `core/image.py` (stdlib).
