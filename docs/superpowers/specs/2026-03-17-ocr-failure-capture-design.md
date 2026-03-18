# OCR Failure Capture Tool — Design Spec

**Date:** 2026-03-17
**Status:** Approved
**Scope:** Standalone research tool, no changes to production pipeline

---

## Problem

Pipeline V4 uses a 3-tier OCR stack (Tesseract direct → SR+Tesseract → EasyOCR GPU) to detect
page numbers matching the pattern "Página N de M". Some pages fail all three tiers and are passed
to the Dempster-Shafer inference engine. Many of these failures are visually clear — the page
number is legible to the human eye — suggesting blind spots in the current preprocessing or
Tesseract configuration rather than genuinely ambiguous images.

There is no way to analyze these failures without first capturing them. Currently the image strips
are generated dynamically and discarded.

---

## Goal

Build a standalone script that processes a PDF, identifies every page where all OCR tiers fail to
detect the page number pattern, and saves the image strip + metadata for offline analysis.

This tool is for research and diagnosis only. It does not modify the production pipeline.

---

## Capture Trigger

A page is captured when both Tesseract tiers fail to match the page pattern:

- **Tier 1:** `_parse(_tess_ocr(gray))` returns `(None, None)`
- **Tier 2:** `_parse(_tess_ocr(gray_sr))` returns `(None, None)` (where `gray_sr` is the 4x upscaled crop)

The script inlines the two-tier sequence directly rather than using `_process_page()`. This
avoids the double-render that would result from calling `_render_clip()` separately and then
`_process_page()` (which also calls `_render_clip()` internally). It also naturally surfaces the
intermediate Tesseract text strings, which `_process_page()` discards.

---

## Output Structure

```
data/
└── ocr_failures/
    ├── failures_index.csv
    ├── CH_39docs/
    │   ├── p037_20260317_143022.png
    │   └── p047_20260317_143025.png
    └── INS_31docs/
        └── p001_20260317_143100.png
```

### Image files

Each PNG is the **raw BGR crop** from `_render_clip()` — the image before any preprocessing
(Otsu, SR, inpainting). This is what the human eye sees. Naming convention:

```
p{page:03d}_{YYYYMMDD}_{HHMMSS}.png
```

> **Future:** Also save the Otsu-binarized version alongside the raw for side-by-side comparison.
> Otsu may destroy information when ink or pen marks overlap the page number text, making the
> problem appear to be OCR when it is actually preprocessing. Naming: `p037_raw.png` /
> `p037_otsu.png`.

### CSV index (`failures_index.csv`)

One row per captured page:

| column | example | notes |
|---|---|---|
| `pdf_nickname` | `CH_39docs` | filename without extension |
| `page_num` | `37` | 1-based page number |
| `timestamp` | `2026-03-17T14:30:22` | ISO 8601 |
| `image_path` | `CH_39docs/p037_20260317_143022.png` | relative to `data/ocr_failures/` |
| `tier1_text` | `"Pbgina 1 de"` | Tesseract output after Otsu binarization (Tier 1) |
| `tier2_text` | `""` | Tesseract output after SR + Otsu binarization (Tier 2), empty if skipped |
| `tier3_text` | `"Psgina 1 de 2"` | EasyOCR raw output (Tier 3), empty if not run |

Note: `tier1_text` and `tier2_text` reflect what Tesseract received after Otsu preprocessing,
not the raw pixel values. A blank `tier1_text` with a visually clear PNG likely indicates Otsu
degraded the image before Tesseract ran — a key diagnostic signal.

---

## Script Design

**Location:** `tools/capture_failures.py`

**Usage:**
```bash
python tools/capture_failures.py eval/fixtures/real/INS_31docs.pdf
python tools/capture_failures.py eval/fixtures/real/  # all PDFs in directory
```

**Imports from `core/analyzer.py`:**

| symbol | purpose |
|---|---|
| `_render_clip(page, dpi)` | get raw BGR franja — single render per page |
| `_tess_ocr(gray)` | Tesseract after Otsu binarization; call once per tier |
| `_upsample_4x(bgr)` | 4x SR upscale for Tier 2 |
| `_parse(text)` | pattern match — returns `(curr, total)` or `(None, None)` |
| `_setup_sr(on_log)` | one-time SR initialization — **must be called before `_upsample_4x`**; sets up GPU bicubic or warms up FSRCNN CPU fallback |
| `_upsample_4x(bgr)` | takes a **BGR array** (not grayscale) — call before converting to gray for Tier 2 |
| `_init_easyocr(on_log)` | lazy-init EasyOCR GPU singleton |
| `_easyocr_reader` | access via module reference (`analyzer._easyocr_reader`), not `from` import — the global is reassigned after `_init_easyocr()` runs; a `from` import captured before that call will remain `None` |

**Flow:**

```
_setup_sr(print)          # one-time SR init before processing any pages
[_init_easyocr(print)]    # optional: only if Tier 3 capture is wanted
initialize output dirs + CSV writer

for each page in PDF:
    bgr_raw  = _render_clip(page, dpi=DPI)        # single render
    gray     = cv2.cvtColor(bgr_raw, BGR2GRAY)

    # Tier 1
    text1    = _tess_ocr(gray)
    c, t     = _parse(text1)
    if c: continue                                 # pattern found, skip

    # Tier 2
    bgr_sr   = _upsample_4x(bgr_raw)
    gray_sr  = cv2.cvtColor(bgr_sr, BGR2GRAY)
    text2    = _tess_ocr(gray_sr)
    c, t     = _parse(text2)
    if c: continue                                 # pattern found, skip

    # Both tiers failed — capture
    [optional Tier 3: re-render at EASYOCR_DPI=300 + run EasyOCR for text3
     note: reuse bgr_raw at 150 DPI would give worse results than production]
    save bgr_raw as PNG
    append row to failures_index.csv (page, text1, text2, text3)

print summary: N pages scanned, M failures captured → data/ocr_failures/{nickname}/
```

**Performance:** Single-threaded, sequential. This is an offline diagnostic tool — speed is
not a concern.

---

## Non-Goals

- No changes to `core/analyzer.py` or `server.py`
- No UI integration
- No real-time capture during normal pipeline execution
- No automatic re-training or parameter tuning (that comes after analysis)

---

## Success Criteria

1. Script runs on any PDF in the project without modifying the production pipeline
2. Every page where both Tesseract tiers fail produces a PNG and a CSV row
3. INS_31docs.pdf produces ≥1 capture (known failure case with visually clear page numbers)
4. CSV is human-readable and openable in Excel/LibreOffice for analysis
