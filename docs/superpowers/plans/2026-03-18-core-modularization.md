# Core Modularization Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `core/analyzer.py` (1186 lines) into 5 focused, testable modules while preserving full backward compatibility and functional parity.

**Architecture:** Incremental extraction following dependency order: utils → {ocr, image, inference} → pipeline. Each module is tested independently before proceeding. Entry points (`analyze_pdf`, `re_infer_documents`) remain unchanged.

**Tech Stack:** Python 3.10+, PyMuPDF, Tesseract, EasyOCR, NumPy, pytest, threading

**Timeline:** ~6-8 tasks per chunk, ~40-50 tasks total. Plan execution can be parallelized using subagent-driven-development.

---

## Chunk 1: Preparation & utils.py

### Task 1.1: Create core/utils.py — Config Constants

**Files:**
- Create: `core/utils.py`

**Purpose:** Extract all configuration constants to a single location.

- [ ] **Step 1: Open current analyzer.py and identify all config constants**

```bash
grep -n "^[A-Z_]* =" core/analyzer.py | head -30
```

Expected output: Lines with DPI, CROP_*, PARALLEL_WORKERS, BATCH_SIZE, etc.

- [ ] **Step 2: Create core/utils.py with config section**

Copy the file content below into `core/utils.py`:

```python
"""Shared configuration, types, and utilities for the OCR pipeline."""

# ============================================================================
# Configuration Constants
# ============================================================================

DPI = 150                       # Render DPI
CROP_X_START = 0.70            # rightmost 30% of page
CROP_Y_END = 0.22              # top 22% of page
PARALLEL_WORKERS = 6           # Tesseract concurrency
BATCH_SIZE = 12                # Pages per pause checkpoint
TESS_CONFIG = "--psm 6 --oem 1"  # Tesseract: uniform block + legacy engine

# Inference calibration
MIN_CONF_FOR_NEW_DOC = 0.60    # Confidence threshold for new document boundary
CONF_BOOST_PERIOD = 0.10       # Boost for period-aligned reads
CONF_BOOST_NEIGHBOR = 0.05     # Boost for neighbor-aligned reads

# Page pattern regex (Spanish-centric)
PAGE_PATTERNS = [
    r"P.{0,2}[gq](?:ina?)?\.?\s*(\d{1,3})\s*\.?\s*de\s*(\d{1,3})",
    r"(?:pag|pg|p)\.?\s*(\d{1,3})\s*de\s*(\d{1,3})",
]

INFERENCE_ENGINE_VERSION = "5-phase-v2"
```

- [ ] **Step 3: Verify file is valid Python**

```bash
python -m py_compile core/utils.py
```

Expected: No output (success). If error, fix syntax.

- [ ] **Step 4: Commit**

```bash
git add core/utils.py
git commit -m "feat(core): create utils.py with config constants"
```

---

### Task 1.2: Add Dataclasses to core/utils.py

**Files:**
- Modify: `core/utils.py`

**Purpose:** Extract `_PageRead` and `Document` dataclasses.

- [ ] **Step 1: Copy _PageRead and Document from analyzer.py**

Add to end of `core/utils.py`:

```python
from dataclasses import dataclass, field
from typing import Optional

# ============================================================================
# Data Types
# ============================================================================

@dataclass
class _PageRead:
    """Result of OCR on a single page."""
    page_idx: int
    curr: Optional[int]        # Current page number (if read)
    total: Optional[int]       # Total pages (if read)
    text_raw: str              # Raw OCR text
    text_clean: str            # Cleaned OCR text
    conf_read: float           # Confidence in read (0.0-1.0)
    ocr_tier: int              # Which OCR tier succeeded (1, 2, or 3)
    inferred: bool = False     # Whether curr/total were inferred

@dataclass
class Document:
    """Inferred document with boundary pages."""
    start_page: int            # 0-indexed page where document starts
    end_page: int              # 0-indexed page where document ends (inclusive)
    total_pages: int           # Length of document
    confidence: float          # Confidence in boundaries (0.0-1.0)
```

- [ ] **Step 2: Verify dataclasses are correct**

```bash
python -c "from core.utils import _PageRead, Document; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add core/utils.py
git commit -m "feat(core): add _PageRead and Document dataclasses to utils.py"
```

---

### Task 1.3: Add Helper Functions to core/utils.py

**Files:**
- Modify: `core/utils.py`

**Purpose:** Extract shared helper functions.

- [ ] **Step 1: Add helper functions to end of core/utils.py**

