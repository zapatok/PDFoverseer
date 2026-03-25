# DPI 300 Tesseract Tier — Postmortem

**Date:** 2026-03-25
**Status:** Abandoned — both placements caused regressions
**Commits:** d690bd7, 8fb7282, d0d2abe (all reverted in f54343a)
**Sweep tool retained:** d0d4587 (`tools/preprocess_sweep.py`)

---

## Hypothesis

Adding a DPI 300 Tesseract pass to the OCR cascade would recover pages that fail at DPI 150 and SR (4x upscale of 150 = effective 600 DPI). A preprocessing sweep of 720 variants on 50 failed ART_670 pages showed DPI 300 as the dominant recovery factor: **23/50 recovered, 0 wrong**.

Cross-PDF validation (ART_670, CH_74, CH_39, INS_31) confirmed DPI 300 and SR are complementary: only_SR=6, only_DPI300=14, overlap=12.

## What Was Built

1. **`tools/preprocess_sweep.py`** — standalone research tool testing 720 preprocessing variants (5 binarization × 4 color × 4 contrast × 3 morphology × 3 DPI) on failed OCR pages. Output: ranked CSV + summary.

2. **Tier 1b (DPI 300 before SR)** — `_process_page` cascade: T1 (DPI 150) → **T1b (DPI 300)** → T2 (SR) → EasyOCR. Return type changed to `tuple[_PageRead, np.ndarray | None]` to pass the DPI 300 image to the GPU consumer, saving a 49ms re-render.

3. **Tier 2b (DPI 300 after SR)** — reordered cascade: T1 → T2 (SR) → **T2b (DPI 300)** → EasyOCR. Intended to let SR handle its known-good pages first, with DPI 300 only acting on SR failures.

4. **Pipeline changes** — GPU queue changed from `Queue[int | None]` to `Queue[tuple[int, np.ndarray] | None]` to pass pre-rendered images. GPU consumer updated to skip re-rendering. Telemetry method map extended with `"dpi300": "3"`.

## What Was Tested

### Sweep (offline, 50 failed pages)

| Variant | Recovered | Wrong | Failed |
|---------|-----------|-------|--------|
| none_blue_only_unsharp_1_03_none_dpi300 | 23 | 0 | 27 |
| none_no_filter_none_none_dpi300 | 23 | 0 | 27 |
| Baseline (DPI 150) | 0 | 0 | 50 |

Key finding: DPI 300 is the dominant factor. Preprocessing (binarization, morphology, contrast) had minimal impact at DPI 300. **0 wrong reads** in the 50-page sample.

### Production run — Tier 1b (before SR)

ART_670.pdf, 2719 pages:

| Metric | v5-max-total | Tier 1b | Delta |
|--------|:-----------:|:-------:|:-----:|
| direct | 1510 | 1510 | = |
| super_resolution | 621 | **79** | -542 |
| dpi300 | — | **741** | +741 |
| easyocr | 2 | 1 | -1 |
| failed | 586 | **388** | **-198** |
| Time | 453.6s | 514.7s | +13% |
| DOC | 667 | 664 | -3 |
| **COM** | **603 (90%)** | **584 (88%)** | **-19** |
| seq_broken | 50 | 64 | **+14** |
| undercount | 14 | 16 | +2 |
| INF | 603 | 404 | -199 |

**Root cause:** Tier 1b intercepted 542 pages that SR was reading correctly. Some of those DPI 300 reads were **wrong** (misread page numbers), but returned with confidence 1.0. The sweep's 0-wrong result on 50 pages did not generalize to the full 2719-page corpus.

### Production run — Tier 2b (after SR)

ART_670.pdf, 2719 pages:

| Metric | v5-max-total | Tier 2b | Delta |
|--------|:-----------:|:-------:|:-----:|
| direct | 1510 | 1510 | = |
| super_resolution | 621 | **621** | = |
| dpi300 | — | **199** | +199 |
| easyocr | 2 | 1 | -1 |
| failed | 586 | **388** | **-198** |
| Time | 453.6s | 537.1s | +18% |
| DOC | 667 | 667 | = |
| **COM** | **603 (90%)** | **581 (87%)** | **-22** |
| seq_broken | 50 | 65 | **+15** |
| undercount | 14 | **21** | **+7** |
| INF | 603 | 407 | -196 |

**Root cause:** Even after SR, the 199 "exclusive" DPI 300 reads (pages that only DPI 300 could parse) contained enough wrong reads to poison downstream inference. The undercount jumped from 14 to 21, indicating DPI 300 was producing page numbers that broke document boundary detection.

### Other PDFs

Most small PDFs (<100 pages) showed 0-2 dpi300 reads with no visible regression, but these PDFs have few failed pages and minimal inference complexity. The regressions were only visible on ART_670 where inference covers 400+ pages.

## Why the Sweep Was Misleading

1. **Sample bias**: The sweep tested 50 pages that **failed all existing tiers**. These are the hardest pages — genuinely degraded text. The 0-wrong result was valid for this population.

2. **Missing population**: The sweep did not test pages that **SR could already read**. When Tier 1b was placed before SR, it intercepted these SR-readable pages. At DPI 300, Tesseract sometimes produced a plausible-but-wrong parse (matching the `Página X de Y` regex with incorrect X or Y) that SR would have read correctly.

3. **Confidence blindness**: All Tesseract reads return confidence 1.0 (binary: parsed or not). There's no way to distinguish a correct DPI 300 read from a wrong one without ground truth comparison.

4. **Inference amplification**: A single wrong read (e.g., "3/4" instead of "2/4") cascades through the inference engine, breaking document boundaries and sequence detection for surrounding pages.

## Lessons Learned

1. **Sweep ≠ production validation.** A sweep on failed pages validates recovery but says nothing about interference with existing tiers. Future sweeps must also test the **overlap population** (pages readable by multiple tiers) for agreement.

2. **Tier ordering matters more than tier quality.** DPI 300 genuinely reads more pages than DPI 150. But inserting it before a proven tier (SR) caused net harm because its error rate on SR-readable pages was nonzero.

3. **Wrong reads are worse than failed reads.** The inference engine handles failed pages gracefully (via D-S propagation). A wrong read with confidence 1.0 is treated as ground truth and corrupts neighboring inference.

4. **Small-sample 0% error does not mean 0% error at scale.** 0/50 wrong ≠ 0/2719 wrong. Even a 1% error rate on 741 intercepted pages = ~7 wrong reads, enough to break dozens of doc boundaries.

## What Survives

- **`tools/preprocess_sweep.py`** — useful research tool for future preprocessing experiments
- **DPI 300 for EasyOCR** — the GPU consumer already renders at DPI 300 independently. This is the correct use of higher DPI: EasyOCR's parser is more robust than Tesseract's regex-based `_parse()`.
- **The pipeline tuple-return pattern** — if a future tier needs to pass images through the queue, the architecture is documented in the reverted commits.

## Future Considerations

- **VLM-based OCR** (see `docs/superpowers/specs/2026-03-25-vlm-resolver-design.md`) may be more promising for failed pages, as vision-language models can understand context beyond regex matching.
- If DPI 300 Tesseract is revisited, it should only be used with a **cross-validation gate**: accept the read only if it agrees with at least one other tier, or if no other tier produced a read.
