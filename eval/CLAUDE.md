# eval/ — Evaluation Harness

## Running Sweeps

```bash
# Extract fixtures (one-time)
python eval/fixtures/extract_fixtures.py

# Inference tuning (sweeps for the deferred V4 inference path)
python eval/inference_tuning/sweep.py
python eval/inference_tuning/report.py

# Pagination counting benchmark (the production counting engine)
python eval/pagination_count/benchmark.py
python eval/pagination_count/report.py

# OCR preprocessing sweep
python eval/ocr_preprocessing/sweep.py
python eval/ocr_preprocessing/report.py
```

## Fixtures

- `fixtures/real/` — real CRS PDF fixtures (charlas, includes ART_674 + ART_674_tess)
- `fixtures/synthetic/` — synthetic test cases
- `fixtures/degraded/` — degraded copies (~15-20% OCR failure rate)
- `fixtures/ground_truth.json` — Expected document counts per fixture

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `shared/` | Types (PageRead, Document) and loaders — single source of truth |
| `inference_tuning/` | Parameter sweep for `core/inference.py` (the deferred V4 inference path) |
| `pagination_count/` | Prototype + benchmark for the production pagination engine (`core/scanners/utils/pagination_count.py`) |
| `ocr_preprocessing/` | Image preprocessing sweep variants (retained research) |
| `fixtures/` | Test fixtures + extraction tools |
| `tests/` | Centralized tests for all eval stages |

> **Removed 2026-06-21 (pre-master audit):** `graph_inference/` (HMM+Viterbi, not adopted),
> `ocr_engines/` (EasyOCR/PaddleOCR — Tesseract is the sole engine), and `pixel_density/`
> (cover-detection research; lives on the `research/pixel-density` branch). Recoverable from
> git history.
