# PDFoverseer

**PDF document analyzer** that counts internal documents in lecture PDFs (CRS) using an OCR + AI inference engine.

## Quick Start

```bash
# Backend (inference + API)
source .venv-cuda/Scripts/activate  # or: .\.venv-cuda\Scripts\activate (Windows)
python server.py                     # FastAPI on http://localhost:8000

# Frontend (React UI)
cd frontend && npm run dev           # Vite on http://localhost:5173

# Tests
pytest
```

## Installation

```bash
# CPU-only (Tesseract + PyMuPDF)
pip install -r requirements.txt

# GPU (adds PyTorch CUDA for SR Tier 2 bicubic upscaling)
pip install -r requirements-gpu.txt
```

## Tech Stack

- **Backend:** Python 3.10+ with CUDA GPU, FastAPI, PyMuPDF, Tesseract
- **Frontend:** React + Vite, react-zoom-pan-pinch
- **OCR Pipeline:** V4 (6 parallel Tesseract workers, Tier 1 direct + Tier 2 SR-GPU)
- **Inference:** 5-phase engine with Dempster-Shafer post-validation
- **VLM Module:** Vision-Language Model benchmark/sweep for OCR comparison

## Project Structure

```
├── core/           # OCR pipeline, inference engine, constants (see core/CLAUDE.md)
├── api/            # FastAPI routes, sessions, WebSocket (see api/CLAUDE.md)
├── vlm/            # VLM benchmark + sweep module (see vlm/CLAUDE.md)
├── eval/           # Evaluation harness: sweeps, fixtures, tests (see eval/CLAUDE.md)
├── tools/          # Standalone utilities (capture, pattern eval, regex test)
├── frontend/       # React UI (components, hooks, store)
├── tests/          # Integration + unit tests
├── models/         # Super-resolution models (FSRCNN_x4.pb, EDSR_x4.pb)
├── data/samples/   # 22 source PDFs for scan + fixture extraction
├── docs/           # Active research notes + referenced plans/postmortems
├── server.py       # FastAPI entry point
└── requirements.txt
```

## Development

### Git Info

- **Main branch:** `master`
- **Active worktrees:** `.worktrees/crop-selector`, `.worktrees/ocr-matcher`

### Worktrees

**Location:** `.worktrees/` (project-local, hidden)

**Active worktrees:**
- `.worktrees/crop-selector` → `feature/crop-selector` — UI crop region selector (unmerged, MVP complete)
- `.worktrees/ocr-matcher` → `feature/ocr-matcher` — fuzzy OCR pattern generator for "Pagina N de M" variants (unmerged)

**Other branches:**
- `research/pixel-density` — pixel density research (no worktree, checked out directly when needed)

**Setup:** Use `superpowers:using-git-worktrees` skill to create isolated workspaces.

### Key Commands

| Command | Purpose |
|---------|---------|
| `python server.py` | Start FastAPI backend + WebSocket |
| `cd frontend && npm run dev` | Start React dev server |
| `pytest` | Run test suite |
| `ruff check .` | Lint (must be 0 violations before commit) |

## Conventions

### Git & Workflow
- **Commits:** English, format: `type(scope): message`
  - Examples: `feat(ocr): add SR tier 2`, `fix(inference): D-S calibration`
- **Branches:** Feature branches from `master` (or `cuda-gpu` when working on GPU features)
  - Pattern: `feature/name` or `fix/issue-name`
- **Tests:** Always pass before merge (no skipped/pending tests)
- **DB mocking:** Avoid mocking in tests — use real fixtures where possible
- **Worktrees:** Use `.worktrees/<name>` for isolated feature work (see `superpowers:using-git-worktrees`)

### Code Quality
- **Linting:** `ruff check .` must report **0 violations** before committing
  - Config in `pyproject.toml`; rules: E, F, W, I (isort), UP (pyupgrade)
  - Intentional late imports (after `sys.path` manipulation): suppress with `# noqa: E402`