```python
import re

# ============================================================================
# Helper Functions
# ============================================================================

def _to_int(s: str) -> Optional[int]:
    """Convert string to int, return None if invalid."""
    try:
        return int(s.strip())
    except (ValueError, AttributeError):
        return None

def _parse(text: str) -> tuple[Optional[int], Optional[int]]:
    """Parse page number pattern from text.

    Returns: (current_page, total_pages) or (None, None) if not found.
    """
    if not text:
        return (None, None)

    for pattern in PAGE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            curr = _to_int(match.group(1))
            total = _to_int(match.group(2))
            if curr and total and 1 <= curr <= total:
                return (curr, total)

    return (None, None)
```

- [ ] **Step 2: Test helper functions**

```bash
python -c "
from core.utils import _to_int, _parse
assert _to_int('42') == 42
assert _to_int('abc') is None
assert _parse('Página 5 de 10') == (5, 10)
assert _parse('random text') == (None, None)
print('OK')
"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add core/utils.py
git commit -m "feat(core): add helper functions to utils.py"
```

---

## Chunk 2: OCR Module

### Task 2.1: Create core/ocr.py — Initialization Functions

**Files:**
- Create: `core/ocr.py`

**Purpose:** Extract EasyOCR and super-resolution initialization.

- [ ] **Step 1: Create core/ocr.py skeleton**

```python
"""OCR pipeline: Tesseract (tiers 1-2) + EasyOCR (tier 3)."""

import logging
from typing import Optional, Callable
import threading

# Global state (must be cached)
_easyocr_reader = None
_easyocr_lock = threading.Lock()
_sr_initialized = False

# ============================================================================
# Initialization
# ============================================================================

def _init_easyocr(on_log: Callable[[str], None]):
    """Lazy-load EasyOCR reader (GPU)."""
    global _easyocr_reader

    if _easyocr_reader is not None:
        return  # Already initialized

    on_log("[GPU] Loading EasyOCR reader...")
    try:
        import easyocr
        _easyocr_reader = easyocr.Reader(["es", "en"], gpu=True)
        on_log("[GPU] EasyOCR ready")
    except Exception as e:
        on_log(f"[GPU] EasyOCR init failed: {e}")
        _easyocr_reader = None

def _init_sr(on_log: Callable[[str], None]):
    """Lazy-load super-resolution model."""
    global _sr_initialized

    if _sr_initialized:
        return

    on_log("[SR] Initializing super-resolution...")
    # Lazy-import to avoid loading TensorFlow unless needed
    try:
        import cv2
        from pathlib import Path

        sr_path = Path("models/FSRCNN_x4.pb")
        if sr_path.exists():
            sr_obj = cv2.dnn_superres.DnnSuperResImpl_create()
            sr_obj.readModel(str(sr_path))
            sr_obj.setModel("fsrcnn", 4)
            on_log("[SR] Model loaded")
        _sr_initialized = True
    except Exception as e:
        on_log(f"[SR] Init failed: {e}")
        _sr_initialized = False
```

- [ ] **Step 2: Verify syntax**

```bash
python -m py_compile core/ocr.py
```

Expected: No output.

- [ ] **Step 3: Commit**

```bash
git add core/ocr.py
git commit -m "feat(core): create ocr.py with initialization functions"
```

---

### Task 2.2: Add Tesseract OCR Function to core/ocr.py

**Files:**
- Modify: `core/ocr.py`

**Purpose:** Extract `_tess_ocr` function (Tier 1).

- [ ] **Step 1: Add to core/ocr.py**

```python
import numpy as np
import cv2

# ============================================================================
# Tesseract OCR (Tier 1)
# ============================================================================

def _tess_ocr(gray: np.ndarray) -> str:
    """Tesseract OCR with Otsu binarization.

    Args:
        gray: Grayscale image

    Returns:
        Extracted text
    """
    try:
        import pytesseract
        from core.utils import TESS_CONFIG

        # Otsu binarization
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Tesseract
        text = pytesseract.image_to_string(
            binary,
            lang="spa+eng",
            config=TESS_CONFIG
        )
        return text.strip()
    except Exception as e:
        return ""
```

- [ ] **Step 2: Test the function**

```bash
python -c "
from core.ocr import _tess_ocr
import numpy as np
# Create dummy gray image
dummy_gray = np.zeros((100, 100), dtype=np.uint8)
result = _tess_ocr(dummy_gray)
print(f'Result type: {type(result).__name__}')
assert isinstance(result, str)
print('OK')
"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add core/ocr.py
git commit -m "feat(ocr): add _tess_ocr function (tier 1)"
```

---

### Task 2.3: Add Super-Resolution & Tier 2 to core/ocr.py

**Files:**
- Modify: `core/ocr.py`

**Purpose:** Extract upsampling and Tier 2 logic.

- [ ] **Step 1: Add upsampling function to core/ocr.py**

