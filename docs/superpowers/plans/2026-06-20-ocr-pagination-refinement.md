# OCR Pagination-Count Refinement Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Controller-owned tasks** (do NOT delegate to an implementer subagent — they need human/vision judgment): **Task 7** (label GT by looking at pages), **Task 9** (GO/NO-GO migration decision), **Task 15** (live browser smoke). Everything else is delegatable.

**Goal:** Replace brittle text-anchor counting with a unified pagination-based document counter (orientation-aware corner OCR + lite sequence-recovery + form-code routing + honest confidence) for the paginated siglas, migrated gradually and reversibly.

**Architecture:** A new pure-logic-heavy engine `count_documents_by_pagination` lives behind the *existing* `PaginationScanner` / `count_ocr` interface (zero contract change). Build + validate it in `eval/pagination_count/` against the real merged MAYO corpus first (eval-first), then port to `core/scanners/utils/pagination_count.py`, wire it into `PaginationScanner`, and migrate validated siglas by flipping `scan_strategy` in `patterns.py`. Each sigla migration is gated by an eval accuracy check and is one-line reversible.

**Tech Stack:** Python 3.10+, PyMuPDF (`fitz`), pytesseract (Tesseract `--psm 6 --oem 1`, `spa+eng`), pytest. Frontend unaffected except a new `method` chip value `"pagination"`.

**Spec:** `docs/superpowers/specs/2026-06-20-ocr-pagination-refinement-design.md` (read it; this plan implements §6/§7/§10/§11 and decisions D1–D11).

**Key existing seams (already verified):**
- `core/scanners/utils/pdf_render.py`: `render_page_region(pdf_path, page_idx, *, bbox=(x0,y0,x1,y1) in [0..1], dpi)` → PIL.Image; `get_page_count`; `PdfRenderError`.
- `core/scanners/utils/header_band_anchors.py`: OCR pattern `pytesseract.image_to_string(pil, config="--psm 6 --oem 1", lang="spa+eng")`; `_normalize_text(text)`.
- `core/scanners/pagination_scanner.py`: `PaginationScanner.count_ocr(folder, *, cancel, on_pdf, only, skip, on_page)`; today calls `count_documents_v4`; A7 (1-page→1 doc), A8 (missing folder).
- `core/scanners/base.py`: `ScanResult(count, confidence, method, breakdown, flags, errors, duration_ms, files_scanned, per_file, telemetry)`; `ConfidenceLevel.{HIGH,LOW}`.
- `core/scanners/__init__.py`: `_scanner_for_sigla` picks the scanner from `PATTERNS[sigla]["scan_strategy"]` → **migration = change that field**.
- `core/scanners/patterns.py`: `PATTERNS`, `SiglaPattern` TypedDict (uses `NotRequired`), `count_type_for`.
- `core/utils.py:56`: `SCANNER_PATTERNS_VERSION` (bump on scan-strategy changes).
- `core/scanners/cancellation.py`: `CancellationToken` (`.cancelled`, `.check()`), `CancelledError`.

**Data-safety (NON-NEGOTIABLE):**
- Tests use **synthetic generated PDFs only** (fake "Página N de M" + dummy text). NEVER commit real corpus slices — they contain worker names/RUTs.
- The eval benchmark reads the real corpus from `INFORME_MENSUAL_ROOT` at **runtime**; its outputs are gitignored.
- Live smoke uses a **copy** of `overseer.db` on a separate port; never the real DB; corpus is read-only.

---

## Chunk 1: Engine core (pure logic, TDD) in `eval/pagination_count/`

> Build the engine in eval first (eval-first). The four pure functions are the heart and are tested with zero OCR/PDF dependency. `cancellation` + `pdf_render` are imported from core (read-only reuse).

**Files:**
- Create: `eval/pagination_count/__init__.py`
- Create: `eval/pagination_count/engine.py`
- Create: `eval/pagination_count/README.md`
- Test: `eval/tests/test_pagination_engine.py`

### Task 1: Scaffold + dataclasses + `parse_pagination`