- **Dead code:** Remove unused imports, variables, and unreachable assignments — never commit them
- **No bare `except:`** — catch specific types (`except ValueError`, `except Exception` at minimum)
- **No `print()` in library code** — use `logging.getLogger(__name__)`; `print()` only in CLI entry points and standalone tools

### Types & Docstrings
- **Type annotations:** Use Python 3.10+ syntax: `X | None` not `Optional[X]`, `list[X]` not `List[X]`
- **Docstrings:** Public entry points (functions callable from outside the module) need Google-style docstrings with `Args:` and `Returns:` sections

### Architecture
- **Constants:** Magic numbers belong in `core/utils.py` (pipeline/inference config) or at module level — never inline
- **One responsibility per file:** Each module has a single clear purpose; if a file is doing two things, split it
- **Module docs:** New packages/modules get a `README.md` explaining their purpose, files, and usage

### Guardrails & Hooks

**Hookify rules** (`.claude/hookify.*.local.md`) enforce code quality + safety at file write time:

| Rule | Type | Purpose |
|------|------|---------|
| **eval-before-core** | warn | Inference changes must be tested in `eval/inference.py` first |
| **no-bare-except** | **BLOCK** | All exception handlers must catch specific types |
| **no-shell-true** | **BLOCK** | Never use `shell=True` in subprocess calls |
| **no-sql-fstrings** | **BLOCK** | SQL queries must use `?` parameterized form |
| **no-print-in-libs** | warn | Use `logging.getLogger(__name__)` in library code |
| **ruff-before-done** | warn | Verify `ruff check .` passes before stopping |
| **no-legacy-typing** | warn | Use Python 3.10+ syntax (`X \| None` not `Optional[X]`) |
| **bump-version-tags** | warn | Update version tags after pipeline changes |
| **constants-in-utils** | warn | Pipeline constants belong in `core/utils.py` |
| **no-db-mocking** | warn | Never mock database in tests |
| **torch-try-except** | warn | Torch imports must be wrapped in try/except |

**Native hooks** (`.claude/settings.json`):
- **PostToolUse** (Edit|Write): Auto-runs `ruff check --fix` + `ruff format` on `.py` files
- **PostCompact**: Re-injects `.claude/context-essentials.txt` after context compaction

## Compaction

When compacting, preserve:
- Complete list of files modified in this session
- Errors encountered and how they were resolved
- Architectural decisions made during the session
- Current task progress and next steps

## Links

- **VLM integration postmortem:** `docs/superpowers/reports/2026-03-29-vlm-integration-postmortem.md`
- **Pixel density README:** `eval/pixel_density/README.md`
- **Eval README:** `eval/README.md`
- **Core README:** `core/README.md`

## Documentation Access (AgentSearch)

When you need current documentation for any library used in this project, use `npx nia-docs` to query it directly:

```bash
npx nia-docs <docs-url> -c "tree -L 1"     # Browse structure
npx nia-docs <docs-url> -c "cat <page>.md"  # Read a page
npx nia-docs <docs-url> -c "grep -rl '<term>' ."  # Search
```

