# Deskew — Design Spec

**Date:** 2026-03-23
**Branch:** cuda-gpu
**Status:** Approved

## Problem

Scanned PDFs with physically tilted pages cause Tesseract to misread or miss the "Página N de M" pattern. Correcting the skew before OCR improves read rates on imperfect scans.

## Scope

Add a `_deskew` function to `core/image.py` that detects and corrects small rotation angles (physical scan skew) using OpenCV's projection profile method. Plug it into `_process_page` in `core/ocr.py` between the render and the first Tesseract pass.

Out of scope: orientation detection (90°/180°/270° flips), full-page re-render for angle detection, telemetry changes.

## Algorithm

**Function:** `_deskew(bgr: np.ndarray) -> np.ndarray`

1. Convert BGR to grayscale.
2. Apply Otsu binarization (invert so text pixels are white on black background).
3. Sweep candidate angles in `[-10°, +10°]` with step `0.5°`.
4. For each angle: rotate the binary image around its center → compute per-row pixel sums → compute variance of that distribution.
5. Select the angle with maximum variance (highest horizontal alignment of text lines).
6. **Guard — too small:** if `|angle| < 0.5°`, return the original image unchanged.
7. **Guard — too large:** if `|angle| > 10°`, return the original image unchanged (likely a detection error on the small crop).
8. Apply `cv2.warpAffine` to the **BGR original** using the selected angle, with a white background fill (`borderValue=(255, 255, 255)`).
9. Return the corrected BGR image.

**Why projection profile:** maximizes row-sum variance when text lines are perfectly horizontal. More robust than Hough on sparse content (a single page-number line is enough).

**Angular range rationale:** physical scan skew rarely exceeds ±10°. Steps of 0.5° balance precision and speed (~40 iterations, each a rotation + sum, ~5–15ms total on CPU).

## Integration

**File:** `core/ocr.py`, function `_process_page`

Insert one call after `_render_clip` and before `_tess_ocr`:

```python
bgr = _render_clip(doc[page_idx])
bgr = _deskew(bgr)          # correct scan skew before OCR
text = _tess_ocr(bgr)
```

The deskewed image flows naturally to:
- Tier 1: Tesseract direct on corrected crop.
- Tier 2: 4x upscale (`_upsample_4x`) + Tesseract on corrected crop.
- Tier 3 (EasyOCR): unaffected — receives images via the GPU queue independently.

## Files Changed

| File | Change |
|------|--------|
| `core/image.py` | Add `_deskew(bgr) -> np.ndarray` |
| `core/ocr.py` | Call `_deskew(bgr)` in `_process_page` after render |

## Error Handling

- Any exception inside `_deskew` (e.g., empty image, OpenCV error) → catch, log via `warnings.warn`, return the original BGR unchanged. OCR proceeds as before.

## Testing

- Unit test in `tests/test_image.py`: synthetic tilted image → `_deskew` → verify returned image angle is within ±0.5° of 0°.
- Verify existing tests still pass (no regressions in `_process_page` behavior).

## Dependencies

No new dependencies. Uses `cv2` and `numpy`, both already present.
