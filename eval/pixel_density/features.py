"""Feature extractors for pixel density analysis.

Each function takes a grayscale image (H x W, uint8) and returns a 1-D numpy
vector. All are pure functions with no side effects.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np


def feat_dark_ratio_grid(img: np.ndarray, grid_n: int = 8) -> np.ndarray:
    """Dark pixel fraction per tile in an NxN grid.

    Args:
        img: Grayscale image (H, W), uint8.
        grid_n: Grid subdivisions per axis.

    Returns:
        1-D array of shape (grid_n**2,), float64.
    """
    h, w = img.shape[:2]
    result = np.empty(grid_n * grid_n, dtype=np.float64)
    for row in range(grid_n):
        r0, r1 = (row * h) // grid_n, ((row + 1) * h) // grid_n
        for col in range(grid_n):
            c0, c1 = (col * w) // grid_n, ((col + 1) * w) // grid_n
            tile = img[r0:r1, c0:c1]
            result[row * grid_n + col] = (
                float((tile < 128).mean()) if tile.size else 0.0
            )
    return result


def feat_histogram(img: np.ndarray, bins: int = 32) -> np.ndarray:
    """Normalized grayscale histogram.

    Args:
        img: Grayscale image (H, W), uint8.
        bins: Number of histogram bins.

    Returns:
        1-D array of shape (bins,), float64. Sums to 1.0.
    """
    hist, _ = np.histogram(img.ravel(), bins=bins, range=(0, 256))
    total = hist.sum()
    if total > 0:
        return hist.astype(np.float64) / total
    return np.zeros(bins, dtype=np.float64)


def feat_histogram_tile(
    img: np.ndarray,
    grid_n: int = 4,
    bins: int = 16,
) -> np.ndarray:
    """Per-tile normalized histograms, concatenated.

    Args:
        img: Grayscale image (H, W), uint8.
        grid_n: Grid subdivisions per axis.
        bins: Histogram bins per tile.

    Returns:
        1-D array of shape (grid_n**2 * bins,), float64.
    """
    h, w = img.shape[:2]
    result = np.empty(grid_n * grid_n * bins, dtype=np.float64)
    idx = 0
    for row in range(grid_n):
        r0, r1 = (row * h) // grid_n, ((row + 1) * h) // grid_n
        for col in range(grid_n):
            c0, c1 = (col * w) // grid_n, ((col + 1) * w) // grid_n
            tile = img[r0:r1, c0:c1]
            hist, _ = np.histogram(tile.ravel(), bins=bins, range=(0, 256))
            total = hist.sum()
            if total > 0:
                result[idx : idx + bins] = hist.astype(np.float64) / total
            else:
                result[idx : idx + bins] = 0.0
            idx += bins
    return result


def feat_lbp_histogram(
    img: np.ndarray,
    P: int = 8,  # noqa: N803
    R: int = 1,  # noqa: N803
) -> np.ndarray:
    """Uniform Local Binary Pattern histogram.

    Args:
        img: Grayscale image (H, W), uint8.
        P: Number of circularly symmetric neighbor points.
        R: Radius of circle.

    Returns:
        1-D array of shape (P+2,), float64. Sums to 1.0.
    """
    from skimage.feature import local_binary_pattern

    lbp = local_binary_pattern(img, P, R, method="uniform")
    n_bins = P + 2  # uniform LBP: P uniform patterns + non-uniform + background
    hist, _ = np.histogram(lbp.ravel(), bins=n_bins, range=(0, n_bins))
    total = hist.sum()
    if total > 0:
        return hist.astype(np.float64) / total
    return np.zeros(n_bins, dtype=np.float64)


def feat_edge_density_grid(img: np.ndarray, grid_n: int = 4) -> np.ndarray:
    """Canny edge pixel fraction per tile.

    Args:
        img: Grayscale image (H, W), uint8.
        grid_n: Grid subdivisions per axis.

    Returns:
        1-D array of shape (grid_n**2,), float64. Values in [0, 1].
    """
    import cv2

    edges = cv2.Canny(img, 50, 150)
    h, w = img.shape[:2]
    result = np.empty(grid_n * grid_n, dtype=np.float64)
    for row in range(grid_n):
        r0, r1 = (row * h) // grid_n, ((row + 1) * h) // grid_n
        for col in range(grid_n):
            c0, c1 = (col * w) // grid_n, ((col + 1) * w) // grid_n
            tile = edges[r0:r1, c0:c1]
            result[row * grid_n + col] = (
                float((tile > 0).mean()) if tile.size else 0.0
            )
    return result


def feat_cc_stats(img: np.ndarray) -> np.ndarray:
    """Connected component count (normalized) and mean size.

    Args:
        img: Grayscale image (H, W), uint8.

    Returns:
        1-D array of shape (2,): [count_normalized, mean_size_normalized].
    """
    import cv2

    _, binary = cv2.threshold(img, 128, 255, cv2.THRESH_BINARY_INV)
    n_labels, _, stats, _ = cv2.connectedComponentsWithStats(binary)

    total_pixels = img.shape[0] * img.shape[1]
    n_components = n_labels - 1  # exclude background
    if n_components <= 0:
        return np.array([0.0, 0.0], dtype=np.float64)

    areas = stats[1:, cv2.CC_STAT_AREA]
    count_norm = n_components / total_pixels
    mean_size_norm = float(areas.mean()) / total_pixels

    return np.array([count_norm, mean_size_norm], dtype=np.float64)


def feat_projection_stats(img: np.ndarray) -> np.ndarray:
    """Horizontal and vertical projection profile statistics.

    Args:
        img: Grayscale image (H, W), uint8.

    Returns:
        1-D array of shape (6,): [h_mean, h_std, h_skew, v_mean, v_std, v_skew].
    """
    from scipy.stats import skew

    inv = 1.0 - img.astype(np.float64) / 255.0  # invert: dark=1

    h_proj = inv.mean(axis=1)
    v_proj = inv.mean(axis=0)

    return np.array(
        [
            h_proj.mean(),
            h_proj.std(),
            float(skew(h_proj)),
            v_proj.mean(),
            v_proj.std(),
            float(skew(v_proj)),
        ],
        dtype=np.float64,
    )


def feat_vertical_density(
    img: np.ndarray,
    bottom_frac: float = 0.35,
) -> np.ndarray:
    """Dark pixel fraction for top and bottom zones.

    Divides the page into two zones: top (1 - bottom_frac) and bottom (bottom_frac).
    Used by scorer_forms for page classification on form-based PDFs.

    Not registered in _FEATURE_REGISTRY — purpose-specific semantics that should
    not be concatenated with general features via extract_features().

    Args:
        img: Grayscale image (H, W), uint8.
        bottom_frac: Fraction of page height for the bottom zone.

    Returns:
        1-D array of shape (2,), float64: [top_dark, bot_dark].
    """
    h = img.shape[0]
    split = int(h * (1.0 - bottom_frac))
    top = img[:split, :]
    bot = img[split:, :]
    top_dark = float((top < 128).mean()) if top.size else 0.0
    bot_dark = float((bot < 128).mean()) if bot.size else 0.0
    return np.array([top_dark, bot_dark], dtype=np.float64)


# -- Feature registry --------------------------------------------------------

_FEATURE_REGISTRY: dict[str, tuple[Callable[..., np.ndarray], dict]] = {
    "dark_ratio_grid": (feat_dark_ratio_grid, {"grid_n": 8}),
    "histogram": (feat_histogram, {"bins": 32}),
    "histogram_tile": (feat_histogram_tile, {"grid_n": 4, "bins": 16}),
    "lbp_histogram": (feat_lbp_histogram, {"P": 8, "R": 1}),
    "edge_density_grid": (feat_edge_density_grid, {"grid_n": 4}),
    "cc_stats": (feat_cc_stats, {}),
    "projection_stats": (feat_projection_stats, {}),
}


def extract_features(
    img: np.ndarray,
    feature_names: list[str],
) -> np.ndarray:
    """Extract and concatenate multiple features into one vector.

    Args:
        img: Grayscale image (H, W), uint8.
        feature_names: Keys from the feature registry.

    Returns:
        1-D concatenated feature vector.
    """
    parts: list[np.ndarray] = []
    for name in feature_names:
        fn, kwargs = _FEATURE_REGISTRY[name]
        parts.append(fn(img, **kwargs))
    return np.concatenate(parts)