Common URLs: [PyMuPDF](https://pymupdf.readthedocs.io) | [FastAPI](https://fastapi.tiangolo.com) | [Tesseract](https://tesseract-ocr.github.io/tessdoc/) | [React](https://react.dev) | [Vite](https://vite.dev/guide/)

## Pending Work

- **INS_31:** ~~Last-page inference gap~~ FIXED (2026-03-26). Tray UX improvements still pending.
- **VLM integration:** ~~Attempted~~ REVERTED (2026-03-30). See postmortem in Links.
- **Browse UX:** `/api/browse` uses server-side tkinter chooser — only works with local display

## Consolidación de `po_overhaul` (2026-06-03)

`po_overhaul` es ahora la **rama única** con todos los avances: se fusionaron
`feature/ocr-per-sigla` (PR #1, refinamiento OCR per-sigla) y
`feature/worker-viewer-ux` — **merges limpios, cero conflictos**. HEAD `a81a016`.
Verificado: backend `598 passed / 52 skipped / 0 failed` + ruff limpio; frontend
vitest `55/55` + build OK. (`crop-selector`/`ocr-matcher` son ramas viejas ajenas.)

## Worker-viewer UX — `po_overhaul` (shipped 2026-06-02, tag `worker-viewer-ux-mvp`)

Mejoras al visor de conteo de trabajadores (Feature 1): **columna de miniaturas**
del PDF actual (lazy + WeakMap cache, badge de conteo por página), **ajuste-a-ventana
+ zoom manual por página** (`useFitScale` + `computeFitScale`; el zoom se resetea al
cambiar de página), **leyenda de atajos persistente** (`WORKER_SHORTCUTS` fuente única),
y un **fix del conteo parcial → 0** en el DetailPanel: `computeWorkerCount` filtraba
todas las marcas cuando `fileNames` era un array vacío (`[]` truthy en JS); ahora
espeja al backend (`compute_worker_count`, que no filtra con `per_file` vacío).
Spec/plan: `docs/superpowers/{specs,plans}/2026-06-02-*worker-viewer-ux*`.

## Conteo confiable / orden de carpeta / revisión por archivo — PLANEADO (spec+plan listos)

Próxima obra sobre `po_overhaul` consolidado (ejecución in-session, worktree
`.worktrees/conteo-confiable`). Modelo de "listo" honesto (verde solo si todos los
archivos 1-página, o sigla de páginas-fijas, o OCR/override/`confirmed`),
`FIXED_PAGE_SIGLAS={bodega,ext,caliente,herramientas_elec,exc}` (páginas=docs sin OCR),
flag `confirmed` + endpoint, lista 1-18 sin agrupar, origen "Estructura", FileList en
grilla + scroll del nombre, lightbox per-file. **Spec:**
`docs/superpowers/specs/2026-06-02-conteo-confiable-y-revision-design.md`. **Plan:**
`docs/superpowers/plans/2026-06-02-pdfoverseer-conteo-confiable.md` (9 tasks, 3 chunks).

## Feature 1 — Conteo asistido de trabajadores firmantes — `po_overhaul` branch (shipped 2026-05-17)

Conteo manual asistido de los trabajadores que firman las listas de asistencia
en los PDFs de `charla` / `chintegral`. El operador abre un visor pdf.js, marca
el número de firmantes por página (teclado o voz) y la suma alimenta el Excel.

1. **Modelo de datos + cascada (backend)**: la celda gana `worker_marks`
   (`{archivo: [{page, count}]}`), `worker_status` (`en_progreso`/`terminado`)
   y `worker_cursor`; el total se deriva con `compute_worker_count` — nunca se
   almacena. `PATCH …/cells/{h}/{s}/worker-count` persiste las marcas. El writer
   emite los rangos `{HOSP}_workers_{purpose}`
   (`WORKER_PURPOSE = {charla: chgen, chintegral: chintegral}`) → filas 29/30
   del template; las filas HH 13/14 ya traen las fórmulas (`=fila29*0.25`,
   `=fila30*0.5`). `/output` devuelve `worker_warnings` con las celdas
   charla/chintegral incompletas.
2. **Visor pdf.js (frontend)**: `WorkerCountViewer` monta `pdfjs-dist` con
   paginación continua multi-PDF; `WorkerBubble` (marca flotante de 3 estados),
   `WorkerHud` (panel lateral con total + `SaveIndicator`), autosave debounced.
   Un PDF que no abre se puede saltar — el HUD y el teclado siguen vivos.
3. **Conteo por teclado y voz**: teclado (dígitos, `PgDn`/`PgUp` fija-avanza,
   `Supr`, `E`, `M`); voz vía `useSpeechNumber` (Web Speech API, es-CL) +
   `parseSpanishNumber` (números 0-999, suite vitest). `M` pausa el micrófono;
   el chip de micrófono reusa el primitive `Badge`.
4. **Integración UI**: módulo "Conteo de trabajadores" en el `DetailPanel` de
   las celdas charla/chintegral; al "Generar Excel", `MonthOverview` muestra un
   `toast.warning` con las celdas incompletas junto al toast de éxito.

- **Spec:** `docs/superpowers/specs/2026-05-16-conteo-trabajadores-design.md`
- **Plan:** `docs/superpowers/plans/2026-05-16-pdfoverseer-conteo-trabajadores.md`
  (22 tasks, 4 chunks + Spike S1)
- **Tag:** `conteo-trabajadores-mvp` (local, awaiting push approval)
- **Bundle:** main JS gzipped 93.66 → 243.57 kB — el salto es `pdfjs-dist`,
  intrínseco a un visor de PDF; el `pdf.worker.min.mjs` (~1.2 MB) se sirve como
  archivo aparte. Sin presupuesto que vigilar para esta app single-user/LAN.
- **New deps:** `pdfjs-dist` (visor), `vitest` (devDep — suite del parser).

### Bugs caught en revisión (commits 2f15036, b792faa, 4555a8e)
1. `PdfPage` no liberaba los recursos del `PDFPageProxy` en el cleanup → fuga
   de memoria al paginar. Fix: `page.cleanup()`.
2. `WorkerCountViewer` hacía early-return ante un error de carga, matando el
   HUD y el handler de teclado → un PDF roto bloqueaba la celda entera. Fix:
   el error se muestra en el panel izquierdo y el visor sigue vivo (spec §10).
3. `useSpeechNumber` dejaba el chip en "error" tras un reinicio automático del
   reconocedor. Fix: un handler `onstart` restablece "listening" en cada
   (re)arranque.

### Voz — validada 2026-05-18 (Spike S1 resuelto)
El smoke de integración (teclado, Excel, `worker_warnings`) pasó. La voz se
depuró a fondo con chrome-devtools:
- **Chrome: funciona** — Web Speech API de nube; Daniel validó el dictado real,
  latencia aceptable. Hay una pausa breve (~0.8 s) entre guardar un número y
  reanudar la escucha — es el `audiostart` del reinicio del reconocedor en modo
  `continuous`, inherente al Web Speech API; no se optimiza.
- **Brave: imposible** — quita la API key del servicio de voz de Google (la
  nube queda como no-op silencioso) y tampoco distribuye el componente SODA
  (on-device también muerto). Para voz hay que usar Chrome; el conteo por
  teclado sí funciona en Brave.
- **On-device (`SpeechRecognition` con `processLocally`): descartado** — se
  probó (Chrome 148 instala el modelo `SODA es-ES`), pero el motor on-device
  oye el audio (`speechstart` dispara) y no transcribe nada (0 eventos
  `onresult`, es-CL/es-ES, con y sin flags). El puente Web Speech → on-device
  para español no funciona. NO reintentar; `useSpeechNumber.js` se mantiene en
  la ruta de nube.

### Next (roadmap restante)
- Refinamiento de motores OCR por tipo de documento (cada doc type con sus
  parámetros propios; ver memoria `project_ocr_refinement_deferred`).
- Feature 2 — badges de inicio-de-documento en el visor + toggle que corrige el
  conteo (ver memoria `project_feature2_boundary_badges`). Orden del roadmap:
  refinamiento OCR → feature 2.

### FASE 5 UX slice — predecessor, `po_overhaul` branch (shipped 2026-05-15)

Slice UX cerrando 3 pendientes del roadmap post-FASE 4:

1. **Histórico drill-in**: click en celda del SparkGrid abre `HistoryDrawer`
   (primitive `ui/Drawer.jsx` no-modal); serie de 12 meses con stats, gráfico
   de línea y tabla mes-a-mes con chips de método. Read-only, estado
   `historyDrawer` en Zustand, cero backend (lee la cache de `useHistoryStore`).
2. **Cancelación a nivel de página**: `count_paginations` y `count_form_codes`
   reciben el `CancellationToken` y lo chequean por página (levanta
   `CancelledError`); un cancel se honra en <3 s.
3. **Auto-retry OCR**: `_ocr_worker` reintenta un scan fallido 2× en silencio
   (`OCR_RETRY_COUNT`/`OCR_RETRY_BACKOFF_S` en `core/utils.py`); un
   `CancelledError` nunca dispara retry.

- **Spec:** `docs/superpowers/specs/2026-05-15-fase-5-design.md`
- **Plan:** `docs/superpowers/plans/2026-05-15-pdfoverseer-fase-5.md`
- **Tag:** `fase-5-mvp` (local, awaiting push approval)
- **Bundle delta:** +1.28 kB gzipped (baseline FASE 4 92.38 kB → 93.66 kB).
  Sin nuevas deps; todo sobre primitives existentes.
- **New deps:** ninguna

#### Smoke bugs caught (commits 9e4b312, 9afddfe, 0a7e7c5)
1. `Drawer` dejaba el foco atrapado dentro del panel `aria-hidden` al cerrar
   con la X. Fix: al cerrar, devuelve el foco al elemento que lo abrió.
2. `HistoryDrawer` parpadeaba al estado vacío durante los 200 ms de la
   animación de cierre (los props caen a null). Fix: congela el último
   contenido real mientras se desliza fuera.
3. Una celda OCR interrumpida quedaba atascada en "Escaneando…" — el evento
   `scan_cancelled` actualizaba `scanProgress` pero nunca limpiaba
   `scanningCells`. Fix: ambos eventos terminales vacían el set.

#### Next (roadmap restante)
- Refinamiento de motores OCR por tipo de documento (fase FINAL — cada doc
  type con sus parámetros propios; ver memoria `project_ocr_refinement_deferred`).

### FASE 4 UX slice — predecessor, `po_overhaul` branch (shipped 2026-05-14)

Slice UX cerrando 3 pendientes del roadmap post-FASE 3:

1. **HLL manual-entry**: HospitalCard CTA "Llenar manualmente →" cuando
   `state==="missing"`, HospitalDetail `mode="manual"` (Zustand-based, no
   router), focus auto-shift en Enter, 18 siglas siempre visibles, audit
   trail con `method="manual"` (literal FASE 2 reusado).
2. **Docs por archivo en FileList**: `ScanResult.per_file` propagado por
   scanners (simple_factory, art, charla, _header_detect_base); FileList
   row con `Npp + Ndocs editable + OriginChip` (OCR/R1/manual);
   `compute_cell_count` Python + `cellCount.js` JS espejados con fixture
   compartido en `tests/fixtures/cell_count_cases.json`.
3. **Multi-mes tendencia**: Toggle [Mes actual]/[Histórico] en
   MonthOverview (state Zustand, sin URL); SparkGrid 18×4 con sparklines
   de 12 meses sobre `historical_counts` via `query_range`; anomalías
   >30% en ámbar (`po-suspect`, baseline ≥6); `useHistoryStore` con cache
   módulo-level singleton.

- **Spec:** `docs/superpowers/specs/2026-05-14-fase-4-design.md`
- **Plan:** `docs/superpowers/plans/2026-05-14-pdfoverseer-fase-4.md`
- **Tag:** `fase-4-mvp` (local, awaiting push approval)
- **Bundle delta:** +2.17 kB gzipped (baseline FASE 3 90.23 kB → 92.40 kB).
  Casi todo construido sobre primitives FASE 3, sin nuevas deps.
- **New deps:** ninguna

#### Smoke bugs caught (commit cf5e1cb)
1. `HospitalCard` referenced `<Tooltip>` sin importarlo (latent FASE 3 bug).
2. `HospitalDetail` filtraba siglas con `cells[s]` truthy → HLL manual mode
   landing en lista vacía. Fix: en `mode="manual"` siempre 18 rows.
3. `FileList` no refrescaba el row tras `savePerFileOverride` (cell state
   updated, files-state stale). Fix: optimistic local update en `onCommit`.

#### Next (FASE 5)
- Per-sigla OCR engine refinement contra el corpus real
- Page-level cancellation (target <3s)
- Drill-in del histórico (vista detalle de serie completa con números
  mes-a-mes)
- Auto-retry on OCR failure
- Refactor: extract `SIGLAS` a `frontend/src/lib/sigla-labels.js` (3 copias
  duplicadas en HospitalCard, HospitalDetail, SparkGrid)

### FASE 3 polish — predecessor, `po_overhaul` branch (shipped 2026-05-13)

UI polish pass on top of FASE 2: design system con Radix Color tokens
+ lucide-react icons, 8 shared primitives under `frontend/src/ui/`,
inline-edit count cells, visible autosave indicator, Radix Dialog wrap
for PDFLightbox (a11y), sonner toasts, full Spanish microcopy.

- **Spec:** `docs/superpowers/specs/2026-05-13-fase-3-polish-design.md`
- **Plan:** `docs/superpowers/plans/2026-05-13-pdfoverseer-fase-3.md`
- **Tag:** `fase-3-polish` (local, awaiting push approval)
- **Bundle delta:** +38.93 kB gzipped (baseline 51.30 kB → 90.23 kB).
- **New deps:** `lucide-react`, `@radix-ui/colors`, `@radix-ui/react-dialog`,
  `@radix-ui/react-tooltip`, `sonner`, `@fontsource/inter`,
  `@fontsource/jetbrains-mono`

#### Design tokens
Defined in `frontend/tailwind.config.js`. Always use `po-*` tokens in JSX,
never raw `bg-slate-*` / `bg-indigo-*` / etc. (grep audit enforced at
commit-time; see CategoryRow + DetailPanel for reference usage). FASE 4
extendió `Badge.jsx` con tones `iris/jade/amber` mapeados a `po-override-*`
/ `po-confidence-high-*` / `po-suspect-*` ya existentes (sin nuevos tokens).

### FASE 2 MVP — predecessor, `po_overhaul` branch (shipped 2026-05-12)

Pase 1 (filename_glob, ~4s on ABRIL) + pase 2 (OCR per cell, opt-in
via UI) + manual override + PDF preview lightbox. Cell state stores
`filename_count`, `ocr_count`, `user_override`, `override_note` as
independent fields; Excel writer applies the priority cascade. The
`/output` endpoint now also UPSERTs `historical_counts` with a `method`
audit (`override` vs OCR technique vs `filename_glob`).

- **Spec:** `docs/superpowers/specs/2026-05-12-fase-2-design.md`
- **Plan:** `docs/superpowers/plans/2026-05-12-pdfoverseer-fase-2.md`
- **Tag:** `fase-2-mvp` (local, awaiting push approval)
- **FASE 3 polished it (above):** auto-retry on OCR failure, page-level cancellation,
  per-sigla OCR engine refinement against the real corpus (header_detect
  semantic, ART corner_count gap — see Known Limitations in the plan).

### FASE 1 MVP — predecessor, `research/pixel-density` branch (shipped 2026-05-11)

Folder-driven overhaul of the UI: open `A:\informe mensual\<MES>\` and the
app counts 4 hospitals × 18 categories with filename-glob, then writes
`RESUMEN_<YYYY>-<MM>.xlsx` via `data/templates/RESUMEN_template_v1.xlsx`.

- **Spec:** `docs/superpowers/specs/2026-05-11-pdfoverseer-overhaul-design.md`
- **Plan:** `docs/superpowers/plans/2026-05-11-pdfoverseer-overhaul-fase-1.md`
- **Tag:** `fase-1-mvp`