**Files:** Create `eval/pagination_count/__init__.py` (empty), `eval/pagination_count/engine.py`; Test `eval/tests/test_pagination_engine.py`

- [ ] **Step 1: Write failing tests** for `parse_pagination(raw: str) -> tuple[int|None, int|None]`:

```python
# eval/tests/test_pagination_engine.py
import pytest
from eval.pagination_count.engine import parse_pagination

@pytest.mark.parametrize("raw,expected", [
    ("Pagina 1 de 4", (1, 4)),
    ("Página 2 de 4", (2, 4)),
    ("r SpA Fecha: 31/12/2025| Página 2 de 4 L", (2, 4)),   # real OCR noise
    ("Pagina 1de1", (1, 1)),                                       # missing space
    ("Pagina l de 4", (1, 4)),                                     # l->1 digit-normalize
    ("Pagina 1", (1, None)),                                       # curr-only (no total)
    ("F-CRS-ART-01 Rev 02", (None, None)),                         # no pagination
    ("", (None, None)),
    ("Pagina 12 de 20", (12, 20)),                                 # full regex wins over curr-only
])
def test_parse_pagination(raw, expected):
    assert parse_pagination(raw) == expected
```

- [ ] **Step 2: Run, verify fail** — `pytest eval/tests/test_pagination_engine.py -v` → ImportError/fail.

- [ ] **Step 3: Implement** in `eval/pagination_count/engine.py`:

```python
"""Pagination-first document counter (eval prototype). See spec §6.

Pure functions (parse_pagination / extract_code / recover_sequence / count_starts)
have zero OCR/PDF dependency and are unit-tested directly. count_documents_by_pagination
is the thin OCR orchestrator (integration-tested with synthetic PDFs).
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.scanners.cancellation import CancellationToken, CancelledError
from core.scanners.utils.pdf_render import PdfRenderError, get_page_count, render_page_region

# digit-normalize common OCR confusions, then match
_DIGIT = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "|": "1", "Z": "2", "S": "5", "B": "8"})
_PAG_FULL = re.compile(r"(?:p[aá4@]?gina|pag)\s*([0-9]{1,3})\s*de\s*([0-9]{1,3})", re.IGNORECASE)
_PAG_CURR = re.compile(r"(?:p[aá4@]?gina|pag)\.?\s*([0-9]{1,3})\b", re.IGNORECASE)
_CODE = re.compile(r"\bF[-\s]?[A-Z]{2,4}[-\s][A-Z0-9\-]{2,12}", re.IGNORECASE)

# Confidence: a count that needed lots of gap-recovery is guesswork (eval-tuned).
RECOVERY_LOW_CONF_RATIO = 0.30


def parse_pagination(raw: str) -> tuple[int | None, int | None]:
    """Parse "Página C de M" (or "Página C" without total) from OCR text.

    Full regex (C de M) takes precedence; the curr-only fallback applies only
    when the full regex does not match (spec §6 precedence).
    """
    norm = raw.replace("\n", " ")
    m = _PAG_FULL.search(norm) or _PAG_FULL.search(norm.translate(_DIGIT))
    if m:
        return int(m.group(1)), int(m.group(2))
    m = _PAG_CURR.search(norm) or _PAG_CURR.search(norm.translate(_DIGIT))
    if m:
        return int(m.group(1)), None
    return None, None
```

- [ ] **Step 4: Run, verify pass** — `pytest eval/tests/test_pagination_engine.py -v`.
- [ ] **Step 5: Commit** — `git add eval/pagination_count eval/tests/test_pagination_engine.py && git commit -m "feat(eval): pagination engine parse_pagination"`

### Task 2: `extract_code`

- [ ] **Step 1: Failing tests:**

```python
from eval.pagination_count.engine import extract_code

@pytest.mark.parametrize("raw,expected", [
    ("Código: F-CRS-ART-01 Rev 02", "F-CRS-ART-01"),
    ("F-CRS-ODI-01 INFORMACION", "F-CRS-ODI-01"),
    ("F-LCH-CRS-36 EN CALIENTE", "F-LCH-CRS-36"),
    ("no code here", None),
])
def test_extract_code(raw, expected):
    assert extract_code(raw) == expected
```

