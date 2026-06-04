# FileList & CategoryRow refinements — implementation plan

> **For agentic workers:** execute in-session. Tests are written alongside each task; the full run (vitest + build) and the live smoke happen once at the end, not per task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Land 5 small frontend UI refinements to the conteo-confiable review surface (column alignment, honest doc-count placeholders, precedence sort, decluttered category chips, repositioned worker button).

**Architecture:** Frontend-only. Two pure helpers (`file-origin.js`) carry the testable logic for G2/G3; the rest are component-local layout/markup edits. No backend, API, DB, or scanner changes.

**Tech Stack:** React + Vite, Tailwind (po-* tokens), vitest.

**Spec:** `docs/superpowers/specs/2026-06-04-filelist-refinements-design.md`

**Branch:** `po_overhaul` (work directly — single live branch convention). Push at the end of the round.

**Co-Author trailer (verbatim):** `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

## Chunk 1: helpers + FileList

### Task 1: file-origin pure helpers (G2 + G3) — TDD

**Files:**
- Create: `frontend/src/lib/file-origin.js`
- Create: `frontend/src/lib/__tests__/file-origin.test.js`

- [ ] **Step 1: Write the failing tests**

```js
// frontend/src/lib/__tests__/file-origin.test.js
import { describe, it, expect } from "vitest";
import { fileCountDisplay, ORIGIN_RANK, compareByOrigin } from "../file-origin";

describe("fileCountDisplay", () => {
  it("Pendiente → null value + em-dash placeholder (still editable)", () => {
    expect(fileCountDisplay("Pendiente", 1)).toEqual({ value: null, placeholder: "—" });
  });
  it("Revisar → shows the real 0", () => {
    expect(fileCountDisplay("Revisar", 0)).toEqual({ value: 0, placeholder: undefined });
  });
  it("OCR/Manual/R1 → effective count", () => {
    expect(fileCountDisplay("OCR", 17)).toEqual({ value: 17, placeholder: undefined });
    expect(fileCountDisplay("R1", 1)).toEqual({ value: 1, placeholder: undefined });
  });
  it("missing count → defaults to 1 (non-Pendiente)", () => {
    expect(fileCountDisplay("R1", undefined)).toEqual({ value: 1, placeholder: undefined });
  });
});

describe("compareByOrigin", () => {
  it("orders Error → Pendiente → Revisar → Manual → OCR → R1", () => {
    const rows = [
      { name: "d.pdf", origin: "R1" },
      { name: "a.pdf", origin: "OCR" },
      { name: "b.pdf", origin: "Error" },
      { name: "c.pdf", origin: "Manual" },
      { name: "e.pdf", origin: "Pendiente" },
      { name: "f.pdf", origin: "Revisar" },
    ];
    const sorted = [...rows].sort(compareByOrigin).map((r) => r.origin);
    expect(sorted).toEqual(["Error", "Pendiente", "Revisar", "Manual", "OCR", "R1"]);
  });
  it("ties broken by filename within the same origin", () => {
    const rows = [
      { name: "2026-04-30_x.pdf", origin: "Pendiente" },
      { name: "2026-04-02_x.pdf", origin: "Pendiente" },
    ];
    const sorted = [...rows].sort(compareByOrigin).map((r) => r.name);
    expect(sorted).toEqual(["2026-04-02_x.pdf", "2026-04-30_x.pdf"]);
  });
  it("unknown origin sorts last", () => {
    const rows = [{ name: "a", origin: "???" }, { name: "b", origin: "R1" }];
    const sorted = [...rows].sort(compareByOrigin).map((r) => r.origin);
    expect(sorted).toEqual(["R1", "???"]);
  });
});
```

- [ ] **Step 2: Implement the helpers**

```js
// frontend/src/lib/file-origin.js
// Pure, node-testable helpers for the FileList "Archivos" column.

// G2 — what to show in the per-file doc-count cell. A "Pendiente" file has not
// been counted yet, so it reads as "—" (still editable). A "Revisar" file was
// scanned and read 0 — that 0 is a real count, shown as-is. Everyone else shows
// their effective count (default 1 when absent).
export function fileCountDisplay(origin, effectiveCount) {
  if (origin === "Pendiente") return { value: null, placeholder: "—" };
  return { value: effectiveCount ?? (origin === "Revisar" ? 0 : 1), placeholder: undefined };
}

