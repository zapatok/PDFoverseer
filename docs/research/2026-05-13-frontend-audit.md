# Frontend Audit — PDFoverseer FASE 2 MVP

**Date:** 2026-05-13
**Branch:** `po_overhaul`
**Scope:** Critique-and-design direction only. No code changes in this pass.

The product owner just landed FASE 2 and called the UI "como algo entregado por un junior", citing the Windows-3.1 warning triangles as the most visible offender. This audit reads every file under `frontend/src/`, names what's broken or shallow, and proposes a concrete design direction the next implementation pass can execute against.

The goal is **modern, professional, serious** — not playful, not flashy. The target user (Daniel) runs this once a month against a fixed corpus he has audited by hand for years. He needs a tool that signals trust on every cell, not a dashboard that competes for his attention.

---

## 1. Inventory

### `frontend/src/views/`

| File | What it does | Verdict |
|------|---|---|
| `MonthOverview.jsx` | Month picker + Escanear/Generar buttons + 4 hospital cards. The home screen. | **Restructure** — flat layout, button labels weak, cards lack hierarchy, the "MES" + "Hospitales" sections compete instead of stacking like a workflow. |
| `HospitalDetail.jsx` | Three-column layout: Categorías list / Detalle of selected cell / Archivos picker. The screen Daniel spends 95% of his time on. | **Restructure** — the three columns each look like a different app. Categorías is a flat list of 18 rows with no grouping; Detalle is a stack of plain `<p>` tags with `Sigla:` / `Filename:` etc. ; jargon leaks (`compilation_suspect`, `filename_glob`). |

### `frontend/src/components/`

| File | What it does | Verdict |
|------|---|---|
| `CategoryRow.jsx` | The single-row primitive used 18× per hospital screen. Checkbox + sigla + confidence text + count + status icons (`⟳ ✕ ⚠`). | **Replace** — this is the most-seen widget in the app and the worst-looking one. See §4. |
| `ConfidenceBadge.jsx` | Map of `{high, medium, low, manual}` → border+bg colors, returns an `<span>`. **Currently unused** — `CategoryRow` renders confidence as bare uppercase text instead of using this component. | **Keep + actually use** — needs new color palette and to be wired in everywhere. |
| `HospitalCard.jsx` | Big tile on home: hospital code + count + "total documentos" footer, dimmed for `missing` hospitals. | **Restructure** — empty state ("no normalizado" / "—") gives zero affordance; no visual indication of scan freshness; numbers and labels not typographically distinct enough to read at a glance. |
| `FileList.jsx` | Search input + list of PDFs in the selected cell. `pp` page count, amber `⚠` for suspect. | **Restructure** — `font-mono` for the entire filename is hard to skim; `· {n}pp` looks ad-hoc; no row affordance that it's a clickable link to the PDF viewer. |
| `OverridePanel.jsx` | Number input + textarea, autosave on blur. | **Restructure** — no save feedback whatsoever; inline horizontal `Override:` label is amateur; no indication this is the source of truth that overrides everything else. |
| `PDFLightbox.jsx` | Modal: iframe of `/pdf` endpoint on the left, 320px counts+override sidebar on the right. | **Restructure** — header is a single `font-mono` line that smashes hospital, sigla, and filename together; the right sidebar duplicates the Detalle panel's information without resolving the same jargon issues. |
| `ScanControls.jsx` | Two buttons: "OCR N seleccionadas" / "OCR suspects de {hospital}". | **Restructure** — labels mix Spanish and English (`suspects`), counter wording is wrong when 0/1, and the primary vs secondary distinction is encoded only by color, not size or position. |
| `ScanProgress.jsx` | Fixed bottom bar showing `done/total` + bar + Cancel button. | **Keep, polish** — actually one of the better-shaped components; needs ETA display, smoother color transitions, an icon, and the Cancel button needs a proper destructive style. |
| `ScanIndicator.jsx` | Unicode glyph status indicator (`○ ● ✓ ⚠ ✕ ✎`). **Currently unused** — never imported anywhere. | **Delete or replace with icon component** — if status indicators are reintroduced they must come from a real icon library. |
| `HeaderBar.jsx` | 200-line top bar from a prior iteration: file-open dropdown, play/pause/stop/skip transport, history. References `bg-surface`, `bg-panel`, `bg-accent` colors that don't exist in `tailwind.config.js`. **Not imported anywhere.** | **Delete** — dead code. |
| `Sidebar.jsx` | Left-rail PDF list with per-file confidence dot from the legacy app. **Not imported.** | **Delete** — dead code. |
| `ProgressBar.jsx` | Top-of-app progress strip with ETA, also references the phantom `bg-accent` palette. **Not imported.** | **Delete** — dead code. |
| `README.md` | Describes `IssueInbox`, `CorrectionPanel`, `Terminal`, `ConfirmModal`, `HistoryModal` — none of which exist. | **Delete and rewrite** — completely stale. |

