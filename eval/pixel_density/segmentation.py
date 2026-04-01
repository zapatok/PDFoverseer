"""PELT change-point detection wrapper for pixel density analysis.

Requires `ruptures` package. Install: pip install ruptures
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

try:
    import ruptures
except ImportError:
    ruptures = None  # type: ignore[assignment]


def _check_ruptures() -> None:
    if ruptures is None:
        raise ImportError(
            "ruptures is required for PELT segmentation. "
            "Install it with: pip install ruptures"
        )


def pelt_segment(
    signal: np.ndarray,
    model: str = "l2",
    min_size: int = 2,
    penalty: float = 1.0,
) -> list[int]:
    """Run PELT on a signal, return change-point indices.

    Args:
        signal: 1-D or 2-D array (n_samples,) or (n_samples, n_features).
        model: PELT cost model ("l2" or "rbf").
        min_size: Minimum segment size.
        penalty: PELT penalty parameter.

    Returns:
        List of change-point indices (0-based, exclusive).
        Empty list if no change-points found.
    """
    _check_ruptures()

    if signal.ndim == 1:
        signal = signal.reshape(-1, 1)

    algo = ruptures.Pelt(model=model, min_size=min_size).fit(signal)
    bkps = algo.predict(pen=penalty)

    # ruptures returns breakpoints including the last index (n_samples).
    if bkps and bkps[-1] == len(signal):
        bkps = bkps[:-1]

    return bkps


def calibrate_penalty(
    signal: np.ndarray,
    target_docs: int,
    model: str = "l2",
    min_size: int = 2,
) -> tuple[float, int]:
    """Log-space scan for penalty yielding ~target_docs segments.

    Args:
        signal: 1-D or 2-D signal array.
        target_docs: Desired number of segments (= documents).
        model: PELT cost model.
        min_size: Minimum segment size.

    Returns:
        Tuple of (best_penalty, n_segments_at_best_penalty).
    """
    _check_ruptures()

    penalties = np.logspace(-2, 3, 30)

    best_penalty = penalties[0]
    best_error = float("inf")
    best_n_segments = 0

    for pen in penalties:
        cps = pelt_segment(signal, model=model, min_size=min_size, penalty=pen)
        n_segments = len(cps) + 1
        error = abs(n_segments - target_docs)
        if error < best_error:
            best_error = error
            best_penalty = float(pen)
            best_n_segments = n_segments

    logger.info(
        "Calibrated penalty=%.4f -> %d segments (target=%d, error=%d)",
        best_penalty,
        best_n_segments,
        target_docs,
        abs(best_n_segments - target_docs),
    )

    return best_penalty, best_n_segments


def pelt_to_scores(
    change_points: list[int],
    n_pages: int,
    alpha: float = 1.0,
) -> np.ndarray:
    """Convert binary change-points to soft scores via exponential decay.

    Args:
        change_points: 0-based change-point indices.
        n_pages: Total number of pages.
        alpha: Decay rate (higher = faster decay).

    Returns:
        1-D array of scores, shape (n_pages,).
    """
    if not change_points:
        logger.warning("pelt_to_scores called with 0 change-points; returning zeros")
        return np.zeros(n_pages, dtype=np.float64)

    scores = np.zeros(n_pages, dtype=np.float64)
    cp_arr = np.array(change_points)

    for i in range(n_pages):
        min_dist = float(np.abs(cp_arr - i).min())
        scores[i] = np.exp(-alpha * min_dist)

    return scores
