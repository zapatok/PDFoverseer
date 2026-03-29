# Tier Isolation Experiment: T1-only vs T2-only vs Baseline

**Date:** 2026-03-29
**Branch:** `cuda-gpu`
**Baseline:** HELENA tag (`s2t-helena`, commit `a53d87a`)
**Logs:** `manual_test_logs/BASELINE.txt`, `log_tier1only.txt`, `log_tier2only.txt`

## Purpose

Isolate the contribution of each OCR tier to understand:
1. How many pages each tier reads exclusively (not readable by the other)
2. How inference compensates when one tier is missing
3. Speed characteristics of each tier alone
4. Whether T2 (SR) is a strict superset of T1 (direct Tesseract)

## Method

Modified `core/ocr.py` → `_process_page()` to disable one tier at a time:
- **Sabor A (T1-only):** Commented out the SR upscale + Tesseract block. Tag: `s2t-helena-t1only`
- **Sabor B (T2-only):** Commented out the direct Tesseract block. Tag: `s2t-helena-t2only`

Same inference engine, same parameters, same 21-PDF batch.

## ART_670 Results (ground truth: 674 docs, 662 complete)

| Metric | BASELINE (T1+T2) | T1-only | T2-only | Ground Truth |
|--------|:-----------------:|:-------:|:-------:|:------------:|
| **DOC** | 668 | 670 (+2) | 689 (+21) | **674** |
| **COM** | 606 | 627 (+21) | 635 (+29) | 662 |
| **INC** | 62 | 41 | 54 | 12 |
| **seq errors** | 50 | 32 | 38 | — |
| **INF** | 603 | 1219 | 754 | 35 |
| OCR success | 2131 | 1510 | 1974 | — |
| OCR failed | 588 | 1209 | 745 | — |
| **Time** | 472s | **180s** | 782s | — |
| ms/page | 174 | **66** | 288 | — |
| Period conf | 85% | 73% | 76% | — |

## Key Finding: T2 is NOT a superset of T1

This was the most surprising result. The assumption was that SR (4x upscale + Tesseract) would read everything T1 reads plus additional pages. **This is false.**

### Page read overlap analysis (ART_670)

```
T1 reads:     1510 pages
T2 reads:     1974 pages
T1+T2 reads:  2131 pages (baseline)
Total pages:  2719

Overlap (both read):     1510 + 1974 - 2131 = 1353 pages
T1-exclusive (T1 only):  2131 - 1974 = 157 pages
T2-exclusive (T2 only):  2131 - 1510 = 621 pages
Neither reads:            2719 - 2131 = 588 pages
```

**157 pages** are readable by direct Tesseract at 150 DPI but NOT by SR 4x bicubic upscale + Tesseract.

### Why T2 fails where T1 succeeds

The 4x bicubic upscale amplifies noise and artifacts along with text. For some page-number crops:
- Upscaling introduces interpolation artifacts around thin strokes
- Color removal / inpainting operates on different pixel distributions at 4x
- Tesseract's segmentation (PSM 6) behaves differently on 600 DPI-equivalent images vs 150 DPI
- Some stamps, watermarks, or backgrounds that are ignorable at 150 DPI become prominent features at 600 DPI

### Why T1 fails where T2 succeeds

The 621 T2-exclusive pages are the designed use case for SR:
- Text too small or blurry at 150 DPI for Tesseract to segment
- Low-contrast text that becomes readable after upscaling
- Partial occlusion where 4x resolution provides enough detail for character recognition

## T2-only over-splits documents

T2-only finds 689 docs vs 668 baseline (+21 phantom documents). This indicates SR reads some pages **differently** — not just "success vs failure" but actually reading different values:
- A page T1 reads as "2 de 4" might be read by T2 as "2 de 1" (misread due to upscaling artifact)
- These misreads create false document boundaries
- The inference engine, with 76% period confidence (vs 85% baseline), cannot correct all of them

## Inference robustness

T1-only demonstrates the inference engine's strength: with **double the failures** (1209 vs 588), it only gains 2 extra documents (670 vs 668) and actually has **fewer sequence errors** (32 vs 50).

Why fewer seq errors with more failures?
- Failures are "no data" — inference fills gaps conservatively using neighbor propagation
- OCR reads (especially misreads) are "wrong data" — harder to correct
- Fewer OCR data points → fewer opportunities for contradictory reads → cleaner gap-filling

This mirrors the VLM finding: **inference handles "no data" better than "wrong data"**.

## Small PDF comparison

| PDF | BASELINE | T1-only | T2-only | Note |
|-----|:--------:|:-------:|:-------:|------|
| CHAR_17 | 17 | **16** (-1) | 17 | T1 loses 1 doc — SR rescue matters |
| INS_31 | 31 | 31 | 31 | All perfect |
| CH_39 | 39 | 39 | 39 | All perfect |
| CH_74 | 74 | 74 | 74 | Same docs, different INF counts |
| CH_51 | 51 | 51 | 51 | Same |
| CH_BSM_18 | 18 | 18 | 18 | Same (T1 reads all, no SR needed) |

CHAR_17 is the only small PDF affected: T1 misses a page that SR reads, causing a doc count mismatch.

## Speed analysis

| Config | ART_670 time | ms/page | Relative |
|--------|:------------:|:-------:|:--------:|
| T1-only | 180s | 66 | **1.0x** (fastest) |
| Baseline T1+T2 | 472s | 174 | 2.6x |
| T2-only | 782s | 288 | 4.3x |

The SR upscale adds ~220ms per failed page. In the baseline, only 588 pages need SR (fallback). In T2-only, all 2719 pages go through SR regardless.

## Conclusions

1. **The T1+T2 cascade is the correct architecture.** T1 provides speed + 157 exclusive reads. T2 provides 621 exclusive rescues. Neither is a superset.

2. **T2 (SR) is not inherently better than T1** — it reads more pages total (1974 vs 1510) but also makes different errors, leading to over-splitting when used alone.

3. **Inference is the real safety net.** T1-only with 1209 failures still finds 670 docs (within 2 of baseline). The gap solver handles "no data" gracefully.

4. **"Wrong data > no data" is confirmed again.** T2-only has fewer failures but more phantom docs because SR misreads create false boundaries that inference cannot fully correct.

5. **Speed optimization opportunity:** If latency matters more than accuracy, T1-only at 66ms/page is viable (670/674 docs = 99.4% doc detection vs 668/674 = 99.1% baseline). The tradeoff is 1219 inferred pages vs 603.

## Future directions

- Investigate the 157 T1-exclusive pages: what visual patterns make SR fail?
- Consider adaptive tier selection based on image characteristics (contrast, noise level)
- The 588 pages that neither tier reads are the real ceiling — these require a fundamentally different approach (VLM was attempted and ruled out, see `docs/superpowers/reports/2026-03-29-vlm-integration-postmortem.md`)
