# Incremento 1B — Frontend honesto: Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the cell "ready" signal honest (green dot by per-file provenance, not scanner `confidence`), make the cell↔files override reversible and legible (toggle `Por archivos · Manual` + inline amber hint), and reject negative manual entries — all on the React frontend, consuming the `per_file_method` foundation that Incr 1A already shipped.

**Architecture:** Almost-pure frontend. The honest green dot, the files-count helper, and the override-input validation are pure functions in `frontend/src/lib/` (unit-tested with vitest). The toggle is a new accessible primitive in `frontend/src/ui/`. `DetailPanel` / `OverridePanel` / `FileList` are rewired to derive the override "mode" from `cell.user_override` and to reuse the existing `saveOverride` action (which already accepts `value=null` to clear). No backend change. No version-tag bump (no `core/*.py` or `vlm/*.py` touched).

**Tech Stack:** React 18, Zustand store, Vite, Vitest (no React Testing Library — component behavior is verified by a conducted chrome-devtools smoke, not render tests), Tailwind with `po-*` design tokens.

**Spec:** `docs/superpowers/specs/2026-06-15-incremento-1b-frontend-honesto-design.md`

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `frontend/src/lib/cell-status.js` | Green-dot readiness from provenance | Modify (rewrite `isCellReady`; add `OCR_METHODS`, `allFilesReliable`, `anyUnreliableOcrFile`) |
| `frontend/src/lib/cell-status.test.js` | Truth-table tests for the dot | Modify |
| `frontend/src/lib/cellCount.js` | Cell total + files-only total | Modify (extract `computeFilesCount`) |
| `frontend/src/lib/cellCount.test.js` | Parity + files-only tests | Create |
| `frontend/src/lib/override-input.js` | Parse/validate manual-override input | Create |
| `frontend/src/lib/override-input.test.js` | Validation tests | Create |
| `frontend/src/ui/SegmentedToggle.jsx` | Accessible 2-segment toggle primitive | Create |
| `frontend/src/components/DetailPanel.jsx` | Header: toggle + `archivos: N`; remove confidence badge | Modify |
| `frontend/src/components/OverridePanel.jsx` | Disabled state per mode; focus on manual; negative rejection | Modify |
| `frontend/src/components/FileList.jsx` | Inline amber hint when cell override active | Modify |

**Mode model (shared by Tasks 4–6):** the override "mode" is **local UI state** in `DetailPanel`, initialized and re-synced from `hasOverride(cell)` whenever the selected cell changes:
- `mode === "manual"` ⟺ user is editing the cell-level override (or just clicked Manual).
- `mode === "files"` ⟺ total comes from the per-file sum.
- Switching **→ files** calls `saveOverride(..., value=null)` (clears the override).
- Switching **→ manual** focuses the input (no write until the user types a number).
- This matches spec §5.1/§5.3: "Manual mode focuses the field; saves on type."

---

## Chunk 1: Pure logic (TDD) + UI rewiring

### Task 1: Honest green dot (`cell-status.js`)

**Files:**
- Modify: `frontend/src/lib/cell-status.js`
- Test: `frontend/src/lib/cell-status.test.js`

- [ ] **Step 1: Write the failing tests**

Replace the body of `frontend/src/lib/cell-status.test.js` with the truth-table cases (spec §4.3). Keep the existing `hasOverride` and `dotVariantFor` describe blocks; extend `isCellReady` and add `allFilesReliable` coverage:

