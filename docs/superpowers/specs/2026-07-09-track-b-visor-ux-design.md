# Track B — viewer + UX polish round — Design

**Date:** 2026-07-09
**Status:** DRAFT for review
**Author:** Claude (Fable 5) + Daniel
**Scope:** Frontend, plus one one-liner backend touch (month sort; none other).
**No counting change:** nothing in this spec alters `compute_cell_count`, per-file
state, Excel output, or history.

---

## Origin

The 2026-06-09 ideas triage (`docs/backlog/2026-06-09-ideas-triage.md`) approved
a "Track paralelo B — Pulido UX" — ~15 small items with design decisions already
recorded — that was never scheduled: no spec, plan, or commit exists for any of
them. Daniel hit the gap live on 2026-07-08 (slow page rendering, small
thumbnails, missing filters, rotation that doesn't straighten the view) and
added two new items: the **month-level manifest panel** (§7) and the
**DetailPanel reorder** that unburies the worker-count button (§6). Decision
2026-07-09: ship **all** of Track B in one round, plus the two new items, plus
the still-open M1 month-order bug.

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
  `page@scale@rotation` — the rotation term is `rotation ?? 0`, so this chunk
  is order-independent from §4 (which introduces the `rotation` prop on
  `PdfPage`; until it lands, every key carries `0`). Rendered output stored as
  `ImageBitmap` (fallback: dataURL) so re-showing a cached page is a
  synchronous draw.
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
  (placeholder `Ir a pág.`), Enter jumps (clamped), Esc blurs.
- **Input-focus guard — new work, not an existing rule.** `PDFLightbox`
  already ignores keys while an input has focus (`document.activeElement`
  check); **`WorkerCountViewer` does NOT** — its keydown handler deliberately
  captures every `[0-9]` keystroke into the worker-count digit buffer, and its
  own comment notes this is safe only *because the viewer has no inputs
  today*. Adding "Ir a página" (here) and the calculator (§8) introduces the
  first inputs, so the guard must be **built**: every WorkerCountViewer
  keydown handler (counting digits, nav, reorg gate) becomes a no-op while
  `document.activeElement` is an input/textarea. Explicit collision risk to
  test: typing `12` in "Ir a página" must NOT feed the count buffer.
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
  sums `rotation_deg` (mod 360) of all **pending** `rotate` ops for that cell
  whose `source.file` matches and whose `source.page_range` covers `page`.
  **A missing/`null` `page_range` means the whole file** — this is the common
  case: rotate ops created from FileList's `ReorgMenu` send `source: {file}`
  with no range; only viewer-reorg-mode ops carry `[start, end]` (1-based,
  inclusive). Non-pending (`applied`) ops contribute 0.
- **Healing assumption (stated, cross-project):** an op retires (`applied`)
  only when its `source.file` *name* disappears from the folder on a pase-1
  re-scan. This assumes paso-1's second pass renames when it rotates (its
  naming convention). If paso-1 ever rotates in place keeping the name, the
  op stays pending and the view would double-rotate — the operator's remedy
  is deleting the op; flagging evidence for `rotate` in the paso-1 contract
  is out of scope here.
- Application: pdf.js native `getViewport({ scale, rotation: base + extra })`
  where `base` is the page's own `/Rotate`. Applied in `PdfPage` (all three
  viewer surfaces) and in thumbnails.
- Plumbing: the parent viewers know `hospital`/`sigla`/`file` and the store's
  `reorg_ops` (already in the session payload consumed by
  `ReorganizacionPanel`). `WorkerThumbnails`/`Thumb` do **not** — instead of
  threading cell coords into the child, the parent passes a precomputed
  `rotationForPage(page) -> deg` prop; `Thumb` uses it for rendering and adds
  the degrees to its cache key (`page@rotation`), so a rotated page's
  thumbnail re-renders once instead of showing a stale orientation.

## 5 · FileList (E1 + E2 + E3 + D2)

- **Chip filter bar (E2):** a compact toggle row between the search input and
  the list — one toggle per origin in the canonical vocabulary
  (`R1`, `RN`, `OCR`, `Manual`, `Pendiente`, `Revisar`, `Error` — the
  `ORIGIN_VARIANT` keys), multi-select, combinable (AND) with the text search.
  Empty selection = no origin filter (today's behavior). Pure predicate
  `matchesFilters(file, search, activeOrigins)` in `lib/` (vitest). The footer
  count keeps showing `filtered de total`.
- **docs≠pages highlight (E3, triage: "versión sutil"):** when a file's
  effective count differs from its `page_count`, tint the count number (subtle
  text-tone change, no heavy background). Applies to both doc-counting cell
  types — `documents` **and** `documents_workers` (the `CAPPED_COUNT_TYPES`
  set: both carry a real per-file doc count comparable to pages); `checks`
  cells excluded.
- **Keep scroll position (E1 — triage marked *verificar*):** reproduce first;
  if saving a per-file override resets the list scroll, anchor/restore the
  scroll position across the refetch re-render. If it does not reproduce,
  record that in the plan and close the item.
- **Steppers (D2):** small always-visible `−`/`+` buttons beside the per-file
  count that save `current±1` through the existing per-file override path
  (same clamps: ≥0, and whatever cap behavior that path has — including the
  over-cap confirmation once `2026-07-09-conteo-session-fixes-design.md` §3
  ships; the steppers add no cap logic of their own). Thin layer, no new
  state.

## 6 · DetailPanel (D1 + reorder + collapsible reorg)

- **Section order becomes:** Ajuste manual → Nota → **Conteo de
  trabajadores/chequeos** (`WorkerCountModule` + `OrphanMarksPanel`) →
  **Reorganización** → Posibles colados. Rationale: the worker counter is a
  primary counting tool and today sits below a list that grows with every op.
- **Reorganización collapses:** the section renders as a disclosure
  (collapsed by default) whose header shows the pending-op count for the cell
  (e.g. `Reorganización · 3 ops`). Build it as a small reusable
  `frontend/src/ui/Disclosure.jsx` primitive (the project already centralizes
  its shared primitives there), keyboard-accessible (the ReorgMenu `<summary>`
  A11y lesson applies); ReorgMenu's existing ad hoc details/summary stays as
  is. The panel's per-cell content (in/out ops, delete, net delta) is
  unchanged — except the export button moves out (§7).
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
  **Known test migration:** `ReorganizacionPanel.test.jsx` asserts
  `data-testid="export-btn"` exists on the per-cell panel — §7 removes that
  button, so those assertions move to the new month-panel test (export button
  present + enabled there; per-cell panel asserts its absence). New guard
  test: the WorkerCountViewer input-focus rule (§3) — digits typed into
  "Ir a página"/calculator never reach the count buffer.
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
- The conteo-session fixes spec's items
  (`2026-07-09-conteo-session-fixes-design.md`: cap confirmation, forbid-extra,
  irl cover_code, presence) — the steppers here simply inherit whatever the
  override path does.
- Flavor-authoring viewer (Grupo G), badges (Grupo K) — separate tracks.
