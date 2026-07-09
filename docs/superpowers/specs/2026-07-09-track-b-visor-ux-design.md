# Track B — viewer + UX polish round — Design

**Date:** 2026-07-09
**Status:** DRAFT for review
**Author:** Claude (Fable 5) + Daniel
**Scope:** Frontend, plus two one-liner backend touches (month sort; none other).
**No counting change:** nothing in this spec alters `compute_cell_count`, per-file
state, Excel output, or history.

---

## Origin

The 2026-06-09 ideas triage (`docs/backlog/2026-06-09-ideas-triage.md`) approved
a "Track paralelo B — Pulido UX" — ~15 small items with design decisions already
recorded — that was never scheduled: no spec, plan, or commit exists for any of
them. Daniel hit the gap live on 2026-07-08 (slow page rendering, small
thumbnails, missing filters, rotation that doesn't straighten the view) and
added two new items. Decision 2026-07-09: ship **all** of Track B in one round,
plus the two new items, plus the still-open M1 month-order bug.

Where the triage recorded a decision, this spec restates it as the authority —
implementation must not re-litigate those decisions.

---

## 1 · Viewer performance (the "lentísimo" item)

**Current state:** `PdfPage.jsx` renders only the current page, cold, on a
canvas, and frees it on every page change — no look-ahead, no cache, no
placeholder. Exactly the state the triage diagnosed ("NO está en su techo").

**Design (triage decision, verbatim intent):** pre-render window + bounded
cache + instant placeholder.

- **Page cache:** a per-document LRU holding ~5 rendered pages, keyed by
  `page@scale@rotation`. Rendered output stored as `ImageBitmap` (fallback:
  dataURL) so re-showing a cached page is a synchronous draw.
- **Pre-render window:** after the current page renders, queue `current ±1`
  then `±2` (clamped to `[1, pageCount]`) at the same scale, low priority
  (idle callback / after paint), cancellable on page change. A pure helper
  `prerenderOrder(current, pageCount, radius=2) -> number[]` (vitest-tested)
  defines the order.
- **Instant placeholder:** while a non-cached page renders, show the thumbnail
  for that page from the existing `THUMB_CACHE` (WorkerThumbnails), upscaled
  and slightly blurred, swapped for the crisp canvas when the render lands.
  No thumbnail cached → keep today's blank + spinner behavior.
- **Cancel semantics preserved:** the existing render-task cancel on
  page/scale change stays; pre-renders are cancelled the same way.
- **Zoom:** manual zoom changes the scale key — cache misses re-render (the
  window re-primes at the new scale). Accept the miss; no multi-scale cache.

Consumers: `WorkerCountViewer` and `PDFLightbox` (both render through
`PdfPage`); `PdfCoverViewer` benefits for free.

## 2 · Thumbnails: +20% and centered (I1 + I2)

- `WorkerThumbnails.jsx`: `THUMB_WIDTH` 92 → **110** px raster; column
  `w-28` → **`w-32`**. Serves both viewers (PDFLightbox reuses the component).
- Autoscroll: `scrollIntoView({ block: "center" })` (today `"nearest"`), so the
  active thumbnail stays mid-column and the upcoming pages are visible.
- The thumbnail cache key gains the rotation term (§4) — a rotated page's thumb
  re-renders once instead of showing stale orientation.

## 3 · Viewer navigation (I4 + I5 + I6)

- **Shift+PageDown / Shift+PageUp = ±10 pages** in both paged viewers
  (WorkerCountViewer, PDFLightbox), clamped. Plain PageDown/PageUp keep their
  current single-page behavior; the counting-mode PageDown (fix-and-advance)
  keeps precedence in WorkerCountViewer — Shift only jumps, never counts.
- **"Ir a página":** a small numeric input in each viewer's toolbar
  (placeholder `Ir a pág.`), Enter jumps (clamped), Esc blurs. Existing rule
  honored: counting/nav shortcuts are ignored while focus is in an input.
- **Near-match viewer (I6):** `PdfCoverViewer` gains optional prev/next.
  Contract: DetailPanel passes the near-match list index context
  (`onPrev`, `onNext`, `positionLabel` e.g. `"2 de 5"`); the dialog header
  renders ‹ › buttons + the label when provided (single-item usage stays
  exactly as today — props optional). ArrowLeft/ArrowRight navigate while open.

## 4 · Rotation straightens the view (I7, scoped per 2026-07-09 decision)

Creating a `rotate` reorg op today only records the manifest operation — the
viewer keeps showing the page sideways. Decision: **pending rotate ops drive
display rotation**; no separate view-only rotation state (that half of the
original I7 was dropped — one state, one source of truth).

- Pure helper in `frontend/src/lib/` (vitest-tested):
  `pageRotation(reorgOps, hospital, sigla, file, page) -> 0|90|180|270` —
  sums `rotation_deg` (mod 360) of all **pending** `rotate` ops whose
  `source.file` matches and whose `source.page_range` covers `page`, for that
  cell. Non-pending (`applied`) ops contribute 0 — when paso-1 physically
  rotates the file and the op retires on re-scan, the view heals to natural
  automatically.
- Application: pdf.js native `getViewport({ scale, rotation: base + extra })`
  where `base` is the page's own `/Rotate`. Applied in `PdfPage` (all three
  viewer surfaces) and `WorkerThumbnails` (rotation term in the cache key).
