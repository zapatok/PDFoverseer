# eval/tests/test_pd_segmentation.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import pytest


def test_pelt_segment_finds_changepoints():
    from eval.pixel_density.segmentation import pelt_segment
    signal = np.concatenate([np.zeros(50), np.ones(50)])
    cps = pelt_segment(signal, model="l2", min_size=2, penalty=1.0)
    assert len(cps) >= 1
    assert any(45 <= cp <= 55 for cp in cps)


def test_pelt_segment_no_change():
    from eval.pixel_density.segmentation import pelt_segment
    signal = np.ones(100)
    cps = pelt_segment(signal, model="l2", min_size=2, penalty=10.0)
    assert len(cps) == 0


def test_pelt_segment_multidim():
    from eval.pixel_density.segmentation import pelt_segment
    seg1 = np.tile([0.0, 0.0], (30, 1))
    seg2 = np.tile([1.0, 1.0], (30, 1))
    signal = np.vstack([seg1, seg2])
    cps = pelt_segment(signal, model="l2", min_size=2, penalty=1.0)
    assert len(cps) >= 1


def test_calibrate_penalty_converges():
    from eval.pixel_density.segmentation import calibrate_penalty
    signal = np.concatenate([np.full(25, 0.0), np.full(25, 1.0),
                             np.full(25, 0.0), np.full(25, 2.0)])
    penalty, n_segments = calibrate_penalty(
        signal, target_docs=4, model="l2", min_size=2,
    )
    assert penalty > 0
    assert abs(n_segments - 4) <= 2


def test_pelt_to_scores_decay():
    from eval.pixel_density.segmentation import pelt_to_scores
    scores = pelt_to_scores(change_points=[0, 50], n_pages=100, alpha=1.0)
    assert scores.shape == (100,)
    assert scores[0] == pytest.approx(1.0)
    assert scores[50] == pytest.approx(1.0)
    assert scores[25] < scores[0]


def test_pelt_to_scores_no_changepoints():
    from eval.pixel_density.segmentation import pelt_to_scores
    scores = pelt_to_scores(change_points=[], n_pages=50, alpha=1.0)
    assert scores.shape == (50,)
    assert scores.sum() == 0.0