- [ ] **Step 2: Run, fail.**
- [ ] **Step 3: Implement:**

```python
def extract_code(raw: str) -> str | None:
    """Extract a form code like F-CRS-ART-01 from OCR text (uppercased, '-'-joined)."""
    m = _CODE.search(raw.replace("\n", " "))
    if not m:
        return None
    return m.group(0).upper().replace(" ", "-")
```

- [ ] **Step 4: Run, pass.**
- [ ] **Step 5: Commit** — `git commit -am "feat(eval): pagination engine extract_code"`

### Task 3: `recover_sequence` (the heart)

- [ ] **Step 1: Failing tests** — covers direct, single gap, run of gaps (forward fill), leading gap (right neighbor), orphan (failed), no-total (curr-only never recovered), dominant-total selection:

```python
from eval.pagination_count.engine import recover_sequence, PageRead

def _currs(reads): return [r.curr for r in reads]
def _status(reads): return [r.status for r in reads]

def test_recover_no_gaps():
    parsed = [(1,4,"A"),(2,4,"A"),(3,4,"A"),(4,4,"A")]
    out = recover_sequence(parsed)
    assert _currs(out) == [1,2,3,4]
    assert _status(out) == ["direct"]*4

def test_recover_run_of_gaps_forward_fill():
    # ART rhythm with 3 unreadable corners mid-run
    parsed = [(1,4,"A"),(None,None,None),(None,None,None),(4,4,"A"),(1,4,"A")]
    out = recover_sequence(parsed)
    assert _currs(out) == [1,2,3,4,1]
    assert _status(out) == ["direct","recovered","recovered","direct","direct"]

def test_recover_leading_gap_uses_right_neighbor():
    parsed = [(None,None,None),(2,4,"A"),(3,4,"A"),(4,4,"A")]
    out = recover_sequence(parsed)
    assert _currs(out)[0] == 1

def test_recover_orphan_is_failed():
    parsed = [(None,None,None)]  # no dominant total, no neighbor
    out = recover_sequence(parsed)
    assert out[0].status == "failed" and out[0].curr is None

def test_recover_dominant_total_ignores_outliers():
    parsed = [(1,4,"A"),(2,4,"A"),(3,4,"A"),(4,4,"A"),(1,4,"A"),(2,3,"A")]  # one bad total=3
    out = recover_sequence(parsed)
    assert out[0].total == 4  # dominant
```

- [ ] **Step 2: Run, fail.**
- [ ] **Step 3: Implement:**

```python
@dataclass(frozen=True)
class PageRead:
    curr: int | None
    total: int | None
    code: str | None
    status: str  # "direct" | "recovered" | "failed"


def recover_sequence(parsed: list[tuple[int | None, int | None, str | None]]) -> list[PageRead]:
    """Fill no-read pages by completing the pagination cycle from neighbors.

    Lite recovery (spec D3): NOT autocorrelation/Dempster-Shafer. dominant_total
    is the most frequent read total; gaps are filled forward from the (possibly
    already-recovered) left neighbor, else from the original right neighbor.
    A gap with no usable sequence context stays ``failed``.
    """
    totals = [t for _, t, _ in parsed if t]
    dom = Counter(totals).most_common(1)[0][0] if totals else None
    out: list[PageRead] = [
        PageRead(c, t, code, "direct" if c is not None else "failed")
        for c, t, code in parsed
    ]
    for i, pr in enumerate(out):
        if pr.curr is not None:
            continue
        rec: int | None = None
        if dom:
            left = out[i - 1].curr if i > 0 else None
            if left is not None:
                rec = left % dom + 1
            elif i + 1 < len(parsed) and parsed[i + 1][0] is not None:
                rec = (parsed[i + 1][0] - 2) % dom + 1
        if rec is not None:
            out[i] = PageRead(rec, dom, None, "recovered")
    return out
```

- [ ] **Step 4: Run, pass.**
- [ ] **Step 5: Commit** — `git commit -am "feat(eval): pagination engine recover_sequence (lite gap recovery)"`

### Task 4: `count_starts` + cover_code filter

