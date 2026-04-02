# Pixel Density — Document Cover Detection Without OCR

Detects document first pages by analyzing pixel darkness patterns across neighboring pages. No OCR required — works purely on rendered page images.

## How It Works

1. Render each page as grayscale at low DPI (100)
2. Extract feature vector(s) per page (dark_ratio grid, edge density grid, etc.)
3. Compute L2 distance to both neighbors — bilateral score (min aggregation)
4. Classify via percentile threshold (top ~25% = cover pages)

## Configurations (in `params.py`)

### Current Best: PD_V2_RC (2026-04-01)

Multi-descriptor bilateral with percentile threshold. Cross-validated on 27 PDFs.

```
features:      dark_ratio_grid (8x8, 64d) + edge_density_grid (4x4, 16d)
normalization: robust-z (median + MAD * 1.4826)
distance:      L2 bilateral, min scoring
threshold:     percentile 75.2
```

| Metric | Value |
|--------|-------|
| ART_674 F1 (page-level) | **0.956** |
| ART_674 TESS-ONLY recovered | 26/27 |
| General corpus MAE (22 PDFs) | 16.4 |
| ART family exact matches | 5/5 |

### V1 Baseline: PD_BASELINE (2026-03-31)

Single-feature dark_ratio with CLAHE preprocessing.

| Config | Matches | Error | F1 |
|--------|---------|-------|----|
| **Best Count** (CLAHE/min/pct75.2) | 675 | +1 | 0.922 |
| **Best Quality** (CLAHE/min/kmeans_k2) | 626 | -48 | 0.931 |

## Pipeline

The detection pipeline for PD_V2_RC works as follows:

```
PDF ──► Render all pages (DPI=100, grayscale)
         │
         ├── dark_ratio_grid: 8x8 grid, dark pixel fraction per tile (64 dims)
         │
         ├── edge_density_grid: 4x4 grid, Canny edge fraction per tile (16 dims)
         │
         ├── Concatenate ──► 80-dim vector per page
         │
         ├── Robust Z-score normalize (median + MAD across all pages)
         │
         ├── Bilateral L2: distance to left + right neighbor, take min
         │
         └── Percentile 75.2 threshold ──► cover page indices
```

## Files

| File | Purpose | Usage |
|------|---------|-------|
| `pixel_density.py` | Core: rendering, dark_ratio, grid, L2 distance, clustering | Library |
| `params.py` | All configs: `BEST_RESCUE_CONFIG` (current), `BEST_COUNT_CONFIG` (V1) | Reference constants |
| `features.py` | 7 feature extractors + registry | Library |
| `metrics.py` | Chi², bilateral_scores, L2/chi² shortcuts | Library |
| `cache.py` | Disk cache for rendered page arrays | Library |
| `evaluate.py` | Shared GT loading, metrics, reporting | Library |
| `sweep_rescue.py` | Rescue sweep: 4 scorers × 27 PDFs cross-validation | `python eval/pixel_density/sweep_rescue.py` |
| `sweep_bilateral.py` | Bilateral score computation + K-Means classification | `python eval/pixel_density/sweep_bilateral.py` |
| `sweep_preprocessing.py` | 10 preprocessing variants | `python eval/pixel_density/sweep_preprocessing.py` |
| `sweep_chi2.py` | Phase 1: chi² histogram bilateral sweep (84 combos) | `python eval/pixel_density/sweep_chi2.py` |
| `sweep_multidesc.py` | Phase 3: multi-descriptor bilateral (Stage A+B) | `python eval/pixel_density/sweep_multidesc.py` |
| `sweep_combine.py` | Phase 4: signal fusion/voting/set ops | `python eval/pixel_density/sweep_combine.py` |
| `baseline.py` | Full 54-combo standalone sweep + VLM evaluation | `python eval/pixel_density/baseline.py` |
| `inspect_pages.py` | 3-way diff (bilateral vs Tesseract) + score diagnostics | `python eval/pixel_density/inspect_pages.py` |
| `audit_coverage.py` | Cross-reference bilateral pages vs inference pipeline + VLM GT | `python eval/pixel_density/audit_coverage.py` |
| `characterize_density.py` | Density regime analysis + bimodality check | `python eval/pixel_density/characterize_density.py` |
| `simulate_injection.py` | Realistic injection simulation | `python eval/pixel_density/simulate_injection.py` |
| `simulate_naive.py` | Naive injection simulation | `python eval/pixel_density/simulate_naive.py` |
| `extract_pages.py` | Extract PNG strips for visual inspection | `python eval/pixel_density/extract_pages.py` |
| `analyze_errors.py` | FP/FN diagnostic: scores, positions, neighbor context | `python eval/pixel_density/analyze_errors.py --render` |
| `sweep_v3.py` | V3 sweep: floor + consecutive suppression (18 combos) | `python eval/pixel_density/sweep_v3.py` |
| `sweep_find_peaks.py` | find_peaks prominence sweep on ART family | `python eval/pixel_density/sweep_find_peaks.py` |
| `sweep_template_rescue.py` | Template rescue threshold sweep on ART family | `python eval/pixel_density/sweep_template_rescue.py` |

## Research History

1. **PD_BASELINE** (2026-03-31): 54-combo sweep, dark_ratio L2 bilateral. Report: `docs/research/2026-03-31-bilateral-pixel-density.md`
2. **PD_V2** (2026-04-01): Multi-descriptor + KMeans. F1=0.957 on ART_674 but failed cross-validation (overfit). **Superseded.**
3. **PD_V2_RC** (2026-04-01): V2 features + V1 threshold. F1=0.956, generalizes. Report: `docs/research/2026-04-01-pixel-density-advanced-sweep-results.md`
4. **PD_V3 Error Analysis** (2026-04-01): FP/FN diagnosis + absolute floor + consecutive suppression. Floor has no effect on ART_674 (FPs have genuinely high scores). Suppress reduces FP 30→3 but regresses gen_MAE 20.1→29.7. **V2_RC remains best for general use.** Report: `docs/research/2026-04-01-pd-v3-error-analysis.md`
5. **PD_FIND_PEAKS** (2026-04-01): `scipy.signal.find_peaks` + cover-shift + template rescue. Three-stage pipeline: peak detection, displacement correction, similarity rescue. F1=0.996 on ART_674, **6/6 ART exact (MAE=0.0)**. Report: `docs/research/2026-04-01-pd-v3-error-analysis.md`

Key findings:
- The percentile threshold (75.2) is what makes configs generalize. KMeans k=2 overfits to each PDF's score distribution.
- FPs on ART_674 are structural (document boundary pairs) — not fixable by score filtering.
- Consecutive suppression works for ART but breaks short-document PDFs.
- **find_peaks detects structure, not ratios** — no 25% assumption, fixes single-document problem.
