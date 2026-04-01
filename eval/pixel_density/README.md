# Pixel Density — Document Cover Detection Without OCR

Detects document first pages by analyzing pixel darkness patterns across neighboring pages. No OCR required — works purely on rendered page images.

## How It Works

1. Render each page as grayscale at low DPI (100)
2. Split into 8x8 grid of tiles, compute dark pixel fraction per tile (64-dim vector)
3. Compute L2 distance to both neighbors → bilateral score (harmonic mean or min)
4. Classify via K-Means or percentile threshold into cover vs non-cover

## Baseline (PD_BASELINE, 2026-03-31)

Configs defined in `params.py`:

| Config | Matches | Error | Precision | Recall | F1 |
|--------|---------|-------|-----------|--------|-----|
| **Best Count** (CLAHE/min/pct75.2) | 675 | +1 | 0.921 | 0.923 | 0.922 |
| **Best Quality** (CLAHE/min/kmeans_k2) | 626 | -48 | 0.966 | 0.898 | 0.931 |

## Files

| File | Purpose | Usage |
|------|---------|-------|
| `pixel_density.py` | Core: rendering, dark_ratio, grid, L2 distance, clustering | Library — imported by all other scripts |
| `params.py` | Baseline configs: `BEST_COUNT_CONFIG`, `BEST_QUALITY_CONFIG` | Reference constants |
| `sweep_bilateral.py` | Bilateral score computation + K-Means classification | `python eval/pixel_density/sweep_bilateral.py data/samples/ART_674.pdf --target 674` |
| `sweep_preprocessing.py` | 8 preprocessing variants (CLAHE, Otsu, ink, red channel) | `python eval/pixel_density/sweep_preprocessing.py` |
| `baseline.py` | Full 54-combo standalone sweep + VLM evaluation | `python eval/pixel_density/baseline.py` |
| `inspect_pages.py` | 3-way diff (bilateral vs Tesseract) + score diagnostics | `python eval/pixel_density/inspect_pages.py [--diagnose]` |
| `audit_coverage.py` | Cross-reference bilateral pages vs inference pipeline + VLM GT | `python eval/pixel_density/audit_coverage.py` |
| `characterize_density.py` | Density regime analysis + bimodality check | `python eval/pixel_density/characterize_density.py [--bimodality]` |
| `simulate_injection.py` | Realistic injection simulation (correct totals from VLM GT) | `python eval/pixel_density/simulate_injection.py` |
| `simulate_naive.py` | Naive injection simulation (total=1, all bilateral-only) | `python eval/pixel_density/simulate_naive.py` |
| `extract_pages.py` | Extract PNG strips for visual inspection of bilateral/tess pages | `python eval/pixel_density/extract_pages.py` |

## Key Research Findings (2026-03-31)

- Pipeline integration rejected — injecting bilateral covers fragments correctly-assembled documents
- No density segments in ART_674 — local K-Means = global K-Means
- CLAHE + min score is the best combo — CLAHE enhances contrast, min acts as strict AND gate
- Ink-only / continuous darkness variants tested, no improvement over CLAHE binary
- Full report: `docs/research/2026-03-31-bilateral-pixel-density.md`
