# OCR Pagination-Count Refinement Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking. **Execute tasks in numerical order.**
>
> **Controller-owned tasks** (do NOT delegate to an implementer subagent — they need human/vision judgment): **Task 7** (label GT by looking at pages), **Task 9** (GO/NO-GO migration decision), **Task 15** (live browser smoke). Everything else is delegatable.

**Goal:** Replace brittle text-anchor counting with a unified pagination-based document counter (orientation-aware corner OCR + lite sequence-recovery + form-code routing + honest confidence) for the paginated siglas, migrated gradually and reversibly.

**Architecture:** A new pure-logic-heavy engine `count_documents_by_pagination` lives behind the *existing* `PaginationScanner` / `count_ocr` interface (zero contract change). Build + validate it in `eval/pagination_count/` against the real merged MAYO corpus first (eval-first), then port to `core/scanners/utils/pagination_count.py`, wire it into `PaginationScanner`, and migrate validated siglas by flipping `scan_strategy` in `patterns.py`. Each sigla migration is gated by an eval accuracy check and is one-line reversible.

**Tech Stack:** Python 3.10+, PyMuPDF (`fitz`), pytesseract (Tesseract `--psm 6 --oem 1`, `spa+eng`), pytest. Frontend unaffected except a new `method` chip value `"pagination"`.

**Spec:** `docs/superpowers/specs/2026-06-20-ocr-pagination-refinement-design.md` (read it; this plan implements §6/§7/§10/§11 and decisions D1–D11).

**Key existing seams (verified against the repo):**
- `core/scanners/utils/pdf_render.py`: `render_page_region(pdf_path, page_idx, *, bbox=(x0,y0,x1,y1) in [0..1], dpi)` → PIL.Image; `get_page_count`; `PdfRenderError`. (The engine renders corners with `fitz` directly — single open per PDF, see Task 6 A2 note — but `render_page_region` is the reference for bbox semantics.)
- `core/scanners/utils/header_band_anchors.py`: OCR pattern `pytesseract.image_to_string(pil, config="--psm 6 --oem 1", lang="spa+eng")`; `_normalize_text(text)`.
- `core/scanners/pagination_scanner.py`: `PaginationScanner.count_ocr(folder, *, cancel, on_pdf, only, skip, on_page)`; today calls `count_documents_v4`; A7 (1-page→1 doc), A8 (missing folder); flags `"a7_one_page_locked"`, `"v4_low_confidence"`.
- `core/scanners/base.py`: `ScanResult(count, confidence, method, breakdown, flags, errors, duration_ms, files_scanned, per_file, telemetry)`; `ConfidenceLevel.{HIGH,LOW}`.
- `core/scanners/__init__.py`: `_build_scanner_for_sigla` picks the scanner from `PATTERNS[sigla]["scan_strategy"]` → **migration = change that field**.
- `core/scanners/patterns.py`: `PATTERNS`, `SiglaPattern` TypedDict (uses `NotRequired`), `count_type_for`.
- `core/utils.py:56`: `SCANNER_PATTERNS_VERSION` (bump on scan-strategy changes).
- `core/scanners/cancellation.py`: `CancellationToken` (`.cancelled`, `.check()`), `CancelledError`.

**Data-safety (NON-NEGOTIABLE):**
- Tests use **synthetic generated PDFs only** (fake "Página N de M" + dummy text). NEVER commit real corpus slices — they contain worker names/RUTs.
- The eval benchmark reads the real corpus from `INFORME_MENSUAL_ROOT` at **runtime**; its outputs are gitignored.
- Live smoke uses a **copy** of `overseer.db` on a separate port; never the real DB; corpus is read-only.

---

## Chunk 1: Engine core (pure logic, TDD) in `eval/pagination_count/`

> Build the engine in eval first (eval-first). The pure functions are the heart and are tested with zero OCR/PDF dependency. The synthetic-PDF fixture (Task 5) is built **before** the orchestrator (Task 6) so the orchestrator's integration test can use it.

