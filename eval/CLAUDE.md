# eval/ — Evaluation Harness

## Running Sweeps

```bash
# Extract fixtures (one-time)
python eval/fixtures/extract_fixtures.py

# Inference tuning (primary workflow)
python eval/inference_tuning/sweep.py
python eval/inference_tuning/report.py

# Graph inference (experimental)
python eval/graph_inference/sweep.py
python eval/graph_inference/compare.py

# OCR preprocessing sweep
python eval/ocr_preprocessing/sweep.py
python eval/ocr_preprocessing/report.py

# OCR engine benchmark
python eval/ocr_engines/benchmark.py

# Pixel density (standalone cover detection, no OCR)
python eval/pixel_density/baseline.py           # full 54-combo sweep
python eval/pixel_density/inspect_pages.py            # 3-way diff vs Tesseract
python eval/pixel_density/inspect_pages.py --diagnose # per-page score table
python eval/pixel_density/audit_coverage.py     # pipeline cross-reference
python eval/pixel_density/characterize_density.py --bimodality  # density regimes
```

## Fixtures

- `fixtures/real/` — 22 real fixtures (charlas CRS, includes ART_674 + ART_674_tess)
- `fixtures/synthetic/` — 15 synthetic test cases
- `fixtures/degraded/` — 7 degraded copies (~15-20% OCR failure rate)
- `fixtures/ground_truth.json` — Expected document counts per fixture

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `shared/` | Types (PageRead, Document) and loaders — single source of truth |
| `inference_tuning/` | Parameter sweep for `core/inference.py` (LHS → fine grid → beam) |
| `graph_inference/` | Experimental HMM + Viterbi graph-based inference |
| `ocr_preprocessing/` | Image preprocessing sweep variants |
| `ocr_engines/` | OCR engine benchmarks (EasyOCR, PaddleOCR) |
| `pixel_density/` | Bilateral pixel density cover detection (no OCR). See `pixel_density/README.md` |
| `tests/` | Centralized tests for all eval stages |
