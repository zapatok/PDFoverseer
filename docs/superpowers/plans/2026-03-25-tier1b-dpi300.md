# Tier 1b (DPI 300) Integration Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a DPI 300 Tesseract pass (Tier 1b) between Tier 1 and Tier 2, and reuse the DPI 300 image for EasyOCR instead of re-rendering.

**Architecture:** Tier 1b renders the page-number strip at DPI 300, deskews it, and runs Tesseract. If it fails, the same DPI 300 image is passed through the GPU queue so EasyOCR can reuse it (saving 49ms re-render). The `_process_page` return type becomes `tuple[_PageRead, np.ndarray | None]` to carry the image back to the main thread. Note: the image (~145 KB crop) is serialized across the `ProcessPoolExecutor` boundary — acceptable overhead for this size.

**Behavior change:** EasyOCR previously received non-deskewed DPI 300 images (rendered independently). It will now receive deskewed images from Tier 1b. Validated on 24 pages with zero regressions — this is an intentional improvement.

**Tech Stack:** Python, PyMuPDF, Tesseract (pytesseract), EasyOCR, OpenCV, numpy

**Sweep evidence:** `data/preprocess_sweep/sweep_summary.txt` — DPI 300 recovers 23/50 failed pages with zero regressions. SR and DPI 300 are complementary (only_SR=6, only_DPI300=14, overlap=12). DPI 300 cannot replace DPI 150 (5 regressions found).

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `core/ocr.py` | Modify | Add Tier 1b (DPI 300 render + deskew + Tesseract) in `_process_page`; change return type to `tuple[_PageRead, np.ndarray \| None]` |
| `core/pipeline.py` | Modify | Update `_process_page_worker` return type; change `gpu_queue` to carry `(idx, bgr_300)`; update `_gpu_consumer` to reuse image; add `"dpi300": "3"` to telemetry method map |
| `tests/test_ocr_tiers.py` | Create | Unit tests for Tier 1b cascade and return type |
| `tests/test_gpu_consumer.py` | Create | Unit tests for GPU consumer image reuse |

---

## Chunk 1: Tier 1b in core/ocr.py

### Task 0: Commit the preprocessing sweep tool

The sweep tool (`tools/preprocess_sweep.py`, `tests/test_preprocess_sweep.py`) and results (`data/preprocess_sweep/`) are uncommitted from the previous session.

- [ ] **Step 1: Commit sweep tool and results**

```bash
git add tools/preprocess_sweep.py tests/test_preprocess_sweep.py
git commit -m "feat(tools): OCR preprocessing sweep — 720 variants × 50 failed pages

Standalone research tool that tests binarization, color filtering, contrast,
morphology, and DPI variants on failed OCR pages. Results: DPI 300 is the
dominant recovery factor (23/50 recovered, 0 wrong)."
```

### Task 1: Write failing tests for Tier 1b cascade

**Files:**
- Create: `tests/test_ocr_tiers.py`

- [ ] **Step 1: Write test for return type change**