**Files:**
- Create: `eval/pagination_count/__init__.py`, `eval/pagination_count/engine.py`, `eval/pagination_count/README.md`
- Create/extend: `conftest.py` at the **project root** (`a:/PROJECTS/PDFoverseer/conftest.py`) for the shared fixture
- Test: `eval/tests/test_pagination_engine.py`

### Task 1: Scaffold + `parse_pagination`

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

Pure functions (parse_pagination / extract_code / dominant_total / recover_sequence /
count_starts) have zero OCR/PDF dependency and are unit-tested directly.
count_documents_by_pagination is the thin OCR orchestrator (integration-tested with
synthetic PDFs).
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.scanners.cancellation import CancellationToken

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

### Task 3: `dominant_total` + `recover_sequence` (the heart)

- [ ] **Step 1: Failing tests** — `dominant_total` (mode of totals, ignores outliers), and `recover_sequence` for: no gaps, run of gaps (forward fill), leading gap (right neighbor), orphan (failed), recovered page carries the dominant total:

```python
from eval.pagination_count.engine import dominant_total, recover_sequence, PageRead

def _currs(reads): return [r.curr for r in reads]
def _status(reads): return [r.status for r in reads]

def test_dominant_total_mode_ignores_outliers():
    parsed = [(1,4,"A"),(2,4,"A"),(3,4,"A"),(4,4,"A"),(1,4,"A"),(2,3,"A")]  # one bad total=3
    assert dominant_total(parsed) == 4

def test_dominant_total_none_when_no_totals():
    assert dominant_total([(None,None,None),(1,None,"A")]) is None

def test_recover_no_gaps():
    parsed = [(1,4,"A"),(2,4,"A"),(3,4,"A"),(4,4,"A")]
    out = recover_sequence(parsed)
    assert _currs(out) == [1,2,3,4]
    assert _status(out) == ["direct"]*4

def test_recover_run_of_gaps_forward_fill():
    # ART rhythm with 2 unreadable corners mid-run
    parsed = [(1,4,"A"),(None,None,None),(None,None,None),(4,4,"A"),(1,4,"A")]
    out = recover_sequence(parsed)
    assert _currs(out) == [1,2,3,4,1]
    assert _status(out) == ["direct","recovered","recovered","direct","direct"]

def test_recovered_page_carries_dominant_total():
    parsed = [(1,4,"A"),(None,None,None),(3,4,"A"),(4,4,"A")]
    out = recover_sequence(parsed)
    assert out[1].status == "recovered" and out[1].curr == 2 and out[1].total == 4

def test_recover_leading_gap_uses_right_neighbor():
    parsed = [(None,None,None),(2,4,"A"),(3,4,"A"),(4,4,"A")]
    out = recover_sequence(parsed)
    assert _currs(out)[0] == 1

def test_recover_orphan_is_failed():
    parsed = [(None,None,None)]  # no dominant total, no neighbor
    out = recover_sequence(parsed)
    assert out[0].status == "failed" and out[0].curr is None
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


def dominant_total(parsed: list[tuple[int | None, int | None, str | None]]) -> int | None:
    """The most frequent read total (the pagination period), or None if no totals read."""
    totals = [t for _, t, _ in parsed if t]
    return Counter(totals).most_common(1)[0][0] if totals else None


def recover_sequence(
    parsed: list[tuple[int | None, int | None, str | None]],
    dom: int | None = None,
) -> list[PageRead]:
    """Fill no-read pages by completing the pagination cycle from neighbors.

    Lite recovery (spec D3): NOT autocorrelation/Dempster-Shafer. ``dom`` is the
    dominant (mode) total; gaps fill forward from the (possibly already-recovered)
    left neighbor, else from the original right neighbor. A gap with no usable
    sequence context stays ``failed``. Recovered pages carry ``total = dom`` and
    ``code = None`` (their corner wasn't read).
    """
    if dom is None:
        dom = dominant_total(parsed)
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
- [ ] **Step 5: Commit** — `git commit -am "feat(eval): pagination engine dominant_total + recover_sequence"`

### Task 4: `count_starts` + cover_code filter (with documented IRL limitation)

- [ ] **Step 1: Failing tests** — plain count, cover_code filter, substring match, AND the **documented limitation** (a recovered curr==1 with code=None is NOT counted under cover_code):

```python
from eval.pagination_count.engine import count_starts, PageRead

