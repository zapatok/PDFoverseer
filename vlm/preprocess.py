"""Image preprocessing for VLM input."""
from __future__ import annotations

import cv2
import numpy as np


def apply_preprocess(img: np.ndarray, mode: str, upscale: float) -> np.ndarray:
    """Apply preprocessing + upscale to an image.

    Args:
        img: BGR numpy array (as read by cv2.imread).
        mode: One of "none", "grayscale", "otsu", "contrast".
        upscale: Scale factor (1.0 = no change).

    Returns:
        Processed BGR numpy array.
    """
    if mode == "none":
        out = img.copy()
    elif mode == "grayscale":
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        out = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    elif mode == "otsu":
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        out = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
    elif mode == "contrast":
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_ch = clahe.apply(l_ch)
        out = cv2.cvtColor(cv2.merge([l_ch, a_ch, b_ch]), cv2.COLOR_LAB2BGR)
    else:
        raise ValueError(f"Unknown preprocess mode: {mode!r}")

    if upscale != 1.0:
        h, w = out.shape[:2]
        new_h, new_w = int(h * upscale), int(w * upscale)
        out = cv2.resize(out, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

    return out
