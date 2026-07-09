# Track B — viewer + UX polish round Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the ~16 approved Track B items: viewer performance (pre-render + cache + placeholder), bigger/centered thumbnails, navigation (Shift±10, ir-a-página, near-match prev/next), rotate-ops driving display rotation, FileList chip filters + diff highlight + steppers, DetailPanel reorder with collapsible Reorganización, a month-level manifest panel, and chronological month order.

**Architecture:** Spec `docs/superpowers/specs/2026-07-09-track-b-visor-ux-design.md` is the authority — do not re-litigate its decisions (they trace to the approved 2026-06-09 triage). All frontend except one backend line (§9). Every behavior with logic lands as a pure helper in `frontend/src/lib/` with vitest; components consume the helpers. Nothing touches `compute_cell_count`, Excel, or history.

**Tech Stack:** React 18 + Zustand + Tailwind (`po-*` tokens only — never raw palette classes) + Radix + lucide-react; pdf.js (`pdfjs-dist`) via `usePdfDocument`/`PdfPage`; vitest (+ @testing-library/react for components, mocking pdfjs like `DetailPanel.reorgLoop.test.jsx` does); pytest for the one backend change.

**Conventions that bind every task:** `ruff check .` 0 and `cd frontend && npx vitest run` green before each commit; conventional commits in English; work directly on `po_overhaul`; stage named paths only (never `git add -A`); Spanish-neutro microcopy (tú, not vos).

**Task ordering constraint:** the per-cell export button is removed only in Chunk 6 (when the month panel that replaces it exists) — Chunk 1 must NOT touch it, so `ReorganizacionPanel.test.jsx` stays green at every commit.

---

## Chunk 1: Month order, Disclosure primitive, DetailPanel reorder, select-on-focus

### Task 1: Months in chronological order (§9)

**Files:**
- Modify: `api/routes/months.py:48-68` (`list_months`)
- Test: `tests/unit/api/test_months_sort.py` (create)

- [ ] **Step 1: Write the failing test**

`list_months` builds from `sorted(root.iterdir())` — alphabetical folder
names (ABRIL, JUNIO, MAYO). Test the route with a fake root:

```python
"""list_months must return chronological order, not folder-name order (M1)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def months_client(tmp_path, monkeypatch):
    for name in ("ABRIL", "JUNIO", "MAYO", "FEBRERO"):
        (tmp_path / name).mkdir()
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    from api.main import create_app

    with TestClient(create_app()) as c:
        yield c


def test_months_chronological(months_client):
    r = months_client.get("/api/months")
    assert r.status_code == 200
    nums = [m["month"] for m in r.json()["months"]]
    assert nums == sorted(nums), f"months not chronological: {nums}"
    assert nums == [2, 4, 5, 6]
```

Implementer note: check how `_informe_root()` reads its root (env var vs
constant) in `api/routes/months.py` and how existing api tests build a client
(`tests/unit/api/test_cells_routes.py` idiom); adapt the fixture to match —
env override at import time may need `monkeypatch` + reload, or the root may
be injectable. Follow the closest existing test's pattern. **conftest DB
isolation:** api tests must not touch the real `overseer.db` — reuse the
isolation fixture the suite already has (post-incident `501ff34`); confirm
`create_app()` in a test context picks up the isolated `OVERSEER_DB_PATH`.

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/api/test_months_sort.py -v`
Expected: FAIL — `[2, 4, 5, 6] != [4, 6, 5, 2]`-style mismatch (ABRIL, JUNIO, MAYO, FEBRERO alphabetical).

- [ ] **Step 3: Implement (one line)**

In `list_months`, after the loop and before `return`:

```python
    months.sort(key=lambda m: (m["year"], m["month"]))
    return {"months": months}
```

- [ ] **Step 4: Run + commit**

Run: `pytest tests/unit/api/test_months_sort.py -v` → PASS; `pytest -m "not slow" -q` → 0 failures; `ruff check .` → 0.

```bash
git add api/routes/months.py tests/unit/api/test_months_sort.py
git commit -m "fix(api): months list in chronological order (triage M1)"
```

### Task 2: `ui/Disclosure.jsx` primitive

**Files:**
- Create: `frontend/src/ui/Disclosure.jsx`
- Test: `frontend/src/ui/Disclosure.test.jsx` (create)

- [ ] **Step 1: Write the failing test**

```jsx
import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import Disclosure from "./Disclosure";

describe("Disclosure", () => {
  it("renders collapsed by default; toggles content on click", () => {
    render(
      <Disclosure summary="Reorganización · 3 ops">
        <p>contenido</p>
      </Disclosure>,
    );
    expect(screen.queryByText("contenido")).toBeNull();
    fireEvent.click(screen.getByText("Reorganización · 3 ops"));
    expect(screen.getByText("contenido")).toBeTruthy();
  });

  it("summary is a real button (keyboard-accessible by construction)", () => {
    render(<Disclosure summary="S"><p>c</p></Disclosure>);
    expect(screen.getByRole("button", { name: "S" })).toBeTruthy();
  });

  it("defaultOpen=true starts expanded", () => {
    render(
      <Disclosure summary="S" defaultOpen>
        <p>c</p>
      </Disclosure>,
    );
    expect(screen.getByText("c")).toBeTruthy();
  });
});
```

Run: `cd frontend && npx vitest run src/ui/Disclosure.test.jsx` → FAIL (module missing).

- [ ] **Step 2: Implement**

```jsx
import { useState } from "react";
import { ChevronRight } from "lucide-react";

/**
 * Disclosure — collapsible section with a keyboard-accessible summary button.
 *
 * A native <button> (not <details>/<summary>) so Enter/Space work everywhere
 * and screen readers get aria-expanded (the ReorgMenu <summary> A11y lesson).
 *
 * @param {object} props
 * @param {import("react").ReactNode} props.summary - header content.
 * @param {boolean} [props.defaultOpen] - start expanded (default false).
 * @param {import("react").ReactNode} props.children
 */
export default function Disclosure({ summary, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1.5 text-left text-xs font-medium uppercase tracking-wider text-po-text-muted hover:text-po-text transition"
      >
        <ChevronRight
          size={13}
          strokeWidth={2}
          className={["transition-transform", open ? "rotate-90" : ""].join(" ")}
          aria-hidden
        />
        <span className="flex-1 min-w-0">{summary}</span>
      </button>
      {open && <div className="mt-2">{children}</div>}
    </div>
  );
}
```

- [ ] **Step 3: Run + commit**

Run: `cd frontend && npx vitest run src/ui/Disclosure.test.jsx` → PASS.

```bash
git add frontend/src/ui/Disclosure.jsx frontend/src/ui/Disclosure.test.jsx
git commit -m "feat(ui): Disclosure primitive (button-based, aria-expanded)"
```

### Task 3: DetailPanel reorder + collapsible Reorganización (§6)

**Files:**
- Modify: `frontend/src/components/DetailPanel.jsx` (~lines 499-540: section order)
- Test: `frontend/src/components/DetailPanel.reorgLoop.test.jsx` (verify still green; extend if it asserts section order)

- [ ] **Step 1: Read the current section block (lines ~485-540)**

Current order: `Ajuste manual` (inside a conditional) → `<h4>Nota` +
`NotePanel` → `<h4>Reorganización` + `ReorganizacionPanel` →
`WorkerCountModule` + `OrphanMarksPanel` (inside `showsWorkerCounter(...)`) →
`PosiblesColadosPanel`.

- [ ] **Step 2: Reorder + wrap Reorganización in Disclosure**

Move the `showsWorkerCounter(countType)` block (WorkerCountModule +
OrphanMarksPanel, including its comment) to directly AFTER the NotePanel.
Then replace the Reorganización heading + panel with:

```jsx
      <div className="mt-6">
        <Disclosure
          summary={`Reorganización${pendingOpsCount > 0 ? ` · ${pendingOpsCount} op${pendingOpsCount !== 1 ? "s" : ""}` : ""}`}
        >
          <ReorganizacionPanel
            hospital={hospital}
            sigla={sigla}
            ops={reorgOps}
            onDelete={(opId) => deleteReorgOp(sessionId, opId)}
            onExport={() => exportManifest(sessionId)}
            locked={locked}
          />
        </Disclosure>
      </div>