def _reads(specs):  # specs: list of (curr, code, status)
    return [PageRead(c, None, code, st) for c, code, st in specs]

def test_count_starts_plain():
    reads = _reads([(1,"A","direct"),(2,"A","direct"),(1,"A","direct"),(2,"A","direct")])
    assert count_starts(reads, cover_code=None) == 2

def test_count_starts_cover_code_filters_appendix():
    reads = _reads([(1,"F-CRS-ODI-01","direct"),(2,"F-CRS-ODI-01","direct"),
                    (1,"F-CRS-ODI-02","direct"),(1,"F-CRS-ODI-02","direct")])
    assert count_starts(reads, cover_code="F-CRS-ODI-01") == 1

def test_count_starts_cover_code_substring_match():
    reads = _reads([(1,"Código-F-CRS-ODI-01-rev","direct")])
    assert count_starts(reads, cover_code="F-CRS-ODI-01") == 1

def test_count_starts_cover_code_skips_recovered_cover_DOCUMENTED_LIMITATION():
    # A recovered curr==1 has code=None → not counted under cover_code. The scanner
    # compensates by forcing LOW confidence when cover_code is set and recovered
    # reads exist (Task 11), so the operator reviews. This test pins the behavior.
    reads = _reads([(1,None,"recovered"),(2,"F-CRS-ODI-01","direct")])
    assert count_starts(reads, cover_code="F-CRS-ODI-01") == 0
```

- [ ] **Step 2: Run, fail.**
- [ ] **Step 3: Implement:**

```python
def count_starts(reads: list[PageRead], cover_code: str | None) -> int:
    """Count document starts (curr == 1).

    With ``cover_code`` set, count only starts whose page code contains it (IRL:
    ignore appendix page-1s). KNOWN LIMITATION: a *recovered* curr==1 page has
    ``code=None`` and is therefore NOT counted under cover_code (a cover whose
    corner OCR failed would be missed). The scanner offsets this by forcing LOW
    confidence when cover_code is set and any recovered read exists (Task 11), so
    the operator reviews. In practice IRL covers are the cleanest page of a packet
    and read directly; the eval (Task 9) confirms the real impact.
    """
    if cover_code:
        cc = cover_code.upper()
        return sum(1 for r in reads if r.curr == 1 and r.code and cc in r.code.upper())
    return sum(1 for r in reads if r.curr == 1)
```

- [ ] **Step 4: Run, pass.**
- [ ] **Step 5: Commit** — `git commit -am "feat(eval): pagination engine count_starts + cover_code (documented limitation)"`

### Task 5: Synthetic pagination-PDF fixture (built before the orchestrator)

> Placed at the **project-root `conftest.py`** so it is visible to BOTH `eval/tests/` and `tests/` (pytest loads the rootdir conftest for the whole session; a fixture in `eval/tests/conftest.py` would NOT be visible to `tests/`). If a root `conftest.py` already exists, append to it.

- [ ] **Step 1: Failing self-test** in `eval/tests/test_pagination_engine.py`:

```python
def test_make_pagination_pdf(tmp_path, make_pagination_pdf):
    from core.scanners.utils.pdf_render import get_page_count
    pdf = make_pagination_pdf(tmp_path / "x.pdf", docs=[(2, "F-CRS-ODI-03"), (2, "F-CRS-ODI-03")])
    assert get_page_count(pdf) == 4
    land = make_pagination_pdf(tmp_path / "l.pdf", docs=[(1, "F-CRS-LCH-22")], landscape=True)
    assert get_page_count(land) == 1
```

- [ ] **Step 2: Run, fail** (fixture not defined).
- [ ] **Step 3: Implement** the fixture in `a:/PROJECTS/PDFoverseer/conftest.py`:

```python
import fitz
import pytest