// G3 — precedence for the per-file rows: most-urgent first. Unknown origins last.
export const ORIGIN_RANK = {
  Error: 0,
  Pendiente: 1,
  Revisar: 2,
  Manual: 3,
  OCR: 4,
  R1: 5,
};

export function compareByOrigin(a, b) {
  const ra = ORIGIN_RANK[a.origin] ?? 99;
  const rb = ORIGIN_RANK[b.origin] ?? 99;
  if (ra !== rb) return ra - rb;
  return (a.name ?? "").localeCompare(b.name ?? "");
}
```

> Note: `fileCountDisplay("Revisar", 0)` returns `value: 0` via the `?? ` chain
> (0 is not nullish). The explicit `Revisar ? 0 : 1` only governs the
> *missing*-count fallback.

- [ ] **Step 3: Commit**

```
feat(frontend): file-origin helpers for per-file display + precedence sort
```

### Task 2: G1 — fixed-width column alignment in FileList

**Files:** Modify `frontend/src/components/FileList.jsx`

- [ ] **Step 1:** Replace the per-row grid template (line ~87) so all rows share
  fixed tracks instead of content-sized `auto`:

```jsx
className="grid grid-cols-[minmax(0,1fr)_3rem_1.25rem_3.5rem_5.5rem] items-center gap-2 px-3 py-2 hover:bg-po-panel-hover transition"
```

- [ ] **Step 2:** Right-align the page-count cell and keep it from shrinking:

```jsx
<span className="text-xs tabular-nums text-po-text-muted text-right">{f.page_count}pp</span>
```

- [ ] **Step 3:** Center the compilation-icon track (present or empty) so the next
  columns never shift:

```jsx
{f.suspect ? (
  <Tooltip content="Probable compilación">
    <span className="flex justify-center"><FileStack size={14} strokeWidth={1.75} className="text-po-suspect" /></span>
  </Tooltip>
) : (
  <span />
)}
```

- [ ] **Step 4:** The count cell keeps `InlineEditCount` (already `w-14`,
  right-aligned). The origin-chip cell gets a fixed-width left-aligned wrapper so
  chips line up on a common left edge:

```jsx
<div className="flex justify-start"><OriginChip origin={f.origin ?? "R1"} /></div>
```

- [ ] **Step 5:** Visual check deferred to the end-of-batch smoke (column alignment
  across rows with mixed page counts / suspect icons / 2-digit counts).

- [ ] **Step 6: Commit**

```
fix(frontend): align FileList columns with a shared fixed-width grid
```

### Task 3: G2 — Pendiente "—" / Revisar "0" in FileList

**Files:** Modify `frontend/src/components/FileList.jsx`

- [ ] **Step 1:** Import the helper: `import { fileCountDisplay } from "../lib/file-origin";`
- [ ] **Step 2:** Replace the `InlineEditCount` value wiring (line ~113-114). Today:
  `value={f.effective_count ?? 1}`. New:

```jsx
{(() => {
  const { value, placeholder } = fileCountDisplay(f.origin, f.effective_count);
  return (
    <InlineEditCount
      value={value}
      placeholder={placeholder}
      onCommit={(newCount) => {
        setFiles((prev) =>
          prev.map((row) =>
            row.name === f.name
              ? { ...row, effective_count: newCount, override_count: newCount, origin: "Manual" }
              : row,
          ),
        );
        savePerFileOverride(session.session_id, hospital, sigla, f.name, newCount);
      }}
    />
  );
})()}
```

- [ ] **Step 3:** Commit

```
feat(frontend): FileList shows "—" for pendiente, "0" for revisar
```

### Task 4: G3 — precedence sort in FileList

**Files:** Modify `frontend/src/components/FileList.jsx`

- [ ] **Step 1:** Import the comparator: `import { compareByOrigin, fileCountDisplay } from "../lib/file-origin";` (merge with Task 3 import).
- [ ] **Step 2:** Sort the *filtered* copy (keep `files` intact so `files.indexOf(f)`
  in the lightbox call stays correct — per reviewer note):

```jsx
const filtered = files
  .filter((f) => f.name.toLowerCase().includes(search.toLowerCase()))
  .sort(compareByOrigin);