```

with, near the other derivations in the component body:

```jsx
  const pendingOpsCount = reorgOps.filter(
    (op) =>
      (op.status ?? "pending") === "pending" &&
      ((op.source?.hospital === hospital && op.source?.sigla === sigla) ||
        (op.dest?.hospital === hospital && op.dest?.sigla === sigla)),
  ).length;
```

Import `Disclosure` from `"../ui/Disclosure"`. Keep the existing
`WorkerCountModule` comment ("Keep above near-match suspects") truthful —
update it to reflect the new order ("above Reorganización so the counter is
never buried under a growing op list"). **Do NOT touch the export button in
this task** (it moves in Chunk 6).

- [ ] **Step 3: Update the reorgLoop test if it navigates via the heading**

Run: `cd frontend && npx vitest run src/components/DetailPanel.reorgLoop.test.jsx`.
If it fails because "Reorganización" content is now behind the Disclosure,
prepend a `fireEvent.click(screen.getByRole("button", { name: /Reorganización/ }))`
to the flows that reach the panel. Keep assertions otherwise identical.

- [ ] **Step 4: Full vitest + visual sanity**

Run: `cd frontend && npx vitest run` → green.
Run: `cd frontend && npm run build` → OK.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DetailPanel.jsx frontend/src/components/DetailPanel.reorgLoop.test.jsx
git commit -m "feat(web): worker counter above Reorganización; reorg section collapses

DetailPanel order becomes Ajuste manual -> Nota -> Conteo de
trabajadores/chequeos -> Reorganización (Disclosure, collapsed, op-count
badge) -> Posibles colados. The counter no longer sinks under a growing
op list (Daniel 2026-07-08)."
```

### Task 4: Select-on-focus (D1)

**Files:**
- Modify: `frontend/src/components/InlineEditCount.jsx` (the `<input>`)
- Modify: `frontend/src/components/OverridePanel.jsx` (its number input)
- Test: `frontend/src/components/InlineEditCount.test.jsx` (extend/create)

- [ ] **Step 1: Failing test**

```jsx
it("selects the current value on focus so typing overwrites (D1)", () => {
  render(<InlineEditCount value={42} onCommit={() => {}} />);
  fireEvent.click(screen.getByRole("button"));
  const input = screen.getByRole("spinbutton");
  // jsdom: verify the onFocus handler wires select()
  const select = vi.fn();
  input.select = select;
  fireEvent.focus(input);
  expect(select).toHaveBeenCalled();
});
```

Run: `cd frontend && npx vitest run src/components/InlineEditCount.test.jsx` → FAIL.

- [ ] **Step 2: Implement**

`InlineEditCount.jsx` input gains:

```jsx
      onFocus={(e) => e.target.select()}
```

`OverridePanel.jsx`: find its `<input` (the manual-adjust field) and add the
same `onFocus={(e) => e.target.select()}`.

- [ ] **Step 3: Run + commit**

Run: `cd frontend && npx vitest run` → green.

```bash
git add frontend/src/components/InlineEditCount.jsx frontend/src/components/OverridePanel.jsx frontend/src/components/InlineEditCount.test.jsx
git commit -m "feat(web): override inputs select-on-focus (triage D1)"
```

---

## Chunk 2: Rotation straightens the view (§4)

### Task 5: `pageRotation` pure helper

**Files:**
- Create: `frontend/src/lib/page-rotation.js`
- Test: `frontend/src/lib/page-rotation.test.js` (create)

- [ ] **Step 1: Failing tests**

```js
import { describe, it, expect } from "vitest";
import { pageRotation, rotationForPageFn } from "./page-rotation";

const op = (over = {}) => ({
  id: "op_001",
  op_type: "rotate",
  status: "pending",
  rotation_deg: 90,
  source: { hospital: "HRB", sigla: "altura", file: "a.pdf", page_range: null },
  dest: { hospital: "HRB", sigla: "altura" },
  ...over,
});

describe("pageRotation", () => {
  it("no ops → 0", () => {
    expect(pageRotation([], "HRB", "altura", "a.pdf", 1)).toBe(0);
  });

  it("whole-file op (page_range null/missing) rotates every page", () => {
    const ops = [op()];
    expect(pageRotation(ops, "HRB", "altura", "a.pdf", 1)).toBe(90);
    expect(pageRotation(ops, "HRB", "altura", "a.pdf", 99)).toBe(90);
  });

  it("missing page_range key (FileList ReorgMenu shape) = whole file", () => {
    const o = op();
    delete o.source.page_range;
    expect(pageRotation([o], "HRB", "altura", "a.pdf", 3)).toBe(90);
  });

  it("ranged op rotates only covered pages (1-based inclusive)", () => {
    const ops = [op({ source: { hospital: "HRB", sigla: "altura", file: "a.pdf", page_range: [3, 5] } })];
    expect(pageRotation(ops, "HRB", "altura", "a.pdf", 2)).toBe(0);
    expect(pageRotation(ops, "HRB", "altura", "a.pdf", 3)).toBe(90);
    expect(pageRotation(ops, "HRB", "altura", "a.pdf", 5)).toBe(90);
    expect(pageRotation(ops, "HRB", "altura", "a.pdf", 6)).toBe(0);
  });

  it("sums multiple pending ops mod 360", () => {
    const ops = [op(), op({ id: "op_002", rotation_deg: 270 })];
    expect(pageRotation(ops, "HRB", "altura", "a.pdf", 1)).toBe(0); // 90+270
  });

  it("ignores applied ops, other files, other cells, other op types", () => {
    const ops = [
      op({ status: "applied" }),
      op({ id: "x", source: { hospital: "HRB", sigla: "altura", file: "b.pdf" } }),
      op({ id: "y", source: { hospital: "HLU", sigla: "altura", file: "a.pdf" } }),
      op({ id: "z", op_type: "extract_pages" }),
    ];
    expect(pageRotation(ops, "HRB", "altura", "a.pdf", 1)).toBe(0);
  });

  it("missing status counts as pending (store ops may omit it)", () => {
    const o = op();
    delete o.status;
    expect(pageRotation([o], "HRB", "altura", "a.pdf", 1)).toBe(90);
  });
});

describe("rotationForPageFn", () => {
  it("binds ops+cell+file into a page->deg function", () => {
    const fn = rotationForPageFn([op()], "HRB", "altura", "a.pdf");
    expect(fn(1)).toBe(90);
  });
});
```

Run: `cd frontend && npx vitest run src/lib/page-rotation.test.js` → FAIL.

- [ ] **Step 2: Implement**

