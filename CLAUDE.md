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
- **Working branch:** `po_overhaul` — the single active branch (see "Consolidación" below). Work here directly; push at the end of each round.

### Worktrees

**Location:** `.worktrees/` (project-local, hidden)

**Convention:** Work directly on `po_overhaul` in the main checkout. Do **not** leave feature worktrees unmerged — that debt has bitten us before. If a worktree is used for isolation, fast-forward it into `po_overhaul`, push, and delete it before calling the work done.

**Old foreign worktrees** (NOT merged into `po_overhaul` — predate the consolidation, unrelated to current work; kept only as branch refs):
- `feature/crop-selector` — UI crop region selector (unmerged MVP)
- `feature/ocr-matcher` — fuzzy OCR pattern generator (unmerged)

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
- **Branches:** Work directly on `po_overhaul` (the single active branch); only branch off for genuinely isolated experiments, and fast-forward + delete them when done
- **Tests:** Always pass before merge (no skipped/pending tests)
- **DB mocking:** Avoid mocking in tests — use real fixtures where possible
- **Worktrees:** Use `.worktrees/<name>` only for isolated experiments, and close them (FF → push → delete) before declaring done — do not accumulate unmerged worktrees

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
- **Frontend design tokens:** Always use `po-*` tokens in JSX (defined in `frontend/tailwind.config.js`), never raw `bg-slate-*`/`bg-indigo-*`/etc. 8 shared primitives live under `frontend/src/ui/`; `Badge.jsx` tones `iris/jade/amber` map to the existing `po-override-*`/`po-confidence-high-*`/`po-suspect-*` tokens. See `CategoryRow` + `DetailPanel` for reference usage.

### Guardrails & Hooks

**Hookify rules** (`.claude/hookify.*.local.md`) enforce code quality + safety at file write time:

| Rule | Type | Purpose |
|------|------|---------|
| **eval-before-core** | warn | Inference changes must be prototyped in `eval/inference_tuning/inference.py` first |
| **no-bare-except** | **BLOCK** | All exception handlers must catch specific types |
| **no-shell-true** | **BLOCK** | Never use `shell=True` in subprocess calls |
| **no-sql-fstrings** | **BLOCK** | SQL queries must use `?` parameterized form |
| **no-print-in-libs** | warn | Use `logging.getLogger(__name__)` in library code |
| **ruff-before-done** | warn | Verify `ruff check .` passes before stopping |
| **no-legacy-typing** | warn | Use Python 3.10+ syntax (`X \| None` not `Optional[X]`) |
| **bump-version-tags** | **BLOCK** | Bump a version tag in `core/utils.py` before editing `core/{pipeline,ocr,inference,image}.py` or `vlm/*.py` |
| **constants-in-utils** | warn | Pipeline constants belong in `core/utils.py` |
| **no-db-mocking** | warn | Never mock database in tests |
| **torch-try-except** | warn | Torch imports must be wrapped in try/except |

