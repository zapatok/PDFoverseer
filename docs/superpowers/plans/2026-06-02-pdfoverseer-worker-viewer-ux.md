# Worker-Viewer UX Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four refinements to Feature 1's worker-count viewer — fix the partial total reading 0 outside the viewer, fit-to-window + per-page manual zoom, a current-PDF thumbnail column, and a persistent shortcuts legend.

**Architecture:** Three small pure modules under `frontend/src/lib/` (each unit-tested with vitest), wired into the existing `WorkerCountViewer`/`WorkerHud` React components plus one new `WorkerThumbnails` component. The bug fix lives in the shared `worker-count.js`, so both the DetailPanel and the viewer get correct totals. No backend changes.

**Tech Stack:** React + Vite, pdf.js (`usePdfDocument`/`PdfPage`), Tailwind `po-*` tokens, `Badge`/`Button` primitives, lucide-react icons, vitest.

**Spec:** `docs/superpowers/specs/2026-06-02-worker-viewer-ux-design.md`

---

## File Structure

**Create:**
- `frontend/src/lib/worker-count.test.js` — vitest for the bug fix.
- `frontend/src/lib/fit-scale.js` — pure `computeFitScale(viewport, panel)`.
- `frontend/src/lib/fit-scale.test.js` — vitest.
- `frontend/src/lib/worker-shortcuts.js` — single-source `WORKER_SHORTCUTS` list.
- `frontend/src/lib/worker-shortcuts.test.js` — vitest (handler-key coverage).
- `frontend/src/hooks/useFitScale.js` — wires `computeFitScale` to the panel size + page size.
- `frontend/src/components/WorkerThumbnails.jsx` — left thumbnail column.

**Modify:**
- `frontend/src/lib/worker-count.js` — fix the empty-array filter guard.
- `frontend/src/components/WorkerCountViewer.jsx` — fit scale, zoom state + keys + overlay, thumbnails column.
- `frontend/src/components/WorkerHud.jsx` — shortcuts legend.

**Conventions:** run tests with `npm test` (= `vitest run`) from `frontend/`. Tests live beside the lib as `*.test.js`. Use `po-*` Tailwind tokens (never raw palette). Commit messages: `type(scope): message`; end body with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

## Chunk 1: Pure libs (TDD)

### Task 1: Fix the partial-count bug in `worker-count.js`

**Root cause:** `computeWorkerCount(marks, fileNames)` guards with `if (fileNames && !present.has(...))`. The DetailPanel passes `Object.keys(cell.per_file || {})`, which is `[]` for an unscanned cell — and `[]` is **truthy** in JS, so every mark is filtered out → 0. The backend (`api/state.py:compute_worker_count`) guards with `if per_file and ...` and an empty dict is falsy, so it counts all marks. The fix makes the JS mirror the backend: only filter when the list is non-empty.

**Files:**
- Create: `frontend/src/lib/worker-count.test.js`
- Modify: `frontend/src/lib/worker-count.js:11-21`

- [ ] **Step 1: Write the failing test**

`frontend/src/lib/worker-count.test.js`:
```js
import { describe, it, expect } from "vitest";

import { computeWorkerCount } from "./worker-count";

describe("computeWorkerCount", () => {
  const marks = {
    "a.pdf": [{ page: 1, count: 3 }, { page: 2, count: 2 }],
    "b.pdf": [{ page: 1, count: 5 }],
  };

  it("cuenta TODAS las marcas cuando fileNames es un array vacío (celda sin escanear)", () => {
    // Reproduce el bug: el DetailPanel pasa Object.keys({}) === [] (truthy en JS).
    expect(computeWorkerCount(marks, [])).toBe(10);
  });

  it("cuenta todas las marcas cuando fileNames es null/undefined", () => {
    expect(computeWorkerCount(marks, null)).toBe(10);
    expect(computeWorkerCount(marks, undefined)).toBe(10);
  });

  it("filtra las marcas huérfanas cuando hay una lista de archivos presente", () => {
    expect(computeWorkerCount(marks, ["a.pdf"])).toBe(5); // 3 + 2, sin b.pdf
  });

  it("regresión: Object.keys de un per_file vacío sigue sumando", () => {
    expect(computeWorkerCount(marks, Object.keys({}))).toBe(10);
  });

  it("devuelve 0 sin marcas", () => {
    expect(computeWorkerCount({}, [])).toBe(0);
    expect(computeWorkerCount(null, null)).toBe(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- worker-count`