@pytest.fixture
def make_pagination_pdf():
    """Generate a synthetic compilation PDF: docs=[(n_pages, code), ...].
    Draws "Codigo: {code}" and "Pagina {c} de {n}" in the top-right corner of each
    page. NO personal data — safe to commit and use in tests. landscape=True emits
    A4-landscape pages (exercises the orientation branch)."""
    def _make(path, docs, landscape=False):
        doc = fitz.open()
        rect = fitz.paper_rect("a4-l" if landscape else "a4")
        for n_pages, code in docs:
            for c in range(1, n_pages + 1):
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

- [ ] **Step 4: Run, pass.**
- [ ] **Step 5: Commit** — `git add conftest.py eval/tests/test_pagination_engine.py && git commit -m "test(eval): synthetic pagination-PDF fixture (root conftest)"`

### Task 6: `count_documents_by_pagination` orchestrator (single-open, orientation-aware)

> A2 fix: open each PDF **once** with `fitz` and render corners inline (avoids the double-open of calling `render_page_region` per page). A3: includes a landscape integration test. B2 fix: `dominant_total` field comes from `dominant_total(parsed)`, not `reads[0].total`.

- [ ] **Step 1: Failing tests:**

```python
from eval.pagination_count.engine import count_documents_by_pagination, PaginationCountResult
from core.scanners.cancellation import CancellationToken

def test_count_documents_synthetic_art(tmp_path, make_pagination_pdf):
    pdf = make_pagination_pdf(tmp_path / "art.pdf", docs=[(4, "F-CRS-ART-01")] * 3)
    r = count_documents_by_pagination(pdf, cancel=CancellationToken())
    assert r.count == 3 and r.failed_reads == 0 and r.dominant_total == 4

def test_count_documents_cover_code_irl(tmp_path, make_pagination_pdf):
    pdf = make_pagination_pdf(tmp_path / "irl.pdf",
        docs=[(5, "F-CRS-ODI-01"), (1, "F-CRS-ODI-02"), (1, "F-CRS-ODI-02")])
    r = count_documents_by_pagination(pdf, cancel=CancellationToken(), cover_code="F-CRS-ODI-01")
    assert r.count == 1

def test_count_documents_landscape(tmp_path, make_pagination_pdf):
    pdf = make_pagination_pdf(tmp_path / "senal.pdf",
        docs=[(1, "F-CRS-LCH-22")] * 5, landscape=True)
    r = count_documents_by_pagination(pdf, cancel=CancellationToken())
    assert r.count == 5

def test_count_documents_on_page_callback(tmp_path, make_pagination_pdf):
    pdf = make_pagination_pdf(tmp_path / "p.pdf", docs=[(2, "F-CRS-ODI-03")])
    seen = []
    count_documents_by_pagination(pdf, cancel=CancellationToken(), on_page=lambda d, t: seen.append((d, t)))
    assert seen == [(1, 2), (2, 2)]
```

- [ ] **Step 2: Run, fail.**
- [ ] **Step 3: Implement** (append to `engine.py`):

