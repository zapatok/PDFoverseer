# tools/

Standalone analysis utilities. These are run manually for data capture and debugging —
not part of the API or pipeline.

## Scripts

### capture_all.py
Renders and saves OCR page images for every page in every fixture PDF.
Output: `data/ocr_all/<fixture>/page_NNN.png`

### capture_failures.py
Renders and saves image strips specifically from pages where OCR failed (method=failed).
Output: `data/ocr_failures/<fixture>/`
Used to visually analyze failure patterns.

### preprocess_sweep.py
Sweeps preprocessing parameters (DPI, crop, thresholding) on a set of pages
to find the best settings for OCR accuracy.
Output: `data/preprocess_sweep/`

### regex_pattern_test.py
Compares 4 regex strategies for "Página N de M" detection using real OCR text
from `data/ocr_all/all_index.csv` (no re-OCR needed):
- `CONTROL` — current production pattern (P-prefix anchor)
- `NO_ANCHOR` — pure N de M without prefix
- `SOFT` — P-word anywhere on same line
- `WORD` — any word before N de M

Run against ART_670 to measure Tier 1 success/failure rates and disagreements.
