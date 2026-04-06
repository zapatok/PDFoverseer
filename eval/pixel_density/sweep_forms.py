"""Scorer for form-based PDFs — page classification by vertical density.

Classifies each page as cover/non-cover using vertical ink distribution.
Independent from bilateral scorers (scorer_find_peaks, scorer_rescue_c).

Usage
-----
    python eval/pixel_density/sweep_forms.py          # full sweep
    python eval/pixel_density/sweep_forms.py --quick   # HLL_363 only
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np  # noqa: E402
from scipy.stats import kurtosis, skew  # noqa: E402


# ── Threshold utilities ───────────────────────────────────────────────────


def otsu_threshold_1d(data: np.ndarray, n_bins: int = 256) -> float:
    """Otsu's method on a 1-D float array.

    Finds the threshold that maximizes between-class variance. Equivalent to
    cv2.threshold(THRESH_OTSU) but operates on arbitrary float arrays.

    Args:
        data: 1-D array of float values.
        n_bins: Number of histogram bins.

    Returns:
        Optimal threshold value.
    """
    lo, hi = float(data.min()), float(data.max())
    if hi - lo < 1e-12:
        return lo

    hist, bin_edges = np.histogram(data, bins=n_bins, range=(lo, hi))
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0
    hist_norm = hist.astype(np.float64) / hist.sum()

    best_thresh = lo
    best_var = -1.0

    cum_w = 0.0
    cum_sum = 0.0
    total_sum = float((hist_norm * bin_centers).sum())

    for i in range(n_bins):
        cum_w += hist_norm[i]
        cum_sum += hist_norm[i] * bin_centers[i]

        if cum_w < 1e-12 or (1.0 - cum_w) < 1e-12:
            continue

        mean_bg = cum_sum / cum_w
        mean_fg = (total_sum - cum_sum) / (1.0 - cum_w)

        var_between = cum_w * (1.0 - cum_w) * (mean_bg - mean_fg) ** 2

        if var_between > best_var:
            best_var = var_between
            best_thresh = bin_centers[i]

    return best_thresh


def bimodal_coefficient(data: np.ndarray) -> float:
    """Bimodal coefficient (BC) for a 1-D array.

    BC = (skewness^2 + 1) / kurtosis_excess_plus_3.
    BC >= 5/9 (0.555) suggests bimodality.

    Args:
        data: 1-D array of float values.

    Returns:
        Bimodal coefficient. Returns 0.0 for constant arrays.
    """
    if len(data) < 4 or data.std() < 1e-12:
        return 0.0

    s = float(skew(data))
    # scipy kurtosis() returns excess kurtosis by default; we need regular kurtosis
    k = float(kurtosis(data, fisher=True)) + 3.0

    if k < 1e-12:
        return 0.0

    return (s ** 2 + 1.0) / k