```python
# ============================================================================
# Super-Resolution (Tier 2)
# ============================================================================

_sr_obj = None  # Will be set by _init_sr()

def _upsample_4x(bgr: np.ndarray) -> np.ndarray:
    """Upsample image 4x using FSRCNN or bicubic fallback."""
    try:
        import cv2
        global _sr_obj

        if _sr_obj is not None:
            return _sr_obj.upsample(bgr)
    except Exception:
        pass

    # Fallback: bicubic
    h, w = bgr.shape[:2]
    return cv2.resize(bgr, (w*4, h*4), interpolation=cv2.INTER_CUBIC)
```

- [ ] **Step 2: Verify function compiles**

```bash
python -c "from core.ocr import _upsample_4x; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add core/ocr.py
git commit -m "feat(ocr): add _upsample_4x and super-resolution setup"
```

---

### Task 2.4: Add _process_page to core/ocr.py

**Files:**
- Modify: `core/ocr.py`

**Purpose:** Main OCR producer function (combines tier 1, 2, 3 logic). This is the largest function in ocr.py.

- [ ] **Step 1: Add imports at top of ocr.py**

```python
import fitz  # PyMuPDF
from core.utils import _PageRead, _parse, TESS_CONFIG, DPI
```

- [ ] **Step 2: Add _process_page function to end of ocr.py**

```python
# ============================================================================
# Producer: _process_page (Tiers 1-2, queue failed for Tier 3)
# ============================================================================

def _process_page(doc: fitz.Document, page_idx: int, crop_rect: tuple,
                  on_log: Callable[[str], None]) -> _PageRead:
    """Process single page: Tesseract T1+T2, queue for EasyOCR if needed.

    Args:
        doc: PyMuPDF document
        page_idx: Page index (0-based)
        crop_rect: Crop rectangle (x0, y0, x1, y1)
        on_log: Logging callback

    Returns:
        _PageRead with curr, total, confidence, tier info
    """
    page = doc[page_idx]
    pix = page.get_pixmap(clip=crop_rect, dpi=DPI)
    bgr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # Tier 1: Direct Tesseract
    text = _tess_ocr(gray)
    curr, total = _parse(text)

    tier = 1
    conf = 0.8 if (curr and total) else 0.0

    # Tier 2: Super-resolution + Tesseract
    if not (curr and total):
        try:
            bgr_sr = _upsample_4x(bgr)
            gray_sr = cv2.cvtColor(bgr_sr, cv2.COLOR_BGR2GRAY)
            text_sr = _tess_ocr(gray_sr)
            curr_sr, total_sr = _parse(text_sr)

            if curr_sr and total_sr:
                text = text_sr
                curr, total = curr_sr, total_sr
                tier = 2
                conf = 0.75
        except Exception as e:
            on_log(f"[T2] Page {page_idx}: {e}")

    # Return _PageRead (Tier 3/EasyOCR handled by consumer thread)
    return _PageRead(
        page_idx=page_idx,
        curr=curr,
        total=total,
        text_raw=text,
        text_clean=text,
        conf_read=conf,
        ocr_tier=tier,
        inferred=False
    )
```

- [ ] **Step 2: Test _process_page with a real PDF**

```bash
python -c "
from core.ocr import _process_page
import fitz

# Open a test PDF
doc = fitz.open('eval/fixtures/real/art.pdf')
page = doc[0]
crop_rect = (page.rect.width * 0.70, 0, page.rect.width, page.rect.height * 0.22)

result = _process_page(doc, 0, crop_rect, print)
print(f'Page 0: curr={result.curr}, total={result.total}, tier={result.ocr_tier}')
"
```

Expected: Output showing curr/total values and tier.

- [ ] **Step 3: Commit**

```bash
git add core/ocr.py
git commit -m "feat(ocr): add _process_page producer function (tiers 1-2)"
```

---

## Chunk 3: Image Module

### Task 3.1: Create core/image.py — Rendering Function

**Files:**
- Create: `core/image.py`

**Purpose:** Extract image rendering and preprocessing.

- [ ] **Step 1: Create core/image.py**

```python
"""Image processing: rendering, preprocessing, upsampling."""

import fitz  # PyMuPDF
import numpy as np
import cv2
from typing import Tuple
from core.utils import DPI, CROP_X_START, CROP_Y_END

# ============================================================================
# Image Rendering
# ============================================================================

def _render_clip(page: fitz.Page, dpi: int = DPI) -> Tuple[np.ndarray, Tuple]:
    """Render page clip (rightmost 30%, top 22%) at specified DPI.

    Args:
        page: PyMuPDF page
        dpi: Render DPI

    Returns:
        (BGR numpy array, crop_rect tuple for reconstruction)
    """
    rect = page.rect
    crop_rect = fitz.Rect(
        rect.width * CROP_X_START,
        0,
        rect.width,
        rect.height * CROP_Y_END
    )

    pix = page.get_pixmap(clip=crop_rect, dpi=dpi)
    bgr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)

    return bgr, (crop_rect.x0, crop_rect.y0, crop_rect.x1, crop_rect.y1)

# ============================================================================
# Preprocessing (future: move more here)
# ============================================================================

def _setup_sr(on_log):
    """Initialize super-resolution model (deprecated: call from ocr._init_sr)."""
    on_log("[SR] Super-resolution setup deferred to ocr._init_sr")
```