```python
import io

import fitz
import pytesseract
from PIL import Image

# Corner crop (relative x0,y0,x1,y1). Text is top-right in both orientations.
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
    cover_code_recovery: bool  # cover_code set AND >=1 recovered read → caller forces LOW


def _corner_text(page: fitz.Page) -> str:
    r = page.rect
    bbox = _CORNER_LANDSCAPE if r.width > r.height else _CORNER_PORTRAIT
    clip = fitz.Rect(
        r.x0 + bbox[0] * r.width, r.y0 + bbox[1] * r.height,
        r.x0 + bbox[2] * r.width, r.y0 + bbox[3] * r.height,
    )
    pix = page.get_pixmap(matrix=fitz.Matrix(_OCR_DPI / 72.0, _OCR_DPI / 72.0), clip=clip, alpha=False)
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
    return pytesseract.image_to_string(img, config="--psm 6 --oem 1", lang="spa+eng").strip()


def count_documents_by_pagination(
    pdf_path: Path,
    *,
    cancel: CancellationToken,
    cover_code: str | None = None,
    on_page: Callable[[int, int], None] | None = None,
) -> PaginationCountResult:
    """Count documents in a compilation by their "Página N de M" pagination."""
    cancel.check()
    parsed: list[tuple[int | None, int | None, str | None]] = []
    codes: Counter[str] = Counter()
    with fitz.open(pdf_path) as doc:  # single open (A2)
        n = doc.page_count
        for pi in range(n):
            cancel.check()
            raw = _corner_text(doc[pi])
            curr, total = parse_pagination(raw)
            code = extract_code(raw)
            if code:
                codes[code] += 1
            parsed.append((curr, total, code))
            if on_page is not None:
                on_page(pi + 1, n)
    dom = dominant_total(parsed)
    reads = recover_sequence(parsed, dom)
    recovered = sum(1 for r in reads if r.status == "recovered")
    return PaginationCountResult(
        count=count_starts(reads, cover_code),
        pages_total=len(reads),
        direct_reads=sum(1 for r in reads if r.status == "direct"),
        recovered_reads=recovered,
        failed_reads=sum(1 for r in reads if r.status == "failed"),
        dominant_total=dom,
        codes=dict(codes),
        cover_code_recovery=bool(cover_code) and recovered > 0,
    )
```

> Note: `fitz`/`pytesseract`/`PIL` imports are placed with the orchestrator (the pure functions above need none). If ruff prefers top-of-file imports, hoist them — they're real deps already used across the repo.

- [ ] **Step 4: Run, pass** — `pytest eval/tests/test_pagination_engine.py -v`.
- [ ] **Step 5: Commit** — `git commit -am "feat(eval): count_documents_by_pagination orchestrator (single-open, orientation, cover_code)"`

---

## Chunk 2: GT samples + benchmark (eval validation)

**Files:**
- Create: `eval/pagination_count/samples.py` (GT manifest — **controller-labeled**)
- Create: `eval/pagination_count/benchmark.py`, `eval/pagination_count/report.py`
- Modify: `.gitignore` (add `eval/pagination_count/results/`)

### Task 7 [CONTROLLER]: Label GT samples manifest

> **Controller-owned.** Render light page-range slices of the real corpus and hand-count documents by looking (using ALL cues — layout, fields, code — not just pagination, to avoid circularity), then write the manifest. Slices stay light (~30–60 pages). The manifest references corpus paths + ranges + GT counts; it does NOT copy corpus bytes.

- [ ] **Step 1:** For each family pick 1–2 light samples: Tier A (art slice, odi, ext, bodega, caliente slice, altura, insgral×2 [1pp & 6pp]); "verificar" (exc, herramientas_elec, andamios); special (irl 1-packet, cover_code=F-CRS-ODI-01); control RCH (chintegral, charla — expect pagination to mis-count → stays anchors). Render + **count by eye**.
- [ ] **Step 2:** Write `eval/pagination_count/samples.py`:

```python
"""Hand-labeled GT for the pagination benchmark (controller-curated 2026-06-20).
Light slices only. GT counted by eye from ALL cues (not just pagination) to stay
non-circular. References corpus paths under INFORME_MENSUAL_ROOT/MAYO at runtime."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Sample:
    sigla: str
    glob: str                       # under INFORME_MENSUAL_ROOT/MAYO
    page_range: tuple[int, int] | None
    gt: int
    cover_code: str | None = None

SAMPLES: list[Sample] = [
    # filled by controller, e.g.:
    Sample("odi", "HRB/3.-ODI Visitas/**/*odi*.pdf", None, 21),
    Sample("art", "HLL/7.-ART/*art*.pdf", (0, 120), 30),         # GT counted by eye
    Sample("irl", "HLU/2.-Induccion IRL/**/*mathias*.pdf", None, 1, cover_code="F-CRS-ODI-01"),
    # ... (the rest, ~12-16 samples)
]
```

- [ ] **Step 3: Commit** — `git commit -am "test(eval): hand-labeled pagination GT samples"`

### Task 8: Benchmark + report

