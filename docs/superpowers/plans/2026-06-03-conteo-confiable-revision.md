# Conteo Confiable — Revisión post-MVP — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the 14 review fixes on the shipped Conteo-Confiable MVP: honest per-file chips, a paged file viewer (thumbnails + fit + scroll/zoom), OCR-from-the-viewer with post-scan refresh, five small fixes, and a clickable last-Excel on the home.

**Architecture:** Mostly surgical frontend changes plus three small backend touches (`_origin_for` gains `page_count` and a 5-value chip rule; two new `GET` output endpoints). The biggest unit is rebuilding `PDFLightbox`'s inspect viewer on the already-proven `WorkerCountViewer` paging pattern (drop `react-zoom-pan-pinch`). A new `filesTick` store counter drives post-OCR re-fetch.

**Tech Stack:** Python 3.10+ / FastAPI / PyMuPDF (fitz) / pytest · React + Vite / Zustand / Tailwind `po-*` tokens / pdfjs-dist / vitest.

**Spec:** `docs/superpowers/specs/2026-06-03-conteo-confiable-revision-design.md`

---

## ⚠️ Testing cadence (Daniel's standing preference)

**Write each task's test alongside its code and COMMIT per task, but DEFER all test
EXECUTION to the final chunk (Chunk 6).** Run the full `pytest` + `vitest` + `build`
once, together — do NOT run tests per-task and do NOT gate per-chunk. The TDD test
code is included per task so it's captured; just don't execute until the end.

- Ruff still runs automatically on each `.py` write (PostToolUse hook) — that's not a
  test run.
- **Worktree caveat:** the worktree lacks the gitignored `data/samples/*.pdf`, so
  ~12 VLM/pdf_render/eval tests fail with `FileNotFoundError` in the worktree but pass
  in main. That is NOT a regression — ignore those 12 at the final run.
- Co-Authored-By trailer verbatim: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## Pre-flight

The worktree `.worktrees/conteo-confiable` already exists (branch
`feature/conteo-confiable`, HEAD has the MVP + spec commits). The smoke servers may
still be running (backend :8000 isolated DB, Vite :5173, Chrome :9222) — reuse them
for the Chunk-6 smoke. Verify `file:line` anchors below before editing; re-pin if drifted.

## File-structure map

**Backend**
- `api/routes/sessions.py` — `_origin_for` (signature `+page_count`, 5-chip rule, canonical casing).
- `api/routes/output.py` — new `GET /sessions/{id}/output` (serve) + `GET /api/outputs` (list).
- Tests: `tests/test_cell_files_endpoint.py` (extend), `tests/test_output_serve_endpoint.py` (new).

**Frontend**
- `src/components/OriginChip.jsx` — 5 variants, drop `Estructura`.
- `src/ui/Badge.jsx` — keep `blue` (now Manual).
- `src/components/FileList.jsx`, `src/components/PDFLightbox.jsx` — chip render; viewer rework; OCR button; refresh; white input.
- `src/components/HistoryDrawer.jsx` — `methodToOrigin` casing + R1, remove stale TODO.
- `src/components/ScanProgress.jsx` — ETA minutes.
- `src/views/HospitalDetail.jsx` — header copy.
- `src/views/MonthOverview.jsx` — single toast; last-Excel section.
- `src/components/DetailPanel.jsx` — (i) on Método.
- `src/store/session.js` — `filesTick` + increment on `cell_done`/`scan_cancelled`.
- `src/lib/api.js` — `outputUrl`, `listOutputs`.
- New: `src/lib/method-info.js`, `src/lib/viewer-nav.js` (`wheelToPageStep`).
- `src/lib/scanCost.js` — `formatEta`.
- Reuse unchanged: `src/components/WorkerThumbnails.jsx`, `src/hooks/useFitScale.js`, `src/components/PdfPage.jsx`.
- Tests: `OriginChip.test.js`, `scanCost.test.js`, `method-info.test.js`, `viewer-nav.test.js`.

---

## Chunk 1: G1 — Honest per-file chips

### Task 1.1: Backend `_origin_for` — `page_count` + 5-chip rule