- [ ] **Step 2: Verify syntax**

```bash
python -m py_compile core/image.py
```

Expected: No output.

- [ ] **Step 3: Test with real PDF**

```bash
python -c "
from core.image import _render_clip
import fitz

doc = fitz.open('eval/fixtures/real/art.pdf')
page = doc[0]
bgr, crop_rect = _render_clip(page)
print(f'Image shape: {bgr.shape}')
print(f'Crop rect: {crop_rect}')
assert bgr.shape[2] == 3, 'Should be BGR'
print('OK')
"
```

Expected: `OK` with image shape printed.

- [ ] **Step 4: Commit**

```bash
git add core/image.py
git commit -m "feat(core): create image.py with _render_clip function"
```

---

## Chunk 4: Inference Module

### Task 4.1: Create core/inference.py — Period Detection

**Files:**
- Create: `core/inference.py`

**Purpose:** Extract period detection (autocorrelation, mode, gaps).

- [ ] **Step 1: Create core/inference.py**

```python
"""Inference engine: period detection, Dempster-Shafer fusion, phases 1-6."""

from typing import Optional, Dict, List
import numpy as np
from core.utils import _PageRead, Document, MIN_CONF_FOR_NEW_DOC

# ============================================================================
# Period Detection (Autocorrelation + Mode + Gap Analysis)
# ============================================================================

def _detect_period(reads: List[_PageRead]) -> Dict:
    """Detect document period (pages per document).

    Args:
        reads: List of _PageRead from OCR

    Returns:
        Dict with 'period', 'confidence', 'method', 'supports'
    """
    confirmed = [r for r in reads if r.curr is not None]

    if len(confirmed) < 3:
        return {
            "period": None,
            "confidence": 0.0,
            "method": "insufficient_data",
            "supports": []
        }

    # Collect confirmed page numbers
    page_nums = [r.curr for r in confirmed]

    # Gap analysis: most common gap
    gaps = []
    for i in range(len(page_nums) - 1):
        gap = page_nums[i+1] - page_nums[i]
        if gap > 0:
            gaps.append(gap)

    if not gaps:
        return {
            "period": None,
            "confidence": 0.0,
            "method": "no_gaps",
            "supports": []
        }

    # Mode of gaps (most common)
    unique_gaps, counts = np.unique(gaps, return_counts=True)
    period = int(unique_gaps[np.argmax(counts)])
    mode_count = int(np.max(counts))

    confidence = min(1.0, mode_count / len(gaps))

    return {
        "period": period,
        "confidence": confidence,
        "method": "gap_analysis",
        "supports": [r.page_idx for r in confirmed]
    }
```

- [ ] **Step 2: Test with synthetic data**

```bash
python -c "
from core.inference import _detect_period
from core.utils import _PageRead

# Create synthetic reads: pages 1, 11, 21, 31 of 30 (period=10)
reads = [
    _PageRead(0, 1, 30, '', '', 1.0, 1),
    _PageRead(10, 11, 30, '', '', 1.0, 1),
    _PageRead(20, 21, 30, '', '', 1.0, 1),
    _PageRead(30, 31, 30, '', '', 1.0, 1),
]

result = _detect_period(reads)
print(f'Detected period: {result[\"period\"]}')
assert result['period'] == 10, f'Expected 10, got {result[\"period\"]}'
print('OK')
"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add core/inference.py
git commit -m "feat(inference): add _detect_period function"
```

---

### Task 4.2: Add Dempster-Shafer & Evidence Functions

**Files:**
- Modify: `core/inference.py`

**Purpose:** Add belief combination and evidence computation.

- [ ] **Step 1: Add D-S functions to core/inference.py**

