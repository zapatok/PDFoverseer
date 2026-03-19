# Core Modularization Design

**Date:** 2026-03-18
**Status:** Design (awaiting implementation)
**Next Step:** writing-plans skill for implementation roadmap

---

## Overview

Refactor `core/analyzer.py` (1186 lines) from monolithic structure into focused, testable modules organized by responsibility. Maintain full backward compatibility and functional parity with current implementation.

**Goals:**
- Enable isolated testing per subsystem (OCR, image processing, inference)
- Facilitate independent tuning and future module additions
- Reduce file size for maintainability and token efficiency in code reviews
- Preserve stateless inference for human-in-the-loop corrections

---

## Current State

**File:** `core/analyzer.py` (1186 lines)

**Mixed responsibilities:**
- OCR (Tesseract tiers 1–2, EasyOCR tier 3, parsing)
- Image processing (rendering, preprocessing, super-resolution)
- Inference engine (period detection, Dempster-Shafer, phases 1–6)
- V4 producer-consumer pipeline orchestration

**Key data structure:** `_PageRead` (per-page OCR result, passed through inference)

**Entry points:** `analyze_pdf()`, `re_infer_documents()`

---

## Target Architecture

### File Structure

```
core/
├── __init__.py              # Public API exports
├── utils.py                 # ~80 lines
│   ├── Config constants (DPI, CROP_X_START, PARALLEL_WORKERS, etc.)
│   ├── _PageRead, Document dataclasses
│   ├── Helper functions (_to_int, _parse, regex patterns)
│   └── Magic number: INFERENCE_ENGINE_VERSION
├── ocr.py                   # ~300 lines
│   ├── _init_easyocr(on_log)
│   ├── _init_sr(on_log)
│   ├── _tess_ocr(gray)
│   ├── _upsample_4x(bgr)
│   ├── _process_page(doc, page_idx) → _PageRead
│   ├── EasyOCR GPU consumer state (_easyocr_reader, _easyocr_lock)
│   └── Dependencies: utils, OpenCV, PyTorch, EasyOCR, pytesseract
├── image.py                 # ~180 lines
│   ├── _setup_sr(on_log)
│   ├── _render_clip(page, dpi) → np.ndarray
│   └── Dependencies: utils, PyMuPDF, OpenCV
├── inference.py             # ~300 lines
│   ├── _detect_period(reads) → dict
│   ├── _ds_combine(m1, m2) → dict
│   ├── _period_evidence(...) → dict
│   ├── _infer_missing(reads, period_info) → list[_PageRead]
│   ├── _build_documents(reads) → list[Document]
│   └── Dependencies: utils, NumPy
└── pipeline.py              # ~200 lines
    ├── analyze_pdf(...) → tuple[list[Document], list[_PageRead]]
    ├── re_infer_documents(...) → tuple[list[Document], list[_PageRead]]
    ├── Producer-consumer orchestration (ThreadPoolExecutor, queues)
    ├── GPU consumer thread management
    └── Dependencies: utils, ocr, image, inference, threading
```

### Dependency Graph

```
utils.py
  ↑
  ├── ocr.py (imports Config, _PageRead, _parse, helpers)
  ├── image.py (imports Config, _render_clip logic)
  └── inference.py (imports Config, _PageRead, Document)
       ↑
       └── pipeline.py (imports all above + orchestrates threading)
            ↑
            └── server.py, app.py (unchanged imports)
```

**No circular dependencies.** Unidirectional flow: utils → {ocr, image, inference} → pipeline.

---

## Module Responsibilities

### `utils.py`

**Purpose:** Shared configuration, types, and utilities.

**Contents:**
- Constants: DPI, CROP_X_START, CROP_Y_END, PARALLEL_WORKERS, BATCH_SIZE, TESS_CONFIG, etc.
- Dataclasses: `Document`, `_PageRead`
- Functions: `_to_int(s)`, `_parse(text)`, `_Z2` regex
- Page pattern regex: `_PAGE_PATTERNS`
- Version string: `INFERENCE_ENGINE_VERSION`

**Why separate:** These are referenced by multiple modules. Centralizing eliminates duplication and makes configuration changes atomic.

---

### `ocr.py`

**Purpose:** All OCR operations (text extraction, tier logic).

**Main Functions:**
- `_init_easyocr(on_log)` — Lazy-load GPU reader (called once per session)
- `_init_sr(on_log)` — Lazy-load super-resolution model
- `_tess_ocr(gray: np.ndarray) → str` — Tesseract OCR with Otsu threshold
- `_upsample_4x(bgr: np.ndarray) → np.ndarray` — FSRCNN or bicubic upsampling
- `_process_page(doc, page_idx) → _PageRead` — Main producer function (Tier 1 + Tier 2)

