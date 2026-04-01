# eval/tests/test_pd_metrics.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import pytest


def test_chi2_distance_identical():
    from eval.pixel_density.metrics import chi2_distance
    h = np.array([0.25, 0.25, 0.25, 0.25])
    assert chi2_distance(h, h) == 0.0


def test_chi2_distance_disjoint():
    from eval.pixel_density.metrics import chi2_distance
    h1 = np.array([1.0, 0.0, 0.0, 0.0])
    h2 = np.array([0.0, 0.0, 0.0, 1.0])
    assert chi2_distance(h1, h2) == pytest.approx(2.0)


def test_chi2_distance_zero_denominator():
    from eval.pixel_density.metrics import chi2_distance
    h1 = np.array([0.5, 0.5, 0.0, 0.0])
    h2 = np.array([0.5, 0.5, 0.0, 0.0])
    assert chi2_distance(h1, h2) == 0.0


def test_chi2_tile_distance():
    from eval.pixel_density.metrics import chi2_tile_distance
    t1 = np.array([[0.25, 0.25, 0.25, 0.25], [0.5, 0.5, 0.0, 0.0]])
    t2 = np.array([[0.25, 0.25, 0.25, 0.25], [0.0, 0.0, 0.5, 0.5]])
    d = chi2_tile_distance(t1, t2)
    assert d > 0.0


def test_bilateral_scores_shape():
    from eval.pixel_density.metrics import bilateral_scores
    rng = np.random.default_rng(42)
    features = [rng.random(10) for _ in range(5)]
    scores = bilateral_scores(features, lambda a, b: np.linalg.norm(a - b), "min")
    assert scores.shape == (5,)


def test_bilateral_scores_edge_fallback():
    from eval.pixel_density.metrics import bilateral_scores
    features = [np.zeros(4), np.ones(4), np.ones(4)]
    scores = bilateral_scores(features, lambda a, b: np.linalg.norm(a - b), "min")
    assert scores[0] > 0


def test_bilateral_l2_shortcut():
    from eval.pixel_density.metrics import bilateral_l2
    features = [np.zeros(4), np.ones(4), np.zeros(4)]
    scores = bilateral_l2(features, "min")
    assert scores.shape == (3,)
    # All scores equal 2.0 due to symmetric features + edge fallback
    assert scores[1] >= scores[0] and scores[1] >= scores[2]


def test_bilateral_chi2_shortcut():
    from eval.pixel_density.metrics import bilateral_chi2
    h_uniform = np.array([0.25, 0.25, 0.25, 0.25])
    h_peaked = np.array([1.0, 0.0, 0.0, 0.0])
    features = [h_uniform, h_peaked, h_uniform]
    scores = bilateral_chi2(features, "min")
    assert scores.shape == (3,)
    assert scores[1] > 0