**Files:**
- Modify: `api/routes/sessions.py` (`_origin_for` nested in `get_cell_files`, def ~408, body ~415-425; call site ~453)
- Test: `tests/test_cell_files_endpoint.py` (extend)

- [ ] **Step 1: Write the failing test** (append to `tests/test_cell_files_endpoint.py`)

The existing file seeds a session + cell via `mgr.apply_filename_result` and hits
`GET …/cells/{h}/{s}/files`. Mirror that. Note: the endpoint reads the **real folder**
from `month_root`, so the test must point `month_root` at a tmp dir with actual PDFs of
the right page counts (the endpoint opens each PDF for `page_count`). Use `fitz` to
create them, matching the existing endpoint test's fixture style.

```python
def test_origin_chip_rule(tmp_path, monkeypatch):
    """_origin_for returns R1/OCR/Manual/Pendiente/Error per spec G1."""
    import fitz
    from core.scanners.base import ConfidenceLevel, ScanResult

    # Build a real HRB/charla folder with a 1-page and a 28-page PDF.
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "t.db"))
    hosp_dir = tmp_path / "HRB" / "4.-Charlas"
    hosp_dir.mkdir(parents=True)
    for name, pages in {"2026-04-01_charla_a.pdf": 1, "2026-04-02_charla_b.pdf": 28}.items():
        d = fitz.open()
        for _ in range(pages):
            d.new_page()
        d.save(hosp_dir / name)
        d.close()

    from api.main import create_app
    app = create_app()
    with TestClient(app) as c:
        mgr = app.state.manager
        sid = mgr.open_session(year=2026, month=4, month_root=tmp_path)["session_id"]
        # filename_glob cell (not OCR): 1-page -> R1, 28-page -> Pendiente.
        mgr.apply_filename_result("2026-04", "HRB", "charla", ScanResult(
            count=2, confidence=ConfidenceLevel.LOW, method="filename_glob",
            breakdown=None, flags=[], errors=[], duration_ms=1, files_scanned=2,
            per_file={"2026-04-01_charla_a.pdf": 1, "2026-04-02_charla_b.pdf": 1},
        ))
        rows = {r["name"]: r for r in c.get("/api/sessions/2026-04/cells/HRB/charla/files").json()}
        assert rows["2026-04-01_charla_a.pdf"]["origin"] == "R1"       # 1 page
        assert rows["2026-04-02_charla_b.pdf"]["origin"] == "Pendiente"  # multipage, filename
```

Note the month folder name must match how `_find_category_folder` resolves `charla`
(it maps sigla→`CATEGORY_FOLDERS`; verify the exact folder name `4.-Charlas` against
`core/domain.py` and adjust). Confirm `_resolve_month_dir`/`enumerate` expectations by
reading the existing `test_cell_files_endpoint.py` fixture before finalizing.

- [ ] **Step 2 (deferred run):** would be `pytest tests/test_cell_files_endpoint.py::test_origin_chip_rule -v` → FAIL (origin is "R1" for both today). Do not run now.

- [ ] **Step 3: Change `_origin_for` signature + rule.** Replace the nested function and its call site.

```python
        def _origin_for(filename: str, override: int | None, page_count: int) -> str:
            """Per-file chip (spec G1): Manual/Error/OCR/R1/Pendiente. Canonical casing."""
            if override is not None:
                return "Manual"
            if page_count == 0:  # unreadable PDF
                return "Error"
            if cell_method in ("header_detect", "corner_count", "header_band_anchors", "v4"):
                return "OCR"
            if cell_method == "page_count_pure":
                return "R1"  # fixed-page sigla, auto-reliable (was "Estructura")
            if cell_method == "filename_glob":
                return "R1" if page_count == 1 else "Pendiente"
            return "R1"
```

At the call site (inside the `for pdf` loop, after `page_count` is computed):
```python
                "origin": _origin_for(pdf.name, override, page_count),
```

