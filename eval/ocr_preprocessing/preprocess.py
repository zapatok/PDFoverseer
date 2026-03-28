# eval/ocr_preprocess.py
"""
Parameterized OCR preprocessing pipeline for the sweep harness.

Applies a configurable sequence of image transforms to a BGR crop,
returning the processed image and the Tesseract config string to use.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.image import _deskew

# HSV range for blue ink — must match core/ocr.py _tess_ocr()
_LOWER_BLUE = np.array([90, 50, 50])
_UPPER_BLUE = np.array([150, 255, 255])


def preprocess(bgr: np.ndarray, params: dict) -> tuple[np.ndarray, str]:
    """
    Apply parameterized preprocessing to a BGR crop image.

    Returns
    -------
    (image, tess_config) where image is grayscale (or binary) ndarray
    and tess_config is the Tesseract CLI config string.
    """
    img = bgr.copy()

    # 1. Deskew (projection profile) — requires BGR input
    if params.get("deskew", False) and img.ndim == 3:
        img = _deskew(img)

    # 2. Color separation (blue ink removal)
    color_sep = params.get("color_separation", "hsv_inpaint")
    if color_sep == "red_channel":
        # Red channel extraction: blue ink (R~30-80) fades, black text (R~0-40) preserved
        if img.ndim == 3 and img.shape[2] >= 3:
            img = img[:, :, 2]  # BGR → R channel (already grayscale)
    elif params.get("blue_inpaint", True):
        # Existing: HSV mask + Navier-Stokes inpainting
        if img.ndim == 3 and img.shape[2] >= 3:
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            mask_blue = cv2.inRange(hsv, _LOWER_BLUE, _UPPER_BLUE)
            img = cv2.inpaint(img, mask_blue, 3, cv2.INPAINT_NS)

    # 3. Grayscale conversion
    if img.ndim == 3 and img.shape[2] >= 3:
        method = params.get("grayscale_method", "luminance")
        if method == "min_channel":
            gray = np.min(img, axis=2)
        else:  # "luminance" (default)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    elif img.ndim == 2:
        gray = img
    else:
        gray = img[:, :, 0]

    # 3b. CLAHE (adaptive contrast equalization)
    clahe_clip = params.get("clahe_clip", 0.0)
    if clahe_clip > 0:
        clahe_obj = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(4, 4))
        gray = clahe_obj.apply(gray)

    # 4. Unsharp mask
    sigma = params.get("unsharp_sigma", 0.0)
    strength = params.get("unsharp_strength", 0.0)
    if sigma > 0 and strength > 0:
        ksize = int(round(sigma * 6)) | 1  # ensure odd kernel size
        blurred = cv2.GaussianBlur(gray, (ksize, ksize), sigma)
        gray = cv2.addWeighted(gray, 1.0 + strength, blurred, -strength, 0)

    # 5. White border padding
    border = params.get("white_border", 0)
    if border > 0:
        gray = cv2.copyMakeBorder(
            gray, border, border, border, border,
            cv2.BORDER_CONSTANT, value=255,
        )

    # 6. Binarization
    skip_bin = params.get("skip_binarization", False)
    if not skip_bin:
        _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # 6b. Morphological dilation (thicken thin character strokes)
    morph_k = params.get("morph_dilate", 0)
    if morph_k > 0:
        kernel = np.ones((morph_k, morph_k), np.uint8)
        gray = cv2.bitwise_not(gray)
        gray = cv2.dilate(gray, kernel, iterations=1)
        gray = cv2.bitwise_not(gray)

    # 7. Tesseract config — built from params, not from the production constant
    psm = params.get("psm", 6)
    oem = params.get("oem", 1)
    tess_cfg = f"--psm {psm} --oem {oem}"
    if skip_bin:
        tess_thresh = params.get("tess_threshold", 0)
        tess_cfg += f" -c thresholding_method={tess_thresh}"
    if params.get("preserve_interword_spaces", 0):
        tess_cfg += " -c preserve_interword_spaces=1"

    return gray, tess_cfg
