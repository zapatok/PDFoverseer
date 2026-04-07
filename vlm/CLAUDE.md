# vlm/ — Vision-Language Model Module

Benchmark and sweep module for comparing VLM-based OCR against Tesseract pipeline.

## Commands

```bash
# Run VLM as module
python -m vlm

# Run VLM benchmark
python vlm/benchmark.py

# Run VLM sweep
python vlm/sweep.py
```

## Status

VLM pre-inference tier was **attempted and reverted** (2026-03-30). The s2t-helena baseline was restored.
See `docs/superpowers/reports/2026-03-29-vlm-integration-postmortem.md` for details.

## Files

- `client.py` — VLM API client
- `parser.py` — VLM response parser
- `preprocess.py` — Image preprocessing for VLM
- `benchmark.py` — VLM benchmark runner
- `ground_truth.py` — Ground truth management
- `sweep.py` — VLM parameter sweep
- `params.py` — VLM sweep parameters
- `report.py` — VLM results reporter
- `results/` — Sweep results (gitignored)
