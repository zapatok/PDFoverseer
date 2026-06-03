# Conteo Confiable + Organización + Revisión — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the automatic count honest (green = verified, amber = unverified), count fixed-page siglas by pages, list the 18 categories in folder order, scan only pending cells, and turn the per-file viewer into a per-file editor.

**Architecture:** One surgical change to the pase-1 scanner sets `confidence` from a real verification rule (all-files-1-page, fixed-page sigla, or none) and counts fixed-page siglas by pages via `per_file`. A new `confirmed` cell flag + endpoint covers manual "mark ready". The frontend drops the Normalizadas/Compilaciones grouping (single 1-18 list), redefines the dot to listo/pendiente, adds two bulk actions, fixes the FileList grid, and makes the lightbox panel per-file.

**Tech Stack:** Python 3.10+ / FastAPI / PyMuPDF (fitz) / pytest · React + Vite / Zustand / Tailwind `po-*` tokens / vitest.

**Spec:** `docs/superpowers/specs/2026-06-02-conteo-confiable-y-revision-design.md`

---

## ⚠️ Pre-requisite: consolidate first (decision D1)

This plan executes on a **consolidated `po_overhaul`**. Before Task 1:
1. Daniel runs the manual smoke of PR #1 (`feature/ocr-per-sigla`).
2. Merge `feature/ocr-per-sigla` → `po_overhaul`.
3. Merge `feature/worker-viewer-ux` → `po_overhaul`.
4. Create the worktree (superpowers:using-git-worktrees): `.worktrees/conteo-confiable` → `feature/conteo-confiable` off the consolidated `po_overhaul`.
5. **Verify every `file:line` anchor below against the consolidated tree before editing** (the anchors were pinned against `feature/ocr-per-sigla`, which is the bulk of the consolidated base; only `FileList.jsx` differs from raw po_overhaul). Re-pin if shifted.

## File structure

**Backend — create/modify:**
- `core/utils.py` — add `FIXED_PAGE_SIGLAS`, `FIXED_PAGE_SIGLAS_INFERRED`; bump `SCANNER_PATTERNS_VERSION`.
- `core/scanners/simple_factory.py` — rewrite `SimpleFilenameScanner.count` (the confidence/count rule).
- `tests/scanners/test_simple_factory_confidence.py` — new pytest.
- `api/state.py` — `confirmed` cell field (init + preserve) + `apply_confirmed`.
- `api/routes/sessions.py` — `PATCH …/confirm` endpoint; `_origin_for` "Estructura".
- `tests/api/test_confirm_endpoint.py` — new pytest.

**Frontend — modify:**
- `frontend/src/components/OriginChip.jsx` — "Estructura" variant.
- `frontend/src/components/CategoryRow.jsx` + `frontend/src/components/HospitalCard.jsx` — `dotVariantFor` → listo/pendiente.
- `frontend/src/views/HospitalDetail.jsx` — single 1-18 list, bulk actions.
- `frontend/src/components/ScanControls.jsx` (or a new `CategoryBulkActions.jsx`) — "Escanear pendientes" + "Marcar seleccionadas como listas".
- `frontend/src/store/session.js` — `confirmCell` action; `scanPending` helper.
- `frontend/src/components/FileList.jsx` — grid + name scroll.
- `frontend/src/components/PDFLightbox.jsx` — per-file panel + white numbers.
- `frontend/src/lib/*.test.js` — vitest where logic is extractable.

---

## Chunk 1: Tema A backend — honest count + fixed-page + confirmed

### Task 1: Pase-1 confidence/count rule + FIXED_PAGE_SIGLAS

**Files:**
- Modify: `core/utils.py` (add constants near other scanner constants; bump `SCANNER_PATTERNS_VERSION`)
- Modify: `core/scanners/simple_factory.py:25-56` (`SimpleFilenameScanner.count`)
- Create: `tests/scanners/test_simple_factory_confidence.py`