### `frontend/src/lib/` and `store/`

| File | Verdict |
|------|---|
| `lib/api.js` | **Keep** — clean fetch wrappers. |
| `lib/ws.js` | **Keep** — pairs with the store. |
| `lib/constants.js` | **Restructure** — `SPINNER`, `IMPACT_LABELS`, `formatTime` are all dead carryover from the previous app. Only `API_BASE` / `WS_BASE` are still used. |
| `store/session.js` | **Keep** — well-structured, no design issues. |

**Dead-code total: 4 components (HeaderBar, Sidebar, ProgressBar, ScanIndicator) + most of `constants.js` + the README.** Removing it is half the visual cleanup — the visual debt is partly inherited from a pivot that was never finished.

---

## 2. UX Weaknesses Table

| Location | What's wrong | Why it's bad | Severity |
|---|---|---|---|
| `App.jsx:13-14` | App title is "PDFoverseer" + subtitle "FASE 2" | "FASE 2" is a project-management term leaking to the UI. Reads as unfinished software. | **P1** |
| `CategoryRow.jsx:35` | Confidence rendered as bare uppercase text (`LOW`, `HIGH`) — same color as everything else | The most important quality signal in the app is invisible. `ConfidenceBadge` already exists but isn't used. | **P0** |
| `CategoryRow.jsx:37-39` | Status indicators are literal Unicode glyphs: `⟳ ✕ ⚠` | These render as system emoji on Windows and look like Windows 3.1. Daniel called them out specifically. | **P0** |
| `CategoryRow.jsx` overall | 18 siglas rendered as a flat single-column list, no grouping | The two scan regimes (normalized vs compilation) are the central mental model of the product. Burying them in a flat list throws away the workflow. | **P1** |
| `HospitalDetail.jsx:84-107` | Detalle panel renders metadata as 5 stacked `<p>` tags with inline labels (`Sigla:`, `Filename:`, `OCR:`, `Confidence:`, `Flags:`) | Reads like a debug print. No visual hierarchy, no way to scan for the answer. Daniel needs to see *the number* and *whether to trust it* — those should be the two largest elements. | **P1** |
| `HospitalDetail.jsx:96-98` | `<span class="text-xs text-slate-500">via {selectedCell.method}</span>` — renders internal token `filename_glob` | Engineering jargon in user-facing copy. Daniel doesn't think in terms of method names. | **P0** |
| `HospitalDetail.jsx:103-107` | Flags rendered as comma-joined raw token list: `compilation_suspect, ocr_disagreement` | Raw enum names leaking to UI. | **P0** |
| `HospitalDetail.jsx:84, 113-115` | Three empty-state panels say only "Selecciona una categoría" | No guidance for first-time use, no preview of what will appear, no hint at scope. | **P1** |
| `HospitalCard.jsx:16-19` | HLL renders as "no normalizado" + "—" with no actionable next step | Empty state with no call-to-action. User left wondering what to do. | **P1** |
| `OverridePanel.jsx` | No save feedback (no toast, no checkmark, no inline indicator) | Autosave-on-blur is invisible. Daniel can't tell if his override took. Same complaint Daniel logged for past projects (`feedback_incomplete_root_cause_investigation`). | **P0** |
| `OverridePanel.jsx:25,36` | Inline "Override:" / "Nota:" labels with no description of what an override does | Override is the load-bearing manual correction primitive of FASE 2. It deserves more than a horizontal label. | **P1** |
| `ScanControls.jsx:30,37` | Button labels "OCR 0 seleccionadas" and "OCR suspects de HPV" | Counter wording wrong when 0 (should be disabled/different copy); `suspects` is English in a Spanish UI; "OCR" abbreviation reads cold. | **P1** |
| `ScanProgress.jsx` | Cancel button uses `bg-slate-700` — same chrome as decorative chips | Destructive action with no destructive affordance. | **P2** |
| `ScanProgress.jsx:9-18` | `terminal === "complete"` and `"cancelled"` collapse to a label change; no icon | Color-only signaling. Fails for colorblind users; reads as a chrome change, not a status change. | **P2** |
| `FileList.jsx:58-64` | `<button>` row with entire filename in `font-mono`, count appended `· {n}pp`, sometimes `⚠` | Filenames are ~50 chars in the corpus (date_sigla_subject). Mono font + no truncation makes the list visually noisy. | **P1** |
| `PDFLightbox.jsx:56-60` | Header line concatenates `{hospital} / {sigla} · {filename}` in `font-mono` | No hierarchy; filename can be longer than the lightbox is wide. | **P1** |
| `PDFLightbox.jsx:75-87` | Right panel ("Counts") duplicates Detalle panel's structure with the same jargon (`via {method}`) | Two surfaces, same UX bug. | **P0** (because it propagates the Detalle issue) |
| `MonthOverview.jsx:55-72` | Two action buttons ("Escanear todo" + "Generar Resumen") sit in a flat row with no separation | These are sequential workflow steps; presenting them as equals invites users to click Generar before scanning. | **P1** |
| `MonthOverview.jsx:38-48` | Month buttons are a flat row of equal-weight chips | The active month is indicated only by indigo fill. No "you are here" hierarchy. | **P2** |
| `App.jsx:11` | Background `bg-slate-950` against `slate-100` text — fine, but never extended into a real palette | The whole app uses ad-hoc `slate-800/700/900` mixes. No semantic tokens. Every card chooses its own border. | **P1** |
| Global | No icon library at all; six unicode glyphs (`⟳ ✕ ⚠ ✎ ○ ●`) hand-placed | This is the symptom Daniel led with. Single biggest visible upgrade we can do. | **P0** |
| Global | No loading skeletons, no toast system, no tooltip primitive | Every interaction lacks state feedback. | **P1** |
| `index.css:5-33` | Two scrollbar styles defined globally (`::-webkit-scrollbar` + `.custom-scroll`), neither applied via class anywhere | Dead CSS. | **P2** |
| `components/README.md` | Describes a different application entirely | Stale documentation actively misleads. | **P2** |
| Dead components | `HeaderBar.jsx`, `Sidebar.jsx`, `ProgressBar.jsx`, `ScanIndicator.jsx` all unused | Confuses contributors and reviewers. Reference colors (`bg-surface`, `bg-accent`) that don't exist. | **P2** |

