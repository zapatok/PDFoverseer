"""
Pixel density configurations.

PD_BASELINE (2026-03-31): 54-combination sweep on ART_674.pdf, dark_ratio L2 bilateral.
PD_V2 (2026-04-01): Multi-descriptor bilateral (dark_ratio + edge_density, robust-z).
PD_V2_RESCUE (2026-04-01): V2 features + V1 threshold — generalizes across 27 PDFs.
"""

# ── Shared rendering parameters ─────────────────────────────────────────────

DPI = 100
GRID = 8

# ── V1: Best Count — production baseline (PD_BASELINE) ─────────────────────
# 675 matches, error=+1, P=0.921, R=0.923, F1=0.922

BEST_COUNT_CONFIG: dict[str, str | float] = {
    "variant": "clahe",
    "score_fn": "min",
    "threshold_method": "percentile",
    "threshold_percentile": 75.2,
}

# ── V1: Best Quality — high precision reference (PD_BASELINE) ──────────────
# 626 matches, error=-48, P=0.966, R=0.898, F1=0.931 (only 21 FPs)

BEST_QUALITY_CONFIG: dict[str, str | float] = {
    "variant": "clahe",
    "score_fn": "min",
    "threshold_method": "kmeans_k2",
}

# ── V2: Multi-descriptor bilateral (PD_V2) — SUPERSEDED by V2_RESCUE ──────
# Overfits to ART_674 (KMeans threshold). Kept for reference only.
# F1=0.957 on ART_674 but MAE=22.4 on cross-validation (worse than V1).

BEST_MULTIDESC_CONFIG: dict = {
    "features": ["dark_ratio_grid", "edge_density_grid"],
    "normalization": "robust_z",
    "score_fn": "min",
    "threshold_method": "kmeans_k2",
}

# ── V2 Rescue: Multi-descriptor + V1 threshold (PD_V2_RESCUE) ─────────────
# Cross-validated on 27 PDFs: MAE=20.1 general (same as V1), 0.0 ART family.
# ART_674 page-level: F1=0.956, P=0.956, R=0.957, TESS-ONLY=26/27.
#
# Same features and normalization as V2, but percentile 75.2 instead of
# KMeans — eliminates overfitting while preserving accuracy gains.

BEST_RESCUE_CONFIG: dict = {
    "features": ["dark_ratio_grid", "edge_density_grid"],
    "normalization": "robust_z",
    "score_fn": "min",
    "threshold_method": "percentile",
    "threshold_percentile": 75.2,
}

# ── find_peaks: Peak detection for ART documents (PD_FIND_PEAKS) ─────────
# Uses scipy.signal.find_peaks on bilateral score signal instead of
# percentile threshold. Detects pages that genuinely stand out from
# neighbors — no fixed cover ratio assumption.
#
# Three-stage pipeline:
#   1. find_peaks (prominence + distance): detect bilateral score peaks
#   2. Cover-shift (similarity): correct off-by-one displacement at boundaries
#   3. Template rescue (threshold): recover covers similar to confirmed ones
#
# ART_674 page-level: F1=0.996, P=0.996, R=0.996, 3 FP, 3 FN, 674 docs (exact).
# ART family (6 PDFs total): 6/6 exact, MAE=0.0.

BEST_FIND_PEAKS_CONFIG: dict = {
    "features": ["dark_ratio_grid", "edge_density_grid"],
    "normalization": "robust_z",
    "score_fn": "min",
    "threshold_method": "find_peaks",
    "prominence": 0.5,
    "distance": 2,
    "shift_covers": True,
    "score_similarity": 0.99,
    "rescue_threshold": 0.40,
}