**Native hooks** (`.claude/settings.json`):
- **PreToolUse** (Write|Edit): Guards hand-editable deliverables (`.xlsx/.docx/.pptx/.pdf`). If the target already exists, makes a dated `<file>.bak-<ts>` backup and returns `permissionDecision: ask` so the overwrite is confirmed — never lose hand-edited work again (`guard-editable-deliverables.py`)
- **PostToolUse** (Edit|Write): Auto-runs `ruff format` on `.py` files (format only — `--fix` was removed so the autofix can't strip an import mid-edit; lint reporting is left to `ruff-before-done` + the pre-commit `ruff check .` gate)
- **PostToolUse** (WebFetch|WebSearch): Injects an "untrusted web content" prompt-injection warning next to fetched content
- **PostCompact**: Re-injects `.claude/context-essentials.txt` after context compaction
- **Stop**: Non-blocking reminder when the current branch is ahead of its remote (`origin/<branch>`) — surfaces "N commits sin pushear" via `systemMessage`, honoring the push-at-close convention (`remind-push.py`)

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

## Consolidación de `po_overhaul` — rama única, sincronizada con origin (2026-06-03)

`po_overhaul` es la **rama única** del proyecto, con **todos** los avances
(ocr-per-sigla, worker-viewer-ux, y conteo-confiable MVP + rev-1 + rev-2) y
**pusheada a origin** (`origin/po_overhaul` == local, tags `conteo-confiable-*` +
demás milestones en origin). `crop-selector`/`ocr-matcher` son ramas viejas ajenas.

**Convención de trabajo (para que la deuda de merges no reaparezca):** trabajar
**directo en `po_overhaul`** en el repo principal y **pushear al cierre de cada
ronda**. NO abrir feature worktrees que quedan sin mergear. Si se usa un worktree
para algo aislado, cerrarlo (fast-forward a po_overhaul + push + borrar) antes de
darlo por terminado.

## Project history

Shipped milestones on `po_overhaul`, newest first. The full narrative (smoke notes,
"bugs caught", bundle deltas, new deps) lives in the per-milestone memory files
(`~/.claude/projects/.../memory/project_*`) and the git tags; specs/plans under
`docs/superpowers/{specs,plans}/`.

- **2026-06-04** — Refinement batches: filelist polish (alignment, chips → red dot), Excel `#REF!` fix + `no-store`, CPHS visible-only rename, V4 double-pass OCR preprocessing. Memory: `project_refinements_2026_06_04`.
- **2026-06-03 · tags `conteo-confiable-{mvp,rev-1,rev-2}`** — Per-file count as source of truth: honest "ready" model, `FIXED_PAGE_SIGLAS`, `per_file_method` chips, per-file OCR from the viewer, per-sigla cards (p25–p75 corpus range). Memory: `project_conteo_confiable_shipped`, `project_conteo_confiable_revision_planned`.
- **2026-06-02 · tag `worker-viewer-ux-mvp`** — Worker-count viewer UX: thumbnail column (lazy + WeakMap), fit-to-window + manual zoom, persistent shortcut legend, partial-count→0 fix (`compute_worker_count`).
- **2026-05-23 · tag `ocr-per-sigla-mvp`** — Per-sigla OCR flavors (22 verbatim) + Fase A/B calibration; audited 2026-06-01 (7 findings fixed). Memory: `project_ocr_per_sigla_shipped`.
- **2026-05-17 · tag `conteo-trabajadores-mvp`** — Feature 1: assisted worker-signer count; pdf.js viewer, keyboard + voice (es-CL via Web Speech). Memory: `project_feature1_shipped`.
- **2026-05-15 · tag `fase-5-mvp`** — History drill-in (`HistoryDrawer`), page-level cancel (<3 s), OCR auto-retry. Memory: `project_fase5_shipped`.
- **2026-05-14 · tag `fase-4-mvp`** — HLL manual entry, per-file docs in FileList, multi-month trend (SparkGrid). Memory: `project_fase4_shipped`.
- **2026-05-13 · tag `fase-3-polish`** — Design system (`po-*` tokens, 8 primitives), inline-edit cells, autosave indicator, sonner toasts. Memory: `project_fase3_shipped`.
- **2026-05-12 · tag `fase-2-mvp`** — Pass 1 (`filename_glob`, ~4 s on ABRIL) + pass 2 (OCR per cell, opt-in) + manual override + PDF lightbox; cell-state cascade (`filename_count`/`ocr_count`/`user_override`) resolved by the Excel writer.
- **2026-05-11 · tag `fase-1-mvp`** — Folder-driven overhaul: open `A:\informe mensual\<MES>\` → count 4 hospitals × 18 categories with filename-glob → write `RESUMEN_<YYYY>-<MM>.xlsx` from `data/templates/RESUMEN_template_v1.xlsx`.

**Voice (Feature 1):** Chrome + cloud Web Speech works (validated 2026-05-18); Brave impossible (strips Google's voice key, no SODA); on-device discarded. Keyboard counting works everywhere. Detail in `project_feature1_shipped`.

**Reverted/parked:** VLM integration (reverted 2026-03-30 — see postmortem in Links); Feature 2 boundary badges (parked — see `project_feature2_boundary_badges`).
