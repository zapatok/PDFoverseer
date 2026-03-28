# OCR Preprocessing Sweep v2 — Design Spec

**Date:** 2026-03-27
**Scope:** eval/ only — nothing ports to core/
**Branch:** cuda-gpu

## Objective

Evaluate 3 new image preprocessing techniques against the corrected production baseline, measuring rescue rate and regression on the existing `data/ocr_all/` dataset. Incremental sweeps isolate each technique, then a combo sweep crosses the winners.

## Context

- Images: 383x363px crops, chars ~5-6px cap height at 150 DPI
- Failure characteristics: blue pen overlap (~50%), right-edge clipping (~20%), colored cell fills (~15%), thin borders near text
- Production pipeline: deskew -> HSV blue mask + inpaint NS -> grayscale -> unsharp (sigma=1.0, strength=0.3) -> Tesseract PSM6 OEM1 (no external Otsu)
- Previous sweeps: skip_bin+unsharp won +23 net (already in production); PSM11 global regressed in manual test; Otsu discarded for this text size

## Baseline Correction

`OCR_PRODUCTION_PARAMS` in `eval/ocr_params.py` is stale. Must be updated to match actual `core/ocr.py`:

```python
OCR_PRODUCTION_PARAMS = {
    "blue_inpaint":      True,
    "grayscale_method":  "luminance",
    "skip_binarization": True,       # was False — production sends grayscale to Tesseract
    "tess_threshold":    0,
    "white_border":      0,
    "unsharp_sigma":     1.0,        # was 0.0
    "unsharp_strength":  0.3,        # was 0.0
    "deskew":            False,
}
```

`OCR_TIER1_PARAMS` inherits via spread, so it auto-corrects.

## New Techniques

### 1. Red Channel Extraction (`color_separation`)

Replace HSV mask + inpaint with direct red channel extraction (`bgr[:,:,2]`).

- Blue ink: R~30-80 (fades to near-white on white paper)
- Black text: R~0-40 (strong contrast preserved)
- Eliminates cvtColor(HSV) + inRange + inpaint — faster than baseline
- Values: `"hsv_inpaint"` (current), `"red_channel"` (new)
- Output is already grayscale (ndim==2), so grayscale step is skipped

### 2. CLAHE (`clahe_clip`)

Contrast Limited Adaptive Histogram Equalization after grayscale, before unsharp.

- `cv2.createCLAHE(clipLimit=X, tileGridSize=(4,4))`
- Handles colored cell backgrounds (blue/yellow) that lower local text contrast
- tileGridSize=(4,4) because images are small (383x363)
- Values: `0.0` (off), `2.0`, `3.0`
- Cost: ~0.5ms/image

### 3. Morphological Dilation (`morph_dilate`)

Thicken character strokes via dilate on inverted image, after binarization.

- At ~5-6px cap height, strokes are ~1px wide; Tesseract needs >=2px
- Invert -> dilate (thicken dark strokes) -> re-invert
- Values: `0` (off), `2` (2x2 kernel), `3` (3x3 kernel)
- Cost: ~0.2ms/image

## Pipeline Order

```
Current:  deskew -> blue_inpaint -> grayscale -> unsharp -> border -> binarization -> tess_config
New:      deskew -> COLOR_SEP -> grayscale -> CLAHE -> unsharp -> border -> binarization -> DILATE -> tess_config
```

## Sweep Structure

Mode `--preprocess` runs 4 sequential phases:

### Phase 1 — Red Channel (2 configs)
- `{color_separation: "hsv_inpaint"}` and `{color_separation: "red_channel"}`, rest = production
- Phase A: both against all failed pages
- Phase B: regression check against 200 success pages

### Phase 2 — CLAHE (3 configs)
- `{clahe_clip: 0.0, 2.0, 3.0}`, rest = production
- Phase A + B

### Phase 3 — Dilation (3 configs)
- `{morph_dilate: 0, 2, 3}`, rest = production
- Phase A + B

### Phase 4 — Combo (dynamic)
- Takes winners from phases 1-3 (net_gain > 0 only)
- Cartesian product of winning values x production base
- If no technique won, phase 4 is skipped
- Phase A + B

## Output Format

Single JSON in `eval/results/ocr_preprocess_v2_YYYYMMDD_HHMMSS.json`:

```json
{
  "run_at": "ISO timestamp",
  "mode": "preprocess_v2",
  "baseline_params": { "...corrected production params..." },
  "total_failed_pages": 1967,
  "total_success_pages": 1498,
  "success_sample_size": 200,
  "phases": {
    "red_channel": {
      "configs": [
        {
          "label": "hsv_inpaint",
          "params": { ... },
          "phase_a": { "rescued": N, "regressed": 0, "still_failed": N, ... },
          "phase_b": { "rescued": 0, "regressed": N, "maintained": N, ... },
          "net_gain": N,
          "rescued_pages": ["ART_670/p016", ...]
        }
      ],
      "winner": { "label": "...", "net_gain": N }
    },
    "clahe": { "configs": [...], "winner": {...} },
    "dilate": { "configs": [...], "winner": {...} },
    "combo": { "configs": [...], "winner": {...} }
  }
}
```

## Time Estimate

| Phase | Configs | Failed pages | Success sample | Est. time |
|-------|---------|-------------|----------------|-----------|
| 1. Red channel | 2 | 1967 | 200 | ~2 min |
| 2. CLAHE | 3 | 1967 | 200 | ~3 min |
| 3. Dilate | 3 | 1967 | 200 | ~3 min |
| 4. Combo | <=18 | 1967 | 200 | ~10 min |
| **Total** | | | | **~18 min** |

## Out of Scope

- PSM11 / fallback strategies
- Otsu binarization (discarded for this text size)
- Changes to core/ (eval only)
- Re-extraction of fixtures (uses existing images)
- 300 DPI / crop expansion (requires re-render from PDFs)
- min_channel grayscale (already tested, didn't win)
- Sauvola thresholding (already tested as tess_threshold=2, didn't win)

## Files Modified

| File | Change |
|------|--------|
| `eval/ocr_params.py` | Correct `OCR_PRODUCTION_PARAMS`, add `OCR_PREPROCESS_V2_SPACE` |
| `eval/ocr_preprocess.py` | Add red channel, CLAHE, dilate steps |
| `eval/ocr_sweep.py` | Add `--preprocess` mode with 4-phase runner |