- [ ] **Step 1: Failing tests:**

```python
from eval.pagination_count.engine import count_starts

def _reads(specs):  # specs: list of (curr, code)
    return [PageRead(c, None, code, "direct") for c, code in specs]

def test_count_starts_plain():
    reads = _reads([(1,"A"),(2,"A"),(1,"A"),(2,"A")])
    assert count_starts(reads, cover_code=None) == 2

def test_count_starts_cover_code_filters_appendix():
    # IRL: one ODI-01 cover (start) + appendix page-1s with other codes
    reads = _reads([(1,"F-CRS-ODI-01"),(2,"F-CRS-ODI-01"),(1,"F-CRS-ODI-02"),(1,"F-CRS-ODI-02")])
    assert count_starts(reads, cover_code="F-CRS-ODI-01") == 1

def test_count_starts_cover_code_substring_match():
    reads = _reads([(1,"Código-F-CRS-ODI-01-rev")])
    assert count_starts(reads, cover_code="F-CRS-ODI-01") == 1
```

- [ ] **Step 2: Run, fail.**
- [ ] **Step 3: Implement:**

```python
def count_starts(reads: list[PageRead], cover_code: str | None) -> int:
    """Count document starts (curr == 1). With cover_code, count only starts
    whose page code contains cover_code (IRL: ignore appendix page-1s)."""
    if cover_code:
        cc = cover_code.upper()
        return sum(1 for r in reads if r.curr == 1 and r.code and cc in r.code.upper())
    return sum(1 for r in reads if r.curr == 1)
```

- [ ] **Step 4: Run, pass.**
- [ ] **Step 5: Commit** — `git commit -am "feat(eval): pagination engine count_starts + cover_code"`

### Task 5: `count_documents_by_pagination` orchestrator + synthetic-PDF integration test

> Orchestrates: per page → render corner (orientation-aware) → OCR → parse+code → recover → count. Returns `PaginationCountResult`. A7 handled by the caller (scanner), so this function assumes a multi-page PDF but must still work on any page count.

- [ ] **Step 1: Failing test** (uses the synthetic-PDF helper from Task 6 — write Task 6 first if executing strictly TDD; here we forward-reference `make_pagination_pdf`):

```python
from eval.pagination_count.engine import count_documents_by_pagination, PaginationCountResult
from core.scanners.cancellation import CancellationToken

def test_count_documents_synthetic_art(tmp_path, make_pagination_pdf):
    # 3 ART-like docs of 4 pages each: "Pagina {c} de 4" + code F-CRS-ART-01
    pdf = make_pagination_pdf(tmp_path / "art.pdf", docs=[(4, "F-CRS-ART-01")] * 3)
    r = count_documents_by_pagination(pdf, cancel=CancellationToken())
    assert r.count == 3
    assert r.failed_reads == 0

def test_count_documents_cover_code_irl(tmp_path, make_pagination_pdf):
    # 1 ODI-01 form (5p) + 2 single-page appendices with other code
    pdf = make_pagination_pdf(
        tmp_path / "irl.pdf",
        docs=[(5, "F-CRS-ODI-01"), (1, "F-CRS-ODI-02"), (1, "F-CRS-ODI-02")],
    )
    r = count_documents_by_pagination(pdf, cancel=CancellationToken(), cover_code="F-CRS-ODI-01")
    assert r.count == 1
```

- [ ] **Step 2: Run, fail.**
- [ ] **Step 3: Implement:**

