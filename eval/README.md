# eval/

Evaluation harness for tuning and benchmarking PDFoverseer's OCR + inference pipeline.
Organized by investigation stage — each subdirectory is a self-contained research area
with its own parameters, sweep runner, results, and (where relevant) a postmortem.

## Directory Structure

```
eval/
├── shared/                  # Shared types and loaders used by all stages
│   ├── types.py             # PageRead, Document dataclasses (single source of truth)
│   └── loaders.py           # load_fixtures(), load_ground_truth()
├── inference_tuning/        # Parameter sweep for core/inference.py (deferred V4 path)
│   ├── inference.py         # Parameterized copy of core/inference.py (sweep isolation)
│   ├── params.py            # PARAM_SPACE (search ranges) + PRODUCTION_PARAMS
│   ├── sweep.py             # LHS sample → fine grid → beam search
│   ├── report.py            # Ranked results table
│   ├── baseline_art674.py   # ART_674 VLM baseline runner
│   ├── baseline_art674_tess.py  # ART_674 Tesseract baseline runner
│   ├── results/             # Sweep result JSONs (gitignored)
│   ├── docs/                # Stage-specific documentation
│   └── POSTMORTEM.md        # Sweep history, lessons, production params
├── pagination_count/        # Pagination-first counting engine (the production engine)
│   ├── engine.py            # Prototype of core/scanners/utils/pagination_count.py
│   ├── samples.py           # Hand-labeled Sample fixtures
│   ├── benchmark.py         # Anchors vs pagination benchmark on real corpus
│   ├── report.py            # MIGRATE/KEEP verdict per sigla
│   └── results/             # Benchmark result JSONs (gitignored)
├── ocr_preprocessing/       # OCR image preprocessing sweeps (retained research)
│   ├── preprocess.py        # Preprocessing pipeline variants
│   ├── params.py            # Preprocessing parameter space
│   ├── sweep.py             # Preprocessing sweep runner
│   ├── report.py            # Preprocessing results
│   ├── results/             # Sweep result JSONs (gitignored)
│   ├── docs/                # Stage-specific documentation
│   └── POSTMORTEM.md        # CLAHE regression, eval-production gap lessons
├── tests/                   # Centralized tests for all stages
│   ├── test_inference.py    # Inference engine tests
│   ├── test_sweep_scoring.py # Sweep scoring tests
│   ├── test_pagination_engine.py   # Pagination engine pure-function tests
│   ├── test_pagination_benchmark.py # Pagination benchmark harness tests
│   └── test_ocr_preprocess.py # OCR preprocessing tests
├── fixtures/                # Test fixtures + extraction tools
│   ├── real/                # Real CRS PDF fixtures — primary benchmark corpus
│   ├── synthetic/           # Synthetic edge cases
│   ├── degraded/            # Degraded copies (~15-20% OCR failure rate)
│   ├── archived/            # Superseded fixtures
│   ├── ground_truth.json    # Expected document counts per fixture
│   ├── extract_fixtures.py  # Fixture extraction from real PDFs (Tess+SR)
│   └── extract_art674_tess.py # ART_674 Tesseract fixture extraction
```

> **Removed 2026-06-21 (pre-master audit):** the shelved experiments `graph_inference/`
> (HMM+Viterbi, not adopted), `ocr_engines/` (EasyOCR/PaddleOCR benchmark — Tesseract is the
> sole engine), and `pixel_density/` (cover-detection research, lives on the
> `research/pixel-density` branch) were deleted from `po_overhaul`. Recoverable from git
> history if needed.

## Workflow

### Inference Tuning (sweeps for the deferred V4 inference path)

```bash
# Extract fixtures (one-time)
python eval/fixtures/extract_fixtures.py

# Run parameter sweep (3 passes)
python eval/inference_tuning/sweep.py

# Print ranked results
python eval/inference_tuning/report.py
```

### Pagination counting benchmark (the production engine)

```bash
python eval/pagination_count/benchmark.py   # anchors vs pagination on the real corpus
python eval/pagination_count/report.py      # per-sigla MIGRATE/KEEP verdict
```

### OCR Preprocessing

```bash
python eval/ocr_preprocessing/sweep.py
python eval/ocr_preprocessing/report.py
```

## Shared Code

`eval/shared/` contains types and loaders used by all stages:

- **`types.py`** — `PageRead` and `Document` dataclasses. Single source of truth;
  all stages import from here instead of defining their own copies.
- **`loaders.py`** — `load_fixtures()` and `load_ground_truth()` functions.
  Reads from `eval/fixtures/` and `eval/fixtures/ground_truth.json`.

## Important

`eval/inference_tuning/inference.py` is intentionally a separate copy from `core/inference.py`.
Changes to the inference algorithm must be tested in eval first, then ported to core after
sweep validation. See the `eval-before-core` hookify rule.