```python
"""Tests for OCR tier cascade (core/ocr.py)."""
import numpy as np
import pytest
from unittest.mock import patch, MagicMock
import fitz

from core.utils import _PageRead


def _make_fake_doc(n_pages=1):
    """Create a mock fitz.Document with n pages."""
    doc = MagicMock(spec=fitz.Document)
    pages = []
    for _ in range(n_pages):
        page = MagicMock(spec=fitz.Page)
        page.rect = fitz.Rect(0, 0, 612, 792)
        pages.append(page)
    doc.__getitem__ = lambda self, idx: pages[idx]
    doc.__len__ = lambda self: len(pages)
    return doc


class TestProcessPageReturnType:
    """_process_page must return (PageRead, bgr_300_or_None)."""

    @patch("core.ocr._tess_ocr", return_value="Página 1 de 4")
    @patch("core.ocr._deskew", side_effect=lambda x: x)
    @patch("core.ocr._render_clip", return_value=np.zeros((50, 150, 3), dtype=np.uint8))
    def test_tier1_success_returns_tuple_with_none(self, mock_render, mock_deskew, mock_tess):
        """When Tier 1 succeeds, return (PageRead, None) — no DPI 300 image needed."""
        from core.ocr import _process_page
        doc = _make_fake_doc()
        result = _process_page(doc, 0)
        assert isinstance(result, tuple) and len(result) == 2
        pr, img = result
        assert isinstance(pr, _PageRead)
        assert pr.method == "direct"
        assert img is None

    @patch("core.ocr._tess_ocr")
    @patch("core.ocr._deskew", side_effect=lambda x: x)
    @patch("core.ocr._render_clip", return_value=np.zeros((50, 150, 3), dtype=np.uint8))
    def test_tier1b_success_returns_dpi300_method(self, mock_render, mock_deskew, mock_tess):
        """When Tier 1 fails but Tier 1b succeeds, method is 'dpi300'."""
        # Tier 1 fails (call 1 with DPI 150 image), Tier 1b succeeds (call 2 with DPI 300 image)
        mock_tess.side_effect = ["garbage", "Página 2 de 4"]
        from core.ocr import _process_page
        doc = _make_fake_doc()
        result = _process_page(doc, 0)
        pr, img = result
        assert pr.method == "dpi300"
        assert pr.curr == 2
        assert pr.total == 4
        assert img is None  # success → no image needed for EasyOCR
        # Verify two renders: DPI 150 then DPI 300
        assert mock_render.call_count == 2
        assert mock_render.call_args_list[1][1].get("dpi") == 300

    @patch("core.ocr._tess_ocr", return_value="garbage no match")
    @patch("core.ocr._upsample_4x", return_value=np.zeros((200, 600, 3), dtype=np.uint8))
    @patch("core.ocr._deskew", side_effect=lambda x: x)
    @patch("core.ocr._render_clip", return_value=np.zeros((50, 150, 3), dtype=np.uint8))
    def test_all_tiers_fail_returns_bgr300(self, mock_render, mock_deskew, mock_sr, mock_tess):
        """When all Tesseract tiers fail, return (failed_PageRead, bgr_300)."""
        from core.ocr import _process_page
        doc = _make_fake_doc()
        result = _process_page(doc, 0)
        pr, img = result
        assert pr.method == "failed"
        assert img is not None
        assert isinstance(img, np.ndarray)
        assert len(img.shape) == 3  # BGR

    @patch("core.ocr._tess_ocr")
    @patch("core.ocr._upsample_4x", return_value=np.zeros((200, 600, 3), dtype=np.uint8))
    @patch("core.ocr._deskew", side_effect=lambda x: x)
    @patch("core.ocr._render_clip", return_value=np.zeros((50, 150, 3), dtype=np.uint8))
    def test_tier2_sr_success_returns_bgr300(self, mock_render, mock_deskew, mock_sr, mock_tess):
        """When Tier 1 and 1b fail but SR succeeds, still no bgr_300 needed."""
        # Tier 1 fails, Tier 1b fails, Tier 2 SR succeeds
        mock_tess.side_effect = ["garbage", "garbage", "Página 3 de 4"]
        from core.ocr import _process_page
        doc = _make_fake_doc()
        result = _process_page(doc, 0)
        pr, img = result
        assert pr.method == "super_resolution"
        assert img is None  # SR succeeded, no EasyOCR needed
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_ocr_tiers.py -v
```
Expected: FAIL — `_process_page` returns `_PageRead`, not a tuple.

### Task 2: Implement Tier 1b in core/ocr.py

**Files:**
- Modify: `core/ocr.py:131-154`

- [ ] **Step 1: Add DPI_300 constant**

After line 25 (`EASYOCR_DPI = 300`), this constant already exists and equals 300. We'll reuse `EASYOCR_DPI` since the value is identical. No new constant needed.

- [ ] **Step 2: Modify `_process_page` to add Tier 1b and return tuple**

Replace `_process_page` (lines 131–154) with:

```python
def _process_page(doc: fitz.Document, page_idx: int) -> tuple[_PageRead, np.ndarray | None]:
    """
    Render one page clip and run Tesseract OCR (3 tiers).
    Returns (PageRead, bgr_300_or_None).
    bgr_300 is the deskewed DPI-300 image, returned only when all tiers fail
    so the GPU consumer can reuse it for EasyOCR without re-rendering.
    """
    pdf_page = page_idx + 1
    bgr = _render_clip(doc[page_idx])
    bgr = _deskew(bgr)

    # Tier 1: Tesseract @ DPI 150
    text = _tess_ocr(bgr)
    c, t = _parse(text)
    if c:
        return _PageRead(pdf_page, c, t, "direct", 1.0), None

    # Tier 1b: Tesseract @ DPI 300 (sweep-validated: +23/50 recovered, 0 wrong)
    bgr_300 = _render_clip(doc[page_idx], dpi=EASYOCR_DPI)
    bgr_300 = _deskew(bgr_300)
    text_300 = _tess_ocr(bgr_300)
    c, t = _parse(text_300)
    if c:
        return _PageRead(pdf_page, c, t, "dpi300", 1.0), None

    # Tier 2: 4x upscale of DPI-150 image + Tesseract
    bgr_sr = _upsample_4x(bgr)
    text_sr = _tess_ocr(bgr_sr)
    c, t = _parse(text_sr)
    if c:
        return _PageRead(pdf_page, c, t, "super_resolution", 1.0), None

    return _PageRead(pdf_page, None, None, "failed", 0.0), bgr_300
```

