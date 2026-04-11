"""Distance functions and bilateral score computation for pixel density analysis."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np


def chi2_distance(h1: np.ndarray, h2: np.ndarray) -> float:
    """Chi-squared distance between two histograms.

    Args:
        h1: First histogram (1-D).
        h2: Second histogram (1-D), same shape as h1.

    Returns:
        Chi-squared distance (0 = identical).
    """
    denom = h1 + h2
    with np.errstate(invalid="ignore", divide="ignore"):
        terms = np.where(denom > 0, (h1 - h2) ** 2 / denom, 0.0)
    return float(terms.sum())


def chi2_tile_distance(tiles1: np.ndarray, tiles2: np.ndarray) -> float:
    """Sum of per-tile chi-squared distances.

    Args:
        tiles1: Array of shape (n_tiles, bins).
        tiles2: Array of shape (n_tiles, bins).

    Returns:
        Sum of per-tile chi² distances.
    """
    total = 0.0
    for i in range(tiles1.shape[0]):
        total += chi2_distance(tiles1[i], tiles2[i])
    return total


def bilateral_scores(
    page_features: list[np.ndarray],
    distance_fn: Callable[[np.ndarray, np.ndarray], float],
    score_fn: str,
) -> np.ndarray:
    """Generic bilateral scoring: compare each page to left/right neighbor.

    Args:
        page_features: Per-page feature vectors.
        distance_fn: Distance function (a, b) -> float.
        score_fn: Aggregation: "min", "mean", or "harmonic".

    Returns:
        1-D array of bilateral scores, one per page.
    """
    n = len(page_features)
    left = np.zeros(n)
    right = np.zeros(n)

    for i in range(1, n):
        left[i] = distance_fn(page_features[i], page_features[i - 1])
    for i in range(n - 1):
        right[i] = distance_fn(page_features[i], page_features[i + 1])

    left[0] = right[0]
    right[-1] = left[-1]

    if score_fn == "min":
        return np.minimum(left, right)
    elif score_fn == "mean":
        return (left + right) / 2.0
    elif score_fn == "harmonic":
        denom = left + right
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(denom > 0, 2 * left * right / denom, 0.0)
    else:
        raise ValueError(f"Unknown score_fn: {score_fn!r}")


def bilateral_l2(
    page_features: list[np.ndarray],
    score_fn: str,
) -> np.ndarray:
    """Bilateral scoring with L2 distance.

    Args:
        page_features: Per-page feature vectors.
        score_fn: Aggregation: "min", "mean", or "harmonic".

    Returns:
        1-D array of bilateral scores.
    """
    return bilateral_scores(
        page_features,
        lambda a, b: float(np.linalg.norm(a - b)),
        score_fn,
    )


def bilateral_cosine(
    page_features: list[np.ndarray],
    score_fn: str,
) -> np.ndarray:
    """Bilateral scoring with cosine distance (1 - cosine similarity).

    Magnitude-invariant: only the direction of each feature vector matters.
    Recommended for high-dimensional embeddings (e.g., DiT 768-d) where L2
    distance concentration is a problem.

    Args:
        page_features: Per-page feature vectors.
        score_fn: Aggregation: "min", "mean", or "harmonic".

    Returns:
        1-D array of bilateral scores in [0, 2].
    """
    def cosine_dist(a: np.ndarray, b: np.ndarray) -> float:
        na = float(np.linalg.norm(a))
        nb = float(np.linalg.norm(b))
        if na == 0.0 or nb == 0.0:
            return 1.0
        return 1.0 - float(np.dot(a, b) / (na * nb))

    return bilateral_scores(page_features, cosine_dist, score_fn)


def bilateral_chi2(
    page_features: list[np.ndarray],
    score_fn: str,
) -> np.ndarray:
    """Bilateral scoring with chi-squared distance.

    Args:
        page_features: Per-page histogram vectors.
        score_fn: Aggregation: "min", "mean", or "harmonic".

    Returns:
        1-D array of bilateral scores.
    """
    return bilateral_scores(page_features, chi2_distance, score_fn)