```python
# Corner crop (relative). Portrait vs landscape get different x0 (text is top-right in both).
_CORNER_PORTRAIT = (0.50, 0.0, 1.0, 0.15)
_CORNER_LANDSCAPE = (0.62, 0.0, 1.0, 0.12)
_OCR_DPI = 216


@dataclass(frozen=True)
class PaginationCountResult:
    count: int
    pages_total: int
    direct_reads: int
    recovered_reads: int
    failed_reads: int
    dominant_total: int | None
    codes: dict[str, int]


def _ocr_corner(pdf_path: Path, page_idx: int) -> str:
    import fitz
    import pytesseract
    # orientation: read page rect cheaply
    with fitz.open(pdf_path) as doc:
        r = doc[page_idx].rect
        landscape = r.width > r.height
    bbox = _CORNER_LANDSCAPE if landscape else _CORNER_PORTRAIT
    pil = render_page_region(pdf_path, page_idx, bbox=bbox, dpi=_OCR_DPI).convert("L")
    return pytesseract.image_to_string(pil, config="--psm 6 --oem 1", lang="spa+eng").strip()


def count_documents_by_pagination(
    pdf_path: Path,
    *,
    cancel: CancellationToken,
    cover_code: str | None = None,
    on_page: Callable[[int, int], None] | None = None,
) -> PaginationCountResult:
    """Count documents in a compilation by their "Página N de M" pagination."""
    cancel.check()
    n = get_page_count(pdf_path)
    parsed: list[tuple[int | None, int | None, str | None]] = []
    codes: Counter[str] = Counter()
    for pi in range(n):
        cancel.check()
        try:
            raw = _ocr_corner(pdf_path, pi)
        except PdfRenderError:
            raw = ""
        curr, total = parse_pagination(raw)
        code = extract_code(raw)
        if code:
            codes[code] += 1
        parsed.append((curr, total, code))
        if on_page is not None:
            on_page(pi + 1, n)
    reads = recover_sequence(parsed)
    count = count_starts(reads, cover_code)
    return PaginationCountResult(
        count=count,
        pages_total=n,
        direct_reads=sum(1 for r in reads if r.status == "direct"),
        recovered_reads=sum(1 for r in reads if r.status == "recovered"),
        failed_reads=sum(1 for r in reads if r.status == "failed"),
        dominant_total=(reads[0].total if reads else None),
        codes=dict(codes),
    )
```

- [ ] **Step 4: Run, pass** (after Task 6 helper exists).
- [ ] **Step 5: Commit** — `git commit -am "feat(eval): count_documents_by_pagination orchestrator"`

---

## Chunk 2: Synthetic fixtures + benchmark + GT (eval validation)

**Files:**
- Create: `eval/tests/conftest.py` (or extend) — `make_pagination_pdf` fixture
- Create: `eval/pagination_count/samples.py` — GT manifest (**controller-labeled**)
- Create: `eval/pagination_count/benchmark.py`, `eval/pagination_count/report.py`
- Ensure: `eval/pagination_count/results/` is gitignored

### Task 6: Synthetic pagination-PDF test helper

- [ ] **Step 1: Failing test** — a self-test that the helper produces the right page count and OCR-able pagination:

```python
def test_make_pagination_pdf(tmp_path, make_pagination_pdf):
    pdf = make_pagination_pdf(tmp_path / "x.pdf", docs=[(2, "F-CRS-ODI-03"), (2, "F-CRS-ODI-03")])
    from core.scanners.utils.pdf_render import get_page_count
    assert get_page_count(pdf) == 4
```

- [ ] **Step 2: Run, fail.**
- [ ] **Step 3: Implement** the pytest fixture in `eval/tests/conftest.py`:

```python
import fitz
import pytest

@pytest.fixture
def make_pagination_pdf():
    """Generate a synthetic compilation PDF: docs=[(n_pages, code), ...].
    Draws "Código: {code}" and "Página {c} de {n}" in the top-right corner of each page.
    NO personal data — safe to use in committed tests.
    """
    def _make(path, docs, landscape=False):
        doc = fitz.open()
        for n_pages, code in docs:
            for c in range(1, n_pages + 1):
                rect = fitz.paper_rect("a4-l" if landscape else "a4")
                page = doc.new_page(width=rect.width, height=rect.height)
                x = page.rect.width - 230
                page.insert_text((x, 36), f"Codigo: {code}", fontsize=10)
                page.insert_text((x, 52), f"Pagina {c} de {n_pages}", fontsize=10)
                page.insert_text((72, 200), "contenido de prueba", fontsize=12)
        doc.save(path)
        doc.close()
        return path
    return _make
```