- [ ] **Step 1: Add constants to `core/utils.py`**
```python
# Siglas whose every document is a fixed number of pages → count = total pages.
# Source: corpus audit 2026-05-11 + OCR per-sigla spec §9/§11/§13/§15/§16 +
# calibration Fase A/B. All divisor 1 (1 page = 1 document).
FIXED_PAGE_SIGLAS: dict[str, int] = {
    "bodega": 1,            # documented + Fase A confirmed
    "ext": 1,              # documented + Fase A confirmed (canonical LCH-18/37)
    "caliente": 1,         # inferred (Fase B: 20 pages → 20 covers)
    "herramientas_elec": 1,  # inferred (Fase B: 38 covers / 40 pages)
    "exc": 1,             # inferred (Fase A: 2 covers / 2 pages, small sample)
}
# Subset whose page-per-doc is inferred (less evidence) → UI "verificar" hint.
FIXED_PAGE_SIGLAS_INFERRED: frozenset[str] = frozenset(
    {"caliente", "herramientas_elec", "exc"}
)
```
Bump `SCANNER_PATTERNS_VERSION` (string in `core/utils.py`).

- [ ] **Step 2: Write the failing test**

`tests/scanners/test_simple_factory_confidence.py`:
```python
"""Pase-1 confidence/count rule (2026-06-02 conteo-confiable spec, Tema A1)."""
from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
import pytest

from core.scanners.base import ConfidenceLevel
from core.scanners.simple_factory import make_simple_scanner


def _pdf(path: Path, pages: int) -> None:
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    doc.save(path)
    doc.close()


def _folder(tmp_path: Path, sigla: str, files: dict[str, int]) -> Path:
    """Create <tmp>/<sigla>/ with canonical filenames of the given page counts."""
    folder = tmp_path / sigla
    folder.mkdir()
    for name, pages in files.items():
        _pdf(folder / name, pages)
    return folder


def test_fixed_page_sigla_counts_pages_high(tmp_path: Path):
    # bodega: each page is a chequeo → count = sum of pages.
    folder = _folder(tmp_path, "bodega", {
        "2026-04-01_bodega_a.pdf": 1,
        "2026-04-02_bodega_b.pdf": 4,
    })
    r = make_simple_scanner("bodega").count(folder)
    assert r.count == 5
    assert r.per_file == {"2026-04-01_bodega_a.pdf": 1, "2026-04-02_bodega_b.pdf": 4}
    assert r.method == "page_count_pure"
    assert r.confidence == ConfidenceLevel.HIGH
    assert "fixed_pages_inferred" not in r.flags  # bodega is solid


def test_inferred_fixed_page_sigla_flags_verificar(tmp_path: Path):
    folder = _folder(tmp_path, "exc", {"2026-04-01_exc_a.pdf": 2})
    r = make_simple_scanner("exc").count(folder)
    assert r.count == 2
    assert "fixed_pages_inferred" in r.flags
    assert r.confidence == ConfidenceLevel.HIGH


def test_normal_sigla_all_one_page_high(tmp_path: Path):
    # charla, all single-page files → trivially 1 doc each → HIGH.
    folder = _folder(tmp_path, "charla", {
        "2026-04-01_charla_a.pdf": 1,
        "2026-04-02_charla_b.pdf": 1,
    })
    r = make_simple_scanner("charla").count(folder)
    assert r.count == 2
    assert r.per_file == {"2026-04-01_charla_a.pdf": 1, "2026-04-02_charla_b.pdf": 1}
    assert r.confidence == ConfidenceLevel.HIGH
    assert r.method == "filename_glob"


def test_normal_sigla_with_multipage_low(tmp_path: Path):
    # A multi-page file of a variable sigla → unverified → LOW (amber).
    folder = _folder(tmp_path, "charla", {
        "2026-04-01_charla_a.pdf": 1,
        "2026-04-02_charla_b.pdf": 28,
    })
    r = make_simple_scanner("charla").count(folder)
    assert r.count == 2          # still file count (1 doc per file, unverified)
    assert r.confidence == ConfidenceLevel.LOW


def test_missing_folder_high_zero(tmp_path: Path):
    r = make_simple_scanner("bodega").count(tmp_path / "nope")
    assert r.count == 0
    assert r.confidence == ConfidenceLevel.HIGH
    assert "folder_missing" in r.flags
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/scanners/test_simple_factory_confidence.py -v`
Expected: FAIL (current scanner returns HIGH for the multipage case, `filename_glob` method for bodega, file-count not page-count).

- [ ] **Step 4: Rewrite `SimpleFilenameScanner.count`**