```js
import { describe, expect, it } from "vitest";

import {
  allFilesReliable,
  anyUnreliableOcrFile,
  dotVariantFor,
  hasOverride,
  isCellReady,
} from "./cell-status";

describe("isCellReady (honest provenance)", () => {
  it("all-R1 single-page cell (high, filename_glob) -> ready", () => {
    expect(
      isCellReady({ confidence: "high", per_file_method: { "a.pdf": "filename_glob" } }),
    ).toBe(true);
  });

  it("fixed-page sigla (high, page_count_pure) -> ready", () => {
    expect(
      isCellReady({ confidence: "high", per_file_method: { "a.pdf": "page_count_pure" } }),
    ).toBe(true);
  });

  it("multipage no-OCR cell (low) -> NOT ready", () => {
    expect(
      isCellReady({ confidence: "low", per_file_method: { "a.pdf": "filename_glob" } }),
    ).toBe(false);
  });

  it("clean OCR cell (high) -> NOT ready (the honest change)", () => {
    expect(
      isCellReady({ confidence: "high", per_file_method: { "a.pdf": "v4" } }),
    ).toBe(false);
    expect(
      isCellReady({ confidence: "high", per_file_method: { "a.pdf": "header_band_anchors" } }),
    ).toBe(false);
  });

  it("OCR cell + confirmed -> ready", () => {
    expect(
      isCellReady({ confidence: "high", per_file_method: { "a.pdf": "v4" }, confirmed: true }),
    ).toBe(true);
  });

  it("OCR cell + cell-level override -> ready", () => {
    expect(
      isCellReady({ confidence: "high", per_file_method: { "a.pdf": "v4" }, user_override: 5 }),
    ).toBe(true);
    expect(
      isCellReady({ confidence: "high", per_file_method: { "a.pdf": "v4" }, user_override: 0 }),
    ).toBe(true);
  });

  it("mix R1 + one OCR file -> NOT ready", () => {
    expect(
      isCellReady({
        confidence: "high",
        per_file_method: { "a.pdf": "filename_glob", "b.pdf": "v4" },
      }),
    ).toBe(false);
  });

  it("mix R1 + OCR file overridden per-file -> ready", () => {
    expect(
      isCellReady({
        confidence: "high",
        per_file_method: { "a.pdf": "filename_glob", "b.pdf": "v4" },
        per_file_overrides: { "b.pdf": 3 },
      }),
    ).toBe(true);
    // a 0 per-file override still counts as Manual (reliable)
    expect(
      isCellReady({
        confidence: "high",
        per_file_method: { "b.pdf": "v4" },
        per_file_overrides: { "b.pdf": 0 },
      }),
    ).toBe(true);
  });

  it("empty per_file_method with high confidence -> ready (no OCR evidence)", () => {
    expect(isCellReady({ confidence: "high" })).toBe(true);
    expect(isCellReady({ confidence: "high", per_file_method: {} })).toBe(true);
  });

  it("manually confirmed even if confidence low -> ready", () => {
    expect(isCellReady({ confidence: "low", confirmed: true })).toBe(true);
  });
});

describe("anyUnreliableOcrFile", () => {
  it("true only for an OCR method without a per-file override", () => {
    expect(anyUnreliableOcrFile({ per_file_method: { "a.pdf": "v4" } })).toBe(true);
    expect(
      anyUnreliableOcrFile({ per_file_method: { "a.pdf": "v4" }, per_file_overrides: { "a.pdf": 2 } }),
    ).toBe(false);
    expect(anyUnreliableOcrFile({ per_file_method: { "a.pdf": "filename_glob" } })).toBe(false);
    expect(anyUnreliableOcrFile({ per_file_method: { "a.pdf": "page_count_pure" } })).toBe(false);
    expect(anyUnreliableOcrFile({})).toBe(false);
  });
});

describe("allFilesReliable", () => {
  it("requires high confidence AND no unreliable OCR file", () => {
    expect(allFilesReliable({ confidence: "high", per_file_method: { "a.pdf": "filename_glob" } })).toBe(true);
    expect(allFilesReliable({ confidence: "low", per_file_method: { "a.pdf": "filename_glob" } })).toBe(false);
    expect(allFilesReliable({ confidence: "high", per_file_method: { "a.pdf": "v4" } })).toBe(false);
  });
});

describe("hasOverride", () => {
  it("treats 0 as an override but null/undefined as none", () => {
    expect(hasOverride({ user_override: 0 })).toBe(true);
    expect(hasOverride({ user_override: null })).toBe(false);
    expect(hasOverride({})).toBe(false);
  });
});

describe("dotVariantFor", () => {
  it("scanning takes precedence over everything", () => {
    expect(dotVariantFor({ confidence: "high" }, { isScanning: true })).toBe("state-scanning");
  });
  it("error takes precedence over readiness", () => {
    expect(dotVariantFor({ confidence: "high", errors: ["boom"] })).toBe("state-error");
  });
  it("ready -> green, pendiente -> amber", () => {
    expect(dotVariantFor({ confidence: "high" })).toBe("confidence-high");
    expect(dotVariantFor({ confidence: "low" })).toBe("confidence-low");
    expect(dotVariantFor({ confidence: "high", per_file_method: { "a.pdf": "v4" } })).toBe("confidence-low");
    expect(dotVariantFor({ confidence: "low", confirmed: true })).toBe("confidence-high");
  });
  it("a cell with no data yet stays neutral", () => {
    expect(dotVariantFor(undefined)).toBe("neutral");
    expect(dotVariantFor(null)).toBe("neutral");
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/lib/cell-status.test.js`
Expected: FAIL (`allFilesReliable`/`anyUnreliableOcrFile` not exported; OCR cases still green).

