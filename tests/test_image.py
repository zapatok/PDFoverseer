"""Unit tests for core/image.py."""
import numpy as np
import cv2
from core.image import _deskew


def _make_lined_bgr(tilt_deg: float = 0.0, width: int = 400, height: int = 300) -> np.ndarray:
    """White BGR image with evenly-spaced black horizontal stripes, optionally tilted."""
    img = np.ones((height, width, 3), dtype=np.uint8) * 255
    for y in range(20, height - 20, 30):
        img[y : y + 5, 20 : width - 20] = 0
    if tilt_deg != 0.0:
        M = cv2.getRotationMatrix2D((width / 2, height / 2), tilt_deg, 1.0)
        img = cv2.warpAffine(img, M, (width, height), borderValue=(255, 255, 255))
    return img


def _row_variance(bgr: np.ndarray) -> float:
    """Project-profile variance — higher when text lines are horizontal."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return float(binary.sum(axis=1).astype(np.float64).var())


def test_deskew_straight_image_unchanged():
    """Image with no meaningful tilt must pass through unchanged (small-angle guard)."""
    img = _make_lined_bgr(tilt_deg=0.0)
    result = _deskew(img)
    np.testing.assert_array_equal(result, img)


def test_deskew_tilted_image_corrected():
    """A 3° tilted image must be corrected: result differs from input and has higher row variance."""
    img_tilted = _make_lined_bgr(tilt_deg=3.0)
    result = _deskew(img_tilted)
    assert not np.array_equal(result, img_tilted), "Expected correction but image was returned unchanged"
    assert _row_variance(result) > _row_variance(img_tilted), (
        "Corrected image must have higher row-sum variance than tilted input"
    )


def test_deskew_out_of_range_angle_unchanged():
    """Skew beyond ±10° must not be corrected (large-angle guard returns original)."""
    img = _make_lined_bgr(tilt_deg=15.0)
    result = _deskew(img)
    np.testing.assert_array_equal(result, img)


def test_deskew_exception_safety():
    """An invalid (empty) input must not raise — must return the original unchanged."""
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    result = _deskew(empty)
    np.testing.assert_array_equal(result, empty)
