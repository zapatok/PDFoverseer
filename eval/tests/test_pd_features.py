"""Tests for pixel density feature extractors."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import pytest


def test_feat_dark_ratio_grid_shape():
    from eval.pixel_density.features import feat_dark_ratio_grid
    img = np.zeros((100, 100), dtype=np.uint8)
    vec = feat_dark_ratio_grid(img, grid_n=8)
    assert vec.shape == (64,)
    assert vec.dtype == np.float64


def test_feat_dark_ratio_grid_all_black():
    from eval.pixel_density.features import feat_dark_ratio_grid
    img = np.zeros((80, 80), dtype=np.uint8)
    vec = feat_dark_ratio_grid(img, grid_n=4)
    np.testing.assert_array_almost_equal(vec, np.ones(16))


def test_feat_histogram_shape():
    from eval.pixel_density.features import feat_histogram
    img = np.random.default_rng(42).integers(0, 256, (100, 100), dtype=np.uint8)
    vec = feat_histogram(img, bins=32)
    assert vec.shape == (32,)
    assert vec.dtype == np.float64


def test_feat_histogram_normalized():
    from eval.pixel_density.features import feat_histogram
    img = np.random.default_rng(42).integers(0, 256, (100, 100), dtype=np.uint8)
    vec = feat_histogram(img, bins=32)
    assert pytest.approx(vec.sum(), abs=1e-6) == 1.0


def test_feat_histogram_all_same_value():
    from eval.pixel_density.features import feat_histogram
    img = np.full((50, 50), 128, dtype=np.uint8)
    vec = feat_histogram(img, bins=32)
    assert vec.max() == pytest.approx(1.0, abs=1e-6)
    assert (vec > 0).sum() == 1


def test_feat_histogram_tile_shape():
    from eval.pixel_density.features import feat_histogram_tile
    img = np.random.default_rng(42).integers(0, 256, (100, 100), dtype=np.uint8)
    vec = feat_histogram_tile(img, grid_n=4, bins=16)
    assert vec.shape == (4 * 4 * 16,)  # 256 dims


def test_feat_histogram_tile_each_tile_normalized():
    from eval.pixel_density.features import feat_histogram_tile
    img = np.random.default_rng(42).integers(0, 256, (80, 80), dtype=np.uint8)
    vec = feat_histogram_tile(img, grid_n=4, bins=16)
    for t in range(16):
        tile_hist = vec[t * 16 : (t + 1) * 16]
        assert pytest.approx(tile_hist.sum(), abs=1e-6) == 1.0


def test_feat_lbp_histogram_shape():
    from eval.pixel_density.features import feat_lbp_histogram
    img = np.random.default_rng(42).integers(0, 256, (100, 100), dtype=np.uint8)
    vec = feat_lbp_histogram(img, P=8, R=1)
    # Uniform LBP with P=8 produces P+2 = 10 bins
    assert vec.shape == (10,)


def test_feat_lbp_histogram_normalized():
    from eval.pixel_density.features import feat_lbp_histogram
    img = np.random.default_rng(42).integers(0, 256, (100, 100), dtype=np.uint8)
    vec = feat_lbp_histogram(img, P=8, R=1)
    assert pytest.approx(vec.sum(), abs=1e-6) == 1.0


def test_feat_edge_density_grid_shape():
    from eval.pixel_density.features import feat_edge_density_grid
    img = np.random.default_rng(42).integers(0, 256, (100, 100), dtype=np.uint8)
    vec = feat_edge_density_grid(img, grid_n=4)
    assert vec.shape == (16,)
    assert all(0.0 <= v <= 1.0 for v in vec)


def test_feat_edge_density_blank_image():
    from eval.pixel_density.features import feat_edge_density_grid
    img = np.full((100, 100), 128, dtype=np.uint8)  # uniform -> no edges
    vec = feat_edge_density_grid(img, grid_n=4)
    assert vec.sum() == 0.0


def test_feat_cc_stats_shape():
    from eval.pixel_density.features import feat_cc_stats
    img = np.full((100, 100), 255, dtype=np.uint8)
    img[10:20, 10:20] = 0  # one dark blob
    vec = feat_cc_stats(img)
    assert vec.shape == (2,)


def test_feat_cc_stats_no_components():
    from eval.pixel_density.features import feat_cc_stats
    img = np.full((100, 100), 255, dtype=np.uint8)  # all white
    vec = feat_cc_stats(img)
    assert vec[0] == 0.0
    assert vec[1] == 0.0


def test_feat_projection_stats_shape():
    from eval.pixel_density.features import feat_projection_stats
    img = np.random.default_rng(42).integers(0, 256, (100, 100), dtype=np.uint8)
    vec = feat_projection_stats(img)
    assert vec.shape == (6,)


def test_extract_features_concatenates():
    from eval.pixel_density.features import extract_features
    img = np.random.default_rng(42).integers(0, 256, (100, 100), dtype=np.uint8)
    vec = extract_features(img, ["dark_ratio_grid", "histogram"])
    # 64 (grid 8x8) + 32 (histogram) = 96
    assert vec.shape == (96,)