- [ ] **Step 3: Rewrite `cell-status.js`**

Replace `frontend/src/lib/cell-status.js` with:

```js
// Cell readiness for the honest "listo / pendiente" model (Incr 1B, Decisión 1).
//
// A cell is *listo* (green) when its count is trustworthy by PROVENANCE, not by
// the scanner's `confidence` alone: the operator confirmed it, there is a
// cell-level manual override, OR every file is reliable (R1 / Manual). Any file
// counted by OCR (without a per-file override), Pendiente, or Error keeps the
// cell *pendiente* (amber) until a human confirms it.
//
// OCR_METHODS mirrors the OCR/Revisar branch of `_origin_for`
// (api/routes/sessions.py): these per-file methods read uncertain values.
// `page_count_pure` is intentionally NOT here — it maps to R1 (reliable
// fixed-page path); adding it would wrongly amber fixed-page siglas.
export const OCR_METHODS = new Set([
  "header_detect",
  "corner_count",
  "header_band_anchors",
  "v4",
]);

export function hasOverride(cell) {
  // 0 is a valid override (discard a file's contribution) — guard on presence.
  return cell?.user_override !== null && cell?.user_override !== undefined;
}

// True when at least one file was counted by OCR and has NOT been corrected by a
// per-file override. A per-file override turns that file into "Manual" (reliable).
export function anyUnreliableOcrFile(cell) {
  const methods = cell?.per_file_method ?? {};
  const overrides = cell?.per_file_overrides ?? {};
  for (const [filename, method] of Object.entries(methods)) {
    if (OCR_METHODS.has(method) && overrides[filename] === undefined) {
      return true;
    }
  }
  return false;
}

// Every file is R1 or Manual. `confidence === "high"` already guarantees every
// filename_glob file is single-page (simple_factory.py:84/97); the OCR exclusion
// is what this layer adds on top.
export function allFilesReliable(cell) {
  return cell?.confidence === "high" && !anyUnreliableOcrFile(cell);
}

export function isCellReady(cell) {
  return !!cell?.confirmed || hasOverride(cell) || allFilesReliable(cell);
}

// Dot tone. Scanning/error take precedence; a cell with no data yet stays
// neutral (gray) so a fresh, unscanned month doesn't read as all-pendiente.
export function dotVariantFor(cell, { isScanning = false } = {}) {
  if (isScanning) return "state-scanning";
  if (cell?.errors?.length > 0) return "state-error";
  if (!cell) return "neutral";
  return isCellReady(cell) ? "confidence-high" : "confidence-low";
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/lib/cell-status.test.js`
Expected: PASS (all cases).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/cell-status.js frontend/src/lib/cell-status.test.js
git commit -m "feat(1b): honest green dot by per-file provenance (Decisión 1)"
```

---

### Task 2: Files-only count helper (`cellCount.js`)

**Files:**
- Modify: `frontend/src/lib/cellCount.js`
- Test: `frontend/src/lib/cellCount.test.js` (create)

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/lib/cellCount.test.js`:

```js
import { describe, expect, it } from "vitest";

import { computeCellCount, computeFilesCount } from "./cellCount";

describe("computeFilesCount (ignores user_override)", () => {
  it("sums per_file with per_file_overrides taking precedence", () => {
    const cell = {
      per_file: { "a.pdf": 1, "b.pdf": 2 },
      per_file_overrides: { "b.pdf": 5 },
    };
    expect(computeFilesCount(cell)).toBe(6); // 1 + 5
  });

  it("ignores user_override entirely", () => {
    const cell = { per_file: { "a.pdf": 3 }, user_override: 999 };
    expect(computeFilesCount(cell)).toBe(3);
  });

  it("falls back to ocr_count then filename_count then 0 when no per-file data", () => {
    expect(computeFilesCount({ ocr_count: 7 })).toBe(7);
    expect(computeFilesCount({ filename_count: 4 })).toBe(4);
    expect(computeFilesCount({})).toBe(0);
    expect(computeFilesCount(null)).toBe(0);
  });
});

describe("computeCellCount (override wins, else files)", () => {
  it("returns user_override when present (including 0)", () => {
    expect(computeCellCount({ per_file: { "a.pdf": 3 }, user_override: 10 })).toBe(10);
    expect(computeCellCount({ per_file: { "a.pdf": 3 }, user_override: 0 })).toBe(0);
  });

  it("equals computeFilesCount when no override (parity preserved)", () => {
    const cell = { per_file: { "a.pdf": 1, "b.pdf": 2 }, per_file_overrides: { "b.pdf": 5 } };
    expect(computeCellCount(cell)).toBe(computeFilesCount(cell));
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/lib/cellCount.test.js`
Expected: FAIL (`computeFilesCount` not exported).

- [ ] **Step 3: Refactor `cellCount.js`**

Replace `frontend/src/lib/cellCount.js` with:

```js
// Mirror of api/state.py:compute_cell_count. Mantener en sync — ambas funciones
// deben producir el mismo número para el mismo cell. Cross-language parity
// validada por tests/fixtures/cell_count_cases.json (Python tests + smoke).
// Spec FASE 4 §6.2. Incr 1B: extraído computeFilesCount (suma por archivos sin
// el override de celda) para el toggle "archivos: N" — misma lógica de suma.

export function computeFilesCount(cell) {
  const perFile = cell?.per_file ?? {};
  const perFileOverrides = cell?.per_file_overrides ?? {};
  const hasPerFile = Object.keys(perFile).length > 0;
  const hasOverrides = Object.keys(perFileOverrides).length > 0;

  if (hasPerFile || hasOverrides) {
    const allFiles = new Set([
      ...Object.keys(perFile),
      ...Object.keys(perFileOverrides),
    ]);
    let sum = 0;
    for (const f of allFiles) {
      sum += perFileOverrides[f] ?? perFile[f] ?? 0;
    }
    return sum;
  }

  return cell?.ocr_count ?? cell?.filename_count ?? 0;
}

export function computeCellCount(cell) {
  if (cell?.user_override != null) return cell.user_override;
  return computeFilesCount(cell);
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/lib/cellCount.test.js`
Expected: PASS.

- [ ] **Step 5: Run the full suite to confirm no parity regression**

Run: `cd frontend && npm test`
Expected: PASS (existing `computeCellCount` consumers + the Python-parity fixture path unaffected — `computeCellCount` returns identical values).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/cellCount.js frontend/src/lib/cellCount.test.js
git commit -m "refactor(1b): extract computeFilesCount (files-only sum) preserving parity"
```

---

### Task 3: Manual-override input validation (`override-input.js`)

**Files:**
- Create: `frontend/src/lib/override-input.js`
- Test: `frontend/src/lib/override-input.test.js`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/lib/override-input.test.js`:

```js
import { describe, expect, it } from "vitest";

import { parseOverrideInput } from "./override-input";

describe("parseOverrideInput", () => {
  it("empty/null clears the override (value null, valid)", () => {
    expect(parseOverrideInput("")).toEqual({ value: null, valid: true });
    expect(parseOverrideInput(null)).toEqual({ value: null, valid: true });
    expect(parseOverrideInput(undefined)).toEqual({ value: null, valid: true });
  });

  it("0 is a valid override", () => {
    expect(parseOverrideInput("0")).toEqual({ value: 0, valid: true });
  });

  it("positive integers are valid", () => {
    expect(parseOverrideInput("12")).toEqual({ value: 12, valid: true });
  });

  it("negatives are invalid", () => {
    expect(parseOverrideInput("-5")).toEqual({ value: null, valid: false });
  });

  it("non-numeric is invalid", () => {
    expect(parseOverrideInput("abc")).toEqual({ value: null, valid: false });
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/lib/override-input.test.js`
Expected: FAIL (module not found).

- [ ] **Step 3: Create `override-input.js`**

```js
// Validation for the manual-override field (Incr 1B, Decisión 4 partial).
// Negatives are rejected; 0 is a valid override; empty clears it. The ≤páginas
// cap is intentionally NOT here (deferred to Incr 2 with persisted per_file_pages).

export function parseOverrideInput(raw) {
  if (raw === "" || raw === null || raw === undefined) {
    return { value: null, valid: true };
  }
  const n = parseInt(raw, 10);
  if (Number.isNaN(n) || n < 0) {
    return { value: null, valid: false };
  }
  return { value: n, valid: true };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/lib/override-input.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/override-input.js frontend/src/lib/override-input.test.js
git commit -m "feat(1b): parseOverrideInput — reject negatives, 0 valid, empty clears"
```

---

### Task 4: `SegmentedToggle` primitive

**Files:**
- Create: `frontend/src/ui/SegmentedToggle.jsx`

> No render-test infra (no RTL) — verified by usage in Task 5 + smoke (Task 7).

- [ ] **Step 1: Create the primitive**

```jsx
// Two-segment toggle (radiogroup). Tokens po-* only; no Radix needed.
// options: [{ value, label }]. Controlled via `value` + `onChange`.
export default function SegmentedToggle({ value, onChange, options, ariaLabel }) {
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className="inline-flex rounded-md border border-po-border bg-po-bg p-0.5"
    >
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(opt.value)}
            className={`rounded px-3 py-1 text-sm transition outline-none focus-visible:ring-1 focus-visible:ring-po-accent ${
              active
                ? "bg-po-panel text-po-text shadow-sm"
                : "text-po-text-muted hover:text-po-text"
            }`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Verify it builds**

Run: `cd frontend && npm run build`
Expected: build succeeds (no import/syntax errors).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/ui/SegmentedToggle.jsx
git commit -m "feat(1b): SegmentedToggle ui primitive (accessible radiogroup)"
```

---

### Task 5: Wire toggle + remove confidence badge (`DetailPanel.jsx`)

**Files:**
- Modify: `frontend/src/components/DetailPanel.jsx`
- Modify: `frontend/src/components/OverridePanel.jsx`

This task is verified by build + smoke (Task 7), not unit tests.

- [ ] **Step 1: Add mode state + toggle to `DetailPanel`**

In `DetailPanel.jsx`:

1. Add imports:
   ```js
   import { useEffect, useRef, useState } from "react"; // file currently imports {useEffect, useState} — ADD useRef
   import SegmentedToggle from "../ui/SegmentedToggle";
   import { hasOverride } from "../lib/cell-status";
   import { computeCellCount, computeFilesCount } from "../lib/cellCount";
   ```
2. Remove the confidence badge import + symbols. Read the exact ranges first, then delete:
   - `CONFIDENCE_LABEL` from the `method-labels` import (line 11). `METHOD_LABEL` stays.
   - the `confidenceVariant` function (lines 20–24).
   - the **entire** badge conditional in the badges row — the wrapper `{cell.confidence && (` (line 232),
     the `<Badge variant={confidenceVariant(cell)}>…</Badge>` (line 233), and the closing `)}` (line 235).
     Delete all of it as one block; do NOT leave the `{cell.confidence && (` guard with an empty body.
   - Keep the immediately-following `{hasOverride && <Badge … "Manual">}` (`state-override`) and the
     `state-suspect` "Compilación" badge untouched.