- [ ] **Step 3b: Update the EXISTING assertions in `tests/test_cell_files_endpoint.py`.**
The casing change breaks any test asserting the old lowercase `"manual"`. Grep
`tests/test_cell_files_endpoint.py` for `== "manual"` (there is at least one, ~line
64) and change `"manual"` → `"Manual"`. Also re-check any assertion that expects an
old multipage file to be `"R1"`: a multipage `filename_glob` file now returns
`"Pendiente"` — update those to `"Pendiente"` (and 1-page ones stay `"R1"`). Read the
file and reconcile every `origin` assertion with the new rule before moving on.

- [ ] **Step 4 (deferred run):** test would PASS.

- [ ] **Step 5: Commit**
```bash
git add api/routes/sessions.py tests/test_cell_files_endpoint.py
git commit -m "feat(api): per-file chip rule R1/OCR/Manual/Pendiente/Error" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 1.2: Frontend chip — OriginChip 5 variants + drop trivial/Estructura

**Files:**
- Modify: `src/components/OriginChip.jsx`, `src/components/FileList.jsx` (~114-116), `src/components/PDFLightbox.jsx` (`FileSummary` ~the trivial branch), `src/components/HistoryDrawer.jsx` (`methodToOrigin` + remove TODO)
- Test: `src/components/OriginChip.test.js` (extend)

- [ ] **Step 1: Update `OriginChip.test.js`** — replace the Estructura case with the 5-variant set:
```js
it("maps the five canonical origins to tones", () => {
  expect(originVariant("R1")).toBe("jade");
  expect(originVariant("OCR")).toBe("iris");
  expect(originVariant("Manual")).toBe("blue");
  expect(originVariant("Pendiente")).toBe("amber");
  expect(originVariant("Error")).toBe("state-error");
});
it("falls back to neutral for unknown", () => {
  expect(originVariant("???")).toBe("neutral");
});
```
(Delete the old `Estructura`/`not.toBe(OCR)` assertions.)

- [ ] **Step 2: `OriginChip.jsx`** — set the map:
```jsx
export const ORIGIN_VARIANT = {
  R1: "jade",
  OCR: "iris",
  Manual: "blue",
  Pendiente: "amber",
  Error: "state-error",
};
```
(`originVariant` + default `OriginChip` unchanged.)

- [ ] **Step 3: `FileList.jsx`** — remove the trivial branch; always render the chip:
```jsx
            <OriginChip origin={f.origin ?? "R1"} />
```
(Delete the `{f.page_count === 1 ? <Badge variant="iris">trivial</Badge> : ...}` ternary.)
Also change the optimistic `onCommit` update `origin: "manual"` → `origin: "Manual"`.

- [ ] **Step 4: `PDFLightbox.jsx` `FileSummary`** — same: replace the
`{file.page_count === 1 ? trivial : <OriginChip .../>}` with `<OriginChip origin={file.origin ?? "R1"} />`. Change the editor's optimistic `origin: "manual"` → `origin: "Manual"`.

- [ ] **Step 5: `HistoryDrawer.jsx`** — `methodToOrigin`: return `"Manual"` (was `"manual"`), and `"R1"` for `page_count_pure`:
```jsx
function methodToOrigin(method) {
  if (method === "manual") return "Manual";
  if (method === "filename_glob" || method === "page_count_pure") return "R1";
  return "OCR"; // header_detect / corner_count / header_band_anchors / v4
}
```
Delete the stale `TODO(conteo-confiable)` comment block above it (history mapping is now aligned).

- [ ] **Step 6: Commit**
```bash
git add src/components/OriginChip.jsx src/components/OriginChip.test.js src/components/FileList.jsx src/components/PDFLightbox.jsx src/components/HistoryDrawer.jsx
git commit -m "feat(frontend): render 5-chip origin set, drop trivial/Estructura" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Chunk 2: G4 — Five small fixes

### Task 2.1: #11 ETA in minutes (`formatEta`)

**Files:** `src/lib/scanCost.js`, `src/lib/scanCost.test.js`, `src/components/ScanProgress.jsx:42-43`

