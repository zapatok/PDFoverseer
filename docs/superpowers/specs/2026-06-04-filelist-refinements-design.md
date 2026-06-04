# FileList & CategoryRow refinements — design

**Date:** 2026-06-04
**Branch:** `po_overhaul` (work directly — single live branch convention)
**Scope:** 5 small UI refinements to the conteo-confiable review surface. Frontend-only, no backend changes.

## Context

Daniel reviewed the shipped conteo-confiable rev-2 surface in the live app and reported six findings. After triage, five are in scope here; one (clearing the near-match suspects list) is deferred. All five touch only the React frontend — no API, no DB, no scanner changes.

The affected components:
- `frontend/src/components/FileList.jsx` — the "Archivos" column (per-file rows: name, page count, doc count, origin chip).
- `frontend/src/components/CategoryRow.jsx` — the "Categorías" column (per-sigla rows: sigla, status dot, status chips, count).
- `frontend/src/components/DetailPanel.jsx` — the "Detalle" column (charla/chintegral worker-count module + near-match suspects section).

## Goals (the five changes)

### G1 — Stable column alignment in FileList

**Problem.** Each file row is its own independent CSS grid with `auto`-width tracks
(`grid grid-cols-[minmax(0,1fr)_auto_auto_auto_auto]`, FileList.jsx:87). `auto`
sizes each track to *that row's* content, so a 2-digit doc count, a present-vs-empty
compilation icon (~14px vs 0px), or a wider page count ("10pp" vs "1pp") shifts that
row's columns independently. Across the list the page-count, doc-count, and chip
columns drift and never line up.

**Design.** Replace the `auto` tracks with **fixed widths** so every row shares the
same column geometry:
- name: `minmax(0,1fr)` (unchanged — scrolls horizontally)
- page count: fixed width, right-aligned (fits "NNpp")
- compilation icon: fixed width, centered (the empty `<span/>` still occupies the track)
- doc count (`InlineEditCount`, already `w-14`): fixed width, right-aligned
- origin chip: fixed width sized for the widest label ("Pendiente"), left-aligned so
  chips line up on a common left edge

Result: page count / doc count / chip read as true vertical columns; a file that
differs (different page count, a 2-digit count, a suspect icon) jumps out instead of
nudging the layout.

### G2 — Pendiente shows "—", Revisar shows "0"

**Problem.** A "Pendiente" file (multipage filename-glob, not yet OCR'd) displays doc
count "1" — the filename-glob default — which reads as a real count when it is not.

**Design.** `InlineEditCount` already renders a placeholder when `value` is `null`
and stays editable (InlineEditCount.jsx:28). So:
- `origin === "Pendiente"` → pass `value={null}` + `placeholder="—"` → shows "—",
  still editable (typing a number → Manual override).
- `origin === "Revisar"` (OCR ran, read 0) → its `effective_count` is already `0`,
  so it shows "0" with no change. This is a genuine count ("scanned, found zero"),
  distinct from "—" ("not counted yet").
- All other origins → `effective_count ?? 1`, unchanged.

### G3 — Precedence sort in FileList

**Problem.** Files render in backend (filename) order, so attention-needing files
(pending, error) are scattered among trivial R1 files.

**Design.** Sort the *displayed* copy by an origin-precedence map; keep the source
`files` array intact so the lightbox index (`files.indexOf(f)`, FileList.jsx:92)
stays correct. Precedence (most-urgent first):

```
Error → Pendiente → Revisar → Manual → OCR → R1
```

Secondary sort by filename within each group (preserves chronology). Unknown origins
sort last.

### G4 — Remove status chips from CategoryRow; error becomes a red dot

**Problem.** The "Categorías" column carries status chips (Error, Manual,
Compilación) whose information already lives in the "Detalle" column once a sigla is
selected (the method table says scanned vs manual; the compilation flag shows there
too). The chips are redundant in the list, and Daniel wants that horizontal space
reserved for a future "a user is working here" presence chip (multiusuario phase).

**Design.**
- Remove the **Error**, **Manual**, and **Compilación** badges from CategoryRow
  (CategoryRow.jsx:71-81).
- Error state instead reads as a **red dot** next to the sigla. This is *already*
  wired: `dotVariantFor` returns `"state-error"` when `cell.errors` is non-empty
  (cell-status.js:22), and `Dot` maps `state-error` → `bg-po-dot-error` = `ruby-9`
  (Dot.jsx:6, tailwind.config.js:55). No new code for the dot — removing the Error
  chip simply lets the existing red dot stand as the sole error signal.
- The transient **"Escaneando…"** badge (shown only during an active scan,
  CategoryRow.jsx:67-68) is **kept** — it is live progress feedback, not a persistent
  status, and only occupies the space mid-scan.
- After removal, the row's trailing slot holds only the count (`InlineEditCount`),
  leaving room for the future presence chip.

**Out of scope (future):** the user-presence chip itself belongs to the multiusuario
phase — it needs a presence backend (WS broadcasting who is on each cell + cell
locking). This spec only frees the space.

### G5 — Worker-count button above the near-match suspects

**Problem.** In DetailPanel, the charla/chintegral worker-count module renders *after*
the near-match suspects section (DetailPanel.jsx:266-275). When a cell has many
near-matches (e.g. 60 candidate pages), the "Contar trabajadores" button is pushed far
below the fold, requiring a long scroll.

**Design.** Render the `WorkerCountModule` **before** the `NearMatchesSection` for
charla/chintegral. The worker button is a primary action; the suspects list is
secondary reference. Pure reorder — no logic change.

## Non-goals

- **#6 — clearing the suspects list (total + individual): deferred.** It needs a
  backend endpoint to mutate `cell.near_matches`, a store action, and per-row +
  bulk controls. Self-contained but heavier than this batch; revisit later.
- No backend, API, scanner, DB, or Excel changes.
- The user-presence chip is conceptual only here (multiusuario phase).

## Testing

Vitest is the unit harness for pure logic; the visual/layout changes are verified by
the live smoke (chrome-devtools).

- **G2:** unit-test a small pure helper that maps `(origin, effective_count)` →
  the value/placeholder passed to `InlineEditCount` (Pendiente → `{value: null,
  placeholder: "—"}`; Revisar → `{value: 0}`; others → `{value: effective_count}`).
- **G3:** unit-test the precedence comparator: a shuffled set of origins sorts to
  `Error, Pendiente, Revisar, Manual, OCR, R1`, with filename as tiebreak.
- **G1, G4, G5:** layout/structure — verified in the smoke (column alignment across
  rows; CategoryRow shows red dot + no chips for an error cell; worker button above
  the suspects list). No meaningful unit assertion beyond "component renders".

All tests run at the end (one batch: vitest + build), then a live smoke via
chrome-devtools on a real month (ABRIL). Commits are atomic, one per change, English
conventional-commit messages, Co-Authored-By "Claude Opus 4.8 <noreply@anthropic.com>".

## Files touched

| File | Change |
|------|--------|
| `frontend/src/components/FileList.jsx` | G1 fixed-width grid; G2 value/placeholder; G3 precedence sort |
| `frontend/src/lib/file-origin.js` (new) | G2 + G3 pure helpers (display value, precedence comparator) — node-testable |
| `frontend/src/components/CategoryRow.jsx` | G4 remove Error/Manual/Compilación chips |
| `frontend/src/components/DetailPanel.jsx` | G5 reorder worker module above near-matches |
| `frontend/src/lib/__tests__/file-origin.test.js` (new) | G2 + G3 unit tests |
