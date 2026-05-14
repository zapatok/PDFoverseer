# PDFoverseer FASE 3 — Polish pass Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the FASE 2 MVP UI ("looks like a junior shipped a feature") into a serious operator's tool (Linear/Mercury density, professional iconography, semantic tokens, no jargon).

**Architecture:** Layered foundation. (1) Foundation: install deps, wire Radix Colors as CSS variables, define semantic `po-*` Tailwind tokens. (2) Primitives: 8 reusable UI components under `frontend/src/ui/`. (3) Component redesign: rewrite 10 existing components consuming primitives + tokens. (4) Polish + audit + smoke: zero raw palette classes in JSX, manual end-to-end smoke, tag `fase-3-polish`. Backend untouched.

**Tech Stack:** React 18, Vite, Zustand, Tailwind 3, `@radix-ui/colors`, `@radix-ui/react-{dialog,tooltip}`, `lucide-react`, `sonner`, `@fontsource/{inter,jetbrains-mono}`. No new backend deps. No new tests harness (Vitest/RTL/Playwright deferred to FASE 4).

**Spec:** [`docs/superpowers/specs/2026-05-13-fase-3-polish-design.md`](../specs/2026-05-13-fase-3-polish-design.md) (831 lines, approved round 3).

**Research backing:**
- [`docs/research/2026-05-13-frontend-audit.md`](../../research/2026-05-13-frontend-audit.md)
- [`docs/research/2026-05-13-frontend-references.md`](../../research/2026-05-13-frontend-references.md)

---

## Conventions for this plan

### TDD adaptation for frontend

The frontend has no automated UI test harness (Vitest/RTL/Playwright not wired). Each task adapts TDD as:

1. **Plan the change** (file path + complete code shown in plan)
2. **Apply the change** (Write tool with full code)
3. **Verify build is green** (`cd frontend && npm run build`)
4. **Verify visually if applicable** (`npm run dev` + browser at `localhost:5173`)
5. **Commit** with conventional commit message

Backend remains test-driven (`pytest`) but no backend changes are expected in this plan. If a task accidentally touches backend, run `pytest -q` to confirm zero regressions.

### File path conventions

- All paths in this plan are relative to repo root `a:\PROJECTS\PDFoverseer\`.
- Use forward slashes in commands (Git Bash / cross-platform).
- Frontend files use `.jsx` extension; pure JS files use `.js`.

### Commit message format

`<type>(<scope>): <message>` per project CLAUDE.md. Types used in this plan:

- `chore(frontend)` — deps, config, deletes
- `feat(ui)` — new primitives under `frontend/src/ui/`
- `refactor(<component>)` — redesign of existing component
- `style(<component>)` — purely visual change with no behavior delta
- `docs(plan)` / `docs(spec)` — doc updates

All commits trailer with `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.

### How to invoke `npm run build` from a subagent

The Vite build runs from `frontend/` directory. Use:

```bash
cd frontend && npm run build
```

Expect exit code 0 and final line containing `✓ built in <time>`. Any error → STOP and surface to controller.

### Token usage rule (enforced via grep at Chunk 4 task 29)

Once tokens are wired (Chunk 1 task 5), NO new JSX may use raw Tailwind palette classes (`bg-slate-*`, `bg-indigo-*`, `bg-emerald-*`, etc.). Always use `po-*` tokens.

### Visual smoke commands

When a task says "verify visually," ensure backend + frontend are running:

```bash
# In one terminal
.venv-cuda/Scripts/python.exe server.py

# In another
cd frontend && npm run dev
```

Then navigate to `http://localhost:5173` in a browser and exercise the redesigned flow.

---

## File structure overview

### Files DELETED (Chunk 1)

```
frontend/src/components/HeaderBar.jsx
frontend/src/components/Sidebar.jsx
frontend/src/components/ProgressBar.jsx
frontend/src/components/ScanIndicator.jsx
frontend/src/components/README.md
```

Plus exports removed from `frontend/src/lib/constants.js` (SPINNER, IMPACT_LABELS, formatTime). Plus dead scrollbar CSS in `frontend/src/index.css`.

### Files CREATED

```
frontend/src/ui/Button.jsx
frontend/src/ui/Badge.jsx
frontend/src/ui/Dot.jsx
frontend/src/ui/SaveIndicator.jsx
frontend/src/ui/EmptyState.jsx
frontend/src/ui/Skeleton.jsx
frontend/src/ui/Tooltip.jsx
frontend/src/ui/Dialog.jsx
frontend/src/lib/sigla-labels.js
frontend/src/lib/method-labels.js
frontend/src/lib/hooks/useDebouncedCallback.js
frontend/src/components/CategoryGroup.jsx
```

### Files MODIFIED

```
frontend/package.json                                # +deps
frontend/tailwind.config.js                          # +tokens, +font families
frontend/src/index.css                               # +Radix CSS imports, -dead scrollbar
frontend/src/main.jsx                                # +font imports
frontend/src/App.jsx                                 # +TooltipProvider, +Toaster, -FASE 2 subtitle
frontend/src/store/session.js                       # +_pendingSave, AbortController, saveOverride coordination
frontend/src/views/MonthOverview.jsx                # redesign
frontend/src/views/HospitalDetail.jsx               # redesign + grouping
frontend/src/components/HospitalCard.jsx           # redesign
frontend/src/components/CategoryRow.jsx            # redesign + InlineEditCount inline
frontend/src/components/ConfidenceBadge.jsx        # delete (subsumed by Badge primitive)
frontend/src/components/OverridePanel.jsx          # redesign + SaveIndicator + debounce
frontend/src/components/FileList.jsx               # redesign
frontend/src/components/ScanControls.jsx           # redesign
frontend/src/components/ScanProgress.jsx           # redesign
frontend/src/components/PDFLightbox.jsx            # wrap with Radix Dialog
frontend/src/lib/constants.js                       # remove dead exports
```

### CLAUDE.md update at end

```
a:/PROJECTS/PDFoverseer/CLAUDE.md                    # Update FASE 3 section, list new deps
```

---

## Chunk 1: Cleanup + foundation

Bundle baseline, dead-code removal, dependency install, token wiring. Establishes the foundation every subsequent task depends on.

### Task 0: Measure bundle baseline

**Files:**
- Read: `frontend/dist/assets/index-*.js` (after build)
- Modify: `docs/superpowers/specs/2026-05-13-fase-3-polish-design.md` (update §10 placeholder)

- [ ] **Step 1: Run a clean build on tip-of-`po_overhaul`**

```bash
cd frontend && rm -rf dist node_modules/.vite && npm run build
```

Expected: exit 0, line `✓ built in <time>`, plus a line like `dist/assets/index-XXXX.js  161.42 kB │ gzip: 51.85 kB`.

- [ ] **Step 2: Capture the gzipped JS bundle size**

The baseline measured for AC10 is the **gzipped main JS bundle only** (`dist/assets/index-*.js` after `gzip:`). It does NOT include:
- WOFF2 font files added via `@fontsource/*` (those are separate static assets the browser caches independently, not part of the JS bundle)
- Other separate CSS chunks if Vite splits them
- Source maps (dev only)

Read the build output. The number after `gzip:` for the single `index-*.js` line is the baseline. Note it down (example: 51.85 kB). If Vite emits multiple `index-*.js` files (code-splitting), sum their gzipped sizes.

- [ ] **Step 3: Update spec §10 placeholder**

Use Edit to replace the placeholder line in the spec:

```
**Bundle baseline (medido en Chunk 1):** _<placeholder — implementer measures and commits actual gzipped size of `frontend/dist/assets/index-*.js` on tip-of-`po_overhaul` before Chunk 1 installs>_
```

With (replace `XX.XX` with the actual number):

```
**Bundle baseline (medido en Chunk 1):** **XX.XX kB** gzipped (`frontend/dist/assets/index-*.js` on tip-of-`po_overhaul` commit `b7468d4`, measured 2026-05-13).
```

- [ ] **Step 4: Commit baseline doc update**

```bash
git add docs/superpowers/specs/2026-05-13-fase-3-polish-design.md
git commit -m "$(cat <<'EOF'
docs(spec): FASE 3 bundle baseline — XX.XX kB gzipped

Captured pre-Chunk-1 bundle size for AC10 (≤ baseline + 25 KB after polish).
Measured on tip-of-po_overhaul commit b7468d4.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 1: Delete dead components

**Files:**
- Delete: `frontend/src/components/HeaderBar.jsx`
- Delete: `frontend/src/components/Sidebar.jsx`
- Delete: `frontend/src/components/ProgressBar.jsx`
- Delete: `frontend/src/components/ScanIndicator.jsx`
- Delete: `frontend/src/components/README.md`

These components are documented as dead code in the audit (audit doc §1, lines 35-38). None are imported anywhere. The README describes a different application entirely.

- [ ] **Step 1: Confirm zero imports + zero doc references to the README**

```bash
grep -rE "from .*/(HeaderBar|Sidebar|ProgressBar|ScanIndicator)" frontend/src/
grep -rE "components/README" frontend/src/ docs/
```

Expected: both empty.

If ANY import or doc reference is found, STOP and surface — the audit's "dead code" claim is wrong and these files need migration, not deletion.

- [ ] **Step 2: Delete the 5 files**

```bash
git rm frontend/src/components/HeaderBar.jsx
git rm frontend/src/components/Sidebar.jsx
git rm frontend/src/components/ProgressBar.jsx
git rm frontend/src/components/ScanIndicator.jsx
git rm frontend/src/components/README.md
```

- [ ] **Step 3: Verify build is green**

```bash
cd frontend && npm run build
```

Expected: exit 0, `✓ built in <time>`.

- [ ] **Step 4: Commit**

```bash
git commit -m "$(cat <<'EOF'
chore(frontend): delete 4 dead components + stale README

HeaderBar.jsx, Sidebar.jsx, ProgressBar.jsx, ScanIndicator.jsx, and
components/README.md are carryover from a prior application iteration —
none are imported anywhere and they reference Tailwind colors that don't
exist (bg-surface, bg-accent). README documents a different app entirely.

Verified via grep: zero imports of any of the 4 components.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Remove dead exports from `lib/constants.js` + dead scrollbar CSS

**Files:**
- Modify: `frontend/src/lib/constants.js` — keep `API_BASE`, `WS_BASE`; remove `SPINNER`, `IMPACT_LABELS`, `formatTime`
- Modify: `frontend/src/index.css` — remove the unused `.custom-scroll` block (audit §2 line 79)

- [ ] **Step 1: Read current `lib/constants.js`**

```bash
cat frontend/src/lib/constants.js
```

Note current contents.

- [ ] **Step 2: Replace with cleaned version**

Write `frontend/src/lib/constants.js` with ONLY:

```js
export const API_BASE = "/api";
export const WS_BASE = "/ws";
```

(If the file uses different default values, preserve them — only remove the dead exports.)

- [ ] **Step 3: Edit `index.css` to remove the unused `.custom-scroll` block**

In `frontend/src/index.css`, remove lines containing `.custom-scroll` (the 4 selectors). Keep the global `::-webkit-scrollbar` block — that one IS applied globally.

The result of `frontend/src/index.css` should be:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}
::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.2);
  border-radius: 4px;
}
::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.2);
}
```

(The Radix Color imports added in Task 5 will prepend this file.)

- [ ] **Step 4: Verify build + grep for stale refs**

```bash
cd frontend && npm run build
```

Expected: green.

```bash
grep -rE "SPINNER|IMPACT_LABELS|formatTime|custom-scroll" frontend/src/
```

Expected: empty.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/constants.js frontend/src/index.css
git commit -m "$(cat <<'EOF'
chore(frontend): remove dead constants exports + unused scrollbar CSS

SPINNER, IMPACT_LABELS, and formatTime in lib/constants.js are carryover
from a prior app iteration with zero current consumers.

.custom-scroll CSS class in index.css is never applied via className
anywhere in the JSX tree.

API_BASE and WS_BASE preserved (only live exports).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Install new dependencies

**Files:**
- Modify: `frontend/package.json` (via npm)
- Modify: `frontend/package-lock.json` (regenerated)

- [ ] **Step 1: Install runtime deps**

```bash
cd frontend && npm install --save \
  lucide-react@^0.400.0 \
  @radix-ui/colors@^3.0.0 \
  @radix-ui/react-dialog@^1.1.0 \
  @radix-ui/react-tooltip@^1.1.0 \
  sonner@^1.7.0 \
  @fontsource/inter@^5.1.0 \
  @fontsource/jetbrains-mono@^5.1.0
