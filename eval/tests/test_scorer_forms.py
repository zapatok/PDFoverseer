"""Tests for scorer_forms: vertical density feature, Otsu 1D, scorer smoke, ART gate."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np  # noqa: E402
import pytest  # noqa: E402


# ── feat_vertical_density ─────────────────────────────────────────────────


def test_vertical_density_shape():
    """Returns shape (2,) for any image."""
    from eval.pixel_density.features import feat_vertical_density

    img = np.random.randint(0, 256, (100, 80), dtype=np.uint8)
    result = feat_vertical_density(img, bottom_frac=0.35)
    assert result.shape == (2,)
    assert result.dtype == np.float64


def test_vertical_density_white_page():
    """All-white page has [0, 0] dark ratios."""
    from eval.pixel_density.features import feat_vertical_density

    img = np.full((100, 80), 255, dtype=np.uint8)
    result = feat_vertical_density(img, bottom_frac=0.35)
    assert result[0] == 0.0
    assert result[1] == 0.0


def test_vertical_density_black_page():
    """All-black page has [1, 1] dark ratios (all pixels < 128)."""
    from eval.pixel_density.features import feat_vertical_density

    img = np.zeros((100, 80), dtype=np.uint8)
    result = feat_vertical_density(img, bottom_frac=0.35)
    assert result[0] == pytest.approx(1.0)
    assert result[1] == pytest.approx(1.0)


def test_vertical_density_bottom_heavy():
    """Page with dark bottom, white top has high bot_dark, low top_dark."""
    from eval.pixel_density.features import feat_vertical_density

    img = np.full((100, 80), 255, dtype=np.uint8)
    img[65:, :] = 0  # bottom 35% is black
    result = feat_vertical_density(img, bottom_frac=0.35)
    assert result[0] == 0.0  # top is white
    assert result[1] == pytest.approx(1.0)  # bottom is black


def test_vertical_density_different_bottom_frac():
    """Changing bottom_frac changes the split point."""
    from eval.pixel_density.features import feat_vertical_density

    img = np.full((100, 80), 255, dtype=np.uint8)
    img[50:, :] = 0  # bottom 50% is black

    r25 = feat_vertical_density(img, bottom_frac=0.25)
    r50 = feat_vertical_density(img, bottom_frac=0.50)
    # With bottom_frac=0.50, bot zone covers exactly the black region
    assert r50[1] == pytest.approx(1.0)
    # With bottom_frac=0.25, bot zone is fully black AND top zone has some black
    assert r25[1] == pytest.approx(1.0)
    assert r25[0] > 0.0  # top zone includes some black pixels


def test_vertical_density_not_in_registry():
    """feat_vertical_density must NOT be in the feature registry."""
    from eval.pixel_density.features import _FEATURE_REGISTRY

    assert "vertical_density" not in _FEATURE_REGISTRY
