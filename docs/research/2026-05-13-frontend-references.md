# Frontend reference research — polish pass for PDFoverseer

**Date:** 2026-05-13
**Author:** outside-in research for the `po_overhaul` polish pass
**Stack constraint:** React 18 + Vite + Zustand + Tailwind 3, desktop-only 1280–1920px, dark-themed
**Reading order:** if you only read one section, jump to §6 (Top 3 recommendations).

---

## 0. Framing

PDFoverseer is a single-user, monthly-batch ops tool. The user opens a folder, watches a scan complete, eyeballs 72 cells of inferred counts, overrides what looks wrong, and exports an Excel. The product owner says the UI reads as "junior". The diagnosis from reading the codebase: zero design tokens (`tailwind.config.js` is empty), ad-hoc colors per component, hand-rolled lightbox, no icon library, no shared primitives. The fix is not visual flair — it is a **disciplined token system, a primitives layer, and density tuned for a power user**.

The references below are chosen because they solve our four structural problems: **dense review tables**, **long-running batch with per-item status**, **document-with-side-panel**, and **inbox-style triage**.

---

## 1. Workflow analogues

### 1.1 Audit / review dashboards — operator inspects N items with a confidence score

**Linear (issue list + inspector).** [linear.app](https://linear.app/now/how-we-redesigned-the-linear-ui) · [UI refresh changelog](https://linear.app/changelog/2026-03-12-ui-refresh)
- Pattern: 48–52px row height, a leading status indicator that is a **tiny solid dot in the state's color**, not a labeled pill. The label appears only on hover, in the inspector, or in dense list filters. Linear's March 2026 refresh explicitly "made navigation sidebars slightly dimmer so the main content stands out" and moved to LCH for perceptual color uniformity.
- Why for us: 72 cells per month is a list, not a dashboard. A 16px dot in the row beats a 60px-wide "HIGH CONFIDENCE" pill. Reserve the loud version for the inspector.

**Sentry (issue triage).** [sentry.io issue details UI](https://sentry.io/changelog/new-issue-details-ui-now-available/)
- Pattern: progressive disclosure — list rows show count + severity + last-seen, and the right pane is grouped into **"Workflow actions" up top, "Event details" below**, with a hard divider. Workflow stays sticky as event data scrolls.
- Why for us: overrides are workflow actions; OCR counts and source PDFs are details. Right pane in `HospitalDetail` should have an always-visible action header (Override / Re-OCR / Open PDF) and a scrollable detail body below it.

**PostHog (session replay inspector).** [posthog.com/docs/session-replay](https://posthog.com/docs/session-replay)
- Pattern: container-query-driven side pane that **collapses to icons** below a width threshold; activity panel is a single time-ordered event log with monospace timestamps.
- Why for us: if a user opens the PDF lightbox at 1280px, the inspector should auto-collapse to ~56px icon rail, not crowd the viewer.

**Mercury (transactions).** [mercury.com/blog/updated-transactions-page](https://mercury.com/blog/updated-transactions-page) · [Mercury demo](https://demo.mercury.com/transactions)
- Pattern: hairline 1px borders between rows in a low-chroma neutral; tabular-numeric numbers right-aligned next to a left-aligned label column; a **single accent color** for the primary CTA and nothing else.
- Why for us: the count column (`12`, `134`, `1`) is the visual anchor. It must be tabular-nums right-aligned, and *nothing else* in the row should compete with that accent.

### 1.2 Import / ETL wizards with progress

**Vercel deployments.** [vercel.com/docs/projects/project-dashboard](https://vercel.com/docs/projects/project-dashboard) · [Vercel dashboard redesign](https://vercel.com/blog/dashboard-redesign)
- Pattern: a **single-line "deployment in progress" strip** at the top of the project with phase label + elapsed time + a thin horizontal progress bar. Per-step build log opens in a slide-over, not a modal.
- Why for us: scan progress should be a sticky strip (matches `ScanProgress.jsx`), not a centered modal. Phase name ("Pase 1 filename glob 4/4 hospitales") + elapsed seconds + cancel button.

**Stripe Dashboard patterns.** [docs.stripe.com/stripe-apps/patterns](https://docs.stripe.com/stripe-apps/patterns)
- Pattern: their guidance for long-running tasks is "always show the step the user is on, the steps remaining, and a single primary action". Use indeterminate spinners only when you genuinely cannot estimate.
- Why for us: we *can* estimate (we know the file count). Replace any indeterminate spinner with a determinate bar + "23 of 47" label.

**Geist empty-state recipe.** [vercel.com/geist/empty-state](https://vercel.com/geist/empty-state)
- Pattern: four variants — *Blank Slate, Informational, Educational, Guide* — but all four cap at "one primary CTA, plus one secondary only if there are two legitimate paths". Title in Title Case + a sentence-case description that **adds information** rather than restating the title. CTA label format: `Title-Case Verb + Noun`, never "Get Started".
- Why for us: the "no folder open" state today says "Open a folder" — that is fine. Add one sentence below it: "Selecciona la carpeta del mes (ej. `A:\informe mensual\MAYO`) para escanear los 4 hospitales." Single button. No illustration.

### 1.3 Document inspection — PDF viewer + side-panel metadata

**Adobe Acrobat web.** [helpx.adobe.com — comments pane](https://helpx.adobe.com/acrobat/web/share-review-and-export/review-pdfs/add-manage-comments.html) · [side panel customization](https://helpx.adobe.com/acrobat/desktop/get-started/preferences-and-settings/customize-side-panels.html)
- Pattern: right rail is **collapsible to a narrow icon column**; only one panel (Comments, Bookmarks, AI Assistant) is expanded at a time; the active panel header has a close arrow, not an X.
- Why for us: when the PDF lightbox is open, the override panel and the file metadata should not both be visible. Tab between them or stack with collapse arrows.

**Notion right inspector.** [notion.com — layouts](https://www.notion.com/help/layouts)
- Pattern: a **collapsible "details panel"** on the right of database items, organized into named **property groups** ("Classification", "Account"). Each row is `label (muted, smaller) → value (primary text size)`, never `label: value` on one line.
- Why for us: `OverridePanel.jsx` should be a two-line layout per field — muted micro-label `Conteo filename` over the value `12`. Same for `Conteo OCR`, `Override`, `Nota`.

### 1.4 Inbox-style triage — list with status pills, filter by state

**Airtable grid views.** [support.airtable.com — grid view](https://support.airtable.com/docs/airtable-grid-view) · [interface grid](https://support.airtable.com/docs/interface-element-grid)
- Pattern: short row height by default (~32px), one line of text; row height is a **first-class user setting** with discrete steps (Short / Medium / Tall / Extra Tall). Status fields render as small colored chips inline.
- Why for us: 72 cells × month at 32px = 2304px — fits one screen at 1280×1080 with scroll. Offer a "compact / comfortable" toggle. Default to compact.

**Retool editable tables.** [retool.com — table guide](https://docs.retool.com/apps/guides/data/table/)
- Pattern: cells are read-only until the user clicks the cell — then a **bordered input replaces the cell in place**, with Enter/Escape commit/cancel and a small "edited" dot indicator until saved. No modal for single-cell edits.
- Why for us: today's override flow opens a panel. For the common case ("the OCR said 13, I want 12") an inline editable cell is faster. Keep the panel for adding notes.

---

## 2. Patterns to adopt

Eight specific moves, each traceable to a reference above.

1. **Replace verbose pills with 8px solid dots + label-on-hover.** *From Linear's row design.* `HIGH`/`LOW`/`MANUAL`/`SUSPECT`/`PENDING` become a 8×8 rounded square in a semantic color, followed by the count. Full label appears in tooltip and inspector. Frees ~80px of horizontal space per row, lets density double.

2. **Sticky workflow header in the inspector, scrollable details below.** *From Sentry.* `OverridePanel` gets a non-scrolling top section (`Override` input + Save / Cancel / Re-OCR buttons) and a scrolling body (filename matches, OCR debug, page list).

3. **Single-strip determinate progress bar at the top of the workspace.** *From Vercel deployments.* Replace any modal/centered spinner with a fixed-top 36px strip: phase name on the left, `23 / 47 archivos` middle, elapsed seconds right, thin 2px bar across the bottom edge. Cancellable.

4. **Inline-edit on count cells; panel only for notes.** *From Retool tables.* Click count → cell becomes a `<input type="number">` with the existing value pre-selected. Enter saves, Esc cancels. A 6×6 emerald dot replaces the chevron to mark unsaved-but-edited state until the WS round-trip completes. The override panel keeps the note + reason workflow.

5. **Property-group inspector with muted label / primary value.** *From Notion.* Each metadata field is two lines: `text-xs text-slate-400 uppercase tracking-wider` for the label, `text-base text-slate-100 tabular-nums` for the value. Groups separated by a 1px `slate-800` rule with a small section heading.

6. **Geist empty-state copy formula on every zero state.** *From Vercel Geist.* Title (Title Case) + one descriptive sentence that adds info + one CTA with `Verb + Noun` label. No SVG illustration. Applies to: no folder selected, scan-not-yet-run, zero OCR results, error state.

7. **Tabular-nums + right-aligned counts, hairline row borders.** *From Mercury.* Wrap every numeric cell in `font-variant-numeric: tabular-nums` (Tailwind: `tabular-nums`). Rows separated by `border-b border-slate-800/60` — not full-strength borders, not zebra stripes. The eye reads down the count column like a spreadsheet.

8. **Auto-collapsing inspector when viewport < 1400px.** *From PostHog + Acrobat.* Use a Zustand `inspectorMode: 'expanded' | 'rail' | 'hidden'` driven by `window.innerWidth` and a manual override pin. Below 1400 the inspector becomes a 56px icon rail; click-to-expand overlays the table instead of squeezing it.

---

## 3. Anti-patterns to avoid

Five things to explicitly reject.

1. **No microinteractions for delight.** No bounce on save, no confetti on "Generar Resumen", no slide-and-fade row insertions. Mercury and Linear both have *zero* decorative motion; the only animation is a 120ms color transition on state change. This is an ops tool — animation is information, not garnish.

2. **No color as decoration.** Every hue must be semantic. The Mercury rule is one accent (their indigo `#5266eb`) for *one* thing — the primary CTA. Avoid the Tailwind temptation of decorating headers in indigo, buttons in emerald, badges in violet "just because". Define semantic tokens (§5) and forbid raw color classes.

3. **No generous whitespace at the row level.** A 64px row with airy padding is for marketing dashboards (5–10 KPIs). We have 72 cells. Default to 32px row height (Airtable short), 40px comfortable as an option. Whitespace lives **between sections**, not inside rows.

4. **No skeuomorphic icons / no emoji status indicators.** Lucide stroke icons at 16px or 18px, monochromatic, in `text-slate-400` for resting and `text-slate-100` for active. No 🟢🟡🔴, no shadowed glyphs, no two-tone Phosphor duotone — those break the "serious tool" promise instantly.

5. **No gradient buttons, no glassmorphism, no glow.** A primary button is a flat fill of `indigo-9` (Radix) with `indigo-10` on hover, period. Glass/blur is a Mac-system aesthetic that signals "consumer app"; we are not that.

---

## 4. Library recommendations

One pick per category, with the reasoning compressed.

| Category | Pick | Why |
|---|---|---|
| Icon library | **lucide-react** | 1,500+ icons, ~8 KB gzipped for 50 icons, `strokeWidth` prop for hierarchy (competitors don't expose this), tree-shakeable per-icon imports. The aesthetic — clean Feather-style strokes — matches Linear/Vercel/Mercury. Heroicons is fine but only 292 icons; Phosphor's ~15 KB cost is real and its multi-weight tree-shaking is per-icon not per-weight. ([pkgpulse 2026](https://www.pkgpulse.com/guides/lucide-vs-heroicons-vs-phosphor-react-icon-libraries-2026)) |
| Headless primitives | **@radix-ui/react-\*** (individual packages) | 28 components covering tooltip / dialog / dropdown / popover / select / tabs — exactly what we need. Mature, `asChild` composition pattern composes cleanly with Tailwind. React Aria is more powerful but heavier and its render-prop API costs us ergonomics for features we will not use. Headless UI is too small (16 components). ([LogRocket headless comparison](https://blog.logrocket.com/headless-ui-alternatives/)) |
| Toast / notification | **sonner** | Imperative `toast()` API, no provider/hook setup, handles z-index against Radix portals out of the box, ~3 KB. Adopted by shadcn/ui as the default. react-hot-toast is solid but Sonner's stacking and Radix-compat win for our case. ([pkgpulse toast comparison](https://www.pkgpulse.com/guides/react-hot-toast-vs-react-toastify-vs-sonner-2026)) |
| Empty state | **No library — Geist recipe.** | Title + one sentence + one CTA. Inline component, ~30 lines. Avoid `react-empty-state` packages — overspecified for a one-screen polish. ([Geist empty state](https://vercel.com/geist/empty-state)) |
| Skeleton loaders | **Tailwind `animate-pulse` hand-rolled** | We have ~5 loading surfaces (file list, count cells, OCR debug). react-loading-skeleton's value is auto-matching arbitrary dimensions across hundreds of components — overkill. A 6-line `<Skeleton className="h-4 w-12 rounded bg-slate-800 animate-pulse" />` covers our needs without a dep. |
| Rich tooltips (compilation_suspect explanations) | **@radix-ui/react-tooltip** | Already in the toolbox if we pick Radix above. Supports rich JSX content via `<Tooltip.Content>`, manages portals, has built-in delay group for nearby triggers. floating-ui alone is too low-level; react-tooltip is fine but redundant with Radix. |
| Modal / lightbox (replace hand-rolled `PDFLightbox`) | **@radix-ui/react-dialog** | Free a11y (focus trap, ESC, aria-modal), portal handling, controlled-open API that fits Zustand cleanly. The hand-rolled lightbox is currently missing focus trap — Radix fixes it for free. Keep the `react-zoom-pan-pinch` inner viewport; only swap the outer chrome. |

**Total bundle add (gzipped, estimated):** lucide ~8 KB (icons used) + radix primitives ~12 KB across 5 components + sonner ~3 KB ≈ **~23 KB**. Acceptable for a localhost tool.

---

## 5. Color & typography references

### 5.1 Token system — adopt Radix Colors dark scales

Reference: [Radix color scale meaning](https://www.radix-ui.com/colors/docs/palette-composition/understanding-the-scale) — 12 steps with documented semantic purpose:

| Step | Purpose |
|---|---|
| 1 | App background |
| 2 | Subtle background (card / panel) |
| 3 | UI element background (input rest) |
| 4 | Hovered UI element |
| 5 | Active / selected UI element |
| 6 | Subtle borders (cards) |
| 7 | UI element borders (inputs, focus rings) |
| 8 | Hovered borders |
| 9 | Solid background (primary fills) |
| 10 | Hovered solid background |
| 11 | Low-contrast text |
| 12 | High-contrast text |

This 12-step convention is the deepest leverage in the whole research: it gives us a **named role per shade** so we never again pick `slate-800` or `slate-700` by feel.

Install `@radix-ui/colors` and import the dark variants. Map to Tailwind via `tailwind.config.js` `theme.extend.colors`. Recommended palettes:

- **`slateDark`** — neutrals (background, surface, text). Mercury-style warm-gray feel without being beige.
- **`indigoDark`** — accent / primary CTA / focus rings. Matches the existing palette mention.
- **`jadeDark`** — success / high confidence (Radix's perceptually-matched green, more legible on dark than `emerald-500`).
- **`amberDark`** — low confidence / suspect warning. Don't use orange/yellow Tailwind — Radix amber is tuned for dark backgrounds.
- **`rubyDark`** — error / OCR failure (subtler than `red-500`; reads as "attention" not "alarm").
- **`irisDark`** — manual override applied (a distinct hue from indigo so override state never blends with primary CTA).

### 5.2 Semantic token mapping for PDFoverseer

Pin these in `tailwind.config.js`. Names below are the **semantic** layer; values reference the Radix step.

| Semantic role | Token | Radix mapping | Hex (dark, step 9 / 11) |
|---|---|---|---|
| `confidence-high` | `--po-confidence-high` | `jadeDark.9` solid / `jadeDark.11` text | `#29a383` / `#3dd68c` |
| `confidence-low` | `--po-confidence-low` | `amberDark.9` / `amberDark.11` | `#ffb224` / `#f1a10d` |
| `compilation-suspect` | `--po-suspect` | `amberDark.10` (border `amberDark.7`) | `#ffcb47` |
| `error` | `--po-error` | `rubyDark.9` / `rubyDark.11` | `#e54666` / `#ff8b9c` |
| `success` | `--po-success` | `jadeDark.9` (alias of confidence-high) | `#29a383` |
| `scanning` | `--po-scanning` | `indigoDark.9` (pulsing) | `#3e63dd` |
| `override-applied` | `--po-override` | `irisDark.9` / `irisDark.11` | `#5b5bd6` / `#b1a9ff` |
| `surface-app` | `--po-bg` | `slateDark.1` | `#111113` |
| `surface-panel` | `--po-panel` | `slateDark.2` | `#18191b` |
| `border-hairline` | `--po-border` | `slateDark.6` | `#2a2b2e` |
| `text-primary` | `--po-text` | `slateDark.12` | `#edeef0` |
| `text-muted` | `--po-text-muted` | `slateDark.11` | `#b0b4ba` |

These map cleanly via [`windy-radix-palette`](https://github.com/brattonross/windy-radix-palette) which exposes Radix scales as Tailwind classes.

### 5.3 Typography

From Linear's 2026 refresh: **Inter Display for headings, Inter for body**. We can defer Inter Display — switching headings later is cheap. For now:
- `font-sans`: Inter (system fallback `-apple-system, "Segoe UI"`)
- `font-mono`: JetBrains Mono *only* for filenames, OCR debug strings, timestamps
- Body 14px (`text-sm`), micro labels 11px uppercased `tracking-wider`, counts 16px `tabular-nums font-medium`
- Line height 1.45 default — tighter than Tailwind's `leading-normal` (1.5), which is too airy at our density

---

## 6. Top 3 recommendations (TL;DR)

If only three things ship in the polish pass:

1. **Install Radix Colors + define the semantic token layer in `tailwind.config.js`.** Replace every raw `slate-*`, `indigo-*`, `emerald-*` class with semantic tokens (`bg-po-panel`, `text-po-confidence-high`, etc.). This single change eliminates the "junior" feel because it removes the by-feel color picking and enforces meaning. ~2 hours; touches every component but mechanically. Reference: Radix Colors 12-step scale.

2. **Adopt Radix primitives + lucide-react + sonner together as a "primitives commit".** Replace the hand-rolled `PDFLightbox` with `@radix-ui/react-dialog` (gets focus trap + a11y for free), add lucide icons to every action (16px stroke, `text-po-text-muted` resting), and route every success/error message through `toast()`. Bundle cost ~23 KB gzipped; perceived quality jump is large. Reference: Radix, Lucide, Sonner.

3. **Adopt the Linear/Mercury row design: 8px dot + tabular-nums count + hairline borders, no pills, no zebra.** Drop row height to 32px. Inline-edit on count cells (Retool pattern). Move full status labels to tooltips and the inspector. This is the visible "before/after" — the table goes from "form" to "spreadsheet for ops". Pairs with §5 tokens so the dot colors are semantic, not decorative.

Everything else in this doc is supporting detail. These three together turn the look from "junior shipped a feature" into "operator's tool, considered".

---

## Sources

- Linear: [redesign post](https://linear.app/now/how-we-redesigned-the-linear-ui) · [UI refresh changelog](https://linear.app/changelog/2026-03-12-ui-refresh) · [LogRocket "linear design"](https://blog.logrocket.com/ux-design/linear-design/)
- Sentry: [new issue details UI](https://sentry.io/changelog/new-issue-details-ui-now-available/) · [issue states & triage](https://docs.sentry.io/product/issues/states-triage/)
- Stripe: [design patterns](https://docs.stripe.com/stripe-apps/patterns) · [UI components](https://docs.stripe.com/stripe-apps/components)
- Vercel: [dashboard redesign](https://vercel.com/blog/dashboard-redesign) · [project dashboard docs](https://vercel.com/docs/projects/project-dashboard) · [Geist empty state](https://vercel.com/geist/empty-state)
- Mercury: [updated transactions blog](https://mercury.com/blog/updated-transactions-page) · [demo](https://demo.mercury.com/transactions) · [Mercury design notes](https://github.com/rohitg00/awesome-claude-design/blob/main/design-md/warm/mercury.md)
- Notion: [layouts help](https://www.notion.com/help/layouts) · [UI breakdown](https://medium.com/@quickmasum/ui-breakdown-of-notions-sidebar-2121364ec78d)
- PostHog: [session replay docs](https://posthog.com/docs/session-replay) · [replay UX issue](https://github.com/PostHog/posthog/issues/21302)
- Adobe Acrobat: [web comments pane](https://helpx.adobe.com/acrobat/web/share-review-and-export/review-pdfs/add-manage-comments.html) · [side panel customization](https://helpx.adobe.com/acrobat/desktop/get-started/preferences-and-settings/customize-side-panels.html)
- Airtable: [grid view](https://support.airtable.com/docs/airtable-grid-view) · [interface grid](https://support.airtable.com/docs/interface-element-grid)
- Retool: [table guide](https://docs.retool.com/apps/guides/data/table/)
- Radix Colors: [scales](https://www.radix-ui.com/colors/docs/palette-composition/scales) · [understanding the scale](https://www.radix-ui.com/colors/docs/palette-composition/understanding-the-scale) · [composing a palette](https://www.radix-ui.com/colors/docs/palette-composition/composing-a-palette) · [windy-radix-palette Tailwind plugin](https://github.com/brattonross/windy-radix-palette)
- Library comparisons: [LogRocket headless UI](https://blog.logrocket.com/headless-ui-alternatives/) · [pkgpulse icons 2026](https://www.pkgpulse.com/guides/lucide-vs-heroicons-vs-phosphor-react-icon-libraries-2026) · [pkgpulse toast 2026](https://www.pkgpulse.com/guides/react-hot-toast-vs-react-toastify-vs-sonner-2026)
- Empty states: [Vercel Geist](https://vercel.com/geist/empty-state) · [PatternFly empty state](https://www.patternfly.org/components/empty-state/design-guidelines/) · [Pixxen SaaS empty patterns](https://pixxen.com/saas-empty-state-design/)