```

Expected: each line resolves, no peer-dep errors. If npm warns about peer-deps, read the warning — react 18 is current, all libs above support it.

- [ ] **Step 2: Verify `package.json`**

```bash
cat frontend/package.json
```

The `dependencies` block must include all 7 new packages. The dev dependencies block remains unchanged.

- [ ] **Step 3: Verify `npm run build` still passes**

```bash
cd frontend && npm run build
```

Expected: green. No new files in `src/` reference the new deps yet, so nothing should break.

- [ ] **Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "$(cat <<'EOF'
chore(frontend): install FASE 3 polish deps

Adds:
- lucide-react ^0.400.0 (icon library, replaces emoji placeholders)
- @radix-ui/colors ^3.0.0 (12-step dark scales as CSS variables)
- @radix-ui/react-dialog ^1.1.0 (PDFLightbox a11y wrapper)
- @radix-ui/react-tooltip ^1.1.0 (jargon explanations on hover)
- sonner ^1.7.0 (toast notifications, replaces alert())
- @fontsource/inter ^5.1.0 (sans-serif via npm, no Google Fonts)
- @fontsource/jetbrains-mono ^5.1.0 (monospace for sigla + filenames)

No JSX consumers yet — wired in next tasks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Wire fonts in `main.jsx`

**Files:**
- Modify: `frontend/src/main.jsx`

- [ ] **Step 1: Read current `main.jsx`**

Already known: imports React + createRoot + './index.css' + App, renders App in StrictMode.

- [ ] **Step 2: Write new `main.jsx` with font imports**

Write `frontend/src/main.jsx`:

```jsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "./index.css";
import App from "./App.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

Note: import order matters — fonts BEFORE `./index.css` so Tailwind base styles see the `@font-face` declarations.

- [ ] **Step 3: Verify build**

```bash
cd frontend && npm run build
```

Expected: green. Bundle size will increase (each Inter weight is ~30 KB; total ~150-200 KB for 4 weights × 2 fonts × WOFF2). That's acceptable — fontsource is per-weight and we only ship 6 weights.

- [ ] **Step 4: Commit (chunked with Task 5)**

Defer commit — we'll bundle Task 4 + Task 5 as one foundation commit.

---

### Task 5: Wire Radix Colors + semantic tokens + Toaster

**Files:**
- Modify: `frontend/src/index.css` (add Radix imports + z-index ladder)
- Modify: `frontend/tailwind.config.js` (add semantic tokens + font families)
- Modify: `frontend/src/App.jsx` (add TooltipProvider, Toaster, remove `FASE 2` subtitle, switch chrome to `po-*` tokens)

- [ ] **Step 1: Update `frontend/src/index.css`**

Replace the file with:

```css
@import "@radix-ui/colors/slate-dark.css";
@import "@radix-ui/colors/slate-dark-alpha.css";
@import "@radix-ui/colors/indigo-dark.css";
@import "@radix-ui/colors/indigo-dark-alpha.css";
@import "@radix-ui/colors/jade-dark.css";
@import "@radix-ui/colors/jade-dark-alpha.css";
@import "@radix-ui/colors/amber-dark.css";
@import "@radix-ui/colors/amber-dark-alpha.css";
@import "@radix-ui/colors/ruby-dark.css";
@import "@radix-ui/colors/ruby-dark-alpha.css";
@import "@radix-ui/colors/iris-dark.css";
@import "@radix-ui/colors/iris-dark-alpha.css";

@tailwind base;
@tailwind components;
@tailwind utilities;

/* z-index ladder (per spec §10 risks):
   z-40 ScanProgress (fixed-bottom)
   z-50 Dialog Overlay
   z-51 Dialog Content
   z-60 Toaster (must overlap Dialog so errors stay visible) */

::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}
::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.2);
  border-radius: 4px;
}
::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.2);
}
```

- [ ] **Step 2: Update `frontend/tailwind.config.js`**

Replace the file with:

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Canvas
        "po-bg":            "var(--slate-1)",
        "po-panel":         "var(--slate-2)",
        "po-panel-hover":   "var(--slate-3)",
        "po-border":        "var(--slate-6)",
        "po-border-strong": "var(--slate-7)",

        // Text
        "po-text":         "var(--slate-12)",
        "po-text-muted":   "var(--slate-11)",
        "po-text-subtle":  "var(--slate-10)",

        // Semantic state foregrounds (text in pills)
        "po-confidence-high":   "var(--jade-11)",
        "po-confidence-low":    "var(--amber-11)",
        "po-suspect":           "var(--amber-11)",
        "po-error":             "var(--ruby-11)",
        "po-scanning":          "var(--indigo-11)",
        "po-override":          "var(--iris-11)",
        "po-success":           "var(--jade-11)",

        // Semantic state backgrounds (subtle fills for pills) — use the
        // ALPHA scales (step 3) so they composite correctly over any
        // panel/canvas background. NEVER use Tailwind's /opacity modifier
        // on the `po-*` tokens — those resolve to hex via CSS var and
        // Tailwind can't inject an alpha channel.
        "po-confidence-high-bg":  "var(--jade-a3)",
        "po-confidence-low-bg":   "var(--amber-a3)",
        "po-suspect-bg":          "var(--amber-a3)",
        "po-error-bg":            "var(--ruby-a3)",
        "po-scanning-bg":         "var(--indigo-a3)",
        "po-override-bg":         "var(--iris-a3)",

        // Semantic state borders (step 7 alpha for the pill outlines)
        "po-confidence-high-border": "var(--jade-a7)",
        "po-confidence-low-border":  "var(--amber-a7)",
        "po-suspect-border":         "var(--amber-a7)",
        "po-error-border":           "var(--ruby-a7)",
        "po-scanning-border":        "var(--indigo-a7)",
        "po-override-border":        "var(--iris-a7)",

        // Dot solids (step 9 of base scale — the canonical solid)
        "po-dot-high":     "var(--jade-9)",
        "po-dot-low":      "var(--amber-9)",
        "po-dot-suspect":  "var(--amber-9)",
        "po-dot-error":    "var(--ruby-9)",
        "po-dot-scanning": "var(--indigo-9)",
        "po-dot-override": "var(--iris-9)",

        // Accent (primary CTA)
        "po-accent":       "var(--indigo-9)",
        "po-accent-hover": "var(--indigo-10)",
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', '"Segoe UI"', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', '"Cascadia Code"', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 3: Update `frontend/src/App.jsx`**

Write `frontend/src/App.jsx`:

```jsx
import { Tooltip } from "@radix-ui/react-tooltip";
import { Toaster } from "sonner";
import { useSessionStore } from "./store/session";
import MonthOverview from "./views/MonthOverview";
import HospitalDetail from "./views/HospitalDetail";
import PDFLightbox from "./components/PDFLightbox";
import ScanProgress from "./components/ScanProgress";

export default function App() {
  const { view, hospital, setView } = useSessionStore();

  return (
    <Tooltip.Provider delayDuration={300}>
      <div className="min-h-screen bg-po-bg text-po-text font-sans">
        <header className="px-6 py-4 border-b border-po-border">
          <h1 className="text-lg font-semibold">PDFoverseer</h1>
        </header>
        <main className="px-6 py-6 max-w-[1600px] mx-auto">
          {view === "month" && <MonthOverview />}
          {view === "hospital" && (
            <HospitalDetail hospital={hospital} onBack={() => setView("month")} />
          )}
        </main>
        <PDFLightbox />
        <ScanProgress />
        <Toaster position="bottom-right" theme="dark" className="z-[60]" />
      </div>
    </Tooltip.Provider>
  );
}
```

Note three changes vs old App.jsx:
- `Tooltip.Provider` wraps everything (delay 300ms per spec §4.5)
- `Toaster` added at `z-60` (top of ladder)
- `FASE 2` subtitle removed
- `bg-slate-950 text-slate-100` → `bg-po-bg text-po-text font-sans`
- Border `border-slate-800` → `border-po-border`

- [ ] **Step 4: Verify build + visual smoke**

```bash
cd frontend && npm run build
```

Expected: green. The bundle should now include Radix Colors CSS, font CSS, and Sonner.

```bash
cd frontend && npm run dev
```

Open `localhost:5173`. The page should still render the existing FASE 2 UI (no visual changes yet — components still use old slate classes). But:
- Inspect element on `<body>` → should show `font-family` resolved to Inter
- Inspect element on `<header>` → should show `background-color` resolves to a Radix slate value (`#111113` from `var(--slate-1)`)
- No console errors

If console shows `Cannot find module '@radix-ui/...` or similar, the install in Task 3 didn't complete — re-run install.

- [ ] **Step 5: Commit (Tasks 4 + 5 together)**

```bash
git add frontend/src/main.jsx frontend/src/index.css frontend/tailwind.config.js frontend/src/App.jsx
git commit -m "$(cat <<'EOF'
feat(frontend): foundation — Radix Colors tokens + Inter/JetBrains fonts + Toaster

Wires the foundation every FASE 3 component depends on:
- Inter (400/500/600/700) + JetBrains Mono (400/500) via @fontsource imports
- Radix Colors dark scales (slate, indigo, jade, amber, ruby, iris) via
  @import in index.css — exposes --slate-1 through --iris-12 as CSS vars
- Semantic po-* tokens in tailwind.config.js referencing those vars
  (po-bg, po-panel, po-text, po-confidence-high/low, po-suspect, po-error,
  po-scanning, po-override, po-success, po-accent + hover)
- App.jsx switches chrome to po-* tokens, wraps in Tooltip.Provider
  (delayDuration 300ms), removes "FASE 2" subtitle, adds Sonner Toaster
  at z-60

The existing component slate-* classes still render correctly — those
are migrated in Chunks 2-4.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Chunk 1 review checkpoint

After Tasks 0-5 commit cleanly:

- [ ] Run `cd frontend && npm run build` — green
- [ ] Run `cd frontend && npm run dev` — page loads at `localhost:5173`, no console errors, Inter font visible in dev tools, no visual regression vs pre-FASE-3 (components still use old slate, but foundation is wired)
- [ ] Run `grep -rE "windy-radix" frontend/` — empty
- [ ] Run `grep -rE "SPINNER|IMPACT_LABELS|formatTime|HeaderBar|Sidebar.jsx|ProgressBar.jsx|ScanIndicator" frontend/src/` — empty
- [ ] **Dispatch chunk-1 plan-reviewer subagent.** Pass: chunk 1 content + spec path. Fix any blocking findings.

---

## Chunk 2: UI primitives

8 reusable components under `frontend/src/ui/`. Each is small (≤80 lines), used in Chunk 3+. Built in dependency order so each task can verify in isolation.

### Task 6: `ui/Button.jsx`

**Files:**
- Create: `frontend/src/ui/Button.jsx`

The most-used primitive — every action in the UI passes through it. Spec §4.5.1.

- [ ] **Step 1: Create the file**

Write `frontend/src/ui/Button.jsx`:

```jsx
import { forwardRef } from "react";

const VARIANTS = {
  primary:     "bg-po-accent text-white hover:bg-po-accent-hover",
  secondary:   "bg-po-panel border border-po-border hover:border-po-border-strong text-po-text",
  ghost:       "text-po-text-muted hover:text-po-text hover:bg-po-panel-hover",
  destructive: "border border-po-error text-po-error hover:bg-po-error-bg",
};

const SIZES = {
  sm: "text-xs px-2.5 py-1",
  md: "text-sm px-3 py-1.5",
};

const Button = forwardRef(function Button(
  {
    variant = "secondary",
    size = "md",
    icon: Icon,
    disabled = false,
    type = "button",
    className = "",
    children,
    ...props
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled}
      className={[
        "inline-flex items-center gap-1.5 rounded-md font-medium transition",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-po-accent",
        VARIANTS[variant],
        SIZES[size],
        className,
      ].join(" ")}
      {...props}
    >
      {Icon && <Icon size={16} strokeWidth={1.75} />}
      {children}
    </button>
  );
});

export default Button;
```

- [ ] **Step 2: Smoke test via tmp consumer**

There's no test runner. Verify the component compiles cleanly:

```bash
cd frontend && npm run build
```

Expected: green. Nothing imports `Button` yet — this verifies syntax only.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/ui/Button.jsx
git commit -m "$(cat <<'EOF'
feat(ui): Button primitive — 4 variants × 2 sizes + icon slot

Variants: primary (po-accent solid), secondary (po-panel + border), ghost
(text-only hover), destructive (po-error outline). Sizes: sm / md.
forwardRef-aware so Radix Tooltip/Dialog can use asChild composition.
Icon prop renders a lucide-style 16px stroke before the label.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: `ui/Badge.jsx`

**Files:**
- Create: `frontend/src/ui/Badge.jsx`

Spec §4.5.2.

- [ ] **Step 1: Create the file**

Write `frontend/src/ui/Badge.jsx`:

```jsx
const VARIANTS = {
  "confidence-high": "bg-po-confidence-high-bg text-po-confidence-high border border-po-confidence-high-border",
  "confidence-low":  "bg-po-confidence-low-bg text-po-confidence-low border border-po-confidence-low-border",
  "state-suspect":   "bg-po-suspect-bg text-po-suspect border border-po-suspect-border",
  "state-scanning":  "bg-po-scanning-bg text-po-scanning border border-po-scanning-border",
  "state-error":     "bg-po-error-bg text-po-error border border-po-error-border",
  "state-override":  "bg-po-override-bg text-po-override border border-po-override-border",
  "neutral":         "bg-po-panel-hover text-po-text-muted border border-po-border",
};

export default function Badge({ variant = "neutral", icon: Icon, children, className = "" }) {
  return (
    <span
      className={[
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5",
        "text-[11px] font-medium tabular-nums",
        VARIANTS[variant],
        className,
      ].join(" ")}
    >
      {Icon && <Icon size={12} strokeWidth={2} />}
      {children}
    </span>
  );
}
```

Note: every color class here is a pre-composed semantic token (`po-confidence-high-bg`, `po-confidence-high-border`) — there are NO Tailwind opacity modifiers like `/10` or `/30`. Those don't work with `var(--*)`-backed colors because Tailwind can't inject an alpha channel into a CSS variable that resolves to a hex string. The Radix `*-a3` and `*-a7` alpha scales (imported in Task 5) ARE pre-multiplied alpha values, so they composite correctly over any background.

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build
```

