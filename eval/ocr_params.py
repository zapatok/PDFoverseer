# eval/ocr_params.py
"""
Parameter search space for the OCR preprocessing sweep.
Each key maps to a list of discrete candidate values.
OCR_PRODUCTION_PARAMS mirrors the current _tess_ocr pipeline in core/ocr.py.
"""

OCR_PARAM_SPACE: dict[str, list] = {
    # Blue ink removal (HSV mask + inpainting)
    "blue_inpaint":       [True, False],

    # Grayscale conversion method
    #   "luminance"    = cv2.COLOR_BGR2GRAY (standard weighted)
    #   "min_channel"  = np.min(bgr, axis=2) (max ink-vs-paper contrast)
    "grayscale_method":   ["luminance", "min_channel"],

    # Skip external binarization (let Tesseract LSTM handle thresholding)
    "skip_binarization":  [True, False],

    # Tesseract internal thresholding (only effective when skip_binarization=True)
    #   0 = Otsu (Tesseract default), 2 = Sauvola (adaptive, local)
    "tess_threshold":     [0, 2],

    # White border padding in pixels (improves Tesseract edge detection)
    "white_border":       [0, 5, 10, 15],

    # Unsharp mask gaussian sigma (0 = disabled)
    "unsharp_sigma":      [0.0, 1.0, 1.5, 2.0],

    # Unsharp mask strength/amount (0 = disabled)
    "unsharp_strength":   [0.0, 0.3, 0.5, 0.8],

    # Deskew via projection profile (core/image.py _deskew)
    "deskew":             [True, False],
}

# Current production pipeline equivalent
OCR_PRODUCTION_PARAMS: dict[str, object] = {
    "blue_inpaint":      True,
    "grayscale_method":  "luminance",
    "skip_binarization": False,
    "tess_threshold":    0,
    "white_border":      0,
    "unsharp_sigma":     0.0,
    "unsharp_strength":  0.0,
    "deskew":            False,
}