```js
// Display rotation derived from PENDING rotate reorg-ops (spec §4).
// One source of truth: when paso-1 executes the rotation physically and the
// op retires on the next pase-1 re-scan, the extra rotation drops to 0 and
// the view heals to natural on its own. No view-only rotation state exists.

/**
 * Extra display rotation for one page of a file, from pending rotate ops.
 *
 * @param {object[]} reorgOps - session reorg_ops (any hospital).
 * @param {string} hospital
 * @param {string} sigla
 * @param {string} file - bare filename (op.source.file).
 * @param {number} page - 1-based page number.
 * @returns {0|90|180|270} degrees to add to the page's own /Rotate.
 */
export function pageRotation(reorgOps, hospital, sigla, file, page) {
  let deg = 0;
  for (const op of reorgOps || []) {
    if (op.op_type !== "rotate") continue;
    if ((op.status ?? "pending") !== "pending") continue;
    const src = op.source || {};
    if (src.hospital !== hospital || src.sigla !== sigla || src.file !== file) continue;
    const pr = src.page_range;
    // Missing/null page_range = whole file (the FileList ReorgMenu shape —
    // the only rotate-creation path in common use sends source:{file} bare).
    if (pr != null && (page < pr[0] || page > pr[1])) continue;
    deg += op.rotation_deg || 0;
  }
  return ((deg % 360) + 360) % 360;
}

/** Bind ops+cell+file into a `(page) => deg` for child components (§4 plumbing). */
export function rotationForPageFn(reorgOps, hospital, sigla, file) {
  return (page) => pageRotation(reorgOps, hospital, sigla, file, page);
}
```

- [ ] **Step 3: Run + commit**

Run: `cd frontend && npx vitest run src/lib/page-rotation.test.js` → PASS.

```bash
git add frontend/src/lib/page-rotation.js frontend/src/lib/page-rotation.test.js
git commit -m "feat(web): pageRotation — pending rotate ops -> display degrees"
```

### Task 6: `PdfPage` rotation prop

**Files:**
- Modify: `frontend/src/components/PdfPage.jsx`

- [ ] **Step 1: Add the prop**

`PdfPage({ doc, pageNumber, scale = 1.5, rotation = 0 })`. In the effect:

```js
      const viewport = page.getViewport({
        scale,
        rotation: ((page.rotate ?? 0) + rotation) % 360,
      });
```

(pdf.js: `page.rotate` is the page's own `/Rotate`; passing `rotation` to
`getViewport` REPLACES it, so add the base explicitly.) Add `rotation` to the
effect deps array. Update the JSDoc.

- [ ] **Step 2: Verify no consumer broke**

Run: `cd frontend && npx vitest run` → green (prop defaults to 0 — inert).
Run: `cd frontend && npm run build` → OK.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/PdfPage.jsx
git commit -m "feat(web): PdfPage rotation prop (adds to the page's own /Rotate)"
```

### Task 7: Plumb rotation into the three viewers + thumbnails

**Files:**
- Modify: `frontend/src/components/WorkerCountViewer.jsx`
- Modify: `frontend/src/components/PDFLightbox.jsx`
- Modify: `frontend/src/components/DetailPanel.jsx` (PdfCoverViewer call site)
- Modify: `frontend/src/components/PdfCoverViewer.jsx`
- Modify: `frontend/src/components/WorkerThumbnails.jsx`

- [ ] **Step 1: WorkerCountViewer**

It already selects from the store; add:

```jsx
  const reorgOps = useSessionStore((s) => s.session?.reorg_ops) ?? [];
```

(**Zustand v5 footgun:** the `?? []` default goes OUTSIDE the selector —
never return a fresh literal from the selector itself. Check how DetailPanel
selects `reorgOps` today and copy that exact idiom.) Then at the `PdfPage`
call site (line ~565):

```jsx
              <PdfPage
                doc={doc}
                pageNumber={page}
                scale={effectiveScale}
                rotation={pageRotation(reorgOps, hospital, sigla, currentFile.name, page)}
              />
```

and pass to the thumbnails column:

```jsx
        <WorkerThumbnails
          ...
          rotationForPage={rotationForPageFn(reorgOps, hospital, sigla, currentFile.name)}
        />
```

Import both helpers from `"../lib/page-rotation"`.

- [ ] **Step 2: PDFLightbox**

`InspectView({ url, pageCount })` gains a `rotationForPage = null` prop; its
`PdfPage` call becomes `rotation={rotationForPage ? rotationForPage(page) : 0}`
and its `WorkerThumbnails` gets `rotationForPage={rotationForPage}`. The
parent `PDFLightbox` builds it (it has `lightbox.hospital/sigla`, the current
file name, and the store): pass
`rotationForPage={rotationForPageFn(reorgOps, lightbox.hospital, lightbox.sigla, currentFileName)}`
— read the component to find the current-file variable name at the
`InspectView` call site.

- [ ] **Step 3: PdfCoverViewer + DetailPanel**

`PdfCoverViewer` gains optional `rotation = 0`, passed to its `PdfPage`.
`NearMatchRow`/`NearMatchesSection` in DetailPanel computes
`rotation={pageRotation(reorgOps, hospital, sigla, nm.pdf_name, nm.page_index + 1)}`
at the `PdfCoverViewer` call site (it already has `hospital`/`sigla`/`nm`).

- [ ] **Step 4: WorkerThumbnails rotation-aware cache**

`WorkerThumbnails({ ..., rotationForPage = null })`; each `<Thumb>` receives
`rotation={rotationForPage ? rotationForPage(p) : 0}`. In `Thumb`:

- cache key becomes composite: `const cacheKey = rotation ? `${pageNumber}@${rotation}` : pageNumber;`
  — used for BOTH `cacheFor(doc).get(cacheKey)` and `.set(cacheKey, dataUrl)`
  (an unrotated page keeps the plain numeric key, so existing cache entries
  stay valid).
- the render viewport becomes
  `page.getViewport({ scale: THUMB_WIDTH / base.width, rotation: ((page.rotate ?? 0) + rotation) % 360 })`
  — note `base` must then be computed with the same rotation for the width
  math: `const base = page.getViewport({ scale: 1, rotation: ((page.rotate ?? 0) + rotation) % 360 });`
- add `rotation` to the `useEffect` deps.

- [ ] **Step 5: vitest for the composite key (pure bit)**

The cache-key logic is 1 line inside a component; cover it indirectly via the
`page-rotation` tests (already done) plus a `WorkerThumbnails` render test
ONLY if a pdfjs mock is already available in some test — otherwise skip the
component test (mocking a PDFDocumentProxy for a thumbnail render is not
worth the harness; the live smoke covers it).

- [ ] **Step 6: Gates + commit**

Run: `cd frontend && npx vitest run` → green; `npm run build` → OK.

```bash
git add frontend/src/components/WorkerCountViewer.jsx frontend/src/components/PDFLightbox.jsx frontend/src/components/PdfCoverViewer.jsx frontend/src/components/DetailPanel.jsx frontend/src/components/WorkerThumbnails.jsx
git commit -m "feat(web): pending rotate ops straighten the view everywhere

PdfPage + thumbnails in WorkerCountViewer, PDFLightbox InspectView and
PdfCoverViewer apply pageRotation() from pending rotate ops. Thumb cache
key gains the rotation term. When paso-1 applies the op physically and it
retires on re-scan, the view heals to natural (spec §4)."
```

---

## Chunk 3: Viewer performance (§1)

### Task 8: `prerenderOrder` + tiny LRU (pure)

**Files:**
- Create: `frontend/src/lib/page-cache.js`
- Test: `frontend/src/lib/page-cache.test.js` (create)

- [ ] **Step 1: Failing tests**

```js
import { describe, it, expect } from "vitest";
import { prerenderOrder, LruCache } from "./page-cache";

describe("prerenderOrder", () => {
  it("orders ±1 then ±2, clamped", () => {
    expect(prerenderOrder(5, 100)).toEqual([6, 4, 7, 3]);
  });
  it("clamps at the start", () => {
    expect(prerenderOrder(1, 100)).toEqual([2, 3]);
  });
  it("clamps at the end", () => {
    expect(prerenderOrder(100, 100)).toEqual([99, 98]);
  });
  it("single page → empty", () => {
    expect(prerenderOrder(1, 1)).toEqual([]);
  });
  it("radius param respected", () => {
    expect(prerenderOrder(5, 100, 1)).toEqual([6, 4]);
  });
});