Expected: green.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/ui/Badge.jsx
git commit -m "$(cat <<'EOF'
feat(ui): Badge primitive — 7 semantic variants + optional icon

Variants: confidence-high/low, state-suspect/scanning/error/override,
neutral. Replaces the hand-rolled ConfidenceBadge (which was never wired
up) and consolidates all pill/chip rendering through one primitive.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: `ui/Dot.jsx`

**Files:**
- Create: `frontend/src/ui/Dot.jsx`

Spec §4.5.3.

- [ ] **Step 1: Create the file**

Write `frontend/src/ui/Dot.jsx`:

```jsx
const VARIANTS = {
  "confidence-high": "bg-po-dot-high",
  "confidence-low":  "bg-po-dot-low",
  "state-suspect":   "bg-po-dot-suspect",
  "state-scanning":  "bg-po-dot-scanning animate-pulse",
  "state-error":     "bg-po-dot-error",
  "state-override":  "bg-po-dot-override",
  "neutral":         "bg-po-text-subtle",
};

export default function Dot({ variant = "neutral", className = "" }) {
  return (
    <span
      aria-hidden="true"
      className={[
        "inline-block h-2 w-2 rounded-full shrink-0",
        VARIANTS[variant],
        className,
      ].join(" ")}
    />
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build
```

Expected: green.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/ui/Dot.jsx
git commit -m "$(cat <<'EOF'
feat(ui): Dot primitive — 8px semantic status indicator

Same variant taxonomy as Badge. Used in CategoryRow as the leading status
indicator (Linear pattern) and in HospitalCard as the 18-dot ribbon
(per-sigla confidence telemetry).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: `ui/SaveIndicator.jsx`

**Files:**
- Create: `frontend/src/ui/SaveIndicator.jsx`

Spec §4.5.4. This is the P0 primitive — OverridePanel autosave-on-blur is currently invisible per Daniel's repeated feedback.

- [ ] **Step 1: Create the file**

Write `frontend/src/ui/SaveIndicator.jsx`:

```jsx
import { useEffect, useState } from "react";
import { Loader2, CheckCircle2, AlertCircle } from "lucide-react";

/**
 * status: 'idle' | 'saving' | 'saved' | 'error'
 *
 * idle: nothing rendered
 * saving: spinner + "Guardando…" in muted text
 * saved: check + "Guardado" in success color — auto-fades after 2s back to idle (the parent should set status back to 'idle' too, but the visual fades regardless)
 * error: alert + "No se pudo guardar" — sticky (no auto-fade)
 */
export default function SaveIndicator({ status = "idle" }) {
  const [visible, setVisible] = useState(status !== "idle");

  useEffect(() => {
    if (status === "saved") {
      setVisible(true);
      const t = setTimeout(() => setVisible(false), 2000);
      return () => clearTimeout(t);
    }
    setVisible(status !== "idle");
  }, [status]);

  if (!visible) return null;

  if (status === "saving") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-po-text-muted">
        <Loader2 size={12} strokeWidth={2} className="animate-spin" />
        Guardando…
      </span>
    );
  }
  if (status === "saved") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-po-success">
        <CheckCircle2 size={12} strokeWidth={2} />
        Guardado
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-po-error">
        <AlertCircle size={12} strokeWidth={2} />
        No se pudo guardar
      </span>
    );
  }
  return null;
}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build
```

Expected: green.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/ui/SaveIndicator.jsx
git commit -m "$(cat <<'EOF'
feat(ui): SaveIndicator primitive — visible autosave feedback

States: idle (nothing) / saving (spinner + 'Guardando…') / saved (check +
'Guardado', 2s auto-fade) / error (alert + 'No se pudo guardar', sticky).

Closes the long-standing 'invisible autosave' UX gap in OverridePanel —
Daniel previously had no way to tell if a manual override persisted
(feedback_incomplete_root_cause_investigation memory).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: `ui/EmptyState.jsx`

**Files:**
- Create: `frontend/src/ui/EmptyState.jsx`

Spec §4.5.5. Follows Vercel Geist recipe: title + 1 info-adding sentence + 1 CTA.

- [ ] **Step 1: Create the file**

Write `frontend/src/ui/EmptyState.jsx`:

```jsx
export default function EmptyState({ icon: Icon, title, description, action, className = "" }) {
  return (
    <div className={["flex flex-col items-center text-center py-8 px-4 gap-3", className].join(" ")}>
      {Icon && <Icon size={32} strokeWidth={1.5} className="text-po-text-subtle" />}
      {title && <h3 className="text-sm font-medium text-po-text">{title}</h3>}
      {description && <p className="text-xs text-po-text-muted max-w-xs">{description}</p>}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build
```

Expected: green.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/ui/EmptyState.jsx
git commit -m "$(cat <<'EOF'
feat(ui): EmptyState primitive — Geist recipe (icon + title + sentence + CTA)

Used for: 'Selecciona una categoría' panels, HLL 'Sin carpeta normalizada',
FileList 'Sin archivos'. Replaces hand-rolled stacked-paragraph empty
states scattered through the FASE 2 components.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: `ui/Skeleton.jsx`

**Files:**
- Create: `frontend/src/ui/Skeleton.jsx`

Spec §4.5.6.

- [ ] **Step 1: Create the file**

Write `frontend/src/ui/Skeleton.jsx`:

```jsx
export default function Skeleton({ className = "" }) {
  return (
    <span
      aria-hidden="true"
      className={["block bg-po-panel-hover rounded animate-pulse", className].join(" ")}
    />
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build
```

Expected: green.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/ui/Skeleton.jsx
git commit -m "$(cat <<'EOF'
feat(ui): Skeleton primitive — animated placeholder for loading states

10-line wrapper around Tailwind animate-pulse. Replaces 'Cargando…' text
in FileList and PDFLightbox.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: `ui/Tooltip.jsx`

**Files:**
- Create: `frontend/src/ui/Tooltip.jsx`

Spec §4.5.7. Wraps Radix Tooltip with project's visual style.

- [ ] **Step 1: Create the file**

Write `frontend/src/ui/Tooltip.jsx`:

```jsx
import * as RadixTooltip from "@radix-ui/react-tooltip";

/**
 * <Tooltip content="...">{trigger}</Tooltip>
 *
 * Provider lives in App.jsx with delayDuration=300. This wrapper assumes
 * the provider is in scope.
 */
export default function Tooltip({ content, side = "top", children }) {
  if (!content) return children;
  return (
    <RadixTooltip.Root>
      <RadixTooltip.Trigger asChild>{children}</RadixTooltip.Trigger>
      <RadixTooltip.Portal>
        <RadixTooltip.Content
          side={side}
          sideOffset={6}
          className="z-[70] rounded-md bg-po-panel border border-po-border px-2.5 py-1.5 text-xs text-po-text shadow-lg max-w-xs"
        >
          {content}
          <RadixTooltip.Arrow className="fill-po-border" />
        </RadixTooltip.Content>
      </RadixTooltip.Portal>
    </RadixTooltip.Root>
  );
}
```

`z-[70]` is above the Sonner Toaster (z-60), so tooltips show over toasts (rare but correct).

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build
```

Expected: green.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/ui/Tooltip.jsx
git commit -m "$(cat <<'EOF'
feat(ui): Tooltip primitive — wraps @radix-ui/react-tooltip

API: <Tooltip content="...">{trigger}</Tooltip>. asChild composition lets
buttons, sigla labels, and any focusable element trigger a tooltip without
extra DOM. Provider sits at App.jsx with delayDuration 300ms.

Renders at z-70 (above Toaster z-60 + Dialog z-51).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 13: `ui/Dialog.jsx`

**Files:**
- Create: `frontend/src/ui/Dialog.jsx`

Spec §4.5.8. Wraps Radix Dialog with project visual style + reusable subcomponents.

- [ ] **Step 1: Create the file**

Write `frontend/src/ui/Dialog.jsx`:

```jsx
import * as RadixDialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";

/**
 * Compound component:
 *   <Dialog open={...} onOpenChange={...}>
 *     <Dialog.Header>...</Dialog.Header>
 *     <Dialog.Body>...</Dialog.Body>
 *   </Dialog>
 *
 * Renders overlay (z-50) + content (z-51) in a portal. ESC + click-outside
 * close. Focus trap inside the content. Returns null when !open.
 */
export default function Dialog({ open, onOpenChange, children }) {
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-50 bg-black/70" />
        <RadixDialog.Content className="fixed inset-4 z-[51] bg-po-bg border border-po-border rounded-xl shadow-2xl flex flex-col focus-visible:outline-none">
          {children}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}

Dialog.Header = function DialogHeader({ children }) {
  return (
    <header className="px-5 py-3 border-b border-po-border flex items-center gap-3">
      <div className="flex-1 min-w-0">{children}</div>
      <RadixDialog.Close className="text-po-text-muted hover:text-po-text shrink-0">
        <X size={18} strokeWidth={1.75} />
      </RadixDialog.Close>
    </header>
  );
};

Dialog.Body = function DialogBody({ children, className = "" }) {
  return <div className={["flex-1 min-h-0 flex", className].join(" ")}>{children}</div>;
};

// Accessibility: Radix requires Dialog.Title and Dialog.Description for screen
// readers. Re-export so consumers can include them. If a consumer doesn't, Radix
// will console.warn in dev — that warning is benign for a single-user desktop
// app but we provide the slots for hygiene.
Dialog.Title = RadixDialog.Title;
Dialog.Description = RadixDialog.Description;
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build
```

Expected: green.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/ui/Dialog.jsx
git commit -m "$(cat <<'EOF'
feat(ui): Dialog primitive — wraps @radix-ui/react-dialog

Compound component (Dialog + Dialog.Header + Dialog.Body + Dialog.Title +
Dialog.Description) so PDFLightbox can compose without re-declaring Radix
internals.

Brings free a11y wins to the lightbox: focus trap, ESC close, click-outside
close, body scroll lock, aria-modal. Hand-rolled lightbox had none of these.

Renders at z-50 (overlay) + z-51 (content), per the z-index ladder.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Chunk 2 review checkpoint

After Tasks 6-13 commit cleanly:

- [ ] `cd frontend && npm run build` — green
- [ ] `ls frontend/src/ui/` — 8 files: Badge, Button, Dialog, Dot, EmptyState, SaveIndicator, Skeleton, Tooltip
- [ ] **Dispatch chunk-2 plan-reviewer subagent.** Pass: chunk 2 content + spec path. Fix any blocking findings.

---

## Chunk 3: Constants + components redesign

11 tasks — `lib/` constants, store extension for save coordination, then component redesigns in dependency order. By the end, every visible surface has been touched.

### Task 14: `lib/sigla-labels.js` + `lib/method-labels.js`

**Files:**
- Create: `frontend/src/lib/sigla-labels.js`
- Create: `frontend/src/lib/method-labels.js`

Spec §5.5 + §5.6.

- [ ] **Step 1: Create `sigla-labels.js`**

Write `frontend/src/lib/sigla-labels.js` (values match `core/domain.py:CATEGORY_FOLDERS` with prefix stripped + tildes added):

```js
// Source of truth: core/domain.py CATEGORY_FOLDERS. Do NOT fabricate domain
// meaning — folder name IS the label (prefix N.- stripped, tildes added).
// Acronyms (ART, ODI, IRL, PTS, CHPS) stay as-is — Daniel uses them.
//
// If a label reads awkwardly in tooltips/Detail header, ASK Daniel before
// changing it. Don't expand acronyms unilaterally.
export const SIGLA_LABELS = {
  reunion: "Reunión de prevención",
  irl: "Inducción IRL",
  odi: "ODI Visitas",
  charla: "Charlas",
  chintegral: "Charla integral",
  dif_pts: "Difusión PTS",
  art: "ART",
  insgral: "Inspecciones generales",
  bodega: "Inspección bodega",
  maquinaria: "Inspección de maquinaria",
  ext: "Extintores",
  senal: "Señaléticas",
  exc: "Excavaciones y vanos",
  altura: "Trabajos en altura",
  caliente: "Inspección trabajos en caliente",
  herramientas_elec: "Inspección herramientas eléctricas",
  andamios: "Andamios",
  chps: "CHPS",
};
```

- [ ] **Step 2: Create `method-labels.js`**

Write `frontend/src/lib/method-labels.js`:

```js
// Maps backend ScanResult.method tokens → human Spanish labels for UI.
// Token comes verbatim from core.scanners.*; never invent new tokens here.
export const METHOD_LABEL = {
  filename_glob:    "Nombre",
  header_detect:    "Encabezados OCR",
  corner_count:     "Recuadro de página",
  page_count_pure:  "Conteo de páginas",
  manual:           "Manual",
};

