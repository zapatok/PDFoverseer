# tools/

Standalone analysis utilities. These are run manually for data capture, corpus
audits, and debugging — not part of the API or pipeline.

## Scripts

### capture_all.py
Renders and saves OCR page images for every page in every fixture PDF, plus OCR
text from each tier in a CSV index.
Output: `data/ocr_all/<fixture>/page_NNN.png` + `data/ocr_all/all_index.csv`

Fixed 2026-07-03 (QA-6): imported from `core.analyzer`, a V4-era module that no
longer exists, plus `EASYOCR_DPI`/`_init_easyocr` from `core.ocr`, removed
there in the 2026-03-26 EasyOCR removal (see `core/README.md`). Remapped to
the current module layout; the EasyOCR Tier-3 capture path (the `--easyocr`
flag) was dropped entirely — `tier3_text` stays an always-empty CSV column so
any prior index keeps the same schema.

### capture_failures.py
Renders and saves image strips specifically from pages where OCR failed (method=failed).
Output: `data/ocr_failures/<fixture>/` + `data/ocr_failures/failures_index.csv`
Used to visually analyze failure patterns.

Fixed 2026-07-03 (QA-7): same `core.analyzer` import breakage and EasyOCR
Tier-3 removal as `capture_all.py`.

### pattern_eval.py
Tests OCR page-number pattern variants against real Tesseract output stored in
`data/ocr_all/all_index.csv` (captured by `capture_all.py`) — reports
matches/correct/FP-rate/distribution per variant against each fixture's
structural ground truth.

### preprocess_sweep.py
Sweeps preprocessing parameters (DPI, crop, thresholding) on a set of pages
to find the best settings for OCR accuracy.
Output: `data/preprocess_sweep/`

### audit_filename_glob.py
One-off audit: scanner count vs. raw PDF count per (hospital, sigla) on the
real ABRIL corpus.

### audit_sigla_page_ranges.py
One-off audit: typical page-count range (p25/median/p75/min/max/n) per sigla,
walked across every month folder × hospital in the real corpus. Feeds the
frontend's per-sigla info cards (`sigla-info.js`).

### extract_fase2_fixtures.py
Copies real PDFs from the ABRIL corpus into folder-shaped fixtures under
`tests/fixtures/scanners_ocr/`. Idempotent.

### dump_counts.py
Dumps every cell's effective count (via `compute_cell_count`/`compute_worker_count`)
as JSON from a session DB — the audit-remediation output-safety guard (diff
two dumps to prove a code change didn't move any count).
