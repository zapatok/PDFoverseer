# OCR Confidence Gating Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the v4-post-otsu regression on ART_670 (COM 90%→74%) by adding Tesseract confidence filtering, with split-preprocessing fallback if confidence gating isn't enough.

**Architecture:** Two sequential options. Option A adds confidence gating to `_tess_ocr()` using `pytesseract.image_to_data()` — keeps unsharp mask but filters low-confidence digit reads. Option B splits preprocessing: Tier 1 gets conservative (no unsharp), Tier 2 gets aggressive (unsharp + SR). Both options modify only `core/ocr.py`.

**Tech Stack:** pytesseract (image_to_data API), OpenCV, NumPy

**Spec:** `docs/superpowers/specs/2026-03-25-ocr-confidence-gating-design.md`

---

## File Map

| File | Role | Changes |
|------|------|---------|
| `core/ocr.py` | OCR pipeline | Option A: rewrite `_tess_ocr()` internals. Option B: split into two functions, update `_process_page()` |
| `core/pipeline.py:110` | MOD tag | Update version string |
| `tests/test_ocr_confidence.py` | New test file | Unit tests for confidence filtering logic |

---

## Task 1: Add confidence-aware OCR helper (Option A)

**Files:**
- Modify: `core/ocr.py:109-136` (`_tess_ocr` function)
- Modify: `core/ocr.py:1-14` (imports)
- Create: `tests/test_ocr_confidence.py`

### Context for implementer

`_tess_ocr(bgr)` currently returns a raw string from `pytesseract.image_to_string()`. The caller (`_process_page`) runs `_parse(text)` to extract `(curr, total)`. There is no confidence signal — all parses are trusted equally.

`pytesseract.image_to_data()` returns a dict with keys including `text` (list of words) and `conf` (list of int confidences, 0-100, -1 for non-text blocks). We need to:
1. Call `image_to_data()` instead of `image_to_string()`
2. Reconstruct the full text from the word list
3. Check if `_parse()` finds a match in that text
4. If it does, find the confidence of the words containing the matched digits
5. If min digit confidence < threshold, return "" (forces fallback to next tier)
6. Otherwise return the full text as before

The tricky part: `_parse()` operates on the full text string, but confidence is per-word. We need to map the regex match back to specific words to get their confidence. The simplest approach: instead of mapping, just find the minimum confidence across ALL numeric words in the text. Page number strips are small (the crop is ~30% width × 22% height), so there are few words total. If ANY digit word has low confidence, we reject the whole read.

- [ ] **Step 1: Write tests for the confidence filtering logic**

Create `tests/test_ocr_confidence.py`:

```python
"""Tests for OCR confidence filtering in _tess_ocr."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock
import numpy as np

from core.ocr import _tess_ocr, CONF_THRESHOLD


def _make_data_output(words_and_confs: list[tuple[str, int]]) -> dict:
    """Build a pytesseract.image_to_data()-style dict from word/conf pairs."""
    return {
        "text": [w for w, _ in words_and_confs],
        "conf": [c for _, c in words_and_confs],
    }


class TestConfidenceGating:
    """Test that _tess_ocr filters low-confidence digit reads."""

    @patch("core.ocr.pytesseract")
    def test_high_confidence_digits_accepted(self, mock_tess):
        """Digits with confidence >= threshold should pass through."""
        mock_tess.image_to_data.return_value = _make_data_output([
            ("Página", 90), ("1", 85), ("de", 92), ("5", 88),
        ])
        mock_tess.Output = MagicMock()
        gray = np.zeros((50, 200), dtype=np.uint8)
        result = _tess_ocr(gray)
        assert "1" in result and "5" in result

    @patch("core.ocr.pytesseract")
    def test_low_confidence_digit_rejected(self, mock_tess):
        """If ANY digit word has confidence < threshold, return empty."""
        mock_tess.image_to_data.return_value = _make_data_output([
            ("Página", 90), ("1", 30), ("de", 92), ("5", 88),
        ])
        mock_tess.Output = MagicMock()
        gray = np.zeros((50, 200), dtype=np.uint8)
        result = _tess_ocr(gray)
        assert result.strip() == ""

    @patch("core.ocr.pytesseract")
    def test_no_digits_returns_text(self, mock_tess):
        """Text without digits should pass through (no filtering)."""
        mock_tess.image_to_data.return_value = _make_data_output([
            ("hello", 90), ("world", 85),
        ])
        mock_tess.Output = MagicMock()
        gray = np.zeros((50, 200), dtype=np.uint8)
        result = _tess_ocr(gray)
        assert "hello" in result

    @patch("core.ocr.pytesseract")
    def test_negative_conf_ignored(self, mock_tess):
        """Confidence of -1 (non-text blocks) should be ignored, not treated as low."""
        mock_tess.image_to_data.return_value = _make_data_output([
            ("", -1), ("Página", 90), ("3", 75), ("de", 88), ("4", 80), ("", -1),
        ])
        mock_tess.Output = MagicMock()
        gray = np.zeros((50, 200), dtype=np.uint8)
        result = _tess_ocr(gray)
        assert "3" in result and "4" in result

    def test_conf_threshold_is_reasonable(self):
        """Threshold should be between 30 and 90."""
        assert 30 <= CONF_THRESHOLD <= 90
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ocr_confidence.py -v`
Expected: ImportError for `CONF_THRESHOLD` (doesn't exist yet)

- [ ] **Step 3: Implement confidence gating in `_tess_ocr`**

Modify `core/ocr.py`. Add the constant and rewrite `_tess_ocr`:

```python
# Add after line 25 (EASYOCR_DPI = 300):
CONF_THRESHOLD = 60  # min Tesseract word confidence for digit words (0-100)
```

Replace the entire `_tess_ocr` function (lines 111-136) with:

```python
def _tess_ocr(bgr: np.ndarray) -> str:
    """OCR a page-number strip. Returns text only if digit confidence >= CONF_THRESHOLD."""
    # If image is already grayscale, skip HSV filtering
    if len(bgr.shape) == 2 or bgr.shape[2] == 1:
        gray = bgr
    else:
        # Convert to HSV to detect specific ink colors
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

        # Define typical Hue ranges for Blue ink (often 90 to 150)
        lower_blue = np.array([90, 50, 50])
        upper_blue = np.array([150, 255, 255])
        mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)

        # Inpaint removes the masked pixels and interpolates the background
        bgr_clean = cv2.inpaint(bgr, mask_blue, 3, cv2.INPAINT_NS)

        gray = cv2.cvtColor(bgr_clean, cv2.COLOR_BGR2GRAY)

    # Unsharp mask: sharpen blurred text (sweep-tuned: sigma=1.0, strength=0.3)
    blurred = cv2.GaussianBlur(gray, (0, 0), 1.0)
    gray = cv2.addWeighted(gray, 1.3, blurred, -0.3, 0)

    # Use image_to_data for per-word confidence instead of image_to_string
    data = pytesseract.image_to_data(
        gray, lang="eng", config=TESS_CONFIG,
        output_type=pytesseract.Output.DICT,
    )

    words = data["text"]
    confs = data["conf"]

    # Reconstruct full text
    text = " ".join(w for w in words if w.strip())

    # Check confidence of digit-containing words
    digit_confs = [
        int(confs[i])
        for i in range(len(words))
        if words[i].strip() and any(ch.isdigit() for ch in words[i]) and int(confs[i]) >= 0
    ]

    # If there are digit words with low confidence, reject the entire read
    if digit_confs and min(digit_confs) < CONF_THRESHOLD:
        return ""

    return text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ocr_confidence.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Run existing test suite**

Run: `pytest tests/ -v`
Expected: All existing tests still pass (no regressions)

- [ ] **Step 6: Update MOD tag**

In `core/pipeline.py:110`, change `[MOD:v4-post-otsu]` to `[MOD:v5-conf-gate]`.

- [ ] **Step 7: Commit**

```bash
git add core/ocr.py core/pipeline.py tests/test_ocr_confidence.py
git commit -m "feat(ocr): add confidence gating to _tess_ocr [v5-conf-gate]

Use pytesseract.image_to_data() for per-word confidence scores.
Reject page-number reads where any digit word has confidence < 60.
Low-confidence reads fall to the next tier (SR or EasyOCR) instead
of poisoning the inference chain with wrong values."
```

---

## Task 2: Validate Option A on ART_670

**Files:**
- None modified — this is a production test

- [ ] **Step 1: Run ART_670 scan**

Start the backend server and scan ART_670 through the UI or API. Capture the `[AI:]` log block output.

- [ ] **Step 2: Compare against baselines**

Check these metrics from the `[AI:]` log:

| Metric | v3.1-fix (target) | v4-post-otsu (bad) | v5-conf-gate (new) |
|--------|-------------------|--------------------|--------------------|
| DOC | 684 | 658 | ? |
| COM | 613 (90%) | 484 (74%) | target ≥ 610 |
| INC | 71 | 174 | ? |
| direct | 775 | 1639 | ? |
| SR | 1157 | 512 | ? |
| failed | 776 | 565 | ? |

**Success criteria:** COM ≥ 610 on ART_670.

- [ ] **Step 3: Decision gate**

- If COM ≥ 610: **Option A wins.** Proceed to Task 4 (final commit + cleanup).
- If COM < 610 but improved over v4-post-otsu (COM > 484): Try adjusting CONF_THRESHOLD (e.g., 50 or 70) and re-run. If still < 610 after one adjustment, proceed to Task 3 (Option B).
- If COM ≤ 484 (worse or equal): Skip threshold tuning, proceed directly to Task 3 (Option B).

---

## Task 3: Split Preprocessing Fallback (Option B)

**Only execute this task if Option A fails the ART_670 validation.**

**Files:**
- Modify: `core/ocr.py:109-163` (`_tess_ocr` and `_process_page`)
- Modify: `tests/test_ocr_confidence.py` (update tests)

- [ ] **Step 1: Replace `_tess_ocr` with two variants**

Remove the confidence gating code from Task 1. Replace `_tess_ocr` with:

```python
def _preprocess_gray(bgr: np.ndarray) -> np.ndarray:
    """Shared preprocessing: blue ink removal + grayscale conversion."""
    if len(bgr.shape) == 2 or bgr.shape[2] == 1:
        return bgr

    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    lower_blue = np.array([90, 50, 50])
    upper_blue = np.array([150, 255, 255])
    mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)
    bgr_clean = cv2.inpaint(bgr, mask_blue, 3, cv2.INPAINT_NS)
    return cv2.cvtColor(bgr_clean, cv2.COLOR_BGR2GRAY)


