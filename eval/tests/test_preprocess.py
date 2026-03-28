# eval/tests/test_ocr_preprocess.py
"""Tests for the parameterized OCR preprocessing pipeline."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import cv2
import numpy as np
import pytest

from eval.ocr_preprocessing.params import OCR_PRODUCTION_PARAMS  # noqa: E402
from eval.ocr_preprocessing.preprocess import preprocess  # noqa: E402


def _make_test_image(w: int = 100, h: int = 60) -> np.ndarray:
    """Create a synthetic BGR image with dark text-like marks on white."""
    img = np.full((h, w, 3), 255, dtype=np.uint8)
    cv2.putText(img, "Pag 1 de 3", (5, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1, cv2.LINE_AA)
    return img


def _make_blue_ink_image(w: int = 100, h: int = 60) -> np.ndarray:
    """Create image with blue ink overlay on text."""
    img = _make_test_image(w, h)
    # Add blue stroke across middle
    cv2.line(img, (0, 30), (w, 30), (255, 100, 0), 2)  # BGR blue
    return img


class TestPreprocessProductionBaseline:
    def test_returns_tuple(self):
        bgr = _make_test_image()
        result = preprocess(bgr, OCR_PRODUCTION_PARAMS)
        assert isinstance(result, tuple) and len(result) == 2

    def test_image_is_2d(self):
        """Production pipeline should return a binarized (2D) image."""
        bgr = _make_test_image()
        img, _ = preprocess(bgr, OCR_PRODUCTION_PARAMS)
        assert img.ndim == 2

    def test_config_is_string(self):
        bgr = _make_test_image()
        _, cfg = preprocess(bgr, OCR_PRODUCTION_PARAMS)
        assert "--psm 6" in cfg and "--oem 1" in cfg


class TestSkipBinarization:
    def test_grayscale_not_binary(self):
        """When skip_binarization=True, output should have intermediate values."""
        params = dict(OCR_PRODUCTION_PARAMS, skip_binarization=True, tess_threshold=0)
        bgr = _make_test_image()
        img, _ = preprocess(bgr, params)
        unique = np.unique(img)
        # Grayscale should have more than 2 unique values (not just 0/255)
        assert len(unique) > 2

    def test_config_includes_threshold_method(self):
        params = dict(OCR_PRODUCTION_PARAMS, skip_binarization=True, tess_threshold=2)
        bgr = _make_test_image()
        _, cfg = preprocess(bgr, params)
        assert "thresholding_method=2" in cfg


class TestMinChannel:
    def test_differs_from_luminance(self):
        bgr = _make_blue_ink_image()
        # Disable blue inpainting so the blue ink is preserved for grayscale comparison
        p_lum = dict(OCR_PRODUCTION_PARAMS, grayscale_method="luminance", skip_binarization=True, blue_inpaint=False)
        p_min = dict(OCR_PRODUCTION_PARAMS, grayscale_method="min_channel", skip_binarization=True, blue_inpaint=False)
        img_lum, _ = preprocess(bgr, p_lum)
        img_min, _ = preprocess(bgr, p_min)
        assert not np.array_equal(img_lum, img_min)


class TestWhiteBorder:
    def test_adds_padding(self):
        bgr = _make_test_image(100, 60)
        params = dict(OCR_PRODUCTION_PARAMS, white_border=10)
        img, _ = preprocess(bgr, params)
        # Should be 20px wider and 20px taller (10 each side)
        assert img.shape[0] == 60 + 20
        assert img.shape[1] == 100 + 20

    def test_no_padding_when_zero(self):
        bgr = _make_test_image(100, 60)
        params = dict(OCR_PRODUCTION_PARAMS, white_border=0)
        img, _ = preprocess(bgr, params)
        assert img.shape[0] == 60
        assert img.shape[1] == 100


class TestUnsharpMask:
    def test_sharpened_differs(self):
        bgr = _make_test_image()
        p_none = dict(OCR_PRODUCTION_PARAMS, skip_binarization=True, unsharp_sigma=0.0)
        p_sharp = dict(OCR_PRODUCTION_PARAMS, skip_binarization=True, unsharp_sigma=1.5, unsharp_strength=0.5)
        img_none, _ = preprocess(bgr, p_none)
        img_sharp, _ = preprocess(bgr, p_sharp)
        assert not np.array_equal(img_none, img_sharp)

    def test_disabled_when_sigma_zero(self):
        bgr = _make_test_image()
        p1 = dict(OCR_PRODUCTION_PARAMS, skip_binarization=True, unsharp_sigma=0.0, unsharp_strength=0.5)
        p2 = dict(OCR_PRODUCTION_PARAMS, skip_binarization=True, unsharp_sigma=0.0, unsharp_strength=0.0)
        img1, _ = preprocess(bgr, p1)
        img2, _ = preprocess(bgr, p2)
        assert np.array_equal(img1, img2)
