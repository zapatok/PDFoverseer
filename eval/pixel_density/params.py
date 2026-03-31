"""
Pixel density baseline configurations.

Established via 54-combination sweep on ART_674.pdf (2719 pages, target=674).
Tag: PD_BASELINE (2026-03-31).
"""

# ── Shared rendering parameters ─────────────────────────────────────────────

DPI = 100
GRID = 8

# ── Best Count — production baseline ────────────────────────────────────────
# 675 matches, error=+1, P=0.921, R=0.923, F1=0.922

BEST_COUNT_CONFIG: dict[str, str | float] = {
    "variant": "clahe",
    "score_fn": "min",
    "threshold_method": "percentile",
    "threshold_percentile": 75.2,
}

# ── Best Quality — high precision reference ─────────────────────────────────
# 626 matches, error=-48, P=0.966, R=0.898, F1=0.931 (only 21 FPs)

BEST_QUALITY_CONFIG: dict[str, str | float] = {
    "variant": "clahe",
    "score_fn": "min",
    "threshold_method": "kmeans_k2",
}