def _tess_ocr(bgr: np.ndarray, apply_unsharp: bool = False) -> str:
    """OCR a page-number strip. apply_unsharp=True for Tier 2 (aggressive rescue)."""
    gray = _preprocess_gray(bgr)

    if apply_unsharp:
        blurred = cv2.GaussianBlur(gray, (0, 0), 1.0)
        gray = cv2.addWeighted(gray, 1.3, blurred, -0.3, 0)

    return pytesseract.image_to_string(gray, lang="eng", config=TESS_CONFIG)
```

- [ ] **Step 2: Update `_process_page` to use split preprocessing**

Replace lines 140-163:

```python
def _process_page(doc: fitz.Document, page_idx: int) -> _PageRead:
    """
    Render one page clip and run Tesseract OCR (2 tiers).
    Tier 1: conservative (no unsharp) — only reads clearly legible numbers.
    Tier 2: aggressive (unsharp + SR 4x) — rescues degraded text.
    """
    pdf_page = page_idx + 1
    bgr = _render_clip(doc[page_idx])
    bgr = _deskew(bgr)

    # Tier 1: Tesseract direct, conservative preprocessing
    text = _tess_ocr(bgr, apply_unsharp=False)
    c, t = _parse(text)
    if c:
        return _PageRead(pdf_page, c, t, "direct", 1.0)

    # Tier 2: 4x upscale + aggressive preprocessing (unsharp mask)
    bgr_sr = _upsample_4x(bgr)
    text_sr = _tess_ocr(bgr_sr, apply_unsharp=True)
    c, t = _parse(text_sr)
    if c:
        return _PageRead(pdf_page, c, t, "super_resolution", 1.0)

    return _PageRead(pdf_page, None, None, "failed", 0.0)