---

## 3. Design System Recommendation

### 3.1 Color tokens

Stay in dark mode. The existing slate ramp is fine as the canvas but needs **semantic tokens** layered on top so confidence, scan state, and override state each have a fixed visual identity.

Extend `tailwind.config.js` with named colors instead of letting each component pick its own slate shade:

```js
// tailwind.config.js theme.extend.colors
{
  // canvas
  canvas: { DEFAULT: '#0b0f14', raised: '#11161d', sunken: '#070a0e' },
  // hairlines
  hairline: { DEFAULT: 'rgba(255,255,255,0.06)', strong: 'rgba(255,255,255,0.12)' },
  // semantic — see mapping below
  confidence: {
    high:   { fg: '#86efac', bg: 'rgba(34,197,94,0.10)',  border: 'rgba(34,197,94,0.28)'  }, // emerald 300
    medium: { fg: '#fde68a', bg: 'rgba(245,158,11,0.10)', border: 'rgba(245,158,11,0.28)' }, // amber 200
    low:    { fg: '#fca5a5', bg: 'rgba(244,63,94,0.10)',  border: 'rgba(244,63,94,0.28)'  }, // rose 300
  },
  state: {
    scanning:   { fg: '#93c5fd', bg: 'rgba(59,130,246,0.10)' }, // sky 300
    suspect:    { fg: '#fcd34d', bg: 'rgba(234,179,8,0.10)'  }, // amber 300
    error:      { fg: '#fda4af', bg: 'rgba(244,63,94,0.12)'  },
    override:   { fg: '#c4b5fd', bg: 'rgba(139,92,246,0.10)' }, // violet 300
    success:    { fg: '#86efac', bg: 'rgba(34,197,94,0.10)'  },
    muted:      { fg: '#64748b' }, // slate-500
  },
  accent: { DEFAULT: '#6366f1', hover: '#4f46e5' }, // keep indigo as the brand action
}
```

