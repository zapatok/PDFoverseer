# OCR Preprocessing Sweep — Design Spec

**Date:** 2026-03-24
**Branch:** cuda-gpu
**Status:** Draft

## Problem

697 pages fail OCR parsing across 7 PDFs (686 from ART_670 alone). In 693/697 cases, Tesseract reads *something* but `_parse()` cannot extract the "Página N de M" pattern. Both Tier 1 (direct) and Tier 2 (4x SR) fail on the same pages. Typical failure modes:

- Garbled keyword: `F·zina 1 06`, `Pagne 7 ot`, `aging 1 de 4`
- Truncated total: `Pagina 1 do` (no digit after "de")
- Wrong separator: `Pagina 4 aa`, `Pagina 4 da`

The current preprocessing (HSV blue-mask → inpainting → grayscale → Otsu binarization → Tesseract) was hand-tuned. Research indicates:

1. **External Otsu binarization may hurt Tesseract LSTM** — the LSTM engine uses gradient info at character edges that binarization destroys (Tesseract issue #1780).
2. **Tesseract's built-in Sauvola** (`-c thresholding_method=2`) adapts locally and may handle degraded scans better.
3. **Min-channel grayscale** (`np.min(bgr, axis=2)`) maximizes ink-vs-background contrast.
4. **White border padding** (10px) improves Tesseract edge detection per official docs.
5. **Unsharp mask** sharpens blurred text (Chernyshova 2020: 70.2% → 92.9% accuracy).
6. **Deskew** (projection profile) is already implemented in `core/image.py`.

## Goal

Build an evaluation harness that tests parameterized preprocessing pipelines against saved OCR crop images, measures rescue rate (failed→parsed) and regression rate (parsed→failed), and identifies the optimal preprocessing configuration.

## Scope

- **In scope:** New files under `eval/` for OCR preprocessing sweep. Uses existing image captures in `data/ocr_all/` and existing `_parse()` from `core/utils.py`.
- **Out of scope:** Changes to production `core/ocr.py` or `core/image.py` (those come after sweep results). EasyOCR (Tier 3) preprocessing. Regex/parser changes. New image captures.

## Data

### Source: `data/ocr_all/`

| Item | Detail |
|------|--------|
| Images | BGR PNGs at `<PDF_NAME>/pNNN.png` (150 DPI crops, top-right 30%×22%) |
| Index | `all_index.csv` — columns: `pdf_nickname, page_num, tier1_parsed, tier2_parsed, tier1_text, tier2_text, tier3_text, image_path` |
| Total pages | 3465 across 21 PDFs |
| Failed pages | 697 (no tier1 or tier2 parse) |
| PDFs with failures | ART_670 (686), CHAR_25 (2), CH_39 (1), CH_51docs (1), CH_74docs (2), INSAP_20 (3), INS_31 (2) |

### Ground Truth

Derived from `all_index.csv`:
- **Success:** `tier1_parsed` or `tier2_parsed` is non-empty (e.g., `"1/2"`)
- **Failure:** both empty

No external ground truth needed — `_parse()` is the oracle. A page is "rescued" if `_parse()` succeeds on the Tesseract output after new preprocessing.

## Architecture

### File Structure

```
eval/
├── ocr_params.py       # Parameter space + production baseline
├── ocr_preprocess.py   # Parameterized preprocessing pipeline
├── ocr_sweep.py        # Sweep runner: load images, preprocess, OCR, score
└── ocr_report.py       # Print ranked results from sweep JSON
```

### `eval/ocr_params.py` — Parameter Space

```python
OCR_PARAM_SPACE: dict[str, list] = {
    # Blue ink removal
    "blue_inpaint":       [True, False],

    # Grayscale conversion method
    #   "luminance"  = cv2.COLOR_BGR2GRAY (standard)
    #   "min_channel" = np.min(bgr, axis=2) (max ink contrast)
    "grayscale_method":   ["luminance", "min_channel"],

    # Skip external binarization (let Tesseract LSTM handle it)
    "skip_binarization":  [True, False],

    # Tesseract internal thresholding (only when skip_binarization=True)
    #   0 = Otsu (default), 1 = LeptonicaOtsu, 2 = Sauvola
    "tess_threshold":     [0, 2],

    # White border padding (pixels)
    "white_border":       [0, 5, 10, 15],

    # Unsharp mask: sigma (0 = disabled)
    "unsharp_sigma":      [0.0, 1.0, 1.5, 2.0],

    # Unsharp mask: strength (amount - 1.0)
    "unsharp_strength":   [0.0, 0.3, 0.5, 0.8],

    # Deskew (projection profile, already in core/image.py)
    "deskew":             [True, False],
}

# Current production pipeline equivalent
OCR_PRODUCTION_PARAMS: dict[str, ...] = {
    "blue_inpaint":      True,
    "grayscale_method":  "luminance",
    "skip_binarization": False,
    "tess_threshold":    0,
    "white_border":      0,
    "unsharp_sigma":     0.0,
    "unsharp_strength":  0.0,
    "deskew":            False,
}
```

**Total combinations:** 2 × 2 × 2 × 2 × 4 × 4 × 4 × 2 = **2048**

**Constraint:** When `skip_binarization=False`, `tess_threshold` is ignored (external Otsu is applied regardless). This halves the effective space to ~1024 unique pipelines.

### `eval/ocr_preprocess.py` — Parameterized Pipeline

```python
def preprocess(bgr: np.ndarray, params: dict) -> tuple[np.ndarray, str]:
    """
    Apply parameterized preprocessing to a BGR crop image.
    Returns (processed_image, tess_config_string).
    """
```

Pipeline steps (in order):

1. **Deskew** — if `params["deskew"]` is True, call `_deskew(bgr)` from `core/image.py`.
2. **Blue ink removal** — if `params["blue_inpaint"]` is True, apply HSV mask + inpainting (same logic as current `_tess_ocr`).
3. **Grayscale conversion** — `"luminance"`: `cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)`. `"min_channel"`: `np.min(bgr, axis=2)`.
4. **Unsharp mask** — if `params["unsharp_sigma"] > 0`: apply `cv2.GaussianBlur` then `cv2.addWeighted(gray, 1+strength, blurred, -strength, 0)`.
5. **White border** — if `params["white_border"] > 0`: `cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)`.
6. **Binarization** — if `params["skip_binarization"]` is False: apply `cv2.threshold(img, 0, 255, THRESH_BINARY + THRESH_OTSU)`. Otherwise pass grayscale directly to Tesseract.
7. **Tesseract config** — base `"--psm 6 --oem 1"`. If `skip_binarization=True`, append `-c thresholding_method=<tess_threshold>`.

Returns `(processed_image, tess_config)`.

### `eval/ocr_sweep.py` — Sweep Runner

**Data loading:**
1. Parse `data/ocr_all/all_index.csv` to build page registry with known parse results.
2. For each page, note: `pdf_nickname`, `page_num`, `image_path`, `is_success` (tier1 or tier2 parsed), `expected_parse` (the `curr/total` string if parsed).

**Scoring a config:**
```python
def score_config(params: dict, pages: list[PageEntry]) -> dict:
    rescued = 0       # was failed, now parses
    regressed = 0     # was success, now fails
    maintained = 0    # was success, still parses
    still_failed = 0  # was failed, still fails

    for page in pages:
        bgr = cv2.imread(page.image_path)
        img, tess_cfg = preprocess(bgr, params)
        text = pytesseract.image_to_string(img, lang="eng", config=tess_cfg)
        curr, total = _parse(text)
        parsed = curr is not None

        if page.is_success and parsed:
            maintained += 1
        elif page.is_success and not parsed:
            regressed += 1
        elif not page.is_success and parsed:
            rescued += 1
        else:
            still_failed += 1

    return {
        "rescued": rescued,
        "regressed": regressed,
        "maintained": maintained,
        "still_failed": still_failed,
        "rescue_rate": rescued / max(1, rescued + still_failed),
        "regression_rate": regressed / max(1, maintained + regressed),
        "net_gain": rescued - regressed * 3,  # penalize regressions 3x
    }
```

**Sweep strategy — two-phase:**

1. **Phase A — Failed pages only (697 images):** Run all ~1024 effective configs against failed pages only. Score = rescue count. This is fast: 697 images × 1024 configs ÷ ~10 pages/sec ≈ ~20 hours single-threaded, but parallelizable across configs. Use `concurrent.futures.ProcessPoolExecutor` to parallelize across Tesseract workers (6 workers = ~3-4 hours).

2. **Phase B — Regression check (top-10 configs):** Run the top-10 configs from Phase A against a random sample of 200 successful pages. Verify regression rate < 1%. Rank by `net_gain = rescued - regressed * 3`.

**Parallelization:** Each config runs independently. Use multiprocessing (not threading) because Tesseract subprocess + OpenCV preprocessing are CPU-bound. A process pool of 6 workers matches the production `PARALLEL_WORKERS` setting.

**Output:** `eval/results/ocr_sweep_YYYYMMDD_HHMMSS.json` with:
```json
{
  "run_at": "...",
  "total_failed_pages": 697,
  "total_success_sample": 200,
  "configs_tested": 1024,
  "phase_a_top10": [...],
  "phase_b_results": [...],
  "baseline": { "rescued": 0, "regressed": 0, ... }
}
```

### `eval/ocr_report.py` — Results Reporter

Print a ranked table of top configs from the sweep JSON, showing:
- Rank, rescue count, regression count, net gain
- Parameter values that differ from production baseline

## Performance Estimate

| Phase | Images | Configs | OCR calls | Workers | Est. time |
|-------|--------|---------|-----------|---------|-----------|
| A: Failures | 697 | 1024 | 713,728 | 6 | ~3-4 hr |
| B: Regression | 200 | 10 | 2,000 | 6 | ~3 min |

**Alternative — fast mode:** Phase A can run on ART_670 failures only (686 images) with a random sample of 200 configs first to identify promising regions, then full grid on top candidates. This reduces Phase A to ~30 min.

## Error Handling

- Missing image file → skip page, log warning, do not crash
- Tesseract timeout or crash on single page → count as "failed", continue
- Invalid parameter combination → skip config (e.g., `unsharp_strength > 0` but `unsharp_sigma == 0`)

## Dependencies

No new pip dependencies. Uses `cv2`, `numpy`, `pytesseract`, `csv`, `concurrent.futures` (all already available). Imports `_parse` from `core.utils` and `_deskew` from `core.image`.

## Testing

Unit tests for `eval/ocr_preprocess.py`:
1. `test_preprocess_production_baseline` — verify production params produce same output as current `_tess_ocr` pipeline (minus Tesseract call).
2. `test_preprocess_skip_binarization` — verify grayscale (not binary) image returned when `skip_binarization=True`.
3. `test_preprocess_min_channel` — verify min-channel grayscale differs from luminance.
4. `test_preprocess_white_border` — verify output image is 2×pad larger in each dimension.
5. `test_preprocess_unsharp` — verify unsharp mask produces different (sharper) output than no-op.

## Known Limitations

1. **No Tier 2 (SR) in sweep.** The sweep tests preprocessing on Tier 1 images only (150 DPI). A rescued page at Tier 1 means SR was unnecessary; a still-failed page might succeed with SR + new preprocessing, but that combination is not tested. Follow-up: add SR tier to sweep if Tier 1 rescue rate is low.
2. **No EasyOCR.** The sweep uses Tesseract only. EasyOCR has its own preprocessing and is out of scope.
3. **ART_670 dominates.** 686/697 failures are from one PDF. Results may be ART_670-specific. The regression check on diverse PDFs mitigates this.
4. **Single DPI.** Images are captured at 150 DPI. Testing higher DPI would require re-rendering from PDFs, which is out of scope for this harness (uses saved images only).