```

- [ ] **Step 3: Update tests**

Update `tests/test_ocr_confidence.py` — remove confidence-specific tests, add split preprocessing tests:

```python
"""Tests for OCR split preprocessing in _tess_ocr."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock, call
import numpy as np

from core.ocr import _tess_ocr, _preprocess_gray


class TestPreprocessGray:
    def test_grayscale_passthrough(self):
        """Already-grayscale images skip HSV filtering."""
        gray = np.zeros((50, 200), dtype=np.uint8)
        result = _preprocess_gray(gray)
        assert result.shape == (50, 200)

    def test_bgr_converts_to_gray(self):
        """BGR images get blue ink removal + grayscale conversion."""
        bgr = np.zeros((50, 200, 3), dtype=np.uint8)
        result = _preprocess_gray(bgr)
        assert len(result.shape) == 2  # grayscale output


class TestSplitPreprocessing:
    @patch("core.ocr.pytesseract")
    @patch("core.ocr.cv2")
    def test_no_unsharp_by_default(self, mock_cv2, mock_tess):
        """Tier 1 (apply_unsharp=False) should NOT call GaussianBlur."""
        mock_tess.image_to_string.return_value = "Página 1 de 5"
        gray = np.zeros((50, 200), dtype=np.uint8)
        _tess_ocr(gray, apply_unsharp=False)
        mock_cv2.GaussianBlur.assert_not_called()

    @patch("core.ocr.pytesseract")
    @patch("core.ocr.cv2")
    def test_unsharp_when_requested(self, mock_cv2, mock_tess):
        """Tier 2 (apply_unsharp=True) should apply GaussianBlur + addWeighted."""
        mock_tess.image_to_string.return_value = "Página 1 de 5"
        mock_cv2.GaussianBlur.return_value = np.zeros((50, 200), dtype=np.uint8)
        mock_cv2.addWeighted.return_value = np.zeros((50, 200), dtype=np.uint8)
        gray = np.zeros((50, 200), dtype=np.uint8)
        _tess_ocr(gray, apply_unsharp=True)
        mock_cv2.GaussianBlur.assert_called_once()
        mock_cv2.addWeighted.assert_called_once()
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_ocr_confidence.py tests/ -v`
Expected: All tests pass

- [ ] **Step 5: Update MOD tag**

In `core/pipeline.py:110`, change `[MOD:v5-conf-gate]` to `[MOD:v5-split-preproc]`.

- [ ] **Step 6: Commit**

```bash
git add core/ocr.py core/pipeline.py tests/test_ocr_confidence.py
git commit -m "feat(ocr): split preprocessing — conservative Tier 1, aggressive Tier 2

Tier 1: grayscale + blue ink removal only (no unsharp mask).
Tier 2: unsharp mask + SR 4x (rescues degraded text).
Replaces confidence gating (Option A) which did not meet targets."
```

- [ ] **Step 7: Validate on ART_670**

Re-run ART_670 scan. Same success criteria: COM ≥ 610.

---

## Task 4: Final Cleanup

**Execute after the winning option is validated.**

- [ ] **Step 1: Update `core/README.md` section 3**

Update the `ocr.py` documentation to reflect whichever option won (confidence gating or split preprocessing).

- [ ] **Step 2: Commit cleanup**

```bash
git add core/README.md
git commit -m "docs(core): update ocr.py docs for v5 preprocessing"
```