`core/scanners/simple_factory.py` — replace the body of `count` (keep imports; add `from core.utils import FIXED_PAGE_SIGLAS, FIXED_PAGE_SIGLAS_INFERRED` and reuse `_page_count` from `page_count_heuristic`):
```python
def count(self, folder: Path, *, override_method: str | None = None) -> ScanResult:
    start = time.perf_counter()
    glob_result = count_pdfs_by_sigla(folder, sigla=self.sigla)
    breakdown = per_empresa_breakdown(folder)
    flags = list(glob_result.flags)

    if "folder_missing" in flags:
        return self._result(glob_result, breakdown, flags,
                            count=0, per_file={}, method="filename_glob",
                            confidence=ConfidenceLevel.HIGH, start=start)

    # page counts of the matched files (open each once)
    pages = {fn: _page_count(folder / fn) for fn in glob_result.matched_filenames}
    # NOTE: matched_filenames are basenames; if recursive, resolve via rglob map.

    if self.sigla in FIXED_PAGE_SIGLAS:
        per_file = dict(pages)
        if self.sigla in FIXED_PAGE_SIGLAS_INFERRED:
            flags.append("fixed_pages_inferred")
        return self._result(glob_result, breakdown, flags,
                            count=sum(pages.values()), per_file=per_file,
                            method="page_count_pure",
                            confidence=ConfidenceLevel.HIGH, start=start)

    all_one_page = bool(pages) and all(p == 1 for p in pages.values())
    if flag_compilation_suspect(folder, sigla=self.sigla):
        flags.append("compilation_suspect")
    confidence = ConfidenceLevel.HIGH if all_one_page else ConfidenceLevel.LOW
    return self._result(glob_result, breakdown, flags,
                        count=glob_result.count,
                        per_file={fn: 1 for fn in glob_result.matched_filenames},
                        method="filename_glob", confidence=confidence, start=start)
```
Add a small private `_result(...)` helper **as a method of `SimpleFilenameScanner`** (NOT on `ScanResult` — it's a `@dataclass(frozen=True)`) that builds the `ScanResult` (DRY — avoids repeating the 9 fields three times). **Gotcha:** `matched_filenames` are basenames but files may live in subfolders (recursive glob); resolve the actual path per file (e.g. build a `{basename: full_path}` map from `folder.rglob("*.pdf")` filtered by `extract_sigla`) so `_page_count` opens the right file. Verify against the consolidated `filename_glob.py`.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/scanners/test_simple_factory_confidence.py -v`
Expected: PASS (5 tests). Then `pytest tests/ -q` (no regressions) and `ruff check .` (0).

- [ ] **Step 6: Commit**
```bash
git add core/utils.py core/scanners/simple_factory.py tests/scanners/test_simple_factory_confidence.py
git commit -m "feat(scanners): honest pase-1 confidence + page-count for fixed-page siglas" \
  -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 2: "Estructura" origin chip

**Files:**
- Modify: `api/routes/sessions.py` (`_origin_for`, ~408-425)
- Modify: `frontend/src/components/OriginChip.jsx`
- Modify: `frontend/src/lib/method-labels.js` (confirm `page_count_pure` label exists: "Conteo de páginas")

- [ ] **Step 1:** In `_origin_for`, before the OCR branch, add: if `cell_method == "page_count_pure"` return `"Estructura"`. (So page-count cells don't read as "OCR".)
- [ ] **Step 2:** `OriginChip.jsx` — add `Estructura: "iris"` (or a distinct tone) to `ORIGIN_VARIANT`.
- [ ] **Step 3 (test):** `frontend/src/components/__tests__/OriginChip.test.jsx` (or inline vitest) — renders "Estructura" with its variant; unknown origin → neutral.
- [ ] **Step 4:** Run `npm test -- OriginChip`; `npm run build`.
- [ ] **Step 5: Commit** `feat(frontend): add "Estructura" origin chip for page-count cells`.

### Task 3: `confirmed` cell flag + endpoint + store action

**Files:**
- Modify: `api/state.py` — new `apply_confirmed(session_id, hospital, sigla, confirmed)`; add `cell.setdefault("confirmed", False)` in **both** `apply_filename_result` AND `apply_ocr_result` (both overwrite `per_file` directly, so `confirmed` must be re-asserted via `setdefault` in each) so a re-scan never clears it
- Modify: `api/routes/sessions.py` (new `PATCH /api/sessions/{id}/cells/{h}/{s}/confirm`, mirroring the worker-count endpoint)
- Modify: `frontend/src/store/session.js` (`confirmCell(sessionId, hospital, sigla, confirmed)` → PATCH + optimistic cell update)
- Create: `tests/api/test_confirm_endpoint.py`

- [ ] **Step 1: Write the failing test** — open session, PATCH confirm true → cell `confirmed` true; re-run pase-1 scan → still true (preserved); PATCH false → false. Real fixtures, no DB mock.
- [ ] **Step 2:** Run `pytest tests/api/test_confirm_endpoint.py -v` → FAIL (endpoint missing).
- [ ] **Step 3:** Implement `apply_confirmed` + endpoint (validate session_id regex like the others; 404 if cell missing) + `cell.setdefault("confirmed", False)` in **both `apply_filename_result` and `apply_ocr_result`** so neither a filename re-scan nor an OCR scan clears it.
- [ ] **Step 4:** Run the test → PASS; `pytest tests/ -q`; `ruff check .`.
- [ ] **Step 5:** Add `confirmCell` store action (mirror `saveWorkerCount`/`savePerFileOverride` PATCH pattern in `session.js`).
- [ ] **Step 6: Commit** `feat(sessions): add confirmed cell flag + confirm endpoint`.

- [ ] **Chunk 1 gate:** `pytest tests/ -q` green, `ruff check .` 0. Dispatch plan-review already done; proceed.

---

## Chunk 2: Tema A frontend — list 1-18 + dot + bulk actions

### Task 4: `dotVariantFor` → listo/pendiente (CategoryRow + HospitalCard)

**Files:** `frontend/src/components/CategoryRow.jsx:11-19`, `frontend/src/components/HospitalCard.jsx:11-16`

- [ ] **Step 1:** Extract the rule into a shared helper `frontend/src/lib/cell-status.js`: `isCellReady(cell)` = `cell?.confidence === "high" || cell?.confirmed || hasOverride(cell)`; `dotVariantFor(cell, {isScanning})`.
- [ ] **Step 2 (test):** `frontend/src/lib/cell-status.test.js` — ready when confidence high / confirmed / override; pendiente (amber) when low and none; scanning/error precedence.
- [ ] **Step 3:** Run `npm test -- cell-status` → FAIL → implement → PASS.
- [ ] **Step 4:** Point both `CategoryRow.jsx` and `HospitalCard.jsx` at the shared helper (delete their local copies). Dot: ready → `confidence-high` (green), else `confidence-low` (amber); keep scanning/error. (Per spec A3: override collapses into green; the "Manual" chip still marks it.)
- [ ] **Step 5:** `npm run build`. **Commit** `feat(frontend): redefine cell dot to listo/pendiente`.

### Task 5: single 1-18 list (HospitalDetail)

**Files:** `frontend/src/views/HospitalDetail.jsx:23-101`

- [ ] **Step 1:** Replace `normalized`/`compilations` (lines 23-30) with a single `ordered = mode==="manual" ? SIGLAS : SIGLAS.filter((s) => cells[s])` (keep the manual-mode 18-rows behavior). Render ONE `CategoryGroup` (no title split, no second group). Remove the `showScanAll` group.
- [ ] **Step 2:** Verify the row tooltip can show `CATEGORY_FOLDERS[sigla]` (folder name). (`sigla-labels.js` may already expose labels; add folder name if useful.)
- [ ] **Step 3:** `npm run build`; visual check deferred to smoke. **Commit** `feat(frontend): list categories 1-18 in folder order, drop compilation grouping`.

### Task 6: bulk actions — Escanear pendientes + Marcar listas

**Files:** new `frontend/src/components/CategoryBulkActions.jsx`; `frontend/src/views/HospitalDetail.jsx` (mount it above the list); `frontend/src/store/session.js` (`scanPending`)

- [ ] **Step 1:** `scanPending(sessionId, hospital)` store helper: derive amber siglas (`!isCellReady(cell)`) from state, call `scanOcr` with those pairs (locate the existing >50-PDF cost guard first — it lives in the `scanOcr` store action / `scanCost.js` from the OCR audit — and reuse it, don't duplicate the threshold).
- [ ] **Step 2:** `CategoryBulkActions.jsx`: two `Button`s — "Escanear pendientes" (`scanPending`) and "Marcar seleccionadas como listas" (`confirmCell` for each checked sigla; optimistic). Disabled states (no pendientes / nothing selected).
- [ ] **Step 3:** Mount above the category list in `HospitalDetail`; reconcile with the header `ScanControls` (keep targeted scan or fold in — no behavior change to targeted scan).
- [ ] **Step 4:** `npm run build`. **Commit** `feat(frontend): scan-pending + mark-ready bulk actions`.

- [ ] **Chunk 2 gate:** `npm test` green, `npm run build` OK.

---

## Chunk 3: Tema B (FileList grid) + Tema C (lightbox per-file)

### Task 7: FileList grid + name horizontal scroll

**Files:** `frontend/src/components/FileList.jsx:82-117`

- [ ] **Step 1:** Restructure the row `<li>` to a grid: `grid grid-cols-[auto_minmax(0,1fr)_auto_auto_auto_auto] items-center gap-2`. Columns: FileText icon · name · `Npp` · compilation icon (or empty) · `InlineEditCount` · `OriginChip`/`trivial`.
- [ ] **Step 2:** Name cell: `min-w-0 overflow-x-auto whitespace-nowrap font-mono text-xs` (horizontal scroll appears only when it overflows). Row click (`li onClick`) opens the lightbox; `InlineEditCount` + chip keep `stopPropagation`; `Npp` and the compilation icon are non-interactive (no lightbox open from them per spec B).
- [ ] **Step 3:** `npm run build`; verify alignment in smoke. **Commit** `fix(frontend): align FileList rows in a grid with scrollable filename`.

### Task 8: PDFLightbox per-file panel + white numbers

**Files:** `frontend/src/components/PDFLightbox.jsx:27-54,146-150`

- [ ] **Step 1:** Replace `CountSummary({cell})` with a per-file panel reading `files[lightbox.fileIndex]`: big number = `file.effective_count` (`text-po-text`), "documentos en este archivo", `OriginChip origin={file.origin}`, `{file.page_count}pp`.
- [ ] **Step 2:** Replace the cell `OverridePanel` with a per-file editor: `InlineEditCount` / number input committing `savePerFileOverride(session_id, hospital, sigla, file.name, n)`; after commit, refresh the FileList row (optimistic, FASE-4 pattern). All numbers `text-po-text` (fix the dark contrast).
- [ ] **Step 3:** Leave `mode === "count_workers"` branch untouched. Drop the cell-level Por nombre/OCR/Método/confianza from this panel.
- [ ] **Step 4:** `npm run build`. **Commit** `feat(frontend): per-file count + override in the PDF lightbox, white numbers`.

### Task 9: Live smoke + tag

- [ ] **Step 1:** Start backend + Vite from `.worktrees/conteo-confiable`; Chrome debug :9222.
- [ ] **Step 2:** Drive chrome-devtools — verify: 18-row list in folder order; bodega/ext/exc show page-count totals + green; a multipage charla amber; "Escanear pendientes" targets only amber; "Marcar seleccionadas" → green; FileList aligned + name scroll; lightbox per-file with white numbers + per-file override; a fixed-page compilation's number changed (e.g. bodega 1→N).
- [ ] **Step 3:** Fix bugs (superpowers:systematic-debugging), commit per fix.
- [ ] **Step 4:** `pytest -q && (cd frontend && npm test && npm run build)` all green. Tag `conteo-confiable-mvp` (local).

---

## Out of scope (YAGNI)
Divisors ≠ 1 (odi/art), promoting inferred siglas to solid, cascade/Excel changes, history/manual-mode changes beyond the 18 rows.

## Notes
- **Number changes are expected** for fixed-page compilations (bodega/ext/etc.) — flag in the smoke.
- Anchors pinned vs `feature/ocr-per-sigla`; re-verify against the consolidated tree at execution (pre-req step 5).
- **Latent inconsistency (out of scope):** `HistoryDrawer.jsx`'s `methodToOrigin` maps `page_count_pure` → "OCR", so historical fixed-page cells will read "OCR" (not "Estructura") in the history drawer. History is untouched here; add a `TODO` comment in `HistoryDrawer.jsx` during Task 2 so it surfaces at the next history task.