describe("LruCache", () => {
  it("evicts least-recently-used beyond capacity, calling onEvict", () => {
    const evicted = [];
    const c = new LruCache(2, (v) => evicted.push(v));
    c.set("a", 1);
    c.set("b", 2);
    c.get("a"); // refresh a
    c.set("c", 3); // evicts b
    expect(c.get("b")).toBeUndefined();
    expect(c.get("a")).toBe(1);
    expect(evicted).toEqual([2]);
  });
  it("clear() evicts everything", () => {
    const evicted = [];
    const c = new LruCache(4, (v) => evicted.push(v));
    c.set("a", 1);
    c.set("b", 2);
    c.clear();
    expect(evicted.sort()).toEqual([1, 2]);
    expect(c.get("a")).toBeUndefined();
  });
});
```

Run: `cd frontend && npx vitest run src/lib/page-cache.test.js` → FAIL.

- [ ] **Step 2: Implement**

```js
// Viewer page cache (spec §1): pre-render window + bounded LRU.
// Pure/pdfjs-free so it is unit-testable; PdfPage owns the pdfjs wiring.

/**
 * Pages to pre-render around the current one: ±1 first, then ±2 … ±radius,
 * clamped to [1, pageCount], current excluded.
 *
 * @param {number} current - 1-based current page.
 * @param {number} pageCount
 * @param {number} [radius] - window half-width (default 2).
 * @returns {number[]} pages in priority order.
 */
export function prerenderOrder(current, pageCount, radius = 2) {
  const order = [];
  for (let d = 1; d <= radius; d++) {
    if (current + d <= pageCount) order.push(current + d);
    if (current - d >= 1) order.push(current - d);
  }
  return order;
}

/** Tiny LRU keyed by string; onEvict lets callers close() ImageBitmaps. */
export class LruCache {
  constructor(capacity, onEvict = null) {
    this.capacity = capacity;
    this.onEvict = onEvict;
    this.map = new Map(); // Map preserves insertion order → LRU via delete+set
  }

  get(key) {
    if (!this.map.has(key)) return undefined;
    const v = this.map.get(key);
    this.map.delete(key);
    this.map.set(key, v);
    return v;
  }

  set(key, value) {
    if (this.map.has(key)) this.map.delete(key);
    this.map.set(key, value);
    if (this.map.size > this.capacity) {
      const [oldestKey, oldestVal] = this.map.entries().next().value;
      this.map.delete(oldestKey);
      this.onEvict?.(oldestVal);
    }
  }

  clear() {
    for (const v of this.map.values()) this.onEvict?.(v);
    this.map.clear();
  }
}
```

- [ ] **Step 3: Run + commit**

Run: `cd frontend && npx vitest run src/lib/page-cache.test.js` → PASS.

```bash
git add frontend/src/lib/page-cache.js frontend/src/lib/page-cache.test.js
git commit -m "feat(web): prerenderOrder + LruCache (viewer perf foundation)"
```

### Task 9: PdfPage renders through the cache + placeholder + pre-render

**Files:**
- Modify: `frontend/src/components/PdfPage.jsx` (full rewrite of the effect)
- Modify: `frontend/src/components/WorkerThumbnails.jsx` (export a thumb getter)

- [ ] **Step 1: Export the thumbnail getter**

In `WorkerThumbnails.jsx`, next to `cacheFor`:

```js
/** Read-only peek for PdfPage's instant placeholder (spec §1). */
export function getCachedThumb(doc, pageNumber) {
  return THUMB_CACHE.get(doc)?.get(pageNumber) ?? null;
}
```

(Plain `pageNumber` key = the unrotated thumb; a slightly stale-orientation
placeholder for a rotated page is acceptable for the ~100 ms it lives.)

- [ ] **Step 2: Rewrite PdfPage**

Complete new implementation (replaces the current effect wholesale — keep the
file's JSDoc style):

```jsx
import { useEffect, useRef, useState } from "react";
import { LruCache, prerenderOrder } from "../lib/page-cache";
import { getCachedThumb } from "./WorkerThumbnails";

// Per-document render cache: WeakMap<doc, LruCache>. Key `page@scale@rot`;
// value ImageBitmap (or HTMLCanvasElement fallback). Capacity 6 ≈ the ±2
// window + current at one scale, with slack for a zoom change.
const RENDER_CACHE = new WeakMap();
const CACHE_CAPACITY = 6;

function cacheFor(doc) {
  let c = RENDER_CACHE.get(doc);
  if (!c) {
    c = new LruCache(CACHE_CAPACITY, (bmp) => bmp?.close?.());
    RENDER_CACHE.set(doc, c);
  }
  return c;
}

const keyFor = (page, scale, rotation) => `${page}@${scale}@${rotation}`;

async function renderToBitmap(doc, pageNumber, scale, rotation) {
  const page = await doc.getPage(pageNumber);
  try {
    const viewport = page.getViewport({
      scale,
      rotation: ((page.rotate ?? 0) + rotation) % 360,
    });
    const canvas = document.createElement("canvas");
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
    if (typeof createImageBitmap === "function") {
      const bmp = await createImageBitmap(canvas);
      canvas.width = 0; // release backing store eagerly
      return bmp;
    }
    return canvas; // jsdom / old browsers: drawImage accepts canvases too
  } finally {
    page.cleanup();
  }
}

/**
 * Renderiza una página de un PDF a un canvas, con caché LRU por documento,
 * placeholder instantáneo desde la miniatura y pre-render de la ventana ±2.
 *
 * @param {object} props
 * @param {object} props.doc - PDFDocumentProxy de usePdfDocument.
 * @param {number} props.pageNumber - número de página, 1-indexado.
 * @param {number} [props.scale] - escala de render (1.5 por defecto).
 * @param {number} [props.rotation] - grados extra sobre el /Rotate propio (§4).
 */
