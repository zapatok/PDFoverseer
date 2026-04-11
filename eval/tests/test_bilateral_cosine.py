"""Tests for bilateral_cosine distance in metrics.py."""

from __future__ import annotations

import numpy as np

from eval.pixel_density.metrics import bilateral_cosine


def test_bilateral_cosine_identical_pages_score_zero():
    """Identical page features should yield zero cosine distance."""
    features = [np.array([1.0, 2.0, 3.0]) for _ in range(5)]
    scores = bilateral_cosine(features, score_fn="min")
    assert scores.shape == (5,)
    assert np.allclose(scores, 0.0, atol=1e-6)


def test_bilateral_cosine_orthogonal_neighbors_score_one():
    """Orthogonal neighbors should yield cosine distance of 1.0."""
    features = [
        np.array([1.0, 0.0]),
        np.array([0.0, 1.0]),
        np.array([1.0, 0.0]),
    ]
    scores = bilateral_cosine(features, score_fn="min")
    # Middle page: both neighbors orthogonal, min should be 1.0
    assert abs(scores[1] - 1.0) < 1e-6


def test_bilateral_cosine_normalizes_magnitude():
    """Scaling a vector should not change cosine distance (magnitude-invariant)."""
    features = [
        np.array([1.0, 0.0]),
        np.array([1.0, 0.0]),  # same direction
        np.array([100.0, 0.0]),  # same direction, different magnitude
    ]
    scores = bilateral_cosine(features, score_fn="mean")
    assert np.allclose(scores, 0.0, atol=1e-6)