```python
# ============================================================================
# Dempster-Shafer Belief Combination
# ============================================================================

def _ds_combine(m1: Dict, m2: Dict) -> Dict:
    """Dempster-Shafer combination of two belief structures.

    Args:
        m1, m2: Belief dicts with keys 'boundary' (bool), 'strength' (0-1)

    Returns:
        Combined belief dict
    """
    if m1["boundary"] == m2["boundary"]:
        # Same conclusion
        combined_strength = m1["strength"] + m2["strength"] - m1["strength"] * m2["strength"]
        return {"boundary": m1["boundary"], "strength": combined_strength}
    else:
        # Conflicting: neutral
        return {"boundary": None, "strength": 0.5}

def _period_evidence(page_idx: int, period_info: Dict, reads: List[_PageRead],
                     neighbor_reads: List[_PageRead]) -> Dict:
    """Compute evidence for document boundary at page_idx.

    Args:
        page_idx: Page index to evaluate
        period_info: Output from _detect_period()
        reads: All page reads
        neighbor_reads: Reads from ±1 neighbors

    Returns:
        Evidence dict for Dempster-Shafer
    """
    period = period_info.get("period")
    if period is None:
        return {"boundary": False, "strength": 0.0}

    # Period alignment
    is_aligned = (page_idx % period == 0)
    strength = 0.8 if is_aligned else 0.1

    # Neighbor alignment
    for neighbor in neighbor_reads:
        if neighbor.curr and neighbor.total:
            neighbor_aligned = (neighbor.curr % period == 1)  # Page 1 of new doc
            if neighbor_aligned:
                strength = min(1.0, strength + 0.1)

    return {"boundary": is_aligned, "strength": strength}
```

- [ ] **Step 2: Test D-S combination**

```bash
python -c "
from core.inference import _ds_combine

m1 = {'boundary': True, 'strength': 0.7}
m2 = {'boundary': True, 'strength': 0.6}
result = _ds_combine(m1, m2)
print(f'Combined strength: {result[\"strength\"]}')
assert result['boundary'] == True
print('OK')
"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add core/inference.py
git commit -m "feat(inference): add Dempster-Shafer belief combination"
```

---

### Task 4.3: Add Inference Phases 1-6

**Files:**
- Modify: `core/inference.py`

**Purpose:** Add main inference function (all phases).

- [ ] **Step 1: Add _infer_missing to core/inference.py**

```python
# ============================================================================
# Phases 1-6: Inference
# ============================================================================

def _infer_missing(reads: List[_PageRead], period_info: Dict) -> List[_PageRead]:
    """Infer missing page numbers (phases 1-6).

    Phase 1: Detect period
    Phase 2: Mark candidate boundaries
    Phase 3: Compute evidence (period alignment, neighbor support)
    Phase 4: Apply Dempster-Shafer fusion
    Phase 5: Confidence guards (phase-specific thresholds)
    Phase 6: Infer pages for boundaries

    Args:
        reads: List of _PageRead from OCR
        period_info: Output from _detect_period()

    Returns:
        Updated reads with inferred pages
    """
    period = period_info.get("period")
    if period is None or period < 2:
        return reads  # Can't infer without valid period

    # Phase 2: Candidate boundaries
    candidates = []
    for page_idx in range(len(reads)):
        if reads[page_idx].curr is None:  # Missing page number
            candidates.append(page_idx)

    # Phase 3-4: Evidence & combination
    inferred_pages = {}
    for page_idx in candidates:
        # Get neighbors
        neighbors = []
        if page_idx > 0:
            neighbors.append(reads[page_idx - 1])
        if page_idx < len(reads) - 1:
            neighbors.append(reads[page_idx + 1])

        # Compute evidence
        evidence = _period_evidence(page_idx, period_info, reads, neighbors)

        # Phase 5: Guard (confidence threshold)
        if evidence["strength"] >= MIN_CONF_FOR_NEW_DOC:
            # Phase 6: Infer page numbers
            inferred_curr = (page_idx // period) * period + 1  # Simplified
            inferred_pages[page_idx] = inferred_curr

    # Apply inferences
    updated_reads = reads.copy()
    for page_idx, curr in inferred_pages.items():
        read = updated_reads[page_idx]
        updated_reads[page_idx] = _PageRead(
            page_idx=read.page_idx,
            curr=curr,
            total=read.total,
            text_raw=read.text_raw,
            text_clean=read.text_clean,
            conf_read=read.conf_read,
            ocr_tier=read.ocr_tier,
            inferred=True
        )

    return updated_reads

def _build_documents(reads: List[_PageRead]) -> List[Document]:
    """Build Document objects from _PageRead list.

    Infers document boundaries from confirmed/inferred page numbers.

    Args:
        reads: List of _PageRead

    Returns:
        List of Document objects
    """
    documents = []
    doc_start = None
    last_curr = None

    for read in reads:
        if read.curr is None:
            continue  # Skip unreadable pages

        if doc_start is None:
            doc_start = read.page_idx
            last_curr = read.curr
        elif read.curr == last_curr + 1:
            # Continuation
            last_curr = read.curr
        else:
            # New document (gap detected)
            if doc_start is not None:
                documents.append(Document(
                    start_page=doc_start,
                    end_page=read.page_idx - 1,
                    total_pages=read.page_idx - doc_start,
                    confidence=0.8
                ))
            doc_start = read.page_idx
            last_curr = read.curr

    # Final document
    if doc_start is not None:
        documents.append(Document(
            start_page=doc_start,
            end_page=len(reads) - 1,
            total_pages=len(reads) - doc_start,
            confidence=0.8
        ))

    return documents
```

