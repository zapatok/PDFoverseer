"""Image processing: rendering PDF clips."""
from __future__ import annotations

import warnings

import fitz  # PyMuPDF
import cv2
import numpy as np

from core.utils import DPI, CROP_X_START, CROP_Y_END


# ── PyMuPDF clip rendering ───────────────────────────────────────────────────

def _render_clip(page: fitz.Page, dpi: int = DPI) -> np.ndarray:
    """Render only the top-right corner of a PDF page. Returns BGR numpy array."""
    rect = page.rect
    clip = fitz.Rect(
        rect.width * CROP_X_START,
        0,
        rect.width,
        rect.height * CROP_Y_END,
    )
    pix = page.get_pixmap(dpi=dpi, clip=clip)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
    if pix.n == 4:
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
    elif pix.n == 3:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    else:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    return img


# ── Deskew (projection profile) ─────────────────────────────────────────────

_DESKEW_ANGLES = [a * 0.5 for a in range(-22, 23)]   # -11.0° … +11.0° in 0.5° steps
_DESKEW_MIN    = 0.5    # skip corrections smaller than this (independent of step size)
_DESKEW_MAX    = 10.0   # skip corrections larger than this (likely false detection)


def _deskew(bgr: np.ndarray) -> np.ndarray:
    """Detect and correct scan skew via horizontal projection-profile variance.

    Sweeps candidate angles in ±11° and selects the one that maximises the
    variance of per-row pixel sums on a binarised copy of the image.
    Returns the BGR-corrected image, or the original if the detected angle is
    below the minimum threshold (< 0.5°) or above the false-detection guard
    (> 10°), or if any error occurs.
    """
    try:
        if bgr.size == 0:
            return bgr

        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        h, w = binary.shape
        center = (w / 2.0, h / 2.0)
        best_angle    = 0.0
        best_variance = -1.0

        for angle in _DESKEW_ANGLES:
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated  = cv2.warpAffine(binary, M, (w, h),
                                      flags=cv2.INTER_NEAREST, borderValue=0)
            variance = rotated.sum(axis=1).astype(np.float64).var()
            if variance > best_variance:
                best_variance = variance
                best_angle    = angle

        if abs(best_angle) < _DESKEW_MIN or abs(best_angle) > _DESKEW_MAX:
            return bgr

        M = cv2.getRotationMatrix2D(center, best_angle, 1.0)
        return cv2.warpAffine(bgr, M, (w, h),
                              flags=cv2.INTER_LINEAR,
                              borderValue=(255, 255, 255))
    except Exception as exc:  # noqa: BLE001
        warnings.warn(f"_deskew: failed ({exc}), returning original", stacklevel=2)
        return bgr