Expected: FAIL — the empty-array and `Object.keys({})` cases return 0, not 10.

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/lib/worker-count.js`, change `computeWorkerCount` so the filter only applies to a non-empty list:
```js
export function computeWorkerCount(marks, fileNames) {
  const filter = Array.isArray(fileNames) && fileNames.length > 0;
  const present = new Set(fileNames || []);
  let total = 0;
  for (const [filename, pageMarks] of Object.entries(marks || {})) {
    if (filter && !present.has(filename)) continue;
    for (const m of pageMarks || []) {
      if (m && typeof m.count === "number") total += m.count;
    }
  }
  return total;
}
```
(Update the JSDoc note above it to: "Si `fileNames` viene vacío o nulo no se filtra — espeja a `compute_worker_count` del backend, que no filtra cuando `per_file` está vacío.")

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- worker-count`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**
```bash
git add frontend/src/lib/worker-count.js frontend/src/lib/worker-count.test.js
git commit -m "fix(frontend): count partial worker totals when file list is empty" \
  -m "computeWorkerCount filtered out every mark when fileNames was an empty array (Object.keys of an empty per_file), because [] is truthy in JS. Mirror the backend: only filter when the list is non-empty. Fixes the DetailPanel showing 0 for an in-progress charla/chintegral cell." \
  -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `computeFitScale` pure function

**Files:**
- Create: `frontend/src/lib/fit-scale.js`
- Create: `frontend/src/lib/fit-scale.test.js`

- [ ] **Step 1: Write the failing test**

`frontend/src/lib/fit-scale.test.js`:
```js
import { describe, it, expect } from "vitest";

import { computeFitScale } from "./fit-scale";