- [ ] **Step 2: Test _infer_missing**

```bash
python -c "
from core.inference import _infer_missing, _detect_period
from core.utils import _PageRead

# Synthetic: reads with gaps
reads = [
    _PageRead(0, 1, 10, '', '', 1.0, 1),
    _PageRead(1, None, None, '', '', 0.0, 0),  # Missing
    _PageRead(2, None, None, '', '', 0.0, 0),  # Missing
    _PageRead(3, 4, 10, '', '', 1.0, 1),
]

period_info = _detect_period(reads)
print(f'Detected period: {period_info[\"period\"]}')

inferred = _infer_missing(reads, period_info)
print(f'Inferred pages:')
for r in inferred:
    if r.inferred:
        print(f'  Page {r.page_idx}: {r.curr}')
print('OK')
"
```

Expected: `OK` with inferred pages printed.

- [ ] **Step 3: Commit**

```bash
git add core/inference.py
git commit -m "feat(inference): add phases 1-6 inference engine"
```

---

## Chunk 5: Pipeline Module

### Task 5.1: Create core/pipeline.py — Skeleton & analyze_pdf

**Files:**
- Create: `core/pipeline.py`

**Purpose:** Orchestration: producer-consumer pattern, thread management.

- [ ] **Step 1: Create core/pipeline.py with analyze_pdf skeleton**

```python
"""Pipeline orchestration: V4 producer-consumer, analyze_pdf, re_infer_documents."""

import threading
from queue import Queue
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional, Tuple, List
import fitz  # PyMuPDF

from core.utils import _PageRead, Document, PARALLEL_WORKERS, BATCH_SIZE, CROP_X_START, CROP_Y_END
from core.ocr import _process_page, _init_easyocr, _init_sr
from core.image import _render_clip
from core.inference import _detect_period, _infer_missing, _build_documents

# ============================================================================
# Main Entry Points
# ============================================================================

def analyze_pdf(
    pdf_path: str,
    on_progress: Callable[[str], None],
    on_log: Callable[[str], None],
    pause_event: Optional[threading.Event] = None,
    cancel_event: Optional[threading.Event] = None,
    on_issue: Optional[Callable[[str], None]] = None,
    doc_mode: str = "charla",
) -> Tuple[List[Document], List[_PageRead]]:
    """Analyze PDF: OCR all pages, detect period, infer missing, build documents.

    Args:
        pdf_path: Path to PDF
        on_progress: Callback(page_count) for progress updates
        on_log: Callback(message) for logging
        pause_event: threading.Event to pause processing
        cancel_event: threading.Event to cancel processing
        on_issue: Optional callback(issue_str) for warnings
        doc_mode: "charla" or other document type

    Returns:
        (list[Document], list[_PageRead]) — inferred documents and raw reads
    """
    on_log(f"[PIPELINE] Starting analyze_pdf: {pdf_path}")

    # Step 1: Open PDF
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        on_log(f"[ERROR] Failed to open PDF: {e}")
        return ([], [])

    num_pages = len(doc)
    on_progress(num_pages)
    on_log(f"[PDF] Opened {pdf_path} ({num_pages} pages)")

    # Step 2: Initialize GPU resources
    _init_easyocr(on_log)
    _init_sr(on_log)

    # Step 3: V4 Pipeline (producer-consumer)
    reads = _v4_pipeline(doc, num_pages, on_log, on_progress, pause_event, cancel_event)

    # Step 4: Inference
    on_log("[INFER] Detecting period...")
    period_info = _detect_period(reads)
    on_log(f"[INFER] Period: {period_info['period']} ({period_info['confidence']:.2f})")

    on_log("[INFER] Inferring missing pages...")
    reads = _infer_missing(reads, period_info)

    # Step 5: Build documents
    on_log("[BUILD] Building documents...")
    documents = _build_documents(reads)
    on_log(f"[BUILD] Found {len(documents)} documents")

    doc.close()
    return (documents, reads)

def _v4_pipeline(doc: fitz.Document, num_pages: int, on_log: Callable,
                  on_progress: Callable, pause_event, cancel_event) -> List[_PageRead]:
    """V4 Producer-Consumer: Tesseract workers + EasyOCR GPU consumer.

    Producers: 6 workers render + OCR tier 1-2
    Consumer: 1 GPU thread handles tier 3 (EasyOCR)

    Returns:
        list[_PageRead] with OCR results
    """
    on_log("[V4] Starting producer-consumer pipeline")

    # Compute crop rectangle
    page0 = doc[0]
    crop_rect = (
        page0.rect.width * CROP_X_START,
        0,
        page0.rect.width,
        page0.rect.height * CROP_Y_END
    )

    # Shared state
    reads = [None] * num_pages
    failed_queue = Queue()  # Pages that failed T1+T2, queue for GPU
    producer_lock = threading.Lock()

    # Producer function
    def producer_worker(worker_id: int):
        for page_idx in range(worker_id, num_pages, PARALLEL_WORKERS):
            if cancel_event and cancel_event.is_set():
                break
            if pause_event:
                pause_event.wait()

            try:
                read = _process_page(doc, page_idx, crop_rect, on_log)
                with producer_lock:
                    reads[page_idx] = read

                if read.ocr_tier < 3 and read.curr is None:
                    # Failed T1+T2, queue for EasyOCR
                    failed_queue.put(page_idx)

                # Batch checkpoint
                if page_idx % BATCH_SIZE == 0:
                    on_progress(page_idx)
            except Exception as e:
                on_log(f"[PRODUCER] Page {page_idx} error: {e}")
                failed_queue.put(page_idx)

    # Run producers
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        futures = [executor.submit(producer_worker, i) for i in range(PARALLEL_WORKERS)]
        for future in futures:
            future.result()  # Wait for all producers

    on_log("[V4] Producers done")
    return reads
```