3. Inside the component, derive + hold the mode:
   ```js
   const filesCount = computeFilesCount(cell);
   const [mode, setMode] = useState(hasOverride(cell) ? "manual" : "files");
   const [focusNonce, setFocusNonce] = useState(0);

   // Re-sync mode from provenance when the selected cell changes.
   useEffect(() => {
     setMode(hasOverride(cell) ? "manual" : "files");
   }, [hospital, sigla, cell?.user_override]);

   function handleModeChange(next) {
     setMode(next);
     if (next === "files") {
       // Clear the cell override → total = files sum.
       saveOverride(sessionId, hospital, sigla, null, cell?.override_note ?? null);
     } else {
       // Manual: focus the field; no write until the operator types.
       setFocusNonce((n) => n + 1);
     }
   }
   ```
   (Pull `saveOverride` from the store: `const saveOverride = useSessionStore((s) => s.saveOverride);`.)
4. Render the toggle directly under the `documentos` line, before the badges row:
   ```jsx
   <div className="mt-3 flex items-center gap-3">
     <SegmentedToggle
       ariaLabel="Origen del conteo"
       value={mode}
       onChange={handleModeChange}
       options={[
         { value: "files", label: "Por archivos" },
         { value: "manual", label: "Manual" },
       ]}
     />
     <span className="text-xs text-po-text-muted tabular-nums">
       archivos: {filesCount.toLocaleString()}
     </span>
   </div>
   ```
5. Pass mode down to `OverridePanel`:
   ```jsx
   <OverridePanel
     hospital={hospital}
     sigla={sigla}
     cell={cell}
     disabled={mode === "files"}
     focusNonce={focusNonce}
   />
   ```

- [ ] **Step 2: Update `OverridePanel` to honor `disabled` + `focusNonce`**

In `OverridePanel.jsx`:

1. Accept the new props: `export default function OverridePanel({ hospital, sigla, cell, disabled = false, focusNonce = 0 }) {`.
2. Add a ref + focus effect:
   ```js
   import { useEffect, useRef, useState } from "react";
   import { parseOverrideInput } from "../lib/override-input";
   // ...
   const inputRef = useRef(null);
   const [invalid, setInvalid] = useState(false);

   useEffect(() => {
     if (focusNonce > 0 && !disabled && inputRef.current) {
       inputRef.current.focus();
       inputRef.current.select();
     }
   }, [focusNonce, disabled]);
   ```
3. Replace `onChangeValue` with validation:
   ```js
   const onChangeValue = (e) => {
     const raw = e.target.value;
     setValue(raw);
     const { value: parsed, valid } = parseOverrideInput(raw);
     setInvalid(!valid);
     if (valid) flushSave(parsed === null ? "" : String(parsed), note);
   };
   ```
   (`flushSave` already coerces `""`→`null`; keep that path.)
4. On the `<input>`: add `ref={inputRef}`, `disabled={disabled}`, `min={0}`, and an error/disabled style:
   ```jsx
   className={`w-24 rounded border px-2 py-1.5 text-sm tabular-nums outline-none ${
     disabled
       ? "cursor-not-allowed border-po-border bg-po-bg/40 text-po-text-muted opacity-50"
       : invalid
         ? "border-po-error bg-po-bg focus:border-po-error"
         : "border-po-border bg-po-bg focus:border-po-accent"
   }`}
   ```
