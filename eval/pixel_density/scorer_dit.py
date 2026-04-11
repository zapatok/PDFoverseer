"""Cover-page scorers over DiT embeddings + bilateral cosine similarity.

Minimal ports of scorer_find_peaks and scorer_rescue_c from sweep_rescue.py,
using cosine distance over 768-d DiT embeddings instead of L2 over 80-d
handcrafted features.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import find_peaks as scipy_find_peaks

from eval.pixel_density.metrics import bilateral_cosine


def _bilateral_cosine_min(embeddings: np.ndarray) -> np.ndarray:
    """Return per-page bilateral-min cosine scores for an (N, D) embedding matrix."""
    features = [embeddings[i] for i in range(embeddings.shape[0])]
    return bilateral_cosine(features, score_fn="min")


def score_dit_find_peaks(
    embeddings: np.ndarray,
    prominence: float = 0.1,
    distance: int = 2,
) -> list[int]:
    """Peak-detection scorer over DiT bilateral-cosine signal.

    Args:
        embeddings: (N, 768) DiT embeddings, float32.
        prominence: Minimum peak prominence (scipy find_peaks).
        distance: Minimum separation between peaks.

    Returns:
        Sorted list of cover-page indices (always includes 0).
    """
    signal = _bilateral_cosine_min(embeddings)
    peaks, _ = scipy_find_peaks(signal, prominence=prominence, distance=distance)
    covers = set(peaks.tolist())
    covers.add(0)
    return sorted(covers)


def score_dit_percentile(
    embeddings: np.ndarray,
    percentile: float = 75.0,
) -> list[int]:
    """Percentile-threshold scorer over DiT bilateral-cosine signal.

    Args:
        embeddings: (N, 768) DiT embeddings, float32.
        percentile: Pages at or above this percentile of the bilateral score
            are classified as covers.

    Returns:
        Sorted list of cover-page indices (always includes 0).
    """
    signal = _bilateral_cosine_min(embeddings)
    threshold = float(np.percentile(signal, percentile))
    covers = set(int(i) for i in np.where(signal >= threshold)[0])
    covers.add(0)
    return sorted(covers)