**Files:** Create `eval/pagination_count/benchmark.py`, `eval/pagination_count/report.py`; Modify `.gitignore`

- [ ] **Step 1:** Implement `benchmark.py`: for each `Sample`, (a) extract the slice to a temp PDF in a temp folder, named with the sigla token (so filename-glob matches), (b) run the **current production scanner** via `from core.scanners import _build_scanner_for_sigla; _build_scanner_for_sigla(sample.sigla).count_ocr(folder, cancel=CancellationToken())`, (c) run `count_documents_by_pagination(slice_pdf, cancel=..., cover_code=sample.cover_code)`. Record both counts vs `gt`. Write JSON to `eval/pagination_count/results/` (gitignored). Use the project venv's Tesseract.
- [ ] **Step 2:** Implement `report.py`: read the results JSON and print a **Markdown table to stdout** — per sample: sigla, pages, GT, current_count (Δ), pagination_count (Δ), recovered_ratio; plus a per-family roll-up and a **migration verdict** column (`MIGRATE` if pagination |Δ| ≤ current |Δ| across that sigla's samples, else `KEEP`).
- [ ] **Step 3:** Add `eval/pagination_count/results/` to `.gitignore`.
- [ ] **Step 4: Run** `PYTHONPATH=. python eval/pagination_count/benchmark.py` then `PYTHONPATH=. python eval/pagination_count/report.py` → confirm a table prints.
- [ ] **Step 5: Commit** — `git commit -am "feat(eval): pagination benchmark + report"`

### Task 9 [CONTROLLER]: Run benchmark, decide migrations

> **Controller-owned.** Run benchmark + report. Record the per-sigla verdict. Output: the **GO list** of siglas to migrate (Tier A confirmed + any "verificar" that passed). This list drives Task 13. No code; updates this plan's Task 13 GO-list + a one-line note in spec §5 if any "(verificar)" resolves.

- [ ] **Step 1:** Run benchmark+report; capture the table.
- [ ] **Step 2:** Write the GO list into Task 13 below (replace the placeholder).

---

## Chunk 3: Port to core + wire scanner (TDD)

**Files:**
- Create: `core/scanners/utils/pagination_count.py` (port of the eval engine)
- Test: `tests/unit/scanners/test_pagination_count.py`
- Modify: `core/scanners/patterns.py` (`SiglaPattern` += `cover_code`)
- Modify: `core/scanners/pagination_scanner.py` (use new engine; thread `on_page`; method `"pagination"`)
- Test: `tests/unit/scanners/test_pagination_scanner.py` (extend)
- Modify: `frontend/src/...` (method chip) + a vitest

### Task 10: Port engine to core + mirror tests

- [ ] **Step 1:** Copy `eval/pagination_count/engine.py` → `core/scanners/utils/pagination_count.py` verbatim (same pure functions + `PaginationCountResult` + `count_documents_by_pagination`). Keep the eval copy (eval-isolation, like `inference_tuning/inference.py`).
- [ ] **Step 2:** Write `tests/unit/scanners/test_pagination_count.py` = the pure-function tests from Tasks 1–4 (import from `core.scanners.utils.pagination_count`) + the synthetic-PDF integration tests from Task 6 (the `make_pagination_pdf` fixture is in the root `conftest.py`, visible here).
- [ ] **Step 3: Run** `pytest tests/unit/scanners/test_pagination_count.py -v` → PASS. `ruff check core/scanners/utils/pagination_count.py` → 0.
- [ ] **Step 4: Commit** — `git commit -am "feat(scanners): port pagination_count engine to core"`

### Task 11: Extend `SiglaPattern` + wire `PaginationScanner` to the new engine

- [ ] **Step 1: Failing tests** in `tests/unit/scanners/test_pagination_scanner.py`: with a synthetic multi-page PDF in a temp folder, `PaginationScanner(sigla="insgral").count_ocr(folder, cancel=...)` returns `method == "pagination"` and the right `count`; `on_page` is invoked (capture calls); a multi-page PDF heavy on recovery returns `confidence == LOW`; with a pattern carrying `cover_code`, appendix starts are filtered AND `confidence == LOW` (cover_code recovery rule).
- [ ] **Step 2: Run, fail.**
- [ ] **Step 3: Implement:**
  - `patterns.py`: add `cover_code: NotRequired[str]` to the `SiglaPattern` TypedDict + docstring.
  - `pagination_scanner.py`: replace the `count_documents_v4(pdf, cancel=cancel)` call with `count_documents_by_pagination(pdf, cancel=cancel, cover_code=PATTERNS[self.sigla].get("cover_code"), on_page=on_page)`. Import `count_documents_by_pagination` + `RECOVERY_LOW_CONF_RATIO` from `core.scanners.utils.pagination_count`. **Do NOT import `count_documents_v4`** (D10 fallback is deferred; an unused import fails ruff F401). Map result→`ScanResult`:
    - `method="pagination"`
    - per-PDF `confidence`/trust: a PDF is low-trust if `result.failed_reads > 0` OR `result.recovered_reads / max(1, result.pages_total) > RECOVERY_LOW_CONF_RATIO` OR `result.cover_code_recovery`. Collect low-trust filenames into the existing `low_confidence_files` list; cell `confidence = LOW if errors or low_confidence_files else HIGH`.
    - rename the flag `"v4_low_confidence"` → `"pagination_low_confidence"`.
    - keep A7/A8, `per_file`, the degenerate-`0`→`1` guard, the `on_pdf(name, count, "pagination", [])` callback, and the `finally` cancel semantics **byte-for-byte** as today (only the engine call, method string, confidence inputs, and flag name change).
  - Update the `PaginationScanner` module + method docstrings (s/V4/pagination/ where they describe the engine; keep A7).
- [ ] **Step 4: Run, pass** — `pytest tests/unit/scanners -q`; `ruff check core/scanners` → 0.
- [ ] **Step 5: Commit** — `git commit -am "feat(scanners): PaginationScanner uses pagination engine + on_page + cover_code"`

### Task 12: Frontend `method` chip value `"pagination"`

- [ ] **Step 1:** Find where per-file method chips render (`frontend/src/` — grep for `"header_band_anchors"` / `"v4"` chip mapping). Write a vitest asserting a `"pagination"` method maps to a chip label (e.g. "Paginación") parallel to the existing ones (`feedback_chip_consistency`: same Badge shape, short parallel name).
- [ ] **Step 2: Run, fail** — `cd frontend && npx vitest run <file>`.
- [ ] **Step 3: Implement** the chip mapping addition (po-* tokens; do NOT add a new shape).
- [ ] **Step 4: Run** `cd frontend && npx vitest run` → PASS; `npm run build` → OK.
- [ ] **Step 5: Commit** — `git commit -am "feat(frontend): pagination method chip"`

---

## Chunk 4: Migration + validation + smoke

**Files:**
- Modify: `core/scanners/patterns.py` (migrate GO-list siglas), `core/utils.py` (version bump)
- Test: the patterns completeness/count_type gate (ensure green)

### Task 13: Migrate validated siglas + version bump

> **GO list** (DECIDED in Task 9 — see `docs/research/2026-06-21-pagination-benchmark-results.md`):
> **MIGRATE to `pagination`:** `odi, ext, bodega, caliente, exc, herramientas_elec, art, andamios`,
> and `irl` (add `"cover_code": "F-CRS-ODI-01"`). `altura, insgral` are already `pagination` →
> their engine auto-upgrades to the lite one (no patterns change for them).
> **KEEP `anchors` (controller override of the mechanical verdict):** `charla, chintegral, dif_pts`
> (RCH "1 de 2" bug, D6), `senal` (landscape — both methods got 0/18; open follow-up), `chps`,
> `maquinaria` (checks), `reunion` (none). `andamios` migrates but is expected to be honestly
> LOW-confidence (high recovery ratio) → keyboard-counter review.

- [ ] **Step 1: Guard test:** extend the patterns completeness test to assert each GO-list sigla now has `scan_strategy == "pagination"` and `irl` has `cover_code == "F-CRS-ODI-01"`.
- [ ] **Step 2: Run, fail.**
- [ ] **Step 3: Implement:** for each GO-list sigla, set `"scan_strategy": "pagination"` in `PATTERNS` (add `"cover_code": "F-CRS-ODI-01"` to `irl`). Bump `SCANNER_PATTERNS_VERSION` in `core/utils.py` with a dated suffix.
- [ ] **Step 4: Run** `pytest -m "not slow" -q` + `ruff check .` → green. Confirm no pre-existing test regressed.
- [ ] **Step 5: Commit** — `git commit -am "feat(scanners): migrate validated paginated siglas + bump SCANNER_PATTERNS_VERSION"`

### Task 14: Full verification gate

- [ ] **Step 1:** `pytest -m "not slow" -q` (incl. eval/tests) → 0 failures.
- [ ] **Step 2:** `ruff check .` → 0 violations.
- [ ] **Step 3:** `cd frontend && npx vitest run && npm run build` → green.
- [ ] No commit (gate only).

### Task 15 [CONTROLLER]: Live smoke (Brave debug, copy DB)

> **Controller-owned.** Data-safe: copy `overseer.db` → smoke DB, run a 2nd backend on `PORT=8010` with `OVERSEER_DB_PATH=<copy>`; corpus read-only. Drive via chrome-devtools (`feedback_browser_testing_via_devtools`).

- [ ] **Step 1:** Snapshot real DB sha256. Copy to smoke DB. Launch 2nd backend on :8010 (frontend `dist` served at `/`, or Vite pointed at :8010).
- [ ] **Step 2:** For 2–3 migrated siglas on a real cell, run pase-2 OCR; record count + confidence; compare to GT/eye-count and to the pre-migration count.
- [ ] **Step 3:** Verify the `"pagination"` chip renders + amber/keyboard-counter path on a low-confidence cell.
- [ ] **Step 4:** Tear down; confirm real DB sha256 unchanged (byte-identical).

### Task 16: Final review + ship

- [ ] **Step 1:** Dispatch the holistic reviewer (superpowers:code-reviewer) over the whole branch diff vs the spec.
- [ ] **Step 2:** Fix any blocking findings.
- [ ] **Step 3:** Clean up `.tmp_ocr_refine/` (delete throwaway scripts; logic now lives in `eval/pagination_count/`).
- [ ] **Step 4:** Push `po_overhaul`; tag `ocr-pagination-mvp`. Write memory `project_ocr_pagination_shipped`.

---

## Test design notes (for the implementer)

- **Pure functions** (`parse_pagination`/`extract_code`/`dominant_total`/`recover_sequence`/`count_starts`) carry the logic — test them exhaustively with synthetic strings/sequences (OCR noise, gaps, orphans, dominant-total outliers). No PDF needed.
- **OCR orchestration** — test with the synthetic `make_pagination_pdf` (clean, deterministic, no personal data, both orientations). Do NOT depend on the real corpus or commit slices of it.
- **Recovery correctness** is the highest-risk logic: a recovered read must never *invent* a `curr==1` between two valid reads of the same cycle (forward fill from the left neighbor guarantees this).
- **No regression:** the migration only flips `scan_strategy`; un-migrated siglas, free cells, and the single-user path are untouched. The `count_ocr`/`ScanResult` contract is unchanged, so no frontend change beyond the additive chip.
- **DB mocking:** none — use real fixtures (synthetic PDFs) per project convention.

## Risks & rollback
- Any migrated sigla that regresses in the live smoke (Task 15) → revert that one sigla's `scan_strategy` to `"anchors"` (one line) and re-bump version. The rest stay migrated.
- If lite recovery proves insufficient for a sigla in eval (Task 9), enable the V4 fallback (D10) for that sigla's low-confidence files — that adds back the `count_documents_v4` import (resolving the F401 then) behind an actual call.
- IRL recovered-cover limitation (Task 4): mitigated by forcing LOW confidence when `cover_code` is set and recovery occurred; the eval (Task 9) quantifies the real miss rate before IRL is migrated.
