# Conteo Confiable — Revisión 2 — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-file OCR from the viewer (page-level progress), method tooltips derived from anchors, per-sigla cards (description + page range), and auto-R1 on opening a fresh month — all on a new `per_file_method` foundation so each file's chip reflects how *that file* was counted.

**Architecture:** A transversal `per_file_method` map (written wherever `per_file` is written; read by `_origin_for`) precedes everything. Then three small independent features (#5 scan-info, #6 sigla cards, R1-auto), then the big one (#1: a single-file OCR endpoint + `file_*` WS events + a per-page progress bar + a merge that touches only the scanned file).

**Tech Stack:** Python 3.10+ / FastAPI / PyMuPDF (fitz) / pytest · React + Vite / Zustand / Tailwind `po-*` tokens / pdfjs-dist / vitest.

**Spec:** `docs/superpowers/specs/2026-06-03-conteo-confiable-rev2-design.md`

---

## ⚠️ Testing cadence (Daniel's standing preference)

**Write each task's test alongside its code and COMMIT per task, but DEFER all test
EXECUTION to the final chunk (Chunk 6).** Run the full `pytest` + `vitest` + `build`
once, together — do NOT run tests per-task and do NOT gate per-chunk.

- Ruff runs automatically on each `.py` write (PostToolUse hook) — not a test run.
- **Worktree caveat:** ~12 VLM/pdf_render/eval tests fail with `FileNotFoundError`
  (gitignored `data/samples/*.pdf` absent in the worktree) — NOT a regression; ignore
  those at the final run.
- Co-Authored-By trailer verbatim: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## Pre-flight

Worktree `.worktrees/conteo-confiable` (branch `feature/conteo-confiable`) already has
the MVP + rev-1 + bug-fix stream + this spec. Smoke servers may be live (backend :8000
isolated DB `_smoke/smoke.db`, Vite :5173, Chrome :9222) — reuse for the Chunk-6 smoke.
**Verify every `file:line` anchor before editing; re-pin if drifted.**

## File-structure map

**Backend**
- `api/state.py` — `per_file_method` writes in `apply_filename_result` (~153) + `apply_ocr_result` (~189); new `apply_per_file_ocr_result`.
- `api/routes/sessions.py` — `get_cell_files` reads `per_file_method`; `_origin_for` resolves per-file method; new single-file scan endpoint.
- `api/routes/siglas.py` (new) — `GET /api/siglas/{sigla}/scan-info`.
- `core/scanners/scan_info.py` (new) — `scan_info_for(sigla)`.
- `core/scanners/utils/header_band_anchors.py` — `count_covers_by_anchors` gains `on_page` (~128/170).
- `core/scanners/anchors_scanner.py` (~42) / `pagination_scanner.py` (~57) — `count_ocr` gains `only` + propagates `on_page`.
- `core/orchestrator.py` — `scan_one_file_ocr` + `file_*` events.
- `tools/audit_sigla_page_ranges.py` (new, one-off).

**Frontend**
- `src/lib/api.js` — `getScanInfo`, `scanFileOcr`.
- `src/lib/method-info.js` — sigla-aware tooltip compositor.
- `src/lib/sigla-info.js` (new) — `SIGLA_DESCRIPTION` + `SIGLA_PAGE_RANGE`.
- `src/store/session.js` — `fileScan` + `file_*` WS handlers; `openMonth` R1-auto.
- `src/components/DetailPanel.jsx` — sigla card (#6) + tooltip source (#5).
- `src/components/PDFLightbox.jsx` — single-file scan button + per-page bar.
- `src/components/FileViewerProgress.jsx` (new) — `página X de N` bar.
- Tests: `scan-info` parity, `method-info` text, `sigla-info` completeness, store R1-auto.

---

## Chunk 1: `per_file_method` foundation

### Task 1.1: Backend — write `per_file_method` in both cell-run setters

**Files:**
- Modify: `api/state.py` (`apply_filename_result` ~145-153, `apply_ocr_result` ~182-189)
- Test: `tests/unit/api/test_state.py`

- [ ] **Step 1: Write the test** (append to `test_state.py`):
```python
def test_apply_results_write_per_file_method(manager):
    """Every cell run records how each file was counted (rev-2 §3)."""
    from core.scanners.base import ConfidenceLevel, ScanResult

    fr = ScanResult(count=2, confidence=ConfidenceLevel.HIGH, method="filename_glob",
                    breakdown={}, flags=[], errors=[], files_scanned=2, duration_ms=1,
                    per_file={"a.pdf": 1, "b.pdf": 1})
    manager.apply_filename_result("2026-04", "HRB", "odi", fr)
    cell = manager.get_session_state("2026-04")["cells"]["HRB"]["odi"]
    assert cell["per_file_method"] == {"a.pdf": "filename_glob", "b.pdf": "filename_glob"}

    orr = ScanResult(count=3, confidence=ConfidenceLevel.HIGH, method="header_band_anchors",
                     breakdown={}, flags=[], errors=[], files_scanned=2, duration_ms=1,
                     per_file={"a.pdf": 3, "b.pdf": 0})
    manager.apply_ocr_result("2026-04", "HRB", "odi", orr)
    cell = manager.get_session_state("2026-04")["cells"]["HRB"]["odi"]
    assert cell["per_file_method"] == {"a.pdf": "header_band_anchors", "b.pdf": "header_band_anchors"}
```

- [ ] **Step 2 (deferred run):** would FAIL (`per_file_method` absent).

- [ ] **Step 3: Implement.** In `apply_filename_result`, right after `cell["per_file"] = result.per_file`:
```python
        cell["per_file_method"] = {f: result.method for f in (result.per_file or {})}
```
In `apply_ocr_result`, right after `cell["per_file"] = result.per_file`:
```python
        cell["per_file_method"] = {f: result.method for f in (result.per_file or {})}
```
Add `cell.setdefault("per_file_method", {})` to the `setdefault` blocks of BOTH (so a cell that never scanned still has the key).

- [ ] **Step 4: Commit**
```bash
git add api/state.py tests/unit/api/test_state.py
git commit -m "feat(state): record per_file_method on every cell run" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 1.2: Backend — `_origin_for` resolves the per-file method

**Files:**
- Modify: `api/routes/sessions.py` (`get_cell_files`: extract `per_file_method` ~435; `_origin_for` ~441-473)
- Test: `tests/test_cell_files_endpoint.py`

- [ ] **Step 1: Write the test** (append): a cell with `per_file_method={"a.pdf":"header_band_anchors","b.pdf":"filename_glob"}`, `cell.method="filename_glob"`, both real multipage PDFs, `per_file={"a.pdf":3,"b.pdf":1}` → `a.pdf` origin `OCR`, `b.pdf` origin `Pendiente` (multipage filename_glob). Seed via `apply_ocr_result` then overwrite one file's method by a follow-up `apply_per_file_ocr_result`? Simpler: seed the cell state directly is not the pattern — instead seed with `apply_filename_result` (both `filename_glob`), then `apply_per_file_ocr_result` on `a.pdf` (Task 5.3 exists later). **Ordering note:** this test depends on Task 5.3's `apply_per_file_ocr_result`. To keep Chunk 1 self-contained, test the *fallback + mixed* purely via `apply_ocr_result` mixed counts instead:
```python
def test_origin_uses_per_file_method(client_with_pdfs_mixed):
    # cell OCR-scanned: per_file_method all header_band_anchors; bad.pdf count 0
    ...
    assert rows["good.pdf"]["origin"] == "OCR"
    assert rows["bad.pdf"]["origin"] == "Revisar"
```
(The genuine *mixed-method* case — one file OCR, another R1 in the same cell — is exercised by Task 5.3's test, which is where mixed state first becomes reachable.)

- [ ] **Step 2 (deferred run).**

- [ ] **Step 3: Implement.** In `get_cell_files`, alongside `per_file = cell.get("per_file") or {}`:
```python
    per_file_method = cell.get("per_file_method") or {}
```
Inside `_origin_for`, resolve the method first and use it in every branch:
```python
        method = per_file_method.get(filename) or cell_method
        if override is not None:
            return "Manual"
        if page_count == 0:
            return "Error"
        if method in ("header_detect", "corner_count", "header_band_anchors", "v4"):
            return "Revisar" if per_file_count == 0 else "OCR"
        if method == "page_count_pure":
            return "R1"
        if method == "filename_glob":
            return "R1" if page_count == 1 else "Pendiente"
        return "R1"
```
(`_origin_for` reads `per_file_method` by closure; signature/call site unchanged.)

- [ ] **Step 4: Commit** `feat(api): per-file chip resolves per_file_method (fallback cell.method)`.

---

## Chunk 2: #5 — Method tooltip from anchors

### Task 2.1: Backend — `scan_info_for` + endpoint

**Files:**
- Create: `core/scanners/scan_info.py`, `api/routes/siglas.py`
- Modify: `api/main.py` (include the new router with prefix `/api`)
- Test: `tests/unit/scanners/test_scan_info.py` (new)

- [ ] **Step 1: Write the test**:
```python
from core.scanners.scan_info import scan_info_for

def test_scan_info_anchors_pagination_none():
    odi = scan_info_for("odi")
    assert odi["kind"] == "anchors"
    assert len(odi["looks_for"]) >= 1 and len(odi["looks_for"]) <= 3
    assert "pagina 1 de" not in odi["looks_for"]  # pagination anchor skipped
    assert scan_info_for("insgral")["kind"] == "pagination"
    assert scan_info_for("reunion")["kind"] == "none"
```

- [ ] **Step 2 (deferred run).**

- [ ] **Step 3: Implement `scan_info.py`** — read `PATTERNS[sigla]`:
```python
from core.scanners.patterns import PATTERNS

_PAGINATION_ANCHORS = ("pagina 1 de", "pagina n de")

def scan_info_for(sigla: str) -> dict:
    """What the pase-2 scanner looks for, per sigla (rev-2 §5). Derived from
    patterns.py — never hand-authored."""
    pat = PATTERNS.get(sigla)
    strat = pat.get("scan_strategy") if pat else "none"
    if strat == "anchors":
        seen, looks_for = set(), []
        for flavor in pat.get("cover_flavors", []):
            for a in flavor.get("anchors", []):
                al = a.lower()
                if al in seen or any(al.startswith(p) for p in _PAGINATION_ANCHORS):
                    continue
                seen.add(al)
                looks_for.append(a)
                if len(looks_for) == 3:
                    break
            if len(looks_for) == 3:
                break
        return {"sigla": sigla, "kind": "anchors", "looks_for": looks_for}
    return {"sigla": sigla, "kind": strat}  # "pagination" | "none"
```
Implement `siglas.py` (`GET /siglas/{sigla}/scan-info` → `scan_info_for(sigla)`; 400 if sigla unknown — validate against `SIGLAS`). Register router in `api/main.py` with `prefix="/api"`.

- [ ] **Step 4: Commit** `feat(api): scan-info endpoint deriving per-sigla OCR anchors`.

### Task 2.2: Frontend — sigla-aware tooltip compositor

**Files:**
- Modify: `src/lib/api.js` (`getScanInfo`), `src/lib/method-info.js`, `src/components/DetailPanel.jsx` (Método row tooltip ~219-233)
- Test: `src/lib/method-info.test.js`

- [ ] **Step 1: Update the test** — `composeMethodInfo(method, scanInfo)`:
```js
import { composeMethodInfo } from "./method-info";
it("composes anchor-based OCR info", () => {
  const t = composeMethodInfo("header_band_anchors",
    { kind: "anchors", looks_for: ["antecedentes generales", "tipo de inducción"] });
  expect(t).toMatch(/Busca:/);
  expect(t).toMatch(/antecedentes generales/);
});
it("falls back per method without scan-info", () => {
  expect(composeMethodInfo("filename_glob", null)).toMatch(/un archivo/i);
});
```

- [ ] **Step 2: `api.js`** — `getScanInfo: (sigla) => fetch(\`${BASE}/siglas/${sigla}/scan-info\`).then(jsonOrThrow)`.

- [ ] **Step 3: `method-info.js`** — add `composeMethodInfo(method, scanInfo)`:
```js
const FALLBACK = {
  filename_glob: "Un documento por archivo PDF.",
  page_count_pure: "Un documento por página.",
  manual: "Valor ingresado a mano por el operador.",
};
export function composeMethodInfo(method, scanInfo) {
  if (scanInfo?.kind === "anchors" && scanInfo.looks_for?.length) {
    return `OCR de encabezado. Busca: ${scanInfo.looks_for.join(" · ")}.`;
  }
  if (scanInfo?.kind === "pagination" || method === "v4") {
    return "Cuenta documentos por la numeración 'Página N de M'.";
  }
  return FALLBACK[method] ?? "Conteo por nombre de archivo.";
}
```
(Keep `METHOD_INFO` for any caller that still wants the static map; new code uses `composeMethodInfo`.)

- [ ] **Step 4: `DetailPanel.jsx`** — fetch `scan-info` for the selected sigla (a small `useEffect` keyed on `sigla`, cached in component state, tolerate failure → null); the Método (i) Tooltip content becomes `composeMethodInfo(cell?.method, scanInfo)`.

- [ ] **Step 5: Commit** `feat(frontend): method (i) tooltip shows what the sigla's OCR looks for`.

---

## Chunk 3: #6 — Per-sigla cards (description + page range)

### Task 3.1: One-off corpus page-range audit

**Files:** Create `tools/audit_sigla_page_ranges.py`

- [ ] **Step 1: Implement the script** — walk `INFORME_MENSUAL_ROOT` (every month × hospital), resolve each sigla's folder via the same enumeration the app uses (`enumerate_cell_pdfs` + `_find_category_folder`/`count_pdfs_by_sigla`), open each PDF (`fitz`) for its page count, and print `{sigla: {p25, median, p75, min, max, n}}` as JSON. CLI tool → `print()` is allowed here. No test (one-off, excluded from the suite).
- [ ] **Step 2: Run it** (`python tools/audit_sigla_page_ranges.py`) and capture the numbers for Task 3.2's `SIGLA_PAGE_RANGE`. (If the corpus is huge, sample a couple of months — the p25–p75 band is robust.)
- [ ] **Step 3: Commit** `feat(tools): one-off audit of per-sigla page-count ranges`.

### Task 3.2: Frontend — `sigla-info.js` + DetailPanel card

**Files:**
- Create: `src/lib/sigla-info.js`, `src/lib/sigla-info.test.js`
- Modify: `src/components/DetailPanel.jsx` (insert card between the big count and "Conteo automático" ~ after the count block)

- [ ] **Step 1: Write the test** — completeness over the 18 siglas:
```js
import { SIGLAS } from "./sigla-labels";
import { SIGLA_DESCRIPTION, SIGLA_PAGE_RANGE, formatPageRange } from "./sigla-info";
it("covers all 18 siglas", () => {
  for (const s of SIGLAS) {
    expect(typeof SIGLA_DESCRIPTION[s]).toBe("string");
    expect(SIGLA_PAGE_RANGE[s]).toBeTruthy();
  }
});
it("formats a range and a single value", () => {
  expect(formatPageRange({ p25: 4, p75: 6 })).toBe("Suele tener 4–6 páginas por documento.");
  expect(formatPageRange({ p25: 1, p75: 1 })).toBe("Normalmente 1 página.");
});
```

- [ ] **Step 2: `sigla-info.js`** — `SIGLA_DESCRIPTION` = the 18 descriptions from spec §6.2 (verbatim, incl. chps = "Acta del Comité Paritario de Higiene y Seguridad."); `SIGLA_PAGE_RANGE` = the audited numbers from Task 3.1; `formatPageRange({p25,p75})` per spec §6.3 microcopy.

- [ ] **Step 3: `DetailPanel.jsx`** — render the card (description lines + `formatPageRange(SIGLA_PAGE_RANGE[sigla])`) between the big count and the "Conteo automático" `<h4>`. Use `po-*` text tokens; keep it compact.

- [ ] **Step 4: Commit** `feat(frontend): per-sigla card with description + typical page range`.

---

## Chunk 4: R1-auto on opening a fresh month

### Task 4.1: `openMonth` auto-runs pase 1 when the session is empty

**Files:**
- Modify: `src/store/session.js` (`openMonth` ~55-67)
- Test: `src/store/session.autoscan.test.js` (new) or extend an existing store test

- [ ] **Step 1: Write the test** — mock `api.createSession`/`getSession`/`scanSession`; `openMonth` with `getSession` returning `cells:{}` calls `scanSession`; with non-empty `cells`, does NOT. (Mirror how other store tests stub `api`.)

- [ ] **Step 2: Implement.** In `openMonth`, after `const session = await api.getSession(sessionId)` and the `set({...})`:
```js
      if (Object.keys(session.cells || {}).length === 0) {
        get().runScan(sessionId);  // pase 1 only the first time (spec §7)
      }
```
(Use `get()` to reach `runScan`; do not await — let the existing `loading`/progress UI cover it.)

- [ ] **Step 3: Commit** `feat(store): auto-run pase 1 when opening a month with no scanned data`.

---

## Chunk 5: #1 — Per-file OCR from the viewer

### Task 5.1: Backend — per-page hook + single-file scope in the scanners

**Files:**
- Modify: `core/scanners/utils/header_band_anchors.py` (`count_covers_by_anchors` ~128, loop ~170), `core/scanners/anchors_scanner.py` (`count_ocr` ~42, `pdfs = enumerate_cell_pdfs` ~81), `core/scanners/pagination_scanner.py` (~57, ~99)
- Test: `tests/unit/scanners/test_anchors_scanner.py` (extend)

- [ ] **Step 1: Write the test** — `AnchorsScanner(sigla="odi").count_ocr(folder, cancel=..., only="a.pdf", on_page=cb)` over a folder with `a.pdf`+`b.pdf` (monkeypatch `get_page_count`→2 to force the OCR path, monkeypatch the per-page OCR to return no covers): only `a.pdf` is processed (`per_file == {"a.pdf": 0}`), and `on_page` was called with `(0, 2)` and `(1, 2)`.

- [ ] **Step 2 (deferred run).**

- [ ] **Step 3: Implement.**
  - `count_covers_by_anchors(...)` gains `on_page: Callable[[int, int], None] | None = None`; call `on_page(page_idx, pages_total)` at the top of the page loop (~170).
  - `AnchorsScanner.count_ocr(self, folder, *, cancel, on_pdf=None, only=None, on_page=None)`: after `pdfs = enumerate_cell_pdfs(folder)`, if `only is not None`: `pdfs = [p for p in pdfs if p.name == only]`. Pass `on_page` through to `count_covers_by_anchors`.
  - `PaginationScanner.count_ocr`: same `only` filter. `on_page`: per spec §4.2, **do not** wire it through V4 this round — accept the kwarg and ignore it (the viewer bar is indeterminate for insgral/altura).

- [ ] **Step 4: Commit** `feat(scanners): single-file scope (only=) + per-page on_page hook`.

### Task 5.2: Backend — `scan_one_file_ocr` orchestrator path + `file_*` events

**Files:**
- Modify: `core/orchestrator.py`
- Test: `tests/unit/test_orchestrator_ocr_progress.py` (extend)

- [ ] **Step 1: Write the test** — `scan_one_file_ocr("HPV", "odi", folder, "a.pdf", on_progress=events.append, cancel=...)` (1-page A7 PDFs, monkeypatch `get_page_count`→1): events include `file_scan_started` (with `pages_total`), at least one `file_page_progress` (page/pages_total), and a terminal `file_scan_done` whose `result.per_file == {"a.pdf": 1}` and `result.method` set.

- [ ] **Step 2 (deferred run).**

- [ ] **Step 3: Implement `scan_one_file_ocr(hospital, sigla, folder, filename, *, on_progress, cancel)`** — look up the scanner from the registry (mirror `_ocr_worker`), emit `file_scan_started {hospital, sigla, filename, pages_total}` (pages from `get_page_count`), run `scanner.count_ocr(folder, cancel=cancel, only=filename, on_page=lambda i, n: on_progress({"type":"file_page_progress","hospital":hospital,"sigla":sigla,"filename":filename,"page":i+1,"pages_total":n}))`, then emit `file_scan_done {hospital, sigla, filename, result:{ocr_count, method, per_file, near_matches}}` (serialise near_matches like `cell_done` does). On exception → `file_scan_error {hospital, sigla, filename, error}`.

- [ ] **Step 4: Commit** `feat(orchestrator): scan_one_file_ocr with file_* progress events`.

### Task 5.3: Backend — merge method + single-file endpoint

**Files:**
- Modify: `api/state.py` (new `apply_per_file_ocr_result`), `api/routes/sessions.py` (new endpoint + reuse `_find_category_folder`)
- Test: `tests/test_cell_files_endpoint.py` + `tests/unit/api/test_state.py`

- [ ] **Step 1: Write the tests.**
  - State: seed cell via `apply_ocr_result` `per_file={"a.pdf":3,"b.pdf":2}`; `apply_per_file_ocr_result(..., "a.pdf", count=5, method="header_band_anchors", near_matches=[])` → `per_file=={"a.pdf":5,"b.pdf":2}` (b untouched), `per_file_method["a.pdf"]=="header_band_anchors"`, `b` intact.
  - Endpoint: `POST .../cells/HRB/odi/files/a.pdf/scan-ocr` returns 202/200 for an existing file; `.../files/missing.pdf/scan-ocr` → 404.

- [ ] **Step 2 (deferred run).**

- [ ] **Step 3: Implement.**
  - `apply_per_file_ocr_result(self, session_id, hospital, sigla, filename, *, count, method, near_matches)`: `cell.setdefault("per_file", {})[filename] = count`; `cell.setdefault("per_file_method", {})[filename] = method`; replace near_matches for that `pdf_name` (`others = [nm for nm in cell.get("near_matches", []) if nm["pdf_name"] != filename]; cell["near_matches"] = others + near_matches`); persist.
  - Endpoint `POST /sessions/{id}/cells/{h}/{s}/files/{filename}/scan-ocr`: validate `session_id`; resolve `folder = _find_category_folder(Path(state["month_root"]) / hospital, sigla)`; 404 if `filename not in {p.name for p in folder.rglob("*.pdf")}`. Launch `scan_one_file_ocr` in the executor with an `on_progress` that (a) broadcasts each `file_*` event over the session WS, and (b) on `file_scan_done` calls `mgr.apply_per_file_ocr_result(...)` (mirror the batch `on_progress` cell_done handler at sessions.py ~204-237). Return `{"accepted": True, "filename": filename, "pages_total": ...}`.

- [ ] **Step 4: Commit** `feat(api): single-file OCR endpoint + per-file merge`.

### Task 5.4: Frontend — `fileScan` store state + `file_*` handlers + api

**Files:**
- Modify: `src/lib/api.js` (`scanFileOcr`), `src/store/session.js` (state + WS handlers)
- Test: none new (store wiring; covered by smoke) — optional store unit test for the reducer

- [ ] **Step 1: `api.js`** — `scanFileOcr: (sessionId, hospital, sigla, filename) => fetch(\`${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/files/${encodeURIComponent(filename)}/scan-ocr\`, { method: "POST" }).then(jsonOrThrow)`.

- [ ] **Step 2: `session.js`** — add `fileScan: null` to initial state. WS handlers:
  - `file_scan_started` → `set({ fileScan: { hospital, sigla, filename, page: 0, pagesTotal: event.pages_total, terminal: null } })`.
  - `file_page_progress` → `set((s) => s.fileScan ? { fileScan: { ...s.fileScan, page: event.page, pagesTotal: event.pages_total } } : {})`.
  - `file_scan_done` → bump `filesTick` for `${event.hospital}|${event.sigla}` (mirror `cell_done`) + `set({ fileScan: { ...prev, terminal: "done" } })`; clear `fileScan` after a short timeout.
  - `file_scan_error` → `set` terminal "error"; clear after timeout.

- [ ] **Step 3: Commit** `feat(store): fileScan progress + file_* WS handlers, refresh on done`.

### Task 5.5: Frontend — single-file button + per-page bar in the viewer

**Files:**
- Create: `src/components/FileViewerProgress.jsx`
- Modify: `src/components/PDFLightbox.jsx` (the inspect-branch OCR button + `useSessionStore` for `fileScan`/`scanFileOcr`)
- Test: none new (smoke)

- [ ] **Step 1: `FileViewerProgress.jsx`** — given `{ page, pagesTotal }`, render a compact bar `página {page} de {pagesTotal}` (reuse the `ScanProgress` visual language); if `pagesTotal` unknown (pagination siglas) show an indeterminate bar.

- [ ] **Step 2: `PDFLightbox.jsx`** — the existing "Escanear con OCR" button now calls `scanFileOcr(session.session_id, lightbox.hospital, lightbox.sigla, files[lightbox.fileIndex].name)` (the CURRENT file), not the whole cell. While `fileScan?.filename === currentFile.name && !fileScan.terminal`, render `<FileViewerProgress .../>` and disable the button. Disable + tooltip "Esta categoría no usa OCR" when the sigla's strategy is `none` (derive from a tiny `scan-info` check or the cell method; simplest: disable when `scanInfo?.kind === "none"`). On `file_scan_done`, Task 5.4's tick already refreshes the file row.

- [ ] **Step 3: Commit** `feat(frontend): scan the current file with OCR from the viewer, page-level bar`.

---

## Chunk 6: Verification (END — all tests together)

### Task 6.1: Full suite + build
- [ ] `ruff check .` (worktree) → 0.
- [ ] `pytest -q` (worktree, venv python) → only the ~12 known `FileNotFoundError` env failures; everything else green. New failure → fix (superpowers:systematic-debugging), commit.
- [ ] `cd frontend && npx vitest run` → green; `npm run build` → OK.

### Task 6.2: Live smoke (chrome-devtools, ABRIL, isolated DB)
- [ ] Reuse/restart backend(:8000 isolated DB) + Vite(:5173) + Chrome(:9222).
- [ ] Drive and verify:
  - **per_file_method/chips:** a mixed cell (one file OCR-ed individually, others by name) shows OCR/Revisar on the scanned file, R1/Pendiente on the rest.
  - **#1:** open a multipage file in the viewer → "Escanear con OCR" runs ONLY that file, page-level bar advances, on completion the file's chip + count update (and the cell total via computeCellCount); the outside cell-scan button still scans the whole cell; a `none` sigla (reunion) disables the viewer button.
  - **#5:** the (i) on Método shows "Busca: …" with the sigla's anchors; pagination sigla shows the "Página N de M" text.
  - **#6:** the sigla card shows the description + "Suele tener X–Y páginas".
  - **R1-auto:** open a never-scanned month → pase 1 runs automatically; re-open a scanned month → no auto-scan.
- [ ] Fix any smoke bugs (commit per fix). Screenshots → `docs/research/`.

### Task 6.3: Tag
- [ ] `git tag -a conteo-confiable-rev-2 -m "Conteo confiable — revisión 2 (per-file OCR, method tooltips, sigla cards, R1-auto)"`. Local. Confirm with Daniel.

---

## Out of scope (YAGNI)
- Multiusuario / presencia / bloqueo de celda (separate future plan — spec §11).
- #7 live per-PDF chip during a full-cell scan.
- Wiring V4 (insgral/altura) per-page progress (indeterminate bar instead).
- Renaming the `chps` sigla token (cross-project; deferred).

## Notes
- Verify every `file:line` anchor against the tree before editing; re-pin if drifted.
- Order: per_file_method → #5 → #6 → R1-auto → #1 → Chunk 6.