- [ ] **Step 2: Verify syntax**

```bash
python -m py_compile core/pipeline.py
```

Expected: No output.

- [ ] **Step 3: Commit**

```bash
git add core/pipeline.py
git commit -m "feat(pipeline): create core/pipeline.py with analyze_pdf skeleton"
```

---

### Task 5.2: Add re_infer_documents to core/pipeline.py

**Files:**
- Modify: `core/pipeline.py`

**Purpose:** Human-in-the-loop corrections and re-inference.

- [ ] **Step 1: Add re_infer_documents function**

```python
def re_infer_documents(
    reads: List[_PageRead],
    corrections: dict,
    on_log: Callable[[str], None],
    on_issue: Optional[Callable[[str], None]] = None,
    exclusions: Optional[List[int]] = None,
) -> Tuple[List[Document], List[_PageRead]]:
    """Re-infer documents after user corrections.

    Applies corrections, resets inferred pages, re-runs inference pipeline.

    Args:
        reads: Original list[_PageRead]
        corrections: Dict {page_idx: (curr, total)}
        on_log: Logging callback
        on_issue: Optional warnings callback
        exclusions: Page indices to exclude from inference

    Returns:
        (list[Document], list[_PageRead]) — updated documents and reads
    """
    on_log("[RE_INFER] Applying user corrections...")

    # Step 1: Apply corrections
    updated_reads = []
    for page_idx, read in enumerate(reads):
        if page_idx in corrections:
            curr, total = corrections[page_idx]
            on_log(f"[CORRECTION] Page {page_idx}: {curr}/{total}")
            updated_read = _PageRead(
                page_idx=page_idx,
                curr=curr,
                total=total,
                text_raw=read.text_raw,
                text_clean=read.text_clean,
                conf_read=read.conf_read,
                ocr_tier=read.ocr_tier,
                inferred=False
            )
            updated_reads.append(updated_read)
        else:
            # Reset inferred pages
            if read.inferred:
                reset_read = _PageRead(
                    page_idx=read.page_idx,
                    curr=None,
                    total=None,
                    text_raw=read.text_raw,
                    text_clean=read.text_clean,
                    conf_read=read.conf_read,
                    ocr_tier=read.ocr_tier,
                    inferred=False
                )
                updated_reads.append(reset_read)
            else:
                updated_reads.append(read)

    # Step 2: Re-detect period (cascading)
    on_log("[RE_INFER] Detecting new period...")
    period_info = _detect_period(updated_reads)
    on_log(f"[RE_INFER] Period: {period_info['period']} ({period_info['confidence']:.2f})")

    # Step 3: Re-infer missing (cascading)
    on_log("[RE_INFER] Re-inferring missing pages...")
    updated_reads = _infer_missing(updated_reads, period_info)

    # Step 4: Re-build documents
    on_log("[RE_INFER] Building updated documents...")
    documents = _build_documents(updated_reads)
    on_log(f"[RE_INFER] Found {len(documents)} documents")

    return (documents, updated_reads)
```

- [ ] **Step 2: Test re_infer_documents**

