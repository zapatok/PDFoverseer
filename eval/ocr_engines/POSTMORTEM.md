# Postmortem: OCR Engine Benchmark

**Date:** 2026-03-25
**Branch:** `cuda-gpu`
**Verdict:** EasyOCR and PaddleOCR eliminated. Tesseract (PSM 6 + OEM 1) retained as sole OCR engine.

---

## Purpose

Benchmark alternative OCR engines (EasyOCR, PaddleOCR) against Tesseract for the narrow task of detecting Spanish page numbers ("Pagina N de M") in cropped PDF page strips. The V4 pipeline used EasyOCR as a GPU fallback (Tier 3) for pages where Tesseract failed. PaddleOCR was evaluated as a potential faster replacement.

## Benchmark Setup

- **Test PDF:** ART_670 (2719 pages, the largest real fixture)
- **Rendering:** 300 DPI crops (top 22%, right 30% of each page)
- **Ground truth:** 796 VLM-verified entries (Claude + Opus) from `eval/fixtures/real/ART_674.json`
- **Isolation:** Each engine runs in a subprocess (`--engine easy` / `--engine paddle`) to avoid CUDA DLL conflicts between PyTorch (EasyOCR) and PaddlePaddle
- **Scoring:** `_parse()` output compared against GT; categories: `direct` (Tesseract-easy), `vlm` (Tesseract-hard), `no_gt` (potential recoveries)

## Results

| Engine | GT Accuracy | Potential Recoveries | ms/page |
|--------|------------|---------------------|---------|
| **Tesseract** (PSM 6 + OEM 1, 150 DPI) | ~93% (production w/ SR Tier 2) | N/A (baseline) | ~71 |
| **EasyOCR** (GPU, 300 DPI) | 5/796 (0.6%) on GT; 2/2719 (0.07%) in production | 82 (unverified) | 276 |
| **PaddleOCR** PP-OCRv4 mobile (GPU) | 0/796 (0%) | 0 | 33 |
| **PaddleOCR** PP-OCRv5 server det (GPU) | 0/796 (0%) | 0 | 68 |

Production A/B test (full 2719-page pipeline with/without EasyOCR): EasyOCR's 2 hits introduced noise that reduced complete documents from 606 to 603. Net negative impact.

## Why Tesseract Wins

1. **PSM 6** (uniform text block) matches the fixed-crop layout exactly — no detection stage needed
2. **OEM 1** (LSTM engine) handles the specific Spanish font variants in CRS lecture PDFs
3. **Domain-specific preprocessing:** blue ink removal, unsharp mask, OCR digit normalization (`O->0`, `I/l->1`, etc.) are tuned for this exact pattern
4. **EasyOCR/PaddleOCR** are general-purpose scene text engines optimized for varied layouts, orientations, and languages — overkill and under-tuned for narrow fixed-crop document page numbers
5. **PaddleOCR** lacks a real Spanish model; `en_PP-OCRv5` cannot recognize "Pagina"

## Architecture Impact

EasyOCR removal simplified the V4 pipeline significantly:

- **Before:** Producer-consumer pattern — 6 Tesseract workers + 1 GPU consumer thread (EasyOCR) with a shared queue
- **After:** Producers-only — 6 parallel Tesseract workers (Tier 1 direct + Tier 2 SR GPU bicubic), no consumer thread
- **Removed:** `_easyocr_reader`, `_easyocr_lock`, `_init_easyocr()`, GPU consumer queue, ~3 GB VRAM at startup
- **Kept:** PyTorch for SR Tier 2 (4x bicubic upscale, ~1ms/page)
- **Telemetry:** Updated to `[MOD:v6-tess-sr]`

## Lesson

Domain-specific preprocessing + a well-configured traditional OCR engine (Tesseract) beats general-purpose neural OCR for narrow, structured tasks. Literature benchmarks claiming PaddleOCR is "3x faster, more accurate" do not transfer to specialized use cases without fine-tuning. The 30-minute A/B production test was the decisive evidence — measure first.

## Files

| File | Purpose |
|------|---------|
| `eval/ocr_engines/benchmark.py` | Subprocess-isolated benchmark runner |
| `eval/ocr_engines/docs/specs/benchmark-design.md` | Original benchmark design spec |
| `eval/ocr_engines/docs/plans/benchmark-art670.md` | ART_670 implementation plan |
| `eval/ocr_engines/docs/reports/easyocr-paddle-postmortem.md` | Detailed results (Spanish) |