Key principle: **confidence and state are different axes.** A high-confidence cell can also be scanning. Don't collapse them into one badge color. The current code already conflates them (`isSuspect && !isScanning && <⚠>`).

Tailwind class examples after extension:
- High confidence pill: `bg-confidence-high-bg text-confidence-high-fg border border-confidence-high-border`
- Compilation-suspect chip: `bg-state-suspect-bg text-state-suspect-fg`
- Override badge: `bg-state-override-bg text-state-override-fg`

### 3.2 Typography

Current state: every text element is a one-off — `text-lg font-semibold`, `text-3xl font-bold`, `text-xs uppercase tracking-widest`, scattered `font-mono` for filenames and sigla. No scale.

Propose a fixed scale, used semantically:

| Token | Class | Use |
|---|---|---|
| `display`  | `text-4xl font-semibold tracking-tight` | The big count on `HospitalCard`. Tabular numerals (`tabular-nums`). |
| `title`    | `text-xl font-semibold` | Page titles (`HPV`, `MonthOverview` "Hospitales"). |
| `subtitle` | `text-sm font-medium uppercase tracking-wider text-slate-500` | Section labels (`CATEGORÍAS`, `DETALLE`, `ARCHIVOS`). |
| `body`     | `text-sm text-slate-200` | Default. |
| `meta`     | `text-xs text-slate-500` | Footnotes, byline, "{n} de {m}". |
| `mono`     | `font-mono text-xs text-slate-300` | **Only filenames and sigla codes** — not labels, not numbers. |

Drop `uppercase` from sigla in CategoryRow — `irl`, `odi`, `art` already function as identifiers; uppercasing them in the row but lowercase elsewhere creates inconsistency.

Use a single sans for everything except sigla/filenames. Inter or Geist; the system stack `ui-sans-serif, system-ui` is fine if no font hosting is desired. Numerals need `font-variant-numeric: tabular-nums` everywhere a count appears so columns line up.

### 3.3 Spacing

Tailwind defaults are fine. Tighten the implicit grid: **everything aligns to 4/8/12/16/24**. Current code uses `gap-2 px-2 py-1` inside `gap-4` containers inside `p-6` pages — every level slightly off. Standardize to a 4px base. No bespoke pixel values.

### 3.4 Iconography (critical)

**Recommendation: lucide-react.**

| Library | Pros | Cons | Verdict |
|---|---|---|---|
| **lucide-react** | 1300+ icons, MIT, tree-shakeable, consistent 24px stroke, the de-facto modern default (used by shadcn/ui, Vercel, Linear-style UIs), maintained, TypeScript-ready | Slightly more bundled if you import a lot | **Pick this.** |
| heroicons | Curated, two weights (outline/solid), official Tailwind ally | Smaller set; less expressive when you need niche icons (e.g. "stack of pages") | Second choice if 1300 is overkill |
| phosphor-react | Six weights, beautiful | Looks editorial/playful by default; weights make discipline harder; 6× the surface area | Reject — wrong feel for "serious tool" |
| tabler-icons | Free, large set | Stroke geometry a hair less consistent than lucide; less mainstream | Reject — no advantage over lucide |

Pin `lucide-react@^0.400.0`. Use a single stroke width across the app (`strokeWidth={1.75}`) and a single base size (16 for inline-with-text; 20 for buttons; 24 for empty-state hero icons).

**Mapping current placeholders → lucide:**

| Current | Lives in | Replace with |
|---|---|---|
| `⟳` (scanning pulse) | `CategoryRow.jsx:37` | `<Loader2 className="animate-spin" />` |
| `✕` (error) | `CategoryRow.jsx:38`, `ScanIndicator.jsx`, `PDFLightbox.jsx:62` close | `<AlertCircle />` for error state; `<X />` for the lightbox close |
| `⚠` (compilation_suspect) | `CategoryRow.jsx:39`, `FileList.jsx:63`, `ScanIndicator.jsx` | `<FileStack />` — visually communicates "multiple docs bound together", which is what compilation_suspect *means*. Reserve `<AlertTriangle>` for *errors*, not for the normal "this looks like a compilation" signal. |
| `✓` (done_high) | `ScanIndicator.jsx` | `<CheckCircle2 />` |
| `○` `●` (pending/scanning) | `ScanIndicator.jsx` | `<Circle />` / `<Loader2 />` |
| `✎` (manual) | `ScanIndicator.jsx` | `<Pencil />` |
| "←" back button | `HospitalDetail.jsx:54` | `<ArrowLeft />` |
| month picker, hospital card | no current icon | `<Calendar />` / `<Building2 />` |
| Escanear todo | `MonthOverview.jsx:60` | `<Scan />` or `<RefreshCw />` |
| Generar Resumen | `MonthOverview.jsx:70` | `<FileSpreadsheet />` (specifically xlsx semantic) |
| Override active | new | `<PenLine />` |
| File row | `FileList.jsx` | `<FileText />` |

