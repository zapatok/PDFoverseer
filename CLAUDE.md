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

## FASE 2 MVP — `po_overhaul` branch (shipped 2026-05-12)

Pase 1 (filename_glob, ~4s on ABRIL) + pase 2 (OCR per cell, opt-in
via UI) + manual override + PDF preview lightbox. Cell state stores
`filename_count`, `ocr_count`, `user_override`, `override_note` as
independent fields; Excel writer applies the priority cascade. The
`/output` endpoint now also UPSERTs `historical_counts` with a `method`
audit (`override` vs OCR technique vs `filename_glob`).

- **Spec:** `docs/superpowers/specs/2026-05-12-fase-2-design.md`
- **Plan:** `docs/superpowers/plans/2026-05-12-pdfoverseer-fase-2.md`
- **Tag:** `fase-2-mvp` (local, awaiting push approval)
- **Next (FASE 3):** auto-retry on OCR failure, page-level cancellation,
  per-sigla OCR engine refinement against the real corpus (header_detect
  semantic, ART corner_count gap — see Known Limitations in the plan).

### FASE 1 MVP — predecessor, `research/pixel-density` branch (shipped 2026-05-11)

Folder-driven overhaul of the UI: open `A:\informe mensual\<MES>\` and the
app counts 4 hospitals × 18 categories with filename-glob, then writes
`RESUMEN_<YYYY>-<MM>.xlsx` via `data/templates/RESUMEN_template_v1.xlsx`.

- **Spec:** `docs/superpowers/specs/2026-05-11-pdfoverseer-overhaul-design.md`
- **Plan:** `docs/superpowers/plans/2026-05-11-pdfoverseer-overhaul-fase-1.md`
- **Tag:** `fase-1-mvp`