- [ ] **Step 1: Test** (append to `scanCost.test.js`):
```js
import { formatEta } from "./scanCost";
describe("formatEta", () => {
  it("rounds to whole minutes, min 1", () => {
    expect(formatEta(90_000)).toBe("~2 min");   // 1.5 min -> 2
    expect(formatEta(20_000)).toBe("~1 min");    // <1 min -> 1
    expect(formatEta(600_000)).toBe("~10 min");
  });
});
```
- [ ] **Step 2: `scanCost.js`** — add:
```js
export function formatEta(ms) {
  return `~${Math.max(1, Math.round(ms / 60000))} min`;
}
```
- [ ] **Step 3: `ScanProgress.jsx`** — import `formatEta`; replace line 43:
```jsx
        {etaMs && !terminal && (
          <span className="text-xs text-po-text-muted">{formatEta(etaMs)}</span>
        )}
```
- [ ] **Step 4: Commit** `feat(frontend): show scan ETA in minutes`.

### Task 2.2: #12 hospital header copy

**Files:** `src/views/HospitalDetail.jsx:61-64`

- [ ] **Step 1:** Change the header label so the count reads as documents:
```jsx
        <span className="text-sm text-po-text-muted">
          Total: <span className="tabular-nums">{total.toLocaleString()}</span>{" "}
          {hospitalMode === "manual" ? "documentos ingresados" : "documentos detectados"}
        </span>
```
Then **delete the now-unused `const headerCountLabel = …` declaration** at
`HospitalDetail.jsx:45` (it's only referenced at line 60, which this edit replaces).
- [ ] **Step 2: Commit** `fix(frontend): label hospital total as documents`.

### Task 2.3: #13 single Excel toast

**Files:** `src/views/MonthOverview.jsx` (`onGenerate` ~42-55)

- [ ] **Step 1:** Fold the warning into the success toast's `description`; keep the `catch` `toast.error` intact:
```jsx
      const r = await generateOutput(session.session_id);
      const warn = r.worker_warnings?.length
        ? `Conteo de trabajadores incompleto en ${r.worker_warnings.length} celda(s).`
        : undefined;
      toast.success(`Excel guardado en ${r.output_path}`, {
        icon: <FileSpreadsheet size={16} />,
        description: warn,
      });
```
(Delete the separate `toast.warning(...)` call. Leave the `try/catch` and `toast.error` as-is.)
- [ ] **Step 2: Commit** `fix(frontend): merge Excel success+warning into one toast`.

### Task 2.4: #8 (i) on Método (`method-info.js`)

**Files:** Create `src/lib/method-info.js` + `src/lib/method-info.test.js`; Modify `src/components/DetailPanel.jsx` (the "Método" row)

- [ ] **Step 1: Test** (`method-info.test.js`):
```js
import { describe, expect, it } from "vitest";
import { METHOD_INFO } from "./method-info";
import { METHOD_LABEL } from "./method-labels";
it("has an explanation for every labelled method", () => {
  for (const token of Object.keys(METHOD_LABEL)) {
    expect(typeof METHOD_INFO[token]).toBe("string");
    expect(METHOD_INFO[token].length).toBeGreaterThan(0);
  }
});
```
- [ ] **Step 2: `method-info.js`**:
```js
// Brief, operator-facing explanation per ScanResult.method token. Adjustable copy.
export const METHOD_INFO = {
  filename_glob: "Un documento por archivo PDF. Fiable cuando cada PDF es un solo documento.",
  page_count_pure: "Un documento por página. Para siglas donde cada página es un chequeo (bodega, extintores, excavaciones…).",
  header_detect: "Lee el encabezado de cada página y cuenta una portada por documento.",
  header_band_anchors: "Lee el encabezado de cada página y cuenta una portada por documento.",
  corner_count: "Cuenta documentos por la numeración de página detectada por OCR.",
  v4: "Cuenta documentos por la numeración 'Página N de M' detectada por OCR.",
  manual: "Valor ingresado a mano por el operador.",
};
```
- [ ] **Step 3: `DetailPanel.jsx`** — next to the "Método" value, add an `Info` icon (lucide) wrapped in the existing `Tooltip` primitive, content `METHOD_INFO[cell?.method]` (only when present):
```jsx
import { Info } from "lucide-react";
import { METHOD_INFO } from "../lib/method-info";
// …in the Método row, after the method label:
{METHOD_INFO[cell?.method] && (
  <Tooltip content={METHOD_INFO[cell.method]}>
    <span className="inline-flex"><Info size={13} strokeWidth={1.75} className="text-po-text-muted ml-1 cursor-help" /></span>
  </Tooltip>
)}
```
(Read `DetailPanel.jsx` first to place this in the exact Método row; it already imports `METHOD_LABEL`.)
- [ ] **Step 4: Commit** `feat(frontend): add (i) method explanation on the detail panel`.

### Task 2.5: #2 white manual-adjust input in the lightbox

**Files:** `src/components/PDFLightbox.jsx` (the per-file editor `InlineEditCount`) and/or `src/components/InlineEditCount.jsx`

- [ ] **Step 1:** Read `InlineEditCount.jsx`. It renders both a display number and an `<input>` in edit mode. In the lightbox's dark `aside`, the input/number inherits a dark color. Ensure the input + displayed number use `text-po-text` (and border/placeholder `po-*` tokens). If `InlineEditCount` is reused in light contexts where the current color is correct, scope the fix: pass a `className`/`tone` prop from the lightbox editor, or wrap the lightbox editor so its input is `text-po-text`. Prefer the minimal change: confirm whether the dark color is an explicit class in `InlineEditCount` or inherited; fix at the source if it's just a missing `text-po-text`, else scope via prop.
- [ ] **Step 2: Commit** `fix(frontend): white manual-adjust input in the PDF lightbox`.

---

## Chunk 3: G3 — OCR from the viewer + post-scan refresh

### Task 3.1: `filesTick` store counter + increment on terminal cell events

**Files:** `src/store/session.js`

- [ ] **Step 1:** Add `filesTick: {}` to the initial store state (near `scanningCells`/`scanProgress`).
- [ ] **Step 2:** Increment the tick in the **`cell_done`** handler only (~462-481) —
that event carries `event.hospital`/`event.sigla` and is the one that just wrote new
`per_file` to the DB. After applying the cell result, bump:
```js
        set((prev) => {
          const key = `${event.hospital}|${event.sigla}`;
          return { filesTick: { ...prev.filesTick, [key]: (prev.filesTick[key] ?? 0) + 1 } };
        });
```
(Integrate into the existing `cell_done` `set` if cleaner than a second `set`.)

> **Do NOT** add this to `scan_cancelled` (`session.js:~535-545`): that is a run-level
> event with **no `hospital`/`sigla`** → the key would be `"undefined|undefined"`
> (a garbage no-op). A cancelled scan didn't change `per_file`, so no refresh is
> needed there. `cell_error`: only bump if that event carries `hospital`/`sigla`
> (read the handler; if it does, include it — otherwise skip).
- [ ] **Step 3: Commit** `feat(store): filesTick counter bumped on terminal cell scan events`.

### Task 3.2: FileList + lightbox re-fetch on tick

**Files:** `src/components/FileList.jsx` (useEffect ~19-28), `src/components/PDFLightbox.jsx` (useEffect ~80-85 / ~93-98)

- [ ] **Step 1: FileList** — subscribe to the tick and add it to the fetch effect deps:
```jsx
  const tick = useSessionStore((s) => s.filesTick[`${hospital}|${sigla}`] ?? 0);
  useEffect(() => { /* existing getCellFiles fetch */ },
    [session?.session_id, hospital, sigla, tick]);
```
- [ ] **Step 2: PDFLightbox** — same, keyed by `lightbox.hospital|lightbox.sigla`:
```jsx
  const tick = useSessionStore((s) => lightbox ? (s.filesTick[`${lightbox.hospital}|${lightbox.sigla}`] ?? 0) : 0);
  // add `tick` to the getCellFiles useEffect deps
```
- [ ] **Step 3: Commit** `feat(frontend): refresh FileList + lightbox after OCR via filesTick`.

### Task 3.3: "Escanear con OCR" button in the viewer

**Files:** `src/components/PDFLightbox.jsx` (inspect branch header/aside)

- [ ] **Step 1:** In the inspect branch, add a `Button` (icon `Scan`) "Escanear con OCR" that calls `scanOcr(session.session_id, [[lightbox.hospital, lightbox.sigla]])` (store action already exists, with its cost guard). Disable + tooltip when the sigla has no OCR strategy — derive from the cell: if `cell?.method === "filename_glob"` and the sigla isn't OCR-capable. Simplest reliable gate: enable always except when a scan for this cell is already running (`scanningCells.has(`${h}|${s}`)`); the backend returns 404/handles non-OCR siglas. (Confirm with Daniel in smoke whether to hide for `none`-strategy siglas like `reunion`.)
- [ ] **Step 2:** While scanning, show the existing spinner state (reuse `scanningCells`/`ScanProgress`). On completion, Task 3.2's tick refreshes the per-file data automatically.
- [ ] **Step 3: Commit** `feat(frontend): scan current cell with OCR from the lightbox`.

### Task 3.4: pytest — origin OCR + per-file count after OCR

**Files:** `tests/test_cell_files_endpoint.py` (extend)

- [ ] **Step 1:** Add a test: seed a cell via `apply_ocr_result` with `method="header_band_anchors"` and `per_file={"x.pdf": 3}` (real folder with a 3+page `x.pdf`); `GET …/files` → that row `origin == "OCR"` and `effective_count == 3`.
- [ ] **Step 2: Commit** `test(api): per-file OCR origin + count after scan`.

---

## Chunk 4: G2 — File viewer rework (thumbnails + fit + scroll/zoom)

### Task 4.1: `wheelToPageStep` helper (testable nav math)

**Files:** Create `src/lib/viewer-nav.js` + `src/lib/viewer-nav.test.js`

- [ ] **Step 1: Test**:
```js
import { describe, expect, it } from "vitest";
import { wheelToPageStep, WHEEL_PAGE_THRESHOLD } from "./viewer-nav";
describe("wheelToPageStep", () => {
  it("accumulates small deltas until threshold, then steps once", () => {
    let acc = 0, step;
    ({ step, acc } = wheelToPageStep(WHEEL_PAGE_THRESHOLD / 2, acc));
    expect(step).toBe(0);
    ({ step, acc } = wheelToPageStep(WHEEL_PAGE_THRESHOLD / 2 + 1, acc));
    expect(step).toBe(1);   // forward one page
    expect(acc).toBe(0);    // resets after a step
  });
  it("steps -1 on sufficient negative delta", () => {
    const { step } = wheelToPageStep(-WHEEL_PAGE_THRESHOLD - 1, 0);
    expect(step).toBe(-1);
  });
});
```
- [ ] **Step 2: `viewer-nav.js`**:
```js
// Trackpads fire many small wheel deltas; accumulate until a threshold so one
// gesture = one page, not five. Returns { step: -1|0|1, acc: carryover }.
export const WHEEL_PAGE_THRESHOLD = 120;
export function wheelToPageStep(deltaY, acc) {
  const next = acc + deltaY;
  if (next >= WHEEL_PAGE_THRESHOLD) return { step: 1, acc: 0 };
  if (next <= -WHEEL_PAGE_THRESHOLD) return { step: -1, acc: 0 };
  return { step: 0, acc: next };
}
```
- [ ] **Step 3: Commit** `feat(frontend): wheel-to-page-step nav helper`.

### Task 4.2: Rewrite `InspectView` on the paged pattern

**Files:** `src/components/PDFLightbox.jsx` (`InspectView` ~42-71)

Read `WorkerCountViewer.jsx` as the template. Build a paged inspect viewer:

- [ ] **Step 1:** Replace `InspectView` so it:
  - Calls `usePdfDocument(url)` → `{doc, error, loading}`; page count from the prop `pageCount` (passed from `PDFLightbox`, sourced from `files[fileIndex].page_count`).
  - Local state `const [page, setPage] = useState(1)` and `const [zoom, setZoom] = useState(1)`; reset `page=1` on `url` change and `zoom=1` on `page` change.
  - `const { panelRef, fitScale } = useFitScale(doc, page)`; `const effectiveScale = Math.max(0.1, fitScale * zoom)`.
  - Layout: `<div className="flex h-full"> <WorkerThumbnails doc={doc} pageCount={pageCount} currentPage={page} marks={[]} onSelect={setPage} /> <div ref={panelRef} onWheel={onWheel} className="flex-1 overflow-auto p-4 flex items-start justify-center"> <PdfPage doc={doc} pageNumber={page} scale={effectiveScale} /> </div> </div>`.
  - `onWheel(e)`: if `e.shiftKey` → `e.preventDefault()` and zoom (`setZoom(z => clamp(z + (e.deltaY<0?ZOOM_STEP:-ZOOM_STEP), 0.25, 4))`); else accumulate via `wheelToPageStep` (keep `acc` in a `useRef`), and on non-zero step `e.preventDefault()` + `setPage(p => clamp(p+step, 1, pageCount))`.
  - Keyboard via a `window` keydown listener (mounted while inspect viewer is alive, mirroring `WorkerCountViewer`): `PageDown`/`ArrowDown` → next, `PageUp`/`ArrowUp` → prev, `+`/`=` → zoom in, `-`/`_` → zoom out. Guard: ignore when focus is in an input/textarea.
  - Error/loading states preserved (the "No se pudo abrir el PDF." message stays).
  - A minimal zoom label `Math.round(zoom*100)%` + a "Ajustar" button that resets `zoom=1` (optional, mirror WorkerCountViewer's Maximize2).
- [ ] **Step 2:** In `PDFLightbox`, pass `pageCount={files?.[lightbox.fileIndex]?.page_count ?? 0}` to `InspectView`, and ensure the inspect branch wraps `InspectView` + the per-file `aside` in a row so thumbnails | page | aside read left→right.
- [ ] **Step 3:** Remove the `react-zoom-pan-pinch` import from `PDFLightbox.jsx` (TransformWrapper/TransformComponent no longer used here). Grep confirmed `PDFLightbox.jsx` is the **only** consumer, so also `npm uninstall react-zoom-pan-pinch` in `frontend/` (clean, zero remaining users). Re-grep to confirm before uninstalling.
- [ ] **Step 4: Commit** `feat(frontend): paged file viewer — thumbnails, fit-to-window, scroll=page, shift+scroll=zoom`.

---

## Chunk 5: G5 — Last Excel on the home

### Task 5.1: Backend — serve + list endpoints

**Files:** `api/routes/output.py`; Test: `tests/test_output_serve_endpoint.py` (new)

- [ ] **Step 1: Test** (`tests/test_output_serve_endpoint.py`):
```python
def test_serve_and_list_output(tmp_path, monkeypatch):
    monkeypatch.setenv("OVERSEER_OUTPUT_DIR", str(tmp_path))
    (tmp_path / "RESUMEN_2026-04.xlsx").write_bytes(b"PK\x03\x04stub")
    from api.main import create_app
    with TestClient(create_app()) as c:
        r = c.get("/api/sessions/2026-04/output")
        assert r.status_code == 200
        assert "spreadsheetml" in r.headers["content-type"]
        assert c.get("/api/sessions/2026-13/output").status_code == 400  # bad id
        assert c.get("/api/sessions/2026-05/output").status_code == 404  # missing
        lst = c.get("/api/outputs").json()
        assert any(o["session_id"] == "2026-04" for o in lst)
```
- [ ] **Step 2: `output.py`** — add (reuse `_output_dir()`, `_SESSION_ID_RE` pattern from sessions, `FileResponse`):
```python
@router.get("/sessions/{session_id}/output")
def serve_output(session_id: str) -> FileResponse:
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", session_id):
        raise HTTPException(400, "invalid session_id")
    path = (_output_dir() / f"RESUMEN_{session_id}.xlsx").resolve()
    if not path.is_file() or not path.is_relative_to(_output_dir().resolve()):
        raise HTTPException(404, "no output for that month")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"RESUMEN_{session_id}.xlsx",
    )

@router.get("/outputs")
def list_outputs() -> list[dict]:
    d = _output_dir()
    if not d.exists():
        return []
    out = []
    for p in d.glob("RESUMEN_*.xlsx"):
        st = p.stat()
        out.append({
            "session_id": p.stem.removeprefix("RESUMEN_"),
            "filename": p.name,
            "mtime_iso": datetime.fromtimestamp(st.st_mtime).isoformat(),
            "size": st.st_size,
        })
    out.sort(key=lambda o: o["mtime_iso"], reverse=True)
    return out
```
Add imports at the top of `output.py`: `import re`, `from datetime import datetime`
(use exactly this form so `datetime.fromtimestamp(...)` works — NOT `import datetime`),
`from fastapi import HTTPException`, `from fastapi.responses import FileResponse`.
`output.py` currently imports none of these — verify and add.
- [ ] **Step 3: Commit** `feat(api): serve + list generated RESUMEN Excel files`.

### Task 5.2: Frontend — last-Excel section on the home

**Files:** `src/lib/api.js`, `src/views/MonthOverview.jsx`

- [ ] **Step 1: `api.js`** — add:
```js
  outputUrl: (sessionId) => `${BASE}/sessions/${sessionId}/output`,
  listOutputs: async () => { const r = await fetch(`${BASE}/outputs`); if (!r.ok) throw new Error(await r.text()); return r.json(); },
```
- [ ] **Step 2: `MonthOverview.jsx`** — near "Generar Excel del mes", fetch `listOutputs()` on mount (or after a successful generate) and render a small "Último Excel" row for the most recent (or the active month's) file: `<a href={api.outputUrl(o.session_id)} className="…">RESUMEN_{o.session_id}.xlsx · {fecha}</a>`. If none, render nothing (or "aún no generado"). Refresh the list after `onGenerate` succeeds. Microcopy notes it downloads/opens.
- [ ] **Step 3: Commit** `feat(frontend): list + open the last generated Excel on the home`.

---

## Chunk 6: Verification (END — all tests together)

### Task 6.1: Full suite + build

- [ ] **Step 1:** `ruff check .` (worktree) → 0.
- [ ] **Step 2:** `pytest -q` (worktree, venv python) → only the ~12 known `FileNotFoundError` env failures (VLM/pdf_render/eval); everything else green. If any NEW failure: fix (superpowers:systematic-debugging), commit.
- [ ] **Step 3:** `cd frontend && npx vitest run` → green; `npm run build` → OK.

### Task 6.2: Live smoke (chrome-devtools, ABRIL, isolated DB)

- [ ] **Step 1:** Reuse/restart backend(:8000 isolated DB) + Vite(:5173) + Chrome(:9222). Re-scan ABRIL if needed.
- [ ] **Step 2:** Drive and verify:
  - **Chips:** a charla/odi multipage file shows **Pendiente** (not R1); exc/bodega files show **R1** (no "Estructura"); after OCR a cell → files show **OCR** + the OCR per-file count (FileList + lightbox refresh, #5/#6); an unreadable PDF (if any) → **Error**.
  - **Viewer:** opens fit-to-window; **scroll changes page**, **Shift+scroll zooms**, +/- and PgUp/Dn work; thumbnails column jumps pages; manual-adjust input is **white** (#2).
  - **OCR button** in the viewer scans the cell.
  - **Fixes:** ETA shows **minutes** (#11); header says **"documentos detectados"** (#12); Excel generate shows **one** toast with the warning as description (#13); **(i)** on Método shows the explanation (#8).
  - **Home:** the last **Excel is listed and clickable** (downloads/opens) (#14).
- [ ] **Step 3:** Fix any smoke bugs (commit per fix). Capture screenshots to `docs/research/`.

### Task 6.3: Tag

- [ ] **Step 1:** Create a **new** tag (don't force-move the MVP tag — preserve that
milestone): `git tag -a conteo-confiable-rev-1 -m "Conteo confiable — revisión post-MVP (14 fixes)"`. Local. Confirm tag name with Daniel.

---

## Out of scope (YAGNI)
- #7 live per-file chip during OCR (needs per-PDF partial-result streaming).
- Reworking the worker viewer (only its pieces are reused).
- Inline `.xlsx` render in the browser (downloads instead).
- Removing the `react-zoom-pan-pinch` dependency (unless grep shows zero other users).

## Notes
- Verify every `file:line` anchor against the tree before editing; re-pin if drifted.
- Suggested order is G1 → G4 → G3 → G2 → G5 (small/independent first, biggest viewer rework late), then Chunk 6.
