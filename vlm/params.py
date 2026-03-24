# vlm/params.py
"""Parameter space for VLM OCR sweep."""
from __future__ import annotations

PARAM_SPACE: dict[str, list] = {
    "prompt": [
        "Read the page number pattern 'Pagina N de M' from this image. Reply only with N/M.",
        "Extract the text 'Pagina X de Y' visible in this image. Reply: X/Y",
        "Que numero de pagina dice esta imagen? Formato: N/M",
        "OCR this image. Return only the page number in format N/M.",
    ],
    "temperature": [0.0, 0.1, 0.3, 0.5],
    "top_p": [0.5, 0.9, 1.0],
    "preprocess": ["none", "grayscale", "otsu", "contrast"],
    "upscale": [1.0, 1.5, 2.0],
    "seed": [42, 123, 7],
}
# Total: 4 x 4 x 3 x 4 x 3 x 3 = 1,728 combinations
# Note: seed tests reproducibility — if results are identical across seeds
# at temperature=0, we can drop seed from the space (reducing to 576).

# Filled after first sweep
PRODUCTION_PARAMS: dict[str, object] = {
    "prompt": PARAM_SPACE["prompt"][0],
    "temperature": 0.0,
    "top_p": 1.0,
    "preprocess": "none",
    "upscale": 1.0,
    "seed": 42,
}