**The single most important swap** is `⚠` → `<FileStack />` in `CategoryRow`. That one change solves the Windows 3.1 critique and *also* makes the semantic meaning more readable (a stack of papers reads as "compilation", which is exactly what `compilation_suspect` means).

### 3.5 Component primitives needed

Build a tiny in-house primitive set under `frontend/src/ui/`. **Do not adopt a full headless lib** (radix, react-aria, headlessui) for this scope — the surface is six small primitives and a dropdown might be the only one that actually benefits from a11y plumbing. Building them inline keeps the bundle small and the styling unambiguous.

Required primitives:

1. **`Badge`** (`ui/Badge.jsx`) — replaces `ConfidenceBadge` and absorbs the suspect/scanning/override pills. Variant prop drives color. Optional `icon` prop.
2. **`SaveIndicator`** (`ui/SaveIndicator.jsx`) — small inline component: idle / saving / saved (auto-fades after 2s) / error. Used by OverridePanel. State as Zustand-driven prop.
3. **`EmptyState`** (`ui/EmptyState.jsx`) — icon + headline + body + optional action. Used in Detalle / Archivos / HospitalCard-missing.
4. **`Tooltip`** (`ui/Tooltip.jsx`) — pure CSS + `data-tooltip` if we want zero deps, or `@radix-ui/react-tooltip` if a11y matters more than bundle size (≈ 12 kB gzipped, acceptable). Recommend radix for this one only.
5. **`Skeleton`** (`ui/Skeleton.jsx`) — animated `bg-canvas-raised` rectangle. Replaces "Cargando…" text in FileList/PDFLightbox.
6. **`ProgressBar`** (replace existing `ScanProgress.jsx` internal markup) — same shape, but stripe pattern + smooth easing, ETA shown.

