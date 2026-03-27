import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.preprocess_sweep import (
    Variant,
    apply_variant,
    build_variant_matrix,
    load_ground_truth,
    score_result,
)


def test_variant_matrix_count():
    """Total combinations = 5 binarize × 4 color × 4 contrast × 3 morph × 3 dpi."""
    matrix = build_variant_matrix()
    assert len(matrix) == 5 * 4 * 4 * 3 * 3  # 720


def test_variant_has_all_fields():
    matrix = build_variant_matrix()
    for v in matrix:
        assert hasattr(v, "binarize")
        assert hasattr(v, "color_filter")
        assert hasattr(v, "contrast")
        assert hasattr(v, "morphology")
        assert hasattr(v, "dpi")


def test_baseline_variant_exists():
    """The current production config must be one of the variants."""
    matrix = build_variant_matrix()
    baseline = [v for v in matrix
                if v.binarize == "none"
                and v.color_filter == "blue_only"
                and v.contrast == "unsharp_1_03"
                and v.morphology == "none"
                and v.dpi == 150]
    assert len(baseline) == 1


def test_apply_variant_returns_gray():
    """apply_variant should return a single-channel numpy array."""
    bgr = np.random.randint(0, 255, (100, 300, 3), dtype=np.uint8)
    v = Variant("none", "no_filter", "none", "none", 150)
    result = apply_variant(bgr, v)
    assert isinstance(result, np.ndarray)
    assert len(result.shape) == 2  # grayscale


def test_apply_variant_otsu_returns_binary():
    """Otsu binarization should return only 0 and 255 values."""
    bgr = np.random.randint(0, 255, (100, 300, 3), dtype=np.uint8)
    v = Variant("otsu", "no_filter", "none", "none", 150)
    result = apply_variant(bgr, v)
    unique = set(np.unique(result))
    assert unique.issubset({0, 255})


def test_load_ground_truth_art670():
    """Load ART_670 GT and verify structure."""
    gt = load_ground_truth("ART_670")
    assert isinstance(gt, dict)
    # GT maps pdf_page → (curr, total); 2683 VLM-verified reads (Opus visual inspection)
    assert gt[1] == (1, 4)
    assert gt[5] == (1, 4)  # doc 2 starts at p5
    assert gt[4] == (4, 4)  # interior pages included in full fixture
    assert len(gt) == 2683


def test_score_variant_result():
    """Score a single variant result against GT."""
    # Correct parse
    assert score_result(parsed=(2, 4), gt=(2, 4)) == "correct"
    # Wrong parse
    assert score_result(parsed=(3, 4), gt=(2, 4)) == "wrong"
    # No parse (failed)
    assert score_result(parsed=(None, None), gt=(2, 4)) == "failed"