export function PdfPage({ doc, pageNumber, scale = 1.5, rotation = 0 }) {
  const canvasRef = useRef(null);
  const [placeholder, setPlaceholder] = useState(null);

  useEffect(() => {
    if (!doc) return undefined;
    let cancelled = false;
    const cache = cacheFor(doc);

    const draw = (bmp) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      canvas.width = bmp.width;
      canvas.height = bmp.height;
      canvas.getContext("2d").drawImage(bmp, 0, 0);
      setPlaceholder(null);
    };

    const cached = cache.get(keyFor(pageNumber, scale, rotation));
    if (cached) {
      draw(cached); // synchronous hit — no flash
    } else {
      // Instant placeholder from the thumbnail cache while the real render runs.
      setPlaceholder(getCachedThumb(doc, pageNumber));
      renderToBitmap(doc, pageNumber, scale, rotation)
        .then((bmp) => {
          if (cancelled) {
            bmp?.close?.();
            return;
          }
          cache.set(keyFor(pageNumber, scale, rotation), bmp);
          draw(bmp);
        })
        .catch(() => {}); // RenderingCancelledException / detached doc
    }

    // Pre-render window, low priority, after the current page settled.
    const idle = window.requestIdleCallback ?? ((fn) => setTimeout(fn, 150));
    const cancelIdle = window.cancelIdleCallback ?? clearTimeout;
    const handle = idle(async () => {
      const total = doc.numPages ?? 0;
      for (const p of prerenderOrder(pageNumber, total)) {
        if (cancelled) return;
        const k = keyFor(p, scale, rotation);
        if (cache.get(k)) continue;
        try {
          const bmp = await renderToBitmap(doc, p, scale, rotation);
          if (cancelled) {
            bmp?.close?.();
            return;
          }
          cache.set(k, bmp);
        } catch {
          return; // doc closed mid-prerender — stop quietly
        }
      }
    });

    return () => {
      cancelled = true;
      cancelIdle(handle);
    };
  }, [doc, pageNumber, scale, rotation]);

  return (
    <div className="relative">
      {placeholder && (
        <img
          src={placeholder}
          alt=""
          aria-hidden
          className="absolute inset-0 h-full w-full blur-[2px] opacity-70"
        />
      )}
      <canvas ref={canvasRef} className="block max-w-full shadow-sm ring-1 ring-po-border" />
    </div>
  );
}
```

Implementation caveats the implementer must honor:
- **Pre-render uses the window rotation** (same `rotation` value) — correct
  for whole-file ops; a per-page-range op makes a neighbor's pre-render key
  miss and re-render on arrival, which is acceptable (correctness first).
  If the caller passes a `rotation` that varies per page (WorkerCountViewer
  does, via `pageRotation(page)`), the neighbor keys may be pre-rendered at
  the current page's rotation. To keep it simple and correct, pre-rendered
  entries are keyed by the rotation they were rendered WITH — a mismatched
  key is a cache miss, never a wrong image.
- Keep `page.cleanup()` inside `renderToBitmap` (memory discipline from the
  old implementation).
- jsdom has no `createImageBitmap`/`requestIdleCallback` — both have
  fallbacks above, so existing component tests keep passing.

- [ ] **Step 3: Gates**

Run: `cd frontend && npx vitest run` → green (PdfCoverViewer/DetailPanel tests
mock pdfjs already; if any test rendered PdfPage with a mock doc lacking
`numPages`, the pre-render loop no-ops on `total = 0`).
Run: `cd frontend && npm run build` → OK.

- [ ] **Step 4: Manual perf check (dev server)**

With the backend + `npm run dev` up, open a big PDF in the lightbox and flip
pages quickly: revisited pages must appear instantly (cache hit), fresh pages
must show the blurred thumbnail placeholder first. This is a keep-honest
check before the Chunk 6 smoke, not a gate.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/PdfPage.jsx frontend/src/components/WorkerThumbnails.jsx
git commit -m "feat(web): viewer page cache + prerender window + thumb placeholder

PdfPage renders through a per-doc LRU (6 ImageBitmaps), pre-renders
current±2 on idle, and shows the cached thumbnail blurred while a cold
page renders. Revisited pages draw synchronously (spec §1 — the
'lentísimo' fix)."
```

---

## Chunk 4: Thumbnails +20% / centered (§2) + navigation (§3)

### Task 10: Thumbnails +20% and centered

**Files:**
- Modify: `frontend/src/components/WorkerThumbnails.jsx`

- [ ] **Step 1: Apply the three changes**

- `const THUMB_WIDTH = 110;` (was 92) — comment: `// px de ancho del raster (+20%, triage I1)`
- column classes: both `<aside>` returns `w-28` → `w-32`.
- autoscroll: `currentRef.current?.scrollIntoView({ block: "center" });` (was `"nearest"`, triage I2).

- [ ] **Step 2: Gates + commit**

Run: `cd frontend && npx vitest run` → green; `npm run build` → OK.

```bash
git add frontend/src/components/WorkerThumbnails.jsx
git commit -m "feat(web): thumbnails +20% and center the active page (I1+I2)"
```

### Task 11: WorkerCountViewer input-focus guard (NEW work — spec §3)

**Files:**
- Modify: `frontend/src/components/WorkerCountViewer.jsx` (`keyHandler.current`, ~line 503)

- [ ] **Step 1: Build the guard**

`keyHandler.current` currently captures every key unconditionally (its own
comment says the viewer has no inputs — Tasks 12/19 are about to add them).
First lines become:

```jsx
  keyHandler.current = (e) => {
    // §3 guard (NEW in this round): the viewer now hosts inputs ("Ir a pág.",
    // calculator). While one has focus, counting/nav shortcuts are inert —
    // typing "12" in a field must NOT feed the count buffer.
    const el = document.activeElement;
    if (el?.tagName === "INPUT" || el?.tagName === "TEXTAREA" || el?.isContentEditable) return;
    if (mode === "reorg") return;
    ...
```

Also update the now-false comment above the handler (lines ~498-500): the
viewer DOES have inputs from this round on; the guard is what keeps capture
safe.

- [ ] **Step 2: Gates + commit**

Run: `cd frontend && npx vitest run` → green.

```bash
git add frontend/src/components/WorkerCountViewer.jsx
git commit -m "feat(web): input-focus guard in the worker viewer key handler

Prereq for Ir-a-página + calculator: digits typed into an input can no
longer feed the count buffer (spec §3 — this guard did NOT exist here,
only in PDFLightbox)."
```

### Task 12: Shift±10 + "Ir a página" in both viewers

**Files:**
- Modify: `frontend/src/components/WorkerCountViewer.jsx`
- Modify: `frontend/src/components/PDFLightbox.jsx` (`InspectView`)
- Create: `frontend/src/lib/go-to-page.js` + `frontend/src/lib/go-to-page.test.js`

- [ ] **Step 1: Pure clamp helper + failing tests**

`go-to-page.js`:

```js
/** Parse an "Ir a página" input: integer clamped to [1, pageCount]; null if unusable. */
export function parseGoToPage(raw, pageCount) {
  const n = Number(raw);
  if (!Number.isInteger(n) || pageCount < 1) return null;
  return Math.min(Math.max(n, 1), pageCount);
}
```

Tests: `"7"→7`, `"0"→1`, `"999"→pageCount`, `"abc"→null`, `""→null`,
`pageCount=0→null`. Run vitest → FAIL → implement → PASS.

- [ ] **Step 2: WorkerCountViewer — Shift+PageDown/Up = ±10**

In `keyHandler.current`, BEFORE the existing PageDown/PageUp branches:

```jsx
    if (e.key === "PageDown" && e.shiftKey) { e.preventDefault(); setPageInFile(Math.min(page + 10, pageCount)); return; }
    if (e.key === "PageUp" && e.shiftKey) { e.preventDefault(); setPageInFile(Math.max(page - 10, 1)); return; }
```

(Shift only jumps within the current file — it never fixes counts and never
crosses files; plain PageDown keeps fix-and-advance.)

- [ ] **Step 3: WorkerCountViewer — "Ir a pág." input**

Add to the zoom cluster overlay (the `absolute bottom-3 right-3` div, ~line
572), before the zoom buttons:

```jsx
            <input
              type="number"
              inputMode="numeric"
              placeholder="Ir a pág."
              aria-label="Ir a página"
              className="w-20 rounded border border-po-border bg-po-panel px-1.5 py-0.5 text-xs text-po-text placeholder-po-text-subtle focus:outline-none focus:ring-1 focus:ring-po-accent"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  const p = parseGoToPage(e.currentTarget.value, pageCount);
                  if (p != null) { setPageInFile(p); e.currentTarget.value = ""; e.currentTarget.blur(); }
                } else if (e.key === "Escape") {
                  e.currentTarget.blur();
                }
                e.stopPropagation();
              }}
            />
```

(`e.stopPropagation()` is belt-and-suspenders on top of the Task 11 guard —
the window listener still fires first on keydown capture order; the guard is
the real protection, verified in the test below.)

- [ ] **Step 4: InspectView (PDFLightbox) — same two features**

In its `onKey` handler add the Shift branches (using `clampPage(p ± 10)`), and
add the same input next to its zoom cluster with `setPage(p)`. Its existing
activeElement guard already covers focus isolation.

- [ ] **Step 5: Guard collision test (the §10 required test)**