describe("computeFitScale", () => {
  it("limita por ancho cuando la página es relativamente más ancha", () => {
    // página 1000x500, panel 500x500 → min(0.5, 1.0)
    expect(computeFitScale({ width: 1000, height: 500 }, { width: 500, height: 500 })).toBe(0.5);
  });

  it("limita por alto cuando la página es relativamente más alta", () => {
    // página 500x1000, panel 500x500 → min(1.0, 0.5)
    expect(computeFitScale({ width: 500, height: 1000 }, { width: 500, height: 500 })).toBe(0.5);
  });

  it("amplía si el panel es mayor que la página (contain, no clamp a 1)", () => {
    expect(computeFitScale({ width: 250, height: 250 }, { width: 500, height: 500 })).toBe(2);
  });

  it("devuelve 1 si alguna dimensión es 0 (guard de división por cero)", () => {
    expect(computeFitScale({ width: 0, height: 500 }, { width: 500, height: 500 })).toBe(1);
    expect(computeFitScale({ width: 500, height: 500 }, { width: 500, height: 0 })).toBe(1);
    expect(computeFitScale(null, null)).toBe(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- fit-scale`
Expected: FAIL with "computeFitScale is not a function" / module not found.

- [ ] **Step 3: Write minimal implementation**

`frontend/src/lib/fit-scale.js`:
```js
/**
 * Escala para que una página quepa COMPLETA (contain) dentro de un panel.
 *
 * @param {{width:number,height:number}} viewport - tamaño de la página a escala 1.
 * @param {{width:number,height:number}} panel - tamaño disponible del panel.
 * @returns {number} factor de escala; 1 si alguna dimensión es <= 0 (degenerado).
 */
export function computeFitScale(viewport, panel) {
  const pw = viewport?.width || 0;
  const ph = viewport?.height || 0;
  const cw = panel?.width || 0;
  const ch = panel?.height || 0;
  if (pw <= 0 || ph <= 0 || cw <= 0 || ch <= 0) return 1;
  return Math.min(cw / pw, ch / ph);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- fit-scale`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**
```bash
git add frontend/src/lib/fit-scale.js frontend/src/lib/fit-scale.test.js
git commit -m "feat(frontend): add computeFitScale contain-fit helper" \
  -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: `WORKER_SHORTCUTS` single source of truth

**Files:**
- Create: `frontend/src/lib/worker-shortcuts.js`
- Create: `frontend/src/lib/worker-shortcuts.test.js`

- [ ] **Step 1: Write the failing test**

`frontend/src/lib/worker-shortcuts.test.js`:
```js
import { describe, it, expect } from "vitest";

import { WORKER_SHORTCUTS } from "./worker-shortcuts";

describe("WORKER_SHORTCUTS", () => {
  const matches = new Set(WORKER_SHORTCUTS.flatMap((s) => s.match));

  it("cubre cada tecla que el visor maneja", () => {
    const handled = ["PageDown", "PageUp", "Delete", "e", "E", "m", "M", "Backspace", "+", "-", "0", "5", "9"];
    for (const k of handled) expect(matches.has(k)).toBe(true);
  });

  it("cada entrada tiene chips (keys) y una acción", () => {
    for (const s of WORKER_SHORTCUTS) {
      expect(Array.isArray(s.keys)).toBe(true);
      expect(s.keys.length).toBeGreaterThan(0);
      expect(typeof s.action).toBe("string");
    }
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- worker-shortcuts`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

`frontend/src/lib/worker-shortcuts.js`:
```js
/**
 * Fuente única de los atajos del visor de conteo de trabajadores. La leyenda
 * (WorkerHud) y el handler de teclado (WorkerCountViewer) se mantienen alineados
 * con esta lista; el test verifica que cada `match` esté cubierto por el handler.
 *
 * - `keys`:  etiquetas mostradas como chips.
 * - `match`: valores de `KeyboardEvent.key` que disparan el atajo (para el test).
 * - `action`: descripción en español neutro.
 */
export const WORKER_SHORTCUTS = [
  { keys: ["0-9"],        match: ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"], action: "Ingresar número" },
  { keys: ["Av Pág"],     match: ["PageDown"],  action: "Fijar y avanzar" },
  { keys: ["Re Pág"],     match: ["PageUp"],    action: "Retroceder" },
  { keys: ["Supr"],       match: ["Delete"],    action: "Borrar marca" },
  { keys: ["E"],          match: ["e", "E"],    action: "Editar página" },
  { keys: ["+", "−"],     match: ["+", "-"],    action: "Acercar / alejar" },
  { keys: ["M"],          match: ["m", "M"],    action: "Voz on / off" },
  { keys: ["Retroceso"],  match: ["Backspace"], action: "Corregir dígito" },
];
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- worker-shortcuts`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**
```bash
git add frontend/src/lib/worker-shortcuts.js frontend/src/lib/worker-shortcuts.test.js
git commit -m "feat(frontend): add WORKER_SHORTCUTS single-source list" \
  -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 6: Full vitest run (chunk gate)**

Run: `npm test`
Expected: PASS — baseline 28 + the new worker-count/fit-scale/worker-shortcuts tests, 0 failures.

---

## Chunk 2: Viewer + HUD integration

> These tasks touch pdf.js canvas rendering and the DOM, which the project does not unit-test (mocking is discouraged; only pure libs have tests). Verification for these is the **live smoke in Chunk 3** plus `ruff`/lint-clean build. Each task ends by confirming `npm run build` succeeds.

### Task 4: Fit-to-window + per-page manual zoom

**Files:**
- Create: `frontend/src/hooks/useFitScale.js`
- Modify: `frontend/src/components/WorkerCountViewer.jsx`

- [ ] **Step 1: Create the fit-scale hook**

`frontend/src/hooks/useFitScale.js`:
```js
import { useEffect, useRef, useState } from "react";

import { computeFitScale } from "../lib/fit-scale";

const PANEL_PADDING = 32; // p-4 (16px) por lado, para no recortar la página

/**
 * Escala de ajuste-a-ventana (contain) para la página actual.
 * Mide el panel con ResizeObserver y el tamaño natural de la página con pdf.js.
 *
 * @returns {{ panelRef: object, fitScale: number }}
 */
export function useFitScale(doc, pageNumber) {
  const panelRef = useRef(null);
  const [panel, setPanel] = useState({ width: 0, height: 0 });
  const [pageSize, setPageSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = panelRef.current;
    if (!el) return undefined;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0]?.contentRect;
      if (r) setPanel({ width: r.width, height: r.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!doc) return undefined;
    let cancelled = false;
    doc.getPage(pageNumber).then((p) => {
      if (cancelled) { p.cleanup(); return; }
      const v = p.getViewport({ scale: 1 });
      setPageSize({ width: v.width, height: v.height });
      p.cleanup();
    });
    return () => { cancelled = true; };
  }, [doc, pageNumber]);

  const fitScale = computeFitScale(pageSize, {
    width: panel.width - PANEL_PADDING,
    height: panel.height - PANEL_PADDING,
  });
  return { panelRef, fitScale };
}
```

- [ ] **Step 2: Wire zoom + fit into the viewer**

In `frontend/src/components/WorkerCountViewer.jsx`:

Add imports near the top:
```js
import { ZoomIn, ZoomOut, Maximize2 } from "lucide-react";

import Button from "../ui/Button";
import { useFitScale } from "../hooks/useFitScale";
```

Add zoom constants below `SAVE_DEBOUNCE_MS`:
```js
const ZOOM_MIN = 0.25;
const ZOOM_MAX = 4;
const ZOOM_STEP = 0.2;
```

Inside the component, after the `micPaused` state (line ~36) add zoom state:
```js
const [zoom, setZoom] = useState(1);
```

After the existing "limpia el buffer pendiente al cambiar de página" effect (lines ~81-83), add the per-page reset (spec ②):
```js
// El zoom es por página: al cambiar de página o archivo vuelve a "ajustado".
useEffect(() => { setZoom(1); }, [fileIndex, pageInFile]);
```

After `const { doc, error } = usePdfDocument(pdfUrl);` (line ~61) add:
```js
const { panelRef, fitScale } = useFitScale(doc, /* page computed below */ 1);
```
> NOTE: `page` is derived later in the file (after the early returns). Move the `useFitScale` call so it uses the bound `page`, OR pass `pageInFile` clamped. Simplest: call `useFitScale(doc, Math.max(pageInFile, 1))` here — `pageInFile` is the source state and the page render already clamps. The hook only reads natural page size, so a transient over-bound value self-corrects on the next render.

Replace the hook call with:
```js
const { panelRef, fitScale } = useFitScale(doc, Math.max(pageInFile, 1));
```

Add zoom helpers next to the other handlers (near `advance`/`retreat`):
```js
const zoomIn = () => setZoom((z) => Math.min(ZOOM_MAX, +(z + ZOOM_STEP).toFixed(2)));
const zoomOut = () => setZoom((z) => Math.max(ZOOM_MIN, +(z - ZOOM_STEP).toFixed(2)));
const resetZoom = () => setZoom(1);
const effectiveScale = Math.max(0.1, fitScale * zoom);
```

In `keyHandler.current`, add the zoom keys (before the digit branch):
```js
else if (e.key === "+" || e.key === "=") { e.preventDefault(); zoomIn(); }
else if (e.key === "-" || e.key === "_") { e.preventDefault(); zoomOut(); }
```

- [ ] **Step 3: Update the PDF panel JSX**

Replace the PDF panel `<div className="relative flex-1 overflow-auto bg-black">` block so it (a) carries `ref={panelRef}`, (b) renders `PdfPage` at `effectiveScale`, (c) shows the zoom overlay:
```jsx
<div ref={panelRef} className="relative flex-1 overflow-auto bg-black">
  {error ? (
    <div className="flex h-full w-full items-center justify-center p-8 text-center text-sm text-po-text-muted">
      No se pudo abrir este PDF. Usa Re Pág / Av Pág para moverte a otro
      archivo; la celda quedará incompleta.
    </div>
  ) : (
    doc && (
      <div className="flex justify-center p-4">
        <PdfPage doc={doc} pageNumber={page} scale={effectiveScale} />
      </div>
    )
  )}
  <WorkerBubble state={bubbleState} value={bubbleValue} />
  {doc && !error && (
    <div className="absolute bottom-3 right-3 flex items-center gap-1 rounded-lg bg-po-panel/90 p-1 shadow-sm ring-1 ring-po-border backdrop-blur">
      <Button size="sm" variant="ghost" icon={ZoomOut} onClick={zoomOut} aria-label="Alejar" />
      <Button size="sm" variant="ghost" icon={Maximize2} onClick={resetZoom} aria-label="Ajustar a ventana">
        {Math.round(zoom * 100)}%
      </Button>
      <Button size="sm" variant="ghost" icon={ZoomIn} onClick={zoomIn} aria-label="Acercar" />
    </div>
  )}
</div>
```

- [ ] **Step 4: Build + lint**

Run: `npm run build`
Expected: build succeeds, no unused-import / lint errors.

- [ ] **Step 5: Commit**
```bash
git add frontend/src/hooks/useFitScale.js frontend/src/components/WorkerCountViewer.jsx
git commit -m "feat(frontend): fit worker-viewer page to window with per-page manual zoom" \
  -m "Page renders contain-fitted to the panel (ResizeObserver + computeFitScale); + / - keys and an overlay control adjust zoom, which resets to fit on every page/file change." \
  -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: `WorkerThumbnails` column (current PDF)

**Files:**
- Create: `frontend/src/components/WorkerThumbnails.jsx`
- Modify: `frontend/src/components/WorkerCountViewer.jsx` (layout)

- [ ] **Step 1: Create the component**

`frontend/src/components/WorkerThumbnails.jsx`:
```jsx
import { useEffect, useRef, useState } from "react";

// Cache de miniaturas: WeakMap sobre el objeto `doc` → Map(page → dataURL).
// Al cambiar de archivo `doc` es otro objeto, así que el cache se invalida solo.
const THUMB_CACHE = new WeakMap();
const THUMB_WIDTH = 92; // px de ancho del raster

function cacheFor(doc) {
  let m = THUMB_CACHE.get(doc);
  if (!m) { m = new Map(); THUMB_CACHE.set(doc, m); }
  return m;
}

function Thumb({ doc, pageNumber, active, count, onSelect }) {
  const ref = useRef(null);
  const [url, setUrl] = useState(() => cacheFor(doc).get(pageNumber) || null);

  useEffect(() => {
    if (url) return undefined; // ya cacheada
    const el = ref.current;
    if (!el) return undefined;
    let cancelled = false;
    const io = new IntersectionObserver((entries) => {
      if (!entries[0]?.isIntersecting) return;
      io.disconnect();
      doc.getPage(pageNumber).then((page) => {
        if (cancelled) { page.cleanup(); return; }
        const base = page.getViewport({ scale: 1 });
        const v = page.getViewport({ scale: THUMB_WIDTH / base.width });
        const canvas = document.createElement("canvas");
        canvas.width = v.width;
        canvas.height = v.height;
        const task = page.render({ canvasContext: canvas.getContext("2d"), viewport: v });
        task.promise.then(() => {
          const dataUrl = canvas.toDataURL("image/jpeg", 0.7);
          cacheFor(doc).set(pageNumber, dataUrl);
          page.cleanup();
          if (!cancelled) setUrl(dataUrl);
        }).catch(() => page.cleanup());
      });
    });
    io.observe(el);
    return () => { cancelled = true; io.disconnect(); };
  }, [doc, pageNumber, url]);

  return (
    <button
      ref={ref}
      onClick={() => onSelect(pageNumber)}
      aria-current={active ? "true" : undefined}
      aria-label={`Página ${pageNumber}${count != null ? `, ${count} trabajadores` : ""}`}
      className={[
        "relative block w-full rounded border p-0.5 transition",
        active
          ? "border-po-accent ring-1 ring-po-accent"
          : "border-po-border hover:border-po-border-strong",
      ].join(" ")}
    >
      {url ? (
        <img src={url} alt="" className="block w-full rounded-sm" />
      ) : (
        <div className="flex aspect-[3/4] w-full items-center justify-center bg-po-bg text-[10px] text-po-text-subtle">
          …
        </div>
      )}
      <span className="absolute left-1 top-1 rounded bg-black/60 px-1 text-[10px] tabular-nums text-white">
        {pageNumber}
      </span>
      {count != null && (
        <span className="absolute right-1 top-1 rounded-full bg-po-confidence-high-bg px-1 text-[10px] font-medium tabular-nums text-po-confidence-high">
          {count}
        </span>
      )}
    </button>
  );
}

/**
 * Columna vertical de miniaturas del PDF actual.
 * @param {object} props
 * @param {object|null} props.doc - PDFDocumentProxy actual.
 * @param {number} props.pageCount
 * @param {number} props.currentPage
 * @param {{page:number,count:number}[]} props.marks - marcas del archivo actual.
 * @param {(page:number)=>void} props.onSelect
 */
export function WorkerThumbnails({ doc, pageCount, currentPage, marks, onSelect }) {
  const countByPage = new Map((marks || []).map((m) => [m.page, m.count]));
  const currentRef = useRef(null);

  useEffect(() => {
    currentRef.current?.scrollIntoView({ block: "nearest" });
  }, [currentPage]);

  if (!doc || !pageCount) {
    return <aside aria-hidden="true" className="w-28 shrink-0 border-r border-po-border bg-po-panel" />;
  }

  return (
    <aside className="w-28 shrink-0 overflow-y-auto border-r border-po-border bg-po-panel p-1.5">
      <ul className="flex flex-col gap-1.5">
        {Array.from({ length: pageCount }, (_, i) => i + 1).map((p) => (
          <li key={p} ref={p === currentPage ? currentRef : null}>
            <Thumb
              doc={doc}
              pageNumber={p}
              active={p === currentPage}
              count={countByPage.has(p) ? countByPage.get(p) : null}
              onSelect={onSelect}
            />
          </li>
        ))}
      </ul>
    </aside>
  );
}
```

- [ ] **Step 2: Add the column to the viewer layout**

In `WorkerCountViewer.jsx`, import it:
```js
import { WorkerThumbnails } from "./WorkerThumbnails";
```
Then make it the first child of the root `<div className="flex h-full w-full">`:
```jsx
return (
  <div className="flex h-full w-full">
    <WorkerThumbnails
      doc={error ? null : doc}
      pageCount={pageCount}
      currentPage={page}
      marks={marks[currentFile.name] || []}
      onSelect={setPageInFile}
    />
    <div ref={panelRef} className="relative flex-1 overflow-auto bg-black">
      {/* …PDF panel from Task 4… */}
    </div>
    <WorkerHud /* …unchanged… */ />
  </div>
);
```

- [ ] **Step 3: Build**

Run: `npm run build`
Expected: build succeeds.

- [ ] **Step 4: Commit**
```bash
git add frontend/src/components/WorkerThumbnails.jsx frontend/src/components/WorkerCountViewer.jsx
git commit -m "feat(frontend): add page-thumbnail column to the worker-count viewer" \
  -m "Lazy (IntersectionObserver) thumbnails for the current PDF, cached per-doc via WeakMap; highlights the active page, badges pages that already have a mark, click jumps to a page." \
  -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Shortcuts legend in `WorkerHud`

**Files:**
- Modify: `frontend/src/components/WorkerHud.jsx`

- [ ] **Step 1: Render the legend**

In `WorkerHud.jsx`, add imports:
```js
import Badge from "../ui/Badge";          // ya importado — reutilizar
import { WORKER_SHORTCUTS } from "../lib/worker-shortcuts";
```
At the foot of the `<aside>` (after the finish `<Button>`), add a compact, always-visible legend:
```jsx
<div className="border-t border-po-border pt-3">
  <p className="mb-1.5 text-xs uppercase tracking-wider text-po-text-muted">Atajos</p>
  <ul className="flex flex-col gap-1">
    {WORKER_SHORTCUTS.map((s) => (
      <li key={s.action} className="flex items-center justify-between gap-2 text-xs">
        <span className="flex shrink-0 gap-1">
          {s.keys.map((k) => (
            <Badge key={k} variant="neutral" className="font-mono">{k}</Badge>
          ))}
        </span>
        <span className="text-right text-po-text-subtle">{s.action}</span>
      </li>
    ))}
  </ul>
</div>
```
> The `aside` is a flex column; the marks list already has `flex-1 overflow-y-auto`, so the legend sits at the bottom without pushing content off-screen. If vertical space is tight, wrap the legend in `shrink-0`.

- [ ] **Step 2: Build**

Run: `npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**
```bash
git add frontend/src/components/WorkerHud.jsx
git commit -m "feat(frontend): show a persistent shortcuts legend in the worker HUD" \
  -m "Renders WORKER_SHORTCUTS (single source) as neutral kbd badges so the legend and keyboard handler can't drift." \
  -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Chunk 3: Live smoke + wrap-up

### Task 7: Bring up the worktree app and smoke all four

- [ ] **Step 1: Point the running app at this worktree**

Stop the OCR-worktree servers (backend `:8000`, Vite `:5173`) and start them from `.worktrees/worker-viewer-ux`:
```bash
# backend (from repo root, main venv supplies packages; CWD = this worktree)
cd "a:/PROJECTS/PDFoverseer/.worktrees/worker-viewer-ux" && \
  source "a:/PROJECTS/PDFoverseer/.venv-cuda/Scripts/activate" && python server.py
# frontend
cd "a:/PROJECTS/PDFoverseer/.worktrees/worker-viewer-ux/frontend" && npm run dev
```
Verify `127.0.0.1:8000` and `5173` are LISTENING and that uvicorn logs `Will watch … worker-viewer-ux`.

- [ ] **Step 2: Drive the smoke via chrome-devtools (Chrome debug :9222)**

Load a session (ABRIL HRB). Open a **charla** or **chintegral** cell → "Contar trabajadores". Verify:
1. Page opens **fitted to the window** (whole page visible).
2. **Thumbnail column** on the left renders the current PDF's pages; the active page is highlighted; clicking a thumbnail jumps to it.
3. **Zoom**: `+`/`−` and the overlay buttons zoom; advancing a page (`Av Pág`) **resets to fit**.
4. **Legend** is visible at the foot of the HUD with all shortcuts.
5. Count 2-3 pages (digits + `Av Pág`); thumbnails show a **count badge** on marked pages.
6. Close the viewer → the **DETALLE shows the partial total** (not 0), and it survives a refresh (bug ① fixed).

- [ ] **Step 3: Fix any bug caught, commit per fix**

Follow superpowers:systematic-debugging for anything that misbehaves. Commit each fix atomically with a descriptive body.

- [ ] **Step 4: Final gate**
```bash
cd "a:/PROJECTS/PDFoverseer/.worktrees/worker-viewer-ux/frontend" && npm test && npm run build
```
Expected: all vitest green, build OK. Tag at the working state:
```bash
git tag worker-viewer-ux-mvp
```
(Local; awaiting Daniel's push approval.)

---

## Out of scope (YAGNI)
- Persisting zoom across pages (resets by design).
- Thumbnails for the whole cell (current PDF only).
- Collapsible/persisted legend.
- Backend changes (bug ① is JS-parity only).

## Integration notes
- Branch `feature/worker-viewer-ux` (worktree `.worktrees/worker-viewer-ux`), independent of PR #1 (OCR). `DetailPanel.jsx` is **not** modified here (the bug fix is in `worker-count.js`), so there is no overlap with the OCR branch's DetailPanel additions.