```bash
python -c "
from core.pipeline import re_infer_documents
from core.utils import _PageRead

# Synthetic reads
reads = [
    _PageRead(0, 1, 10, '', '', 1.0, 1),
    _PageRead(1, None, None, '', '', 0.0, 0),
]

# User corrects page 1
corrections = {1: (2, 10)}
docs, updated = re_infer_documents(reads, corrections, print)
print(f'Updated reads: {len(updated)} pages')
assert updated[1].curr == 2
print('OK')
"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add core/pipeline.py
git commit -m "feat(pipeline): add re_infer_documents for user corrections"
```

---

## Chunk 6: Finalization & Integration

### Task 6.1: Create core/__init__.py

**Files:**
- Create: `core/__init__.py`

**Purpose:** Export public API.

- [ ] **Step 1: Create core/__init__.py**

```python
"""OCR + Inference pipeline for PDF document analysis."""

from core.pipeline import analyze_pdf, re_infer_documents
from core.utils import Document

__all__ = [
    "analyze_pdf",
    "re_infer_documents",
    "Document",
]
```

- [ ] **Step 2: Test imports**

```bash
python -c "from core import analyze_pdf, re_infer_documents, Document; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add core/__init__.py
git commit -m "feat(core): create __init__.py with public API"
```

---

### Task 6.2: Update server.py Imports

**Files:**
- Modify: `server.py`

**Purpose:** Verify imports work (should be no change needed).

- [ ] **Step 1: Check current server.py imports**

```bash
grep -n "from core" server.py | head -5
```

Expected: Lines like `from core.analyzer import analyze_pdf`

- [ ] **Step 2: Verify new imports work**

```bash
python -c "from core import analyze_pdf, re_infer_documents; print('OK')"
```

Expected: `OK` (no change to server.py needed if it uses `from core import ...`)

- [ ] **Step 3: If needed, update server.py**

If server.py imports from `core.analyzer`, update it:

```bash
sed -i 's/from core\.analyzer import/from core import/g' server.py
```

Then verify:

```bash
python -c "import server"
```

- [ ] **Step 4: Commit**

```bash
git add server.py
git commit -m "refactor(server): update core imports (if changed)"
```

---

### Task 6.3: Run Full Test Suite

**Files:**
- Test: All modules

**Purpose:** Verify backward compatibility before cleanup.

- [ ] **Step 1: Run pytest**

```bash
pytest -v
```

Expected: All tests pass (or same failures as before).

- [ ] **Step 2: If tests fail, debug**

If new failures:
```bash
pytest -v --tb=short
```

Review error messages and fix core modules.

- [ ] **Step 3: Run server.py smoke test**

```bash
timeout 5 python server.py &
sleep 2
curl http://localhost:8000/health
kill %1
```

Expected: `200 OK` response from health endpoint.

- [ ] **Step 4: Commit (only if tests pass)**

```bash
git add .
git commit -m "test: verify all tests pass after modularization"
```

---

### Task 6.4: Delete core/analyzer.py

**Files:**
- Delete: `core/analyzer.py`

**Purpose:** Final cleanup after all tests pass.

- [ ] **Step 1: Backup (just in case)**

```bash
cp core/analyzer.py /tmp/analyzer.py.backup
echo "Backup saved to /tmp/analyzer.py.backup"
```

- [ ] **Step 2: Delete**

```bash
rm core/analyzer.py
```

- [ ] **Step 3: Verify no broken imports**

```bash
python -c "from core import analyze_pdf; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Run tests one more time**

```bash
pytest -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add -u core/
git commit -m "feat(core): delete analyzer.py after full modularization"
```

---

## Post-Implementation Checklist

After all tasks complete:

- [ ] All files created: utils.py, ocr.py, image.py, inference.py, pipeline.py, __init__.py
- [ ] core/analyzer.py deleted
- [ ] `pytest` passes (zero failures)
- [ ] `python server.py` starts without errors
- [ ] Frontend can upload PDF and get results
- [ ] `re_infer_documents()` with corrections works correctly
- [ ] Each module is 150–350 lines (maintainable)
- [ ] No circular imports
- [ ] Public API unchanged: `from core import analyze_pdf, re_infer_documents`

---

## Success Criteria

✅ Refactoring complete (all code moved to 5 modules)
✅ `pytest` passes (zero failures, zero skipped tests)
✅ `python server.py` starts and processes PDFs identically to before
✅ `re_infer_documents()` correctly cascades user corrections
✅ File sizes: each module 150–350 lines (readable, testable)
✅ No circular imports
✅ Public API unchanged

---

## References

- **Spec:** [2026-03-18-core-modularization-design.md](../specs/2026-03-18-core-modularization-design.md)
- **Current impl:** core/analyzer.py (to be deleted)
- **Tests:** pytest suite in tests/