// ScanResult.confidence → human label.
export const CONFIDENCE_LABEL = {
  high:   "Alta",
  medium: "Media",
  low:    "Baja",
  manual: "Manual",
};
```

- [ ] **Step 3: Verify build**

```bash
cd frontend && npm run build
```

Expected: green. (No JSX consumers yet — those wire up in component redesigns.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/sigla-labels.js frontend/src/lib/method-labels.js
git commit -m "$(cat <<'EOF'
feat(frontend): label maps — sigla, method, confidence

sigla-labels.js: 18 entries derived from core/domain.py CATEGORY_FOLDERS
(prefix stripped, tildes added). Acronyms preserved.

method-labels.js: maps ScanResult.method tokens (filename_glob,
header_detect, corner_count, page_count_pure, manual) to human Spanish.
Plus CONFIDENCE_LABEL for high/medium/low/manual.

Consumed by CategoryRow tooltips, Detail panel, PDFLightbox header.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 15: `lib/hooks/useDebouncedCallback.js`

**Files:**
- Create: `frontend/src/lib/hooks/useDebouncedCallback.js`

Spec §11 — hand-rolled debounce to avoid `use-debounce` dependency.

- [ ] **Step 1: Create the file**

Write `frontend/src/lib/hooks/useDebouncedCallback.js`:

```js
import { useCallback, useEffect, useRef } from "react";

/**
 * Returns a debounced version of `callback` that delays invocation until
 * `delayMs` have elapsed since the last call. Cancels in-flight timer on
 * unmount.
 *
 * Also exposes `.cancel()` to abort any pending invocation.
 */
export function useDebouncedCallback(callback, delayMs) {
  const timerRef = useRef(null);
  const callbackRef = useRef(callback);

  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const debounced = useCallback(
    (...args) => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        callbackRef.current(...args);
        timerRef.current = null;
      }, delayMs);
    },
    [delayMs],
  );

  debounced.cancel = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  return debounced;
}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build
```

Expected: green.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/hooks/useDebouncedCallback.js
git commit -m "$(cat <<'EOF'
feat(frontend): useDebouncedCallback hook (hand-rolled, zero-dep)

20-line hook with .cancel() method. Used by OverridePanel for 400ms
debounced autosave. Avoids pulling use-debounce as a dep.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 16: Store extension — `_pendingSave` + `saveOverride` coordination

**Files:**
- Modify: `frontend/src/store/session.js`

Spec §6.6 — the central coordination layer for InlineEditCount and OverridePanel.

- [ ] **Step 1: Read the current `saveOverride` action**

Inspect `frontend/src/store/session.js` lines 72-84 (the existing `saveOverride`). Note it currently just calls `api.patchOverride` and patches the local state — no debounce coordination, no AbortController, no pending-save tracking.

- [ ] **Step 2: Update the store**

Apply these edits to `frontend/src/store/session.js`:

**Edit 1:** In the initial state (after `lightbox: null,`), add:

```js
  // FASE 3 — pending-save coordination (see spec §6.6).
  // Map keyed by `${hospital}|${sigla}` → { controller: AbortController, status: 'saving' }
  _pendingSave: new Map(),
  // Public read view for components — keyed identically. Values: 'saving' | 'saved' | 'error'.
  pendingSaves: {},
```

**Edit 2:** Replace the existing `saveOverride` action with:

```js
  saveOverride: async (sessionId, hospital, sigla, value, note) => {
    const key = `${hospital}|${sigla}`;
    const controller = new AbortController();

    // 1+2 combined in a functional set() so reads + writes happen atomically.
    // This prevents the stale-read race when two rapid calls overlap: both
    // would read state._pendingSave before either set()ted, and both would
    // think they are 'first'. Functional setState gives us the prev state
    // synchronously inside the updater.
    set((prev) => {
      const existing = prev._pendingSave.get(key);
      if (existing?.controller) {
        existing.controller.abort();
      }
      const nextPending = new Map(prev._pendingSave);
      nextPending.set(key, { controller });
      return {
        _pendingSave: nextPending,
        pendingSaves: { ...prev.pendingSaves, [key]: "saving" },
      };
    });

    try {
      const result = await api.patchOverride(
        sessionId, hospital, sigla, value, note,
        { signal: controller.signal },
      );

      // If our controller was aborted while in flight, the newer save wins.
      if (controller.signal.aborted) return;

      // Atomically patch session.cells + clear pending.
      set((prev) => {
        if (!prev.session) return {};
        const cells = { ...prev.session.cells };
        const hosp = { ...cells[hospital] };
        hosp[sigla] = {
          ...hosp[sigla],
          user_override: result.user_override,
          override_note: result.override_note,
        };
        cells[hospital] = hosp;
        const cleanedPending = new Map(prev._pendingSave);
        // Only drop OUR controller — if a newer save raced in, leave it alone.
        if (cleanedPending.get(key)?.controller === controller) {
          cleanedPending.delete(key);
        }
        return {
          session: { ...prev.session, cells },
          _pendingSave: cleanedPending,
          pendingSaves: { ...prev.pendingSaves, [key]: "saved" },
        };
      });

      // Auto-flush 'saved' state after 2s — but only if status is still
      // 'saved' (not overwritten by a newer 'saving' from another commit).
      setTimeout(() => {
        set((prev) => {
          if (prev.pendingSaves[key] !== "saved") return {};
          const np = { ...prev.pendingSaves };
          delete np[key];
          return { pendingSaves: np };
        });
      }, 2000);
    } catch (error) {
      if (controller.signal.aborted) return;
      set((prev) => {
        const cleanedPending = new Map(prev._pendingSave);
        if (cleanedPending.get(key)?.controller === controller) {
          cleanedPending.delete(key);
        }
        return {
          _pendingSave: cleanedPending,
          pendingSaves: { ...prev.pendingSaves, [key]: "error" },
          error: String(error),
        };
      });
    }
  },
```

Key invariants in the code above:
1. Every `set()` uses the **functional updater form** `set((prev) => ...)` so reads + writes are atomic within a single Zustand update. No stale-read.
2. Cleanup paths only delete the pending entry if **our** controller is the one still installed (`if (cleanedPending.get(key)?.controller === controller)`) — protects against clobbering a newer save that raced in.
3. `controller.signal.aborted` check immediately after `await` short-circuits clean — newer save wins.

**Edit 3:** Update `api.patchOverride` signature to accept the AbortController signal. In `frontend/src/lib/api.js`, find `patchOverride` and ensure it forwards `signal`:

```js
export async function patchOverride(sessionId, hospital, sigla, value, note, { signal } = {}) {
  const res = await fetch(`/api/sessions/${sessionId}/cells/${hospital}/${sigla}/override`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value, note }),
    signal,
  });
  if (!res.ok) throw new Error(`patchOverride failed: ${res.status}`);
  return res.json();
}
```

(If `api.patchOverride` exists differently, preserve its current shape and add the `signal` option compatibly.)

- [ ] **Step 3: Verify build**

```bash
cd frontend && npm run build
```

Expected: green.

- [ ] **Step 4: Smoke test the API change manually**

Start backend + frontend in separate terminals (Windows-friendly — do NOT use `&`):

```
# Terminal A
.venv-cuda/Scripts/python.exe server.py
```

```
# Terminal B
cd frontend && npm run dev
```

In browser at `localhost:5173`:
1. Open ABRIL
2. Click HPV
3. Click a sigla (e.g. reunion)
4. In OverridePanel, type a number → blur
5. Watch network panel: PATCH `/api/sessions/2026-04/cells/HPV/reunion/override` → 200
6. Refresh page → override persisted

**Rapid-typing race test:** type 10 characters rapidly in the override input. Watch the network panel — only ONE PATCH should land (the debounce coalesces 9 of them; the AbortController would abort an earlier in-flight if a second flushed while the first was mid-request, but the debounce should prevent that). If you see multiple PATCHes with overlapping timestamps, the race is real — debug before commit.

If PATCH errors at all, the signal wiring is broken — debug.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/store/session.js frontend/src/lib/api.js
git commit -m "$(cat <<'EOF'
feat(store): saveOverride coordination via AbortController + pending-save Map

Implements spec §6.6: single write path for user_override that:
- aborts any in-flight HTTP for the same (hospital, sigla)
- tracks pending state in store.pendingSaves[key] = 'saving'|'saved'|'error'
- auto-clears 'saved' after 2s (matches SaveIndicator fade)
- both InlineEditCount and OverridePanel feed through the same path,
  preventing races when both write simultaneously

api.patchOverride now accepts an AbortController signal.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 17: `MonthOverview.jsx` redesign

**Files:**
- Modify: `frontend/src/views/MonthOverview.jsx`

Spec §5.2. Three changes: lucide icons on buttons, toast instead of alert(), copy update (no "FASE 2" anywhere — already removed in App.jsx).

- [ ] **Step 1: Write new `MonthOverview.jsx`**

```jsx
import { useEffect } from "react";
import { Calendar, RefreshCw, FileSpreadsheet } from "lucide-react";
import { toast } from "sonner";
import { useSessionStore } from "../store/session";
import HospitalCard from "../components/HospitalCard";
import Button from "../ui/Button";

const HOSPITALS = ["HPV", "HRB", "HLU", "HLL"];