5. The note textarea: add `disabled={disabled}` and a matching muted style when disabled (spec §5.3 — note is coupled to the override in 1B, so it's disabled in "Por archivos" mode).

- [ ] **Step 3: Verify build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/DetailPanel.jsx frontend/src/components/OverridePanel.jsx
git commit -m "feat(1b): toggle Por archivos·Manual + remove confidence badge"
```

---

### Task 6: Inline amber hint in `FileList.jsx`

**Files:**
- Modify: `frontend/src/components/FileList.jsx`

Verified by build + smoke (Task 7).

- [ ] **Step 1: Read the cell from the store and render the hint**

In `FileList.jsx`:

1. Import the override check + count formatter:
   ```js
   import { hasOverride } from "../lib/cell-status";
   ```
2. Select the cell and the override-clear action from the store:
   ```js
   const cell = useSessionStore(
     (s) => s.session?.cells?.[hospital]?.[sigla],
   );
   const saveOverride = useSessionStore((s) => s.saveOverride);
   ```
   (Confirm the store path to a cell — match how other components read it, e.g. `DetailPanel` gets `cell` as a prop from the same store slice; use the same selector shape the store exposes. If the store nests cells differently, mirror that exact path.)
3. Just inside the outer wrapper (before the search bar `<div className="p-2 border-b …">`), render the hint when the cell has a cell-level override:
   ```jsx
   {hasOverride(cell) && (
     <div className="flex items-start gap-2 border-b border-po-suspect-border bg-po-suspect-bg px-3 py-2 text-xs text-po-suspect">
       <span aria-hidden>⚠</span>
       <span>
         La celda usa un total manual ({cell.user_override}) que anula los archivos.{" "}
         <button
           type="button"
           onClick={() =>
             saveOverride(session.session_id, hospital, sigla, null, cell?.override_note ?? null)
           }
           className="underline underline-offset-2 hover:text-po-text"
         >
           usar conteo por archivos
         </button>
       </span>
     </div>
   )}
   ```
   **Tokens (verified against `tailwind.config.js`):** use `bg-po-suspect-bg` (= `var(--amber-a3)`),
   `text-po-suspect` (= `var(--amber-11)`), `border-po-suspect-border` (= `var(--amber-a7)`) — the
   same amber family as `Badge` tone `amber`. **Do NOT** use the Tailwind `/opacity` modifier on any
   `po-*` token (e.g. `bg-po-suspect/10`): those resolve to hex via CSS var and Tailwind cannot inject
   an alpha channel — the config comment bans it explicitly. The `-bg`/`-border` variants already carry
   the alpha.

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/FileList.jsx
git commit -m "feat(1b): inline amber hint to revert cell override to files count"
```

---

### Task 7: Verification — suite green + conducted smoke

**Files:** none (verification only).

- [ ] **Step 1: Full frontend suite + build**

Run: `cd frontend && npm test && npm run build`
Expected: all vitest tests PASS; build succeeds.

- [ ] **Step 2: Conducted smoke (chrome-devtools, SANDBOX data only)**

Drive the browser yourself (do not hand Daniel a checklist — see `feedback_browser_testing_via_devtools`). **Do NOT mutate a live month's real cells**; use a sandbox/throwaway session/month. Verify:
1. A cell counted by OCR (`confidence high`, no override) now shows an **amber** dot in the category list (was green).
2. Opening that cell: the **confidence badge is gone**; the toggle `Por archivos · Manual` is under the number with `archivos: N`.
3. Toggle → **Manual** focuses the field; typing a number updates the big number and the dot goes green (override).
4. Toggle → **Por archivos** clears the override; number returns to the files sum; dot returns to its provenance color.
5. With a cell override active, the **FileList shows the amber hint**; clicking "usar conteo por archivos" clears the override (hint disappears, mode back to Por archivos).
6. Typing `-5` in the manual field is **rejected** (error border, not saved); `0` is accepted.

Capture screenshots to `data/_smoke/` (already gitignored — commit `be319d1`). Create the dir first
if absent (`mkdir -p data/_smoke`), or `take_screenshot` fails on a missing parent.

- [ ] **Step 3: Tag the milestone**

```bash
git tag incremento-1b
```

(Push at end of round per the push-at-close convention; `git push origin po_overhaul --tags`.)

---

## Out of scope (do not implement here)

- `≤ páginas` cap → Incr 2 with persisted `per_file_pages` (RN forces it; Grupo J foundation).
- RN / "Aplicar R1" / block treatments → Incr 2.
- `count_type` applied to counting, keyboard counter, maquinaria=checks, F1 worker bug → Incr 3.
- Decoupled note-with-state (Grupo N), chip filter, docs≠pages color, viewer perf → Track B UX.
- Reorganization manifest (Grupo J), multiplayer (Grupo L), flavor authoring (Incr 4).
