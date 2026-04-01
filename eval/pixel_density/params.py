"""
Pixel density configurations.

PD_BASELINE (2026-03-31): 54-combination sweep on ART_674.pdf, dark_ratio L2 bilateral.
PD_V2 (2026-04-01): Multi-descriptor bilateral (dark_ratio + edge_density, robust-z).
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

# ── V2: Multi-descriptor bilateral (PD_V2) ─────────────────────────────────
# 648 matches, error=-26, P=0.952, R=0.961, F1=0.957, TESS-ONLY=26/27
# Fusion variant: F1=0.959 (90% multidesc + 10% bilateral L2)
#
# Combines dark_ratio_grid (ink density, 64 dims) with edge_density_grid
# (layout structure, 16 dims) after robust z-score normalization. L2 bilateral
# with min scoring, KMeans k=2 thresholding.

BEST_MULTIDESC_CONFIG: dict = {
    "features": ["dark_ratio_grid", "edge_density_grid"],
    "normalization": "robust_z",
    "score_fn": "min",
    "threshold_method": "kmeans_k2",
}