- [ ] **Step 4: Run, pass** (and re-run Task 5 tests → pass).
- [ ] **Step 5: Commit** — `git commit -am "test(eval): synthetic pagination-PDF fixture"`

### Task 7 [CONTROLLER]: Label GT samples manifest

> **Controller-owned.** The controller renders light page-range slices of the real corpus and hand-counts documents by looking (using ALL cues, not just pagination, to avoid circularity), then writes the manifest. Slices stay light (~30–60 pages). The manifest references corpus paths + ranges + GT counts; it does NOT copy corpus bytes.

- [ ] **Step 1:** For each family pick 1–2 light samples (Tier A: art slice, odi, ext, bodega, caliente slice, altura, insgral×2 [1pp & 6pp]; "verificar": exc, herramientas_elec, andamios; special: irl 1-packet; control RCH: chintegral, charla [expect pagination to over/mis-count → stays anchors]). Render with `.tmp_ocr_refine/render.py`-style slicing and **count by eye**.
- [ ] **Step 2:** Write `eval/pagination_count/samples.py`:

```python
"""Hand-labeled GT for the pagination benchmark (controller-curated 2026-06-20).
Each sample: corpus-relative file glob, page range (None=whole), GT doc count,
the family/sigla, and the current method for the baseline comparison. Light slices
only. GT counted by eye from ALL cues (not just pagination) to stay non-circular."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Sample:
    sigla: str
    glob: str          # under INFORME_MENSUAL_ROOT/MAYO
    page_range: tuple[int, int] | None
    gt: int
    cover_code: str | None = None

SAMPLES: list[Sample] = [
    # filled by controller, e.g.:
    Sample("odi", "HRB/3.-ODI Visitas/**/*odi*.pdf", None, 21),
    Sample("art", "HLL/7.-ART/*art*.pdf", (0, 120), 30),  # GT counted by eye
    Sample("irl", "HLU/2.-Induccion IRL/**/*mathias*.pdf", None, 1, cover_code="F-CRS-ODI-01"),
    # ... (the rest, ~12-16 samples)
]
```

- [ ] **Step 3: Commit** — `git commit -am "test(eval): hand-labeled pagination GT samples"`

### Task 8: Benchmark + report