In a new `frontend/src/components/WorkerCountViewer.guard.test.jsx`, mock
pdfjs like `DetailPanel.reorgLoop.test.jsx` does (stub `usePdfDocument` to
return `{doc: null}` and stub child components as needed) OR — cheaper and
sufficient — test the guard logic itself: render the viewer is heavy, so if
mocking proves disproportionate, extract the guard predicate to
`lib/keyboard-focus.js`:

```js
export function focusIsInInput(el = document.activeElement) {
  return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
}
```

vitest it directly (jsdom: create an input, focus it, assert true; body →
false), and use it in BOTH viewers' handlers. Prefer this extraction — one
predicate, two consumers, trivially tested.

- [ ] **Step 6: Gates + commit**

Run: `cd frontend && npx vitest run` → green; `npm run build` → OK.

```bash
git add frontend/src/lib/go-to-page.js frontend/src/lib/go-to-page.test.js frontend/src/lib/keyboard-focus.js frontend/src/lib/keyboard-focus.test.js frontend/src/components/WorkerCountViewer.jsx frontend/src/components/PDFLightbox.jsx
git commit -m "feat(web): Shift+PageDown/Up = ±10 + Ir-a-página in both viewers (I4+I5)"
```

### Task 13: Near-match viewer prev/next (I6)

**Files:**
- Modify: `frontend/src/components/PdfCoverViewer.jsx`
- Modify: `frontend/src/components/DetailPanel.jsx` (`NearMatchesSection` + `NearMatchRow`)

- [ ] **Step 1: PdfCoverViewer optional nav props**

Props gain `onPrev = null, onNext = null, positionLabel = null`. In the
header, after the title span:

```jsx
          {positionLabel && (
            <span className="shrink-0 text-xs tabular-nums text-po-text-muted">{positionLabel}</span>
          )}
          {(onPrev || onNext) && (
            <span className="flex shrink-0 items-center gap-1">
              <button type="button" disabled={!onPrev} onClick={onPrev ?? undefined} aria-label="Casi-match anterior" className="rounded p-1 text-po-text-muted hover:text-po-text disabled:opacity-40">
                <ChevronLeft size={16} strokeWidth={1.75} />
              </button>
              <button type="button" disabled={!onNext} onClick={onNext ?? undefined} aria-label="Casi-match siguiente" className="rounded p-1 text-po-text-muted hover:text-po-text disabled:opacity-40">
                <ChevronRight size={16} strokeWidth={1.75} />
              </button>
            </span>
          )}
```

(import `ChevronLeft, ChevronRight` from lucide.) ArrowLeft/ArrowRight while
open: add a `useEffect` keydown listener gated on `open` that calls
`onPrev`/`onNext` when provided (and respects `focusIsInInput()` from Task 12).
Single-page usage (no props) renders exactly as today.

- [ ] **Step 2: Lift viewer state in NearMatchesSection**

Today each `NearMatchRow` owns `viewerOpen` for its own single page. Lift:
`NearMatchesSection` holds `const [viewerIndex, setViewerIndex] = useState(null);`
renders ONE `PdfCoverViewer` for `nearMatches[viewerIndex]` with
`positionLabel={`${viewerIndex + 1} de ${nearMatches.length}`}`,
`onPrev={viewerIndex > 0 ? () => setViewerIndex(viewerIndex - 1) : null}`,
`onNext={viewerIndex < nearMatches.length - 1 ? () => setViewerIndex(viewerIndex + 1) : null}`;
each row's "Ver portada" button becomes `onClick={() => setViewerIndex(i)}`.
Move the `pdfUrl` derivation (from `nm`) up with it — read the current row
code and keep the URL construction identical. Rotation from Task 7 rides
along (recompute for the active `nm`).

- [ ] **Step 3: Gates + commit**

Run: `cd frontend && npx vitest run` → green; `npm run build` → OK.

```bash
git add frontend/src/components/PdfCoverViewer.jsx frontend/src/components/DetailPanel.jsx
git commit -m "feat(web): near-match viewer gains prev/next + 'N de M' (I6)"
```

---

## Chunk 5: FileList (§5)

### Task 14: Chip filter bar (E2)

**Files:**
- Create: `frontend/src/lib/file-filters.js` + `frontend/src/lib/file-filters.test.js`
- Modify: `frontend/src/components/FileList.jsx`

- [ ] **Step 1: Pure predicate + failing tests**

`file-filters.js`:

```js
// FileList chip filters (triage E2): search text AND origin-chip toggles.
// Empty origin selection = no origin filter (today's behavior).

export const FILTER_ORIGINS = ["R1", "RN", "OCR", "Manual", "Pendiente", "Revisar", "Error"];

/**
 * @param {{name: string, origin?: string}} file
 * @param {string} search - substring, case-insensitive, against file.name.
 * @param {string[]} activeOrigins - selected chips (empty = all).
 */
export function matchesFilters(file, search, activeOrigins) {
  if (search && !file.name.toLowerCase().includes(search.toLowerCase())) return false;
  if (activeOrigins.length > 0 && !activeOrigins.includes(file.origin ?? "R1")) return false;
  return true;
}
```