For dropdowns / popovers (month picker doesn't need them right now), defer until needed.

---

## 4. Per-Component Redesign Sketches

### 4.1 HospitalCard

Today: `border + p-4 + flex justify-between` with a large count and `"total documentos"` underline. Disabled state is "—" + "no normalizado" and 50% opacity.

**Redesign — present state:**

```
┌──────────────────────────────────────────────┐
│ <Building2 16/>  HPV                  · 14h  │  ← title row; trailing "scanned 14h ago"
│                                              │
│        1 983                                 │  ← display-scale tabular-nums
│        documentos detectados                 │  ← meta
│                                              │
│ ●●●●●●●○○                                    │  ← 18 dots, one per categoría, color = confidence
└──────────────────────────────────────────────┘
```

Concretely:
- Container: `rounded-xl bg-canvas-raised border border-hairline p-5 hover:border-hairline-strong transition`
- Title row: `<Building2 size={16} className="text-slate-500" />` + `<h3 class="text-sm font-medium text-slate-300">HPV</h3>` + right-aligned `<span class="text-xs text-slate-500">hace 14 h</span>` (timestamp from `session.scanned_at`).
- Count: `<p class="text-4xl font-semibold tabular-nums mt-3">{total}</p>`
- Subtitle: `<p class="text-xs text-slate-500 mt-0.5">documentos detectados</p>`
- **New: 18-dot confidence ribbon** at the bottom. Each dot is `h-1.5 w-1.5 rounded-full` colored by that category's confidence. Gives Daniel instant per-hospital "where do I need to look" telemetry without leaving the home screen.

**Empty state for HLL (no folder):**

```
┌──────────────────────────────────────────────┐
│ <Building2 16/>  HLL                         │
│                                              │
│ <FolderX 32/>                                │
│ Sin carpeta normalizada                      │
│ HLL no entrega PDFs por carpeta en abril.    │
│ [Ingresar conteo manualmente]                │
└──────────────────────────────────────────────┘
```

`<FolderX>` (lucide) + an action button that drops the user into an override-only flow for HLL's 18 cells. The point is to **make the empty state actionable**.

### 4.2 CategoryRow (the most-seen widget)

Today:

```
☐ irl              LOW   141  ⚠
```

Tight, hard to scan, and the warning triangle is an emoji.

**Redesign:**

```
┌─────────────────────────────────────────────────────────────────────┐
│ ☐  irl                       141  [LOW]  [<FileStack/> Compilación] │
│    Charlas integrales        ─    ─                                 │
└─────────────────────────────────────────────────────────────────────┘
```

Two-line row (`py-2.5`). Top line: checkbox + monospace sigla + right-aligned count (tabular-nums, `w-14 text-right`) + confidence pill + optional state pills. Second line: human-readable category description (`text-xs text-slate-500`), e.g. "Charlas integrales", "Inspección reglamentaria de luminarias" — maintain a static map sigla→label in `lib/constants.js`.

Pills (all from the new `Badge` primitive):

- **Confidence pill** — `<Badge variant="confidence-low">Baja</Badge>` → `bg-confidence-low-bg text-confidence-low-fg border border-confidence-low-border rounded-full px-2 py-0.5 text-[11px] font-medium`. Spanish copy: `Alta / Media / Baja`. Removes the all-caps shouting.
- **Compilation pill** — `<Badge variant="state-suspect" icon={FileStack}>Compilación</Badge>`. Replaces the bare amber triangle entirely. Word + icon = unmistakable.
- **Scanning state** — *replaces* the trailing icons row: when `isScanning`, swap the whole right-side block for a single pill `<Badge variant="state-scanning" icon={Loader2}>Escaneando…</Badge>`. Don't pile pills on top of a spinning icon.
- **Error state** — pill `<Badge variant="state-error" icon={AlertCircle}>Error</Badge>` with the error string in a tooltip.
- **Override state** — when `cell.user_override !== null`, replace confidence pill with `<Badge variant="state-override" icon={PenLine}>Manual: 141</Badge>`.

Row hover: `bg-canvas-raised`. Selected: `bg-canvas-raised border-l-2 border-accent`. Drop the cursor-pointer on the row when the row also has a checkbox — separate the click target for the checkbox (`stopPropagation` already there).

**Grouping (the big restructure):** group the 18 siglas into two collapsible sections:

```
NORMALIZADAS  (15)                                      [▼]
   reunion         12   [Alta]
   odi             89   [Alta]
   ...
COMPILACIONES (3)                                       [▼]
   art             18   [Baja]  [<FileStack> Compilación]
   chintegral      32   [Media] [<FileStack> Compilación]
   chps             5   [Baja]  [<FileStack> Compilación]
```

The grouping criterion is `cell.flags.includes("compilation_suspect")`. This is the central mental model of the product (`project_pdfoverseer_purpose` in memory) and the UI should mirror it directly. Compilation suspects are the ~10% of work; having them as their own section means "OCR suspects de HPV" can become a single button at the section header — see microcopy.

### 4.3 Detalle panel (with OverridePanel inside)

Today: stacked `<p>` tags reading `Sigla:` / `Filename: 2` / `OCR: 2 via filename_glob` / `Confidence: low` / `Flags: compilation_suspect`. Then a tiny inline override input.

**Redesign:**

```
┌────────────────────────────────────────────────┐
│ irl  ·  Inspección reglamentaria de luminarias │   ← title
│ ────────────────────────────────────────────── │
│                                                │
│            141                                 │   ← display number
│            documentos                          │
│   [<FileStack/> Compilación]   [Baja]          │   ← state pills
│                                                │
│ Conteo automático                              │   ← subhead
│ ─────────                                      │
│ Por nombre de archivo            2             │
│ Por OCR                          2             │
│ Método                           Nombre        │   ← was "via filename_glob"
│                                                │
│ Ajuste manual                                  │   ← subhead, was "Override:"
│ ─────────                                      │
│ [   141   ]   <SaveIndicator/>                 │   ← number input + save state
│                                                │
│ ┌──────────────────────────────────────────┐   │
│ │ Nota (opcional)…                         │   │
│ └──────────────────────────────────────────┘   │
└────────────────────────────────────────────────┘
```

Concrete:
- Title block: sigla in `font-mono`, separator dot, human label in regular sans. `text-base font-medium`.
- Headline number: `text-5xl font-semibold tabular-nums` — the answer to "how many?" should be the largest text on screen. Computed via the existing `user_override ?? ocr_count ?? filename_count ?? count` cascade.
- Source breakdown table: two-column key-value, dot-leader optional, right-aligned values, tabular-nums.
- "Método" row shows a human-readable map: `filename_glob` → `Nombre`, `header_detect` → `Encabezados OCR`, `corner_count` → `Recuadro de página`, `manual` → `Manual`. The raw token is a tooltip on the row.
- Confidence and compilation pills moved from the title bar into a dedicated row directly under the headline number — they qualify the number.
- OverridePanel becomes the bottom card with a real heading ("Ajuste manual") and a SaveIndicator immediately to the right of the input. SaveIndicator states:
  - idle: nothing
  - saving: `<Loader2 12/ class="animate-spin"> Guardando…` muted
  - saved: `<CheckCircle2 12/> Guardado` in `state-success` for 2 s, then fades
  - error: `<AlertCircle 12/> No se pudo guardar` in `state-error`

### 4.4 PDFLightbox right panel ("Counts")

Today: same jargon as Detalle, plus the OverridePanel re-rendered. Header is `font-mono` smush.

**Redesign:**

Header (top of lightbox):
```
HPV  ·  irl  ·  Inspección reglamentaria de luminarias       [<X/>]
2026-04-30_reunion_subcontratos.pdf · pág 1 de 144
```

Two lines instead of one. First line: hospital chip + sigla mono + human label + close button. Second line: filename in `font-mono text-xs text-slate-500` + page count.

Right panel — collapse to a single compact card mirroring the Detalle redesign but tighter:

```
┌──── Conteo ──────────┐
│       141            │
│  [Compilación] [Baja]│
│                      │
│  Nombre        2     │
│  OCR           2     │
│  Método      Nombre  │
│                      │
│ ─ Ajuste manual ─    │
│ [   141   ] Guardado │
│ [ Nota… ]            │
└──────────────────────┘
```

Same primitives, narrower width (`w-72`). Critically: **identical microcopy to the Detalle panel** so users learn the structure in one place and recognize it in the other.

### 4.5 HLL empty state (no normalizado)

See §4.1. The key move is **making the empty state look intentional, not broken**. A dimmed card with a single em-dash communicates "something failed"; a card with an icon, an explanation, and a button to enter the manual flow communicates "this hospital works differently and here's how."

Bonus: store the manual counts for HLL in the same `user_override` field. The existing data model already supports it — only the UX is missing.

---

## 5. Microcopy

Daniel is the only user. He's Spanish-speaking, technically literate, and uses this monthly. Aim for **terse, plain Spanish**. No English. No engineering tokens.

| Current | Where it lives | Proposed |
|---|---|---|
| `compilation_suspect` (raw flag) | `HospitalDetail.jsx:105`, `CategoryRow.jsx:18`, `ScanControls.jsx:17` | **`Compilación`** (in pills) / **"Probable compilación"** (in tooltips/longer text) |
| `via filename_glob` | `HospitalDetail.jsx:96-98`, `PDFLightbox.jsx:84` | **"Método: Nombre"** (with mapping: `filename_glob`→`Nombre`, `header_detect`→`Encabezados OCR`, `corner_count`→`Recuadro de página`, `manual`→`Manual`) |
| `no normalizado` | `HospitalCard.jsx:16` | **"Sin carpeta normalizada"** + body "HLL no entrega PDFs por carpeta este mes. Ingresa los conteos a mano." + action button **"Ingresar conteos"** |
| `OCR 0 seleccionadas` | `ScanControls.jsx:30` | Disabled state: **"Selecciona categorías para OCR"**. Active: **"Escanear {n} categoría{s}"** (handle 1-vs-many). |
| `OCR suspects de HPV` | `ScanControls.jsx:37` | **"Escanear compilaciones de HPV"** — or, better, **move this button into the "COMPILACIONES" section header** as `[<Scan/> Escanear todas]` so the scope is self-evident. |
| `Confidence: low` | `HospitalDetail.jsx:101` | **`Baja`** in a confidence pill. Never a "Confidence:" label. |
| `Filename:` / `OCR:` | `HospitalDetail.jsx:91, 95`, `PDFLightbox.jsx:79, 82` | **"Por nombre de archivo"** / **"Por OCR"** — full Spanish phrasing inside the source-breakdown table. |
| `Sigla:` | `HospitalDetail.jsx:88` | Drop the label entirely. The sigla is the title. |
| `Flags: compilation_suspect` | `HospitalDetail.jsx:103-107` | Remove the row. Flags become pills under the headline number. |
| `Escanear todo` | `MonthOverview.jsx:60` | **"Escanear todos los hospitales"** — disambiguates from per-hospital scan |
| `Generar Resumen` | `MonthOverview.jsx:70` | **"Generar Excel del mes"** — names the output type |
| `alert("Generado: …")` | `MonthOverview.jsx:65` | Replace with a toast: **"Excel guardado en {path}"** + `<FileSpreadsheet/>` icon |
| App subtitle `FASE 2` | `App.jsx:14` | Delete. Internal phasing belongs in commit history, not chrome. |
| `Cargando…` everywhere | `FileList.jsx:35`, `PDFLightbox.jsx:71` | Replace text with `Skeleton` placeholders sized to the eventual content. |
| `Sin PDFs` | `FileList.jsx:36` | **"Esta categoría no tiene archivos en este mes"** (full sentence, with `<FileX/>` icon, inside an `EmptyState`) |
| `Cancel` (ScanProgress) | `ScanProgress.jsx:31` | **"Cancelar"** (Spanish + slightly larger). |
| `Completado · 18/18` | `ScanProgress.jsx:12` | **"Completado"** + the count in a `Badge`. Add auto-dismiss timer label. |

---

## 6. Out of Scope (deliberately deferred)

These were considered and **rejected** for this polish pass, with reasoning:

1. **Responsive / mobile layout.** Daniel runs this on a desktop with multiple monitors. The xl: breakpoint in `HospitalDetail` is fine. No need to design tablet or phone.
2. **Light mode.** Single user, dark-mode preference established. Don't double the design surface.
3. **Animations beyond loading states and badge fade-ins.** No bouncing cards, no entrance choreography, no page transitions. The product owner asked for *serious*.
4. **Real-time presence / multi-user features.** Single-user app for the foreseeable future.
5. **Theme customization (color picker, font size).** Single user.
6. **Keyboard shortcuts beyond Esc-closes-lightbox.** Defer until Daniel asks; he hasn't.
7. **Drag-and-drop month folder.** The backend's `/api/browse` (mentioned in CLAUDE.md as "only works with local display") and the existing month list cover the workflow.
8. **Detailed per-page OCR result viewer / page-by-page breakdown.** Daniel already uses the PDF iframe for that. No need to build a parallel viewer.
9. **Inline editing of category descriptions / sigla mapping.** The sigla→label map is fixed by the upstream domain.
10. **Toast notification stack.** A single transient toast slot is enough for "Excel guardado" / save errors. No need for a notification center.
11. **Component-library migration (e.g., shadcn/ui scaffolding).** Six primitives is too small for that ceremony. Build them inline under `frontend/src/ui/`.
12. **WebSocket reconnection UX.** Backend stability isn't the polish complaint; the icon and copy work is. Defer to a separate reliability pass.
13. **Search and filter on the Categorías list.** 18 fixed rows, grouped into 2 sections — search adds clutter, not value.
14. **Drag-to-resize columns in HospitalDetail.** Three equal columns at `xl:` are fine.
15. **A "Help" / "About" surface.** No new chrome.

---

## Next steps (for the implementation pass)

This document is the brief. The implementation pass should:

1. **Delete dead code first**: `HeaderBar.jsx`, `Sidebar.jsx`, `ProgressBar.jsx`, `ScanIndicator.jsx`, the stale `components/README.md`, and the unused `IMPACT_LABELS` / `SPINNER` / `formatTime` exports in `lib/constants.js`. Smaller surface = faster polish.
2. **Wire lucide-react and the new semantic Tailwind tokens** in one commit, before touching any component.
3. **Build the six `ui/` primitives** (Badge, SaveIndicator, EmptyState, Tooltip, Skeleton, ProgressBar) in their own commits with no consumers — they're trivial to verify in isolation.
4. **Replace `CategoryRow` first.** It's the most-seen widget; landing it well sets the tone for everything else.
5. Then Detalle → PDFLightbox right panel → HospitalCard → MonthOverview chrome → ScanProgress.
6. Translate microcopy alongside each component as you touch it. Don't batch the translations.

Sub-2 day estimate for a focused single-developer pass once the design tokens and primitives land.