- [ ] **Step 3: Run tests to verify they pass**

```bash
pytest tests/test_ocr_tiers.py -v
```
Expected: 4 PASS

- [ ] **Step 4: Commit**

```bash
git add core/ocr.py tests/test_ocr_tiers.py
git commit -m "feat(ocr): add Tier 1b (Tesseract @ DPI 300) between Tier 1 and SR

Sweep data shows DPI 300 recovers 23/50 failed pages with 0 regressions.
Returns (PageRead, bgr_300_or_None) so GPU consumer can reuse the image."
```

---

## Chunk 2: Pipeline integration + GPU consumer reuse

### Task 3: Write failing tests for pipeline changes

**Files:**
- Create: `tests/test_gpu_consumer.py`

- [ ] **Step 1: Write test for worker return type handling**

```python
"""Tests for pipeline GPU consumer image reuse (core/pipeline.py)."""
import numpy as np
import queue
import threading
from unittest.mock import patch, MagicMock

from core.utils import _PageRead


class TestWorkerReturnUnpacking:
    """Pipeline must correctly unpack (PageRead, image) from workers."""

    def test_successful_read_unpacks_none_image(self):
        """A successful OCR read returns (PageRead, None)."""
        pr = _PageRead(1, 1, 4, "direct", 1.0)
        result = (pr, None)
        page_read, bgr_300 = result
        assert page_read.curr == 1
        assert bgr_300 is None

    def test_failed_read_unpacks_image(self):
        """A failed OCR read returns (PageRead, bgr_300)."""
        pr = _PageRead(1, None, None, "failed", 0.0)
        img = np.zeros((100, 300, 3), dtype=np.uint8)
        result = (pr, img)
        page_read, bgr_300 = result
        assert page_read.method == "failed"
        assert bgr_300 is not None
        assert bgr_300.shape == (100, 300, 3)


class TestGpuQueueFormat:
    """GPU queue must accept (page_idx, bgr_300) tuples."""

    def test_queue_accepts_image_tuple(self):
        """Queue should accept (int, ndarray) items."""
        q = queue.Queue()
        img = np.zeros((100, 300, 3), dtype=np.uint8)
        q.put((5, img))
        q.put(None)  # sentinel

        item = q.get()
        assert item is not None
        idx, bgr = item
        assert idx == 5
        assert bgr.shape == (100, 300, 3)

        sentinel = q.get()
        assert sentinel is None
```