Tests: search-only (case-insensitive), origins-only, AND of both, empty
selection passes everything, missing `origin` defaults to `"R1"` (mirroring
the row's `<OriginChip origin={f.origin ?? "R1"} />`). Run → FAIL → implement
→ PASS.

- [ ] **Step 2: Wire the bar into FileList**

State: `const [activeOrigins, setActiveOrigins] = useState([]);`. Replace the
`filtered` derivation (line ~285):

```jsx
  const filtered = files.filter((f) => matchesFilters(f, search, activeOrigins));
```

Under the search `<div>` (after line ~325), the chip bar:

```jsx
      <div className="flex flex-wrap gap-1 border-b border-po-border px-2 py-1.5">
        {FILTER_ORIGINS.map((o) => {
          const active = activeOrigins.includes(o);
          return (
            <button
              key={o}
              type="button"
              aria-pressed={active}
              onClick={() =>
                setActiveOrigins((prev) =>
                  prev.includes(o) ? prev.filter((x) => x !== o) : [...prev, o],
                )
              }
              className={[
                "rounded-full border px-2 py-0.5 text-[11px] transition",
                active
                  ? "border-po-accent bg-po-accent/10 text-po-accent"
                  : "border-po-border text-po-text-muted hover:border-po-border-strong",
              ].join(" ")}
            >
              {o}
            </button>
          );
        })}
      </div>
```

- [ ] **Step 3: Gates + commit**

Run: `cd frontend && npx vitest run` → green; `npm run build` → OK.

```bash
git add frontend/src/lib/file-filters.js frontend/src/lib/file-filters.test.js frontend/src/components/FileList.jsx
git commit -m "feat(web): FileList origin-chip filter bar, AND-combined with search (E2)"
```

### Task 15: docs≠pages subtle highlight (E3)

**Files:**
- Modify: `frontend/src/components/FileList.jsx` (the count cell)
- Create/extend: `frontend/src/lib/file-filters.test.js` (the predicate lives with the filters)

- [ ] **Step 1: Pure predicate (in `file-filters.js`) + tests**

```js
/** E3: subtle cue when a file's effective doc count differs from its pages.
 *  Doc-counting cells only (documents / documents_workers) — checks excluded. */
export function countDiffersFromPages(file, countType) {
  if (countType !== "documents" && countType !== "documents_workers") return false;
  if (file.effective_count == null || file.page_count == null) return false;
  return file.effective_count !== file.page_count;
}
```

Tests: differs → true; equal → false; null count (Pendiente) → false; checks
countType → false. Run → FAIL → implement → PASS.

- [ ] **Step 2: Apply the tint in the count cell**

The count renders via `InlineEditCount` (editable branch, line ~372) and a
plain `<span>` (checks branch). Only the editable branch changes: wrap it —

```jsx
                return (
                  <span className={countDiffersFromPages(f, scanInfo?.count_type) ? "[&_button]:text-po-suspect" : ""}>
                    <InlineEditCount ... />
                  </span>
                );
```

(the `[&_button]` arbitrary variant tints InlineEditCount's display button
without threading a new prop; the input while editing keeps normal colors).
If the arbitrary-variant approach fights the existing classes, add an
optional `tone` prop to `InlineEditCount` instead — implementer's choice,
same visual outcome: **subtle text-tone change, no background** (triage E3).

- [ ] **Step 3: Gates + commit**

Run: `cd frontend && npx vitest run` → green; `npm run build` → OK.

```bash
git add frontend/src/lib/file-filters.js frontend/src/lib/file-filters.test.js frontend/src/components/FileList.jsx
git commit -m "feat(web): subtle tint when a file's count differs from its pages (E3)"
```

### Task 16: Keep scroll position on per-file save (E1 — verify first)

**Files:**
- Possibly modify: `frontend/src/components/FileList.jsx`

- [ ] **Step 1: Reproduce**

Dev server up, open a cell with >20 files, scroll the list, edit a count
mid-list, save (Enter). Watch whether the `<ul>` scroll resets to top.
Likely mechanism if it does: the optimistic `setFiles(prev.map(...))` keeps
identity, but the post-save `filesTick` refetch replaces the array → keys are
`` `${f.name}-${i}` `` (stable) so React should preserve DOM… verify honestly.

- [ ] **Step 2A (reproduces): fix by preserving scrollTop across refetch**

Capture the `<ul>` node with a ref; in the effect that re-fetches on
`filesTick`, snapshot `ulRef.current?.scrollTop` before `setFiles(...)` and
restore it in a `useLayoutEffect` after the new list renders (guard: only
when the file set is unchanged). Keep it minimal — no scroll-anchoring
library.

- [ ] **Step 2B (does not reproduce): close the item**

Record in the commit message (or the round notes) that E1 did not reproduce
on the current code — the triage marked it *(verificar)* — and make no change.

- [ ] **Step 3: Commit (whichever branch)**

```bash
git add frontend/src/components/FileList.jsx
git commit -m "fix(web): FileList keeps scroll position across per-file save (E1)"
# or, if 2B:
git commit --allow-empty -m "docs(web): E1 scroll-reset did not reproduce — closed without change"
```

### Task 17: Per-file steppers (D2)

**Files:**
- Modify: `frontend/src/components/FileList.jsx` (count cell)
- Test: extend `frontend/src/components/InlineEditCount.test.jsx` only if logic lands there (it does not — steppers are FileList-side)

- [ ] **Step 1: Add − / + beside the count (editable branch only)**

In the count cell `<div>`, alongside `InlineEditCount`:

```jsx
              <span className="inline-flex items-center gap-0.5">
                <button
                  type="button"
                  aria-label="Restar un documento"
                  disabled={locked || (value ?? 0) <= 0}
                  onClick={() => commitStep(-1)}
                  className="rounded px-1 text-po-text-muted hover:text-po-text disabled:opacity-30"
                >
                  −
                </button>
                <InlineEditCount ... />
                <button
                  type="button"
                  aria-label="Sumar un documento"
                  disabled={locked}
                  onClick={() => commitStep(+1)}
                  className="rounded px-1 text-po-text-muted hover:text-po-text disabled:opacity-30"
                >
                  +
                </button>
              </span>
```

with, in the same IIFE scope (it already has `f`, `value`):

```jsx
                const commitStep = (d) => {
                  const next = Math.max(0, (value ?? 0) + d);
                  // Same path as typing: optimistic row update + store save.
                  setFiles((prev) =>
                    prev.map((row) =>
                      row.name === f.name
                        ? { ...row, effective_count: next, override_count: next, origin: "Manual" }
                        : row,
                    ),
                  );
                  savePerFileOverride(session.session_id, hospital, sigla, f.name, next);
                };
```

No cap logic here: the override path owns the cap (the conteo-session-fixes
round adds its confirmation there; `+` past the cap will surface whatever
that path does — today, for `+1` above pages, the backend 422s and the store
toasts, which is acceptable until that round lands).

- [ ] **Step 2: Gates + commit**

Run: `cd frontend && npx vitest run` → green; `npm run build` → OK.

```bash
git add frontend/src/components/FileList.jsx
git commit -m "feat(web): always-visible −/+ steppers on the per-file count (D2)"
```

---

## Chunk 6: Month manifest panel (§7), calculator (§8), round close

### Task 18: "Reorganización del mes" panel + single export surface

**Files:**
- Create: `frontend/src/components/MonthReorgPanel.jsx`
- Create: `frontend/src/components/MonthReorgPanel.test.jsx`
- Modify: `frontend/src/views/MonthOverview.jsx` (header button)
- Modify: `frontend/src/components/ReorganizacionPanel.jsx` (remove export button)
- Modify: `frontend/src/components/ReorganizacionPanel.test.jsx` (migrate export assertions)

- [ ] **Step 1: Failing tests for the new panel**

`MonthReorgPanel.test.jsx` (mock nothing heavy — the panel is pure props +
store actions passed in):

```jsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import MonthReorgPanel from "./MonthReorgPanel";

const ops = [
  { id: "op_1", op_type: "rotate", status: "pending", rotation_deg: 90,
    source: { hospital: "HRB", sigla: "altura", file: "a.pdf" },
    dest: { hospital: "HRB", sigla: "altura" } },
  { id: "op_2", op_type: "move_file", status: "applied", doc_count: 2,
    source: { hospital: "HLU", sigla: "art", file: "b.pdf" },
    dest: { hospital: "HLU", sigla: "odi" } },
];

describe("MonthReorgPanel", () => {
  it("groups pending ops by cell and hides applied ones", () => {
    render(<MonthReorgPanel open ops={ops} onClose={() => {}} onDelete={() => {}} onExport={() => {}} />);
    expect(screen.getByText(/HRB · altura/)).toBeTruthy();
    expect(screen.queryByText(/HLU · art/)).toBeNull(); // applied → hidden
  });

  it("export button present and enabled with pending ops", () => {
    render(<MonthReorgPanel open ops={ops} onClose={() => {}} onDelete={() => {}} onExport={() => {}} />);
    const btn = screen.getByTestId("export-btn");
    expect(btn).toBeTruthy();
    expect(btn.disabled).toBe(false);
  });

  it("no pending ops → empty state + disabled export", () => {
    render(<MonthReorgPanel open ops={[ops[1]]} onClose={() => {}} onDelete={() => {}} onExport={() => {}} />);
    expect(screen.getByText(/Sin operaciones pendientes/)).toBeTruthy();
    expect(screen.getByTestId("export-btn").disabled).toBe(true);
  });
});
```

Run → FAIL (module missing).

- [ ] **Step 2: Implement the panel**

Radix dialog (follow `PdfCoverViewer.jsx`'s RadixDialog skeleton — overlay +
content + Title + Close), listing pending ops grouped by
`` `${source.hospital} · ${source.sigla}` `` (group key = the SOURCE cell;
show dest inline per row). Reuse `OpRow` from `ReorganizacionPanel.jsx` if
exportable — check whether `OpRow` is a module-level function there; if it is
not exported, export it (named) rather than duplicating row rendering. Footer:

```jsx
        <footer className="border-t border-po-border px-5 py-3 flex justify-end">
          <Button variant="secondary" icon={Download} size="sm" disabled={!hasPending} onClick={onExport} data-testid="export-btn">
            Exportar manifiesto
          </Button>
        </footer>
```

Empty state text: `Sin operaciones pendientes`.

- [ ] **Step 3: Header wiring in MonthOverview**

Next to "Generar Excel del mes" (~line 118):

```jsx
              <Button
                icon={FolderSync}
                disabled={loading}
                onClick={() => setReorgPanelOpen(true)}
              >
                Reorganización{pendingOpsTotal > 0 ? ` (${pendingOpsTotal})` : ""}
              </Button>
```

with `const reorgOps = useSessionStore((s) => s.session?.reorg_ops) ?? [];`
(Zustand v5: default OUTSIDE the selector), `pendingOpsTotal = reorgOps.filter((op) => (op.status ?? "pending") === "pending").length`,
local `reorgPanelOpen` state, and the panel mounted with
`onDelete={(opId) => deleteReorgOp(sessionId, opId)}` /
`onExport={() => exportManifest(sessionId)}` (both actions already exist in
the store — check their exact names at `store/session.js:771/819` region).
Pick a sensible lucide icon (`FolderSync` or `FileOutput` — whatever exists
in the installed lucide version; verify the import builds).

- [ ] **Step 4: Move the export button OUT of the per-cell panel**

In `ReorganizacionPanel.jsx`: delete the `<Button ... data-testid="export-btn">`
block and the `canExport` derivation; drop the now-unused `onExport` prop and
`Download` import. In `DetailPanel.jsx`: remove `onExport={...}` from the
`ReorganizacionPanel` call site (inside the Task 3 Disclosure).

In `ReorganizacionPanel.test.jsx`: the export assertions (including the
locked-state "export stays enabled" test around lines 178-194) change to
assert **absence**: `expect(container.querySelector('[data-testid="export-btn"]')).toBeNull();`.
The presence+enabled semantics now live in `MonthReorgPanel.test.jsx` (Step 1).

- [ ] **Step 5: Gates + commit**

Run: `cd frontend && npx vitest run` → green; `npm run build` → OK.

```bash
git add frontend/src/components/MonthReorgPanel.jsx frontend/src/components/MonthReorgPanel.test.jsx frontend/src/views/MonthOverview.jsx frontend/src/components/ReorganizacionPanel.jsx frontend/src/components/ReorganizacionPanel.test.jsx frontend/src/components/DetailPanel.jsx
git commit -m "feat(web): month-level Reorganización panel = the ONE export surface

Header button (pending-op badge) opens a dialog listing every pending op
grouped by source cell, with delete + the single Exportar manifiesto
button. The per-cell panel keeps list/delete/delta but loses its export
(Daniel 2026-07-08: 'un solo lugar donde exporte todos los cambios')."
```

### Task 19: Collapsible calculator (§8)

**Files:**
- Create: `frontend/src/lib/calc.js` + `frontend/src/lib/calc.test.js`
- Modify: `frontend/src/components/WorkerHud.jsx` (right column host)

- [ ] **Step 1: Pure evaluator + failing tests**

`calc.js` — recursive-descent, no `eval`:

```js
// Minimal arithmetic evaluator for the viewer calculator (triage I8).
// Grammar: expr := term (('+'|'-') term)* ; term := factor (('*'|'/') factor)* ;
// factor := number | '(' expr ')' | '-' factor. No eval(), ever.

export function evaluate(input) {
  const s = String(input).replace(/\s+/g, "");
  if (!s) return null;
  let i = 0;

  function number() {
    const start = i;
    while (i < s.length && /[0-9.]/.test(s[i])) i++;
    if (start === i) return NaN;
    const n = Number(s.slice(start, i));
    return Number.isFinite(n) ? n : NaN;
  }

  function factor() {
    if (s[i] === "-") { i++; return -factor(); }
    if (s[i] === "(") {
      i++;
      const v = expr();
      if (s[i] !== ")") return NaN;
      i++;
      return v;
    }
    return number();
  }

  function term() {
    let v = factor();
    while (s[i] === "*" || s[i] === "/") {
      const op = s[i++];
      const r = factor();
      v = op === "*" ? v * r : v / r;
    }
    return v;
  }

  function expr() {
    let v = term();
    while (s[i] === "+" || s[i] === "-") {
      const op = s[i++];
      const r = term();
      v = op === "+" ? v + r : v - r;
    }
    return v;
  }

  const v = expr();
  if (i !== s.length || Number.isNaN(v) || !Number.isFinite(v)) return null;
  return v;
}
```

Tests: `"2+3*4"→14`, `"(2+3)*4"→20`, `"10/4"→2.5`, `"-3+5"→2`, `"1.5*2"→3`,
`"2++2"→null`, `"(2"→null`, `"abc"→null`, `""→null`, `"8/0"→null` (Infinity
filtered). Run → FAIL → implement → PASS.

- [ ] **Step 2: Host it in the HUD right column**

Read `WorkerHud.jsx` first; append at its bottom a collapsed-by-default
`Disclosure` (Task 2 primitive):

```jsx
      <Disclosure summary="Calculadora">
        <CalcBar />
      </Disclosure>
```

`CalcBar` (local to WorkerHud or a small `Calculator.jsx` next to it —
implementer's choice by file size; WorkerHud is the host either way):

```jsx
function CalcBar() {
  const [expr, setExpr] = useState("");
  const result = evaluate(expr);
  return (
    <div className="space-y-1">
      <input
        value={expr}
        onChange={(e) => setExpr(e.target.value)}
        placeholder="p. ej. 3*24+7"
        aria-label="Calculadora"
        className="w-full rounded border border-po-border bg-po-panel px-2 py-1 text-xs font-mono text-po-text placeholder-po-text-subtle focus:outline-none focus:ring-1 focus:ring-po-accent"
      />
      <p className="text-right font-mono text-sm tabular-nums text-po-text">
        {result != null ? `= ${result}` : expr ? "…" : ""}
      </p>
    </div>
  );
}
```

Focus isolation: the Task 11 guard (`focusIsInInput`) already makes viewer
shortcuts inert while this input has focus — that is the load-bearing rule;
no extra wiring needed.

- [ ] **Step 3: Gates + commit**

Run: `cd frontend && npx vitest run` → green; `npm run build` → OK.

```bash
git add frontend/src/lib/calc.js frontend/src/lib/calc.test.js frontend/src/components/WorkerHud.jsx
git commit -m "feat(web): collapsible keyboard calculator in the viewer HUD (I8)"
```

### Task 20: Round close — gates + live smoke

- [ ] **Step 1: Full gates**

```bash
pytest -m "not slow" -q        # 0 failures
cd frontend && npx vitest run  # 0 failures
cd frontend && npm run build   # OK
ruff check .                   # 0
```

- [ ] **Step 2: Live browser smoke (Brave via chrome-devtools MCP, isolated copy DB)**

Follow the established isolation protocol (copy `overseer.db`, backend on
:8010, fetch/WS rewrite — see `feedback_browser_testing_via_devtools` +
prior smoke notes). Checklist (spec §10): months chronological in the home;
thumbnails visibly larger + active one centered; fast page flipping on a big
PDF (revisits instant, cold pages show blurred placeholder); Shift+PageDown
jumps 10; Ir-a-página works and typing digits there does NOT create a count
mark; a rotate op on a sideways file straightens viewer + thumbnail, and
deleting the op restores; chip filters combine with search; DetailPanel shows
the counter above the collapsed Reorganización; month header button opens the
panel and Exportar writes the manifest JSON (check `OVERSEER_OUTPUT_DIR` of
the ISOLATED env); calculator evaluates and its digits don't leak into
counting. Verify the real `overseer.db` untouched afterwards (hash compare).

- [ ] **Step 3: Push**

```bash
git push origin po_overhaul
```
