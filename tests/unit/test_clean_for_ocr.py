"""E6 — clean_for_ocr: the V4 image-cleaning cascade, fixture-free."""

from __future__ import annotations

import numpy as np

from core.image import clean_for_ocr


def test_color_input_returns_2d_gray_same_hw():
    bgr = np.full((40, 120, 3), 200, np.uint8)
    out = clean_for_ocr(bgr)
    assert out.ndim == 2
    assert out.shape == (40, 120)
    assert out.dtype == np.uint8


def test_gray_input_passthrough_guard():
    gray = np.full((30, 90), 180, np.uint8)
    out = clean_for_ocr(gray)
    assert out.ndim == 2
    assert out.shape == (30, 90)


def test_does_not_crash_on_blue_region():
    # A patch of blue (the ink the cascade inpaints) must be handled, not error.
    bgr = np.full((24, 24, 3), 255, np.uint8)
    bgr[:, :12] = (200, 60, 60)  # BGR-ish blue block
    out = clean_for_ocr(bgr)
    assert out.shape == (24, 24)
