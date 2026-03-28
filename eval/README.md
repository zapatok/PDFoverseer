# eval/

Evaluation harness for tuning and benchmarking PDFoverseer's OCR + inference pipeline.
Organized by investigation stage — each subdirectory is a self-contained research area
with its own parameters, sweep runner, results, and postmortem.

## Directory Structure

```
eval/
├── shared/                  # Shared types and loaders used by all stages
│   ├── types.py             # PageRead, Document dataclasses (single source of truth)
│   └── loaders.py           # load_fixtures(), load_ground_truth()
├── inference_tuning/        # Parameter sweep for core/inference.py
│   ├── inference.py         # Parameterized copy of core/inference.py (sweep isolation)
│   ├── params.py            # PARAM_SPACE (search ranges) + PRODUCTION_PARAMS
│   ├── sweep.py             # LHS sample → fine grid → beam search
│   ├── report.py            # Ranked results table
│   ├── baseline_art674.py   # ART_674 VLM baseline runner
│   ├── baseline_art674_tess.py  # ART_674 Tesseract baseline runner
│   ├── results/             # Sweep result JSONs (gitignored)
│   ├── docs/                # Stage-specific documentation
│   └── POSTMORTEM.md        # Sweep history, lessons, production params
├── graph_inference/         # Experimental graph-based inference (HMM + Viterbi)
│   ├── engine.py            # Graph inference engine
│   ├── params.py            # Graph engine parameters
│   ├── sweep.py             # Graph engine sweep
│   ├── hybrid.py            # Hybrid: phases 0-6 + Viterbi global decoder
│   ├── compare.py           # Head-to-head engine comparison
│   ├── results/             # Sweep result JSONs (gitignored)
│   ├── docs/                # Stage-specific documentation
│   └── POSTMORTEM.md        # Why not adopted, residual value
├── ocr_preprocessing/       # OCR image preprocessing sweeps
│   ├── preprocess.py        # Preprocessing pipeline variants
│   ├── params.py            # Preprocessing parameter space
│   ├── sweep.py             # Preprocessing sweep runner
│   ├── report.py            # Preprocessing results
│   ├── results/             # Sweep result JSONs (gitignored)
│   ├── docs/                # Stage-specific documentation
│   └── POSTMORTEM.md        # CLAHE regression, eval-production gap lessons
├── ocr_engines/             # OCR engine benchmarks (EasyOCR, PaddleOCR)
│   ├── benchmark.py         # Engine accuracy benchmark
│   ├── docs/                # Stage-specific documentation
│   └── POSTMORTEM.md        # Why Tesseract wins for this domain
├── tests/                   # Centralized tests for all stages
│   ├── test_inference.py    # Inference engine tests
│   ├── test_sweep_scoring.py # Sweep scoring tests
│   ├── test_graph_inference.py # Graph engine tests
│   ├── test_preprocess.py   # OCR preprocessing tests
│   └── test_benchmark.py    # OCR benchmark tests
├── fixtures/                # Test fixtures + extraction tools
│   ├── real/                # 21 real CRS PDFs — primary benchmark corpus
│   ├── synthetic/           # 13 synthetic edge cases
│   ├── degraded/            # 7 degraded copies (~15-20% OCR failure rate)
│   ├── archived/            # Superseded fixtures
│   ├── ground_truth.json    # Expected document counts per fixture
│   ├── extract_fixtures.py  # Fixture extraction from real PDFs (Tess+SR)
│   └── extract_art674_tess.py # ART_674 Tesseract fixture extraction
```

## Workflow

### Inference Tuning (primary)

```bash
# Extract fixtures (one-time)
python eval/fixtures/extract_fixtures.py

# Run parameter sweep (3 passes: ~500k combos)
python eval/inference_tuning/sweep.py

# Print ranked results
python eval/inference_tuning/report.py
```

### Graph Inference (experimental)

```bash
python eval/graph_inference/sweep.py
python eval/graph_inference/compare.py
```

### OCR Preprocessing

```bash
python eval/ocr_preprocessing/sweep.py
python eval/ocr_preprocessing/report.py
```

### OCR Engine Benchmark

```bash
python eval/ocr_engines/benchmark.py
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
