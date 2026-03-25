# OCR Confidence Gating + Fallback Split Preprocessing

## Problem

The v4-post-otsu OCR change (commit `80639a8`) replaced Otsu binarization with unsharp mask based on sweep results showing 149 rescues / 42 regressions. In production, ART_670 completeness dropped from 90% (COM=613) to 74% (COM=484).

**Root cause:** The unsharp mask causes Tier 1 to read MORE pages (direct: 775->1639), but some reads produce incorrect curr/total values. Previously those pages failed Tier 1 and fell to SR (Tier 2), which read them correctly. The incorrect Tier 1 reads poison the inference chain. The sweep failed to catch this because it measures parse success (did `_parse()` return non-None?) but never validates parse correctness (are the extracted values right?).

**Secondary root cause:** `_tess_ocr()` uses `pytesseract.image_to_string()` which discards Tesseract's per-word confidence scores. All successful parses get hardcoded confidence=1.0, leaving no signal to distinguish good from bad reads.

## Solution: Sequential Options

### Option A: Confidence Gating (try first)

Modify `_tess_ocr()` in `core/ocr.py` to use `pytesseract.image_to_data()` instead of `image_to_string()`. This returns per-word confidence scores (0-100). After extracting text and running `_parse()`, check the confidence of the digit words that matched the page number pattern. If any digit word is below `CONF_THRESHOLD` (starting at 60), return empty string — the page naturally falls to the next tier.

**Function signature unchanged** — `_tess_ocr(bgr) -> str`. The filtering is internal.

**Flow:**
1. Preprocess (blue ink removal + grayscale + unsharp mask — same as current)
2. `image_to_data()` -> dict with `text[]` and `conf[]` per word
3. Reconstruct full text from word list
4. `_parse(text)` -> curr, total
5. If parsed: find confidence of digit words in the matched region
6. If min digit confidence >= CONF_THRESHOLD: return text (accept)
7. Else: return "" (reject — falls to next tier)

**Constants:**
- `CONF_THRESHOLD = 60` — starting value, conservative

### Option B: Split Preprocessing (if A fails)

Split `_tess_ocr()` into two variants:
- `_tess_ocr_conservative(bgr)`: grayscale + blue ink removal only (no unsharp, no Otsu)
- `_tess_ocr_aggressive(bgr)`: grayscale + blue ink removal + unsharp mask

Update `_process_page()` to use conservative for Tier 1 and aggressive for Tier 2.

**Rationale:** Tier 1 only reads clearly legible numbers. Pages that fail Tier 1 get the aggressive sharpening + SR 4x treatment, which is where unsharp mask actually helps (rescuing degraded text).

## Validation

Run ART_670 (2719 pages) with each option. Compare against baselines:

| Metric | v3.1-fix (target) | v4-post-otsu (regressed) |
|--------|-------------------|--------------------------|
| DOC | 684 | 658 |
| COM | 613 (90%) | 484 (74%) |
| INC | 71 | 174 |
| direct | 775 | 1639 |
| SR | 1157 | 512 |
| failed | 776 | 565 |
| Time | 587s | 435s |

**Success criteria:** COM >= 610 on ART_670 with the winning option.

## Files

| File | Change |
|------|--------|
| `core/ocr.py` | `_tess_ocr()` internals (A) or split into two variants (B) |
| `core/pipeline.py` | MOD tag update |

## Out of Scope

- Sweep methodology fix (needs manual ground truth — separate project)
- Inference engine changes
- EasyOCR tier changes
- Full 21-PDF validation (ART_670 gatekeeper only)
