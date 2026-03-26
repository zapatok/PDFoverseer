# eval/

Parameter sweep harness and evaluation infrastructure. Used to tune `core/inference.py`
parameters against 40 fixtures before porting changes to production.

## Workflow

```
extract_fixtures.py  →  sweep.py  →  report.py
```

1. **extract_fixtures.py** — one-time setup: extracts page-read fixtures from real PDFs
2. **sweep.py** — three-pass search: Latin Hypercube Sampling → fine grid → beam search
3. **report.py** — prints ranked results table from `eval/results/`

## Core Files

| File | Purpose |
|------|---------|
| `inference.py` | Parameterized copy of `core/inference.py` — self-contained for sweep isolation |
| `params.py` | `PARAM_SPACE` (search ranges) + `PRODUCTION_PARAMS` (current sweep2 winners) |
| `ground_truth.json` | Expected document counts per fixture |
| `sweep.py` | LHS sample → fine grid → beam search |
| `report.py` | Ranked results from eval/results/ |
| `extract_fixtures.py` | One-time fixture extraction from real PDFs |
| `ocr_benchmark.py` | OCR accuracy benchmark across tiers |
| `ocr_sweep.py` | OCR preprocessing parameter sweep |
| `compare_engines.py` | Compare inference engines head-to-head |

## Experimental (not production)

| File | Purpose |
|------|---------|
| `graph_inference.py` | Graph-based inference engine (HMM variant) |
| `graph_sweep.py` | Sweep for graph engine |
| `hybrid_inference.py` | Phases 0-6 + Viterbi global decoder — experimental |

## Fixtures

```
fixtures/
├── real/       # 21 real CRS PDFs — primary benchmark corpus
├── synthetic/  # 13 synthetic edge cases
├── degraded/   # 7 degraded copies (~15-20% OCR failure rate)
└── archived/   # Superseded fixtures
```

## Important

`eval/inference.py` is intentionally a separate copy from `core/inference.py`.
Changes to the inference algorithm must be tested in `eval/inference.py` first,
then ported to `core/inference.py` after sweep validation.