- Plumbing: viewers already know `hospital`/`sigla`/`file`; `reorg_ops` come
  from the session store (already in the session payload consumed by
  `ReorganizacionPanel`).

## 5 · FileList (E1 + E2 + E3 + D2)

- **Chip filter bar (E2):** a compact toggle row between the search input and
  the list — one toggle per origin in the canonical vocabulary
  (`R1`, `RN`, `OCR`, `Manual`, `Pendiente`, `Revisar`, `Error` — the
  `ORIGIN_VARIANT` keys), multi-select, combinable (AND) with the text search.
  Empty selection = no origin filter (today's behavior). Pure predicate
  `matchesFilters(file, search, activeOrigins)` in `lib/` (vitest). The footer
  count keeps showing `filtered de total`.
- **docs≠pages highlight (E3, triage: "versión sutil"):** when a documents-cell
  file's effective count differs from its `page_count`, tint the count number
  (subtle text-tone change, no heavy background). Documents-type cells only.
- **Keep scroll position (E1 — triage marked *verificar*):** reproduce first;
  if saving a per-file override resets the list scroll, anchor/restore the
  scroll position across the refetch re-render. If it does not reproduce,
  record that in the plan and close the item.
- **Steppers (D2):** small always-visible `−`/`+` buttons beside the per-file
  count that save `current±1` through the existing per-file override path
  (same clamps: ≥0, cap → the Spec-B confirmation flow). Thin layer, no new
  state.

## 6 · DetailPanel (D1 + reorder + collapsible reorg)

- **Section order becomes:** Ajuste manual → Nota → **Conteo de
  trabajadores/chequeos** (`WorkerCountModule` + `OrphanMarksPanel`) →
  **Reorganización** → Posibles colados. Rationale: the worker counter is a
  primary counting tool and today sits below a list that grows with every op.
- **Reorganización collapses:** the section renders as a disclosure
  (collapsed by default) whose header shows the pending-op count for the cell
  (e.g. `Reorganización · 3 ops`). Keyboard-accessible (the ReorgMenu
  `<summary>` A11y lesson applies). The panel's per-cell content (in/out ops,
  delete, net delta) is unchanged — except the export button moves out (§7).
- **Select-on-focus (D1):** the override input in `OverridePanel` and the
  inline cell count (`InlineEditCount`) select their content on focus, so
  typing overwrites immediately.

## 7 · Month-level manifest panel (new item, 2026-07-09)

The backend export (`POST …/reorg/export`) is already session-wide; only the
button lives buried inside each cell's panel, which reads as per-cell.

- **New "Reorganización del mes" panel** opened from the `MonthOverview`
  header (button beside "Generar Excel", with a badge = total pending ops in
  the session; hidden/disabled state when 0). Content: all pending ops grouped
  by `hospital · sigla`, each row reusing the per-cell op-row rendering
  (description + delete), plus the single **"Exportar manifiesto"** button
  (existing store action `exportManifest(sessionId)`, unchanged backend).
- **The per-cell `ReorganizacionPanel` loses its export button** (list +
  delete + net delta stay). One export surface, month-scoped, as requested:
  "un solo lugar donde exporte todos los cambios".
- Presentation: Radix dialog/drawer consistent with existing panels (po-*
  tokens); ops listing needs no new API (ops already ride the session payload).

## 8 · Calculator (I8)

Collapsible mini-calculator in the WorkerCountViewer right column (triage:
"barra colapsable, minimalista + − × ÷, manejable por teclado"). Collapsed by
default; expanded state is a simple expression input + result (pure evaluator
helper in `lib/`, vitest-tested — digits, `+ - * /`, parentheses, decimal
point; no `eval`). Focus isolation per the existing rule: while its input has
focus, viewer/counting shortcuts are inert.

## 9 · Months in chronological order (M1)

`api/routes/months.py::list_months` sorts by folder name (alphabetical:
ABRIL, JUNIO, MAYO). Fix: sort the assembled list by `(year, month)`. One
line + a unit test with shuffled month folders.

---

## 10 · Testing & gates

- **vitest:** every pure helper above (`prerenderOrder`, `pageRotation`,
  `matchesFilters`, calculator evaluator) + store-level flows where the
  harness exists (chip filters, go-to-page clamp). Component tests follow the
  existing patterns (mock pdfjs like `DetailPanel.reorgLoop.test.jsx`).
- **pytest:** months sort test. Nothing else server-side.
- **Live smoke (Brave via chrome-devtools MCP, isolated copy DB):** thumbnails
  larger + centered; fast page flipping on a big PDF (cache visibly hot);
  Shift+PageDown jumps 10; ir-a-página; a rotate op straightens the view and
  the thumbnail; chip filters; reorder + collapsed reorg; month panel export
  writes the manifest; months chronological.
- **Gates:** vitest green, fast pytest green, ruff 0, `npm run build` OK.
  Bundle size not a gate (single-user LAN app).

## 11 · Out of scope

- Everything discarded in the triage stays discarded (D3 direct-type-in-viewer,
  F5 subtotals).
- M2 hospital-card worker indicator — already shipped (Incr 3C).
- View-only rotation without a manifest op (dropped half of I7).
- Spec B items (cap confirmation UI arrives with Spec B; the steppers here
  simply inherit whatever the override path does).
- Flavor-authoring viewer (Grupo G), badges (Grupo K) — separate tracks.