```

- [ ] **Step 3:** Confirm the lightbox call still uses `files.indexOf(f)` (the source
  array), not a filtered index. No change needed there.
- [ ] **Step 4:** Commit

```
feat(frontend): order FileList by attention precedence (Error→…→R1)
```

---

## Chunk 2: CategoryRow + DetailPanel

### Task 5: G4 — remove status chips from CategoryRow

**Files:** Modify `frontend/src/components/CategoryRow.jsx`

- [ ] **Step 1:** In the trailing `<div className="ml-auto …">`, keep the
  `isScanning` branch (the "Escaneando…" badge) but strip the three persistent chips
  from the `else` branch — remove the `hasError` Error badge, the `Manual` badge, and
  the `Compilación` badge — leaving only `InlineEditCount`:

```jsx
<div className="ml-auto flex items-center gap-2">
  {isScanning ? (
    <Badge variant="state-scanning" icon={Loader2}>Escaneando…</Badge>
  ) : (
    <InlineEditCount
      value={computeCellCount(cell)}
      onCommit={onCommitCount}
      placeholder={placeholder}
      autoFocus={autoFocus}
    />
  )}
</div>
```

- [ ] **Step 2:** Error now reads as the existing red dot — no new code:
  `dotVariantFor` already returns `"state-error"` (→ `bg-po-dot-error` = ruby) when
  `cell.errors` is non-empty. The `<Dot variant={dotVariantFor(...)} />` call is
  unchanged.
- [ ] **Step 3:** Remove now-unused symbols (verified by fresh-eyes review):
  - lucide imports: drop `AlertCircle`, `FileStack`, `PenLine`. **Keep** `Loader2`
    (used by the Escaneando badge).
  - **Keep** `Badge` (Escaneando badge) and `Tooltip` (sigla-label tooltip at
    line ~61) — both still referenced.
  - cell-status import: change `import { dotVariantFor, hasOverride } from "../lib/cell-status";`
    → `import { dotVariantFor } from "../lib/cell-status";`. Dropping `cellHasOverride`
    removes the only use of `hasOverride`, so the import becomes dead and MUST go.
  - Drop the now-dead locals `cellHasOverride`, `isCompilationSuspect`, `hasError`,
    `showMethodChip`. **Keep** `placeholder` and `onCommitCount` (still passed to
    `InlineEditCount`).
  - Verify by reading the final file; the build (`vite build`) is the backstop for
    any missed unresolved/dead import.
- [ ] **Step 4:** Commit

```
refactor(frontend): drop status chips from CategoryRow; error reads as red dot
```

### Task 6: G5 — worker module above near-matches

**Files:** Modify `frontend/src/components/DetailPanel.jsx`

- [ ] **Step 1:** In the `DetailPanel` return (lines ~266-275), move the
  charla/chintegral `WorkerCountModule` block to render **before** the
  `NearMatchesSection`:

```jsx
{(sigla === "charla" || sigla === "chintegral") && (
  <WorkerCountModule hospital={hospital} sigla={sigla} cell={cell} />
)}

<NearMatchesSection
  hospital={hospital}
  sigla={sigla}
  cell={cell}
  sessionId={sessionId}
/>
```

- [ ] **Step 2:** Commit

```
fix(frontend): show worker-count module above the near-match suspects
```

---

## Chunk 3: verification (all at the end — "todo junto")

### Task 7: run suite + build

- [ ] **Step 1:** `cd frontend && npm run test -- --run` → expect the new
  `file-origin.test.js` green plus the existing vitest suite (78+ passing).
- [ ] **Step 2:** `cd frontend && npm run build` → expect a clean build (catches
  unresolved imports / dead-symbol issues from Task 5).

### Task 8: live smoke (chrome-devtools, ABRIL)

- [ ] **G1:** open a cell with mixed rows (HPV/andamios: 1–4pp, all "1") and a cell
  with 2-digit counts / suspect icons; confirm pp / count / chip line up as columns.
- [ ] **G2:** a Pendiente file shows "—"; a Revisar file (if present) shows "0";
  editing a "—" commits a number and flips it to Manual.
- [ ] **G3:** within a cell, rows order Error → Pendiente → Revisar → Manual → OCR →
  R1.
- [ ] **G4:** a CategoryRow with an error shows a red dot and no chips; a manual /
  compilation cell shows no chip; "Escaneando…" still appears during an active scan.
- [ ] **G5:** open charla/chintegral with near-matches; the "Contar trabajadores"
  button sits above the suspects list.

### Task 9: close the round

- [ ] **Step 1:** `git push origin po_overhaul` (per the work-directly convention).
- [ ] **Step 2:** Report verified facts (commits, suite result, smoke outcome) +
  remaining deferred item (#6 clear-suspects).