**Global State (necessary):**
- `_easyocr_reader` — GPU model singleton
- `_easyocr_lock` — Thread-safe access to GPU reader
- `_sr_initialized` — Initialization flag for super-resolution model

**Why separate:** OCR is a coherent subsystem. Will benefit from independent testing (mock image inputs, verify text extraction). Tier 1/2 logic can be tuned without touching inference.

---

### `image.py`

**Purpose:** Image rendering and preprocessing.

**Main Functions:**
- `_render_clip(page: fitz.Page, dpi: int) → np.ndarray` — Render PDF page clip at specified DPI
- `_setup_sr(on_log)` — Initialize super-resolution model (load FSRCNN weights)

**Why separate:** Image processing (rendering, preprocessing, upsampling) is distinct from text extraction. Future: add noise reduction, binarization strategies, etc. without touching OCR logic.

---

### `inference.py`

**Purpose:** Document boundary inference and statistical fusion.

**Main Functions:**
- `_detect_period(reads) → dict` — Detect page-number period via autocorrelation, gap analysis, mode total
- `_ds_combine(m1, m2) → dict` — Dempster-Shafer belief combination
- `_period_evidence(...) → dict` — Compute evidence from neighbors, period, prior
- `_infer_missing(reads, period_info) → list[_PageRead]` — Phases 1–6: fill gaps, merge documents, apply guards
- `_build_documents(reads) → list[Document]` — Construct `Document` objects from `_PageRead` list

**Statelessness:** Functions take all required inputs as parameters. No global caches. Enables safe re-inference after user corrections.

**Why separate:** Inference is the "brain" of the system. Isolating it allows:
- Parameter sweeps without touching OCR
- Testing inference logic against synthetic fixtures
- Replacing inference strategy later (e.g., ML-based) without breaking OCR

---

### `pipeline.py`

**Purpose:** Orchestration, producer-consumer pattern, human-in-the-loop.

**Main Functions:**
- `analyze_pdf(pdf_path, on_progress, on_log, ...) → (list[Document], list[_PageRead])`
  - V4 orchestration: ThreadPoolExecutor (Tesseract) + GPU consumer thread (EasyOCR)
  - Batch management, pause/cancel events
  - Calls: `ocr._process_page()` → `inference._detect_period()` → `inference._infer_missing()` → `inference._build_documents()`

- `re_infer_documents(reads, corrections, exclusions, ...) → (list[Document], list[_PageRead])`
  - Apply user corrections and reset inferred pages
  - Re-run: `inference._detect_period()` → `inference._infer_missing()` → `inference._build_documents()`
  - Enables cascading updates for human-in-the-loop workflow

**Threading State:**
- ThreadPoolExecutor with document pool (one fitz.Document per worker thread)
- GPU queue for failed pages
- Pause/cancel event handling
- Batch checkpoints

**Why separate:** Pipeline orchestration is distinct from individual subsystems. Threading complexity lives here; modules are called as pure functions.

---

### `__init__.py`

**Purpose:** Clean public API.

**Exports:**
```python
from .pipeline import analyze_pdf, re_infer_documents
from .utils import Document

__all__ = ["analyze_pdf", "re_infer_documents", "Document"]
```

**Result:** `server.py` imports remain unchanged:
```python
from core import analyze_pdf, re_infer_documents
```

---

## Data Flow

### `analyze_pdf()` Flow

```
[PDF file]
    ↓
[ThreadPoolExecutor: _process_page()]  ← ocr.py
    ├─ Render clip (image.py)
    ├─ Tesseract Tier 1 (ocr.py)
    ├─ Tesseract Tier 2 + SR (ocr.py, image.py)
    └─ Queue failed pages to GPU
    ↓
[GPU consumer: EasyOCR]  ← ocr.py
    ↓
[_PageRead list: per-page OCR results]
    ↓
[inference._detect_period()]  ← inference.py
    ↓
[period_info dict]
    ↓
[inference._infer_missing()]  ← inference.py
    ↓
[Updated _PageRead list with inferred pages]
    ↓
[inference._build_documents()]  ← inference.py
    ↓
[(list[Document], list[_PageRead])]
```

### `re_infer_documents()` Flow

```
[reads: list[_PageRead], corrections: dict]
    ↓
[Apply corrections, reset inferred pages]  ← pipeline.py
    ↓
[inference._detect_period()]  ← inference.py (cascading: new period = new corrections)
    ↓
[inference._infer_missing()]  ← inference.py (cascading: phases 1–6 re-run with new data)
    ↓
[inference._build_documents()]  ← inference.py
    ↓
[(list[Document], list[_PageRead])]
```

---

## Implementation Strategy

### Principle: Incremental Refactoring

