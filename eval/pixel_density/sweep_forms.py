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


# ── Scorer ────────────────────────────────────────────────────────────────

from eval.pixel_density.features import feat_vertical_density  # noqa: E402


def scorer_forms(
    pages: np.ndarray,
    bottom_frac: float = 0.35,
    signal: str = "bot_top_ratio",
    threshold_method: str = "otsu",
    _vd_precomputed: np.ndarray | None = None,
) -> list[int]:
    """Classify pages as cover/non-cover by vertical ink distribution.

    Designed for form-based PDFs (e.g., HLL_363) where bilateral scoring fails
    due to visual uniformity across all pages.

    Args:
        pages: Array of shape (N, H, W), uint8 grayscale pages.
        bottom_frac: Fraction of page height for the bottom zone.
        signal: Discriminant signal to compute per page. One of:
            "bot_top_ratio", "bot_absolute", "bot_full_ratio", "bot_mid_ratio".
        threshold_method: Separation method. One of:
            "otsu", "kmeans_k2", "percentile_<N>" (e.g. "percentile_50").
        _vd_precomputed: Optional pre-computed vertical density array of shape
            (N, 2) from feat_vertical_density. Used by sweep to avoid redundant
            extraction. If None, features are extracted internally.

    Returns:
        Sorted list of 0-based page indices classified as covers.
    """
    n = pages.shape[0]
    if n <= 1:
        return [0]

    # Extract vertical density for all pages (or use pre-computed cache)
    if _vd_precomputed is not None:
        vd = _vd_precomputed
    else:
        vd = np.array([feat_vertical_density(pages[i], bottom_frac) for i in range(n)])
    top_dark = vd[:, 0]
    bot_dark = vd[:, 1]

    # Compute discriminant signal
    if signal == "bot_top_ratio":
        values = bot_dark / np.maximum(top_dark, 1e-9)
    elif signal == "bot_absolute":
        values = bot_dark
    elif signal == "bot_full_ratio":
        full_dark = np.array([float((pages[i] < 128).mean()) for i in range(n)])
        values = bot_dark / np.maximum(full_dark, 1e-9)
    elif signal == "bot_mid_ratio":
        # 3-zone split: top=[0, bf*h), mid=[bf*h, (1-bf)*h), bot=[(1-bf)*h, h)
        # Note: top_dark from feat_vertical_density is NOT used here — the zones
        # are redefined symmetrically around the center of the page.
        # At bf=0.40, mid is only 20% of page height — narrow but still meaningful.
        top_frac = 1.0 - bottom_frac
        mid_frac = top_frac - bottom_frac if top_frac > bottom_frac else 0.0
        if mid_frac < 0.05:
            # No meaningful mid zone (bf >= ~0.475) — skip this combo entirely.
            # Returning [0] signals "not applicable" so the sweep can exclude it.
            return [0]
        h = pages.shape[1]
        top_end = int(h * bottom_frac)
        mid_start = top_end
        mid_end = int(h * (1.0 - bottom_frac))
        mid_dark = np.array([
            float((pages[i, mid_start:mid_end, :] < 128).mean())
            if mid_end > mid_start else 0.0
            for i in range(n)
        ])
        values = bot_dark / np.maximum(mid_dark, 1e-9)
    else:
        raise ValueError(f"Unknown signal: {signal!r}")

    # Apply threshold
    # NOTE on percentile convention: the existing _percentile_threshold (sweep_rescue.py)
    # uses pct=75.2 meaning "take pages >= 75.2th percentile" = top 24.8%.
    # Here, percentile_N means "classify top N% as covers" — OPPOSITE convention.
    # This is intentional: bilateral scoring assumes few covers (25%), page
    # classification can have any ratio (HLL has 67.5%).
    if threshold_method == "otsu":
        bc = bimodal_coefficient(values)
        if bc < 0.555:
            return [0]
        thresh = otsu_threshold_1d(values)
        matches = [i for i in range(n) if values[i] >= thresh]
    elif threshold_method == "kmeans_k2":
        import warnings

        from sklearn.cluster import KMeans

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            km = KMeans(n_clusters=2, random_state=42, n_init="auto").fit(
                values.reshape(-1, 1)
            )
        labels = km.labels_
        centers = km.cluster_centers_.flatten()
        high_label = 0 if centers[0] > centers[1] else 1
        matches = [i for i in range(n) if labels[i] == high_label]
    elif threshold_method.startswith("percentile_"):
        # percentile_N = top N% of pages classified as covers
        # e.g. percentile_50 → np.percentile(values, 50) → top 50% are covers
        pct = float(threshold_method.split("_", 1)[1])
        thresh = np.percentile(values, 100.0 - pct)
        matches = [i for i in range(n) if values[i] >= thresh]
    else:
        raise ValueError(f"Unknown threshold_method: {threshold_method!r}")

    if 0 not in matches:
        matches.insert(0, 0)

    return sorted(matches)