export default function MonthOverview() {
  const {
    months, session, loading, error,
    loadMonths, openMonth, selectHospital, runScan, generateOutput,
  } = useSessionStore();

  useEffect(() => {
    loadMonths();
  }, [loadMonths]);

  const activeMonth = session?.session_id;
  const cells = session?.cells || {};

  const totalsByHospital = Object.fromEntries(
    HOSPITALS.map((h) => {
      const hospCells = cells[h] || {};
      const total = Object.values(hospCells).reduce(
        (s, cell) => s + (cell.user_override ?? cell.ocr_count ?? cell.filename_count ?? cell.count ?? 0),
        0,
      );
      return [h, total];
    }),
  );

  const onGenerate = async () => {
    try {
      const r = await generateOutput(session.session_id);
      toast.success(`Excel guardado en ${r.output_path}`, { icon: <FileSpreadsheet size={16} /> });
    } catch (err) {
      toast.error(`No se pudo generar el Excel: ${String(err)}`);
    }
  };

  return (
    <div className="space-y-8">
      <section>
        <h2 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mb-3">Mes</h2>
        <div className="flex gap-2 flex-wrap">
          {months.map((m) => (
            <button
              key={m.session_id}
              onClick={() => openMonth(m.session_id, m.year, m.month)}
              className={[
                "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm border transition",
                activeMonth === m.session_id
                  ? "bg-po-accent text-white border-po-accent"
                  : "bg-po-panel border-po-border hover:border-po-border-strong text-po-text",
              ].join(" ")}
            >
              <Calendar size={14} strokeWidth={1.75} />
              {m.name} {m.year}
            </button>
          ))}
        </div>
      </section>

      {session && (
        <>
          <section className="flex gap-3">
            <Button
              variant="primary"
              icon={RefreshCw}
              disabled={loading}
              onClick={() => runScan(session.session_id)}
            >
              {loading ? "Escaneando…" : "Escanear todos los hospitales"}
            </Button>
            <Button
              icon={FileSpreadsheet}
              disabled={loading}
              onClick={onGenerate}
            >
              Generar Excel del mes
            </Button>
          </section>

          <section>
            <h2 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mb-3">Hospitales</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
              {HOSPITALS.map((h) => (
                <HospitalCard
                  key={h}
                  hospital={h}
                  total={totalsByHospital[h]}
                  cells={cells[h]}
                  status={cells[h] ? "present" : "missing"}
                  onClick={() => selectHospital(h)}
                />
              ))}
            </div>
          </section>
        </>
      )}

      {error && <p className="text-po-error">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Verify build + visual smoke**

```bash
cd frontend && npm run build
```

Then `npm run dev` and at localhost:5173:
- Click a month → loads
- Click "Generar Excel del mes" → toast appears bottom-right with FileSpreadsheet icon

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/MonthOverview.jsx
git commit -m "$(cat <<'EOF'
refactor(month-overview): redesign with po-* tokens + lucide + toast

- Month picker buttons get Calendar icon
- Action buttons use Button primitive with RefreshCw / FileSpreadsheet icons
- alert() replaced with toast.success("Excel guardado en {path}") + icon
- 'FASE 2' subtitle long gone (App.jsx)
- Copy: 'Escanear todo' → 'Escanear todos los hospitales';
        'Generar Resumen' → 'Generar Excel del mes'
- Grid responsive: 1col / md:2col / xl:4col

HospitalCard now receives full cells object for the dots-ribbon
rendering (added in next task).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 18: `HospitalCard.jsx` redesign (present state + 18-dot ribbon)

**Files:**
- Modify: `frontend/src/components/HospitalCard.jsx`

Spec §5.3. Covers both present state (HPV/HRB/HLU) and missing/HLL empty state in a single file.

- [ ] **Step 1: Identify the 18 sigla keys**

Use `core/domain.py:SIGLAS` order:

```js
const SIGLAS = [
  "reunion", "irl", "odi", "charla", "chintegral", "dif_pts",
  "art", "insgral", "bodega", "maquinaria", "ext", "senal",
  "exc", "altura", "caliente", "herramientas_elec", "andamios", "chps",
];
```

- [ ] **Step 2: Write new `HospitalCard.jsx`**

```jsx
import { Building2, FolderX, PenLine } from "lucide-react";
import Dot from "../ui/Dot";
import Button from "../ui/Button";
import EmptyState from "../ui/EmptyState";
import Tooltip from "../ui/Tooltip";

const SIGLAS = [
  "reunion", "irl", "odi", "charla", "chintegral", "dif_pts",
  "art", "insgral", "bodega", "maquinaria", "ext", "senal",
  "exc", "altura", "caliente", "herramientas_elec", "andamios", "chps",
];

function dotVariantFor(cell) {
  if (!cell) return "neutral";
  if (cell.errors?.length > 0) return "state-error";
  if (cell.user_override !== null && cell.user_override !== undefined) return "state-override";
  if (cell.flags?.includes("compilation_suspect")) return "state-suspect";
  if (cell.confidence === "high") return "confidence-high";
  if (cell.confidence === "low") return "confidence-low";
  return "neutral";
}

export default function HospitalCard({ hospital, total, cells, status, onClick }) {
  if (status === "missing") {
    return (
      <div className="rounded-xl bg-po-panel border border-po-border p-5">
        <div className="flex items-center gap-2 mb-3">
          <Building2 size={14} strokeWidth={1.75} className="text-po-text-muted" />
          <span className="text-sm font-medium text-po-text">{hospital}</span>
        </div>
        <EmptyState
          icon={FolderX}
          title="Sin carpeta normalizada"
          description={`${hospital} no entrega PDFs por carpeta este mes. El flujo de ingreso manual estará disponible en una versión próxima.`}
          action={
            <Tooltip content="Disponible en FASE 4">
              <span>
                <Button disabled icon={PenLine}>Ingresar conteos</Button>
              </span>
            </Tooltip>
          }
        />
      </div>
    );
  }

  return (
    <button
      onClick={onClick}
      className="text-left rounded-xl bg-po-panel border border-po-border p-5 hover:border-po-border-strong transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-po-accent"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Building2 size={14} strokeWidth={1.75} className="text-po-text-muted" />
          <span className="text-sm font-medium text-po-text">{hospital}</span>
        </div>
      </div>
      <p className="text-4xl font-semibold tabular-nums">{(total ?? 0).toLocaleString()}</p>
      <p className="text-xs text-po-text-muted mt-0.5">documentos detectados</p>
      <div className="flex gap-0.5 mt-4" aria-label={`${SIGLAS.length} categorías`}>
        {SIGLAS.map((s) => (
          <Tooltip key={s} content={`${s}: ${cells?.[s]?.user_override ?? cells?.[s]?.ocr_count ?? cells?.[s]?.filename_count ?? 0}`}>
            <span><Dot variant={dotVariantFor(cells?.[s])} /></span>
          </Tooltip>
        ))}
      </div>
    </button>
  );
}
```

Note: the missing/HLL branch uses `Tooltip` with a wrapping `<span>` because Radix Tooltip requires a focusable child — the disabled Button can't capture pointer events. The wrapping `<span>` does.

- [ ] **Step 3: Verify build + visual**

```bash
cd frontend && npm run build
```

`npm run dev` → at localhost:5173:
- HPV/HRB/HLU cards show Building2 + total + 18 dots row
- HLL card shows FolderX + "Sin carpeta normalizada" + disabled "Ingresar conteos" button + tooltip on hover

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/HospitalCard.jsx
git commit -m "$(cat <<'EOF'
refactor(hospital-card): redesign with Building2 + ribbon of 18 dots + HLL empty state

Present state:
- Title row: Building2 icon + hospital code
- Big tabular-nums total
- 18-dot ribbon (one per sigla) with Tooltip on each showing sigla:count
  Dot color = confidence/state per dotVariantFor cascade

Missing state (HLL):
- FolderX icon
- 'Sin carpeta normalizada' EmptyState
- Disabled 'Ingresar conteos' Button + Tooltip 'Disponible en FASE 4'
  (manual-entry flow deferred per spec §5.3)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 19: `HospitalDetail.jsx` header redesign + grouping

**Files:**
- Modify: `frontend/src/views/HospitalDetail.jsx`

Spec §5.4 + §5.5 (header + 2 collapsible sections + 3-column grid).

- [ ] **Step 1: Write new `HospitalDetail.jsx`**

```jsx
import { useState } from "react";
import { ArrowLeft } from "lucide-react";
import { useSessionStore } from "../store/session";
import CategoryGroup from "../components/CategoryGroup";
import FileList from "../components/FileList";
import DetailPanel from "../components/DetailPanel";
import ScanControls from "../components/ScanControls";

const SIGLAS = [
  "reunion", "irl", "odi", "charla", "chintegral", "dif_pts",
  "art", "insgral", "bodega", "maquinaria", "ext", "senal",
  "exc", "altura", "caliente", "herramientas_elec", "andamios", "chps",
];

export default function HospitalDetail({ hospital, onBack }) {
  const { session } = useSessionStore();
  const [selected, setSelected] = useState(null);
  const [selectedSet, setSelectedSet] = useState(new Set());

  const cells = session?.cells?.[hospital] || {};
  const total = Object.values(cells).reduce(
    (s, c) => s + (c.user_override ?? c.ocr_count ?? c.filename_count ?? c.count ?? 0),
    0,
  );

  const normalized = SIGLAS.filter((s) => cells[s] && !cells[s].flags?.includes("compilation_suspect"));
  const compilations = SIGLAS.filter((s) => cells[s] && cells[s].flags?.includes("compilation_suspect"));

  const onCheck = (sigla, checked) => {
    setSelectedSet((prev) => {
      const next = new Set(prev);
      if (checked) next.add(sigla);
      else next.delete(sigla);
      return next;
    });
  };

  return (
    <div>
      <header className="flex items-center gap-4 mb-6">
        <button
          onClick={onBack}
          className="inline-flex items-center gap-1 text-sm text-po-text-muted hover:text-po-text"
        >
          <ArrowLeft size={16} strokeWidth={1.75} />
          Volver
        </button>
        <h2 className="text-xl font-semibold">{hospital}</h2>
        <span className="text-sm text-po-text-muted">
          Total: <span className="tabular-nums">{total.toLocaleString()}</span>
        </span>
        <div className="ml-auto">
          <ScanControls hospital={hospital} selectedSiglas={[...selectedSet]} />
        </div>
      </header>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)] gap-6">
        <section>
          <h3 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mb-3">Categorías</h3>
          <CategoryGroup
            title="Normalizadas"
            cells={normalized.map((s) => ({ sigla: s, ...cells[s] }))}
            hospital={hospital}
            selected={selected}
            onSelect={setSelected}
            checkedSet={selectedSet}
            onCheck={onCheck}
            defaultOpen
          />
          {compilations.length > 0 && (
            <CategoryGroup
              title="Compilaciones"
              cells={compilations.map((s) => ({ sigla: s, ...cells[s] }))}
              hospital={hospital}
              selected={selected}
              onSelect={setSelected}
              checkedSet={selectedSet}
              onCheck={onCheck}
              defaultOpen
              showScanAll
            />
          )}
        </section>

        <section>
          <h3 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mb-3">Detalle</h3>
          <DetailPanel hospital={hospital} sigla={selected} cell={selected ? cells[selected] : null} />
        </section>

        <section>
          <h3 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mb-3">Archivos</h3>
          <FileList hospital={hospital} sigla={selected} />
        </section>
      </div>
    </div>
  );
}
```

Note: `CategoryGroup` and `DetailPanel` don't exist yet — Tasks 20 + 22 create them. Build will fail until those land. To keep CI green, we wire stubs first.

- [ ] **Step 2: Create stub `CategoryGroup.jsx` (replaced in Task 20)**

Write `frontend/src/components/CategoryGroup.jsx`:

```jsx
// STUB — replaced in Task 20.
export default function CategoryGroup() {
  return <div className="text-po-text-muted text-sm">[CategoryGroup pending Task 20]</div>;
}
```

- [ ] **Step 3: Create stub `DetailPanel.jsx` (replaced in Task 22)**

Write `frontend/src/components/DetailPanel.jsx`:

```jsx
// STUB — replaced in Task 22.
export default function DetailPanel({ sigla }) {
  return <div className="text-po-text-muted text-sm">Selecciona una categoría {sigla ? `(${sigla})` : ""}</div>;
}
```

- [ ] **Step 4: Verify build**

```bash
cd frontend && npm run build
```

Expected: green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/HospitalDetail.jsx frontend/src/components/CategoryGroup.jsx frontend/src/components/DetailPanel.jsx
git commit -m "$(cat <<'EOF'
refactor(hospital-detail): redesign header + grouping (Normalizadas / Compilaciones)

- Header: ArrowLeft icon + Volver text-button, tabular-nums total
- Categorías partitioned into 2 sections by compilation_suspect flag
- Compilaciones section gets showScanAll prop (button moves out of
  ScanControls in Task 27)
- Stubs for CategoryGroup and DetailPanel — replaced in Tasks 20 and 22

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 20: `CategoryGroup.jsx` real implementation

**Files:**
- Modify: `frontend/src/components/CategoryGroup.jsx`

Spec §5.5 — collapsible section with header + optional scan-all button.

- [ ] **Step 1: Write the real implementation**

Write `frontend/src/components/CategoryGroup.jsx` (REPLACES the stub from Task 19):

```jsx
import { useState } from "react";
import { ChevronDown, ChevronRight, Scan } from "lucide-react";
import CategoryRow from "./CategoryRow";
import Button from "../ui/Button";
import { useSessionStore } from "../store/session";

export default function CategoryGroup({
  title,
  cells,
  hospital,
  selected,
  onSelect,
  checkedSet,
  onCheck,
  defaultOpen = true,
  showScanAll = false,
}) {
  const [open, setOpen] = useState(defaultOpen);
  const session = useSessionStore((s) => s.session);
  const scanOcr = useSessionStore((s) => s.scanOcr);

  const scanAll = () => {
    const pairs = cells.map((c) => [hospital, c.sigla]);
    scanOcr(session.session_id, pairs);
  };

  return (
    <div className="border-b border-po-border last:border-b-0 mb-2 last:mb-0">
      <div className="flex items-center justify-between py-2 px-1">
        <button
          onClick={() => setOpen((v) => !v)}
          className="inline-flex items-center gap-2 text-sm font-medium text-po-text hover:text-po-accent"
        >
          {open ? <ChevronDown size={14} strokeWidth={1.75} /> : <ChevronRight size={14} strokeWidth={1.75} />}
          {title}
          <span className="text-po-text-muted font-normal">· {cells.length}</span>
        </button>
        {showScanAll && open && (
          <Button size="sm" icon={Scan} onClick={scanAll} disabled={cells.length === 0}>
            Escanear todas
          </Button>
        )}
      </div>
      {open && (
        <div>
          {cells.map((cell) => (
            <CategoryRow
              key={cell.sigla}
              sigla={cell.sigla}
              cell={cell}
              hospital={hospital}
              selected={selected === cell.sigla}
              onSelect={() => onSelect(cell.sigla)}
              checked={checkedSet.has(cell.sigla)}
              onCheckChange={(c) => onCheck(cell.sigla, c)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build
```

Build will warn or fail because `CategoryRow` still has the OLD shape. That's expected — Task 21 redesigns CategoryRow. To keep the build green right now, the CategoryRow's CURRENT signature must accept the props we're passing. Inspect:

```bash
head -50 frontend/src/components/CategoryRow.jsx
```

If the existing CategoryRow props differ (e.g., the old one expects `onClick` not `onSelect`), defer this commit and do Tasks 20 + 21 atomically. Otherwise commit now.

For safety, do Tasks 20 + 21 in a single commit. Skip the commit step here.

- [ ] **Step 3: Defer commit — bundled with Task 21**

---

### Task 21: `CategoryRow.jsx` redesign with `InlineEditCount`

**Files:**
- Modify: `frontend/src/components/CategoryRow.jsx`
- Delete: `frontend/src/components/ConfidenceBadge.jsx` (subsumed by Badge primitive)

Spec §5.5 — single-line 32px row, Dot + Badge + InlineEditCount.

- [ ] **Step 1: Write new `CategoryRow.jsx`**

```jsx
import { useState } from "react";
import {
  Loader2, AlertCircle, FileStack, PenLine,
} from "lucide-react";
import { useSessionStore } from "../store/session";
import Badge from "../ui/Badge";
import Dot from "../ui/Dot";
import Tooltip from "../ui/Tooltip";
import { SIGLA_LABELS } from "../lib/sigla-labels";

function dotVariantFor(cell, isScanning, hasOverride) {
  if (isScanning) return "state-scanning";
  if (cell?.errors?.length > 0) return "state-error";
  if (hasOverride) return "state-override";
  if (cell?.flags?.includes("compilation_suspect")) return "state-suspect";
  if (cell?.confidence === "high") return "confidence-high";
  if (cell?.confidence === "low") return "confidence-low";
  return "neutral";
}

function effectiveCount(cell) {
  return cell?.user_override ?? cell?.ocr_count ?? cell?.filename_count ?? cell?.count ?? 0;
}

function InlineEditCount({ value, onCommit }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  if (!editing) {
    return (
      <button
        onClick={(e) => {
          e.stopPropagation();
          setDraft(value ?? "");
          setEditing(true);
        }}
        className="font-mono tabular-nums text-sm w-14 text-right hover:text-po-accent focus-visible:outline-none focus-visible:text-po-accent"
      >
        {value?.toLocaleString() ?? "—"}
      </button>
    );
  }

  return (
    <input
      type="number"
      autoFocus
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          const v = parseInt(draft, 10);
          if (!Number.isNaN(v)) onCommit(v);
          setEditing(false);
        } else if (e.key === "Escape") {
          setEditing(false);
        }
      }}
      onBlur={() => setEditing(false)}
      className="font-mono tabular-nums text-sm w-14 text-right bg-po-bg border border-po-accent rounded px-1 focus-visible:outline-none"
    />
  );
}

export default function CategoryRow({
  sigla,
  cell,
  hospital,
  selected,
  onSelect,
  checked,
  onCheckChange,
}) {
  const scanningCells = useSessionStore((s) => s.scanningCells);
  const pendingSaves = useSessionStore((s) => s.pendingSaves);
  const session = useSessionStore((s) => s.session);
  const saveOverride = useSessionStore((s) => s.saveOverride);

  const cellKey = `${hospital}|${sigla}`;
  const isScanning = scanningCells.has(cellKey);
  const isPendingSave = pendingSaves[cellKey] === "saving";
  const hasOverride = cell?.user_override !== null && cell?.user_override !== undefined;
  const isCompilationSuspect = cell?.flags?.includes("compilation_suspect");
  const hasError = cell?.errors?.length > 0;

  const onCommitCount = (v) => {
    saveOverride(session.session_id, hospital, sigla, v, cell?.override_note ?? null);
  };

  return (
    <div
      onClick={onSelect}
      className={[
        "flex items-center gap-3 px-3 h-8 cursor-pointer transition",
        "hover:bg-po-panel-hover",
        selected && "bg-po-panel-hover border-l-2 border-po-accent",
      ].filter(Boolean).join(" ")}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onCheckChange(e.target.checked)}
        onClick={(e) => e.stopPropagation()}
        className="accent-po-accent"
      />
      <Tooltip content={SIGLA_LABELS[sigla] ?? null}>
        <span className="font-mono text-xs text-po-text">{sigla}</span>
      </Tooltip>
      <Dot variant={dotVariantFor(cell, isScanning, hasOverride)} className={isPendingSave ? "animate-pulse" : ""} />

      <div className="ml-auto flex items-center gap-2">
        {isScanning ? (
          <Badge variant="state-scanning" icon={Loader2}>Escaneando…</Badge>
        ) : (
          <>
            {hasError && (
              <Tooltip content={cell.errors[0]}>
                <span><Badge variant="state-error" icon={AlertCircle}>Error</Badge></span>
              </Tooltip>
            )}
            {hasOverride && <Badge variant="state-override" icon={PenLine}>Manual</Badge>}
            {isCompilationSuspect && !hasOverride && (
              <Tooltip content="Probable compilación (PDF con >5× páginas esperadas)">
                <span><Badge variant="state-suspect" icon={FileStack}>Compilación</Badge></span>
              </Tooltip>
            )}
            <InlineEditCount value={effectiveCount(cell)} onCommit={onCommitCount} />
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Delete `ConfidenceBadge.jsx`**

```bash
git rm frontend/src/components/ConfidenceBadge.jsx
```

(Subsumed by the Badge primitive.)

- [ ] **Step 3: Verify build + visual smoke**

```bash
cd frontend && npm run build
```

Expected: green.

```bash
cd frontend && npm run dev
```

At localhost:5173:
- Open ABRIL → HPV → see CategoryGroup "Normalizadas (N)" + "Compilaciones (M)" with collapse chevrons
- Each CategoryRow shows: checkbox + sigla mono + Dot + (badges) + count
- Click sigla → tooltip with `SIGLA_LABELS` content
- Click count → input appears, type new value, Enter → save → dot turns violet, "Manual" badge appears
- Click "Escanear todas" in Compilaciones header → ScanProgress bar appears

- [ ] **Step 4: Commit (Tasks 20 + 21 together)**

```bash
git add frontend/src/components/CategoryGroup.jsx frontend/src/components/CategoryRow.jsx frontend/src/components/ConfidenceBadge.jsx
git commit -m "$(cat <<'EOF'
refactor(category): grouping + single-line 32px row + InlineEditCount

CategoryGroup: collapsible section with title + count + optional 'Escanear
todas' button (passed via showScanAll for the Compilaciones group).
Compilaciones gets the scan button at its header, replacing the old global
'OCR suspects de HPV' button.

CategoryRow: 32px Linear-density row. Checkbox + mono sigla + Dot (semantic
state) + Tooltip with human label on sigla hover + Badge(s) for
suspect/override/error/scanning + InlineEditCount on the count.

InlineEditCount: click number → input, Enter commits via store.saveOverride
(routes through AbortController per spec §6.6), Esc cancels. Blur cancels.

ConfidenceBadge.jsx deleted — Badge primitive supersedes.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 22: `DetailPanel.jsx` real implementation

**Files:**
- Modify: `frontend/src/components/DetailPanel.jsx`

Spec §5.6 — Notion-style: big number + state pills + breakdown table + OverridePanel below.

- [ ] **Step 1: Write the real implementation**

Write `frontend/src/components/DetailPanel.jsx` (REPLACES the stub from Task 19):

```jsx
import { MousePointer2, FileStack, PenLine } from "lucide-react";
import OverridePanel from "./OverridePanel";
import EmptyState from "../ui/EmptyState";
import Badge from "../ui/Badge";
import Tooltip from "../ui/Tooltip";
import { SIGLA_LABELS } from "../lib/sigla-labels";
import { METHOD_LABEL, CONFIDENCE_LABEL } from "../lib/method-labels";

function effectiveCount(cell) {
  return cell?.user_override ?? cell?.ocr_count ?? cell?.filename_count ?? cell?.count ?? 0;
}

function confidenceVariant(cell) {
  if (cell?.confidence === "high") return "confidence-high";
  if (cell?.confidence === "low") return "confidence-low";
  return "neutral";
}

export default function DetailPanel({ hospital, sigla, cell }) {
  if (!cell || !sigla) {
    return (
      <EmptyState
        icon={MousePointer2}
        title="Selecciona una categoría"
        description="Elige una sigla de la lista para ver el conteo, ajustar manualmente y abrir los archivos."
      />
    );
  }

  const isCompilationSuspect = cell.flags?.includes("compilation_suspect");
  const hasOverride = cell.user_override !== null && cell.user_override !== undefined;
  const total = effectiveCount(cell);
  const label = SIGLA_LABELS[sigla];
  const showLabel = label && label.toLowerCase() !== sigla.toLowerCase();

  return (
    <div className="rounded-xl bg-po-panel border border-po-border p-5">
      <div className="flex items-baseline gap-2 mb-1">
        <span className="font-mono text-sm text-po-text">{sigla}</span>
        {showLabel && (
          <>
            <span className="text-po-text-muted">·</span>
            <span className="text-sm text-po-text">{label}</span>
          </>
        )}
      </div>

      <p className="text-5xl font-semibold tabular-nums mt-4">{total.toLocaleString()}</p>
      <p className="text-xs text-po-text-muted mt-0.5">documentos</p>

      <div className="flex flex-wrap gap-2 mt-3">
        {isCompilationSuspect && (
          <Tooltip content="Probable compilación (PDF con >5× páginas esperadas)">
            <span><Badge variant="state-suspect" icon={FileStack}>Compilación</Badge></span>
          </Tooltip>
        )}
        {cell.confidence && (
          <Badge variant={confidenceVariant(cell)}>{CONFIDENCE_LABEL[cell.confidence] ?? cell.confidence}</Badge>
        )}
        {hasOverride && <Badge variant="state-override" icon={PenLine}>Manual</Badge>}
      </div>

      <h4 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mt-6 mb-2">Conteo automático</h4>
      <table className="w-full text-sm">
        <tbody>
          <tr>
            <td className="text-po-text-muted py-1">Por nombre de archivo</td>
            <td className="text-right font-mono tabular-nums">{cell.filename_count ?? "—"}</td>
          </tr>
          <tr>
            <td className="text-po-text-muted py-1">Por OCR</td>
            <td className="text-right font-mono tabular-nums">{cell.ocr_count ?? "—"}</td>
          </tr>
          <tr>
            <td className="text-po-text-muted py-1">Método</td>
            <td className="text-right">
              <Tooltip content={`Token interno: ${cell.method ?? "—"}`}>
                <span>{METHOD_LABEL[cell.method] ?? cell.method ?? "—"}</span>
              </Tooltip>
            </td>
          </tr>
        </tbody>
      </table>

      <h4 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mt-6 mb-2">Ajuste manual</h4>
      <OverridePanel hospital={hospital} sigla={sigla} cell={cell} />
    </div>
  );
}
```

- [ ] **Step 2: Verify build + visual**

```bash
cd frontend && npm run build
```

`npm run dev` → click a sigla → DetailPanel shows: sigla + label + big number + pills + breakdown table + override panel. OverridePanel still the OLD shape (rewritten in Task 26).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/DetailPanel.jsx
git commit -m "$(cat <<'EOF'
refactor(detail-panel): Notion-style with big number + pills + breakdown table

- Title: sigla mono + human label (omitted if label.lower === sigla.lower)
- 5xl tabular-nums total (the question 'how many?' answered loudly)
- Pill row: Compilación tooltip / confidence label / Manual override
- Breakdown table: Por nombre de archivo / Por OCR / Método (with raw token
  in tooltip)
- OverridePanel rendered below as 'Ajuste manual' section

Replaces the old 5-stacked-paragraph format ('Sigla:' / 'Filename:' /
'OCR:' / 'Confidence:' / 'Flags:').

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 23: `FileList.jsx` redesign

**Files:**
- Modify: `frontend/src/components/FileList.jsx`

Spec §5.7.

- [ ] **Step 1: Read current FileList to preserve API**

```bash
grep -n "useEffect\|fetch\|api\." frontend/src/components/FileList.jsx
```

Note what props it takes and what API it calls. Preserve fetch logic; only redesign markup.

- [ ] **Step 2: Write new `FileList.jsx`**

```jsx
import { useEffect, useState } from "react";
import { FileText, FileStack, FileX, MousePointer2 } from "lucide-react";
import { useSessionStore } from "../store/session";
import { api } from "../lib/api";
import EmptyState from "../ui/EmptyState";
import Skeleton from "../ui/Skeleton";
import Tooltip from "../ui/Tooltip";

export default function FileList({ hospital, sigla }) {
  const session = useSessionStore((s) => s.session);
  const openLightbox = useSessionStore((s) => s.openLightbox);
  const [files, setFiles] = useState(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (!session?.session_id || !hospital || !sigla) {
      setFiles(null);
      return;
    }
    setFiles(null);
    api.getCellFiles(session.session_id, hospital, sigla)
      .then(setFiles)
      .catch((err) => setFiles({ error: String(err) }));
  }, [session?.session_id, hospital, sigla]);

  if (!sigla) {
    return (
      <EmptyState
        icon={MousePointer2}
        title="Selecciona una categoría"
        description="Elige una sigla para ver los archivos PDF asociados."
      />
    );
  }

  if (files === null) {
    return (
      <div className="space-y-2">
        {[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-10" />)}
      </div>
    );
  }

  if (files?.error) {
    return (
      <EmptyState
        icon={FileX}
        title="No se pudieron cargar los archivos"
        description={files.error}
      />
    );
  }

  if (files.length === 0) {
    return (
      <EmptyState
        icon={FileX}
        title="Sin archivos"
        description="Esta categoría no tiene archivos PDF en este mes."
      />
    );
  }

  const filtered = files.filter((f) =>
    f.name.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="rounded-xl bg-po-panel border border-po-border overflow-hidden">
      <div className="p-2 border-b border-po-border">
        <input
          placeholder="Buscar archivo…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full bg-transparent text-sm text-po-text placeholder-po-text-subtle focus:outline-none px-2 py-1"
        />
      </div>
      <ul className="max-h-[60vh] overflow-y-auto">
        {filtered.map((f, i) => (
          <li key={`${f.name}-${i}`}>
            <button
              onClick={() => openLightbox(hospital, sigla, files.indexOf(f))}
              className="w-full flex items-center gap-2 px-3 py-2 hover:bg-po-panel-hover text-left transition"
            >
              <FileText size={14} strokeWidth={1.75} className="text-po-text-muted shrink-0" />
              <span className="font-mono text-xs text-po-text truncate flex-1">{f.name}</span>
              <span className="text-xs tabular-nums text-po-text-muted shrink-0">{f.page_count}pp</span>
              {f.suspect && (
                <Tooltip content="Probable compilación">
                  <span><FileStack size={14} strokeWidth={1.75} className="text-po-suspect shrink-0" /></span>
                </Tooltip>
              )}
            </button>
          </li>
        ))}
      </ul>
      <div className="px-3 py-2 text-xs text-po-text-muted border-t border-po-border">
        {filtered.length} de {files.length}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify build + visual**

```bash
cd frontend && npm run build
```

`npm run dev` → click HPV → click a sigla with files → FileList shows search input + scrollable file rows + footer count. Click a file → PDFLightbox opens (still old, redesigned in Task 24).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/FileList.jsx
git commit -m "$(cat <<'EOF'
refactor(file-list): redesign with Skeleton loaders + EmptyState + lucide icons

- FileText (14px) leads each row
- Filename in font-mono with truncate
- Page count tabular-nums right-aligned
- FileStack icon (replaces ⚠) shows compilation_suspect with tooltip
- Skeleton loaders while files load
- EmptyState for: no sigla selected / no files / error

Behavior preserved: search filter, click row → openLightbox at correct
index in the unfiltered files list.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 24: `PDFLightbox.jsx` redesign with Radix Dialog

**Files:**
- Modify: `frontend/src/components/PDFLightbox.jsx`

Spec §5.9.

- [ ] **Step 1: Read current PDFLightbox state**

```bash
head -30 frontend/src/components/PDFLightbox.jsx
```

Note the URL it uses for the iframe + the file fetching logic.

- [ ] **Step 2: Write new `PDFLightbox.jsx`**

```jsx
import { useEffect, useState } from "react";
import { useSessionStore } from "../store/session";
import { api } from "../lib/api";
import Dialog from "../ui/Dialog";
import OverridePanel from "./OverridePanel";
import Badge from "../ui/Badge";
import Tooltip from "../ui/Tooltip";
import { FileStack, PenLine } from "lucide-react";
import { SIGLA_LABELS } from "../lib/sigla-labels";
import { METHOD_LABEL, CONFIDENCE_LABEL } from "../lib/method-labels";

function effectiveCount(cell) {
  return cell?.user_override ?? cell?.ocr_count ?? cell?.filename_count ?? cell?.count ?? 0;
}

function confidenceVariant(cell) {
  if (cell?.confidence === "high") return "confidence-high";
  if (cell?.confidence === "low") return "confidence-low";
  return "neutral";
}

function CountSummary({ cell }) {
  const isCompilationSuspect = cell?.flags?.includes("compilation_suspect");
  const hasOverride = cell?.user_override !== null && cell?.user_override !== undefined;
  return (
    <div>
      <p className="text-4xl font-semibold tabular-nums">{effectiveCount(cell).toLocaleString()}</p>
      <p className="text-xs text-po-text-muted mt-0.5">documentos</p>
      <div className="flex flex-wrap gap-2 mt-3">
        {isCompilationSuspect && (
          <Tooltip content="Probable compilación">
            <span><Badge variant="state-suspect" icon={FileStack}>Compilación</Badge></span>
          </Tooltip>
        )}
        {cell?.confidence && (
          <Badge variant={confidenceVariant(cell)}>{CONFIDENCE_LABEL[cell.confidence] ?? cell.confidence}</Badge>
        )}
        {hasOverride && <Badge variant="state-override" icon={PenLine}>Manual</Badge>}
      </div>
      <table className="w-full text-sm mt-4">
        <tbody>
          <tr><td className="text-po-text-muted py-1 text-xs">Por nombre</td><td className="text-right font-mono tabular-nums text-xs">{cell?.filename_count ?? "—"}</td></tr>
          <tr><td className="text-po-text-muted py-1 text-xs">Por OCR</td><td className="text-right font-mono tabular-nums text-xs">{cell?.ocr_count ?? "—"}</td></tr>
          <tr><td className="text-po-text-muted py-1 text-xs">Método</td><td className="text-right text-xs">{METHOD_LABEL[cell?.method] ?? cell?.method ?? "—"}</td></tr>
        </tbody>
      </table>
    </div>
  );
}

export default function PDFLightbox() {
  const lightbox = useSessionStore((s) => s.lightbox);
  const closeLightbox = useSessionStore((s) => s.closeLightbox);
  const session = useSessionStore((s) => s.session);
  const [files, setFiles] = useState(null);

  useEffect(() => {
    if (!lightbox) { setFiles(null); return; }
    api.getCellFiles(session.session_id, lightbox.hospital, lightbox.sigla)
      .then(setFiles)
      .catch(() => setFiles([]));
  }, [lightbox?.hospital, lightbox?.sigla, session?.session_id]);

  if (!lightbox || !session) return null;

  const cell = session.cells?.[lightbox.hospital]?.[lightbox.sigla] ?? null;
  const filename = files?.[lightbox.fileIndex]?.name ?? "…";
  const pageCount = files?.[lightbox.fileIndex]?.page_count;
  const pdfUrl = `/api/sessions/${session.session_id}/cells/${lightbox.hospital}/${lightbox.sigla}/pdf?index=${lightbox.fileIndex}`;
  const label = SIGLA_LABELS[lightbox.sigla];
  const showLabel = label && label.toLowerCase() !== lightbox.sigla.toLowerCase();

  return (
    <Dialog open={!!lightbox} onOpenChange={(o) => !o && closeLightbox()}>
      <Dialog.Header>
        <div className="flex items-center gap-2 text-sm">
          <span className="font-mono text-po-text-muted">{lightbox.hospital}</span>
          <span className="text-po-text-muted">·</span>
          <span className="font-mono text-po-text">{lightbox.sigla}</span>
          {showLabel && (
            <>
              <span className="text-po-text-muted">·</span>
              <span className="text-po-text">{label}</span>
            </>
          )}
        </div>
        <div className="font-mono text-xs text-po-text-muted truncate mt-0.5">
          {filename}{pageCount ? ` · ${pageCount}pp` : ""}
        </div>
      </Dialog.Header>
      <Dialog.Body>
        <div className="flex-1 bg-black">
          <iframe src={pdfUrl} className="w-full h-full border-0" title={filename} />
        </div>
        <aside className="w-80 border-l border-po-border p-4 overflow-y-auto">
          <CountSummary cell={cell} />
          <h4 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mt-6 mb-2">Ajuste manual</h4>
          <OverridePanel hospital={lightbox.hospital} sigla={lightbox.sigla} cell={cell} />
        </aside>
      </Dialog.Body>
    </Dialog>
  );
}
```

- [ ] **Step 3: Verify build + visual + a11y**

```bash
cd frontend && npm run build
```

`npm run dev` → open a file in any cell → Dialog opens:
- iframe shows the PDF
- right panel shows CountSummary + OverridePanel
- Tab cycles within the Dialog (focus trap from Radix)
- Escape closes
- Click overlay closes

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/PDFLightbox.jsx
git commit -m "$(cat <<'EOF'
refactor(pdf-lightbox): wrap with Radix Dialog + 2-line header + CountSummary

- Outer chrome is Dialog primitive (focus trap, ESC, click-outside,
  body scroll lock — all free from Radix)
- Header is 2 lines: hospital · sigla · label / filename · pageCount
- Right panel: CountSummary (mirrors DetailPanel breakdown table at
  narrower width) + OverridePanel
- Preserves iframe-based PDF rendering (browser's native viewer)

Old PDFLightbox had no focus trap — Tab escaped to body. Radix fixes
this for free.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Chunk 3 review checkpoint

After Tasks 14-24 commit cleanly:

- [ ] `cd frontend && npm run build` — green
- [ ] Visual smoke: open ABRIL → HPV → 2 grouped sections → click sigla → DetailPanel + FileList → click file → PDFLightbox opens with Radix focus trap
- [ ] **Dispatch chunk-3 plan-reviewer subagent.** Pass: chunk 3 content + spec path. Fix any blocking findings.

---

## Chunk 4: Polish + audit + smoke

5 tasks: OverridePanel SaveIndicator wiring, ScanControls trim, ScanProgress redesign, grep audit gating, manual smoke + tag.

### Task 25: `OverridePanel.jsx` redesign with `SaveIndicator` + debounce

**Files:**
- Modify: `frontend/src/components/OverridePanel.jsx`

Spec §5.8 + §6.6.

- [ ] **Step 1: Write new `OverridePanel.jsx`**

```jsx
import { useEffect, useState } from "react";
import { useSessionStore } from "../store/session";
import { useDebouncedCallback } from "../lib/hooks/useDebouncedCallback";
import SaveIndicator from "../ui/SaveIndicator";

export default function OverridePanel({ hospital, sigla, cell }) {
  const session = useSessionStore((s) => s.session);
  const saveOverride = useSessionStore((s) => s.saveOverride);
  const pendingSaves = useSessionStore((s) => s.pendingSaves);

  const cellKey = `${hospital}|${sigla}`;
  const saveStatus = pendingSaves[cellKey] ?? "idle";

  const [value, setValue] = useState(cell?.user_override ?? "");
  const [note, setNote] = useState(cell?.override_note ?? "");
  const [focused, setFocused] = useState({ value: false, note: false });

  // Resync from store when cell changes (e.g., InlineEditCount committed externally),
  // but ONLY if not currently editing that field.
  useEffect(() => {
    if (!focused.value) setValue(cell?.user_override ?? "");
  }, [cell?.user_override, focused.value]);

  useEffect(() => {
    if (!focused.note) setNote(cell?.override_note ?? "");
  }, [cell?.override_note, focused.note]);

  const flushSave = useDebouncedCallback((v, n) => {
    const numericValue = v === "" || v === null ? null : parseInt(v, 10);
    saveOverride(session.session_id, hospital, sigla, numericValue, n || null);
  }, 400);

  const onChangeValue = (e) => {
    setValue(e.target.value);
    flushSave(e.target.value, note);
  };
  const onChangeNote = (e) => {
    setNote(e.target.value);
    flushSave(value, e.target.value);
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <input
          type="number"
          value={value}
          placeholder={String(cell?.ocr_count ?? cell?.filename_count ?? 0)}
          onChange={onChangeValue}
          onFocus={() => setFocused((f) => ({ ...f, value: true }))}
          onBlur={() => setFocused((f) => ({ ...f, value: false }))}
          className="w-24 bg-po-bg border border-po-border rounded px-2 py-1.5 text-sm tabular-nums focus:border-po-accent outline-none"
        />
        <SaveIndicator status={saveStatus} />
      </div>
      <textarea
        value={note}
        placeholder="Nota (opcional)"
        onChange={onChangeNote}
        onFocus={() => setFocused((f) => ({ ...f, note: true }))}
        onBlur={() => setFocused((f) => ({ ...f, note: false }))}
        rows={3}
        className="w-full bg-po-bg border border-po-border rounded px-2 py-1.5 text-sm placeholder-po-text-subtle focus:border-po-accent outline-none resize-none"
      />
    </div>
  );
}
```

- [ ] **Step 2: Verify build + visual smoke**

```bash
cd frontend && npm run build
```

`npm run dev` → open HPV → click reunion → in OverridePanel:
- Type a number → after 400ms, SaveIndicator shows "Guardando…" → "Guardado" → fades after 2s
- Type a note → same flow
- Cell row dot turns violet, "Manual" badge appears

Test race: type in OverridePanel → before debounce flushes, type in InlineEditCount in another row of CategoryRow → the second action should NOT cancel the first (different cell key). Within the SAME cell, two rapid commits should result in last-wins behavior.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/OverridePanel.jsx
git commit -m "$(cat <<'EOF'
refactor(override-panel): redesign with debounced autosave + SaveIndicator

- 400ms debounce via useDebouncedCallback hook (zero-dep)
- SaveIndicator shows idle/saving/saved/error per pendingSaves[key]
- Local state resyncs from cell.user_override / cell.override_note only
  when NOT focused — prevents InlineEditCount commits from clobbering
  the user's in-progress typing
- All writes route through store.saveOverride per spec §6.6 (AbortController
  cancellation, single pending entry per cell)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 26: `ScanControls.jsx` redesign + move 'OCR suspects' out

**Files:**
- Modify: `frontend/src/components/ScanControls.jsx`

Spec §5.10. The "OCR suspects" button is gone — replaced by per-CategoryGroup "Escanear todas" button (already in Task 20). ScanControls becomes a single button: "Escanear {n} categoría(s)".

- [ ] **Step 1: Write new `ScanControls.jsx`**

```jsx
import { Scan } from "lucide-react";
import { useSessionStore } from "../store/session";
import Button from "../ui/Button";

export default function ScanControls({ hospital, selectedSiglas }) {
  const session = useSessionStore((s) => s.session);
  const scanOcr = useSessionStore((s) => s.scanOcr);

  const n = selectedSiglas.length;

  const onClick = () => {
    if (n === 0) return;
    const pairs = selectedSiglas.map((s) => [hospital, s]);
    scanOcr(session.session_id, pairs);
  };

  let label;
  if (n === 0) label = "Selecciona categorías para OCR";
  else if (n === 1) label = "Escanear 1 categoría";
  else label = `Escanear ${n} categorías`;

  return (
    <Button
      variant={n > 0 ? "primary" : "secondary"}
      icon={Scan}
      disabled={n === 0}
      onClick={onClick}
    >
      {label}
    </Button>
  );
}
```

- [ ] **Step 2: Verify build + visual**

```bash
cd frontend && npm run build
```

`npm run dev` → HPV → tick 2 checkboxes → header button reads "Escanear 2 categorías" + indigo. Untick all → reads "Selecciona categorías para OCR" + secondary + disabled.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ScanControls.jsx
git commit -m "$(cat <<'EOF'
refactor(scan-controls): single pluralized Button + remove duplicate suspects action

- Copy: 'Selecciona categorías para OCR' (disabled, n=0)
       / 'Escanear 1 categoría' / 'Escanear N categorías'
- Variant flips to primary when n > 0
- Scan icon prefix
- 'OCR suspects de HPV' button removed — moved to CategoryGroup
  'Compilaciones' header in Task 20 (showScanAll prop)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 27: `ScanProgress.jsx` redesign

**Files:**
- Modify: `frontend/src/components/ScanProgress.jsx`

Spec §5.11.

- [ ] **Step 1: Write new `ScanProgress.jsx`**

```jsx
import { CheckCircle2, X, Loader2 } from "lucide-react";
import { useSessionStore } from "../store/session";
import Badge from "../ui/Badge";
import Button from "../ui/Button";

export default function ScanProgress() {
  const scanProgress = useSessionStore((s) => s.scanProgress);
  const session = useSessionStore((s) => s.session);
  const cancelScan = useSessionStore((s) => s.cancelScan);

  if (!scanProgress) return null;

  const { done, total, etaMs, terminal } = scanProgress;
  const pct = total > 0 ? Math.min(100, (done / total) * 100) : 0;

  let icon, label, iconColorClass;
  if (terminal === "complete") {
    icon = <CheckCircle2 size={16} strokeWidth={1.75} />;
    iconColorClass = "text-po-success";
    label = "Completado";
  } else if (terminal === "cancelled") {
    icon = <X size={16} strokeWidth={1.75} />;
    iconColorClass = "text-po-error";
    label = "Cancelado";
  } else {
    icon = <Loader2 size={16} strokeWidth={1.75} className="animate-spin" />;
    iconColorClass = "text-po-scanning";
    label = "Escaneando…";
  }

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-40 bg-po-panel border border-po-border rounded-xl shadow-2xl p-4 min-w-[400px]">
      <div className="flex items-center gap-3 mb-2">
        <span className={iconColorClass}>{icon}</span>
        <span className="text-sm font-medium text-po-text">{label}</span>
        <Badge variant="neutral" className="ml-auto">{done}/{total}</Badge>
        {etaMs && !terminal && (
          <span className="text-xs text-po-text-muted">~{Math.round(etaMs / 1000)}s</span>
        )}
        {!terminal && (
          <Button
            variant="destructive"
            size="sm"
            onClick={() => cancelScan(session.session_id)}
          >
            Cancelar
          </Button>
        )}
      </div>
      <div className="h-1.5 bg-po-border rounded-full overflow-hidden">
        <div
          className="h-full bg-po-accent transition-all duration-200"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify build + visual smoke**

```bash
cd frontend && npm run build
```

`npm run dev` → trigger an OCR scan (CategoryGroup "Compilaciones" → "Escanear todas"):
- Bar appears at z-40 (above page content, below Dialog if open)
- Spinner animates, label "Escaneando…", count tabular-nums in Badge
- "Cancelar" button has destructive styling (po-error outline)
- After complete: icon swaps to CheckCircle2 in po-success, auto-dismisses ~5s

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ScanProgress.jsx
git commit -m "$(cat <<'EOF'
refactor(scan-progress): icons + Badge + destructive Cancel + z-40

- Loader2 spin / CheckCircle2 (success) / X (cancelled) lucide icons
- 'Completado' / 'Cancelado' / 'Escaneando…' labels
- done/total in neutral Badge with tabular-nums
- ETA in po-text-muted micro
- Cancel button: destructive variant (po-error outline)
- Progress bar: po-accent fill, smooth 200ms transition

Sits at z-40 in the ladder (below Dialog overlay z-50, below Toaster z-60).

Auto-dismiss after terminal events preserved from FASE 2 behavior.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 28: Grep audit gating — zero raw palette classes

**Files:**
- Verify only — no edits unless audit fails.

Spec §7 AC9 + §12 Chunk 4 gating task.

- [ ] **Step 1: Run the grep audit**

```bash
cd frontend && grep -rE "bg-slate-|bg-indigo-|bg-emerald-|bg-rose-|bg-amber-|bg-violet-|border-slate-|border-indigo-|border-emerald-|border-rose-|text-slate-|text-indigo-|text-emerald-|text-rose-" src/**/*.jsx src/**/*.js
```

Expected: empty.

- [ ] **Step 2: If hits found, migrate**

For each match:
1. Identify the file + line
2. Map the raw class to the semantic `po-*` token (refer to spec §4.1 table)
3. Edit the file to replace

Examples of mappings:
- `bg-slate-950` → `bg-po-bg`
- `bg-slate-900` → `bg-po-panel`
- `bg-slate-800` → `bg-po-panel-hover`
- `border-slate-800` → `border-po-border`
- `border-slate-700` → `border-po-border-strong`
- `text-slate-100` → `text-po-text`
- `text-slate-400` → `text-po-text-muted`
- `text-slate-500` → `text-po-text-subtle`
- `bg-indigo-600` → `bg-po-accent`
- `bg-emerald-700` → `bg-po-success` (if context is success state) — otherwise pick the semantic token by use case
- `bg-rose-500` / `text-rose-400` → `bg-po-error` / `text-po-error`
- `bg-amber-500` / `text-amber-400` → `bg-po-suspect` / `text-po-suspect`

If you encounter a class where the semantic mapping is ambiguous, ask the controller. Don't guess.

- [ ] **Step 3: Re-run audit until empty**

Repeat Step 1 until output is empty. Then verify build:

```bash
cd frontend && npm run build
```

Expected: green.

- [ ] **Step 4: Commit (if any migrations happened)**

If any files were edited:

```bash
git add frontend/src/
git commit -m "$(cat <<'EOF'
style(frontend): final palette migration — zero raw Tailwind palette classes

Closes the grep audit gating per spec §7 AC9. Every JSX className that
referenced bg-slate-*, bg-indigo-*, bg-emerald-*, etc. now uses a po-*
semantic token. No Frankenstein theme — raw palette is OFF the table.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

If no edits needed (audit was clean from the start), no commit — proceed to Task 30.

---

### Task 29: Final smoke test + CLAUDE.md + tag

**Files:**
- Modify: `a:/PROJECTS/PDFoverseer/CLAUDE.md` — add FASE 3 section
- Tag: `fase-3-polish` (local only — push pending Daniel approval)

- [ ] **Step 1: Smoke pre-flight + start backend + frontend**

**Pre-flight — verify env vars are set:**

```bash
.venv-cuda/Scripts/python.exe -c "import os; assert os.environ.get('INFORME_MENSUAL_ROOT'), 'INFORME_MENSUAL_ROOT not set — point it at A:/informe mensual'; assert os.path.exists(os.environ['INFORME_MENSUAL_ROOT']), f\"path does not exist: {os.environ['INFORME_MENSUAL_ROOT']}\"; print('OK', os.environ['INFORME_MENSUAL_ROOT'])"
```

Expected: prints `OK A:/informe mensual` (or wherever the corpus lives). If it asserts, set the env var before starting the server.

**Start backend + frontend in separate terminals** (do NOT use `&` background — Windows PowerShell doesn't support it; foreground each in its own terminal):

```
# Terminal 1
.venv-cuda/Scripts/python.exe server.py
```

```
# Terminal 2
cd frontend && npm run dev
```

Wait for both: `uvicorn running on http://127.0.0.1:8000` from terminal 1, and `Local: http://localhost:5173` from terminal 2.

Open `localhost:5173`. Walk through the 15 acceptance criteria from spec §7:

1. **Open ABRIL → MonthOverview** — 4 cards: HPV/HRB/HLU with totals + 18-dot ribbon, HLL with empty state + disabled CTA + tooltip
2. **Click HPV** → HospitalDetail with 2 collapsible sections + "Escanear todas" button in Compilaciones header
3. **Click a sigla** → DetailPanel renders: sigla + label + 5xl number + pills + breakdown table + override panel
4. **Click count in CategoryRow** → InlineEditCount appears, type new value, Enter → dot turns violet + Manual badge appears
5. **Type in OverridePanel** → SaveIndicator: saving → saved → idle
6. **Click PDF in FileList** → Radix Dialog opens, Tab cycles within (focus trap), Esc closes
7. **"Generar Excel del mes"** → toast bottom-right "Excel guardado en …"
8. **Trigger OCR fail** (e.g., delete a folder mid-scan or use a missing path) → toast error
9. **Grep `bg-slate-` and `bg-indigo-` in JSX** — empty
10. **Bundle size** — `cd frontend && npm run build`, sum the `gzip:` sizes of every `dist/assets/index-*.js` file (the JS bundle). Compare to the baseline measured in Task 0. Delta should be ≤ +25 KB gzipped. WOFF2 font files DO NOT count toward this measurement (they're separate cacheable assets, not part of the JS bundle).
11. **No console errors** during flow
12. **Visual: no emoji/unicode glyphs** anywhere (⚠ ⟳ ✕ ✓ ○ ●)
13. **Tooltips** delay 300ms — hover a sigla → label appears after ~300ms
14. **CategoryRow row height** = 32px (h-8)
15. **Tabular-nums alignment** — counts in CategoryRow column line up vertically

If any of these fail, fix before tagging.

- [ ] **Step 2: Update CLAUDE.md**

In `a:/PROJECTS/PDFoverseer/CLAUDE.md`, replace the "## FASE 2 MVP" section (around line 145+) with a FASE 3 section underneath which subsumes FASE 2. Use Edit to insert this block (right after the existing FASE 2 MVP heading and before "Next (FASE 3)"):

```markdown
## FASE 3 polish — `po_overhaul` branch (shipped 2026-05-XX)

UI polish pass on top of FASE 2: design system with Radix Color tokens
+ lucide-react icons, 8 shared primitives under `frontend/src/ui/`,
inline-edit count cells, visible autosave indicator, Radix Dialog wrap
for PDFLightbox (a11y), sonner toasts, full Spanish microcopy.

- **Spec:** `docs/superpowers/specs/2026-05-13-fase-3-polish-design.md`
- **Plan:** `docs/superpowers/plans/2026-05-13-pdfoverseer-fase-3.md`
- **Tag:** `fase-3-polish` (local, awaiting push approval)
- **Bundle delta:** ~XX KB gzipped (from baseline NN KB to YY KB)
- **New deps:** `lucide-react`, `@radix-ui/colors`, `@radix-ui/react-{dialog,tooltip}`, `sonner`, `@fontsource/inter`, `@fontsource/jetbrains-mono`

### Design tokens
Defined in `frontend/tailwind.config.js`. Always use `po-*` tokens in JSX,
never raw `bg-slate-*` / `bg-indigo-*` / etc. (grep audit enforced at
commit-time; see CategoryRow + DetailPanel for reference usage).

### Next (FASE 4)
- Per-sigla OCR engine refinement against the real corpus
- Page-level cancellation (target <3s)
- HLL manual-entry flow (the disabled CTA on HospitalCard)
- Mostrar docs encontrados por archivo en FileList
- Multi-month overview
```

(Replace `XX` / `NN` / `YY` with actual measurements.)

- [ ] **Step 3: Commit CLAUDE.md**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(claude-md): FASE 3 polish section + design tokens reference

Adds the FASE 3 MVP entry (shipped 2026-05-13) underneath FASE 2,
documenting tokens, primitives, microcopy, and pending FASE 4 work.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Create local tag — DO NOT PUSH**

```bash
git tag fase-3-polish
git tag --list
```

Expected output includes: `fase-1-mvp`, `fase-2-mvp`, `fase-3-polish`.

**STOP HERE.** Do NOT run `git push origin po_overhaul` or `git push origin fase-3-polish`. The push gate is the controller's job after Daniel approves the manual smoke test.

Surface the following message to the controller:

> FASE 3 implementation complete. Tag `fase-3-polish` created locally on `po_overhaul`. Awaiting Daniel's approval to push to origin.

---

### Chunk 4 review checkpoint

After Tasks 25-29 commit cleanly:

- [ ] ~29 commits visible on `po_overhaul` (Tasks 0-29, some bundled into single commits per task instructions)
- [ ] Tag `fase-3-polish` exists locally
- [ ] `git log --oneline po_overhaul ^master | wc -l` — adds ~30 to whatever count was on top of FASE 2 (so ~100 total commits ahead of master)
- [ ] **Dispatch chunk-4 plan-reviewer subagent.** Pass: chunk 4 content + spec path. Fix any blocking findings.

---

## Final state

After all 4 chunks ship:

- Branch: `po_overhaul` (continues from FASE 2)
- Tag (local): `fase-3-polish`
- Push: pending Daniel's smoke approval
- Deps added: 7 (3 lucide/sonner/radix-colors + 2 radix-react + 2 fontsource)
- Files created: 12 (8 primitives + 2 labels + 1 hook + 1 CategoryGroup)
- Files deleted: 5 (4 dead components + 1 ConfidenceBadge + 1 README)
- Files modified: ~14 components + 3 lib/config files
- Lines changed: net positive (~1500-2500 additions, ~800-1200 deletions)
- Bundle delta: ≤ +25 KB gzipped

**Out-of-scope from this plan (deferred to FASE 4):**
- Per-sigla OCR engine refinement
- Page-level cancellation
- HLL manual-entry flow
- Multi-month overview
- Mostrar docs encontrados por archivo en FileList
- Light mode / responsive / keyboard shortcuts

The base is solid; FASE 4 can take the OCR engines into a real refinement pass against the real corpus.