**Each step preserves functionality:**
1. After moving each module, `server.py` and app behavior unchanged
2. All tests pass
3. Rollback possible at each checkpoint

### Recommended Sequence

1. **utils.py** — Extract constants, types, helpers
2. **ocr.py** — Move OCR functions, keep imports from utils
3. **image.py** — Move image rendering/preprocessing, test integration with ocr.py
4. **inference.py** — Move inference logic, test re_infer_documents() workflow
5. **pipeline.py** — Move analyze_pdf(), re_infer_documents(), threading orchestration
6. **__init__.py** — Export public API, update server.py imports (if needed)
7. **Delete analyzer.py** — Last step after all tests pass

### Testing Between Steps

- `pytest` passes after each module extraction
- Integration test: `python server.py`, upload PDF, verify results match baseline
- Re-infer test: upload → correct pages → re-infer, verify cascading works

---

## Backward Compatibility

**Public API unchanged:**
```python
def analyze_pdf(
    pdf_path: str,
    on_progress: callable,
    on_log: callable,
    pause_event: threading.Event | None = None,
    cancel_event: threading.Event | None = None,
    on_issue: callable | None = None,
    doc_mode: str = "charla",
) -> tuple[list[Document], list[_PageRead]]:
    """Same signature, same behavior."""

def re_infer_documents(
    reads: list[_PageRead],
    corrections: dict[int, tuple[int, int]],
    on_log: callable,
    on_issue: callable | None = None,
    exclusions: list[int] | None = None,
) -> tuple[list[Document], list[_PageRead]]:
    """Same signature, same behavior."""
```

**No changes to:**
- `server.py` calls
- `app.py` calls
- WebSocket messages
- Frontend API

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **5 files, no subdirs** | Balances modularity vs. complexity. Avoids excessive `__init__.py` navigation |
| **Stateless inference** | Safe for re-infer-documents() corrections; no stale caches between sessions |
| **Global state in ocr.py** | EasyOCR and SR models are expensive; must be cached and lazy-loaded |
| **pipeline.py owns threading** | Separates pure functions (ocr, image, inference) from orchestration complexity |
| **Unidirectional imports** | Prevents circular dependencies, makes data flow explicit |

---

## Testing Strategy

### Unit Tests (Per Module)

**ocr.py:**
- Mock images → verify _tess_ocr() extracts text correctly
- Verify _upsample_4x() enlarges image 4x
- Verify _process_page() returns _PageRead with correct curr/total

**image.py:**
- Verify _render_clip() returns BGR numpy array of correct size
- Verify _setup_sr() initializes model

**inference.py:**
- Verify _detect_period() detects period from synthetic _PageRead lists
- Verify _infer_missing() fills gaps correctly
- Verify _build_documents() creates Document objects with correct boundaries

**pipeline.py:**
- Integration: full analyze_pdf() → compare with baseline results
- Integration: re_infer_documents() with corrections → verify cascading

### Integration Tests

- Upload real PDF → analyze_pdf() → compare results with current analyzer.py
- User corrects pages → re_infer_documents() → verify cascading inference

### Regression Tests

- All existing tests pass
- `pytest` suite unchanged (or enhanced with module-specific tests)

---

## Success Criteria

✅ Refactoring complete (all code moved to 5 modules)
✅ `pytest` passes (zero failures, zero skipped tests)
✅ `python server.py` starts and processes PDFs identically to before
✅ `re_infer_documents()` correctly cascades user corrections
✅ File sizes: each module 150–350 lines (readable, testable)
✅ No circular imports
✅ Public API unchanged (`from core import analyze_pdf, re_infer_documents`)

---

## Open Questions / Future Considerations

1. **ML-based inference:** If replacing Dempster-Shafer with ML model, inference.py becomes the integration point. Module design supports this.

2. **Tier 4 OCR:** If adding new OCR strategy, ocr.py is the home. Can add new function without touching pipeline.

3. **Parallel fixture evaluation:** eval/inference.py (duplicate logic) can import from core.inference instead. Reduces code duplication.

---

## Files to Create/Modify

| File | Action | Lines |
|------|--------|-------|
| `core/utils.py` | Create | ~80 |
| `core/ocr.py` | Create | ~300 |
| `core/image.py` | Create | ~180 |
| `core/inference.py` | Create | ~300 |
| `core/pipeline.py` | Create | ~200 |
| `core/__init__.py` | Create | ~10 |
| `core/analyzer.py` | Delete | (move content to above) |
| `server.py` | No change | (imports via `__init__.py`) |

---

## References

- Current impl: [core/analyzer.py](../../core/analyzer.py)
- CLAUDE.md: Project conventions, architecture notes
- eval/inference.py: Duplicate logic to consolidate (future)