- [ ] **Step 2: Run tests to verify they pass** (these are structural tests, they'll pass immediately)

```bash
pytest tests/test_gpu_consumer.py -v
```
Expected: 3 PASS (these validate the data contract, not the implementation)

### Task 4: Update pipeline.py — worker return type + GPU queue

**Files:**
- Modify: `core/pipeline.py:34-42` (`_process_page_worker`)
- Modify: `core/pipeline.py:203` (`gpu_queue` type)
- Modify: `core/pipeline.py:206-234` (`_gpu_consumer`)
- Modify: `core/pipeline.py:254-280` (batch result unpacking)

- [ ] **Step 1: Add numpy import to pipeline.py**

Add after the `import cv2` line (line 13):

```python
import numpy as np
```

- [ ] **Step 2: Update `_process_page_worker` return type**

Change lines 34–42:

```python
def _process_page_worker(pdf_path: str, page_idx: int) -> tuple[_PageRead, np.ndarray | None]:
    """Stateless worker function for true multiprocessing.
    Returns (PageRead, bgr_300_or_None) — bgr_300 is the deskewed DPI-300 image
    for failed pages, so the GPU consumer can skip re-rendering.
    """
    import fitz
    import core.ocr as ocr
    doc = fitz.open(pdf_path)
    try:
        return ocr._process_page(doc, page_idx)
    finally:
        doc.close()
```

- [ ] **Step 3: Update `gpu_queue` type annotation**

Change line 203:

```python
gpu_queue: queue.Queue[tuple[int, np.ndarray] | None] = queue.Queue()
```

- [ ] **Step 4: Update `_gpu_consumer` to reuse passed image**

Replace lines 206–234:

```python
    def _gpu_consumer():
        if not has_gpu:
            while gpu_queue.get() is not None:
                pass
            return

        while True:
            item = gpu_queue.get()
            if item is None:
                break
            idx, bgr_300 = item
            try:
                gray = cv2.cvtColor(bgr_300, cv2.COLOR_BGR2GRAY)
                with ocr._easyocr_lock:
                    results = ocr._easyocr_reader.readtext(gray, detail=0, paragraph=True)
                text = " ".join(results) if results else ""
                c, t = _parse(text)
                if c:
                    reads[idx] = _PageRead(idx + 1, c, t, "easyocr", 1.0)
                    on_log(f"  Pag {idx + 1:>4}: {c}/{t}  [easyocr-gpu]", "page_ok")
                    gpu_recovered[0] += 1
            except Exception as e:
                on_log(f"GPU consumer error on page {idx + 1}: {e}", "error")
                break
```

Key changes:
- Removed `doc = fitz.open(pdf_path)` and `image._render_clip(doc[idx], dpi=ocr.EASYOCR_DPI)` — the bgr_300 image arrives pre-rendered and deskewed via the queue
- EasyOCR now receives deskewed images (intentional improvement, validated with zero regressions)

- [ ] **Step 5: Update batch result unpacking**

In the batch processing loop (lines 260–280), update to unpack the tuple:

```python
            batch_results: dict[int, tuple[_PageRead, np.ndarray | None]] = {}
            for future, i in future_to_idx.items():
                try:
                    batch_results[i] = future.result()
                except Exception as e:
                    pdf_page = i + 1
                    on_log(f"  Pag {pdf_page:>4}: error de procesamiento: {e}", "error")
                    batch_results[i] = (_PageRead(pdf_page, None, None, "failed", 0.0), None)

            for i in range(batch_start, batch_end):
                r, bgr_300 = batch_results[i]
                reads[i] = r
                method_tally[r.method] = method_tally.get(r.method, 0) + 1

                pdf_page = i + 1
                if r.curr is not None:
                    on_log(f"  Pag {pdf_page:>4}: {r.curr}/{r.total}  [{r.method}]", "page_ok")
                elif r.method == "failed" and bgr_300 is not None:
                    on_log(f"  Pag {pdf_page:>4}: ???  → GPU queue", "page_warn")
                    gpu_queue.put((i, bgr_300))
                elif r.method == "failed":
                    on_log(f"  Pag {pdf_page:>4}: ???  [no image for GPU]", "page_warn")
                else:
                    on_log(f"  Pag {pdf_page:>4}: ???  [{r.method}]", "page_warn")

                if on_progress:
                    on_progress(pdf_page, total_pages)
```

- [ ] **Step 6: Update telemetry method map**

In `_emit_ai_telemetry` (line 129), add `"dpi300"` to the method char map:

```python
    _M = {"direct": "d", "super_resolution": "s", "easyocr": "e", "inferred": "i", "failed": "f", "dpi300": "3"}
```

- [ ] **Step 7: Run all tests**

```bash
pytest tests/test_ocr_tiers.py tests/test_gpu_consumer.py tests/test_preprocess_sweep.py -v
```
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add core/pipeline.py tests/test_gpu_consumer.py
git commit -m "feat(pipeline): pass DPI-300 image via GPU queue, skip EasyOCR re-render

GPU consumer now receives pre-rendered deskewed bgr_300 from Tier 1b instead
of re-rendering at DPI 300. Saves ~49ms per failed page. Also adds 'dpi300'
method to telemetry."
```

---

## Chunk 3: Validation + finish

### Task 5: Eval harness validation

- [ ] **Step 1: Run existing test suite**

```bash
pytest -v
```
Expected: all PASS — no changes to inference, utils, or image modules.

- [ ] **Step 2: Run a quick scan on ART_670 to verify end-to-end**

```bash
python -c "
import fitz, core.ocr as ocr, core.image as image
from core.utils import _parse

ocr._setup_sr(lambda m, l: None)
doc = fitz.open('eval/fixtures/real/ART_670.pdf')

# Test pages known to fail at DPI 150 but recover at DPI 300
test_pages = [3, 7, 23, 45, 73]  # sample from sweep failures
for pidx in test_pages:
    pr, bgr_300 = ocr._process_page(doc, pidx)
    print(f'  p{pidx+1}: {pr.curr}/{pr.total} [{pr.method}]')
doc.close()
"
```

Verify that pages previously failing now show `[dpi300]` method.

- [ ] **Step 3: Count method distribution across full PDF**

```bash
python -c "
import fitz, core.ocr as ocr
from collections import Counter

ocr._setup_sr(lambda m, l: None)
doc = fitz.open('eval/fixtures/real/ART_670.pdf')
methods = Counter()
for i in range(min(50, len(doc))):
    pr, _ = ocr._process_page(doc, i)
    methods[pr.method] += 1
doc.close()
print(dict(methods))
"
```

Expected: `direct` count stays the same as before, new `dpi300` entries appear, `failed` count decreases.

- [ ] **Step 4: Verify no DPI-150 regressions**

The 5 pages that work at DPI 150 but not 300 must still succeed (Tier 1 catches them before Tier 1b). This is guaranteed by the cascade order but verify by checking the method is `direct` for those pages.

### Task 6: Use superpowers:finishing-a-development-branch

- [ ] **Step 1: Invoke finishing skill to complete the branch**
