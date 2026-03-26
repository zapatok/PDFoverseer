# vlm/

Vision-Language Model evaluation module. Benchmarks VLM accuracy on OCR-failed pages
and sweeps preprocessing parameters.

**Status:** Benchmark infrastructure complete. VLM resolver (post-inference selective
re-inference using VLM reads) is designed but not yet implemented.
See: `docs/superpowers/specs/2026-03-25-vlm-resolver-design.md`

## Usage

```bash
# Run interactive benchmark
python -m vlm

# Run full benchmark
python vlm/benchmark.py

# Run parameter sweep
python vlm/sweep.py
```

## Modules

| File | Purpose |
|------|---------|
| `client.py` | VLM API client — sends page image, receives text response |
| `parser.py` | Parse VLM response into (curr, total) tuple |
| `preprocess.py` | Image preprocessing before sending to VLM |
| `benchmark.py` | Run VLM on fixture pages, record hit/miss/none |
| `ground_truth.py` | Load and manage ground truth for VLM pages |
| `sweep.py` | Sweep preprocessing parameters for VLM |
| `params.py` | VLM sweep parameter space |
| `report.py` | Print benchmark results summary |
| `results/` | Output directory (gitignored) |

## Background

VLM achieves 79-89% accuracy on OCR-failed pages. Naive filling of all VLM reads
into inference worsens overall accuracy by ~7pp because low-confidence VLM reads
introduce noise. The VLM resolver (pending) is designed to fix this via selective,
context-validated replacement.
