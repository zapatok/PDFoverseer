# OCR Engine Benchmark: EasyOCR vs PaddleOCR

**Date:** 2026-03-23
**Branch:** `cuda-gpu`
**Goal:** Compare Tesseract, EasyOCR, and PaddleOCR on real PDFs to determine whether migrating the GPU consumer fallback from EasyOCR to PaddleOCR is worthwhile.

---

## Motivation

The V4 pipeline GPU consumer uses EasyOCR as a last-resort fallback after Tesseract Tier 1 and Tier 2 fail. PaddleOCR is reported to be 2–3x faster and potentially more accurate on degraded text. This benchmark measures both claims on real data before committing to a migration.

**Expected outcomes:**
- EasyOCR is already at or near 100% on most PDFs — accuracy gains will likely be small.
- The most valuable signal is whether PaddleOCR recovers any of the 49 pages that both Tesseract and EasyOCR have historically failed.
- Speed improvement in the GPU consumer is a secondary gain.

---

## Scope

**PDFs tested:** 6 real PDFs from `data/samples/` (ART_HLL_674 excluded — too large for benchmark):

| PDF | Pages | Docs |
|-----|-------|------|
| CH_9docs.pdf | 17 | 9 |
| CH_39docs.pdf | 78 | 39 |
| CH_51docs.pdf | 102 | 51 |
| CH_74docs.pdf | 150 | 74 |
| HLL_363docs.pdf | 538 | 363 |
| INS_31.pdf.pdf | 31 | 31 |
| **Total** | **916** | — |

**Ground truth:** `eval/fixtures/real/*.json` — fixture files from prior pipeline runs.
- 867 pages with known `curr/total` (method = `direct`, `SR`, or `easyocr`) → used for accuracy scoring.
- 49 pages with method = `failed` → no known ground truth; reported separately as potential recoveries.

**Note on EasyOCR self-reference:** 80 of the 867 scoreable pages have `method="easyocr"` in the fixture, meaning EasyOCR is scored against its own prior output on those pages. This is a minor circular dependency. The console output reports accuracy separately for the `direct`/`SR` subset (836 pages) to provide a clean baseline.

---

## Architecture

### Script: `eval/ocr_benchmark.py`

**Phase 1 — Crop extraction**

For every page in each PDF:
- Render **two** crops per page to match production DPI per engine:
  - 150 DPI crop (for Tesseract — matches production `DPI = 150`)
  - 300 DPI crop (for EasyOCR and PaddleOCR — matches `EASYOCR_DPI = 300`)
- Save 300 DPI crops to `data/benchmark_crops/<pdf_stem>/page_<NNN>.png` for visual inspection.
- Hold both crops in memory as parallel lists.

**Phase 2 — Engine passes (sequential)**

Engines run one at a time to avoid GPU memory conflicts between PyTorch (EasyOCR) and PaddlePaddle (PaddleOCR). One warm-up page is run before timing begins for each GPU engine.

Timing covers the OCR call only (not `_parse()`), measured with `time.perf_counter()`.

1. **Tesseract** (CPU, 150 DPI) — calls `ocr._tess_ocr(bgr_150)` directly. Tier 1 only — no super-resolution pass. This reflects the baseline Tesseract capability, not the full two-tier pipeline.
2. **EasyOCR** (GPU, 300 DPI) — init `easyocr.Reader(["es","en"], gpu=True)`, warm up on page 0, process all crops via `reader.readtext(gray, detail=0, paragraph=True)`, then `del reader` + `torch.cuda.empty_cache()`.
3. **PaddleOCR** (GPU, 300 DPI) — init `PaddleOCR(use_angle_cls=False, lang="en", use_gpu=True, show_log=False)`, warm up on page 0, process all crops via `reader.ocr(img, cls=False)`, extract text from nested result `[[bbox, (text, conf)], ...]` by joining all `text` values, then `del reader` + paddle memory release.

Text output from each engine is passed to `_parse()` (returns `curr, total` or `None, None`).

**Phase 3 — Scoring and output**

For each page, compare `curr/total` against the fixture ground truth:
- Match → hit
- Mismatch or None → miss
- `failed` fixture page → excluded from scoring, tracked separately

### Output

**Console — summary table:**
```
PDF         Pages  Scoreable  Tesseract(150)  EasyOCR(300)   PaddleOCR(300)
CH_9           17         17  16 (94%)        16 (94%)       ? (?%)
CH_39          78         77  73 (95%)        76 (99%)       ? (?%)
CH_51         102        101  96 (95%)       101 (100%)      ? (?%)
CH_74         150        145 139 (96%)       145 (100%)      ? (?%)
HLL           538        503 489 (97%)       503 (100%)      ? (?%)
INS_31         31         24  17 (71%)        24 (100%)      ? (?%)
─────────────────────────────────────────────────────────────────────────
TOTAL         916        867  ...             ...             ...

Clean ground truth (direct+SR only, 836 pages):
  Tesseract: ?/?  EasyOCR: ?/?  PaddleOCR: ?/?

Timing (ms/page, GPU warm-up excluded):
  Tesseract: ?ms   EasyOCR: ?ms   PaddleOCR: ?ms

Potential recoveries (failed pages where PaddleOCR found something):
  HLL p47: 3/8   INS_31 p7: 2/5   ...
```

**JSON — `data/benchmark_results.json`:**
```json
{
  "pdfs": [
    {
      "name": "CH_9",
      "pages": [
        {
          "pdf_page": 1,
          "fixture_method": "direct",
          "ground_truth": {"curr": 1, "total": 2},
          "tesseract":  {"curr": 1, "total": 2, "ms": 42},
          "easyocr":    {"curr": 1, "total": 2, "ms": 81},
          "paddleocr":  {"curr": 1, "total": 2, "ms": 28}
        }
      ]
    }
  ]
}
```

---

## Installation

PaddleOCR is installed into the existing `.venv-cuda` alongside PyTorch. They can coexist when run sequentially (not simultaneously in GPU memory).

```bash
# Activate venv first
source .venv-cuda/Scripts/activate

pip install paddlepaddle-gpu==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
pip install paddleocr
```

**Fallback:** If PaddlePaddle GPU conflicts with PyTorch, install CPU-only `paddlepaddle`. Accuracy comparison remains valid; speed comparison will not reflect GPU performance.

`requirements-gpu.txt` is **not modified** — this is an experimental benchmark on the `cuda-gpu` branch only.

---

## Decision Criteria

| Result | Action |
|--------|--------|
| PaddleOCR recovers ≥5 of the 49 failed pages AND no regressions on scoreable pages | Migrate GPU consumer to PaddleOCR |
| PaddleOCR faster but same accuracy (recovers <5 failed pages) | Consider migration for speed gain only |
| PaddleOCR has regressions on previously passing pages | Stay with EasyOCR |
| Install fails or GPU memory conflicts | Abort migration, document findings |

---

## Files Changed

| File | Change |
|------|--------|
| `eval/ocr_benchmark.py` | New — benchmark script |
| `data/benchmark_crops/` | New — extracted page crops (gitignored) |
| `data/benchmark_results.json` | New — results per page (gitignored) |