- [ ] **Step 1:** Implement `benchmark.py`: for each `Sample`, run (a) the **current production scanner** for that sigla on the slice (extract slice to a temp single-PDF folder named with the sigla token, call `_scanner_for_sigla(sigla).count_ocr(folder, cancel=...)`), and (b) `count_documents_by_pagination` on the slice; record both vs `gt`. Write JSON to `results/` (gitignored).
- [ ] **Step 2:** Implement `report.py`: print a **Markdown table** to stdout — per sample: sigla, pages, GT, current_count (Δ), pagination_count (Δ), recovered_ratio; plus a per-family roll-up and a **migration verdict** column (`MIGRATE` if pagination |Δ| ≤ current |Δ| across that sigla's samples, else `KEEP`).
- [ ] **Step 3:** Add `eval/pagination_count/results/` to `.gitignore`.
- [ ] **Step 4: Commit** — `git commit -am "feat(eval): pagination benchmark + report"`

### Task 9 [CONTROLLER]: Run benchmark, decide migrations

> **Controller-owned.** Run `PYTHONPATH=. python eval/pagination_count/benchmark.py && python eval/pagination_count/report.py`. Record the per-sigla verdict. Output: the **GO list** of siglas to migrate (Tier A confirmed + any "verificar" that passed). This list drives Task 13. No code; updates the plan's migration list + a note in the spec's §5 if any "(verificar)" resolves.

---

## Chunk 3: Port to core + wire scanner (TDD)

**Files:**
- Create: `core/scanners/utils/pagination_count.py` (port of the eval engine)
- Test: `tests/unit/scanners/test_pagination_count.py`
- Modify: `core/scanners/patterns.py` (`SiglaPattern` += `cover_code`)
- Modify: `core/scanners/pagination_scanner.py` (use new engine; thread `on_page`; method `"pagination"`)
- Test: `tests/unit/scanners/test_pagination_scanner.py` (extend)

### Task 10: Port engine to core + mirror tests

- [ ] **Step 1:** Copy `eval/pagination_count/engine.py` → `core/scanners/utils/pagination_count.py` (same pure functions + `PaginationCountResult` + `count_documents_by_pagination`). Keep the eval copy (eval-isolation, like `inference_tuning/inference.py`).
- [ ] **Step 2:** Write `tests/unit/scanners/test_pagination_count.py` = the same pure-function tests as Task 1–4 (import from `core.scanners.utils.pagination_count`) + the two synthetic-PDF integration tests (reuse the `make_pagination_pdf` fixture — move it to `tests/conftest.py` or a shared location importable by both `eval/tests` and `tests/`).
- [ ] **Step 3: Run** `pytest tests/unit/scanners/test_pagination_count.py -v` → PASS.
- [ ] **Step 4: Commit** — `git commit -am "feat(scanners): port pagination_count engine to core"`

### Task 11: Extend `SiglaPattern` + wire `PaginationScanner` to the new engine

- [ ] **Step 1: Failing test** in `tests/unit/scanners/test_pagination_scanner.py`: with a synthetic multi-page PDF in a temp folder, `PaginationScanner(sigla="insgral").count_ocr(folder, cancel=...)` returns `method == "pagination"` and the right `count`; and `on_page` is invoked (capture calls). Add a `cover_code` test: a sigla whose pattern sets `cover_code` filters appendix starts.
- [ ] **Step 2: Run, fail.**
- [ ] **Step 3: Implement:**
  - `patterns.py`: add `cover_code: NotRequired[str]` to `SiglaPattern` docstring + TypedDict.
  - `pagination_scanner.py`: replace the `count_documents_v4(pdf, cancel=cancel)` call with `count_documents_by_pagination(pdf, cancel=cancel, cover_code=PATTERNS[self.sigla].get("cover_code"), on_page=on_page)`. Map result→`ScanResult`: `method="pagination"`; `confidence = LOW if (result.failed_reads > 0 or result.recovered_reads / max(1, result.pages_total) > RECOVERY_LOW_CONF_RATIO) else HIGH`; keep A7/A8, `per_file`, the degenerate-0→1 guard, the `on_pdf(name, count, "pagination", [])` callback, and the `finally` cancel semantics **byte-for-byte** as today (only the engine call + method string + confidence rule change).
  - Keep `count_documents_v4` import for the optional fallback (D10) but **do not** call it yet (off by default).
- [ ] **Step 4: Run, pass** (+ full `pytest tests/unit/scanners -q`).
- [ ] **Step 5: Commit** — `git commit -am "feat(scanners): PaginationScanner uses pagination engine + on_page + cover_code"`

### Task 12: Frontend `method` chip value `"pagination"`

- [ ] **Step 1:** Find where per-file method chips render (`frontend/src/` — search for `"header_band_anchors"` / `"v4"` chip mapping). Write a vitest asserting a `"pagination"` method maps to a chip label (e.g. "Paginación") parallel to the existing ones.
- [ ] **Step 2: Run, fail.**
- [ ] **Step 3: Implement** the chip mapping addition (token-compliant, parallel naming per `feedback_chip_consistency`).
- [ ] **Step 4: Run** `cd frontend && npx vitest run` → PASS; `npm run build`.
- [ ] **Step 5: Commit** — `git commit -am "feat(frontend): pagination method chip"`

---

## Chunk 4: Migration + validation + smoke

**Files:**
- Modify: `core/scanners/patterns.py` (migrate GO-list siglas: `scan_strategy` → `"pagination"`, set `cover_code` for irl)
- Modify: `core/utils.py` (`SCANNER_PATTERNS_VERSION` bump)
- Test: `tests/unit/scanners/test_count_type.py` / completeness gate (ensure still green)

### Task 13: Migrate validated siglas + version bump

- [ ] **Step 1: Failing/Guard test:** extend the patterns completeness test to assert the migrated siglas now have `scan_strategy == "pagination"` and `irl` has `cover_code == "F-CRS-ODI-01"`. (Only the siglas on the Task 9 GO list.)
- [ ] **Step 2: Run, fail.**
- [ ] **Step 3: Implement:** for each GO-list sigla, change `"scan_strategy"` to `"pagination"` in `PATTERNS` (and add `"cover_code": "F-CRS-ODI-01"` to `irl`). Bump `SCANNER_PATTERNS_VERSION` in `core/utils.py` with a dated suffix. Leave RCH (charla/chintegral/dif_pts), senal, chps, maquinaria, reunion unchanged.
- [ ] **Step 4: Run** the full backend suite `pytest -m "not slow" -q` + `ruff check .` → green. Confirm no test regressed (free cells / single-user path untouched).
- [ ] **Step 5: Commit** — `git commit -am "feat(scanners): migrate paginated siglas to pagination engine + bump version"`

### Task 14: Full verification gate

- [ ] **Step 1:** `pytest -m "not slow" -q` (incl. eval/tests) → 0 failures.
- [ ] **Step 2:** `ruff check .` → 0 violations.
- [ ] **Step 3:** `cd frontend && npx vitest run && npm run build` → green.
- [ ] **Step 4:** (optional) run the slow OCR integration suite if present for the scanners.
- [ ] No commit (gate only).

### Task 15 [CONTROLLER]: Live smoke (Brave debug, copy DB)

> **Controller-owned.** Data-safe: copy `overseer.db` → smoke DB, run a 2nd backend on `PORT=8010` with `OVERSEER_DB_PATH=<copy>`; corpus read-only. Open a real month, run pase-2 OCR on a migrated sigla cell, compare the new pagination count vs the pre-migration count (and vs the eye-count) per cell. Verify the `"pagination"` chip + honest confidence (amber on low-direct cells) render. Confirm the real `overseer.db` is byte-identical (sha256) after. Drive via chrome-devtools per `feedback_browser_testing_via_devtools`.

- [ ] **Step 1:** Snapshot real DB sha256. Copy to smoke DB. Launch 2nd backend on :8010 + (if needed) frontend pointing at it.
- [ ] **Step 2:** For 2–3 migrated siglas on a real cell, run OCR; record count + confidence; compare to GT/eye-count.
- [ ] **Step 3:** Verify chip + amber + keyboard-counter path on a low-confidence cell.
- [ ] **Step 4:** Tear down; confirm real DB sha256 unchanged.

### Task 16: Final review + ship

- [ ] **Step 1:** Dispatch the holistic code reviewer (superpowers:code-reviewer) over the whole branch diff vs the spec.
- [ ] **Step 2:** Fix any blocking findings.
- [ ] **Step 3:** Clean up `.tmp_ocr_refine/` (delete throwaway scripts; their logic now lives in `eval/pagination_count/`).
- [ ] **Step 4:** Push `po_overhaul`; tag `ocr-pagination-mvp`. Write memory `project_ocr_pagination_shipped`.

---

## Test design notes (for the implementer)

- **Pure functions** (`parse_pagination`/`extract_code`/`recover_sequence`/`count_starts`) carry the logic — test them exhaustively with synthetic strings/sequences (OCR noise, gaps, orphans, dominant-total outliers). No PDF needed.
- **OCR orchestration** — test with the synthetic `make_pagination_pdf` (clean, deterministic, no personal data). Do NOT depend on the real corpus or commit slices of it.
- **Recovery correctness** is the highest-risk logic: a recovered read must never *invent* a `curr==1` between two valid reads of the same cycle (forward fill from the left neighbor guarantees this).
- **No regression:** the migration only flips `scan_strategy`; un-migrated siglas, free cells, and the single-user path are untouched. The `count_ocr`/`ScanResult` contract is unchanged, so no frontend change beyond the additive chip.
- **DB mocking:** none — use real fixtures (synthetic PDFs) per project convention.

## Risks & rollback
- Any migrated sigla that regresses in the live smoke (Task 15) → revert that one sigla's `scan_strategy` to `"anchors"` (one line) and re-bump version. The rest stay migrated.
- If lite recovery proves insufficient for a sigla in eval (Task 9), enable the V4 fallback (D10) for that sigla's low-confidence files, gated behind the eval result.
